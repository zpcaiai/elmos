#!/usr/bin/env python3
from pathlib import Path
import json,re,sys
root=Path(__file__).resolve().parents[1]
required=['README.md','CODEX_IMPLEMENTATION_PROMPT.md','SKILL.md','SKILL_INDEX.md','IMPLEMENTATION_CHECKLIST.md','VALIDATION_REPORT.md','PACKAGE_MANIFEST.json']
errors=[]
for f in required:
    if not (root/f).exists(): errors.append('missing '+f)
skills=list((root/'skills').glob('*/SKILL.md'))
if len(skills)!=16: errors.append(f'expected 16 skills, got {len(skills)}')
names=[]
for p in skills:
    t=p.read_text(encoding='utf-8')
    m=re.search(r'^name:\s*([^\n]+)',t,re.M)
    if not m: errors.append('missing name '+str(p)); continue
    n=m.group(1).strip(); names.append(n)
    if n!=p.parent.name: errors.append('name mismatch '+str(p))
    for h in ['## Objective','## Workflow','## Required Tests','## Verification','## Stop and Escalate','## Definition of Done']:
        if h not in t: errors.append(f'{p}: missing {h}')
if len(names)!=len(set(names)): errors.append('duplicate skill name')
for p in (root/'schemas').glob('*.json'):
    try: json.loads(p.read_text(encoding='utf-8'))
    except Exception as e: errors.append(f'invalid json {p}: {e}')
manifest=json.loads((root/'PACKAGE_MANIFEST.json').read_text(encoding='utf-8')) if (root/'PACKAGE_MANIFEST.json').exists() else {}
if manifest and manifest.get('skill_count')!=16: errors.append('manifest skill_count')
if errors:
    print('FAIL'); print('\n'.join(errors)); sys.exit(1)
print('PASS: 16 skills; schemas and required files valid.')
