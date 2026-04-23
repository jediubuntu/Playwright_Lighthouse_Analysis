from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from controller.run_store import RunStore
from llm.navigator import NavigationLLM


class AnalysisOrchestrator:
    def __init__(self, *, base_dir: Path, reports_dir: Path, run_store: RunStore) -> None:
        self.base_dir = base_dir
        self.reports_dir = reports_dir
        self.run_store = run_store
        self.navigation_llm = NavigationLLM.from_environment()

    async def run(self, *, run_id: str, base_url: str) -> None:
        from controller.site_analyzer import analyze_site

        try:
            self._set_stage(run_id, "running", "Preparing analysis")
            self._event(run_id, "info", "Launching Playwright crawler and Lighthouse workflow")
            result = await analyze_site(
                run_id=run_id,
                base_url=base_url,
                reports_dir=self.reports_dir,
                progress=self._progress_callback(run_id),
                navigation_llm=self.navigation_llm,
            )
            summary_path = self.reports_dir / run_id / "summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            self.run_store.set_pages(run_id, result["pages"])
            self.run_store.update_run(
                run_id,
                status="completed",
                current_stage="Completed",
                summary_path=str(summary_path),
                report_url=f"/reports/{run_id}",
            )
            self._event(run_id, "info", "Analysis completed")
        except Exception as exc:
            self.run_store.update_run(run_id, status="failed", current_stage="Failed")
            self._event(run_id, "error", f"Analysis failed: {exc}")

    def _progress_callback(self, run_id: str):
        def emit(stage: str, message: str, *, pages: list[dict[str, Any]] | None = None) -> None:
            self.run_store.update_run(run_id, current_stage=stage, status="running")
            self._event(run_id, "info", message)
            if pages is not None:
                self.run_store.set_pages(run_id, pages)

        return emit

    def _set_stage(self, run_id: str, status: str, stage: str) -> None:
        self.run_store.update_run(run_id, status=status, current_stage=stage)

    def _event(self, run_id: str, level: str, message: str) -> None:
        self.run_store.append_event(run_id, level=level, message=message)
