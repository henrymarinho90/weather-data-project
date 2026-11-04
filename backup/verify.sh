#!/bin/bash
# Restore test: load the newest backup of the weather database into a scratch
# database and compare row counts with the live tables. Run by `make backup-verify`
# inside the db_backup container. The scratch database is always dropped.
set -euo pipefail
export PGHOST="${PGHOST:-db}" PGUSER="${PGUSER:-postgres}"
: "${DB_NAME:?}" "${BACKUP_DIR:=/backups}"

latest=$(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d ! -name '*.partial' | sort | tail -1)
[ -n "$latest" ] || { echo "No backups in $BACKUP_DIR (run: make backup)" >&2; exit 1; }
dump="$latest/$DB_NAME.dump"
scratch="restore_check_$$"
trap 'dropdb --if-exists "$scratch"' EXIT

createdb "$scratch"
pg_restore --no-owner --no-privileges --exit-on-error --dbname="$scratch" "$dump"

counts() {
    psql -d "$1" -tA -c "select table_name from information_schema.tables
                         where table_schema = 'dev' and table_type = 'BASE TABLE' order by 1" |
    while read -r t; do echo "$t $(psql -d "$1" -tA -c "select count(*) from dev.\"$t\"")"; done
}
echo "Restored $dump into $scratch"
diff <(counts "$DB_NAME") <(counts "$scratch") && echo "OK: row counts match the live database" \
    || { echo "MISMATCH (rows written since the backup also show up here)"; exit 1; }
