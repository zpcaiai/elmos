#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

echo "=========================================================="
echo "ELMOS Independent Frontend/Client Modernization Verification Replay"
echo "Target Dossier: $(basename "${SCRIPT_DIR}")"
echo "=========================================================="

echo "[1/5] Verifying Batch 32 skills and portable check..."
make -C "${REPO_ROOT}" batch32-portable-check

echo "[2/5] Verifying component-dialect-engine test suite (376 tests)..."
cd "${REPO_ROOT}/engines/component-dialect-engine" && npm run build && npx jest --runInBand

echo "[3/5] Validating web-console WeChat dual-track delivery pack (71/71 components)..."
cd "${REPO_ROOT}/engines/component-dialect-engine" && npm run validate:web-console-wechat

echo "[4/5] Verifying Enterprise Frontend Transpiler coverage (100% automated coverage)..."
cd "${REPO_ROOT}" && uv run python -m unittest tests.batch32.test_enterprise_frontend_transpiler

echo "[5/5] Running client gate on web-console client pack & verifying certifier signature..."
python3 "${REPO_ROOT}/scripts/batch32/run_client_gate.py" "${REPO_ROOT}/client-packs/web-console-next16-react19-wechat-v1"

openssl dgst -sha256 -verify "${REPO_ROOT}/certification/keys/ethan-independent-certifier.pub.pem" \
  -signature "${SCRIPT_DIR}/certification-request.sig" \
  "${SCRIPT_DIR}/certification-request.json"

echo "Replay complete. All Frontend/Client Modernization checks PASSED in independent replay."
