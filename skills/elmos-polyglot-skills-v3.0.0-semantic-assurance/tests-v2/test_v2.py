import csv,json,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
class T(unittest.TestCase):
 def test_manifest(self):
  m=json.loads((R/'manifest.json').read_text()); self.assertEqual(168,len(m['skills'])); self.assertEqual(28,len(m['technologies'])); self.assertEqual(8,len(m['repository_surfaces']))
 def test_routes(self):
  with (R/'route-matrix.csv').open() as f: rows=list(csv.DictReader(f))
  self.assertEqual(784,len(rows))
 def test_registry(self): self.assertEqual(40,len(json.loads((R/'route-registry.json').read_text())['spec']['profiles']))
 def test_skill_files(self):
  m=json.loads((R/'manifest.json').read_text()); self.assertTrue(all((R/x['path']).exists() for x in m['skills']))
 def test_readiness(self): self.assertTrue(all(x['readiness']=='not-run' for x in json.loads((R/'manifest.json').read_text())['skills']))
if __name__=='__main__': unittest.main()
