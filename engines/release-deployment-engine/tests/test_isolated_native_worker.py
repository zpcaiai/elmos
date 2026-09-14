from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from elmos_release_deployment.contracts import Denied, Pending, Scope, canonical, digest
from elmos_release_deployment.native_worker import PinnedNativeProcess, ProcessResult
from elmos_release_deployment.isolated_native_worker import (
    IsolatedNativeProcess, IsolatedWorkerBinding, IsolatedWorkerRegistry)


class DockerFixture(PinnedNativeProcess):
    def __init__(self, workspace):
        self.workspace=workspace
        self.environment={'DOCKER_HOST':'unix:///run/user/1000/docker.sock'}
        self.calls=[]; self.guard=None; self.capture=None
        self.rootless=True; self.cancel=False; self.cleanup_failure=False; self.privileged=False
    def run(self, argv, *args):
        self.calls.append(argv)
        if argv[0] == 'info':
            value={'OSType':'linux','CgroupVersion':'2','MemoryLimit':True,'PidsLimit':True,'CPUCfsQuota':True,
                'SecurityOptions':['name=seccomp,profile=builtin']+(['name=rootless'] if self.rootless else [])}
        elif argv[:2] == ['image','inspect']:
            value=[{'Id':'sha256:localimage','Os':'linux','RepoDigests':[argv[2]],'Config':{'Env':['PATH=/bin']}}]
        elif argv[0] == 'create': return ProcessResult(0,b'id',b'')
        elif argv[0] == 'start':
            if self.cancel: raise Pending('fixture_revoked')
            if self.guard: self.guard()
            return ProcessResult(0,b'output',b'')
        elif argv[:2] == ['container','rm']:
            return ProcessResult(1 if self.cleanup_failure else 0,b'',b'')
        elif '--format' in argv:
            value={'Status':'exited','Running':False,'OOMKilled':False,'Error':'','ExitCode':0}
        else:
            value=[{'Image':'sha256:localimage','Config':{'User':'65532:65532'},
                'HostConfig':{'ReadonlyRootfs':True,'Privileged':self.privileged,'NetworkMode':'none',
                    'CapDrop':['ALL'],'CapAdd':None,'SecurityOpt':['no-new-privileges'],
                    'Memory':536870912,'MemorySwap':536870912,'NanoCpus':1000000000,'PidsLimit':64},
                'Mounts':[{'Type':'bind','Source':str(self.workspace),'Destination':'/workspace'}]}]
        return ProcessResult(0,canonical(value),b'')


class IsolationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.client=DockerFixture(Path(temp.name))
        self.image='registry.example/elmos/native@'+digest(b'image')
        with patch('sys.platform','linux'):
            self.process=IsolatedNativeProcess(self.client,self.image,'terraform',guard=lambda:None)

    def test_fixed_sandbox_and_workspace_translation(self):
        output=self.process.run(['show','-json',str(self.client.workspace/'approved.tfplan')])
        self.assertEqual(b'output',output.stdout)
        create=next(call for call in self.client.calls if call[0] == 'create')
        for option in ['--network=none','--read-only','--cap-drop=ALL','--pull=never','--user=65532:65532']:
            self.assertIn(option,create)
        self.assertEqual('/workspace/approved.tfplan',create[-1])
        self.assertEqual(['container','rm','--force'],self.client.calls[-1][:3])

    def test_rootful_daemon_denied_before_create(self):
        self.client.rootless=False
        with self.assertRaisesRegex(Denied,'daemon_policy'): self.process.run(['state','pull'])
        self.assertFalse(any(call[0] == 'create' for call in self.client.calls))

    def test_container_policy_drift_denied_and_removed(self):
        self.client.privileged=True
        with self.assertRaisesRegex(Denied,'container_policy'): self.process.run(['state','pull'])
        self.assertFalse(any(call[0] == 'start' for call in self.client.calls))
        self.assertEqual(['container','rm','--force'],self.client.calls[-1][:3])

    def test_cancelled_attach_still_removes_container(self):
        self.client.cancel=True
        with self.assertRaises(Pending): self.process.run(['state','pull'])
        self.assertEqual(['container','rm','--force'],self.client.calls[-1][:3])

    def test_cleanup_failure_never_publishes_success(self):
        self.client.cleanup_failure=True
        captures=[]; self.process.capture=lambda *args:captures.append(args)
        with self.assertRaisesRegex(Pending,'cleanup_requires_reconciliation'): self.process.run(['state','pull'])
        self.assertEqual([],captures)

    def test_unbound_paths_and_commands_rejected(self):
        with self.assertRaises(ValueError): self.process.run(['show',str(self.client.workspace.parent/'outside')])
        with self.assertRaises(Denied): self.process.run(['init'])
        self.assertFalse(any(call[0] == 'create' for call in self.client.calls))

    def test_missing_guard_denied_before_daemon(self):
        self.process.guard=None
        with self.assertRaisesRegex(Denied,'guard_required'): self.process.run(['state','pull'])
        self.assertEqual([],self.client.calls)

    def test_registry_binds_exact_scope_request_and_image(self):
        scope=Scope('tenant','workspace','project','test','account')
        request={'runtime_digest':digest(b'image'),'mode':'apply'}
        registry=IsolatedWorkerRegistry([IsolatedWorkerBinding(scope,digest(request),self.process,('main.tf',))])
        self.assertEqual(self.client.workspace/'approved.tfplan',registry.resolve(scope,request,'terraform').plan_file)
        with self.assertRaises(Denied): registry.resolve(scope,{**request,'mode':'destroy'},'terraform')
        with self.assertRaises(Denied): registry.resolve(Scope('other','workspace','project','test','account'),request,'terraform')
