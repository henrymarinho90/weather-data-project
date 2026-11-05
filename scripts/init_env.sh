#!/usr/bin/env bash
# Create or complete .env from .env.example.
#   - keys missing from .env are added
#   - `change_me` values are replaced with random secrets
#   - `auto` values are detected for this machine (uid/gid, docker socket gid)
# Existing real values are never overwritten, so it is safe to re-run after
# pulling a version of the repo that adds new settings.
#
#   ./scripts/init_env.sh            write .env (make init)
#   ./scripts/init_env.sh --coolify  print a complete env block to paste into
#                                    Coolify (or any server); writes nothing
set -euo pipefail
cd "$(dirname "$0")/.."

MODE=${1:-write}

docker_gid() {
    # GNU stat (Linux/WSL) vs BSD stat (macOS). On Docker Desktop the socket is
    # root:root inside containers, so 0 is the right group there.
    stat -c %g /var/run/docker.sock 2>/dev/null || stat -f %g /var/run/docker.sock 2>/dev/null || echo 0
}

if [ "$MODE" = "--coolify" ]; then
    # Coolify checks the repo out as root and the server's docker gid is unknown here
    export AUTO_DOCKER_GID="SET_ME"
    export AUTO_HOST_UID=0 AUTO_HOST_GID=0
else
    export AUTO_DOCKER_GID="$(docker_gid)"
    export AUTO_HOST_UID="$(id -u)" AUTO_HOST_GID="$(id -g)"
fi

python3 - "$MODE" <<'PY'
import base64, os, re, secrets, sys

mode = sys.argv[1]
KEY = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)")


def parse(path):
    values = {}
    if os.path.exists(path):
        for line in open(path):
            if m := KEY.match(line):
                values[m.group(1)] = m.group(2)
    return values


def resolve(key, value):
    if value == "change_me":
        return secrets.token_urlsafe(32), True
    if value == "change_me_fernet":
        # Fernet needs 32 random bytes, urlsafe base64 WITH padding (44 chars)
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(), True
    if value == "auto":
        return os.environ[f"AUTO_{key}"], False
    return value, False


if mode == "--coolify":
    overrides = {
        "SUPERSET_PUBLIC_URL": "https://superset.example.com",
        "USE_MOCK_API": "true",
        # No Docker MCP on servers: see COMPOSE_PROFILES in .env.example
        "COMPOSE_PROFILES": "",
    }
    print("# Paste into Coolify > your resource > Environment Variables (Developer view).")
    print("# Then replace DOCKER_GID (run on the server: stat -c %g /var/run/docker.sock),")
    print("# SUPERSET_PUBLIC_URL and, for live data, WEATHERSTACK_API_KEY / USE_MOCK_API=false.")
    for line in open(".env.example"):
        if m := KEY.match(line):
            key, value = m.groups()
            value = overrides.get(key, resolve(key, value)[0])
            print(f"{key}={value}")
    sys.exit(0)

current = parse(".env")
# Earlier versions kept Superset settings in docker/.env: carry the secrets over
# (a new SUPERSET_SECRET_KEY would make stored connection passwords unreadable)
legacy = parse("docker/.env")
for old, new in (("SUPERSET_SECRET_KEY", "SUPERSET_SECRET_KEY"), ("ADMIN_PASSWORD", "SUPERSET_ADMIN_PASSWORD")):
    if new not in current and legacy.get(old):
        current[new] = legacy[old]

existing = set(current)
lines, added, generated = [], 0, 0
for line in open(".env.example"):
    m = KEY.match(line)
    if not m:
        lines.append(line)
        continue
    key, default = m.groups()
    value, is_secret = resolve(key, current.pop(key, default))
    added += key not in existing
    generated += is_secret
    lines.append(f"{key}={value}\n")
# Keep settings the template does not know about (e.g. local overrides)
if current:
    lines.append("\n# Local settings not in the template\n")
    lines += [f"{k}={v}\n" for k, v in current.items()]
with open(".env", "w") as f:
    f.writelines(lines)
os.chmod(".env", 0o600)
print(f".env: {added} keys added, {generated} secrets generated")
if legacy:
    print("docker/.env is no longer used (its secrets are now in .env); you can delete it.")
PY

if [ "$MODE" != "--coolify" ]; then
    # Owned by you (db_backup runs as HOST_UID), not created as root by Docker
    mkdir -p backups
fi
