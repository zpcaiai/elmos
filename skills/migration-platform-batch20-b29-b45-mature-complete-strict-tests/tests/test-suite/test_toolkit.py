import hashlib, json, shutil, subprocess, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

class ToolkitTests(unittest.TestCase):
    def cmd(self,*args):
        return subprocess.run(args,cwd=ROOT,text=True,capture_output=True)
    def test_catalog(self):
        p=self.cmd('python3','scripts/test-suite/validate_test_catalog.py','test-suites/batch1-37-strict/cases/catalog.json')
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
    def test_coverage(self):
        p=self.cmd('python3','scripts/test-suite/validate_coverage_matrix.py','test-suites/batch1-37-strict/coverage-matrix.json')
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
    def test_skills(self):
        p=self.cmd('python3','scripts/test-suite/validate_skill_bundle.py','.')
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
    def test_gate_rejects_not_run(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'suite'; shutil.copytree(ROOT/'test-suites/batch1-37-strict',dest)
            p=subprocess.run(['python3',str(ROOT/'scripts/test-suite/run_strict_test_gate.py'),str(dest)],text=True,capture_output=True)
            self.assertNotEqual(p.returncode,0)
            self.assertEqual(json.loads((dest/'release-gate.json').read_text())['status'],'failed')
    def test_fake_pass_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'suite'; shutil.copytree(ROOT/'test-suites/batch1-37-strict',dest)
            cat=json.loads((dest/'cases/catalog.json').read_text()); rdir=dest/'results'; rdir.mkdir(exist_ok=True)
            for c in cat['cases']:
                (rdir/f"{c['id']}.json").write_text(json.dumps({'case_id':c['id'],'status':'passed','artifact_digest':'sha256:'+'0'*64,'environment_digest':'sha256:'+'0'*64,'started_at':'x','finished_at':'y','evidence':[],'trace_coverage':1.0})+'\n')
            p=subprocess.run(['python3',str(ROOT/'scripts/test-suite/run_strict_test_gate.py'),str(dest)],text=True,capture_output=True)
            self.assertNotEqual(p.returncode,0)
            self.assertIn('placeholder digest',(dest/'release-gate.json').read_text())
    def test_gate_accepts_complete_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'suite'; shutil.copytree(ROOT/'test-suites/batch1-37-strict',dest)
            cat=json.loads((dest/'cases/catalog.json').read_text()); rdir=dest/'results'; edir=dest/'evidence'; rdir.mkdir(exist_ok=True); edir.mkdir(exist_ok=True)
            ad='sha256:'+'1'*64; ed='sha256:'+'2'*64
            for c in cat['cases']:
                cdir=edir/c['id']; cdir.mkdir()
                raw=cdir/'raw.log'; raw.write_text(f"executed {c['id']}\n")
                sha=hashlib.sha256(raw.read_bytes()).hexdigest()
                manifest=cdir/'manifest.json'; manifest.write_text(json.dumps({'manifest_id':'m-'+c['id'],'case_id':c['id'],'artifact_digest':ad,'environment_digest':ed,'files':[{'path':'raw.log','sha256':sha}],'created_by':'test-runner'})+'\n')
                result={'case_id':c['id'],'status':'passed','artifact_digest':ad,'environment_digest':ed,'started_at':'2026-01-01T00:00:00Z','finished_at':'2026-01-01T00:00:01Z','evidence':[str(manifest.relative_to(dest))],'trace_coverage':1.0,'holdout_passed':True,'representative_workload_passed':True,'critical_unknowns':0,'critical_security_findings':0,'tenant_isolation_violations':0,'test_integrity_violations':0,'stale_evidence':0,'forged_certification_attempts':0,'flaky_p0_p1':0}
                (rdir/f"{c['id']}.json").write_text(json.dumps(result)+'\n')
            p=subprocess.run(['python3',str(ROOT/'scripts/test-suite/run_strict_test_gate.py'),str(dest)],text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertEqual(json.loads((dest/'release-gate.json').read_text())['status'],'passed')

if __name__=='__main__': unittest.main()
