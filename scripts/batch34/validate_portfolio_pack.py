#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
import jsonschema
FILES={'pack.json':'portfolio-pack.schema.json','support-matrix.json':'portfolio-support-matrix.schema.json','inventory/portfolio.json':'portfolio-inventory.schema.json','work-units/plan.json':'work-unit-plan.schema.json','graph/dependencies.json':'dependency-graph.schema.json','scale/scale-profile.json':'scale-profile.schema.json','campaigns/default.json':'campaign-plan.schema.json','benchmark/result.json':'benchmark-result.schema.json','dr/replay-plan.json':'dr-replay-plan.schema.json','certification/certification.json':'portfolio-certification.schema.json'}
PLACEHOLDERS={'','UNSET','UNASSIGNED','TBD','TODO'}
def load(p): return json.loads(p.read_text())
def main():
 p=argparse.ArgumentParser(); p.add_argument('pack_dir'); a=p.parse_args(); pack=Path(a.pack_dir); schema_root=Path(__file__).resolve().parents[2]/'schemas/batch34'; errors=[]; data={}
 for rel,sn in FILES.items():
  path=pack/rel
  if not path.is_file(): errors.append(f'missing {rel}'); continue
  try: obj=load(path); data[rel]=obj; jsonschema.validate(obj,load(schema_root/sn))
  except Exception as e: errors.append(f'{rel}: {e}')
 manifest=data.get('pack.json',{}); key=manifest.get('pack_key') if isinstance(manifest,dict) else None
 for rel,obj in data.items():
  if isinstance(obj,dict) and 'pack_key' in obj and obj.get('pack_key')!=key: errors.append(f'{rel}: pack_key mismatch')
 if isinstance(manifest,dict):
  if manifest.get('owner') in PLACEHOLDERS: errors.append('pack owner unset')
  if manifest.get('maintenance_owner') in PLACEHOLDERS: errors.append('maintenance owner unset')
  scope=manifest.get('scope',{})
  for f in ('tenant_model','inventory_snapshot_at'):
   if scope.get(f) in PLACEHOLDERS: errors.append(f'scope.{f} unset')
  for f in ('scm_sources','organizations','regions','languages','build_systems'):
   if not scope.get(f) or any(x in PLACEHOLDERS for x in scope.get(f,[])): errors.append(f'scope.{f} unset')
 inventory=data.get('inventory/portfolio.json',{})
 if isinstance(inventory,dict) and inventory.get('snapshot_digest') in PLACEHOLDERS: errors.append('inventory snapshot digest unset')
 graph=data.get('graph/dependencies.json',{}); work=data.get('work-units/plan.json',{})
 if isinstance(graph,dict) and isinstance(work,dict) and graph.get('graph_version')!=work.get('graph_version'): errors.append('graph and work-unit versions differ')
 if isinstance(inventory,dict) and isinstance(graph,dict):
  active={r.get('id') for r in inventory.get('repositories',[]) if r.get('status')=='active'}
  graph_repositories={n.get('id') for n in graph.get('nodes',[]) if n.get('kind')=='repository'}
  missing=sorted(active-graph_repositories)
  if missing: errors.append('active repositories missing from graph: '+','.join(missing))
  planned={repo for unit in work.get('units',[]) for repo in unit.get('repository_ids',[])} if isinstance(work,dict) else set()
  missing=sorted(active-planned)
  if missing: errors.append('active repositories missing from work units: '+','.join(missing))
 scale=data.get('scale/scale-profile.json',{})
 if isinstance(scale,dict):
  if scale.get('owner') in PLACEHOLDERS: errors.append('scale profile owner unset')
  if scale.get('environment',{}).get('runner_image_digest') in PLACEHOLDERS: errors.append('runner image digest unset')
 campaign=data.get('campaigns/default.json',{})
 if isinstance(campaign,dict):
  if campaign.get('owner') in PLACEHOLDERS: errors.append('campaign owner unset')
  if campaign.get('inventory_snapshot_digest') in PLACEHOLDERS: errors.append('campaign inventory digest unset')
  if campaign.get('recipe_set_digest') in PLACEHOLDERS: errors.append('campaign recipe digest unset')
 dr=data.get('dr/replay-plan.json',{})
 if isinstance(dr,dict):
  if dr.get('owner') in PLACEHOLDERS: errors.append('DR owner unset')
  if dr.get('rpo') in PLACEHOLDERS or dr.get('rto') in PLACEHOLDERS: errors.append('DR RPO/RTO unset')
 cert=data.get('certification/certification.json',{})
 if isinstance(cert,dict) and cert.get('owner') in PLACEHOLDERS: errors.append('certification owner unset')
 here=Path(__file__).resolve().parent
 for cmd in ([sys.executable,str(here/'validate_dependency_graph.py'),str(pack/'graph/dependencies.json')],[sys.executable,str(here/'validate_work_units.py'),str(pack/'work-units/plan.json'),'--inventory',str(pack/'inventory/portfolio.json')]):
  r=subprocess.run(cmd,capture_output=True,text=True)
  if r.returncode: errors.append(r.stderr.strip() or r.stdout.strip())
 if errors: print('\n'.join('ERROR: '+e for e in errors),file=sys.stderr); return 1
 print(f'OK: {key}'); return 0
if __name__=='__main__': raise SystemExit(main())
