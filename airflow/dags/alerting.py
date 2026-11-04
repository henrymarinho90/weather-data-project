"""Task-failure alerts for the weather DAG.

`notify_failure` is an Airflow on_failure_callback (called once a task has used
up its retries). It posts a message to ALERT_WEBHOOK_URL (Slack incoming
webhooks and Discord both accept the payload); without a URL it only logs.
Alerting must never fail the task, so every error is logged and swallowed.
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)


def build_message(context) -> str:
    ti = context.get("ti") or context.get("task_instance")
    run = context.get("dag_run")
    error = context.get("exception")
    lines = [
        f"Airflow task failed: {getattr(ti, 'dag_id', '?')}.{getattr(ti, 'task_id', '?')}",
        f"Run: {getattr(run, 'run_id', '?')} (try {getattr(ti, 'try_number', '?')})",
    ]
    if error:
        lines.append(f"Error: {type(error).__name__}: {str(error)[:500]}")
    if getattr(ti, "task_id", None) == "check_source_freshness":
        lines.append("Newest observation is stale: check USE_MOCK_API and the Weatherstack quota.")
    return "\n".join(lines)


def notify_failure(context) -> None:
    message = build_message(context)
    url = os.getenv("ALERT_WEBHOOK_URL")
    if not url:
        logger.warning("ALERT_WEBHOOK_URL not set; alert not sent:\n%s", message)
        return
    try:
        response = requests.post(url, json={"text": message, "content": message}, timeout=10)
        response.raise_for_status()
        logger.info("Failure alert sent")
    except Exception:
        logger.exception("Could not send failure alert")
