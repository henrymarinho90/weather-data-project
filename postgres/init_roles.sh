#!/bin/bash
# Create every Postgres role and database the stack needs, with least privilege:
#   - $APP_DB_USER     owns database $POSTGRES_DB and schema dev (ingest + dbt), NOT a superuser
#   - airflow          owns airflow_db (Airflow metadata)
#   - superset         owns superset_db (Superset metadata)
#   - weather_reader   SELECT-only on schema dev, read-only sessions (Superset charts, MCP servers)
# The cluster superuser ($POSTGRES_USER) is only used for administration.
#
# Runs automatically on a fresh data volume (docker-entrypoint-initdb.d). It is
# idempotent, so after changing passwords in .env re-apply it with:
#   docker exec db bash /docker-entrypoint-initdb.d/init_roles.sh
set -euo pipefail

for var in POSTGRES_USER POSTGRES_DB APP_DB_USER APP_DB_PASSWORD \
           AIRFLOW_DB_PASSWORD SUPERSET_DB_PASSWORD READER_DB_PASSWORD; do
    if [ -z "${!var:-}" ]; then
        echo "init_roles.sh: $var is not set" >&2
        exit 1
    fi
done
if [ "$APP_DB_USER" = "$POSTGRES_USER" ]; then
    echo "init_roles.sh: DB_USER must differ from POSTGRES_SUPERUSER" >&2
    exit 1
fi

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     -v db="$POSTGRES_DB" -v app="$APP_DB_USER" -v app_pw="$APP_DB_PASSWORD" \
     -v airflow_pw="$AIRFLOW_DB_PASSWORD" -v superset_pw="$SUPERSET_DB_PASSWORD" \
     -v reader_pw="$READER_DB_PASSWORD" <<'SQL'
-- Roles (create if missing, then always (re)apply attributes and password)
SELECT format('CREATE ROLE %I', r) FROM unnest(ARRAY[:'app', 'airflow', 'superset', 'weather_reader']) AS r
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = r) \gexec
ALTER ROLE :"app" WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_pw';
ALTER ROLE airflow WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'airflow_pw';
ALTER ROLE superset WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'superset_pw';
ALTER ROLE weather_reader WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'reader_pw';
-- Defence in depth: the grants below are what actually prevent writes
ALTER ROLE weather_reader SET default_transaction_read_only = on;
ALTER ROLE weather_reader SET statement_timeout = '30s';

-- Metadata databases
SELECT 'CREATE DATABASE airflow_db OWNER airflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow_db') \gexec
SELECT 'CREATE DATABASE superset_db OWNER superset'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'superset_db') \gexec

-- Only the owner (and superuser) may connect to or create temp tables in each database
REVOKE CONNECT, TEMPORARY ON DATABASE airflow_db, superset_db, postgres FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE :"db" FROM PUBLIC;

-- Weather data: owned by the app role
ALTER DATABASE :"db" OWNER TO :"app";
CREATE SCHEMA IF NOT EXISTS dev AUTHORIZATION :"app";
ALTER SCHEMA dev OWNER TO :"app";
-- Objects created earlier by another role (e.g. before this script existed)
SELECT format('ALTER TABLE dev.%I OWNER TO %I', tablename, :'app')
FROM pg_tables WHERE schemaname = 'dev' AND tableowner <> :'app' \gexec
SELECT format('ALTER VIEW dev.%I OWNER TO %I', viewname, :'app')
FROM pg_views WHERE schemaname = 'dev' AND viewowner <> :'app' \gexec

GRANT CONNECT ON DATABASE :"db" TO weather_reader;
GRANT USAGE ON SCHEMA dev TO weather_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA dev TO weather_reader;
-- dbt drops and recreates its tables/views on every run, so grant future ones too
ALTER DEFAULT PRIVILEGES FOR ROLE :"app" IN SCHEMA dev GRANT SELECT ON TABLES TO weather_reader;

-- Query statistics for the Postgres MCP server (needs shared_preload_libraries).
-- track_utility=off (set in docker-compose) keeps ALTER ROLE ... PASSWORD out of it.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
GRANT pg_read_all_stats TO weather_reader;
SELECT pg_stat_statements_reset();
SQL
echo "init_roles.sh: roles and databases ready"
