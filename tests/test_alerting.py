import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "airflow" / "dags"))

import alerting  # noqa: E402


def context(task_id="transform_data_task"):
    return {
        "ti": SimpleNamespace(dag_id="api-dbt-orchestrator", task_id=task_id, try_number=2),
        "dag_run": SimpleNamespace(run_id="scheduled__2026-11-05T08:00:00+00:00"),
        "exception": RuntimeError("dbt build failed"),
    }


def test_message_names_task_run_and_error():
    message = alerting.build_message(context())
    assert "api-dbt-orchestrator.transform_data_task" in message
    assert "scheduled__2026-11-05T08:00:00+00:00 (try 2)" in message
    assert "RuntimeError: dbt build failed" in message


def test_freshness_failures_get_a_hint():
    assert "stale" in alerting.build_message(context("check_source_freshness"))


def test_without_url_nothing_is_posted(monkeypatch):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(
        alerting.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )
    alerting.notify_failure(context())


def test_posts_to_webhook_and_never_raises(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            raise alerting.requests.HTTPError("500")

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        return Response()

    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example/abc")
    monkeypatch.setattr(alerting.requests, "post", fake_post)
    alerting.notify_failure(context())  # webhook error is logged, not raised
    assert calls and calls[0][0] == "https://hooks.example/abc" and calls[0][2] == 10
    assert "transform_data_task" in calls[0][1]["text"]
