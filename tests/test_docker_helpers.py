import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docker-mcp"))

from docker_helpers import (  # noqa: E402
    demux_logs,
    redact,
    safe_details,
    stats_summary,
    summarize_container,
)


def test_redact_masks_secrets_in_common_log_formats():
    lines = {
        "Password for user 'admin': S3cretValue": "Password for user 'admin': ***",
        "DB_PASSWORD=abc123 other=1": "DB_PASSWORD=*** other=1",
        '{"access_token": "tok.en.value"}': '{"access_token": "***"}',
        "GET /current?access_key=d8942f44abc&query=NY": "GET /current?access_key=***&query=NY",
        "Authorization: Bearer abc.def": "Authorization: Bearer ***",
        "postgresql://db_user:hunter2@db:5432/db": "postgresql://db_user:***@db:5432/db",
        "token eyJhbGciOi.eyJzdWIi.c2lnbmF0dXJl end": "token *** end",
    }
    for raw, expected in lines.items():
        assert redact(raw) == expected


def test_redact_keeps_ordinary_lines():
    line = "21:52:33  1 of 19 PASS not_null_stg_weather_data_city [PASS in 0.09s]"
    assert redact(line) == line


def frame(stream: int, payload: bytes) -> bytes:
    return bytes([stream, 0, 0, 0]) + struct.pack(">I", len(payload)) + payload


def test_demux_logs_joins_stdout_and_stderr_frames():
    raw = frame(1, b"out line\n") + frame(2, b"err line\n")
    assert demux_logs(raw, tty=False) == "out line\nerr line\n"


def test_demux_logs_passes_tty_output_through():
    assert demux_logs(b"plain\n", tty=True) == "plain\n"


def test_summarize_container_extracts_health_and_published_ports():
    item = {
        "Names": ["/db"],
        "Image": "postgres:18.6-bookworm",
        "State": "running",
        "Status": "Up 5 minutes (healthy)",
        "Labels": {"com.docker.compose.service": "db"},
        "Ports": [
            {"IP": "127.0.0.1", "PrivatePort": 5432, "PublicPort": 5434, "Type": "tcp"},
            {"PrivatePort": 5432, "Type": "tcp"},
        ],
    }
    summary = summarize_container(item)
    assert summary["name"] == "db" and summary["service"] == "db"
    assert summary["health"] == "healthy"
    assert summary["published_ports"] == ["127.0.0.1:5434->5432/tcp"]


def test_safe_details_never_exposes_environment_or_command():
    inspect = {
        "Name": "/af",
        "Config": {
            "Env": ["DB_PASSWORD=secret"],
            "Cmd": ["--auth-token", "x"],
            "Image": "apache/airflow:3.3.2",
            "Labels": {"com.docker.compose.service": "af"},
        },
        "State": {"Status": "running", "Running": True, "ExitCode": 0},
        "Mounts": [{"Type": "bind", "Source": "/home/x", "Destination": "/opt", "RW": False}],
    }
    details = safe_details(inspect)
    assert "secret" not in repr(details) and "auth-token" not in repr(details)
    assert details["mounts"] == [{"type": "bind", "destination": "/opt", "read_only": True}]


def test_stats_summary_matches_docker_stats_formula():
    stats = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 300},
            "system_cpu_usage": 2000,
            "online_cpus": 2,
        },
        "precpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 1000},
        "memory_stats": {
            "usage": 150 * 2**20,
            "limit": 1000 * 2**20,
            "stats": {"inactive_file": 50 * 2**20},
        },
    }
    summary = stats_summary("db", stats)
    assert summary["cpu_percent"] == 40.0
    assert summary["memory_mb"] == 100.0 and summary["memory_percent"] == 10.0
