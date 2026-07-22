#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
/opt/homebrew/bin/uv run --quiet --with pyyaml python "$ROOT/scripts/validate_package.py" "$ROOT"
