from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from celery import states

from app.celery_app import celery_app
from app.config import settings
from app.db import create_run, finish_run, has_running_run, save_picks
from app.services.notify import notify_job_failed, notify_job_succeeded
from app.services.sctr import scrape_sctr_list
from app.services.yf_metrics import compute_metrics


def _run_key(source: str) -> str:
    tz = ZoneInfo(settings.app_timezone)
    ts = datetime.now(tz).strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{source}"


@celery_app.task(
    bind=True,
    name="app.tasks.run_sctr_pipeline",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.task_max_retries},
)
def run_sctr_pipeline_task(self, source: str = "manual") -> dict:
    if has_running_run():
        return {"status": "skipped", "reason": "run already in progress"}

    key = _run_key(source)
    run_id = create_run(run_key=key, source=source)

    try:
        base_rows = scrape_sctr_list(settings.sctr_source_url, settings.sctr_limit)
        enriched = []
        for row in base_rows:
            enriched.append({**row, **compute_metrics(row["symbol"])})

        save_picks(run_id, enriched)
        finish_run(run_id, "ok", len(enriched))

        notify_job_succeeded(source=source, run_key=key, total=len(enriched))
        return {"status": "ok", "run_id": run_id, "count": len(enriched)}
    except Exception as exc:
        finish_run(run_id, "failed", 0, str(exc))
        notify_job_failed(source=source, run_key=key, err=str(exc))
        self.update_state(state=states.FAILURE, meta={"error": str(exc)})
        raise
