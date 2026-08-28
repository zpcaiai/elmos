#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 -m compileall -q etgb tests
python3 -m etgb skills-audit
python3 -m etgb validate
python3 -m etgb coverage
python3 -m etgb feature-coverage --output reports/FEATURE_COVERAGE.json
python3 -m etgb surface-audit examples/product-surface.yaml --output reports/SURFACE_AUDIT.json
python3 -m etgb freeze-candidate examples/release-candidate.yaml --output reports/example-frozen-candidate.json
python3 -m etgb policy-check examples/environment-authority.yaml examples/policy-request-allowed.json
if python3 -m etgb policy-check examples/environment-authority.yaml examples/policy-request-denied.json; then
  echo "expected denied policy request to fail" >&2
  exit 2
fi
./scripts/run_smoke.sh
pytest -q
