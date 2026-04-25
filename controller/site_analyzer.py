from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urljoin, urlparse

from llm.navigator import NavigationLLM

NAVIGATION_JS = """
() => {
  const elements = Array.from(document.querySelectorAll('a, button'));
  return elements
    .map((element, index) => {
      const text = (element.innerText || element.textContent || '').replace(/\\s+/g, ' ').trim();
      const href = element.tagName.toLowerCase() === 'a' ? (element.href || '') : '';
      const role = element.getAttribute('role') || '';
      return {
        index,
        label: text,
        href,
        tag: element.tagName.toLowerCase(),
        role,
        selector: `[data-pla-nav="${index}"]`
      };
    })
    .filter(item => item.label && item.label.length <= 80);
}
"""

TAG_NAV_JS = """
() => {
  const elements = Array.from(document.querySelectorAll('a, button'));
  elements.forEach((element, index) => element.setAttribute('data-pla-nav', String(index)));
}
"""

REGION_PROFILES = [
    {
        "name": "India - Mumbai",
        "slug": "india-mumbai",
        "locale": "en-IN",
        "timezone_id": "Asia/Kolkata",
        "geolocation": {"latitude": 19.0760, "longitude": 72.8777},
        "extra_http_headers": {"Accept-Language": "en-IN,en;q=0.9"},
    },
    {
        "name": "US West - San Francisco",
        "slug": "us-west-san-francisco",
        "locale": "en-US",
        "timezone_id": "America/Los_Angeles",
        "geolocation": {"latitude": 37.7749, "longitude": -122.4194},
        "extra_http_headers": {"Accept-Language": "en-US,en;q=0.9"},
    },
    {
        "name": "Europe - London",
        "slug": "europe-london",
        "locale": "en-GB",
        "timezone_id": "Europe/London",
        "geolocation": {"latitude": 51.5072, "longitude": -0.1276},
        "extra_http_headers": {"Accept-Language": "en-GB,en;q=0.9"},
    },
]


async def analyze_site(
    *,
    run_id: str,
    base_url: str,
    reports_dir: Path,
    progress,
    navigation_llm: NavigationLLM,
) -> dict:
    from playwright.async_api import async_playwright

    output_dir = reports_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        tasks = [
            analyze_region(
                playwright=playwright,
                profile=profile,
                base_url=base_url,
                output_dir=output_dir,
                progress=progress,
                navigation_llm=navigation_llm,
            )
            for profile in REGION_PROFILES
        ]
        region_results = await asyncio.gather(*tasks)

    return {
        "run_id": run_id,
        "base_url": base_url,
        "regions": region_results,
        "pages": flatten_pages(region_results),
    }


async def analyze_region(*, playwright, profile: dict, base_url: str, output_dir: Path, progress, navigation_llm: NavigationLLM) -> dict:
    progress(
        "Preparing analysis",
        f"Starting virtual region profile: {profile['name']}",
        region_name=profile["name"],
    )
    region_output_dir = output_dir / profile["slug"]
    region_output_dir.mkdir(parents=True, exist_ok=True)

    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        locale=profile["locale"],
        timezone_id=profile["timezone_id"],
        geolocation=profile["geolocation"],
        permissions=["geolocation"],
        extra_http_headers=profile["extra_http_headers"],
    )
    page = await context.new_page()

    try:
        pages, selected = await crawl_region(
            page=page,
            base_url=base_url,
            progress=progress,
            navigation_llm=navigation_llm,
            region_name=profile["name"],
        )

        progress(
            "Lighthouse",
            f"Running Lighthouse for {profile['name']}",
            pages=pages,
            region_name=profile["name"],
        )
        for item in pages:
            if item.get("status") == "navigation_failed":
                continue
            item["lighthouse"] = run_lighthouse(
                url=item["url"],
                output_dir=region_output_dir,
                slug=slugify(item["title"] or item["url"]),
                region_name=profile["name"],
            )

        progress(
            "Completed",
            f"Completed virtual region profile: {profile['name']}",
            pages=pages,
            region_name=profile["name"],
        )
        return {
            "name": profile["name"],
            "slug": profile["slug"],
            "locale": profile["locale"],
            "timezone_id": profile["timezone_id"],
            "geolocation": profile["geolocation"],
            "selected_navigation": selected,
            "pages": pages,
            "report_dir": str(region_output_dir),
        }
    finally:
        await context.close()
        await browser.close()


async def crawl_region(*, page, base_url: str, progress, navigation_llm: NavigationLLM, region_name: str):
    pages: list[dict] = []
    visited_urls: set[str] = set()

    progress("Crawling", f"[{region_name}] Opening base URL {base_url}", region_name=region_name)
    await page.goto(base_url, wait_until="networkidle", timeout=60000)
    await page.add_init_script(TAG_NAV_JS)
    await page.evaluate(TAG_NAV_JS)

    base_entry = await inspect_page(page=page, current_url=page.url, region_name=region_name)
    pages.append(base_entry)
    visited_urls.add(page.url)
    progress("Discovery", f"[{region_name}] Collected initial page details", pages=pages, region_name=region_name)

    candidates = dedupe_candidates(base_entry["navigation_candidates"])
    selected = await navigation_llm.choose_critical(base_url=base_url, candidates=candidates)
    progress(
        "Navigation Selection",
        f"[{region_name}] Selected {len(selected)} critical navigation targets",
        pages=pages,
        region_name=region_name,
    )

    for candidate in selected:
        target_url = candidate.get("href")
        if not target_url:
            continue
        normalized = normalize_url(base_url, target_url)
        if not normalized or normalized in visited_urls:
            continue
        visited_urls.add(normalized)
        progress(
            "Crawling",
            f"[{region_name}] Navigating to {candidate['label']} -> {normalized}",
            pages=pages,
            region_name=region_name,
        )
        try:
            await page.goto(normalized, wait_until="networkidle", timeout=60000)
            await page.evaluate(TAG_NAV_JS)
            page_entry = await inspect_page(
                page=page,
                current_url=page.url,
                source_label=candidate["label"],
                region_name=region_name,
            )
            pages.append(page_entry)
            progress("Crawling", f"[{region_name}] Captured {page.url}", pages=pages, region_name=region_name)
        except Exception as exc:
            pages.append(
                {
                    "title": candidate["label"],
                    "url": normalized,
                    "source_label": candidate["label"],
                    "status": "navigation_failed",
                    "error": str(exc),
                    "navigation_candidates": [],
                    "lighthouse": None,
                    "region_name": region_name,
                }
            )
            progress(
                "Crawling",
                f"[{region_name}] Failed to capture {normalized}: {exc}",
                pages=pages,
                region_name=region_name,
            )

    return pages, selected


async def inspect_page(*, page, current_url: str, source_label: str | None = None, region_name: str) -> dict:
    title = await page.title()
    navigation_candidates = await page.evaluate(NAVIGATION_JS)
    return {
        "title": title,
        "url": current_url,
        "source_label": source_label or "base",
        "status": "ok",
        "navigation_candidates": navigation_candidates,
        "lighthouse": None,
        "region_name": region_name,
    }


def flatten_pages(region_results: list[dict]) -> list[dict]:
    flattened: list[dict] = []
    for region in region_results:
        for page in region["pages"]:
            entry = dict(page)
            entry["region_name"] = region["name"]
            entry["region_slug"] = region["slug"]
            flattened.append(entry)
    return flattened


def dedupe_candidates(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    blocked_terms = {
        "basic_auth",
        "basic auth",
        "auth",
        "login",
        "logout",
        "sign in",
        "signin",
        "register",
    }

    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in candidates:
        href = (item.get("href") or "").strip()
        label = (item.get("label") or "").strip()
        combined = f"{label} {href}".lower()

        if any(term in combined for term in blocked_terms):
            continue

        key = f"{label}|{href}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def normalize_url(base_url: str, href: str) -> str | None:
    if not href:
        return None
    joined = urljoin(base_url, href)
    parsed = urlparse(joined)
    if parsed.scheme not in {"http", "https"}:
        return None
    return joined


def slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower() or "page"


def run_lighthouse(*, url: str, output_dir: Path, slug: str, region_name: str) -> dict[str, str]:
    html_path = output_dir / f"{slug}.report.html"
    json_path = output_dir / f"{slug}.report.json"

    npx_executable = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx_executable:
        raise RuntimeError("Could not find 'npx' on PATH. Install Node.js and ensure npx is available.")

    command = [
        npx_executable,
        "lighthouse",
        url,
        "--only-categories=performance,accessibility,best-practices,seo",
        "--preset=desktop",
        "--output=html",
        "--output=json",
        f"--output-path={output_dir / slug}",
        "--chrome-flags=--headless",
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0 and not (html_path.exists() and json_path.exists()):
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Lighthouse failed")

    warning = None
    if completed.returncode != 0:
        warning = "Lighthouse returned a non-zero exit code after writing the report files. The generated reports are still usable."

    return {
        "html_report": str(html_path),
        "json_report": str(json_path),
        "warning": warning,
        "region_name": region_name,
    }
