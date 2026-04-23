from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any


class RunStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}

    def create_run(self, *, run_id: str, base_url: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._runs[run_id] = {
                "run_id": run_id,
                "base_url": base_url,
                "status": "queued",
                "created_at": now,
                "updated_at": now,
                "current_stage": "Queued",
                "events": [
                    {
                        "timestamp": now,
                        "level": "info",
                        "message": f"Run queued for {base_url}",
                    }
                ],
                "pages": [],
                "summary_path": None,
                "report_url": None,
            }

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            return None if run is None else self._clone(run)

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            items = [self._clone(item) for item in self._runs.values()]
        return sorted(items, key=lambda item: item["created_at"], reverse=True)

    def update_run(self, run_id: str, **updates: Any) -> None:
        with self._lock:
            run = self._runs[run_id]
            run.update(updates)
            run["updated_at"] = datetime.now(UTC).isoformat()

    def append_event(self, run_id: str, *, level: str, message: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            run["events"].append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "level": level,
                    "message": message,
                }
            )
            run["updated_at"] = datetime.now(UTC).isoformat()

    def set_pages(self, run_id: str, pages: list[dict[str, Any]]) -> None:
        with self._lock:
            self._runs[run_id]["pages"] = pages
            self._runs[run_id]["updated_at"] = datetime.now(UTC).isoformat()

    def _clone(self, value: dict[str, Any]) -> dict[str, Any]:
        clone: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(item, list):
                clone[key] = [entry.copy() if isinstance(entry, dict) else entry for entry in item]
            elif isinstance(item, dict):
                clone[key] = item.copy()
            else:
                clone[key] = item
        return clone
