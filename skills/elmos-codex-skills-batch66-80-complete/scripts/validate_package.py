#!/usr/bin/env python3
import json,re
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def fail(x): print('FAIL:',x); raise SystemExit(1)
m=json.loads((R/'manifest.json').read_text()); paths=sorted((R/'agent-skills/runtime').glob('*/SKILL.md'))
if len(paths)!=m['skill_count']: fail(f"expected {m['skill_count']}, found {len(paths)}")
req=['## Objective','## When to Use','## Scope','## Inputs','## Outputs','## Preconditions','## Workflow','## Implementation Requirements','## Required Project Checks','## Security and Hard Rules','## Required Tests','## Verification','## Stop and Escalate','## Evidence Contract','## Definition of Done','## Completion Report']
names=[];ids=[]
for p in paths:
 t=p.read_text(); a=re.search(r'^name:\s*([a-z0-9-]+)\s*$',t,re.M); b=re.search(r'^\s*id:\s*(PG\d+)\s*$',t,re.M)
 if not a or not b or a.group(1)!=p.parent.name: fail(f'frontmatter/path {p}')
 for h in req:
  if h not in t: fail(f'{h} missing in {p}')
 names.append(a.group(1));ids.append(int(b.group(1)[2:]))
if len(set(names))!=len(names) or len(set(ids))!=len(ids): fail('duplicates')
lo=int(m['id_range'][0][2:]);hi=int(m['id_range'][1][2:])
if sorted(ids)!=list(range(lo,hi+1)): fail('ID range mismatch')
for p in list((R/'schemas').glob('*.json'))+list((R/'templates').glob('*.json'))+[R/'index.json']:
 json.loads(p.read_text())
for mf in (R/'manifests').glob('batch-*.json'):
 for e in json.loads(mf.read_text())['skills']:
  if not (R/e['path']).exists(): fail(e['path'])
print(f"PASS: {len(paths)} Skills validated; IDs {m['id_range'][0]}-{m['id_range'][1]}")
