#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$ROOT/scripts/validate_skill_bundle.py" "$ROOT"
python3 "$ROOT/scripts/validate_json_schemas.py" "$ROOT"
python3 -m unittest discover -s "$ROOT/tests" -v
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
"$ROOT/install.sh" "$TMP/target" --profile all
test -f "$TMP/target/.agents/skills/elmos-infrastructure-program-orchestrator/SKILL.md"
test -f "$TMP/target/.claude/skills/elmos-production-readiness-gate/SKILL.md"
test -f "$TMP/target/.codex/skills/elmos-java-migration-production-loop/SKILL.md"
test -f "$TMP/target/docs/elmos-infrastructure-foundation/TASK-MATRIX.csv"
"$ROOT/uninstall.sh" "$TMP/target" --profile all
test ! -e "$TMP/target/.agents/skills/elmos-infrastructure-program-orchestrator"
echo "PASS: smoke installation and removal"
