#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"
ROOT="$(cd "$ROOT" && pwd)"
SKILL="$ROOT/.agents/skills/elmos-auto-skill-router"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

[[ -f "$SKILL/SKILL.md" ]] || fail "SKILL.md missing"
pass "SKILL.md installed"
[[ -f "$ROOT/.elmos/skill-router.json" ]] || fail ".elmos/skill-router.json missing"
pass "router config installed"
[[ -f "$ROOT/.agents/AGENTS.md" ]] || fail ".agents/AGENTS.md missing"
grep -q 'ELMOS_AUTO_SKILL_ROUTER_BEGIN' "$ROOT/.agents/AGENTS.md" || fail "AGENTS routing block missing"
pass "AGENTS auto-router block installed"

python3 "$SKILL/scripts/refresh_skill_index.py" --root "$ROOT" >/dev/null
[[ -s "$ROOT/.agents/skills-index.json" ]] || fail "skills-index.json not generated"
pass "skill index generated"
python3 -m py_compile "$SKILL/scripts/refresh_skill_index.py" "$SKILL/scripts/route_skills.py"
pass "Python scripts compile"

OUT="$(python3 "$SKILL/scripts/route_skills.py" --root "$ROOT" --task 'automatically route all relevant skills' --no-refresh)"
echo "$OUT" | grep -q 'elmos-auto-skill-router' || fail "router smoke test did not route itself"
pass "routing smoke test"

echo "INSTALLATION OK"
