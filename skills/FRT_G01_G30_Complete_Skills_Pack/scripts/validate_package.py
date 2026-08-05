#!/usr/bin/env python3
from pathlib import Path
import json,re,sys
root=Path(__file__).resolve().parents[1]
errors=[]
manifest=json.loads((root/'manifest.json').read_text())
expected=manifest['spec']['skillCount']
files=sorted((root/'skills').glob('*/SKILL.md'))
if len(files)!=expected: errors.append(f'skill count {len(files)} != {expected}')
ids=[]
required=['## Objective','## Workflow','## Verification','## Stop and Escalate When','## Definition of Done']
for f in files:
    t=f.read_text(encoding='utf-8')
    if not t.startswith('---\n'): errors.append(f'{f}: missing frontmatter')
    m=re.search(r'^skill_id:\s*(FRT-\d+)',t,re.M)
    if not m: errors.append(f'{f}: missing skill_id')
    else: ids.append(m.group(1))
    for h in required:
        if h not in t: errors.append(f'{f}: missing {h}')
if len(ids)!=len(set(ids)): errors.append('duplicate skill ids')
for n in range(1,31):
    hits=list((root/'batches').glob(f'G{n:02d}_*/SKILL.md'))
    if len(hits)!=1: errors.append(f'G{n:02d}: expected one batch spec, got {len(hits)}')
secret_patterns=[r'-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----',r'(?i)password\s*[:=]\s*["\'][^"\']+["\']',r'(?<![A-Za-z0-9])sk-proj-[A-Za-z0-9_-]{20,}']
for f in root.rglob('*'):
    if f.is_file() and f.suffix in {'.md','.yaml','.yml','.json','.py','.sh'}:
        txt=f.read_text(encoding='utf-8',errors='ignore')
        for p in secret_patterns:
            if re.search(p,txt): errors.append(f'{f}: possible secret pattern')
if errors:
    print('FAIL')
    for e in errors: print('-',e)
    sys.exit(1)
print(f'PASS: 30 batches, {len(files)} individual skills, unique IDs, required sections and static secret checks')
