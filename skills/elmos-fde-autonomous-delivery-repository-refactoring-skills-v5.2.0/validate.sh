#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STRICT=""
[[ "${1:-}" == "--strict" ]] && STRICT="--strict"
python3 "$ROOT/scripts/validate_package.py" "$ROOT" $STRICT
python3 "$ROOT/scripts/validate_json_schemas.py" "$ROOT"
python3 "$ROOT/scripts/validate_skill_evals.py" "$ROOT"
PYTHONPATH="$ROOT/reference${PYTHONPATH:+:$PYTHONPATH}" python3 -m unittest discover -s "$ROOT/tests" -v
python3 -m compileall -q "$ROOT/reference" "$ROOT/scripts"
bash -n "$ROOT/install.sh" "$ROOT/uninstall.sh" "$ROOT/validate.sh" "$ROOT/scripts/smoke_test_install.sh"
echo "PASS: package contracts, schemas, evals, reference semantics and shell syntax"
