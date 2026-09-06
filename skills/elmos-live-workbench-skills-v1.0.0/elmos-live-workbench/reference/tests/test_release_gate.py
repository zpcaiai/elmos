import importlib.util,json,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('gate',R/'scripts/release_gate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.p={'scope':'full-p0','required_surfaces':['real-600s','sandbox-isolation']}
        self.r={'scope':'full-p0','results':[{'surface':'real-600s','status':'passed','evidence_paths':['a']},{'surface':'sandbox-isolation','status':'passed','evidence_paths':['b']}],'may_self_certify_e5':False}
    def test_complete_shape(self):self.assertEqual(m.check(self.r,self.p),[])
    def test_local_tests_not_deployment(self):
        self.r['results']=[];self.assertTrue(m.check(self.r,self.p))
    def test_not_run_cannot_pass(self):
        self.r['results'][0]['status']='not_run';self.assertTrue(m.check(self.r,self.p))
    def test_no_evidence_cannot_pass(self):
        self.r['results'][0]['evidence_paths']=[];self.assertTrue(m.check(self.r,self.p))
    def test_duplicate_surface_rejected(self):
        self.r['results'].append(self.r['results'][0]);self.assertTrue(m.check(self.r,self.p))
    def test_wrong_scope_rejected(self):
        self.r['scope']='one-lab';self.assertTrue(m.check(self.r,self.p))
