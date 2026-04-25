from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class NavigationCandidate:
    label: str
    href: str
    selector: str


class NavigationLLM:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str | None,
        max_retries: int = 2,
        retry_seconds: float = 10.0,
        timeout_seconds: int = 45,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_retries = max_retries
        self.retry_seconds = retry_seconds
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "NavigationLLM":
        return cls(
            api_key=(
                os.getenv("PLA_LLM_API_KEY")
                or os.getenv("GEMINI_API_KEY")
                or os.getenv("GOOGLE_API_KEY")
                or os.getenv("OPENAI_API_KEY")
            ),
            base_url=os.getenv(
                "PLA_LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"
            ),
            model=os.getenv("PLA_LLM_MODEL", "models/gemini-2.5-flash"),
            max_retries=int(os.getenv("PLA_LLM_MAX_RETRIES", "2")),
            retry_seconds=float(os.getenv("PLA_LLM_RETRY_SECONDS", "10")),
        )

    async def choose_critical(self, *, base_url: str, candidates: list[dict[str, str]]) -> list[dict[str, str]]:
        if not candidates:
            return []

        if not self.api_key or not self.model:
            print(f"[{ts()}] NavigationLLM unavailable; using heuristic fallback.")
            return self._fallback_candidates(candidates)

        payload = {
            "base_url": base_url,
            "candidates": candidates,
            "task": (
                "Pick the most critical navigation paths to audit with Lighthouse. "
                "Prefer primary navigation, product flows, key content hubs, pricing, login, signup, docs, and conversion pages. "
                "Return JSON with key selected_labels as a list of labels."
            ),
        }
        body = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "You choose critical website navigation actions for performance audits. Return strict JSON only.",
                },
                {"role": "user", "content": json.dumps(payload)},
            ],
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            data = self._send_with_retries(request)
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                text_parts = [
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                ]
                content = "\n".join(part for part in text_parts if part).strip()

            parsed = json.loads(content)
            selected = set(parsed.get("selected_labels", []))
            filtered = [item for item in candidates if item["label"] in selected]
            if filtered:
                print(f"[{ts()}] NavigationLLM selected {len(filtered)} critical paths using {self.model}.")
                return filtered
        except (LLMNavigationError, KeyError, IndexError, json.JSONDecodeError) as exc:
            print(f"[{ts()}] NavigationLLM failed: {exc}. Using heuristic fallback.")

        return self._fallback_candidates(candidates)

    def _fallback_candidates(self, candidates: list[dict[str, str]]) -> list[dict[str, str]]:
        scored = sorted(candidates, key=self._candidate_score, reverse=True)
        fallback = scored[:5]
        print(f"[{ts()}] NavigationLLM fallback selected {len(fallback)} paths.")
        return fallback

    def _candidate_score(self, item: dict[str, str]) -> tuple[int, int]:
        text = f"{item.get('label', '')} {item.get('href', '')}".lower()
        score = 0

        priority_terms = [
            ("pricing", 10),
            ("product", 9),
            ("products", 9),
            ("docs", 9),
            ("documentation", 9),
            ("features", 8),
            ("solutions", 8),
            ("platform", 8),
            ("about", 7),
            ("contact", 7),
            ("login", 7),
            ("sign in", 7),
            ("signin", 7),
            ("sign up", 7),
            ("signup", 7),
            ("register", 7),
            ("dashboard", 7),
            ("home", 6),
        ]
        for term, weight in priority_terms:
            if term in text:
                score += weight

        href = item.get("href", "").strip()
        label = item.get("label", "").strip()
        if href and href not in {"/", "#"}:
            score += 2
        if label:
            score += 1

        return score, -len(href)

    def _send_with_retries(self, request: Request) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                message = self._http_error_message(exc)
                retryable = exc.code in {408, 409, 429, 500, 502, 503, 504}
                if not retryable or attempt >= self.max_retries:
                    raise LLMNavigationError(message) from exc

                if exc.code == 429:
                    raise LLMNavigationError(message) from exc

                sleep_seconds = self._retry_after_seconds(exc) or self.retry_seconds
                print(
                    f"[{ts()}] NavigationLLM HTTP {exc.code}; retrying in {sleep_seconds:.1f}s "
                    f"({attempt + 1}/{self.max_retries})"
                )
                time.sleep(sleep_seconds)
            except URLError as exc:
                if attempt >= self.max_retries:
                    raise LLMNavigationError(f"NavigationLLM request failed: {exc.reason}") from exc
                print(
                    f"[{ts()}] NavigationLLM network error; retrying in {self.retry_seconds:.1f}s "
                    f"({attempt + 1}/{self.max_retries})"
                )
                time.sleep(self.retry_seconds)

        raise LLMNavigationError("NavigationLLM request failed after retries")

    def _retry_after_seconds(self, exc: HTTPError) -> float | None:
        retry_after = exc.headers.get("Retry-After")
        if not retry_after:
            return None
        try:
            return max(0.1, float(retry_after))
        except ValueError:
            return None

    def _http_error_message(self, exc: HTTPError) -> str:
        body = ""
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""

        if body:
            try:
                payload = json.loads(body)
                if isinstance(payload, dict):
                    detail = payload.get("error", {}).get("message") or body
                elif isinstance(payload, list) and payload and isinstance(payload[0], dict):
                    detail = payload[0].get("error", {}).get("message") or body
                else:
                    detail = body
            except json.JSONDecodeError:
                detail = body
        else:
            detail = exc.reason

        return f"NavigationLLM request failed with HTTP {exc.code}: {detail}"


class LLMNavigationError(RuntimeError):
    pass
