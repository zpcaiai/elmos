#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$HERE/elmos-auto-skill-router"

fail(){ echo "FAIL: $*" >&2; exit 1; }
pass(){ echo "PASS: $*"; }

[[ -f "$SKILL/SKILL.md" ]] || fail "SKILL.md missing"
grep -q '^name: elmos-auto-skill-router$' "$SKILL/SKILL.md" || fail "skill frontmatter name missing"
pass "skill frontmatter"
python3 -m json.tool "$SKILL/templates/skill-router.json" >/dev/null
pass "router config JSON"
python3 -m py_compile "$HERE/install.py" "$SKILL/scripts/refresh_skill_index.py" "$SKILL/scripts/route_skills.py"
pass "Python compilation"
bash -n "$HERE/install.sh" "$SKILL/scripts/continue-with-skills.sh" "$SKILL/scripts/check_install.sh"
pass "shell syntax"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/repo/.agents/skills/sample-spring"
cat > "$TMP/repo/.agents/skills/sample-spring/SKILL.md" <<'EOF'
---
name: sample-spring
description: Spring Boot modernization, migration, integration tests and compatibility work.
---
# Sample
EOF
mkdir -p "$TMP/repo/.agents/skills/elmos-proof-driven-certification"
cat > "$TMP/repo/.agents/skills/elmos-proof-driven-certification/SKILL.md" <<'EOF'
---
name: elmos-proof-driven-certification
description: Proof-driven verification, execution evidence, truth runner, OPA and certification integrity.
---
# Sample
EOF
cat > "$TMP/repo/.agents/AGENTS.md" <<'EOF'
# Existing Rules
Preserve me.
EOF
"$HERE/install.sh" "$TMP/repo" >/dev/null
"$TMP/repo/.agents/skills/elmos-auto-skill-router/scripts/check_install.sh" "$TMP/repo" >/dev/null
pass "fresh install and smoke test"
grep -q 'Preserve me.' "$TMP/repo/.agents/AGENTS.md" || fail "installer overwrote existing AGENTS.md"
pass "existing AGENTS.md preserved"

# Reinstall must be idempotent: exactly one router block.
"$HERE/install.sh" "$TMP/repo" >/dev/null
COUNT="$(grep -c 'ELMOS_AUTO_SKILL_ROUTER_BEGIN' "$TMP/repo/.agents/AGENTS.md")"
[[ "$COUNT" == "1" ]] || fail "router block duplicated on reinstall"
pass "idempotent reinstall"

ROUTE="$(python3 "$TMP/repo/.agents/skills/elmos-auto-skill-router/scripts/route_skills.py" --root "$TMP/repo" --task 'verify Spring migration evidence with OPA')"
echo "$ROUTE" | grep -q 'sample-spring' || fail "domain skill not routed"
echo "$ROUTE" | grep -q 'elmos-proof-driven-certification' || fail "mandatory trust skill not routed"
pass "multi-skill composition"

python3 "$TMP/repo/.agents/skills/elmos-auto-skill-router/scripts/route_skills.py" --root "$TMP/repo" --task 'verify Spring migration evidence with OPA' --remember >/dev/null
CONT="$(python3 "$TMP/repo/.agents/skills/elmos-auto-skill-router/scripts/route_skills.py" --root "$TMP/repo" --task 'continue')"
echo "$CONT" | grep -q 'sample-spring' || fail "continue did not restore last skill route"
pass "continuation route memory"

echo "PACKAGE VALIDATION OK"
