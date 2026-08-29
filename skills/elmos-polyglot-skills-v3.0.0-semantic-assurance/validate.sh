#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
python3 "$root/scripts/validate_bundle_v3.py" "$root"
python3 -m unittest discover -s "$root/tests-v3" -p "test_*.py"
for f in "$root"/*.sh "$root"/scripts/*.py; do [[ -e "$f" ]] || continue; done
echo "PASS: v3 validation complete"
