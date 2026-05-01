from celery import Celery

from app.config import settings


celery_app = Celery(
    "dreamlist",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.app_timezone,
    enable_utc=False,
    task_track_started=True,
)

celery_app.autodiscover_tasks(["app"])
