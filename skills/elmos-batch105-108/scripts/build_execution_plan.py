#!/usr/bin/env python3
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(); p.add_argument('targets',nargs='+'); p.add_argument('--out',default='execution-plan.json'); a=p.parse_args()
manifest=json.loads((ROOT/'manifest.json').read_text())
contracts={}
for f in (ROOT/'contracts').glob('batch-*/*.json'):
 o=json.loads(f.read_text()); contracts[o['id']]=o
external=set(manifest.get('externalDependencies',[])); visiting=set(); done=set(); order=[]; used_external=set()
def visit(i):
 if i in external: used_external.add(i); return
 if i not in contracts: raise SystemExit(f'unknown skill {i}')
 if i in visiting: raise SystemExit(f'cycle at {i}')
 if i in done:return
 visiting.add(i)
 for d in contracts[i]['dependencies']:visit(d)
 visiting.remove(i);done.add(i);order.append(i)
for t in a.targets:visit(t)
plan={'targets':a.targets,'externalPrerequisites':sorted(used_external),'steps':[{'sequence':n+1,'id':i,'name':contracts[i]['name'],'contract':f'contracts/batch-{contracts[i]["batch"]}/{i}.json'} for n,i in enumerate(order)]}
Path(a.out).write_text(json.dumps(plan,indent=2)+'\n'); print(f'wrote {len(order)}-step plan to {a.out}')
