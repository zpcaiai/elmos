import json,shutil,tempfile,unittest,subprocess,sys
from pathlib import Path
from common import ROOT,system,Request
from install import run,NAME,RECEIPT
from scan_repo import scan
from validate_package import validate
from jsonschema import Draft202012Validator,ValidationError

class ContractTests(unittest.TestCase):
    def schema(self,name):return Draft202012Validator(json.loads((ROOT/f'contracts/schemas/{name}.schema.json').read_text()))
    def example(self,name):return json.loads((ROOT/f'contracts/examples/{name}.json').read_text())
    def test_all_package(self):self.assertEqual(validate(ROOT)['status'],'pass')
    def test_public_authority_injection(self):
        v=self.example('context-request');v['tenant']='victim'
        with self.assertRaises(ValidationError):self.schema('context-request').validate(v)
    def test_exact_selector(self):
        v=self.example('context-request');v.pop('selector')
        with self.assertRaises(ValidationError):self.schema('context-request').validate(v)
    def test_actual_reference_response(self):
        _,s,_,e=system();self.schema('context-response').validate(e.query(s,Request('cancel')))
    def test_no_certificate_property(self):
        v=self.example('context-response');v['certified']=True
        with self.assertRaises(ValidationError):self.schema('context-response').validate(v)
    def test_approved_feature_real_refs(self):
        v=self.example('feature-decision');v['status']='approved'
        with self.assertRaises(ValidationError):self.schema('feature-decision').validate(v)
    def test_existing_path_required(self):
        v=self.example('gap-analysis');v['ports'][0]['status']='existing'
        with self.assertRaises(ValidationError):self.schema('gap-analysis').validate(v)

class InstallTests(unittest.TestCase):
    def test_dry_no_writes(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);self.assertEqual(run(p)['status'],'planned');self.assertEqual(list(p.iterdir()),[])
    def test_install_no_agents_changes(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'AGENTS.md').write_text('keep');self.assertEqual(run(p,apply=True)['status'],'installed');self.assertEqual((p/'AGENTS.md').read_text(),'keep')
    def test_same_version_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);run(p,apply=True);self.assertEqual(run(p,apply=True)['status'],'already_installed')
    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);d=p/'.agents/skills'/NAME;d.mkdir(parents=True);(d/'keep').write_text('x')
            with self.assertRaises(FileExistsError):run(p,apply=True)
            self.assertEqual((d/'keep').read_text(),'x')
    def test_uninstall_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);run(p,apply=True);run(p,apply=True,uninstall=True);self.assertFalse((p/'.agents/skills'/NAME).exists())
    def test_preserve_modified_and_added(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);run(p,apply=True);d=p/'.agents/skills'/NAME;(d/'SPEC.md').write_text('local');(d/'new.txt').write_text('user');r=run(p,apply=True,uninstall=True);self.assertIn('SPEC.md',r['preserve_modified']);self.assertEqual((d/'SPEC.md').read_text(),'local');self.assertTrue((d/'new.txt').is_file())
    def test_parent_symlink(self):
        with tempfile.TemporaryDirectory() as td,tempfile.TemporaryDirectory() as outside:
            p=Path(td);(p/'.agents').symlink_to(outside,target_is_directory=True)
            with self.assertRaises(ValueError):run(p,apply=True)
    def test_receipt_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);run(p,apply=True);d=p/'.agents/skills'/NAME;r=json.loads((d/RECEIPT).read_text());r['files']['../../outside']='0'*64;(d/RECEIPT).write_text(json.dumps(r))
            with self.assertRaises(ValueError):run(p,apply=True,uninstall=True)
    def test_package_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);src=p/'src';repo=p/'repo';repo.mkdir();shutil.copytree(ROOT,src);(src/'SPEC.md').write_text('tamper')
            with self.assertRaises(ValueError):run(repo,source=src,apply=True)
    def test_lock(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'.agents').mkdir();(p/'.agents/.elmos-ai-optimization-install.lock').write_text('busy')
            with self.assertRaises(FileExistsError):run(p,apply=True)
    def test_uninstall_from_installed_copy(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);run(p,apply=True);d=p/'.agents/skills'/NAME;result=subprocess.run([sys.executable,str(d/'scripts/install.py'),'--repo',str(p),'--uninstall','--apply'],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertFalse(d.exists())

class ScannerTests(unittest.TestCase):
    def test_no_secret_or_code_execution(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'.env').write_text('secret');(p/'search.py').write_text('raise RuntimeError("NEVER EXECUTE")');r=scan(p);self.assertEqual(r['files_examined'],1);self.assertFalse(r['secrets_read']);self.assertFalse(r['repository_commands_executed'])
    def test_partial_listing(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            for i in range(3):(p/f'{i}.txt').write_text('x')
            self.assertTrue(scan(p,1)['partial'])
    def test_skip_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'link').symlink_to('/etc/passwd');self.assertEqual(scan(p)['files_examined'],0)
    def test_empty_not_missing(self):
        with tempfile.TemporaryDirectory() as td:self.assertEqual(scan(Path(td))['status'],'needs_source_review')
