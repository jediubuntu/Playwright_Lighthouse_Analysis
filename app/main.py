from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from controller.orchestrator import AnalysisOrchestrator
from controller.run_store import RunStore

BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_DIR / "reports"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"

load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="Playwright Lighthouse Analysis")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/static-reports", StaticFiles(directory=str(REPORTS_DIR)), name="static-reports")

run_store = RunStore()
orchestrator = AnalysisOrchestrator(base_dir=BASE_DIR, reports_dir=REPORTS_DIR, run_store=run_store)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    runs = run_store.list_runs()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "runs": runs,
        },
    )


@app.post("/runs")
async def start_run(base_url: str = Form(...)) -> RedirectResponse:
    run_id = str(uuid.uuid4())
    run_store.create_run(run_id=run_id, base_url=base_url)
    asyncio.create_task(orchestrator.run(run_id=run_id, base_url=base_url))
    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)


@app.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_page(request: Request, run_id: str) -> HTMLResponse:
    run = run_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return templates.TemplateResponse(
        request,
        "run.html",
        {
            "request": request,
            "run_id": run_id,
            "run": run,
        },
    )


@app.get("/api/runs/{run_id}")
async def run_status(run_id: str) -> dict[str, Any]:
    run = run_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/reports/{run_id}", response_class=HTMLResponse)
async def report_view(request: Request, run_id: str) -> HTMLResponse:
    run = run_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    summary_path = run.get("summary_path")
    summary_data: dict[str, Any] | None = None
    if summary_path:
        report_path = Path(summary_path)
        if report_path.exists():
            summary_data = json.loads(report_path.read_text(encoding="utf-8"))

    return templates.TemplateResponse(
        request,
        "report.html",
        {
            "request": request,
            "run_id": run_id,
            "run": run,
            "summary": summary_data,
        },
    )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("PLA_APP_HOST", "127.0.0.1")
    port = int(os.getenv("PLA_APP_PORT", "8011"))
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
