from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen


@dataclass
class NavigationCandidate:
    label: str
    href: str
    selector: str


class NavigationLLM:
    def __init__(self, *, api_key: str | None, base_url: str, model: str | None) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    @classmethod
    def from_environment(cls) -> "NavigationLLM":
        return cls(
            api_key=os.getenv("PLA_LLM_API_KEY"),
            base_url=os.getenv("PLA_LLM_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("PLA_LLM_MODEL"),
        )

    async def choose_critical(self, *, base_url: str, candidates: list[dict[str, str]]) -> list[dict[str, str]]:
        if not self.api_key or not self.model or not candidates:
            return candidates[:5]

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
            },
            method="POST",
        )
        with urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        selected = set(parsed.get("selected_labels", []))
        filtered = [item for item in candidates if item["label"] in selected]
        return filtered or candidates[:5]
