#!/usr/bin/env bash
# Rebuild a throwaway database from V1..V54 and run the P0 acceptance rehearsal.
set -euo pipefail

SOCK=${SOCK:-/tmp/pgsock}
DB=${DB:-elmos_p0}
REPO_MIGRATIONS=${REPO_MIGRATIONS:-/mnt/user-data/uploads/elmos/modules/persistence/src/main/resources/db/migration}
NEW_MIGRATIONS=${NEW_MIGRATIONS:-/home/claude/p0/sql}

psql -h "$SOCK" -U elmos -d postgres -q -c "DROP DATABASE IF EXISTS $DB" >/dev/null
psql -h "$SOCK" -U elmos -d postgres -q -c "CREATE DATABASE $DB" >/dev/null

for f in $(ls "$REPO_MIGRATIONS"/V*.sql | sort -V); do
  psql -h "$SOCK" -U elmos -d "$DB" -v ON_ERROR_STOP=1 -q -f "$f" >/dev/null
done
echo "V1..V51 applied"

for f in "$NEW_MIGRATIONS"/V52*.sql "$NEW_MIGRATIONS"/V53*.sql "$NEW_MIGRATIONS"/V54*.sql; do
  psql -h "$SOCK" -U elmos -d "$DB" -v ON_ERROR_STOP=1 -q -f "$f" >/dev/null
  echo "applied $(basename "$f")"
done

psql -h "$SOCK" -U elmos -d "$DB" -v ON_ERROR_STOP=1 -q -f "$NEW_MIGRATIONS/smoke_test_p0.sql"
