"""Explicit real-tool qualification, run separately from provider-fixture tests."""
from pathlib import Path
import os
import tempfile
import unittest
import json

from elmos_release_deployment.contracts import Denied, canonical, digest
from elmos_release_deployment.host_bridge import strict_json
from elmos_release_deployment.native_worker import PinnedNativeProcess, NativeTerraformWorker, NativeHelmWorker, tree_digest


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environment = {'SystemRoot':os.environ.get('SystemRoot','C:\\Windows'),
                            'TF_IN_AUTOMATION':'1','CHECKPOINT_DISABLE':'1'} if os.name == 'nt' else {
                            'TF_IN_AUTOMATION':'1','CHECKPOINT_DISABLE':'1'}

    def process(self, tool):
        path = Path(os.environ['ELMOS_TEST_'+tool.upper()])
        expected = os.environ['ELMOS_TEST_'+tool.upper()+'_SHA256']
        def capture(argv,result):
            output = os.environ.get('ELMOS_NATIVE_TEST_LOG')
            if output:
                with open(output,'a',encoding='utf-8') as stream:
                    stream.write(json.dumps({'test':self.id(),'tool':tool,'argv':argv,'exit_code':result.code,
                        'stdout':result.stdout.decode(errors='replace'),'stderr':result.stderr.decode(errors='replace')})+'\n')
        return PinnedNativeProcess(path,'sha256:'+expected,self.root,self.environment,capture)

    def test_real_terraform_saved_apply_refresh_and_destroy(self):
        process = self.process('terraform')
        (self.root/'main.tf').write_text('resource "terraform_data" "deployment" { input = "synthetic-v1" }\n')
        self.assertEqual(0,process.run(['init','-input=false','-no-color']).code)
        # Terraform's built-in provider has no downloaded dependency lock entries.
        (self.root/'.terraform.lock.hcl').write_bytes(b'')
        (self.root/'terraform.tfstate').write_bytes(canonical({'version':4,'terraform_version':'1.13.5',
            'serial':0,'lineage':'9b99231f-f138-4f18-8ef9-1f50279ad1b7','outputs':{},'resources':[]}))
        plan = self.root/'approved.tfplan'
        worker = NativeTerraformWorker(process,plan,['main.tf'])
        for mode in ('apply','destroy'):
            args=['plan','-input=false','-no-color','-out='+str(plan)]
            if mode == 'destroy': args.append('-destroy')
            self.assertEqual(0,process.run(args).code)
            state = strict_json(process.run(['state','pull']).stdout)
            request={'saved_plan_digest':digest(plan.read_bytes()),
                     'configuration_digest':digest({'main.tf':digest((self.root/'main.tf').read_bytes())}),
                     'lock_digest':digest(b''),'before_state_digest':digest(state),'mode':mode}
            inspected=worker.inspect(request)
            self.assertEqual(['terraform_data.deployment'],inspected['plan_resources'])
            result=worker.execute(request)
            self.assertTrue(result['refresh_verified'])
            self.assertEqual([] if mode == 'destroy' else ['terraform_data.deployment'],result['resource_addresses'])
        self.assertEqual([],strict_json(process.run(['state','pull']).stdout)['resources'])

    def test_real_helm_render_and_input_drift_rejected(self):
        process=self.process('helm')
        chart=self.root/'chart'; (chart/'templates').mkdir(parents=True)
        (chart/'Chart.yaml').write_text('apiVersion: v2\nname: native-test\nversion: 0.1.0\n')
        (chart/'Chart.lock').write_text('dependencies: []\ndigest: sha256:'+('0'*64)+'\ngenerated: "2026-01-01T00:00:00Z"\n')
        (chart/'templates'/'deployment.yaml').write_text('''apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}
  namespace: {{ .Release.Namespace }}
spec:
  replicas: {{ .Values.replicas }}
''')
        values=self.root/'values.json'; values.write_bytes(canonical({'replicas':2}))
        request={'chart_digest':tree_digest(chart),'values_digest':digest(values.read_bytes()),
            'lock_digest':digest((chart/'Chart.lock').read_bytes()),'network':'none',
            'argv':['helm','template','native-test','/input/chart','--namespace','test','--values','/input/values.json','--skip-tests']}
        worker=NativeHelmWorker(process,chart,values)
        result=worker.render(request)
        self.assertEqual(2,result['manifests'][0]['spec']['replicas'])
        self.assertEqual('test',result['manifests'][0]['metadata']['namespace'])
        values.write_bytes(b'{}')
        with self.assertRaisesRegex(Denied,'helm_input_drift'): worker.render(request)

    def test_binary_digest_mismatch_never_executes(self):
        process=self.process('helm')
        process.binary_digest=digest(b'unapproved')
        with self.assertRaisesRegex(Denied,'native_binary_drift'): process.run(['version'])
