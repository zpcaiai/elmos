#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$ROOT/scripts/validate_package.py"
bash -n "$ROOT/install.sh"
bash -n "$ROOT/validate.sh"
