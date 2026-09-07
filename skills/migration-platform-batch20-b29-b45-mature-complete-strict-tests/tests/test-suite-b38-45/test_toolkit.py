import json,unittest,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[2]; S=R/'test-suites/batch38-45-strict'; P=R/'scripts/test-suite-b38-45'
class T(unittest.TestCase):
 def test_cases(self): self.assertEqual(400,len(json.load(open(S/'cases/catalog.json'))['cases']))
 def test_coverage(self): self.assertEqual(set(range(1325,1497)),{x['product_skill_id'] for x in json.load(open(S/'coverage-matrix.json'))['mappings']})
 def test_skills(self): subprocess.run([sys.executable,str(P/'validate_skill_bundle.py'),str(R)],check=True)
 def test_default_gate_fails(self): self.assertNotEqual(0,subprocess.run([sys.executable,str(P/'run_strict_gate.py'),str(S)]).returncode)
 def test_customer_rules(self): g=json.load(open(S/'release-gate.json')); self.assertEqual(2,g['required_design_partners']); self.assertEqual(1,g['required_independent_reviews'])
 def test_profile(self): p=json.load(open(S/'strict-profile.json')); self.assertEqual(1,p['thresholds']['p0_pass_rate'])
if __name__=='__main__': unittest.main()
