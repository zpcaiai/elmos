"""Native programs for a host-supervised deployment Runner.

These workers do not create authorization, isolation, credentials, dispatch
claims or signatures. The canonical supervisor owns those boundaries. Native
outputs below are observations to be persisted and verified by that supervisor.
The provider-free qualification invokes these same programs in temporary dirs.
"""
from dataclasses import dataclass, field
import os
from pathlib import Path
import signal
import subprocess
import threading

from .contracts import Pending, canonical, digest, require, sha
from .host_bridge import strict_json


@dataclass(frozen=True)
class ProcessResult:
    code: int
    stdout: bytes = field(repr=False)
    stderr: bytes = field(repr=False)


class PinnedNativeProcess:
    def __init__(self, binary, binary_digest, workspace, environment, capture=None):
        self.binary, self.workspace = Path(binary), Path(workspace)
        sha(binary_digest)
        require(self.binary.is_absolute() and self.workspace.is_absolute(), 'native_absolute_paths')
        self.binary_digest = binary_digest
        self.environment = dict(environment)
        self.capture = capture
        require(all(type(k) is str and type(v) is str and '\x00' not in k+v
                    for k,v in self.environment.items()), 'native_environment')

    def run(self, argv, timeout=60, limit=4194304):
        require(type(argv) is list and all(type(v) is str and '\x00' not in v for v in argv), 'native_argv')
        require(type(timeout) is int and 1 <= timeout <= 1800 and 0 < limit <= 16777216, 'native_budgets')
        require(not self.binary.is_symlink() and not any(p.is_symlink() for p in self.binary.parents) and self.binary.is_file()
                and digest(self.binary.read_bytes()) == self.binary_digest, 'native_binary_drift')
        require(self.workspace.is_dir() and not self.workspace.is_symlink(), 'native_workspace')
        process = subprocess.Popen([str(self.binary), *argv], cwd=self.workspace, env=self.environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=(os.name == 'posix'))
        buffers = [bytearray(), bytearray()]
        overflow = threading.Event()
        def stop():
            try:
                if os.name == 'posix': os.killpg(process.pid,signal.SIGKILL)
                else: process.kill()
            except ProcessLookupError: pass
        def drain(stream, buffer):
            try:
                while True:
                    chunk = stream.read(65536)
                    if not chunk: return
                    if len(buffer)+len(chunk) > limit:
                        overflow.set()
                        stop()
                        return
                    buffer.extend(chunk)
            finally:
                stream.close()
        readers = [threading.Thread(target=drain,args=(stream,buffer),daemon=True)
                   for stream,buffer in zip((process.stdout,process.stderr),buffers)]
        for reader in readers: reader.start()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            stop()
            process.wait(timeout=10)
            raise Pending('native_process_timeout_requires_reconciliation') from None
        finally:
            for reader in readers: reader.join(10)
        require(not overflow.is_set() and not any(r.is_alive() for r in readers), 'native_output_bounds')
        result = ProcessResult(process.returncode,bytes(buffers[0]),bytes(buffers[1]))
        if self.capture is not None: self.capture(argv,result)
        return result


def file_bytes(path, limit=16777216):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and not any(p.is_symlink() for p in path.parents),
            'native_input_file')
    require(path.stat().st_size <= limit, 'native_input_bounds')
    raw = path.read_bytes()
    require(len(raw) <= limit, 'native_input_bounds')
    return raw


def tree_digest(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), 'native_tree')
    files = {}
    total = 0
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'native_tree_symlink')
        if path.is_file():
            raw = file_bytes(path)
            total += len(raw)
            require(len(files) < 1000 and total <= 16777216, 'native_tree_bounds')
            files[path.relative_to(root).as_posix()] = digest(raw)
    return digest(files)


class NativeTerraformWorker:
    def __init__(self, process, plan_file, configuration_files):
        self.process, self.plan_file = process, Path(plan_file)
        self.configuration_files = tuple(configuration_files)
        require(0 < len(self.configuration_files) <= 100, 'terraform_configuration_bounds')
        require(len(set(self.configuration_files)) == len(self.configuration_files), 'terraform_duplicate_file')
        for name in self.configuration_files:
            require(type(name) is str and Path(name).name == name and not name.startswith('.')
                    and name.endswith(('.tf','.tf.json','.tfvars','.tfvars.json')), 'terraform_configuration_path')

    def _inputs(self, request):
        require(digest(file_bytes(self.plan_file)) == request['saved_plan_digest'], 'terraform_saved_plan_drift')
        files = {name:digest(file_bytes(self.process.workspace/name)) for name in self.configuration_files}
        actual = {p.name for p in self.process.workspace.iterdir() if p.name.endswith(('.tf','.tf.json','.tfvars','.tfvars.json'))}
        require(actual == set(files) and digest(files) == request['configuration_digest'], 'terraform_configuration_drift')
        require(digest(file_bytes(self.process.workspace/'.terraform.lock.hcl')) == request['lock_digest'], 'terraform_lock_drift')

    def _state(self):
        result = self.process.run(['state','pull'])
        require(result.code == 0, 'terraform_state_unavailable')
        state = strict_json(result.stdout)
        require(type(state) is dict and type(state.get('serial')) is int and state['serial'] >= 0
                and type(state.get('lineage')) is str and state['lineage'], 'terraform_state_identity')
        return state

    def inspect(self, request):
        require(request.get('mode') in {'apply','destroy'}, 'terraform_mode')
        self._inputs(request)
        result = self.process.run(['show','-json',str(self.plan_file)])
        require(result.code == 0, 'terraform_plan_unreadable')
        plan = strict_json(result.stdout)
        require(type(plan) is dict and plan.get('format_version') in {'1.2'} and not plan.get('errored')
                and plan.get('complete') is True, 'terraform_plan_incomplete')
        # Provisioners bypass the provider/resource permission model.
        def no_provisioners(node):
            if type(node) is dict:
                require(not node.get('provisioners'), 'terraform_provisioner_forbidden')
                for value in node.values(): no_provisioners(value)
            elif type(node) is list:
                for value in node: no_provisioners(value)
        no_provisioners(plan.get('configuration',{}))
        changes = plan.get('resource_changes',[])
        require(type(changes) is list and len(changes) <= 100, 'terraform_change_bounds')
        addresses = []
        for change in changes:
            require(change.get('mode') == 'managed' and type(change.get('address')) is str, 'terraform_change_kind')
            actions = change.get('change',{}).get('actions')
            require(actions in ([['delete'],['no-op']] if request['mode'] == 'destroy' else
                    [['create'],['update'],['no-op']]), 'terraform_unapproved_destructive_action')
            addresses.append(change['address'])
        require(len(set(addresses)) == len(addresses) and bool(addresses), 'terraform_change_addresses')
        state = self._state()
        require(digest(state) == request['before_state_digest'], 'terraform_before_state_drift')
        return {'plan_resources':sorted(addresses),'plan_mode':request['mode'],
                'before_state_digest':digest(state),'plan_observation_digest':digest(plan)}

    def execute(self, request):
        before = self.inspect(request)
        result = self.process.run(['apply','-input=false','-lock=true','-lock-timeout=60s',str(self.plan_file)],1800)
        if result.code != 0: raise Pending('terraform_apply_failed_requires_reconciliation')
        # No state repair or blind retry. Refresh-only plan is read-only to managed
        # resources and exit 2 means the observed infrastructure differs from state.
        refresh = self.process.run(['plan','-refresh-only','-detailed-exitcode','-input=false',
                                    '-lock=true','-lock-timeout=60s'],1800)
        if refresh.code != 0: raise Pending('terraform_refresh_not_reconciled')
        state = self._state()
        addresses = []
        for resource in state.get('resources',[]):
            require(resource.get('mode') == 'managed', 'terraform_state_resource_kind')
            prefix = (resource['module']+'.') if resource.get('module') else ''
            for instance in resource.get('instances',[]):
                require(not instance.get('deposed'), 'terraform_deposed_instance')
                suffix = '['+canonical(instance['index_key']).decode()+']' if 'index_key' in instance else ''
                addresses.append(prefix+resource['type']+'.'+resource['name']+suffix)
        expected = [] if request['mode'] == 'destroy' else before['plan_resources']
        require(sorted(addresses) == expected, 'terraform_final_resource_drift')
        return {'exit_code':0,'state_digest':digest(state),'state_lineage':state['lineage'],
                'state_serial':state['serial'],'resource_addresses':sorted(addresses),
                'stdout_digest':digest(result.stdout),'stderr_digest':digest(result.stderr),
                'refresh_verified':True}


class NativeHelmWorker:
    def __init__(self, process, chart_directory, values_file):
        self.process,self.chart,self.values = process,Path(chart_directory),Path(values_file)

    def render(self, request):
        import yaml
        require(tree_digest(self.chart) == request['chart_digest'] and
                digest(file_bytes(self.values)) == request['values_digest'] and
                digest(file_bytes(self.chart/'Chart.lock')) == request['lock_digest'], 'helm_input_drift')
        argv = request['argv']
        require(len(argv) == 9 and argv[:2] == ['helm','template'] and argv[3] == '/input/chart'
                and argv[4] == '--namespace' and argv[6:] == ['--values','/input/values.json','--skip-tests']
                and request['network'] == 'none', 'helm_command_contract')
        import re
        require(all(re.fullmatch(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?',v) and len(v) <= 53
                    for v in (argv[2],argv[5])), 'helm_names')
        result = self.process.run(['template',argv[2],str(self.chart),'--namespace',argv[5],
                                   '--values',str(self.values),'--skip-tests'],60,1048576)
        require(result.code == 0, 'helm_native_render_failed')
        # Reject aliases before loading to keep expansion bounded by output size.
        require(not any(isinstance(token,(yaml.tokens.AliasToken,yaml.tokens.AnchorToken))
                        for token in yaml.scan(result.stdout)), 'helm_yaml_alias')
        manifests = [obj for obj in yaml.safe_load_all(result.stdout) if obj is not None]
        require(0 < len(manifests) <= 100 and all(type(obj) is dict for obj in manifests), 'helm_manifest_bounds')
        return {'exit_code':0,'manifests':manifests,'dependencies_verified':True,
                'stdout_digest':digest(result.stdout),'stderr_digest':digest(result.stderr)}
