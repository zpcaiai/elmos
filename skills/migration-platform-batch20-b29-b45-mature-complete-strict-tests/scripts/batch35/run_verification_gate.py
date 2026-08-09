#!/usr/bin/env python3
from __future__ import annotations
import subprocess,sys,json
from pathlib import Path
from _common import load,real_files,resolve_ref

def main():
 pack=Path(sys.argv[1]); failures=[]
 if subprocess.run([sys.executable,str(Path(__file__).with_name('validate_verification_pack.py')),str(pack)]).returncode: failures.append('verification pack validation failed')
 try:
  manifest=load(pack/'pack.json'); profile=load(pack/'validation-profile.json'); oracles=load(pack/'oracle-registry.json'); proof=load(pack/'solver/proof.json'); assurance=load(pack/'assurance/assurance-case.json'); evidence=load(pack/'certification/evidence.json'); cert=load(pack/'certification/certification.json')
 except Exception as e:
  print(f'GATE FAIL: cannot load pack: {e}',file=sys.stderr); return 2
 requested_certified=manifest.get('status')=='certified' or cert.get('status')=='certified'
 if manifest.get('status')!=cert.get('status'): failures.append('pack and certification status mismatch')
 metrics={}; metrics.update(evidence.get('metrics',{})); metrics.update(cert.get('metrics',{}))
 thresholds={'property_pass_rate':1.0,'metamorphic_pass_rate':1.0,'mutation_score':0.80,'fuzz_campaign_pass_rate':1.0,'model_transition_coverage':0.95,'p0_contract_pass_rate':1.0,'data_money_invariant_pass_rate':1.0,'security_property_pass_rate':1.0,'query_equivalence_pass_rate':1.0,'numeric_verification_pass_rate':1.0,'counterexample_replay_pass_rate':1.0,'representative_workload_pass_rate':1.0,'source_map_coverage':0.95,'evidence_trace_coverage':0.95,'assurance_claim_support_rate':1.0}
 if requested_certified:
  for k,t in thresholds.items():
   if float(metrics.get(k,0))<t: failures.append(f'{k} below {t}')
  zero=['critical_unknown_obligations','unresolved_oracle_conflicts','surviving_critical_mutants','critical_fuzz_crashes','unreplayed_counterexamples','security_property_violations','money_invariant_violations','forbidden_concurrency_outcomes','race_deadlock_liveness_violations','query_equivalence_failures','numeric_precision_regressions','invalid_or_unknown_required_proofs','unsupported_p0_claims','test_integrity_violations','unapproved_oracle_changes','unapproved_tolerance_changes']
  z={}; z.update(evidence.get('zero_tolerance',{})); z.update(cert.get('zero_tolerance',{}))
  for k in zero:
   if z.get(k,1)!=0: failures.append(f'{k} must be zero')
  if proof.get('status') in {'unknown','timeout','unsupported','invalid'} and proof.get('property_id') in {x.get('claim_id') for x in profile.get('claims',[]) if x.get('criticality')=='P0'}: failures.append('required P0 proof is not resolved')
  if not real_files(pack/'corpus/holdout'): failures.append('holdout corpus empty')
  if not real_files(pack/'corpus/representative-workloads'): failures.append('representative workload corpus empty')
  if not real_files(pack/'corpus/negative'): failures.append('negative corpus empty')
  for claim in assurance.get('claims',[]):
   if claim.get('status')!='supported': failures.append(f'assurance claim {claim.get("claim_id")} is not fully supported')
  if not assurance.get('approvals'): failures.append('assurance case approvals empty')
  if oracles.get('conflicts'): failures.append('oracle conflicts remain')
  refs=evidence.get('evidence_refs',[])+cert.get('evidence_refs',[])+assurance.get('evidence',[])+proof.get('evidence_refs',[])
  if not refs: failures.append('certification evidence refs empty')
  for ref in refs:
   if not resolve_ref(pack,ref): failures.append(f'missing evidence ref: {ref}')
 status='failed' if failures else 'passed'; result={'schema_version':1,'pack_key':manifest.get('pack_key'),'status':status,'pack_status':manifest.get('status'),'failures':failures}
 (pack/'certification/gate-result.json').write_text(json.dumps(result,indent=2)+'\n')
 lines=[f'# Batch 35 gate: {manifest.get("pack_key")}', '', f'- Pack status: `{manifest.get("status")}`', f'- Gate status: `{status}`','']
 lines += (['## Failures']+[f'- {x}' for x in failures]) if failures else ['No structural or certification-gate failures were detected.']
 (pack/'certification/gate-report.md').write_text('\n'.join(lines)+'\n')
 if failures: print('\n'.join('GATE FAIL: '+x for x in failures),file=sys.stderr); return 2
 print(f'GATE PASS: {manifest.get("pack_key")} status={manifest.get("status")}'); return 0
if __name__=='__main__': raise SystemExit(main())
