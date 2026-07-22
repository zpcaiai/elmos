import copy, json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'scripts/test-suite-b66-80'
SUITE=ROOT/'test-suites/batch66-80-slightly-strict'
class ToolkitTests(unittest.TestCase):
    def run_ok(self,*args):
        r=subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    def test_skill_bundle(self): self.run_ok(SCRIPTS/'validate_skill_bundle.py',ROOT)
    def test_catalog(self): self.run_ok(SCRIPTS/'validate_test_catalog.py',SUITE/'cases/catalog.json')
    def test_coverage(self): self.run_ok(SCRIPTS/'validate_coverage_matrix.py',SUITE/'coverage-matrix.json',SUITE/'cases/catalog.json')
    def test_results(self): self.run_ok(SCRIPTS/'validate_result_files.py',SUITE)
    def test_default_gate_is_not_run(self):
        with tempfile.TemporaryDirectory() as t:
            dst=Path(t)/'suite'; __import__('shutil').copytree(SUITE,dst)
            r=subprocess.run([sys.executable,str(SCRIPTS/'run_slightly_strict_gate.py'),str(dst)],text=True,capture_output=True)
            self.assertEqual(r.returncode,2); self.assertEqual(json.loads((dst/'release-gate.json').read_text(encoding='utf-8'))['status'],'NOT_RUN')
    def test_gate_rejects_fake_pass_without_evidence(self):
        with tempfile.TemporaryDirectory() as t:
            dst=Path(t)/'suite'; __import__('shutil').copytree(SUITE,dst)
            p=next((dst/'results').glob('*.json')); d=json.loads(p.read_text(encoding='utf-8')); d['status']='passed'; p.write_text(json.dumps(d),encoding='utf-8')
            r=subprocess.run([sys.executable,str(SCRIPTS/'validate_result_files.py'),str(dst)],text=True,capture_output=True)
            self.assertNotEqual(r.returncode,0)
    def test_catalog_rejects_missing_case(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'c.json'; d=json.loads((SUITE/'cases/catalog.json').read_text(encoding='utf-8')); d['cases'].pop(); p.write_text(json.dumps(d),encoding='utf-8')
            r=subprocess.run([sys.executable,str(SCRIPTS/'validate_test_catalog.py'),str(p)],text=True,capture_output=True)
            self.assertNotEqual(r.returncode,0)
    def test_coverage_rejects_missing_negative(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'m.json'; d=json.loads((SUITE/'coverage-matrix.json').read_text(encoding='utf-8')); d['source_skills'][0]['case_ids']=d['source_skills'][0]['case_ids'][:1]; p.write_text(json.dumps(d),encoding='utf-8')
            r=subprocess.run([sys.executable,str(SCRIPTS/'validate_coverage_matrix.py'),str(p),str(SUITE/'cases/catalog.json')],text=True,capture_output=True)
            self.assertNotEqual(r.returncode,0)
if __name__=='__main__': unittest.main()
