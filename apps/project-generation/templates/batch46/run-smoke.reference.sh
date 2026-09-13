#!/usr/bin/env bash
# ELMOS Batch 46 one-click smoke run.
#
#   ./run-smoke.sh              start, seed, probe, assert, then stop after the
#                               free 10 minute runtime lease
#   ./run-smoke.sh --entry compose
#   ./run-smoke.sh --ttl 120    shorter lease
#   ./run-smoke.sh --no-hold    assert and tear down immediately
#
# The lease is enforced: when it expires every service this script started is
# stopped and every byte of smoke data it created is deleted.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "run-smoke: python3 is required to drive the smoke run" >&2
  exit 3
fi

exec python3 smoke/tools/run_smoke.py --project . "$@"
