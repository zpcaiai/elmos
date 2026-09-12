#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

echo "=========================================================="
echo "ELMOS Independent Spring Boot 4.x Verification Replay"
echo "Target Dossier: $(basename "${SCRIPT_DIR}")"
echo "=========================================================="

echo "[1/2] Verifying Batch 30 framework gates on all 7 production packs..."
python3 "${REPO_ROOT}/scripts/operations/run_spring_boot_4_external_gate.py"

echo "[2/2] Cryptographically verifying independent certifier signature..."
openssl dgst -sha256 -verify "${REPO_ROOT}/certification/keys/ethan-independent-certifier.pub.pem" \
  -signature "${SCRIPT_DIR}/certification-request.sig" \
  "${SCRIPT_DIR}/certification-request.json"

echo "Replay verification complete. All 7 Spring Boot 4.x routes CERTIFIED with authentic cryptographic proof."
