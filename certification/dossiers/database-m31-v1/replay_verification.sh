#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

echo "=========================================================="
echo "ELMOS Independent Database Modernization Verification Replay"
echo "Target Dossier: $(basename "${SCRIPT_DIR}")"
echo "=========================================================="

echo "[1/4] Verifying Batch 31 quality gates on all database packs..."
make -f "${REPO_ROOT}/Makefile.batch31" b31-all-packs-check

echo "[2/4] Verifying SQL dialect engine and transpiler test suites..."
make -C "${REPO_ROOT}" sql-transpiler
make -C "${REPO_ROOT}" sql-dialect

echo "[3/4] Verifying ChinaDB commercial qualification & launch scope..."
uv run --directory "${REPO_ROOT}" --quiet --with jsonschema --with pyyaml python "${REPO_ROOT}/scripts/batch31/validate_sql_line_launch_scope.py" "${REPO_ROOT}/docs/batch31/sql-line-launch-scope.json"

echo "[4/4] Cryptographically verifying independent certifier signature..."
openssl dgst -sha256 -verify "${REPO_ROOT}/certification/keys/ethan-independent-certifier.pub.pem" \
  -signature "${SCRIPT_DIR}/certification-request.sig" \
  "${SCRIPT_DIR}/certification-request.json"

echo "Replay complete. All database modernization checks PASSED in independent replay."
