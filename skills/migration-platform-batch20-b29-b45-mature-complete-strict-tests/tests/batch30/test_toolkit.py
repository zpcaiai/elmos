import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts' / 'batch30'


class ToolkitTests(unittest.TestCase):
    def test_skill_bundle(self):
        subprocess.run(
            [sys.executable, str(SCRIPTS/'validate_skill_bundle.py'), str(ROOT/'.agents'/'skills')],
            check=True,
        )

    def test_scaffold_and_validate(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            subprocess.run([
                sys.executable, str(SCRIPTS/'scaffold_framework_pack.py'),
                '--source-framework','spring-boot',
                '--target-framework','aspnet-core',
                '--source-runtime','java',
                '--target-runtime','dotnet',
                '--repo-root',str(repo),
            ], check=True)
            pack = repo/'framework-packs'/'spring-boot-to-aspnet-core'
            manifest = json.loads((pack/'pack.json').read_text())
            manifest['owner']='framework-team'
            manifest['maintenance_owner']='framework-team'
            manifest['source']['framework_versions']=['3.5.1']
            manifest['source']['runtime_versions']=['21']
            manifest['target']['framework_versions']=['10.0']
            manifest['target']['runtime_versions']=['10.0']
            (pack/'pack.json').write_text(json.dumps(manifest,indent=2)+'\n')
            profile=json.loads((pack/'target-profile'/'profile.json').read_text())
            profile['owner']='framework-team'
            profile['framework_versions']=['10.0']
            profile['runtime_versions']=['10.0']
            profile['architecture_style']='controller-service-repository'
            profile['build']={'commands':['dotnet build'],'toolchain_digests':['sha256:test']}
            profile['startup']={'command':'dotnet run','health_check':'/health'}
            (pack/'target-profile'/'profile.json').write_text(json.dumps(profile,indent=2)+'\n')
            subprocess.run([sys.executable,str(SCRIPTS/'validate_framework_pack.py'),str(pack)],check=True)

    def test_framework_scoring(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            source=td/'candidates.json'
            target=td/'result.json'
            source.write_text(json.dumps({
                'weights':{'customer_demand':1.0},
                'candidates':[{'pack_key':'spring-upgrade','customer_demand':4,'evidence_notes':['customer']}],
            }))
            subprocess.run([
                sys.executable,str(SCRIPTS/'score_framework_packs.py'),str(source),'--output',str(target)
            ],check=True)
            self.assertEqual(json.loads(target.read_text())['results'][0]['decision'],'approve')


if __name__ == '__main__':
    unittest.main()
