"""Dedicated Linux rootless Docker backend for offline native deployment tools.

No pulls, daemon discovery, credentials, arbitrary image commands or network
options come from a request. Cloud Terraform backends are deliberately unsupported.
The external host still owns authorization, dispatch, attestation and evidence.
"""
from copy import copy
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from uuid import uuid4

from .contracts import Pending, digest, require
from .host_bridge import strict_json
from .native_worker import NativeHelmWorker, NativeTerraformWorker, PinnedNativeProcess, ProcessResult


class IsolatedNativeProcess(PinnedNativeProcess):
    def __init__(self, client, image, tool, guard=None, capture=None):
        require(sys.platform == 'linux', 'isolated_worker_linux_required')
        require(isinstance(client,PinnedNativeProcess), 'isolated_worker_pinned_client')
        require(client.guard is None, 'isolated_worker_cleanup_client_guard')
        require(re.fullmatch(r'[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}',image) is not None,
                'isolated_worker_image_digest')
        require(tool in {'terraform','helm'}, 'isolated_worker_tool')
        require(set(client.environment) == {'DOCKER_HOST'} and
                re.fullmatch(r'unix:///run/user/[1-9][0-9]*/docker.sock',client.environment['DOCKER_HOST']),
                'isolated_worker_local_rootless_socket')
        require(not any(c in str(client.workspace) for c in ',\n\r'), 'isolated_worker_mount_path')
        self.client,self.image,self.tool = client,image,tool
        self.workspace,self.guard,self.capture = client.workspace,guard,capture

    def _json(self, argv):
        result=self.client.run(argv,30)
        require(result.code == 0, 'isolated_worker_inspection_failed')
        return strict_json(result.stdout)

    def preflight(self):
        info=self._json(['info','--format','{{json .}}'])
        require(info.get('OSType') == 'linux' and info.get('CgroupVersion') == '2'
                and info.get('MemoryLimit') is True and info.get('PidsLimit') is True
                and info.get('CPUCfsQuota') is True
                and 'name=rootless' in info.get('SecurityOptions',[])
                and any(v.startswith('name=seccomp') for v in info.get('SecurityOptions',[])),
                'isolated_worker_daemon_policy')
        images=self._json(['image','inspect',self.image])
        require(type(images) is list and len(images) == 1, 'isolated_worker_image_missing')
        image=images[0]
        require(self.image in image.get('RepoDigests',[]) and image.get('Os') == 'linux'
                and not image.get('Config',{}).get('Volumes'), 'isolated_worker_image_policy')
        require(all(v.split('=',1)[0] in {'PATH','LANG'} for v in image.get('Config',{}).get('Env',[])),
                'isolated_worker_image_environment')
        return image['Id']

    def _arguments(self, argv):
        require(type(argv) is list and argv and all(type(v) is str and '\x00' not in v for v in argv),
                'isolated_worker_argv')
        allowed={'terraform':{'show','state','apply','plan'},'helm':{'template'}}
        require(argv[0] in allowed[self.tool], 'isolated_worker_command')
        translated=[]
        for value in argv:
            if Path(value).is_absolute():
                path=Path(value)
                require(not path.is_symlink() and not any(p.is_symlink() for p in path.parents),
                        'isolated_worker_input_symlink')
                try: relative=path.resolve().relative_to(self.workspace.resolve())
                except ValueError: raise ValueError('isolated_worker_path_outside_workspace') from None
                value='/workspace/'+relative.as_posix()
            translated.append(value)
        return translated

    def run(self, argv, timeout=60, limit=4194304):
        require(type(timeout) is int and 1 <= timeout <= 1800 and type(limit) is int
                and 0 < limit <= 16777216, 'isolated_worker_budgets')
        require(callable(self.guard), 'isolated_worker_guard_required')
        self.guard()
        image_id=self.preflight()
        name='elmos-deployment-'+uuid4().hex
        command=['create','--name',name,'--label','io.elmos.deployment-worker=true',
            '--pull=never','--network=none','--read-only','--cap-drop=ALL',
            '--security-opt=no-new-privileges','--user=65532:65532','--ipc=none',
            '--cpus=1','--memory=512m','--memory-swap=512m','--pids-limit=64',
            '--ulimit=nofile=1024:1024','--log-driver=none',
            '--mount','type=bind,source='+str(self.workspace)+',target=/workspace',
            '--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m','--workdir=/workspace',
            '--env=HOME=/tmp','--env=TF_IN_AUTOMATION=1','--env=CHECKPOINT_DISABLE=1',
            '--env=TF_CLI_CONFIG_FILE=/dev/null','--entrypoint=/opt/elmos/bin/'+self.tool,
            self.image,*self._arguments(argv)]
        try:
            self.guard()
            created=self.client.run(command,30)
            require(created.code == 0, 'isolated_worker_create_failed')
            records=self._json(['container','inspect',name])
            require(type(records) is list and len(records) == 1, 'isolated_worker_container_missing')
            container=records[0]; config=container['HostConfig']
            require(container['Image'] == image_id and config.get('ReadonlyRootfs') is True
                and config.get('Privileged') is False and config.get('NetworkMode') == 'none'
                and config.get('CapDrop') == ['ALL'] and not config.get('CapAdd')
                and 'no-new-privileges' in config.get('SecurityOpt',[])
                and config.get('Memory') == 536870912 and config.get('MemorySwap') == 536870912
                and config.get('NanoCpus') == 1000000000 and config.get('PidsLimit') == 64
                and container['Config'].get('User') == '65532:65532', 'isolated_worker_container_policy')
            mounts=container.get('Mounts',[])
            binds=[mount for mount in mounts if mount.get('Type') == 'bind']
            require(len(binds) == 1 and binds[0].get('Source') == str(self.workspace)
                and binds[0].get('Destination') == '/workspace'
                and all(mount in binds or (mount.get('Type') == 'tmpfs'
                    and mount.get('Destination') == '/tmp') for mount in mounts), 'isolated_worker_mount_policy')
            attached=copy(self.client)
            attached.guard=self.guard
            result=attached.run(['start','--attach',name],timeout,limit)
            state=self._json(['container','inspect','--format','{{json .State}}',name])
            require(state.get('Status') == 'exited' and state.get('Running') is False
                    and not state.get('OOMKilled') and not state.get('Error')
                    and type(state.get('ExitCode')) is int, 'isolated_worker_outcome_unknown')
            require(result.code == state['ExitCode'], 'isolated_worker_exit_mismatch')
            self.guard()
            output=ProcessResult(state['ExitCode'],result.stdout,result.stderr)
        finally:
            # Always address the daemon, even after the attach client is killed.
            # Cleanup uses no revoked workload credentials and cannot launch work.
            removed=self.client.run(['container','rm','--force',name],30)
            if removed.code != 0: raise Pending('isolated_worker_cleanup_requires_reconciliation') from None
        if self.capture is not None: self.capture(argv,output)
        return output


@dataclass(frozen=True)
class IsolatedWorkerBinding:
    scope: object
    request_digest: str
    process: IsolatedNativeProcess
    configuration_files: tuple = ()


class IsolatedWorkerRegistry:
    """Operator-installed exact requests, never browser-selected paths or images."""
    def __init__(self, bindings):
        self.bindings={}
        for binding in bindings:
            require(isinstance(binding.process,IsolatedNativeProcess), 'isolated_worker_binding')
            key=(binding.scope,binding.request_digest,binding.process.tool)
            require(key not in self.bindings, 'isolated_worker_duplicate_binding')
            self.bindings[key]=binding

    def resolve(self, scope, request, kind):
        binding=self.bindings.get((scope,digest(request),kind))
        require(binding is not None, 'isolated_worker_not_installed')
        require(request['runtime_digest'] == binding.process.image.split('@')[1], 'isolated_worker_runtime_drift')
        process=copy(binding.process)
        if kind == 'terraform':
            return NativeTerraformWorker(process,process.workspace/'approved.tfplan',binding.configuration_files)
        return NativeHelmWorker(process,process.workspace/'chart',process.workspace/'values.json')


def main():
    """Read-only operator installation check; never issue a sandbox attestation."""
    import argparse
    import json
    import os
    import stat
    from .native_worker import file_bytes
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,required=True)
    args=parser.parse_args()
    require(sys.platform == 'linux', 'isolated_worker_linux_required')
    metadata=args.config.stat()
    require(metadata.st_uid in {0,os.getuid()} and not metadata.st_mode & (stat.S_IWGRP|stat.S_IWOTH),
            'isolated_worker_config_ownership')
    config=strict_json(file_bytes(args.config,16384))
    require(type(config) is dict and set(config) == {'docker_binary','docker_sha256','socket','workspace','image','tool'},
            'isolated_worker_config_fields')
    client=PinnedNativeProcess(config['docker_binary'],config['docker_sha256'],config['workspace'],
                               {'DOCKER_HOST':config['socket']})
    worker=IsolatedNativeProcess(client,config['image'],config['tool'])
    image_id=worker.preflight()
    print(json.dumps({'status':'PREFLIGHT_PASSED','image_id':image_id,
        'container_execution':'NOT_RUN','host_authority_binding':'NOT_RUN',
        'cloud_execution':'NOT_RUN','certification':'NOT_CERTIFIED'}))
    return 0


if __name__ == '__main__': raise SystemExit(main())
