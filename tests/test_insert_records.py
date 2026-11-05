import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from psycopg2.extras import Json

import insert_records
from api_request import mock_fetch_data
from insert_records import build_record

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "bucaramanga_current.json").read_text())


def make_conn(count=0):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (count,)
    return conn, cursor


def executed_sql(cursor):
    return [c.args[0] for c in cursor.execute.call_args_list]


def test_build_record_maps_fields():
    assert build_record(FIXTURE) == (
        "Bucaramanga",
        19,
        "Light rain shower",
        4,
        "2026-11-05 07:25",
        "-5.0",
    )


def test_build_record_mock_matches_fixture():
    data = mock_fetch_data(now=datetime(2026, 11, 5, 12, 25, tzinfo=UTC))
    assert build_record(data) == build_record(FIXTURE)


def test_build_record_uses_first_description_and_offset():
    data = mock_fetch_data()
    data["current"]["weather_descriptions"] = ["Rain", "Mist"]
    data["location"]["utc_offset"] = "5.5"
    record = build_record(data)
    assert record[2] == "Rain"
    assert record[5] == "5.5"


def test_insert_records_stores_payload_and_source():
    conn, cursor = make_conn()
    insert_records.insert_records(conn, FIXTURE)
    sql, params = cursor.execute.call_args.args
    assert "payload" in sql and "source" in sql
    assert params[:6] == build_record(FIXTURE)
    assert isinstance(params[6], Json)
    assert params[6].adapted == FIXTURE
    assert params[7] == "api"
    conn.commit.assert_called_once()


def test_insert_records_source_flag():
    conn, cursor = make_conn()
    insert_records.insert_records(conn, FIXTURE, source="mock")
    assert cursor.execute.call_args.args[1][7] == "mock"


def test_create_table_is_idempotent_migration():
    conn, cursor = make_conn()
    insert_records.create_table(conn)
    sql = executed_sql(cursor)[0]
    assert "CREATE TABLE IF NOT EXISTS dev.raw_weather_data" in sql
    assert "ADD COLUMN IF NOT EXISTS payload JSONB" in sql
    assert "ADD COLUMN IF NOT EXISTS source TEXT" in sql
    assert "payload JSONB," in sql and "source TEXT\n" in sql
    conn.commit.assert_called_once()


def patch_fetch(monkeypatch):
    calls = []

    def fake_fetch(city):
        calls.append(city)
        return {**FIXTURE, "location": {**FIXTURE["location"], "name": city}}

    monkeypatch.setattr(insert_records, "fetch_data", fake_fetch)
    return calls


def test_budget_guard_skips_at_limit(monkeypatch, caplog):
    monkeypatch.setenv("WEATHERSTACK_MONTHLY_CALL_LIMIT", "90")
    calls = patch_fetch(monkeypatch)
    conn, cursor = make_conn(count=90)
    with caplog.at_level(logging.WARNING):
        assert insert_records.ingest_city(conn, "Bucaramanga", mock=False) is False
    assert calls == []
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert not any("INSERT" in sql for sql in executed_sql(cursor))
    assert "source = 'api'" in executed_sql(cursor)[0]


def test_budget_guard_proceeds_below_limit(monkeypatch):
    monkeypatch.setenv("WEATHERSTACK_MONTHLY_CALL_LIMIT", "90")
    calls = patch_fetch(monkeypatch)
    conn, cursor = make_conn(count=89)
    assert insert_records.ingest_city(conn, "Bucaramanga", mock=False) is True
    assert calls == ["Bucaramanga"]
    assert cursor.execute.call_args.args[1][7] == "api"


def test_budget_guard_default_limit(monkeypatch):
    monkeypatch.delenv("WEATHERSTACK_MONTHLY_CALL_LIMIT", raising=False)
    calls = patch_fetch(monkeypatch)
    conn, _ = make_conn(count=90)
    assert insert_records.ingest_city(conn, "X", mock=False) is False
    assert calls == []


def test_guard_not_applied_in_mock_mode(monkeypatch):
    calls = patch_fetch(monkeypatch)
    conn, cursor = make_conn(count=10_000)
    assert insert_records.ingest_city(conn, "Bucaramanga", mock=True) is True
    assert calls == []
    sqls = executed_sql(cursor)
    assert len(sqls) == 1 and "INSERT" in sqls[0]
    assert cursor.execute.call_args.args[1][7] == "mock"


def test_pause_only_between_calls(monkeypatch):
    monkeypatch.setenv("WEATHERSTACK_CALL_INTERVAL_SECONDS", "7")
    calls = patch_fetch(monkeypatch)
    conn, _ = make_conn(count=0)
    sleeps = []
    insert_records.ingest_cities(conn, ["A", "B", "C"], mock=False, sleep=sleeps.append)
    assert calls == ["A", "B", "C"]
    assert sleeps == [7.0, 7.0]


def test_no_pause_for_single_city(monkeypatch):
    patch_fetch(monkeypatch)
    conn, _ = make_conn(count=0)
    sleeps = []
    insert_records.ingest_cities(conn, ["A"], mock=False, sleep=sleeps.append)
    assert sleeps == []


def test_default_pause_is_five_seconds(monkeypatch):
    monkeypatch.delenv("WEATHERSTACK_CALL_INTERVAL_SECONDS", raising=False)
    patch_fetch(monkeypatch)
    conn, _ = make_conn(count=0)
    sleeps = []
    insert_records.ingest_cities(conn, ["A", "B"], mock=False, sleep=sleeps.append)
    assert sleeps == [5.0]


def test_mock_mode_does_not_sleep():
    conn, _ = make_conn()
    sleeps = []
    insert_records.ingest_cities(conn, ["A", "B"], mock=True, sleep=sleeps.append)
    assert sleeps == []


def test_main_runs_all_cities(monkeypatch):
    conn, _ = make_conn()
    monkeypatch.setattr(insert_records, "connect_to_db", lambda: conn)
    monkeypatch.setenv("USE_MOCK_API", "true")
    monkeypatch.setenv("WEATHER_CITIES", "A,B")
    seen = []
    monkeypatch.setattr(
        insert_records, "ingest_cities", lambda c, cities, mock: seen.append((cities, mock))
    )
    insert_records.main()
    assert seen == [(["A", "B"], True)]
    conn.close.assert_called_once()


def test_main_closes_conn_on_error(monkeypatch):
    conn, _ = make_conn()
    monkeypatch.setattr(insert_records, "connect_to_db", lambda: conn)
    monkeypatch.setattr(insert_records, "create_table", MagicMock(side_effect=RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        insert_records.main()
    conn.close.assert_called_once()
