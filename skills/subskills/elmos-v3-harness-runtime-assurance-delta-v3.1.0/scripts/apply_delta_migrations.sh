#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_URL="${DATABASE_URL:?DATABASE_URL is required}"
for migration in "$ROOT"/payload/database/delta-migrations/V*.sql; do
  echo "Applying $(basename "$migration")"
  psql "$DB_URL" -v ON_ERROR_STOP=1 -f "$migration"
done
