#!/usr/bin/env python3
from __future__ import annotations
import json,re,subprocess,sys
from pathlib import Path
from _common import load,resolve_ref

SHA256 = re.compile(r'^sha256:[0-9a-f]{64}$')

def validate_corpus_manifest(pack: Path, relative: str, failures: list[str]) -> None:
 manifest_path=pack/relative/'manifest.json'
 if not manifest_path.is_file():
  failures.append(f'{relative} corpus manifest missing')
  return
 try: manifest=load(manifest_path)
 except Exception as exc:
  failures.append(f'{relative} corpus manifest invalid: {exc}')
  return
 if manifest.get('status')!='passed': failures.append(f'{relative} corpus status must be passed')
 for key in ('source_digest','dataset_digest'):
  if not SHA256.fullmatch(str(manifest.get(key,''))): failures.append(f'{relative} corpus {key} must be an exact sha256 digest')
 refs=manifest.get('evidence_refs',[])
 if not isinstance(refs,list) or not refs: failures.append(f'{relative} corpus evidence_refs empty')
 else:
  for ref in refs:
   if not isinstance(ref,str) or not resolve_ref(pack,ref): failures.append(f'{relative} corpus evidence ref missing: {ref}')

def main():
 pack=Path(sys.argv[1]); failures=[]; here=Path(__file__)
 if subprocess.run([sys.executable,str(here.with_name('validate_developer_experience_pack.py')),str(pack)]).returncode: failures.append('developer experience pack validation failed')
 if subprocess.run([sys.executable,str(here.with_name('validate_ide_protocol.py')),str(pack/'protocol/ide-protocol.json')]).returncode: failures.append('IDE protocol validation failed')
 if subprocess.run([sys.executable,str(here.with_name('validate_navigation_map.py')),str(pack/'navigation/map.json')]).returncode: failures.append('navigation map validation failed')
 try:
  manifest=load(pack/'pack.json'); evidence=load(pack/'certification/evidence.json'); cert=load(pack/'certification/certification.json'); ownership=load(pack/'ownership/policy.json'); telemetry=load(pack/'telemetry/policy.json')
 except Exception as e:
  print(f'GATE FAIL: cannot load pack: {e}',file=sys.stderr); return 2
 requested=manifest.get('status')=='certified' or cert.get('status')=='certified'
 if manifest.get('status')!=cert.get('status'): failures.append('pack and certification status mismatch')
 metrics={}; metrics.update(evidence.get('metrics',{})); metrics.update(cert.get('metrics',{}))
 thresholds={'ide_protocol_conformance':1.0,'extension_build_pass_rate':1.0,'cli_contract_pass_rate':1.0,'pr_bot_dry_run_pass_rate':1.0,'local_preview_pass_rate':1.0,'navigation_accuracy':0.95,'explanation_provenance_coverage':0.95,'quick_fix_postcondition_pass_rate':1.0,'conflict_resolution_pass_rate':1.0,'ownership_protection_pass_rate':1.0,'affected_test_recall':0.95,'recipe_authoring_validation_pass_rate':1.0,'review_sync_pass_rate':1.0,'offline_workflow_pass_rate':1.0,'telemetry_privacy_pass_rate':1.0,'representative_workflow_pass_rate':1.0,'developer_task_success_rate':0.95,'evidence_trace_coverage':0.95}
 if requested:
  for k,t in thresholds.items():
   if float(metrics.get(k,0))<t: failures.append(f'{k} below {t}')
  z={}; z.update(evidence.get('zero_tolerance',{})); z.update(cert.get('zero_tolerance',{}))
  zero=['cross_tenant_access','unauthorized_repository_writes','secret_leaks','critical_source_mapping_errors','protected_region_overwrites','test_integrity_violations','telemetry_policy_violations','unapproved_dependency_changes','unreplayed_local_failures','unknown_p0_workflows','self_approvals','comment_spam_incidents','hidden_network_dependencies','stale_critical_approvals']
  for k in zero:
   if z.get(k,1)!=0: failures.append(f'{k} must be zero')
  for relative in ('corpus/negative','corpus/holdout','corpus/representative-workflows'):
   validate_corpus_manifest(pack,relative,failures)
  for rel in ['extensions/intellij.json','extensions/visual-studio.json','extensions/vscode.json']:
   ext=load(pack/rel)
   cap=next((x for x in load(pack/'support-matrix.json').get('capabilities',[]) if x.get('capability')==ext.get('host')),None)
   if cap and cap.get('status') in {'certified','supported'}:
    if not ext.get('distribution',{}).get('signed'): failures.append(f'{rel} is supported but not signed')
    for ref in [ext.get('distribution',{}).get('package_ref'),ext.get('distribution',{}).get('signature_ref')]:
     if not ref or not resolve_ref(pack,ref): failures.append(f'missing extension evidence ref: {ref}')
  if telemetry.get('individual_performance_monitoring') is not False: failures.append('individual performance monitoring must be false')
  if not ownership.get('entries'): failures.append('ownership policy entries empty')
  refs=evidence.get('evidence_refs',[])+cert.get('evidence_refs',[])
  if not refs: failures.append('certification evidence refs empty')
  for ref in refs:
   if not resolve_ref(pack,ref): failures.append(f'missing evidence ref: {ref}')
 status='failed' if failures else 'passed'
 decision='BLOCKED' if failures or manifest.get('status')=='blocked' else ('CERTIFIED' if requested else 'NOT_CERTIFIED')
 result={'schema_version':1,'pack_key':manifest.get('pack_key'),'status':status,'structural_gate_status':status,'pack_status':manifest.get('status'),'certification_requested':requested,'certification_decision':decision,'failures':failures}
 (pack/'certification/gate-result.json').write_text(json.dumps(result,indent=2)+'\n')
 lines=[f'# Batch 36 gate: {manifest.get("pack_key")}', '', f'- Pack status: `{manifest.get("status")}`', f'- Structural gate status: `{status}`', f'- Certification requested: `{str(requested).lower()}`', f'- Certification decision: `{decision}`','']
 lines += (['## Failures']+[f'- {x}' for x in failures]) if failures else (['All certification requirements were satisfied.'] if decision=='CERTIFIED' else ['The pack is structurally valid but is not certified. External, holdout, and representative evidence remains governed by the pack evidence status.'])
 (pack/'certification/gate-report.md').write_text('\n'.join(lines)+'\n')
 if failures: print('\n'.join('GATE FAIL: '+x for x in failures),file=sys.stderr); return 2
 print(f'GATE PASS: {manifest.get("pack_key")} status={manifest.get("status")} decision={decision}'); return 0
if __name__=='__main__': raise SystemExit(main())
