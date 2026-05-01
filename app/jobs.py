from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.tasks import run_sctr_pipeline_task


_scheduler: BackgroundScheduler | None = None


def _enqueue_scheduled_run() -> None:
    run_sctr_pipeline_task.delay(source="scheduled")


def start_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone=settings.app_timezone)
    _scheduler.add_job(
        func=_enqueue_scheduled_run,
        trigger=CronTrigger(hour=settings.schedule_hour, minute=settings.schedule_minute),
        id="daily-sctr-job",
        replace_existing=True,
    )
    _scheduler.start()


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
