#!/usr/bin/env python3
from pathlib import Path
import csv,json,sys,yaml
R=Path(sys.argv[1] if len(sys.argv)>1 else Path(__file__).resolve().parents[1]); E=[]
def e(x): E.append(x)
req=['README.md','manifest.json','technology-registry.json','repository-surface-registry.json','route-registry.json','route-matrix.csv','p0-mutual-route-matrix.csv','SKILL_INDEX.md']
for x in req:
    if not (R/x).exists(): e('missing '+x)
m=json.loads((R/'manifest.json').read_text()); sk=m['skills']; names={x['name'] for x in sk}
if len(sk)!=168 or m['package']['skill_count']!=168: e('skill count')
if len(m['technologies'])!=28 or len(set(m['technologies']))!=28: e('technology count')
if len(m['repository_surfaces'])!=8: e('repository surface count')
if len(names)!=168 or len({x['id'] for x in sk})!=168: e('duplicate skills')
sections=['## Objective','## When to use','## Preconditions','## Inputs','## Outputs','## Guardrails','## Workflow','## Implementation Contract','## Required Tests','## Verification','## Stop and Escalate','## Definition of Done','## Completion Report']
for s in sk:
 p=R/s['path']
 if not p.exists(): e('missing skill '+s['name']); continue
 t=p.read_text()
 for sec in sections:
  if sec not in t: e(s['name']+' missing '+sec)
 try: fm=yaml.safe_load(t.split('---',2)[1])
 except Exception: e('bad frontmatter '+s['name']); continue
 if fm.get('name')!=s['name'] or fm.get('skill_id')!=s['id'] or fm.get('readiness')!='not-run': e('frontmatter '+s['name'])
for s in sk:
 for d in s['dependencies']:
  if d not in names: e('unknown dep '+s['name']+'->'+d)
# cycles
g={s['name']:s['dependencies'] for s in sk}; st={}
def dfs(n,path):
 if st.get(n)==1: e('cycle '+'->'.join(path+[n])); return
 if st.get(n)==2:return
 st[n]=1
 for q in g[n]: dfs(q,path+[n])
 st[n]=2
for n in g: dfs(n,[])
with (R/'route-matrix.csv').open() as f: rows=list(csv.DictReader(f))
if len(rows)!=784 or len({(x['source'],x['target']) for x in rows})!=784: e('route matrix')
if any(x['readiness']!='not-run' for x in rows): e('route readiness')
rr=json.loads((R/'route-registry.json').read_text())
if len(rr['spec']['profiles'])!=40: e('route profile count')
for x in rr['spec']['profiles']:
 if not (R/x['profile']).exists(): e('missing profile '+x['profile'])
tr=json.loads((R/'technology-registry.json').read_text())
if len(tr['spec']['technologies'])!=28: e('technology registry count')
sr=json.loads((R/'repository-surface-registry.json').read_text())
if len(sr['spec']['surfaces'])!=8: e('surface registry count')
if E:
 [print('FAIL:',x) for x in E]; raise SystemExit(1)
print('PASS: 168 Skills')
print('PASS: 28 primary technologies + 8 repository surfaces')
print('PASS: 784 route cells + 40 reference profiles')
print('PASS: dependency graph/frontmatter/readiness')
