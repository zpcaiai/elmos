import unittest,yaml
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class SplitPackageTests(unittest.TestCase):
 def test_registry_and_directories_match(self):
  rows=yaml.safe_load((ROOT/'catalog/skill-registry.yaml').read_text())['spec']['skills']
  self.assertEqual({r['name'] for r in rows},{p.name for p in (ROOT/'agent-skills/runtime').iterdir() if p.is_dir()})
 def test_external_dependencies_are_explicit(self):
  rows=yaml.safe_load((ROOT/'catalog/skill-registry.yaml').read_text())['spec']['skills'];by={r['name'] for r in rows}
  for r in rows:
   self.assertTrue(all(d in by for d in r.get('depends_on',[])))
   self.assertTrue(all(d not in by for d in r.get('external_depends_on',[])))
 def test_package_role(self):
  p=yaml.safe_load((ROOT/'package.yaml').read_text())
  self.assertEqual('certification',p['spec']['packageRole'])
