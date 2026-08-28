#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 -m etgb run --profile smoke --output reports/smoke-results.jsonl
python3 -m etgb score reports/smoke-results.jsonl --output reports/smoke-score.json
