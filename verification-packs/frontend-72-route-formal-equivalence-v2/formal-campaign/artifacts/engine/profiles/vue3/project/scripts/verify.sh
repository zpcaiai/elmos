#!/usr/bin/env bash
set -euo pipefail
test -f package-lock.json || { echo "PACKAGE_LOCK_NOT_MATERIALIZED"; exit 2; }
npm ci
npm run test
npm run build
