import csv,json,unittest,tempfile,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
class V3(unittest.TestCase):
 def test_manifest_count(self):
  m=json.loads((R/'manifest.json').read_text()); self.assertEqual(300,len(m['skills'])); self.assertEqual('3.0.0',m['package']['version'])
 def test_new_skill_range(self):
  m=json.loads((R/'manifest.json').read_text()); ids={int(x['id'].split('-')[-1]) for x in m['skills']}; self.assertEqual(set(range(1,301)),ids)
 def test_cert_routes(self): self.assertEqual(40,len(json.loads((R/'route-certification-registry.json').read_text())['spec']['routes']))
 def test_route_matrix_unchanged(self):
  with (R/'route-matrix.csv').open() as f:self.assertEqual(784,len(list(csv.DictReader(f))))
 def test_all_readiness_not_run(self): self.assertTrue(all(x['readiness']=='not-run' for x in json.loads((R/'manifest.json').read_text())['skills']))
 def test_schema_files(self): self.assertEqual(10,len([x for x in ['semantic-obligation.schema.json','fixture-manifest.schema.json','runtime-lab-profile.schema.json','behavior-oracle.schema.json','differential-result.schema.json','proof-obligation.schema.json','counterexample.schema.json','certification-run.schema.json','conformance-mapping.schema.json','coverage-metric.schema.json'] if (R/'schemas'/x).exists()]))
 def test_compare_observables(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d); (d/'a.json').write_text('{"x":1.0}'); (d/'b.json').write_text('{"x":1.001}'); (d/'c.json').write_text('{"numericTolerance":0.01}')
   q=subprocess.run([sys.executable,str(R/'scripts/compare_observables.py'),str(d/'a.json'),str(d/'b.json'),str(d/'c.json')]); self.assertEqual(0,q.returncode)
 def test_plan_generator(self):
  with tempfile.TemporaryDirectory() as d:
   o=Path(d)/'p.json'; route=json.loads((R/'route-certification-registry.json').read_text())['spec']['routes'][0]['route']
   q=subprocess.run([sys.executable,str(R/'scripts/generate_route_certification_plan.py'),'--registry',str(R/'route-certification-registry.json'),'--route',route,'--out',str(o)]); self.assertEqual(0,q.returncode); self.assertEqual('not-run',json.loads(o.read_text())['status'])
if __name__=='__main__': unittest.main()
