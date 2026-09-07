
import json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
S=ROOT/'scripts/product-convergence'
P=ROOT/'product-convergence'
class T(unittest.TestCase):
 def test_skill_bundle(self): subprocess.run([sys.executable,str(S/'validate_skill_bundle.py'),str(ROOT)],check=True)
 def test_bundle(self): subprocess.run([sys.executable,str(S/'validate_convergence_bundle.py'),str(P)],check=True)
 def test_default_gate_fails(self): self.assertNotEqual(0,subprocess.run([sys.executable,str(S/'run_convergence_gate.py'),str(P)]).returncode)
 def test_dependency_cycle_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'g.json'; p.write_text(json.dumps({'nodes':[{'id':'a','kind':'x'},{'id':'b','kind':'x'}],'edges':[{'consumer':'a','provider':'b','dependency_type':'runtime','required_status':'certified'},{'consumer':'b','provider':'a','dependency_type':'runtime','required_status':'certified'}]}))
   self.assertNotEqual(0,subprocess.run([sys.executable,str(S/'validate_dependency_graph.py'),str(p)]).returncode)
 def test_certified_capability_requires_evidence(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'c.json'; p.write_text(json.dumps({'capabilities':[{'capability_id':'x','type':'route','version':'1.0.0','status':'certified','owner':'o','evidence':[]}]}))
   self.assertNotEqual(0,subprocess.run([sys.executable,str(S/'validate_capability_registry.py'),str(p)]).returncode)
 def test_reference_route(self): subprocess.run([sys.executable,str(S/'validate_reference_route.py'),str(P/'reference-route-plan.json')],check=True)
 def test_skill_registry_count(self): self.assertEqual(32,len(json.loads((P/'skill-registry.json').read_text())['skills']))
 def test_customer_gate_requirements(self):
  d=json.loads((P/'readiness-gate.json').read_text()); self.assertEqual([],d['design_partner_evidence']); self.assertEqual('not-run',d['status'])
if __name__=='__main__': unittest.main()
