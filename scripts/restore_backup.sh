#!/usr/bin/env bash
# Restore one database from a backup run (replaces its current contents).
#   ./scripts/restore_backup.sh backups/<timestamp> [database]   (default: DB_NAME)
# Stop the writers first: docker compose stop af superset superset_mcp
set -euo pipefail
cd "$(dirname "$0")/.."
run_dir=${1:?usage: $0 backups/<timestamp> [database]}
db=${2:-$(grep -E '^DB_NAME=' .env | cut -d= -f2-)}
dump="/backups/$(basename "$run_dir")/$db.dump"

read -r -p "Replace database '$db' with $dump? Type the database name to confirm: " answer
[ "$answer" = "$db" ] || { echo "Aborted."; exit 1; }
docker compose exec -T db_backup pg_restore --clean --if-exists --exit-on-error \
    --dbname="$db" "$dump"
echo "Restored $db. Re-apply roles/grants if needed: docker exec db bash /docker-entrypoint-initdb.d/init_roles.sh"
