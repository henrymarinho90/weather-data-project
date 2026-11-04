#!/bin/bash
# Logical backups of every project database, run by the db_backup service.
#   backup.sh          loop: back up now if the newest backup is >24h old, then daily at BACKUP_HOUR_UTC
#   backup.sh once     one backup, then exit (make backup)
# Each run writes /backups/<UTC timestamp>/ with globals.sql (roles) and one
# pg_dump custom-format file per database, then deletes runs older than
# BACKUP_KEEP_DAYS.
set -euo pipefail

: "${BACKUP_DIR:=/backups}" "${BACKUP_KEEP_DAYS:=7}" "${BACKUP_HOUR_UTC:=2}"
: "${DATABASES:?}" "${PGPASSWORD:?}"
export PGHOST="${PGHOST:-db}" PGUSER="${PGUSER:-postgres}"
umask 077  # globals.sql holds role password hashes

backup_once() {
    local dir="$BACKUP_DIR/$(date -u +%Y%m%dT%H%M%SZ)"
    mkdir -p "$dir.partial"
    pg_dumpall --globals-only > "$dir.partial/globals.sql"
    for db in $DATABASES; do
        pg_dump --format=custom --dbname="$db" --file="$dir.partial/$db.dump"
    done
    # Only complete runs get the final name, so restores never pick a half-written one
    mv "$dir.partial" "$dir"
    find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$BACKUP_KEEP_DAYS" -exec rm -rf {} +
    echo "$(date -u +%FT%TZ) backup written to $dir ($(du -sh "$dir" | cut -f1))"
}

if [ "${1:-}" = "once" ]; then
    backup_once
    exit 0
fi

while true; do
    latest=$(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d ! -name '*.partial' -mmin -1440 | head -1)
    [ -z "$latest" ] && backup_once
    now=$(date -u +%s)
    next=$(date -u -d "today ${BACKUP_HOUR_UTC}:00" +%s)
    [ "$next" -le "$now" ] && next=$((next + 86400))
    echo "next backup at $(date -u -d "@$next" +%FT%TZ)"
    sleep $((next - now))
    backup_once
done
