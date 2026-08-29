#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
python3 "$root/scripts/validate_expansion.py" "$root"
python3 -m py_compile "$root"/scripts/*.py
echo "PASS: semantic assurance expansion validation complete"
