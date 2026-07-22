#!/usr/bin/env python3
from pathlib import Path
import re, sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
manifest=__import__('json').load(open(root/'manifest.json',encoding='utf-8'))
expected=manifest['test_skill_count']; entries=manifest['skills']
if expected!=35 or len(entries)!=expected: raise SystemExit('ERROR: expected 35 test skills')
names=set(); codes=set(); required=['## Objective','## Workflow','## Verification','## Stop and Escalate','## Evidence Contract','## Definition of Done','## Completion Report']
for e in entries:
    p=root/e['path']
    if not p.exists(): raise SystemExit(f'ERROR: missing {p}')
    t=p.read_text(encoding='utf-8')
    m=re.search(r'^name:\s*(\S+)\s*$',t,re.M); c=re.search(r'^\s*id:\s*(\S+)\s*$',t,re.M)
    if not m or m.group(1)!=e['name']: raise SystemExit(f'ERROR: frontmatter name mismatch {p}')
    if not c or c.group(1)!=e['code']: raise SystemExit(f'ERROR: code mismatch {p}')
    if m.group(1) in names or c.group(1) in codes: raise SystemExit('ERROR: duplicate test skill')
    names.add(m.group(1)); codes.add(c.group(1))
    for h in required:
        if h not in t: raise SystemExit(f'ERROR: missing {h} in {p}')
print(f'PASS: {expected} test skills validated')
