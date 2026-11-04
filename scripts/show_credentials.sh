#!/usr/bin/env bash
# Print login details for every service in this stack, read from .env files
# and the running Airflow container. Usage:
#   ./scripts/show_credentials.sh                         # print to terminal
#   ./scripts/show_credentials.sh > credentials.local.md  # save (gitignored)
set -euo pipefail
cd "$(dirname "$0")/.."

env_val() { { grep -E "^$2=" "$1" 2>/dev/null || true; } | tail -1 | cut -d= -f2-; }

PG_PORT=$(env_val .env POSTGRES_HOST_PORT)
PG_PORT=${PG_PORT:-5434}
PG_SUPER=$(env_val .env POSTGRES_SUPERUSER)
PG_SUPER=${PG_SUPER:-postgres}
PG_SUPER_PASSWORD=$(env_val .env POSTGRES_SUPERUSER_PASSWORD)
DB_USER=$(env_val .env DB_USER)
DB_PASSWORD=$(env_val .env DB_PASSWORD)
DB_NAME=$(env_val .env DB_NAME)
DB_READER_PASSWORD=$(env_val .env DB_READER_PASSWORD)
AIRFLOW_DB_PASSWORD=$(env_val .env AIRFLOW_DB_PASSWORD)
SUPERSET_DB_PASSWORD=$(env_val .env SUPERSET_DB_PASSWORD)
AIRFLOW_MCP_PASSWORD=$(env_val .env AIRFLOW_MCP_PASSWORD)
SUPERSET_ADMIN_PASSWORD=$(env_val .env SUPERSET_ADMIN_PASSWORD)
SUPERSET_ADMIN_PASSWORD=${SUPERSET_ADMIN_PASSWORD:-admin}

# Airflow standalone generates the admin password on first start
AIRFLOW_PASSWORD=$(docker compose exec -T af \
  cat /opt/airflow/simple_auth_manager_passwords.json.generated 2>/dev/null \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("admin",""))' 2>/dev/null || true)
AIRFLOW_PASSWORD=${AIRFLOW_PASSWORD:-"<not available - is the af service running?>"}

cat <<EOF
# Local credentials - weather-data-project

Generated $(date '+%Y-%m-%d %H:%M'). Do not commit this file.

## Web UIs

| Platform | URL | Username | Password |
|---|---|---|---|
| Airflow | http://localhost:8081 | admin | ${AIRFLOW_PASSWORD} |
| Superset | http://localhost:8089 | admin | ${SUPERSET_ADMIN_PASSWORD} |

dbt has no web UI or login of its own: it connects to Postgres as ${DB_USER}.

## Postgres (localhost:${PG_PORT}, database ${DB_NAME})

| Role | Purpose | Password |
|---|---|---|
| ${PG_SUPER} | Superuser, administration only | ${PG_SUPER_PASSWORD} |
| ${DB_USER} | Owns the weather data (ingest, dbt) | ${DB_PASSWORD} |
| weather_reader | Read-only (Superset charts, dbt and Postgres MCP) | ${DB_READER_PASSWORD} |
| airflow | Airflow metadata (airflow_db) | ${AIRFLOW_DB_PASSWORD} |
| superset | Superset metadata (superset_db) | ${SUPERSET_DB_PASSWORD} |

- From your machine (psql, DBeaver): \`postgresql://${DB_USER}:${DB_PASSWORD}@localhost:${PG_PORT}/${DB_NAME}\`
- Read-only: \`postgresql://weather_reader:${DB_READER_PASSWORD}@localhost:${PG_PORT}/${DB_NAME}\`

## MCP servers (via mcp_gateway, localhost only, no client auth)

| Server | URL | Acts as |
|---|---|---|
| Superset | http://localhost:5008/mcp | Superset admin; SQL runs as weather_reader |
| Airflow | http://localhost:5009/mcp/ | Airflow user mcp (password ${AIRFLOW_MCP_PASSWORD}) |
| dbt | http://localhost:5010/mcp | Postgres weather_reader (safe mode) |
| Postgres | http://localhost:5011/sse | Postgres weather_reader, restricted mode |
| Docker | http://localhost:5012/mcp | Read-only Docker API (docker_proxy), this project's containers only |
EOF
