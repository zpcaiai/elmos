import importlib.util,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('installer',R/'scripts/install.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class InstallTests(unittest.TestCase):
    def test_dry_run_no_files(self):
        with tempfile.TemporaryDirectory() as d:
            repo=Path(d);m.install(repo);self.assertEqual(list(repo.iterdir()),[])
    def test_roundtrip_preserves_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            repo=Path(d);(repo/'AGENTS.md').write_text('baseline')
            m.install(repo,True)
            self.assertTrue((repo/m.ROUTER/'SKILL.md').exists())
            self.assertEqual(len(list((repo/'.agents/skills').rglob('SKILL.md'))),1)
            m.uninstall(repo,True)
            self.assertFalse((repo/m.PAYLOAD).exists());self.assertEqual((repo/'AGENTS.md').read_text(),'baseline')
    def test_conflict_refused(self):
        with tempfile.TemporaryDirectory() as d:
            repo=Path(d);m.install(repo,True)
            with self.assertRaises(FileExistsError):m.install(repo,True)
    def test_modified_file_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            repo=Path(d);m.install(repo,True);p=repo/m.PAYLOAD/'SKILL.md';p.write_text('user edits')
            result=m.uninstall(repo,True)
            self.assertEqual(p.read_text(),'user edits');self.assertIn(str(m.PAYLOAD/'SKILL.md'),result['preserved_modified_files'])
    def test_symlink_parent_refused(self):
        with tempfile.TemporaryDirectory() as d,tempfile.TemporaryDirectory() as target:
            repo=Path(d);(repo/'.elmos').symlink_to(target)
            with self.assertRaises(ValueError):m.install(repo,True)
