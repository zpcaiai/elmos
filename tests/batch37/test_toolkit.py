from __future__ import annotations
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; SCRIPTS=ROOT/'scripts'/'batch37'
def load(p): return json.loads(Path(p).read_text())
def write(p,o): Path(p).write_text(json.dumps(o,indent=2)+'\n')
def attest(pack,rel):
 auth=pack/'certification/test-authorization.json'; write(auth,{'authorized':True,'scope':'isolated-test-only'})
 evidence=pack/rel/'evidence.txt'; evidence.write_text('isolated test evidence\n')
 write(pack/rel/'manifest.json',{'status':'passed','source_digest':'sha256:'+'a'*64,'dataset_digest':'sha256:'+'b'*64,'independent':True,'execution_kind':'approved-sandbox','authorization_refs':['certification/test-authorization.json'],'evidence_refs':[f'{rel}/evidence.txt']})
def complete_pack(pack):
 m=load(pack/'pack.json'); m['owner']='marketplace-team'; m['maintenance_owner']='sdk-platform-team'; m['scope']['environment_digest']='sha256:environment'; write(pack/'pack.json',m)
 pub=load(pack/'publishers/sample-publisher.json'); pub.update({'legal_name':'Sample Publisher Ltd','status':'active','verified':True,'organization_owner':'owner-1','security_contact':'security@example.invalid','agreements':[{'type':'publisher','version':'1','accepted_at':'2026-01-01'}],'signing_identities':[{'key_id':'key-1','status':'active','valid_from':'2026-01-01','valid_until':'2027-01-01'}]}); write(pack/'publishers/sample-publisher.json',pub)
 c=load(pack/'certification/certification.json'); c['owner']='quality-team'; c['exact_scope']=m['scope']; write(pack/'certification/certification.json',c)
 for d in ['corpus/negative','corpus/holdout','corpus/representative-extensions']: attest(pack,d)
 (pack/'certification/sample-evidence.txt').write_text('evidence\n')
class Tests(unittest.TestCase):
 def test_skill_bundle(self): subprocess.run([sys.executable,str(SCRIPTS/'validate_skill_bundle.py'),str(ROOT/'.agents/skills')],check=True)
 def test_schemas_templates(self):
  import jsonschema
  for p in sorted((ROOT/'schemas/batch37').glob('*.schema.json')): jsonschema.validators.validator_for(load(p)).check_schema(load(p))
  pairs=[('marketplace-pack.json','marketplace-pack.schema.json'),('extension-manifest.json','extension-manifest.schema.json'),('sdk-contract.json','sdk-contract.schema.json'),('sandbox-policy.json','sandbox-policy.schema.json'),('publisher-profile.json','publisher-profile.schema.json'),('compatibility-matrix.json','compatibility-matrix.schema.json'),('release-record.json','release-record.schema.json'),('commercial-policy.json','commercial-policy.schema.json'),('support-matrix.json','marketplace-support-matrix.schema.json'),('certification.json','marketplace-certification.schema.json')]
  for t,s in pairs: jsonschema.validate(load(ROOT/'templates/batch37'/t),load(ROOT/'schemas/batch37'/s))
 def test_scaffold_validate(self):
  with tempfile.TemporaryDirectory() as d:
   repo=Path(d); subprocess.run([sys.executable,str(SCRIPTS/'scaffold_marketplace_pack.py'),'--pack-key','sdk-marketplace','--product-version','1.0.0','--repo-root',str(repo)],check=True); pack=repo/'marketplace-packs/sdk-marketplace'; complete_pack(pack); subprocess.run([sys.executable,str(SCRIPTS/'validate_marketplace_pack.py'),str(pack)],check=True)
 def test_manifest_rejects_unknown_permission(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'m.json'; o=load(ROOT/'templates/batch37/extension-manifest.json'); o['permissions'].append('root-host'); write(p,o); self.assertEqual(subprocess.run([sys.executable,str(SCRIPTS/'validate_extension_manifest.py'),str(p)]).returncode,1)
 def test_sandbox_rejects_wildcard_network(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'s.json'; o=load(ROOT/'templates/batch37/sandbox-policy.json'); o['network']={'mode':'allowlist','allowlist':['*'],'deny_metadata_endpoints':True}; write(p,o); self.assertEqual(subprocess.run([sys.executable,str(SCRIPTS/'validate_sandbox_policy.py'),str(p)]).returncode,1)
 def test_candidate_scoring(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'out.json'; subprocess.run([sys.executable,str(SCRIPTS/'score_extension_candidates.py'),str(ROOT/'templates/batch37/extension-candidates.json'),'--output',str(out)],check=True); self.assertEqual(load(out)['results'][0]['decision'],'approve')
 def test_gate_rejects_fake_certification(self):
  with tempfile.TemporaryDirectory() as d:
   repo=Path(d); subprocess.run([sys.executable,str(SCRIPTS/'scaffold_marketplace_pack.py'),'--pack-key','sdk-marketplace','--product-version','1.0.0','--repo-root',str(repo)],check=True); pack=repo/'marketplace-packs/sdk-marketplace'; complete_pack(pack); m=load(pack/'pack.json'); m['status']='certified'; write(pack/'pack.json',m); c=load(pack/'certification/certification.json'); c['status']='certified'; write(pack/'certification/certification.json',c); r=load(pack/'releases/sample/release.json'); r['status']='published'; write(pack/'releases/sample/release.json',r); self.assertEqual(subprocess.run([sys.executable,str(SCRIPTS/'run_marketplace_gate.py'),str(pack)]).returncode,2)
 def test_research_gate_is_explicitly_not_certified(self):
  with tempfile.TemporaryDirectory() as d:
   repo=Path(d); subprocess.run([sys.executable,str(SCRIPTS/'scaffold_marketplace_pack.py'),'--pack-key','sdk-marketplace','--product-version','1.0.0','--repo-root',str(repo)],check=True); pack=repo/'marketplace-packs/sdk-marketplace'; complete_pack(pack)
   self.assertEqual(subprocess.run([sys.executable,str(SCRIPTS/'run_marketplace_gate.py'),str(pack)]).returncode,0)
   result=load(pack/'certification/gate-result.json'); self.assertFalse(result['certification_requested']); self.assertEqual(result['certification_decision'],'NOT_CERTIFIED')
if __name__=='__main__': unittest.main()
