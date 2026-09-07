import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts' / 'batch32'

def complete_pack(pack: Path) -> None:
    manifest = json.loads((pack / 'pack.json').read_text())
    manifest['owner'] = 'client-platform-team'
    manifest['maintenance_owner'] = 'client-platform-team'
    manifest['ux_owner'] = 'product-design-team'
    manifest['accessibility_owner'] = 'accessibility-team'
    manifest['source']['router'] = ['angularjs-router-1.8.3']
    manifest['source']['renderer'] = ['angularjs-1.8.3']
    manifest['source']['state'] = ['scope']
    manifest['source']['forms'] = ['angularjs-forms']
    manifest['source']['styling'] = ['css']
    manifest['source']['design_system'] = ['legacy-design-system']
    manifest['source']['api_client'] = ['$http']
    manifest['source']['identity'] = ['oidc-client']
    manifest['source']['i18n'] = ['angular-translate']
    manifest['source']['test_tools'] = ['karma-6.4', 'jasmine-5.1']
    manifest['source']['browsers'] = ['chromium-126']
    manifest['target']['router'] = ['react-router-7.6']
    manifest['target']['renderer'] = ['react-dom-19.1']
    manifest['target']['state'] = ['react-state']
    manifest['target']['forms'] = ['react-hook-form-7.57']
    manifest['target']['styling'] = ['css-modules']
    manifest['target']['design_system'] = ['target-design-system']
    manifest['target']['api_client'] = ['fetch']
    manifest['target']['identity'] = ['oidc-client-ts-3.3']
    manifest['target']['i18n'] = ['i18next-25']
    manifest['target']['test_tools'] = ['vitest-3', 'playwright-1.53']
    manifest['target']['browsers'] = ['chromium-126']
    (pack / 'pack.json').write_text(json.dumps(manifest, indent=2) + '\n')

    support = json.loads((pack / 'support-matrix.json').read_text())
    for capability in support['capabilities']:
        capability['owner'] = 'client-platform-team'
    (pack / 'support-matrix.json').write_text(json.dumps(support, indent=2) + '\n')

    fingerprint = json.loads((pack / 'source-fingerprint' / 'fingerprint.json').read_text())
    fingerprint['snapshot_digest'] = 'sha256:source'
    fingerprint['source_tuple'] = manifest['source']
    (pack / 'source-fingerprint' / 'fingerprint.json').write_text(json.dumps(fingerprint, indent=2) + '\n')

    target = json.loads((pack / 'target-profile' / 'profile.json').read_text())
    target['owner'] = 'client-platform-team'
    target['router'] = ['react-router-7.6']
    target['rendering_strategy'] = {'mode': 'csr'}
    target['state_strategy'] = {'provider': 'react-state'}
    target['form_strategy'] = {'provider': 'react-hook-form-7.57'}
    target['styling_strategy'] = {'mode': 'css-modules'}
    target['design_system_strategy'] = {'mode': 'mapped-components'}
    target['api_client_strategy'] = {'provider': 'fetch'}
    target['auth_strategy'] = {'mode': 'oidc'}
    target['i18n_strategy'] = {'provider': 'i18next-25'}
    target['accessibility_profile'] = {'standard': 'WCAG-2.2-AA'}
    target['browser_matrix'] = ['chromium-126']
    target['test_profiles'] = ['vitest-3', 'playwright-1.53']
    target['provision'] = {'commands': ['npm ci', 'npm run build']}
    target['health_check'] = {'commands': ['npm run test:e2e -- --project=chromium']}
    target['security'] = {'content_security_policy': 'strict'}
    target['lifecycle'] = {'support_until': '2028-12-31', 'upgrade_policy': 'annual-review'}
    (pack / 'target-profile' / 'profile.json').write_text(json.dumps(target, indent=2) + '\n')

    acceptance = json.loads((pack / 'acceptance' / 'acceptance-profile.json').read_text())
    acceptance['owner'] = 'quality-team'
    acceptance['browser_matrix'] = ['chromium-126']
    acceptance['accessibility'] = {'standard': 'WCAG-2.2-AA', 'critical_violations': 0}
    (pack / 'acceptance' / 'acceptance-profile.json').write_text(json.dumps(acceptance, indent=2) + '\n')

    ir = json.loads((pack / 'ui-ir' / 'model.json').read_text())
    ir['source_snapshot_digest'] = 'sha256:source'
    ir['routes'] = [{
        'id': 'route.home', 'kind': 'route', 'name': 'home',
        'source_refs': [{'path': 'src/app.js', 'line': 1}],
        'references': ['view.home'],
    }]
    ir['views'] = [{
        'id': 'view.home', 'kind': 'view', 'name': 'Home',
        'source_refs': [{'path': 'src/home.html', 'line': 1}],
        'references': [],
    }]
    ir['source_map'] = [
        {'node_id': 'route.home', 'source_refs': [{'path': 'src/app.js', 'line': 1}]},
        {'node_id': 'view.home', 'source_refs': [{'path': 'src/home.html', 'line': 1}]},
    ]
    (pack / 'ui-ir' / 'model.json').write_text(json.dumps(ir, indent=2) + '\n')

    certification = json.loads((pack / 'certification' / 'certification.json').read_text())
    certification['owner'] = 'quality-team'
    certification['exact_tuple'] = {'source': manifest['source'], 'target': manifest['target']}
    (pack / 'certification' / 'certification.json').write_text(json.dumps(certification, indent=2) + '\n')


class ToolkitTests(unittest.TestCase):
    def test_skill_bundle(self):
        subprocess.run([
            sys.executable, str(SCRIPTS / 'validate_skill_bundle.py'),
            str(ROOT / '.agents' / 'skills'),
        ], check=True)

    def test_schemas_and_templates(self):
        import jsonschema
        for schema_path in sorted((ROOT / 'schemas' / 'batch32').glob('*.schema.json')):
            schema = json.loads(schema_path.read_text())
            jsonschema.validators.validator_for(schema).check_schema(schema)
        pairs = [
            ('client-pack.json', 'client-pack.schema.json'),
            ('support-matrix.json', 'client-support-matrix.schema.json'),
            ('source-fingerprint.json', 'source-fingerprint.schema.json'),
            ('ui-interaction-ir.json', 'ui-interaction-ir.schema.json'),
            ('target-profile.json', 'target-profile.schema.json'),
            ('acceptance-profile.json', 'acceptance-profile.schema.json'),
            ('certification.json', 'client-certification.schema.json'),
        ]
        for template, schema_name in pairs:
            data = json.loads((ROOT / 'templates' / 'batch32' / template).read_text())
            schema = json.loads((ROOT / 'schemas' / 'batch32' / schema_name).read_text())
            jsonschema.validate(data, schema)

    def test_scaffold_and_validate(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run([
                sys.executable, str(SCRIPTS / 'scaffold_client_pack.py'),
                '--source-stack', 'angularjs',
                '--target-stack', 'react',
                '--source-version', '1.8.3',
                '--target-version', '19.1.0',
                '--source-language', 'javascript',
                '--target-language', 'typescript',
                '--source-language-version', 'es5',
                '--target-language-version', '5.8',
                '--source-runtime', 'browser',
                '--target-runtime', 'browser',
                '--source-runtime-version', 'chromium-126',
                '--target-runtime-version', 'chromium-126',
                '--source-build-tool', 'grunt-1.6',
                '--target-build-tool', 'vite-6.3',
                '--source-package-manager', 'npm-10',
                '--target-package-manager', 'npm-10',
                '--repo-root', str(repo),
            ], check=True)
            pack = repo / 'client-packs' / 'angularjs-to-react'
            complete_pack(pack)
            subprocess.run([
                sys.executable, str(SCRIPTS / 'validate_client_pack.py'), str(pack)
            ], check=True)
            subprocess.run([
                sys.executable, str(SCRIPTS / 'validate_ui_ir.py'),
                str(pack / 'ui-ir' / 'model.json')
            ], check=True)

    def test_ui_ir_validator_rejects_unknown_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ir.json'
            data = json.loads((ROOT / 'templates' / 'batch32' / 'ui-interaction-ir.json').read_text())
            data['source_snapshot_digest'] = 'sha256:test'
            data['components'] = [{
                'id': 'component.a', 'kind': 'component', 'name': 'A',
                'source_refs': [{'path': 'a.js'}], 'references': ['component.missing'],
            }]
            data['source_map'] = [{
                'node_id': 'component.a', 'source_refs': [{'path': 'a.js'}],
            }]
            path.write_text(json.dumps(data))
            result = subprocess.run([
                sys.executable, str(SCRIPTS / 'validate_ui_ir.py'), str(path)
            ])
            self.assertEqual(result.returncode, 1)

    def test_candidate_scoring(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / 'candidates.json'
            output = directory / 'result.json'
            source.write_text(json.dumps({
                'weights': {
                    'customer_demand': 2,
                    'migration_value': 2,
                    'representative_workloads': 1.5,
                    'engineering_reuse': 1,
                    'source_complexity': -0.5,
                    'visual_risk': -0.5,
                    'security_risk': -1,
                },
                'candidates': [{
                    'pack_key': 'angularjs-to-react',
                    'customer_demand': 4,
                    'migration_value': 4,
                    'representative_workloads': 3,
                    'engineering_reuse': 4,
                    'source_complexity': 3,
                    'visual_risk': 3,
                    'security_risk': 2,
                    'evidence_notes': ['design partner'],
                }],
            }))
            subprocess.run([
                sys.executable, str(SCRIPTS / 'score_client_candidates.py'),
                str(source), '--output', str(output),
            ], check=True)
            self.assertEqual(json.loads(output.read_text())['results'][0]['decision'], 'approve')

    def test_conservative_gate_rejects_fake_certification(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run([
                sys.executable, str(SCRIPTS / 'scaffold_client_pack.py'),
                '--source-stack', 'angularjs',
                '--target-stack', 'react',
                '--source-version', '1.8.3',
                '--target-version', '19.1.0',
                '--source-language', 'javascript',
                '--target-language', 'typescript',
                '--source-language-version', 'es5',
                '--target-language-version', '5.8',
                '--source-runtime', 'browser',
                '--target-runtime', 'browser',
                '--source-runtime-version', 'chromium-126',
                '--target-runtime-version', 'chromium-126',
                '--source-build-tool', 'grunt-1.6',
                '--target-build-tool', 'vite-6.3',
                '--source-package-manager', 'npm-10',
                '--target-package-manager', 'npm-10',
                '--repo-root', str(repo),
            ], check=True)
            pack = repo / 'client-packs' / 'angularjs-to-react'
            complete_pack(pack)
            manifest = json.loads((pack / 'pack.json').read_text())
            manifest['status'] = 'certified'
            (pack / 'pack.json').write_text(json.dumps(manifest, indent=2) + '\n')
            certification = json.loads((pack / 'certification' / 'certification.json').read_text())
            certification['status'] = 'certified'
            (pack / 'certification' / 'certification.json').write_text(json.dumps(certification, indent=2) + '\n')
            result = subprocess.run([
                sys.executable, str(SCRIPTS / 'run_client_gate.py'), str(pack)
            ])
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
