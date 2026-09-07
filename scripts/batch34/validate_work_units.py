#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import jsonschema
from _graph_validation import find_cycle,unique_ids
def main():
 p=argparse.ArgumentParser(); p.add_argument('plan'); p.add_argument('--inventory'); a=p.parse_args(); path=Path(a.plan); data=json.loads(path.read_text()); schema=json.loads((Path(__file__).resolve().parents[2]/'schemas/batch34/work-unit-plan.schema.json').read_text()); errors=[]
 try: jsonschema.validate(data,schema)
 except Exception as e: errors.append(str(e))
 ids,e=unique_ids(data.get('units',[]),'units'); errors+=e
 repo_ids=None
 if a.inventory: repo_ids={r['id'] for r in json.loads(Path(a.inventory).read_text()).get('repositories',[])}
 for u in data.get('units',[]):
  if not u.get('repository_ids') and not u.get('module_refs'): errors.append(f"unit {u.get('id')}: no repositories or modules")
  for dep in u.get('dependencies',[]):
   if dep not in ids: errors.append(f"unit {u.get('id')}: unknown dependency {dep}")
   if dep==u.get('id'): errors.append(f"unit {u.get('id')}: self dependency")
  if repo_ids is not None:
   for r in u.get('repository_ids',[]):
    if r not in repo_ids: errors.append(f"unit {u.get('id')}: unknown repository {r}")
 cycle=find_cycle({u.get('id'):u.get('dependencies',[]) for u in data.get('units',[]) if u.get('id')})
 if cycle: errors.append('work-unit dependency cycle: '+' -> '.join(cycle))
 if errors: print('\n'.join('ERROR: '+x for x in errors),file=sys.stderr); return 1
 print(f'OK: work units={len(ids)}'); return 0
if __name__=='__main__': raise SystemExit(main())
