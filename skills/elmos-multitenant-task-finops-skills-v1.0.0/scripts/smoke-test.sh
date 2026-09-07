#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"$ROOT/install.sh" --target "$TMP/skills"
test "$(find "$TMP/skills" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')" = "12"
test -f "$TMP/skills/elmos-account-concurrency-admission/SKILL.md"
"$ROOT/uninstall.sh" --target "$TMP/skills"
test ! -e "$TMP/skills/elmos-account-concurrency-admission"

echo "Smoke test PASS"
