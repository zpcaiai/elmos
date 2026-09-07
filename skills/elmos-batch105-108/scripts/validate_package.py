#!/usr/bin/env python3
from __future__ import annotations
import json, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REQ=['## Objective','## Implementation scope','## Inputs and outputs','## Repository modules','## Interfaces and state','## Execution workflow','## Tests','## Evidence','## Stop and escalate','## Definition of done','## Codex execution contract']

def load(): return json.loads((ROOT/'manifest.json').read_text())
def validate(raise_on_error=True):
 errors=[]; m=load(); skills=[]; ids=set(); names=set()
 expected_total=int(m.get('skillCount',0))
 for b in m['batches']:
  if len(b['skills'])!=16: errors.append(f"Batch {b['batch']} count != 16")
  expected=[f"B{b['batch']}-S{i:02d}" for i in range(1,17)]
  actual=[s['id'] for s in b['skills']]
  if actual!=expected: errors.append(f"Batch {b['batch']} IDs not continuous")
  for s in b['skills']:
   skills.append(s); p=ROOT/s['path']; c=ROOT/s['contract']
   if not p.exists(): errors.append(f"missing {p}"); continue
   if not c.exists(): errors.append(f"missing {c}"); continue
   text=p.read_text()
   fm=re.search(r'^---\nname:\s*(.+)\ndescription:',text)
   if not fm or fm.group(1).strip()!=s['name']: errors.append(f"frontmatter mismatch {s['id']}")
   for sec in REQ:
    if sec not in text: errors.append(f"{s['id']} missing {sec}")
   obj=json.loads(c.read_text())
   if obj['id']!=s['id'] or obj['name']!=s['name']: errors.append(f"contract identity mismatch {s['id']}")
   for key,minn in [('inputs',1),('outputs',1),('workflow',5),('tests',4),('evidence',3),('definition_of_done',4),('risk_controls',2)]:
    if len(obj.get(key,[]))<minn: errors.append(f"{s['id']} insufficient {key}")
   if s['id'] in ids: errors.append(f"duplicate id {s['id']}")
   if s['name'] in names: errors.append(f"duplicate name {s['name']}")
   ids.add(s['id']); names.add(s['name'])
 if len(skills)!=expected_total: errors.append(f'skill count {len(skills)} != manifest {expected_total}')
 g=json.loads((ROOT/'graph/capability-graph.json').read_text()); nodeids={n['id'] for n in g['nodes']}; ext={n['id'] for n in g.get('externalNodes',[])}
 if nodeids!=ids: errors.append('graph nodes != manifest ids')
 adj={n:[] for n in nodeids}; indeg={n:0 for n in nodeids}
 for e in g['edges']:
  if e['to'] not in nodeids: errors.append(f"unknown edge target {e['to']}"); continue
  if e['from'] not in nodeids|ext: errors.append(f"unknown edge source {e['from']}"); continue
  if e['from'] in nodeids: adj[e['from']].append(e['to']); indeg[e['to']]+=1
 q=[n for n,d in indeg.items() if d==0]; seen=[]
 while q:
  n=q.pop(); seen.append(n)
  for v in adj[n]:
   indeg[v]-=1
   if indeg[v]==0:q.append(v)
 if len(seen)!=len(nodeids): errors.append('blocking dependency cycle')
 for p in (ROOT/'examples/runtime').glob('*.json'):
  o=json.loads(p.read_text())
  if o.get('version')!=1 or o['lifecycle'].get('startTtlAfterReady') is not True: errors.append(f"bad runtime example {p.name}")
  if '@sha256:' not in o['build']['image'] or '@sha256:' not in o['runtime']['image']: errors.append(f"unpinned image {p.name}")
 if errors and raise_on_error: raise SystemExit('\n'.join('ERROR: '+e for e in errors))
 return errors
if __name__=='__main__':
 errors=validate(False)
 if errors:
  print('\n'.join('ERROR: '+e for e in errors)); sys.exit(1)
 print(f"PASS: {load()['skillCount']} skills, contracts, manifest, graph, schemas and examples validated")
