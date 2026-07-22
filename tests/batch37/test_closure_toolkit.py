from __future__ import annotations
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; S=ROOT/'scripts/batch37'
def load(p): return json.loads(Path(p).read_text())
def write(p,o): Path(p).parent.mkdir(parents=True,exist_ok=True); Path(p).write_text(json.dumps(o,indent=2)+'\n')
def run(name,*args): return subprocess.run([sys.executable,str(S/name),*map(str,args)])
def attest(pack,rel):
 write(pack/'certification/test-authorization.json',{'authorized':True,'scope':'isolated-test-only'})
 (pack/rel/'evidence.txt').write_text('isolated test evidence\n')
 write(pack/rel/'manifest.json',{'status':'passed','source_digest':'sha256:'+'a'*64,'dataset_digest':'sha256:'+'b'*64,'independent':True,'execution_kind':'approved-sandbox','authorization_refs':['certification/test-authorization.json'],'evidence_refs':[f'{rel}/evidence.txt']})
def make_pack(root):
 subprocess.run([sys.executable,str(S/'scaffold_marketplace_pack.py'),'--pack-key','closed-marketplace','--product-version','1.0.0','--repo-root',str(root)],check=True)
 return root/'marketplace-packs/closed-marketplace'
def complete_core(pack):
 m=load(pack/'pack.json'); m['owner']='marketplace-team'; m['maintenance_owner']='sdk-team'; m['scope']['environment_digest']='sha256:environment'; write(pack/'pack.json',m)
 pub_path=pack/m['contracts']['publisher_profile']; pub=load(pub_path); pub.update({'legal_name':'Publisher Ltd','status':'active','verified':True,'organization_owner':'owner-1','security_contact':'security@example.invalid','agreements':[{'type':'publisher','version':'1','accepted_at':'2026-01-01'}],'signing_identities':[{'key_id':'key-1','status':'active','valid_from':'2026-01-01','valid_until':'2027-01-01'}]}); write(pub_path,pub)
 for d in ['corpus/negative','corpus/holdout','corpus/representative-extensions']: attest(pack,d)
 for f in ['certification/core-evidence.txt']:(pack/f).write_text('evidence\n')
 c=load(pack/'certification/certification.json'); c['owner']='quality-team'; c['exact_scope']=m['scope']; write(pack/'certification/certification.json',c)
def complete_closure(pack):
 for d in ['corpus/closure-holdout','corpus/representative-lifecycle']: attest(pack,d)
 for rel in ['dependencies/evidence.txt','runtime/evidence.txt','catalog/evidence.txt','catalog/ranking-evidence.txt','publishers/lifecycle-evidence.txt','certification/recertification-evidence.txt','migrations/evidence.txt','continuity/evidence.txt','legal/evidence.txt','support/evidence.txt','private-marketplace/evidence.txt','offline-mirror/evidence.txt','operations/evidence.txt','commercial/settlement-evidence.txt','lifecycle/evidence.txt','certification/closure-evidence.txt']:
  (pack/rel).parent.mkdir(parents=True,exist_ok=True); (pack/rel).write_text('evidence\n')
def mark_external_passed(pack):
 evidence=load(pack/'certification/evidence.json'); evidence['external_evidence_status']='PASSED'; write(pack/'certification/evidence.json',evidence)
 for rel in ['dependencies/lock.json','runtime/health.json','catalog/catalog-entry.json','catalog/ranking-policy.json','publishers/lifecycle.json','certification/recertification-policy.json','migrations/extension-migration.json','continuity/revocation-plan.json','legal-support/policy.json','private-marketplace/policy.json','offline-mirror/policy.json','operations/operations-policy.json','commercial/settlement.json','lifecycle/eol-policy.json']:
  payload=load(pack/rel); payload['evidence_status']='PASSED'; write(pack/rel,payload)
class Tests(unittest.TestCase):
 def test_skill_count(self):
  self.assertEqual(len(list((ROOT/'.agents/skills').glob('b37-*/SKILL.md'))),36)
 def test_schemas_and_templates(self):
  import jsonschema
  for p in (ROOT/'schemas/batch37').glob('*.schema.json'): jsonschema.validators.validator_for(load(p)).check_schema(load(p))
  pairs=[('dependency-lock.json','dependency-lock.schema.json'),('runtime-health.json','runtime-health.schema.json'),('catalog-entry.json','catalog-entry.schema.json'),('ranking-policy.json','ranking-policy.schema.json'),('publisher-lifecycle.json','publisher-lifecycle.schema.json'),('recertification-policy.json','recertification-policy.schema.json'),('extension-migration.json','extension-migration.schema.json'),('continuity-plan.json','continuity-plan.schema.json'),('legal-support.json','legal-support.schema.json'),('private-marketplace.json','private-marketplace.schema.json'),('offline-mirror.json','offline-mirror.schema.json'),('marketplace-operations.json','marketplace-operations.schema.json'),('commercial-settlement.json','commercial-settlement.schema.json'),('eol-policy.json','eol-policy.schema.json'),('closure-certification.json','closure-certification.schema.json')]
  for t,s in pairs: jsonschema.validate(load(ROOT/'templates/batch37'/t),load(ROOT/'schemas/batch37'/s))
 def test_scaffold_and_validators(self):
  with tempfile.TemporaryDirectory() as d:
   pack=make_pack(Path(d)); complete_core(pack); complete_closure(pack)
   checks=[('validate_dependency_lock.py',pack/'dependencies/lock.json'),('validate_runtime_health.py',pack/'runtime/health.json'),('validate_catalog_governance.py',pack/'catalog'),('validate_publisher_lifecycle.py',pack/'publishers/lifecycle.json'),('validate_continuous_certification.py',pack/'certification/recertification-policy.json'),('validate_extension_migration.py',pack/'migrations/extension-migration.json'),('validate_continuity_plan.py',pack/'continuity/revocation-plan.json'),('validate_legal_support.py',pack/'legal-support/policy.json'),('validate_private_marketplace.py',pack/'private-marketplace/policy.json'),('validate_offline_mirror.py',pack/'offline-mirror/policy.json'),('validate_marketplace_operations.py',pack/'operations/operations-policy.json'),('validate_commercial_settlement.py',pack/'commercial/settlement.json'),('validate_eol_policy.py',pack/'lifecycle/eol-policy.json')]
   for n,p in checks: self.assertEqual(run(n,p).returncode,0,n)
 def test_dependency_cycle_and_floating_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'lock.json'; o=load(ROOT/'templates/batch37/dependency-lock.json'); o['nodes'][0]['version']='*'; o['cycles']=[['a','b']]; write(p,o); self.assertEqual(run('validate_dependency_lock.py',p).returncode,1)
 def test_runtime_drift_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'health.json'; o=load(ROOT/'templates/batch37/runtime-health.json'); o['reconciliation']['drift_count']=1; write(p,o); self.assertEqual(run('validate_runtime_health.py',p).returncode,1)
 def test_stale_certification_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'recert.json'; o=load(ROOT/'templates/batch37/recertification-policy.json'); o['overdue']=True; write(p,o); self.assertEqual(run('validate_continuous_certification.py',p).returncode,1)
 def test_migration_without_rollback_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'migration.json'; o=load(ROOT/'templates/batch37/extension-migration.json'); o['rollback_tested']=False; write(p,o); self.assertEqual(run('validate_extension_migration.py',p).returncode,1)
 def test_private_cross_tenant_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'private.json'; o=load(ROOT/'templates/batch37/private-marketplace.json'); o['cross_tenant_sharing']=True; write(p,o); self.assertEqual(run('validate_private_marketplace.py',p).returncode,1)
 def test_stale_mirror_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'mirror.json'; o=load(ROOT/'templates/batch37/offline-mirror.json'); o['current_staleness_hours']=100; write(p,o); self.assertEqual(run('validate_offline_mirror.py',p).returncode,1)
 def test_settlement_difference_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'settlement.json'; o=load(ROOT/'templates/batch37/commercial-settlement.json'); o['reconciliation_difference']=0.01; write(p,o); self.assertEqual(run('validate_commercial_settlement.py',p).returncode,1)
 def test_fake_closure_certification_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   pack=make_pack(Path(d)); complete_core(pack); complete_closure(pack)
   m=load(pack/'pack.json'); m['status']='certified'; write(pack/'pack.json',m)
   c=load(pack/'certification/certification.json'); c['status']='certified'; c['metrics']={k:1.0 for k in ['abi_conformance_rate','sdk_conformance_rate','sandbox_conformance_rate','extension_build_pass_rate','negative_security_pass_rate','signature_verification_rate','sbom_provenance_coverage','publisher_verification_rate','compatibility_matrix_pass_rate','install_upgrade_rollback_pass_rate','revocation_enforcement_rate','entitlement_metering_reconciliation_rate','holdout_pass_rate','representative_extension_pass_rate','evidence_trace_coverage']}; c['zero_tolerance']={k:0 for k in ['critical_unknowns','sandbox_escapes','cross_tenant_access','undeclared_permission_grants','unsigned_published_releases','tampered_artifacts_accepted','critical_vulnerabilities','prohibited_license_findings','unverified_active_publishers','revoked_release_executions','orphaned_credentials','billing_reconciliation_breaks','self_approved_critical_waivers','test_integrity_violations','missing_p0_evidence']}; c['evidence_refs']=['certification/core-evidence.txt']; write(pack/'certification/certification.json',c)
   r=load(pack/'releases/sample/release.json'); r['status']='published'; r['immutable']=True; write(pack/'releases/sample/release.json',r)
   cc=load(pack/'certification/closure-certification.json'); cc['status']='certified'; write(pack/'certification/closure-certification.json',cc)
   self.assertEqual(run('run_marketplace_closure_gate.py',pack).returncode,2)
 def test_complete_closure_gate_passes(self):
  with tempfile.TemporaryDirectory() as d:
   pack=make_pack(Path(d)); complete_core(pack); complete_closure(pack); mark_external_passed(pack)
   m=load(pack/'pack.json'); m['status']='certified'; write(pack/'pack.json',m)
   c=load(pack/'certification/certification.json'); c['status']='certified'; c['metrics']={k:1.0 for k in ['abi_conformance_rate','sdk_conformance_rate','sandbox_conformance_rate','extension_build_pass_rate','negative_security_pass_rate','signature_verification_rate','sbom_provenance_coverage','publisher_verification_rate','compatibility_matrix_pass_rate','install_upgrade_rollback_pass_rate','revocation_enforcement_rate','entitlement_metering_reconciliation_rate','holdout_pass_rate','representative_extension_pass_rate','evidence_trace_coverage']}; c['zero_tolerance']={k:0 for k in ['critical_unknowns','sandbox_escapes','cross_tenant_access','undeclared_permission_grants','unsigned_published_releases','tampered_artifacts_accepted','critical_vulnerabilities','prohibited_license_findings','unverified_active_publishers','revoked_release_executions','orphaned_credentials','billing_reconciliation_breaks','self_approved_critical_waivers','test_integrity_violations','missing_p0_evidence']}; c['evidence_refs']=['certification/core-evidence.txt']; write(pack/'certification/certification.json',c)
   r=load(pack/'releases/sample/release.json'); r['status']='published'; r['immutable']=True; write(pack/'releases/sample/release.json',r)
   cc=load(pack/'certification/closure-certification.json'); cc['status']='certified'; cc['metrics']={k:1.0 for k in ['dependency_resolution_pass_rate','runtime_reconciliation_pass_rate','catalog_governance_pass_rate','publisher_lifecycle_pass_rate','continuous_certification_pass_rate','migration_rollback_pass_rate','continuity_pass_rate','legal_support_pass_rate','private_marketplace_pass_rate','offline_mirror_pass_rate','operations_dr_pass_rate','settlement_reconciliation_pass_rate','eol_portability_pass_rate','closure_holdout_pass_rate','representative_lifecycle_pass_rate','evidence_trace_coverage']}; cc['zero_tolerance']={k:0 for k in ['dependency_cycles','revoked_dependency_activations','runtime_drift','open_critical_incidents','overdue_p0_certifications','failed_state_migrations','continuity_gaps','open_blocking_legal_cases','open_p0_sla_breaches','cross_tenant_private_marketplace_access','stale_revocation_mirrors','dr_reconciliation_breaks','settlement_differences','fraud_findings_open','residual_eol_dependencies','customers_stranded_at_eol','missing_closure_evidence']}; cc['evidence_refs']=['certification/closure-evidence.txt']; write(pack/'certification/closure-certification.json',cc)
   self.assertEqual(run('run_marketplace_closure_gate.py',pack).returncode,0)
   result=load(pack/'certification/closure-gate-result.json'); self.assertTrue(result['closure_complete']); self.assertEqual(result['closure_decision'],'CERTIFIED')
 def test_research_closure_is_not_complete(self):
  with tempfile.TemporaryDirectory() as d:
   pack=make_pack(Path(d)); complete_core(pack); complete_closure(pack)
   self.assertEqual(run('run_marketplace_closure_gate.py',pack).returncode,0)
   result=load(pack/'certification/closure-gate-result.json'); self.assertFalse(result['certification_requested']); self.assertFalse(result['closure_complete']); self.assertEqual(result['closure_decision'],'NOT_CERTIFIED')
if __name__=='__main__': unittest.main()
