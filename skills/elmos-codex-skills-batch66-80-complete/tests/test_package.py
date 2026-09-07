import json,re,subprocess,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
class T(unittest.TestCase):
 def test_inventory(self):
  m=json.loads((R/'manifest.json').read_text());p=list((R/'agent-skills/runtime').glob('*/SKILL.md'));self.assertEqual(m['skill_count'],len(p))
 def test_batch_install(self):
  with tempfile.TemporaryDirectory() as d:
   q=subprocess.run([str(R/'install.sh'),d,'--batch','78']);self.assertEqual(0,q.returncode);self.assertEqual(16,len(list(Path(d).glob('b78-*/SKILL.md'))))
 def test_duplicate_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   self.assertEqual(0,subprocess.run([str(R/'install.sh'),d,'--batch','66'],capture_output=True).returncode);self.assertNotEqual(0,subprocess.run([str(R/'install.sh'),d,'--batch','66'],capture_output=True).returncode)
if __name__=='__main__':unittest.main()
