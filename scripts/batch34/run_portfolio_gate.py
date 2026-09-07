#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
def load(p): return json.loads(p.read_text())
def has_real_file(path):
 if not path.exists(): return False
 return any(x.is_file() and x.name.lower() not in {'readme.md','.gitkeep'} and x.stat().st_size>0 for x in path.rglob('*'))
def has_passed_corpus_evidence(path):
 if not path.exists(): return False
 for item in path.rglob('*.json'):
  try: data=load(item)
  except Exception: continue
  if not isinstance(data,dict): continue
  if str(data.get('status','')).lower()!='passed': continue
  if not data.get('dataset_digest') or not data.get('evidence_refs'): continue
  return True
 return False
def main():
 p=argparse.ArgumentParser(); p.add_argument('pack_dir'); a=p.parse_args(); pack=Path(a.pack_dir); here=Path(__file__).resolve().parent
 if subprocess.run([sys.executable,str(here/'validate_portfolio_pack.py'),str(pack)]).returncode: return 1
 manifest=load(pack/'pack.json'); support=load(pack/'support-matrix.json'); inventory=load(pack/'inventory/portfolio.json'); graph=load(pack/'graph/dependencies.json'); work=load(pack/'work-units/plan.json'); scale=load(pack/'scale/scale-profile.json'); benchmark=load(pack/'benchmark/result.json'); dr=load(pack/'dr/replay-plan.json'); evidence=load(pack/'certification/evidence.json'); cert=load(pack/'certification/certification.json'); failures=[]
 if manifest.get('status')=='certified' or cert.get('status')=='certified':
  if manifest.get('status')!='certified' or cert.get('status')!='certified': failures.append('pack and certification statuses must both be certified')
  if not [c for c in support.get('capabilities',[]) if c.get('status')=='certified']: failures.append('no certified capabilities')
  metrics=evidence.get('metrics',{})
  thresholds={'inventory_coverage':.95,'critical_owner_coverage':1.0,'dependency_graph_coverage':.95,'cross_repo_edge_resolution_rate':.95,'work_unit_coverage':.95,'semantic_index_coverage':.95,'incremental_index_equivalence_rate':1.0,'workflow_idempotency_pass_rate':1.0,'checkpoint_recovery_pass_rate':1.0,'runner_fleet_scheduling_pass_rate':1.0,'cache_correctness_pass_rate':1.0,'artifact_transfer_resume_pass_rate':1.0,'recipe_campaign_pass_rate':1.0,'multi_repo_pr_pass_rate':1.0,'failure_isolation_pass_rate':1.0,'fairness_slo_pass_rate':1.0,'budget_guardrail_pass_rate':1.0,'control_tower_freshness_pass_rate':1.0,'million_loc_benchmark_pass_rate':1.0,'thousand_repo_benchmark_pass_rate':1.0,'mixed_language_benchmark_pass_rate':1.0,'forecast_interval_coverage':.80,'disaster_replay_pass_rate':1.0,'representative_portfolio_pass_rate':1.0,'source_map_coverage':.95}
  for k,t in thresholds.items():
   if metrics.get(k,0)<t: failures.append(f'{k} below {t}')
  zero=['critical_unknown_repositories','hidden_critical_dependencies','silent_repository_drops','cross_tenant_leaks','cache_poisoning_events','critical_stale_index_entries','orphaned_tasks','lost_checkpoints','unbounded_retries','noisy_neighbor_breaches','unapproved_budget_overruns','artifact_corruption_events','unrecoverable_campaigns','duplicate_external_effects','test_integrity_violations','unapproved_baseline_changes']
  for k in zero:
   if evidence.get(k,1)!=0: failures.append(f'{k} must be zero')
  if inventory.get('coverage',0)<.95: failures.append('inventory coverage below 0.95')
  if not inventory.get('repositories'): failures.append('portfolio inventory has no repositories')
  if not graph.get('nodes'): failures.append('dependency graph has no nodes')
  if not work.get('units'): failures.append('work-unit plan has no units')
  if benchmark.get('status')!='passed': failures.append('benchmark result not passed')
  if not all(c.get('dataset_manifest_ref') for c in scale.get('classes',[])): failures.append('scale classes missing dataset manifests')
  if not dr.get('test_cases'): failures.append('DR replay plan has no test cases')
  if not has_real_file(pack/'corpus/holdout'): failures.append('holdout corpus empty')
  elif not has_passed_corpus_evidence(pack/'corpus/holdout'): failures.append('holdout corpus has no passed evidence manifest')
  if not has_real_file(pack/'corpus/representative-portfolios'): failures.append('representative portfolio corpus empty')
  elif not has_passed_corpus_evidence(pack/'corpus/representative-portfolios'): failures.append('representative portfolio corpus has no passed evidence manifest')
  refs=evidence.get('evidence_refs',[])+cert.get('evidence_refs',[])+dr.get('evidence_refs',[])+benchmark.get('evidence_refs',[])
  if not refs: failures.append('certification evidence refs empty')
  for ref in refs:
   if ref.startswith(('http://','https://')): continue
   if not (pack/ref).is_file(): failures.append(f'missing evidence ref: {ref}')
 certified=manifest.get('status')=='certified' and cert.get('status')=='certified' and not failures
 decision='CERTIFIED' if certified else ('BLOCKED' if failures else 'NOT_CERTIFIED')
 result={'schema_version':1,'pack_key':manifest.get('pack_key'),'status':'failed' if failures else 'passed','pack_status':manifest.get('status'),'certification_decision':decision,'failures':failures}
 (pack/'certification/gate-result.json').write_text(json.dumps(result,indent=2)+'\n'); lines=[f"# Batch 34 gate: {manifest.get('pack_key')}",'',f"- Pack status: `{manifest.get('status')}`",f"- Structural gate: `{'failed' if failures else 'passed'}`",f"- Certification decision: `{decision}`",'']
 if failures: lines+=['## Failures']+[f'- {x}' for x in failures]
 elif certified: lines.append('The submitted certified scope met the structural and evidence requirements checked by this gate.')
 else: lines.append('The pack is structurally valid but is not certified. Real benchmark, holdout, representative-portfolio, cost, integrity, recovery, and authorization evidence remains required.')
 (pack/'certification/gate-report.md').write_text('\n'.join(lines)+'\n')
 if failures: print('\n'.join('GATE FAIL: '+x for x in failures),file=sys.stderr); return 2
 print(f"GATE PASS: {manifest.get('pack_key')} status={manifest.get('status')} certification={decision}"); return 0
if __name__=='__main__': raise SystemExit(main())
