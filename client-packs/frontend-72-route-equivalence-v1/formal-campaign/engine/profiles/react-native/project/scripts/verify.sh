#!/usr/bin/env bash
set -euo pipefail
test -f package-lock.json || { echo "PACKAGE_LOCK_NOT_MATERIALIZED"; exit 2; }
npm ci
npm run typecheck
npm run export:web
test "${ELMOS_MOBILE_DEVICE_EVIDENCE:-NOT_RUN}" != "NOT_RUN" || { echo "MOBILE_DEVICE_EVIDENCE_NOT_RUN"; exit 3; }
