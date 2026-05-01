from pathlib import Path
import os

from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv()


class Settings(BaseModel):
    app_timezone: str = os.getenv("APP_TIMEZONE", "Asia/Taipei")
    schedule_hour: int = int(os.getenv("SCHEDULE_HOUR", "6"))
    schedule_minute: int = int(os.getenv("SCHEDULE_MINUTE", "0"))

    sctr_source_url: str = os.getenv(
        "SCTR_SOURCE_URL", "https://stockcharts.com/freecharts/sctr.html"
    )
    sctr_limit: int = int(os.getenv("SCTR_LIMIT", "300"))

    sqlite_path: Path = Path(os.getenv("SQLITE_PATH", "./data/dreamlist.db"))
    screenshot_output_dir: Path = Path(os.getenv("SCREENSHOT_OUTPUT_DIR", "./data/screenshots"))
    chart_site_base_url: str = os.getenv("CHART_SITE_BASE_URL", "https://stockcharts.com")
    chart_capture_timeout_ms: int = int(os.getenv("CHART_CAPTURE_TIMEOUT_MS", "45000"))
    chart_capture_viewport_width: int = int(os.getenv("CHART_CAPTURE_VIEWPORT_WIDTH", "1440"))
    chart_capture_viewport_height: int = int(os.getenv("CHART_CAPTURE_VIEWPORT_HEIGHT", "2200"))

    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    celery_broker_url: str = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://redis:6379/0"))
    celery_result_backend: str = os.getenv(
        "CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://redis:6379/1")
    )

    task_max_retries: int = int(os.getenv("TASK_MAX_RETRIES", "3"))

    slack_webhook_url: str = os.getenv("SLACK_WEBHOOK_URL", "")
    notify_email_enabled: bool = os.getenv("NOTIFY_EMAIL_ENABLED", "false").lower() == "true"
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")
    smtp_to: str = os.getenv("SMTP_TO", "")
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"


settings = Settings()
