#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COUNT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["skillCount"])' "$ROOT/manifest.json")"
BATCHES="$(python3 -c 'import json,sys; print(" ".join(str(b["batch"]) for b in json.load(open(sys.argv[1]))["batches"]))' "$ROOT/manifest.json")"
TARGET="$(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(m["batches"][-1]["skills"][-1]["id"])' "$ROOT/manifest.json")"
python3 "$ROOT/scripts/validate_package.py"
python3 -m unittest discover -s "$ROOT/tests" -p 'test_*.py' -v
bash -n "$ROOT/install.sh" "$ROOT/validate.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
bash "$ROOT/install.sh" "$TMP/skills"
[[ "$(find "$TMP/skills" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')" == "$COUNT" ]]
if bash "$ROOT/install.sh" "$TMP/skills" 2>/dev/null; then echo 'duplicate install should fail' >&2; exit 1; fi
for b in $BATCHES; do rm -rf "$TMP/b$b"; bash "$ROOT/install.sh" "$TMP/b$b" --batch "$b"; [[ "$(find "$TMP/b$b" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')" == "16" ]]; done
python3 "$ROOT/scripts/compile_contracts.py" --out "$TMP/contracts"
python3 "$ROOT/scripts/build_execution_plan.py" --out "$TMP/plan.json" "$TARGET"
python3 "$ROOT/scripts/run_conservative_gate.py" "$ROOT/tests/fixtures/valid-candidate.json" --out "$TMP/good.json"
if python3 "$ROOT/scripts/run_conservative_gate.py" "$ROOT/tests/fixtures/forged-success.json" --out "$TMP/bad.json" >/dev/null 2>&1; then echo 'forged success should be rejected' >&2; exit 1; fi
echo "PASS: $COUNT skills; installer, compiler, planner, conservative gate and batch installs"
