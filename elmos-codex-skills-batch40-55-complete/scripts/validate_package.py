from __future__ import annotations
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
expected = manifest['skills']
errors = []
names = []
required = [
    '## Objective','## Scope','## Preconditions','## Required Capabilities',
    '## Core Workflow','## Required Artifacts','## Security, Governance and Domain Invariants',
    '## Workflow','## Implementation Requirements','## Required Tests','## Verification',
    '## Stop and Escalate','## Definition of Done','## Completion Report',
]
secret_patterns = [
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b'),
    re.compile(r'(?i)(?:api[_-]?key|password|secret|token)\s*[:=]\s*["\']?[A-Za-z0-9_\-]{28,}'),
]
for item in expected:
    p = ROOT / item['path']
    if not p.exists():
        errors.append(f'missing: {item["path"]}')
        continue
    text = p.read_text(encoding='utf-8')
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m:
        errors.append(f'bad frontmatter: {item["path"]}')
        continue
    nm = re.search(r'^name:\s*([^\n]+)$', m.group(1), re.M)
    if not nm:
        errors.append(f'missing name: {item["path"]}')
        continue
    name = nm.group(1).strip().strip('"\'')
    names.append(name)
    if name != item['name']:
        errors.append(f'name mismatch: {item["path"]}: {name} != {item["name"]}')
    if p.parent.name != name:
        errors.append(f'directory mismatch: {p.parent.name} != {name}')
    for section in required:
        if section not in text:
            errors.append(f'missing section {section}: {item["path"]}')
    for pat in secret_patterns:
        if pat.search(text):
            errors.append(f'possible secret: {item["path"]}')
actual = list((ROOT / 'agent-skills/runtime').glob('*/SKILL.md'))
if len(actual) != len(expected):
    errors.append(f'filesystem count {len(actual)} != manifest count {len(expected)}')
if len(set(names)) != len(names):
    errors.append('duplicate skill names')
if errors:
    print('FAIL')
    for e in errors:
        print('-', e)
    sys.exit(1)
print(f'PASS: {len(expected)} skills validated')
print('PASS: frontmatter, required sections, unique names and obvious-secret scan')
