#!/usr/bin/env bash
# Print login details for every service in this stack, read from .env files
# and the running Airflow container. Usage:
#   ./scripts/show_credentials.sh                       # print to terminal
#   ./scripts/show_credentials.sh > credentials.local.md  # save (gitignored)
set -euo pipefail
cd "$(dirname "$0")/.."

env_val() { grep -E "^$2=" "$1" 2>/dev/null | tail -1 | cut -d= -f2-; }

DB_USER=$(env_val .env DB_USER)
DB_PASSWORD=$(env_val .env DB_PASSWORD)
DB_NAME=$(env_val .env DB_NAME)
SUPERSET_DB_USER=$(env_val docker/.env DATABASE_USER)
SUPERSET_DB_PASSWORD=$(env_val docker/.env DATABASE_PASSWORD)
SUPERSET_DB_NAME=$(env_val docker/.env DATABASE_DB)
SUPERSET_ADMIN_PASSWORD=$(grep -m1 -oP '^ADMIN_PASSWORD="\K[^"]+' docker/docker-init.sh || echo admin)

# Airflow standalone generates the admin password on first start
AIRFLOW_PASSWORD=$(docker exec airflow_container \
  cat /opt/airflow/simple_auth_manager_passwords.json.generated 2>/dev/null \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("admin",""))' 2>/dev/null || true)
AIRFLOW_PASSWORD=${AIRFLOW_PASSWORD:-"<not available - is airflow_container running?>"}

cat <<EOF
# Local credentials - weather-data-project

Generated $(date '+%Y-%m-%d %H:%M'). Do not commit this file.

| Platform | URL | Username | Password |
|---|---|---|---|
| Airflow | http://localhost:8081 | admin | ${AIRFLOW_PASSWORD} |
| Superset | http://localhost:8089 | admin | ${SUPERSET_ADMIN_PASSWORD} |
| Superset MCP | http://localhost:5008/mcp | (no auth, localhost only; acts as admin) | - |
| Postgres (weather data) | localhost:5000 / db ${DB_NAME} | ${DB_USER} | ${DB_PASSWORD} |

## dbt
dbt has no web UI or login of its own. It connects to Postgres with the
weather-data credentials above (via \`dbt/profiles.yml\` -> \`DB_*\` in \`.env\`).

## Connection strings
- From your machine (DBeaver, psql): \`postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5000/${DB_NAME}\`
- From Superset "Add database" (inside Docker): \`postgresql://${DB_USER}:${DB_PASSWORD}@db:5432/${DB_NAME}\`

## Internal service accounts (metadata databases)
| Used by | User | Password | Database |
|---|---|---|---|
| Airflow metadata | airflow | airflow | airflow_db |
| Superset metadata | ${SUPERSET_DB_USER} | ${SUPERSET_DB_PASSWORD} | ${SUPERSET_DB_NAME} |
EOF
