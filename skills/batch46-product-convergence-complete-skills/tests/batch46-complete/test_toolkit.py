import json, tempfile, unittest, subprocess, sys, shutil, hashlib, importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'convergence-packs/reference-product'
S=ROOT/'scripts/batch46-complete'
def load(p): return json.loads(Path(p).read_text())
def save(p,o): Path(p).write_text(json.dumps(o,indent=2)+'\n')
def module(name):
 spec=importlib.util.spec_from_file_location(name,S/f'{name}.py'); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class Toolkit(unittest.TestCase):
 def test_skill_bundle(self): subprocess.run([sys.executable,str(S/'validate_skill_bundle.py'),str(ROOT)],check=True)
 def test_pack_schema(self): subprocess.run([sys.executable,str(S/'validate_convergence_pack.py'),str(P)],check=True)
 def test_dependency_cycle_rejected(self):
  d=load(P/'dependency-graph.json'); d['edges'].append({'consumer':'control-plane','provider':'reference-route','dependency_type':'runtime','required_status':'certified','optional':False,'evidence_freshness':'P90D'})
  with tempfile.NamedTemporaryFile('w',delete=False,suffix='.json') as f: json.dump(d,f); path=f.name
  with self.assertRaises(AssertionError): module('validate_dependency_graph').validate(path)
 def test_workflow_cycle_rejected(self):
  d=load(P/'workflow-definition.json'); d['steps'][0]['dependencies']=['transform']
  with tempfile.NamedTemporaryFile('w',delete=False,suffix='.json') as f: json.dump(d,f); path=f.name
  with self.assertRaises(AssertionError): module('validate_workflow_definition').validate(path)
 def test_policy_fail_open_rejected(self):
  d=load(P/'policy-bundle.json'); d['default_effect']='allow'
  with tempfile.NamedTemporaryFile('w',delete=False,suffix='.json') as f: json.dump(d,f); path=f.name
  with self.assertRaises(AssertionError): module('validate_policy_bundle').validate(path)
 def test_evidence_unknown_edge_rejected(self):
  d=load(P/'evidence-graph.json'); d['edges'].append({'from':'missing','to':'target-release','relation':'x'})
  with tempfile.NamedTemporaryFile('w',delete=False,suffix='.json') as f: json.dump(d,f); path=f.name
  with self.assertRaises(AssertionError): module('validate_evidence_graph').validate(path)
 def test_skill_trigger_conflict_rejected(self):
  d=load(P/'skill-registry.json'); d['skills'][1]['triggers']=d['skills'][0]['triggers']
  with tempfile.NamedTemporaryFile('w',delete=False,suffix='.json') as f: json.dump(d,f); path=f.name
  with self.assertRaises(AssertionError): module('validate_skill_registry').validate(path)
 def test_reference_route_incomplete_rejected(self):
  d=load(P/'reference-route.json'); d['stage_results']=d['stage_results'][:-1]
  with tempfile.NamedTemporaryFile('w',delete=False,suffix='.json') as f: json.dump(d,f); path=f.name
  with self.assertRaises(AssertionError): module('validate_reference_route').validate(path)
 def test_two_partners_required(self):
  with self.assertRaises(AssertionError): module('validate_design_partners').validate(P/'design-partners.json')
 def test_weak_delivery_model_rejected(self):
  with self.assertRaises(AssertionError): module('validate_delivery_model').validate(P/'delivery-model.json')
 def test_default_final_gate_rejected(self):
  r=subprocess.run([sys.executable,str(S/'run_convergence_gate.py'),str(P)],capture_output=True,text=True)
  self.assertNotEqual(0,r.returncode)
 def test_positive_final_gate(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'pack'; shutil.copytree(P,p)
   # pass route
   route=load(p/'reference-route.json')
   for x in route['stage_results']: x['status']='passed'; x['evidence']=['evidence/'+x['stage']+'.manifest.json']
   route['status']='certified'; save(p/'reference-route.json',route)
   # partners
   partners={'partners':[]}
   for org in ['customer-a','customer-b']:
    partners['partners'].append({'organization_id':org,'independent':True,'repository':{'digest':hashlib.sha256(org.encode()).hexdigest()},'production_validation':True,'rollback_drill':True,'handoff':True,'accepted':True,'evidence':[f'evidence/{org}-{i}.json' for i in range(5)]})
   save(p/'design-partners.json',partners)
   save(p/'delivery-model.json',{'unit_cost':100.0,'gross_margin':0.45,'cycle_time_days':60,'manual_hours':500,'expert_bottlenecks':[],'risk_reserve':0.1,'repeatable_projects':2})
   save(p/'sla-proof.json',{'observation_days':30,'slo_passed':True,'support_passed':True,'incident_drill_passed':True,'restore_passed':True,'upgrade_passed':True,'customer_value_realized':True,'evidence':[f'evidence/sla-{i}.json' for i in range(6)]})
   # raw manifests
   manifests=[]
   for i in range(16):
    raw=p/'evidence'/f'raw-{i}.log'; raw.write_text(f'evidence {i}')
    man=p/'evidence'/f'man-{i}.json'; save(man,{'artifact_sha256':hashlib.sha256(b'artifact').hexdigest(),'environment_sha256':hashlib.sha256(b'env').hexdigest(),'files':[{'path':str(raw.relative_to(p)),'sha256':hashlib.sha256(raw.read_bytes()).hexdigest()}]}); manifests.append(str(man.relative_to(p)))
   c=load(p/'certification.json'); c['owners']={k:k+'-owner' for k in c['owners']}; c['kernel']={k:True for k in c['kernel']}; c['reference_route']={'certified':True}; c['private_runner']={'certified':True}; c['design_partners']={'accepted_count':2}; c['handoff']={'passed':True}; c['verified_workloads']=['vmw-a','vmw-b']; c['delivery_model']={'passed':True}; c['sla_proof']={'passed':True}; c['evidence_manifests']=manifests; c['status']='passed'; save(p/'certification.json',c)
   r=subprocess.run([sys.executable,str(S/'run_convergence_gate.py'),str(p)],capture_output=True,text=True)
   self.assertEqual(0,r.returncode,r.stderr+r.stdout)
if __name__=='__main__': unittest.main()
