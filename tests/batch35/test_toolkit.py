from __future__ import annotations
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; SCRIPTS=ROOT/'scripts'/'batch35'
def load(p): return json.loads(Path(p).read_text())
def write(p,o): Path(p).write_text(json.dumps(o,indent=2)+'\n')
def complete_pack(pack):
 m=load(pack/'pack.json'); m['owner']='verification-team'; m['maintenance_owner']='quality-team'; m['scope'].update({'source_artifact_digest':'sha256:source','target_artifact_digest':'sha256:target','environment_digest':'sha256:env'}); write(pack/'pack.json',m)
 c=load(pack/'certification/certification.json'); c['owner']='quality-team'; c['exact_scope']=m['scope']; write(pack/'certification/certification.json',c)
 for d in ['corpus/negative','corpus/holdout','corpus/representative-workloads']:
  (pack/d/'sample.txt').write_text('evidence\n')
 (pack/'certification/sample-evidence.txt').write_text('evidence\n')
class Tests(unittest.TestCase):
 def test_skill_bundle(self): subprocess.run([sys.executable,str(SCRIPTS/'validate_skill_bundle.py'),str(ROOT/'.agents/skills')],check=True)
 def test_schemas_templates(self):
  import jsonschema
  for p in sorted((ROOT/'schemas/batch35').glob('*.schema.json')): jsonschema.validators.validator_for(load(p)).check_schema(load(p))
  pairs=[('verification-pack.json','verification-pack.schema.json'),('support-matrix.json','verification-support-matrix.schema.json'),('validation-profile.json','validation-profile.schema.json'),('oracle-registry.json','oracle-registry.schema.json'),('property-spec.json','property-spec.schema.json'),('metamorphic-relation.json','metamorphic-relation.schema.json'),('mutation-campaign.json','mutation-campaign.schema.json'),('fuzz-campaign.json','fuzz-campaign.schema.json'),('model-spec.json','model-spec.schema.json'),('solver-proof.json','solver-proof.schema.json'),('counterexample.json','counterexample.schema.json'),('assurance-case.json','assurance-case.schema.json'),('certification.json','verification-certification.schema.json')]
  for t,s in pairs: jsonschema.validate(load(ROOT/'templates/batch35'/t),load(ROOT/'schemas/batch35'/s))
 def test_scaffold_validate(self):
  with tempfile.TemporaryDirectory() as d:
   repo=Path(d); subprocess.run([sys.executable,str(SCRIPTS/'scaffold_verification_pack.py'),'--pack-key','payment-verification','--migration-route','java-to-csharp','--workload-key','payment','--repo-root',str(repo)],check=True); pack=repo/'verification-packs/payment-verification'; complete_pack(pack); subprocess.run([sys.executable,str(SCRIPTS/'validate_verification_pack.py'),str(pack)],check=True)
 def test_oracle_rejects_authoritative_llm(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'o.json'; o=load(ROOT/'templates/batch35/oracle-registry.json'); o['oracles'][0].update({'type':'llm-advisory','trust_level':'authoritative'}); write(p,o); self.assertEqual(subprocess.run([sys.executable,str(SCRIPTS/'validate_oracle_registry.py'),str(p)]).returncode,1)
 def test_model_rejects_unknown_state(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'m.json'; m=load(ROOT/'templates/batch35/model-spec.json'); m['commands'][0]['to']='missing'; write(p,m); self.assertEqual(subprocess.run([sys.executable,str(SCRIPTS/'validate_model_spec.py'),str(p)]).returncode,1)
 def test_candidate_scoring(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'out.json'; subprocess.run([sys.executable,str(SCRIPTS/'score_verification_candidates.py'),str(ROOT/'templates/batch35/verification-candidates.json'),'--output',str(out)],check=True); self.assertEqual(load(out)['results'][0]['decision'],'approve')
 def test_gate_rejects_fake_certification(self):
  with tempfile.TemporaryDirectory() as d:
   repo=Path(d); subprocess.run([sys.executable,str(SCRIPTS/'scaffold_verification_pack.py'),'--pack-key','payment-verification','--migration-route','java-to-csharp','--workload-key','payment','--repo-root',str(repo)],check=True); pack=repo/'verification-packs/payment-verification'; complete_pack(pack); m=load(pack/'pack.json'); m['status']='certified'; write(pack/'pack.json',m); c=load(pack/'certification/certification.json'); c['status']='certified'; write(pack/'certification/certification.json',c); self.assertEqual(subprocess.run([sys.executable,str(SCRIPTS/'run_verification_gate.py'),str(pack)]).returncode,2)
 def test_research_gate_is_explicitly_not_certified(self):
  with tempfile.TemporaryDirectory() as d:
   repo=Path(d); subprocess.run([sys.executable,str(SCRIPTS/'scaffold_verification_pack.py'),'--pack-key','research-verification','--migration-route','local-regression','--workload-key','sample','--repo-root',str(repo)],check=True); pack=repo/'verification-packs/research-verification'; complete_pack(pack); subprocess.run([sys.executable,str(SCRIPTS/'run_verification_gate.py'),str(pack)],check=True); result=load(pack/'certification/gate-result.json'); self.assertEqual(result['certification_decision'],'NOT_CERTIFIED'); self.assertFalse(result['certification_requested'])
 def test_not_run_corpus_cannot_certify(self):
  with tempfile.TemporaryDirectory() as d:
   repo=Path(d); subprocess.run([sys.executable,str(SCRIPTS/'scaffold_verification_pack.py'),'--pack-key','corpus-verification','--migration-route','java-to-csharp','--workload-key','payment','--repo-root',str(repo)],check=True); pack=repo/'verification-packs/corpus-verification'; complete_pack(pack); m=load(pack/'pack.json'); m['status']='certified'; write(pack/'pack.json',m); c=load(pack/'certification/certification.json'); c['status']='certified'; c['metrics']={k:1.0 for k in ['property_pass_rate','metamorphic_pass_rate','mutation_score','fuzz_campaign_pass_rate','model_transition_coverage','p0_contract_pass_rate','data_money_invariant_pass_rate','security_property_pass_rate','query_equivalence_pass_rate','numeric_verification_pass_rate','counterexample_replay_pass_rate','representative_workload_pass_rate','source_map_coverage','evidence_trace_coverage','assurance_claim_support_rate']}; write(pack/'certification/certification.json',c)
   for corpus_key in ['negative','holdout','representative-workloads']:
    write(pack/f'corpus/{corpus_key}/manifest.json',{'status':'not-run','source_digest':'sha256:source','dataset_digest':'sha256:data','evidence_refs':['certification/sample-evidence.txt']})
   completed=subprocess.run([sys.executable,str(SCRIPTS/'run_verification_gate.py'),str(pack)]); self.assertEqual(completed.returncode,2); self.assertTrue(any('status must be passed' in failure for failure in load(pack/'certification/gate-result.json')['failures']))
if __name__=='__main__': unittest.main()
