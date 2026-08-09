from __future__ import annotations
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; SCRIPTS=ROOT/'scripts'/'batch36'
def load(p): return json.loads(Path(p).read_text())
def write(p,o): Path(p).write_text(json.dumps(o,indent=2)+'\n')
def complete_pack(pack):
 m=load(pack/'pack.json'); m['owner']='developer-experience-team'; m['maintenance_owner']='platform-team'; m['scope'].update({'source_artifact_digest':'sha256:source','target_artifact_digest':'sha256:target','environment_digest':'sha256:env'}); write(pack/'pack.json',m)
 c=load(pack/'certification/certification.json'); c['owner']='quality-team'; c['exact_scope']=m['scope']; write(pack/'certification/certification.json',c)
 for d in ['corpus/negative','corpus/holdout','corpus/representative-workflows']:
  (pack/d/'sample.txt').write_text('evidence\n')
 (pack/'certification/sample-evidence.txt').write_text('evidence\n')
class Tests(unittest.TestCase):
 def test_skill_bundle(self): subprocess.run([sys.executable,str(SCRIPTS/'validate_skill_bundle.py'),str(ROOT/'.agents/skills')],check=True)
 def test_schemas_templates(self):
  import jsonschema
  for p in sorted((ROOT/'schemas/batch36').glob('*.schema.json')): jsonschema.validators.validator_for(load(p)).check_schema(load(p))
  pairs=[('developer-experience-pack.json','developer-experience-pack.schema.json'),('support-matrix.json','developer-support-matrix.schema.json'),('ide-protocol.json','ide-protocol.schema.json'),('intellij-extension.json','extension-manifest.schema.json'),('visual-studio-extension.json','extension-manifest.schema.json'),('vscode-extension.json','extension-manifest.schema.json'),('cli-contract.json','cli-contract.schema.json'),('pr-bot-policy.json','pr-bot-policy.schema.json'),('navigation-map.json','navigation-map.schema.json'),('ownership-policy.json','ownership-policy.schema.json'),('local-eval-profile.json','local-eval-profile.schema.json'),('recipe-authoring-profile.json','recipe-authoring-profile.schema.json'),('telemetry-policy.json','telemetry-policy.schema.json'),('certification.json','developer-experience-certification.schema.json')]
  for t,s in pairs: jsonschema.validate(load(ROOT/'templates/batch36'/t),load(ROOT/'schemas/batch36'/s))
 def test_scaffold_validate(self):
  with tempfile.TemporaryDirectory() as d:
   repo=Path(d); subprocess.run([sys.executable,str(SCRIPTS/'scaffold_developer_experience_pack.py'),'--pack-key','java-csharp-dev','--migration-route','java-to-csharp','--repository-provider','github','--repository-id','acme/repo','--repo-root',str(repo)],check=True); pack=repo/'developer-experience-packs/java-csharp-dev'; complete_pack(pack); subprocess.run([sys.executable,str(SCRIPTS/'validate_developer_experience_pack.py'),str(pack)],check=True)
 def test_protocol_rejects_arbitrary_shell(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'p.json'; o=load(ROOT/'templates/batch36/ide-protocol.json'); o['security']['arbitrary_shell']=True; write(p,o); self.assertEqual(subprocess.run([sys.executable,str(SCRIPTS/'validate_ide_protocol.py'),str(p)]).returncode,1)
 def test_navigation_rejects_escape(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'n.json'; o=load(ROOT/'templates/batch36/navigation-map.json'); o['nodes'][0]['path']='../../secret'; write(p,o); self.assertEqual(subprocess.run([sys.executable,str(SCRIPTS/'validate_navigation_map.py'),str(p)]).returncode,1)
 def test_candidate_scoring(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'out.json'; subprocess.run([sys.executable,str(SCRIPTS/'score_developer_experience_candidates.py'),str(ROOT/'templates/batch36/developer-experience-candidates.json'),'--output',str(out)],check=True); self.assertEqual(load(out)['results'][0]['decision'],'approve')
 def test_gate_rejects_fake_certification(self):
  with tempfile.TemporaryDirectory() as d:
   repo=Path(d); subprocess.run([sys.executable,str(SCRIPTS/'scaffold_developer_experience_pack.py'),'--pack-key','java-csharp-dev','--migration-route','java-to-csharp','--repository-provider','github','--repository-id','acme/repo','--repo-root',str(repo)],check=True); pack=repo/'developer-experience-packs/java-csharp-dev'; complete_pack(pack); m=load(pack/'pack.json'); m['status']='certified'; write(pack/'pack.json',m); c=load(pack/'certification/certification.json'); c['status']='certified'; write(pack/'certification/certification.json',c); self.assertEqual(subprocess.run([sys.executable,str(SCRIPTS/'run_developer_experience_gate.py'),str(pack)]).returncode,2)
if __name__=='__main__': unittest.main()
