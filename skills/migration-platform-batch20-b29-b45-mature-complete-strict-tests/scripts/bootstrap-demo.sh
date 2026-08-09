#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${CONTROL_PLANE_URL:-http://localhost:8080}"
curl -fsS -X POST "$BASE_URL/api/v1/demo/bootstrap" | python3 -m json.tool
