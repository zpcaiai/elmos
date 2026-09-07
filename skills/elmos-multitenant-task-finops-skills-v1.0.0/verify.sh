#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

bash -n install.sh uninstall.sh verify.sh scripts/smoke-test.sh scripts/package.sh
python3 scripts/build_task_catalog.py
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 scripts/validate_api_contracts.py
python3 scripts/validate_sql_contracts.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
bash scripts/smoke-test.sh

echo "All package checks PASS"
