#!/usr/bin/env python3
from __future__ import annotations
import subprocess,sys,json
from pathlib import Path
from _common import load,resolve_ref,validate_attested_corpus

def main():
 pack=Path(sys.argv[1]); failures=[]; here=Path(__file__)
 for script,args in [('validate_marketplace_pack.py',[str(pack)]),('validate_extension_manifest.py',[str(pack/'extensions/sample/manifest.json')]),('validate_sandbox_policy.py',[str(pack/'sandbox/policy.json')]),('validate_release_chain.py',[str(pack)])]:
  if subprocess.run([sys.executable,str(here.with_name(script)),*args]).returncode: failures.append(f'{script} failed')
 try:
  manifest=load(pack/'pack.json'); evidence=load(pack/'certification/evidence.json'); cert=load(pack/'certification/certification.json'); ext=load(pack/'extensions/sample/manifest.json'); sandbox=load(pack/'sandbox/policy.json'); publisher_ref=manifest.get('contracts',{}).get('publisher_profile'); publisher=load(pack/publisher_ref); release=load(pack/'releases/sample/release.json'); commercial=load(pack/'commercial/policy.json')
 except Exception as e: print(f'GATE FAIL: cannot load pack: {e}',file=sys.stderr); return 2
 requested=manifest.get('status')=='certified' or cert.get('status')=='certified' or release.get('status') in {'certified','published'}
 if manifest.get('status')!=cert.get('status'): failures.append('pack and certification status mismatch')
 metrics={}; metrics.update(evidence.get('metrics',{})); metrics.update(cert.get('metrics',{}))
 thresholds={'abi_conformance_rate':1.0,'sdk_conformance_rate':1.0,'sandbox_conformance_rate':1.0,'extension_build_pass_rate':1.0,'negative_security_pass_rate':1.0,'signature_verification_rate':1.0,'sbom_provenance_coverage':1.0,'publisher_verification_rate':1.0,'compatibility_matrix_pass_rate':1.0,'install_upgrade_rollback_pass_rate':1.0,'revocation_enforcement_rate':1.0,'entitlement_metering_reconciliation_rate':1.0,'holdout_pass_rate':1.0,'representative_extension_pass_rate':1.0,'evidence_trace_coverage':0.95}
 if requested:
  if evidence.get('external_evidence_status')!='PASSED': failures.append('external_evidence_status must be PASSED for certification')
  for k,t in thresholds.items():
   if float(metrics.get(k,0))<t: failures.append(f'{k} below {t}')
  z={}; z.update(evidence.get('zero_tolerance',{})); z.update(cert.get('zero_tolerance',{}))
  zero=['critical_unknowns','sandbox_escapes','cross_tenant_access','undeclared_permission_grants','unsigned_published_releases','tampered_artifacts_accepted','critical_vulnerabilities','prohibited_license_findings','unverified_active_publishers','revoked_release_executions','orphaned_credentials','billing_reconciliation_breaks','self_approved_critical_waivers','test_integrity_violations','missing_p0_evidence']
  for k in zero:
   if z.get(k,1)!=0: failures.append(f'{k} must be zero')
  for rel in ['corpus/negative','corpus/holdout','corpus/representative-extensions']:
   validate_attested_corpus(pack,rel,failures)
  if publisher.get('verified') is not True or publisher.get('status')!='active': failures.append('publisher must be verified and active')
  if not publisher.get('signing_identities') or not any(x.get('status')=='active' for x in publisher.get('signing_identities',[])): failures.append('active publisher signing identity required')
  if release.get('status') not in {'certified','published'}: failures.append('release must be certified or published')
  if release.get('immutable') is not True: failures.append('release must be immutable')
  if sandbox.get('default_action')!='deny': failures.append('sandbox must deny by default')
  if commercial.get('metering_authority')!='platform' or commercial.get('security_gate_independent') is not True: failures.append('commercial policy cannot control security gate')
  refs=evidence.get('evidence_refs',[])+cert.get('evidence_refs',[])
  if not refs: failures.append('certification evidence refs empty')
  for ref in refs:
   if not resolve_ref(pack,ref): failures.append(f'missing evidence ref: {ref}')
 status='failed' if failures else 'passed'
 decision='BLOCKED' if failures else ('CERTIFIED' if requested else 'NOT_CERTIFIED')
 result={'schema_version':1,'pack_key':manifest.get('pack_key'),'status':status,'structural_gate_status':status,'pack_status':manifest.get('status'),'certification_requested':requested,'certification_decision':decision,'failures':failures}
 (pack/'certification/gate-result.json').write_text(json.dumps(result,indent=2)+'\n')
 lines=[f'# Batch 37 gate: {manifest.get("pack_key")}', '', f'- Pack status: `{manifest.get("status")}`', f'- Structural gate status: `{status}`', f'- Certification requested: `{str(requested).lower()}`', f'- Certification decision: `{decision}`','']
 lines += (['## Failures']+[f'- {x}' for x in failures]) if failures else (['The exact certification scope and attested evidence passed.'] if requested else ['Structural checks passed; certification was not requested and remains `NOT_CERTIFIED`.'])
 (pack/'certification/gate-report.md').write_text('\n'.join(lines)+'\n')
 if failures: print('\n'.join('GATE FAIL: '+x for x in failures),file=sys.stderr); return 2
 print(f'GATE PASS: {manifest.get("pack_key")} status={manifest.get("status")} decision={decision}'); return 0
if __name__=='__main__': raise SystemExit(main())
