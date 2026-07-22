#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
python3 scripts/test-suite-b66-80/validate_skill_bundle.py .
python3 scripts/test-suite-b66-80/validate_test_catalog.py test-suites/batch66-80-slightly-strict/cases/catalog.json
python3 scripts/test-suite-b66-80/validate_coverage_matrix.py test-suites/batch66-80-slightly-strict/coverage-matrix.json test-suites/batch66-80-slightly-strict/cases/catalog.json
python3 scripts/test-suite-b66-80/validate_result_files.py test-suites/batch66-80-slightly-strict
python3 -m unittest discover -s tests -v
bash -n install.sh validate.sh
echo "PASS: static package validation complete; runtime gate remains NOT_RUN"
