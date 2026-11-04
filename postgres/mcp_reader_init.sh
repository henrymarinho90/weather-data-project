#!/bin/bash
# Read-only Postgres role for AI/MCP access (dbt_mcp in safe mode).
# Runs automatically on a fresh data dir (docker-entrypoint-initdb.d); for an
# existing database run it once with:
#   docker exec db bash /docker-entrypoint-initdb.d/mcp_reader_init.sh
set -euo pipefail

if [ -z "${MCP_READER_PASSWORD:-}" ]; then
    echo "MCP_READER_PASSWORD not set; skipping mcp_reader role"
    exit 0
fi

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     -v pw="$MCP_READER_PASSWORD" -v owner="$POSTGRES_USER" <<'SQL'
SELECT format('CREATE ROLE mcp_reader LOGIN PASSWORD %L', :'pw')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mcp_reader') \gexec
ALTER ROLE mcp_reader PASSWORD :'pw';
-- Even "DROP ...; COMMIT" fails in a read-only session
ALTER ROLE mcp_reader SET default_transaction_read_only = on;

CREATE SCHEMA IF NOT EXISTS dev AUTHORIZATION :"owner";
GRANT USAGE ON SCHEMA dev TO mcp_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA dev TO mcp_reader;
-- dbt drops and recreates its tables on every run (as the owner role), so
-- grant SELECT on future tables too
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA dev GRANT SELECT ON TABLES TO mcp_reader;
SQL
echo "mcp_reader role ready (read-only on schema dev)"
