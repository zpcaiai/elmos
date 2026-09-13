#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

echo "=========================================================="
echo "ELMOS Independent Polyglot Routes Verification Replay"
echo "Target Dossier: $(basename "${SCRIPT_DIR}")"
echo "=========================================================="

echo "[1/2] Verifying Polyglot external gate on all 210 production routes..."
python3 "${REPO_ROOT}/scripts/operations/run_polyglot_external_gate.py"

echo "[2/2] Cryptographically verifying independent certifier signature..."
openssl dgst -sha256 -verify "${REPO_ROOT}/certification/keys/ethan-independent-certifier.pub.pem" \
  -signature "${SCRIPT_DIR}/certification-request.sig" \
  "${SCRIPT_DIR}/certification-request.json"

echo "Replay verification complete. All 210 Polyglot routes CERTIFIED with authentic cryptographic proof."
