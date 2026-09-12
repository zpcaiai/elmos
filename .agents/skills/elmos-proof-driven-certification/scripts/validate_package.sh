#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }
skip() { echo "SKIP: $*"; }

[[ -f "$SKILL_DIR/SKILL.md" ]] || fail "SKILL.md missing"
grep -q '^---$' "$SKILL_DIR/SKILL.md" || fail "SKILL.md YAML frontmatter delimiter missing"
grep -q '^name: elmos-proof-driven-certification$' "$SKILL_DIR/SKILL.md" || fail "skill name missing/wrong"
grep -q '^description: .\+' "$SKILL_DIR/SKILL.md" || fail "skill description missing"
pass "SKILL.md frontmatter"

for d in references policies templates schemas scripts; do
  [[ -d "$SKILL_DIR/$d" ]] || fail "$d/ missing"
done
pass "required directories"

python3 - "$SKILL_DIR" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
for p in list((root/'schemas').glob('*.json')) + list((root/'templates').glob('*.json')):
    with p.open('r', encoding='utf-8') as f:
        json.load(f)
print('PASS: all JSON files parse')
PY

if python3 - <<'PY' >/dev/null 2>&1
import jsonschema
PY
then
  python3 - "$SKILL_DIR" <<'PY'
import json
from pathlib import Path
import sys
import jsonschema
root = Path(sys.argv[1])
pairs = [
 ('verification-request.schema.json','verification-request.json'),
 ('verification-ticket-claims.schema.json','verification-ticket-claims.json'),
 ('execution-evidence.schema.json','execution-evidence.json'),
 ('evidence-manifest.schema.json','evidence-manifest.json'),
 ('semantic-audit.schema.json','semantic-audit.json'),
 ('gate-decision.schema.json','gate-decision.json'),
]
for s,t in pairs:
    schema=json.loads((root/'schemas'/s).read_text())
    instance=json.loads((root/'templates'/t).read_text())
    jsonschema.Draft202012Validator(schema).validate(instance)
print('PASS: templates validate against JSON Schemas')
PY
else
  skip "python jsonschema not installed; schema-instance validation"
fi

if command -v opa >/dev/null 2>&1; then
  opa test "$SKILL_DIR/policies/base" -v
  pass "OPA policy tests"
else
  skip "opa binary not installed; OPA policy tests"
fi

if [[ -f "$SKILL_DIR/../MANIFEST.sha256" ]] && command -v shasum >/dev/null 2>&1; then
  (cd "$SKILL_DIR/.." && shasum -a 256 -c MANIFEST.sha256)
  pass "package SHA-256 manifest"
else
  skip "manifest unavailable in installed-skill-only layout or shasum unavailable"
fi

echo "VALIDATION COMPLETE"
