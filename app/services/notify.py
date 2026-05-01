from __future__ import annotations

import smtplib
from email.message import EmailMessage

import requests

from app.config import settings


def _send_slack(text: str) -> None:
    if not settings.slack_webhook_url:
        return
    requests.post(settings.slack_webhook_url, json={"text": text}, timeout=15).raise_for_status()


def _send_email(subject: str, body: str) -> None:
    if not settings.notify_email_enabled:
        return
    if not (settings.smtp_host and settings.smtp_from and settings.smtp_to):
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = settings.smtp_to
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


def notify_job_failed(source: str, run_key: str, err: str) -> None:
    text = f"[Dreamlist] SCTR job failed | source={source} | run={run_key} | error={err}"
    _send_slack(text)
    _send_email("Dreamlist SCTR job failed", text)


def notify_job_succeeded(source: str, run_key: str, total: int) -> None:
    text = f"[Dreamlist] SCTR job ok | source={source} | run={run_key} | records={total}"
    _send_slack(text)
