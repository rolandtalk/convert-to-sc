from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from pathlib import Path

from celery.result import AsyncResult
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.celery_app import celery_app
from app.config import settings
from app.db import (
    create_convert_run,
    fetch_picks,
    get_convert_run,
    init_db,
    latest_run,
    latest_runs,
    list_convert_runs,
    list_convert_symbols,
)
from app.jobs import shutdown_scheduler, start_scheduler
from app.tasks import build_convert_run_key, capture_convert_run_task, run_sctr_pipeline_task
from app.services.symbol_extract import extract_symbols


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
ARTIFACTS_DIR = settings.screenshot_output_dir


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="Convert to SC", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=ARTIFACTS_DIR), name="artifacts")


class ExtractRequest(BaseModel):
    text: str = Field(default="")


class ConvertRunRequest(BaseModel):
    text: str = Field(default="")
    symbols: list[str] = Field(default_factory=list)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/picks/latest")
def api_latest_picks(
    q: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
):
    run = latest_run()
    if not run:
        return {"status": "empty", "data": [], "total": 0, "page": page, "page_size": page_size}

    offset = (page - 1) * page_size
    total, rows = fetch_picks(int(run["id"]), q=q, offset=offset, limit=page_size)
    return {
        "status": "ok",
        "run": dict(run),
        "data": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.get("/api/runs/latest")
def api_latest_runs(limit: int = Query(default=10, ge=1, le=100)):
    rows = latest_runs(limit=limit)
    return {"status": "ok", "data": [dict(r) for r in rows]}


@app.post("/api/convert/extract")
def api_extract_symbols(payload: ExtractRequest):
    symbols = extract_symbols(payload.text)
    return {"status": "ok", "symbols": symbols, "count": len(symbols)}


@app.post("/api/convert/runs")
def api_create_convert_run(payload: ConvertRunRequest):
    symbols = payload.symbols or extract_symbols(payload.text)
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Source text is required.")
    if not symbols:
        raise HTTPException(status_code=400, detail="No symbols were found.")

    run_id = create_convert_run(
        run_key=build_convert_run_key(),
        source_text=payload.text.strip(),
        symbols=symbols,
    )
    task = capture_convert_run_task.delay(run_id=run_id)
    return {"status": "queued", "run_id": run_id, "task_id": task.id, "symbols": symbols}


@app.get("/api/convert/runs")
def api_list_convert_runs(limit: int = Query(default=10, ge=1, le=100)):
    rows = list_convert_runs(limit=limit)
    return {"status": "ok", "data": [dict(row) for row in rows]}


@app.get("/api/convert/runs/{run_id}")
def api_get_convert_run(run_id: int):
    run = get_convert_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    symbols = []
    for row in list_convert_symbols(run_id):
        item = dict(row)
        item["image_url"] = f"/artifacts/{item['image_path']}" if item.get("image_path") else None
        symbols.append(item)
    return {"status": "ok", "run": dict(run), "symbols": symbols}


@app.post("/api/jobs/run")
def api_run_job():
    task = run_sctr_pipeline_task.delay(source="manual")
    return {"status": "queued", "task_id": task.id}


@app.get("/api/export/latest.csv")
def api_export_latest_csv():
    run = latest_run()
    if not run:
        raise HTTPException(status_code=404, detail="No successful run found.")

    _, rows = fetch_picks(int(run["id"]), q="", offset=0, limit=5000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["rank", "symbol", "sctr", "perf_1d", "perf_5d", "perf_20d", "perf_60d", "rsi_14"])
    for r in rows:
        writer.writerow([
            r["rank"],
            r["symbol"],
            r["sctr"],
            r["perf_1d"],
            r["perf_5d"],
            r["perf_20d"],
            r["perf_60d"],
            r["rsi_14"],
        ])

    data = output.getvalue()
    filename = f"sctr_top_{len(rows)}.csv"
    return StreamingResponse(
        iter([data]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/jobs/status/{task_id}")
def api_job_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    payload = {
        "task_id": task_id,
        "state": result.state,
        "result": result.result if result.successful() else None,
    }
    if result.failed():
        payload["error"] = str(result.result)
    return payload
