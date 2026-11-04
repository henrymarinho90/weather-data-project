#!/usr/bin/env bash
# Create or complete .env and docker/.env from their .example templates.
#   - keys missing from the target file are added
#   - `change_me` values are replaced with random secrets
#   - `auto` values are detected for this machine (paths, uid/gid, docker gid)
# Existing real values are never overwritten, so it is safe to re-run after
# pulling a version of the repo that adds new settings.
set -euo pipefail
cd "$(dirname "$0")/.."

docker_gid() {
    # GNU stat (Linux/WSL) vs BSD stat (macOS). On Docker Desktop the socket is
    # root:root inside containers, so 0 is the right group there.
    stat -c %g /var/run/docker.sock 2>/dev/null || stat -f %g /var/run/docker.sock 2>/dev/null || echo 0
}

export AUTO_DBT_HOST_PATH="$PWD/dbt"
export AUTO_DOCKER_GID="$(docker_gid)"
export AUTO_HOST_UID="$(id -u)"
export AUTO_HOST_GID="$(id -g)"

python3 - .env.example .env docker/.env.example docker/.env <<'PY'
import os, re, secrets, sys

def parse(path):
    values = {}
    if os.path.exists(path):
        for line in open(path):
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
            if m:
                values[m.group(1)] = m.group(2)
    return values

for template, target in zip(sys.argv[1::2], sys.argv[2::2]):
    current = parse(target)
    lines, added, generated = [], 0, 0
    for line in open(template):
        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if not m:
            lines.append(line)
            continue
        key, default = m.groups()
        value = current.pop(key, default)
        if value == "change_me":
            value = secrets.token_urlsafe(32)
            generated += 1
        elif value == "auto":
            value = os.environ[f"AUTO_{key}"]
        if key not in parse(target):
            added += 1
        lines.append(f"{key}={value}\n")
    # Keep settings the template does not know about (e.g. local overrides)
    if current:
        lines.append("\n# Local settings not in the template\n")
        lines += [f"{k}={v}\n" for k, v in current.items()]
    with open(target, "w") as f:
        f.writelines(lines)
    os.chmod(target, 0o600)
    print(f"{target}: {added} keys added, {generated} secrets generated")
PY

# dbt_mcp mounts ./dbt read-only with private tmpfs target/ and logs/; their
# mount points must exist on the host
mkdir -p dbt/weather/target dbt/weather/logs
# Owned by you (db_backup runs as HOST_UID), not created as root by Docker
mkdir -p backups
