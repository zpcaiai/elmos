import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from elmos_release_deployment.contracts import Denied, Pending, canonical, digest
from elmos_release_deployment.native_worker import NativeTerraformWorker, PinnedNativeProcess, ProcessResult


class SupervisionTests(unittest.TestCase):
    def test_revocation_terminates_running_process_without_success_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = Path(sys.executable).resolve()
            start = time.monotonic()
            def guard():
                if time.monotonic()-start >= 0.5: raise Denied('revoked')
            captures = []
            process = PinnedNativeProcess(binary,digest(binary.read_bytes()),root,
                {'SystemRoot':os.environ.get('SystemRoot','C:\\Windows')},
                lambda *args: captures.append(args),guard)
            with self.assertRaises(Pending):
                process.run(['-c','import time; time.sleep(30)'],timeout=10)
            self.assertLess(time.monotonic()-start,5)
            self.assertEqual([],captures)

    def test_revoked_before_launch_never_spawns(self):
        def guard(): raise Denied('revoked')
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(sys.executable).resolve()
            process = PinnedNativeProcess(binary,digest(binary.read_bytes()),Path(directory),{},guard=guard)
            with patch('subprocess.Popen') as spawn:
                with self.assertRaises(Denied): process.run(['--version'])
                spawn.assert_not_called()

    def worker(self, root, module=False, final_lineage='original', final_serial=2):
        plan = {'format_version':'1.2','complete':True,
            'configuration':{'root_module':{'module_calls':{'nested':{}}} if module else {}},
            'resource_changes':[{'mode':'managed','address':'terraform_data.test',
                'change':{'actions':['create']}}]}
        before = {'serial':1,'lineage':'original','resources':[]}
        final = {'serial':final_serial,'lineage':final_lineage,'resources':[{'mode':'managed',
            'type':'terraform_data','name':'test','instances':[{}]}]}
        class Process:
            workspace = root
            def __init__(self): self.calls=[]; self.applied=False
            def run(self, argv, *args):
                self.calls.append(argv)
                if argv[0] == 'show': value=plan
                elif argv[0] == 'state': value=final if self.applied else before
                else:
                    if argv[0] == 'apply': self.applied=True
                    return ProcessResult(0,b'',b'')
                return ProcessResult(0,canonical(value),b'')
        (root/'main.tf').write_bytes(b'fixture')
        (root/'plan').write_bytes(b'plan')
        (root/'.terraform.lock.hcl').write_bytes(b'')
        request={'mode':'apply','saved_plan_digest':digest(b'plan'),
            'configuration_digest':digest({'main.tf':digest(b'fixture')}),
            'lock_digest':digest(b''),'before_state_digest':digest(before)}
        return NativeTerraformWorker(Process(),root/'plan',['main.tf']),request

    def test_unbound_modules_rejected_before_provider_state_read(self):
        with tempfile.TemporaryDirectory() as directory:
            worker,request=self.worker(Path(directory),module=True)
            with self.assertRaisesRegex(Denied,'terraform_module_inputs_unbound'): worker.inspect(request)
            self.assertEqual(['show'],[call[0] for call in worker.process.calls])

    def test_state_replacement_or_serial_regression_never_succeeds(self):
        for lineage,serial in [('replacement',2),('original',0)]:
            with self.subTest(lineage=lineage,serial=serial), tempfile.TemporaryDirectory() as directory:
                worker,request=self.worker(Path(directory),final_lineage=lineage,final_serial=serial)
                with self.assertRaisesRegex(Denied,'terraform_state_identity_drift'): worker.execute(request)
