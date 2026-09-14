#!/usr/bin/env bash
set -euo pipefail

echo "BLOCKED / NOT_CERTIFIED: this dossier used a repository-held private key revoked by ELMOS-CERT-KEY-2026-09-13-01" >&2
echo "Ethan must independently replay exact-SHA evidence and sign outside the repository with a new authenticated key." >&2
exit 2
