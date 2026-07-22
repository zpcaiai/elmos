from __future__ import annotations
import json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; SCRIPTS=ROOT/'scripts'/'batch34'
def load(p): return json.loads(p.read_text())
def complete_pack(pack):
 m=load(pack/'pack.json'); m['owner']='portfolio-team'; m['maintenance_owner']='platform-team'; m['scope']['inventory_snapshot_at']='2026-07-21T00:00:00Z'; (pack/'pack.json').write_text(json.dumps(m,indent=2)+'\n')
 inv=load(pack/'inventory/portfolio.json'); inv['snapshot_digest']='sha256:inventory'; inv['captured_at']='2026-07-21T00:00:00Z'; inv['coverage']=.5; inv['repositories']=[{'id':'repo.a','scm_provider':'github','organization':'acme','name':'a','default_branch':'main','baseline_commit':'a'*40,'owner':'team-a','status':'active','criticality':'P0','regions':['us-east'],'languages':['java'],'build_systems':['maven'],'loc':1000,'size_bytes':10000,'evidence_refs':['certification/sample-evidence.txt']}]; (pack/'inventory/portfolio.json').write_text(json.dumps(inv,indent=2)+'\n')
 g=load(pack/'graph/dependencies.json'); g['graph_version']='g1'; g['nodes']=[{'id':'repo.a','kind':'repository','logical_key':'acme/a','owner':'team-a','source_refs':[{'path':'inventory/portfolio.json'}]}]; g['edges']=[]; (pack/'graph/dependencies.json').write_text(json.dumps(g,indent=2)+'\n')
 w=load(pack/'work-units/plan.json'); w['graph_version']='g1'; w['units']=[{'id':'wu.a','owner':'team-a','tenant_scope':'tenant-a','regions':['us-east'],'repository_ids':['repo.a'],'module_refs':[],'partition_key':'repo.a','dependencies':[],'estimated_loc':1000,'resource_profile':'small-java','criticality':'P0','entry_gate':'inventory-ready','exit_gate':'verified','evidence_refs':['certification/sample-evidence.txt']}]; (pack/'work-units/plan.json').write_text(json.dumps(w,indent=2)+'\n')
 s=load(pack/'scale/scale-profile.json'); s['owner']='sre-team'; s['environment']['runner_image_digest']='sha256:runner'; (pack/'scale/scale-profile.json').write_text(json.dumps(s,indent=2)+'\n')
 c=load(pack/'campaigns/default.json'); c['owner']='migration-team'; c['inventory_snapshot_digest']='sha256:inventory'; c['recipe_set_digest']='sha256:recipes'; (pack/'campaigns/default.json').write_text(json.dumps(c,indent=2)+'\n')
 dr=load(pack/'dr/replay-plan.json'); dr['owner']='sre-team'; dr['rpo']='15m'; dr['rto']='2h'; dr['test_cases']=[{'key':'workflow-replay'}]; (pack/'dr/replay-plan.json').write_text(json.dumps(dr,indent=2)+'\n')
 cert=load(pack/'certification/certification.json'); cert['owner']='quality-team'; cert['exact_scope']=m['scope']; (pack/'certification/certification.json').write_text(json.dumps(cert,indent=2)+'\n')
 (pack/'certification/sample-evidence.txt').write_text('evidence\n')
class Tests(unittest.TestCase):
 def test_skill_bundle(self): subprocess.run([sys.executable,str(SCRIPTS/'validate_skill_bundle.py'),str(ROOT/'.agents/skills')],check=True)
 def test_schemas_templates(self):
  import jsonschema
  for p in sorted((ROOT/'schemas/batch34').glob('*.schema.json')): jsonschema.validators.validator_for(load(p)).check_schema(load(p))
  pairs=[('portfolio-pack.json','portfolio-pack.schema.json'),('support-matrix.json','portfolio-support-matrix.schema.json'),('portfolio-inventory.json','portfolio-inventory.schema.json'),('work-unit-plan.json','work-unit-plan.schema.json'),('dependency-graph.json','dependency-graph.schema.json'),('scale-profile.json','scale-profile.schema.json'),('campaign-plan.json','campaign-plan.schema.json'),('benchmark-result.json','benchmark-result.schema.json'),('dr-replay-plan.json','dr-replay-plan.schema.json'),('certification.json','portfolio-certification.schema.json')]
  for t,s in pairs: jsonschema.validate(load(ROOT/'templates/batch34'/t),load(ROOT/'schemas/batch34'/s))
 def test_scaffold_validate(self):
  with tempfile.TemporaryDirectory() as d:
   repo=Path(d); subprocess.run([sys.executable,str(SCRIPTS/'scaffold_portfolio_pack.py'),'--pack-key','acme-enterprise','--scm-provider','github','--organization','acme','--region','us-east','--repo-root',str(repo)],check=True); pack=repo/'portfolio-packs/acme-enterprise'; complete_pack(pack); subprocess.run([sys.executable,str(SCRIPTS/'validate_portfolio_pack.py'),str(pack)],check=True)
 def test_graph_rejects_unknown(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'g.json'; g=load(ROOT/'templates/batch34/dependency-graph.json'); g['graph_version']='g1'; g['nodes']=[{'id':'a','kind':'repository','logical_key':'a','owner':'x','source_refs':[]}]; g['edges']=[{'id':'e','from':'a','to':'missing','kind':'build','criticality':'P0','confidence':1.0,'evidence_refs':[]}]; p.write_text(json.dumps(g)); self.assertEqual(subprocess.run([sys.executable,str(SCRIPTS/'validate_dependency_graph.py'),str(p)]).returncode,1)
 def test_work_units_reject_unknown_repo(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d); inv=load(ROOT/'templates/batch34/portfolio-inventory.json'); inv['snapshot_digest']='x'; inv['captured_at']='now'; invp=d/'inv.json'; invp.write_text(json.dumps(inv)); w=load(ROOT/'templates/batch34/work-unit-plan.json'); w['graph_version']='g1'; w['units']=[{'id':'w','owner':'o','tenant_scope':'t','regions':['r'],'repository_ids':['missing'],'module_refs':[],'partition_key':'p','dependencies':[],'estimated_loc':1,'resource_profile':'s','criticality':'P0','entry_gate':'a','exit_gate':'b','evidence_refs':[]}]; wp=d/'w.json'; wp.write_text(json.dumps(w)); self.assertEqual(subprocess.run([sys.executable,str(SCRIPTS/'validate_work_units.py'),str(wp),'--inventory',str(invp)]).returncode,1)
 def test_work_units_reject_cycle(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'work.json'; w=load(ROOT/'templates/batch34/work-unit-plan.json'); w['graph_version']='g1'
   def unit(ident,dependency): return {'id':ident,'owner':'o','tenant_scope':'t','regions':['r'],'repository_ids':[],'module_refs':[ident],'partition_key':ident,'dependencies':[dependency],'estimated_loc':1,'resource_profile':'s','criticality':'P0','entry_gate':'a','exit_gate':'b','evidence_refs':[]}
   w['units']=[unit('a','b'),unit('b','a')]; path.write_text(json.dumps(w))
   run=subprocess.run([sys.executable,str(SCRIPTS/'validate_work_units.py'),str(path)],capture_output=True,text=True)
   self.assertEqual(run.returncode,1); self.assertIn('work-unit dependency cycle',run.stderr)
 def test_candidate_scoring(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'out.json'; subprocess.run([sys.executable,str(SCRIPTS/'score_portfolio_candidates.py'),str(ROOT/'templates/batch34/portfolio-candidates.json'),'--output',str(out)],check=True); self.assertEqual(load(out)['results'][0]['decision'],'approve')
 def test_gate_rejects_fake_certification(self):
  with tempfile.TemporaryDirectory() as d:
   repo=Path(d); subprocess.run([sys.executable,str(SCRIPTS/'scaffold_portfolio_pack.py'),'--pack-key','acme-enterprise','--scm-provider','github','--organization','acme','--region','us-east','--repo-root',str(repo)],check=True); pack=repo/'portfolio-packs/acme-enterprise'; complete_pack(pack); m=load(pack/'pack.json'); m['status']='certified'; (pack/'pack.json').write_text(json.dumps(m,indent=2)+'\n'); c=load(pack/'certification/certification.json'); c['status']='certified'; (pack/'certification/certification.json').write_text(json.dumps(c,indent=2)+'\n'); self.assertEqual(subprocess.run([sys.executable,str(SCRIPTS/'run_portfolio_gate.py'),str(pack)]).returncode,2)
 def test_noncertified_gate_is_explicit(self):
  with tempfile.TemporaryDirectory() as d:
   repo=Path(d); subprocess.run([sys.executable,str(SCRIPTS/'scaffold_portfolio_pack.py'),'--pack-key','acme-enterprise','--scm-provider','github','--organization','acme','--region','us-east','--repo-root',str(repo)],check=True); pack=repo/'portfolio-packs/acme-enterprise'; complete_pack(pack)
   self.assertEqual(subprocess.run([sys.executable,str(SCRIPTS/'run_portfolio_gate.py'),str(pack)]).returncode,0)
   result=load(pack/'certification/gate-result.json'); self.assertEqual(result['certification_decision'],'NOT_CERTIFIED'); self.assertEqual(result['status'],'passed')
 def test_not_run_corpus_is_not_certification_evidence(self):
  with tempfile.TemporaryDirectory() as d:
   repo=Path(d); subprocess.run([sys.executable,str(SCRIPTS/'scaffold_portfolio_pack.py'),'--pack-key','acme-enterprise','--scm-provider','github','--organization','acme','--region','us-east','--repo-root',str(repo)],check=True); pack=repo/'portfolio-packs/acme-enterprise'; complete_pack(pack)
   for rel in ('corpus/holdout/manifest.json','corpus/representative-portfolios/manifest.json'):
    path=pack/rel; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps({'status':'not-run','dataset_digest':'NOT_RUN','evidence_refs':[]}))
   m=load(pack/'pack.json'); m['status']='certified'; (pack/'pack.json').write_text(json.dumps(m,indent=2)+'\n')
   c=load(pack/'certification/certification.json'); c['status']='certified'; (pack/'certification/certification.json').write_text(json.dumps(c,indent=2)+'\n')
   run=subprocess.run([sys.executable,str(SCRIPTS/'run_portfolio_gate.py'),str(pack)],capture_output=True,text=True)
   self.assertEqual(run.returncode,2); self.assertIn('holdout corpus has no passed evidence manifest',run.stderr); self.assertIn('representative portfolio corpus has no passed evidence manifest',run.stderr)
if __name__=='__main__': unittest.main()
