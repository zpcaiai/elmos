"""Host-authorized Terraform on an internal network with a pinned egress gateway."""
from dataclasses import dataclass, asdict
import ipaddress
import os
from pathlib import Path
import re
import stat
from .contracts import digest, require
from .isolated_native_worker import IsolatedNativeProcess


@dataclass(frozen=True)
class NetworkPolicy:
    network_id: str
    proxy_id: str
    proxy_image: str
    proxy_ip: str
    endpoints: tuple[tuple[str,str], ...]
    secret_reference: str
    profile: str
    credential_owner_uid: int

    def validate(self):
        require(all(re.fullmatch(r'[0-9a-f]{64}',v) for v in (self.network_id,self.proxy_id)), 'network_exact_ids')
        require(re.fullmatch(r'[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}',self.proxy_image), 'network_proxy_image')
        ip=ipaddress.ip_address(self.proxy_ip)
        require(ip.version == 4 and any(ip in ipaddress.ip_network(cidr) for cidr in
            ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')), 'network_private_proxy')
        require(0 < len(self.endpoints) <= 64 and len(dict(self.endpoints)) == len(self.endpoints), 'network_endpoints')
        for host,ip in self.endpoints:
            address=ipaddress.ip_address(ip)
            require(re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,251}[a-z0-9]',host)
                    and address.is_global and not address.is_multicast and not address.is_reserved, 'network_public_pins')
        require(re.fullmatch(r'secret-ref:[A-Za-z0-9_.:/-]{1,200}',self.secret_reference)
                and re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',self.profile), 'network_secret_reference')
        require(type(self.credential_owner_uid) is int and self.credential_owner_uid > 0, 'network_credential_uid')


def private_tmpfs_file(path, owner_uid=None):
    path=Path(path)
    require(path.is_absolute() and not any(c in str(path) for c in ',\n\r\\'), 'network_secret_path')
    require(not path.is_symlink() and not any(p.is_symlink() for p in path.parents), 'network_secret_symlink')
    info=path.stat()
    require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o400 and info.st_nlink == 1
            and info.st_uid == (os.getuid() if owner_uid is None else owner_uid)
            and 0 < info.st_size <= 65536, 'network_secret_file_policy')
    root=path.parent.stat()
    require(root.st_uid == os.getuid() and stat.S_IMODE(root.st_mode) == 0o700, 'network_secret_root_policy')
    mounts=[]
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        left,right=line.split(' - ',1); mount=left.split()[4]
        if '\\' not in mount and path.is_relative_to(Path(mount)):
            mounts.append((len(mount),right.split()[0]))
    require(mounts and max(mounts)[1] == 'tmpfs', 'network_secret_not_tmpfs')


class ConnectedTerraformProcess(IsolatedNativeProcess):
    def __init__(self, client, image, policy, credential_path, authority, lifecycle, capture):
        require(isinstance(policy,NetworkPolicy) and lifecycle is not None and callable(capture), 'network_host_bindings')
        policy.validate()
        super().__init__(client,image,'terraform',capture=capture,lifecycle=lifecycle)
        self.policy,self.credential_path,self.authority=policy,Path(credential_path),authority
        self.invocation=None

    def bind_invocation(self, request, lease):
        require(lease.scope == self.lifecycle.scope and digest(request) == self.lifecycle.request_digest, 'network_invocation_binding')
        self.invocation=(request,lease)

    def _authorize(self):
        require(self.invocation is not None, 'network_invocation_missing')
        request,lease=self.invocation
        self.authority.require_network(lease,request,self.policy,self.credential_path)
        private_tmpfs_file(self.credential_path,self.policy.credential_owner_uid)

    def network(self):
        self._authorize()
        network=self._json(['network','inspect',self.policy.network_id])[0]
        require(network.get('Id') == self.policy.network_id and network.get('Driver') == 'bridge'
                and network.get('Internal') is True and not network.get('Ingress'), 'network_not_internal')
        proxy=self._json(['container','inspect',self.policy.proxy_id])[0]
        require(proxy.get('Id') == self.policy.proxy_id and proxy.get('State',{}).get('Running') is True
                and proxy.get('Config',{}).get('Image') == self.policy.proxy_image
                and proxy.get('Config',{}).get('Labels',{}).get('io.elmos.egress-policy') == digest(asdict(self.policy)), 'network_proxy_binding')
        peers=network.get('Containers',{})
        require(self.policy.proxy_id in peers and peers[self.policy.proxy_id].get('IPv4Address','').split('/')[0]
                == self.policy.proxy_ip and len(peers) <= 2, 'network_peer_bounds')
        for peer in peers:
            if peer == self.policy.proxy_id: continue
            workload=self._json(['container','inspect',peer])[0]
            require(all(workload.get('Config',{}).get('Labels',{}).get(k) == v for k,v in self.lifecycle.labels.items()), 'network_foreign_workload')
        return self.policy.network_id

    def extra_options(self):
        self._authorize()
        proxy='http://'+self.policy.proxy_ip+':8080'
        return ['--env=HTTPS_PROXY='+proxy,'--env=HTTP_PROXY='+proxy,'--env=NO_PROXY=',
            '--env=ALIBABA_CLOUD_CREDENTIALS_FILE=/run/elmos/credentials.json',
            '--env=ALIBABA_CLOUD_PROFILE='+self.policy.profile,
            '--mount','type=bind,source='+str(self.credential_path)+',target=/run/elmos/credentials.json,readonly']

    def verify_mounts(self, mounts):
        secrets=[m for m in mounts if m.get('Destination') == '/run/elmos/credentials.json']
        require(len(secrets) == 1 and secrets[0].get('Type') == 'bind'
                and secrets[0].get('Source') == str(self.credential_path) and secrets[0].get('RW') is False, 'network_secret_mount_policy')
        super().verify_mounts([m for m in mounts if m not in secrets])

    def run(self, argv, timeout=60, limit=4194304):
        original=self.guard
        require(callable(original), 'network_guard_missing')
        def guard():
            original()
            self._authorize()
        self.guard=guard
        try: return super().run(argv,timeout,limit)
        finally: self.guard=original
