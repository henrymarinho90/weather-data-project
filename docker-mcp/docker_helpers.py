"""Pure helpers for the read-only Docker MCP server (no I/O, unit tested).

They decide what an AI client may see: selected container fields (never the
environment, which holds every password of this stack), and logs with secrets
masked.
"""

import re
import struct

PROJECT_LABEL = "com.docker.compose.project"
SERVICE_LABEL = "com.docker.compose.service"
MASK = "***"

_REDACTIONS = [
    # Airflow simple auth manager: "Password for user 'admin': <password>"
    (re.compile(r"(?i)(password for user \S+:\s*)\S+"), rf"\g<1>{MASK}"),
    # key=value / key: value / "key": "value" for secret-looking keys
    (
        re.compile(
            r"(?i)((?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key)"
            r"[\w.-]*[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,;]+"
        ),
        rf"\g<1>{MASK}",
    ),
    # Authorization headers
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), rf"\g<1>{MASK}"),
    # Credentials embedded in URLs: scheme://user:password@host
    (re.compile(r"(\b[a-z][\w+.-]*://[^:/\s@]+:)[^@\s]+(@)"), rf"\g<1>{MASK}\g<2>"),
    # JWTs
    (re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+"), MASK),
]


def redact(text: str) -> str:
    """Mask passwords, tokens, API keys and URL credentials in log text."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def demux_logs(raw: bytes, tty: bool) -> str:
    """Decode the body of GET /containers/{id}/logs.

    Without a TTY, Docker multiplexes stdout/stderr into frames with an 8-byte
    header (stream type, 3 zero bytes, big-endian payload length).
    """
    if tty:
        return raw.decode("utf-8", errors="replace")
    chunks, pos = [], 0
    while pos + 8 <= len(raw):
        (size,) = struct.unpack(">I", raw[pos + 4 : pos + 8])
        chunks.append(raw[pos + 8 : pos + 8 + size])
        pos += 8 + size
    return b"".join(chunks).decode("utf-8", errors="replace")


def _health(status: str) -> str | None:
    match = re.search(r"\((healthy|unhealthy|health: starting)\)", status or "")
    return match.group(1).replace("health: ", "") if match else None


def summarize_container(item: dict) -> dict:
    """Safe fields from one entry of GET /containers/json."""
    labels = item.get("Labels") or {}
    return {
        "name": (item.get("Names") or ["?"])[0].lstrip("/"),
        "service": labels.get(SERVICE_LABEL),
        "image": item.get("Image"),
        "state": item.get("State"),
        "status": item.get("Status"),
        "health": _health(item.get("Status", "")),
        "published_ports": sorted(
            f"{p['IP']}:{p['PublicPort']}->{p['PrivatePort']}/{p['Type']}"
            for p in item.get("Ports") or []
            if p.get("PublicPort")
        ),
    }


def safe_details(inspect: dict) -> dict:
    """Allow-listed fields from GET /containers/{id}/json (no Env, Cmd or Args)."""
    state = inspect.get("State") or {}
    health = state.get("Health") or {}
    config = inspect.get("Config") or {}
    host = inspect.get("HostConfig") or {}
    return {
        "name": inspect.get("Name", "").lstrip("/"),
        "service": (config.get("Labels") or {}).get(SERVICE_LABEL),
        "image": config.get("Image"),
        "created": inspect.get("Created"),
        "state": {
            "status": state.get("Status"),
            "running": state.get("Running"),
            "exit_code": state.get("ExitCode"),
            "oom_killed": state.get("OOMKilled"),
            "error": state.get("Error") or None,
            "started_at": state.get("StartedAt"),
            "finished_at": state.get("FinishedAt"),
            "health": health.get("Status"),
            "health_failing_streak": health.get("FailingStreak"),
        },
        "restart_count": inspect.get("RestartCount"),
        "restart_policy": (host.get("RestartPolicy") or {}).get("Name"),
        "user": config.get("User") or "root (image default)",
        "networks": sorted((inspect.get("NetworkSettings") or {}).get("Networks") or {}),
        "mounts": [
            {
                "type": m.get("Type"),
                "destination": m.get("Destination"),
                "read_only": not m.get("RW"),
            }
            for m in inspect.get("Mounts") or []
        ],
    }


def stats_summary(name: str, stats: dict) -> dict:
    """CPU and memory usage from GET /containers/{id}/stats?stream=false."""
    cpu, pre = stats.get("cpu_stats") or {}, stats.get("precpu_stats") or {}
    cpu_delta = (cpu.get("cpu_usage") or {}).get("total_usage", 0) - (
        pre.get("cpu_usage") or {}
    ).get("total_usage", 0)
    system_delta = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
    cpus = cpu.get("online_cpus") or 1
    mem = stats.get("memory_stats") or {}
    # Same as `docker stats`: exclude the page cache
    usage = mem.get("usage", 0) - (mem.get("stats") or {}).get("inactive_file", 0)
    limit = mem.get("limit") or 0
    networks = stats.get("networks") or {}
    return {
        "name": name,
        "cpu_percent": round(cpu_delta / system_delta * cpus * 100, 2) if system_delta > 0 else 0.0,
        "memory_mb": round(usage / 2**20, 1),
        "memory_limit_mb": round(limit / 2**20, 1),
        "memory_percent": round(usage / limit * 100, 2) if limit else None,
        "net_rx_mb": round(sum(n.get("rx_bytes", 0) for n in networks.values()) / 2**20, 2),
        "net_tx_mb": round(sum(n.get("tx_bytes", 0) for n in networks.values()) / 2**20, 2),
    }
