#!/usr/bin/env python3
from pathlib import Path
import csv,json,sys,yaml,re
R=Path(sys.argv[1] if len(sys.argv)>1 else Path(__file__).resolve().parents[1]); E=[]
def err(x): E.append(x)
req=['README.md','manifest.json','route-certification-registry.json','SKILL_INDEX.md','certification-corpus/corpus-registry.json','native-runtime-lab/lab-registry.json']
for x in req:
 if not (R/x).exists(): err('missing '+x)
m=json.loads((R/'manifest.json').read_text()); sk=m['skills']; names={x['name'] for x in sk}
if len(sk)!=132 or m['package'].get('skill_count')!=132: err('skill count')
if len(names)!=132 or len({x['id'] for x in sk})!=132: err('duplicate skill')
ids=sorted(int(x['id'].split('-')[-1]) for x in sk)
if ids!=list(range(169,301)): err('skill id continuity')
sections=['## Objective','## When to use','## Preconditions','## Inputs','## Outputs','## Guardrails','## Workflow','## Implementation Contract','## Required Tests','## Verification','## Stop and Escalate','## Definition of Done','## Completion Report']
for s in sk:
 p=R/s['path']
 if not p.exists(): err('missing skill '+s['name']); continue
 t=p.read_text()
 for sec in sections:
  if sec not in t: err(s['name']+' missing '+sec)
 try: fm=yaml.safe_load(t.split('---',2)[1])
 except Exception as ex: err('bad frontmatter '+s['name']); continue
 if fm.get('name')!=s['name'] or fm.get('skill_id')!=s['id'] or fm.get('readiness')!='not-run': err('frontmatter '+s['name'])
for s in sk:
 for d in s.get('dependencies',[]):
  if d not in names and not d.startswith('elmos-'): err('bad dep '+s['name']+'->'+d)
g={s['name']:[d for d in s.get('dependencies',[]) if d in names] for s in sk}; state={}
def dfs(n,path):
 if state.get(n)==1: err('cycle '+'->'.join(path+[n])); return
 if state.get(n)==2:return
 state[n]=1
 for q in g[n]: dfs(q,path+[n])
 state[n]=2
for n in g: dfs(n,[])
rc=json.loads((R/'route-certification-registry.json').read_text())
if len(rc['spec']['routes'])!=40: err('cert count')
for x in rc['spec']['routes']:
 if x['readiness']!='not-run': err('cert readiness')
 for s in x['requiredSemanticSkills']:
  if s not in names: err('unknown cert skill '+s)
for name in ['semantic-obligation.schema.json','fixture-manifest.schema.json','runtime-lab-profile.schema.json','behavior-oracle.schema.json','differential-result.schema.json','proof-obligation.schema.json','counterexample.schema.json','certification-run.schema.json','conformance-mapping.schema.json','coverage-metric.schema.json']:
 try: json.loads((R/'schemas'/name).read_text())
 except Exception: err('bad/missing schema '+name)
# simple secret markers
badpat=re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|sk-[A-Za-z0-9]{20,}')
for p in R.rglob('*'):
 if p.is_file() and p.stat().st_size<2_000_000 and p.suffix not in {'.zip','.gz','.png','.jpg','.pyc'}:
  try: t=p.read_text(errors='ignore')
  except: continue
  if badpat.search(t): err('secret-like material '+str(p.relative_to(R)))
if E:
 [print('FAIL:',x) for x in E]; raise SystemExit(1)
print('PASS: 132 semantic assurance expansion Skills')
print('PASS: IDs 169..300, frontmatter and required sections')
print('PASS: 40 route certification plans')
print('PASS: 10 semantic assurance schemas + corpus/lab registries')
print('PASS: all static readiness states remain not-run')
