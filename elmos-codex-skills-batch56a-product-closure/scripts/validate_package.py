#!/usr/bin/env python3
from pathlib import Path
import json,re,sys
root=Path(__file__).resolve().parents[1]
m=json.loads((root/'manifest.json').read_text())
errs=[]
req=['## Objective','## Scope','## Preconditions','## Domain Model','## Workflow','## Required Tests','## Verification','## Stop and Escalate','## Definition of Done','## Completion Report']
if m.get('skillCount')!=16 or len(m.get('skills',[]))!=16: errs.append('expected 16 skills')
seen=set()
for s in m['skills']:
 p=root/s['path']
 if not p.exists(): errs.append('missing '+str(p)); continue
 x=p.read_text()
 if s['name'] in seen: errs.append('duplicate '+s['name'])
 seen.add(s['name'])
 mm=re.search(r'^name:\s*(.+)$',x,re.M)
 if not mm or mm.group(1).strip()!=s['name']: errs.append('name mismatch '+s['name'])
 if p.parent.name!=s['name']: errs.append('dir mismatch '+s['name'])
 for q in req:
  if q not in x: errs.append('missing '+q+' in '+s['name'])
 if 'BEGIN PRIVATE KEY' in x: errs.append('secret pattern '+s['name'])
for p in (root/'schemas').glob('*.json'): json.loads(p.read_text())
for p in (root/'templates').glob('*.json'): json.loads(p.read_text())
if errs:
 print('FAIL'); [print('-',e) for e in errs]; sys.exit(1)
print('PASS: 16 skills validated')
print('PASS: frontmatter, required sections, JSON and secret scan')
