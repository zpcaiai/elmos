import json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ToolkitTests(unittest.TestCase):
 def manifest(self): return json.loads((ROOT/'manifest.json').read_text())
 def test_manifest_count(self):
  m=self.manifest(); self.assertEqual(m['skillCount'],sum(len(b['skills']) for b in m['batches']))
 def test_each_batch_has_16(self): self.assertTrue(all(len(b['skills'])==16 for b in self.manifest()['batches']))
 def test_valid_candidate_passes(self):
  with tempfile.TemporaryDirectory() as d:
   r=subprocess.run(['python3',str(ROOT/'scripts/run_conservative_gate.py'),str(ROOT/'tests/fixtures/valid-candidate.json'),'--out',d+'/o.json'],stdout=subprocess.DEVNULL); self.assertEqual(0,r.returncode)
 def test_forged_candidate_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   r=subprocess.run(['python3',str(ROOT/'scripts/run_conservative_gate.py'),str(ROOT/'tests/fixtures/forged-success.json'),'--out',d+'/o.json'],stdout=subprocess.DEVNULL); self.assertNotEqual(0,r.returncode)
 def test_plan_reaches_pack_batches(self):
  m=self.manifest(); target=m['batches'][-1]['skills'][-1]['id']
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'p.json'; subprocess.check_call(['python3',str(ROOT/'scripts/build_execution_plan.py'),'--out',str(out),target],stdout=subprocess.DEVNULL); p=json.loads(out.read_text()); batches={int(s['id'][1:4]) for s in p['steps']}; self.assertEqual({b['batch'] for b in m['batches']},batches)
if __name__=='__main__': unittest.main()
