#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 -m etgb validate
python3 -m etgb coverage
./scripts/run_smoke.sh
pytest -q
