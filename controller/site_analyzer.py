from __future__ import annotations

import asyncio
import json
import re
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
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        pages: list[dict] = []
        visited_urls: set[str] = set()

        progress("Crawling", f"Opening base URL {base_url}")
        await page.goto(base_url, wait_until="networkidle", timeout=30000)
        await page.add_init_script(TAG_NAV_JS)
        await page.evaluate(TAG_NAV_JS)

        base_entry = await inspect_page(page=page, current_url=page.url)
        pages.append(base_entry)
        visited_urls.add(page.url)
        progress("Discovery", "Collected initial page details", pages=pages)

        candidates = dedupe_candidates(base_entry["navigation_candidates"])
        selected = await navigation_llm.choose_critical(base_url=base_url, candidates=candidates)
        progress("Navigation Selection", f"Selected {len(selected)} critical navigation targets", pages=pages)

        for candidate in selected:
            target_url = candidate.get("href")
            if not target_url:
                continue
            normalized = normalize_url(base_url, target_url)
            if not normalized or normalized in visited_urls:
                continue
            visited_urls.add(normalized)
            progress("Crawling", f"Navigating to {candidate['label']} -> {normalized}", pages=pages)
            try:
                await page.goto(normalized, wait_until="networkidle", timeout=30000)
                await page.evaluate(TAG_NAV_JS)
                page_entry = await inspect_page(page=page, current_url=page.url, source_label=candidate["label"])
                pages.append(page_entry)
                progress("Crawling", f"Captured {page.url}", pages=pages)
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
                    }
                )
                progress("Crawling", f"Failed to capture {normalized}: {exc}", pages=pages)

        progress("Lighthouse", "Running Lighthouse reports", pages=pages)
        for item in pages:
            if item.get("status") == "navigation_failed":
                continue
            report_paths = run_lighthouse(url=item["url"], output_dir=output_dir, slug=slugify(item["title"] or item["url"]))
            item["lighthouse"] = report_paths

        await context.close()
        await browser.close()

    return {
        "run_id": run_id,
        "base_url": base_url,
        "pages": pages,
    }


async def inspect_page(*, page, current_url: str, source_label: str | None = None) -> dict:
    title = await page.title()
    navigation_candidates = await page.evaluate(NAVIGATION_JS)
    return {
        "title": title,
        "url": current_url,
        "source_label": source_label or "base",
        "status": "ok",
        "navigation_candidates": navigation_candidates,
        "lighthouse": None,
    }


def dedupe_candidates(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in candidates:
        href = item.get("href") or ""
        label = item.get("label") or ""
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


def run_lighthouse(*, url: str, output_dir: Path, slug: str) -> dict[str, str]:
    html_path = output_dir / f"{slug}.lighthouse.html"
    json_path = output_dir / f"{slug}.lighthouse.json"
    command = [
        "npx",
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
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Lighthouse failed")

    return {
        "html_report": str(html_path),
        "json_report": str(json_path),
    }
