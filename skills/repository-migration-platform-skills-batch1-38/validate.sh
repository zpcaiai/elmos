#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
python3 "$ROOT/scripts/validate_package.py"
python3 -m unittest discover -s "$ROOT/tests" -v
