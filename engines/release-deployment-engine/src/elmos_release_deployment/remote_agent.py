"""Installed deterministic Docker agent for a dedicated Linux deployment user.

Trust/config roots are host provisioned; source bundles cannot select commands,
filesystem roots, cloud accounts, public keys or Docker flags. The CLI has no
bootstrap/install/network-credential functionality.
"""
from __future__ import annotations
import argparse
import base64
from contextlib import contextmanager
from dataclasses import asdict
import http.client
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import time
from .adapters import DockerHostRuntime, HealthVerifier
from .contracts import Artifact, Denied, canonical, digest, require, sha


class Ed25519Trust:
    """Verifier-only pinned public-key ring; signing is a separate host authority."""
    def __init__(self, keys, revoked=()):
        self.keys=dict(keys)
        self.revoked=frozenset(revoked)

    def verify(self, purpose, body, signature):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        try:
            key_id, encoded=signature.split(':',1)
            if key_id not in self.keys or key_id in self.revoked:
                return False
            key=Ed25519PublicKey.from_public_bytes(base64.b64decode(self.keys[key_id],validate=True))
            key.verify(base64.b64decode(encoded,validate=True),purpose.encode()+b'\x00'+canonical(body))
            return True
        except Exception:
            return False


def read_owned(path: Path, max_bytes, *, owner_uid=None):
    """Reject links, non-regular files and group/world-writable trust material."""
    require(not path.is_symlink() and all(not parent.is_symlink() for parent in path.parents), 'agent_path_symlink')
    flags=os.O_RDONLY | getattr(os,'O_NOFOLLOW',0)
    fd=os.open(path,flags)
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size<=max_bytes,'agent_file_bounds')
        if os.name=='posix':
            require(not info.st_mode & 0o022 and (owner_uid is None or info.st_uid==owner_uid), 'agent_file_permissions')
        with os.fdopen(fd,'rb',closefd=False) as stream:
            return stream.read(max_bytes+1)
    finally:
        os.close(fd)


class RemoteAgent:
    def __init__(self, root, trust, host_scope, instance_id, clock=time.time, runner=None):
        self.root=Path(root).resolve()
        require(self.root.is_dir(),'agent_root_not_provisioned')
        self.trust,self.scope,self.instance_id,self.clock=trust,host_scope,instance_id,clock
        self.runner=runner or self._run
        self.database=self.root/'agent-journal.sqlite3'
        require(not self.database.is_symlink(),'agent_journal_symlink')
        with self.connection() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.executescript('''CREATE TABLE IF NOT EXISTS operations(
                key TEXT PRIMARY KEY, permit_digest TEXT NOT NULL, target TEXT NOT NULL,
                fence INTEGER NOT NULL, state TEXT NOT NULL, result BLOB);
                CREATE TABLE IF NOT EXISTS fences(target TEXT PRIMARY KEY, fence INTEGER NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS active_remote_target ON operations(target) WHERE state='DISPATCHING';''')

    @contextmanager
    def connection(self, isolation_level='DEFERRED'):
        connection=sqlite3.connect(self.database,isolation_level=isolation_level)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _run(argv, timeout):
        # Never collect application stdout/stderr in this process or evidence.
        result=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL,timeout=timeout,check=False,shell=False)
        return result.returncode

    def validate(self, envelope, expected_operation, action):
        require(type(envelope) is dict and set(envelope)=={'body','signature'},'remote_signed_permit_required')
        body=envelope['body']
        require(self.trust.verify('remote_permit',body,envelope['signature']),'remote_signature_invalid')
        require(set(body)=={'scope','instance_id','operation_key','action','expires_at','issued_at','fence',
                           'target_id','project_name','artifacts','config_digest','secret_refs','compose_digest','probes'},
                'remote_permit_fields')
        require(body['scope']==self.scope and body['instance_id']==self.instance_id,'remote_resource_fence')
        require(body['operation_key']==expected_operation and body['action']==action,'remote_operation_binding')
        require(type(body['issued_at']) is int and type(body['expires_at']) is int and
                body['issued_at']<=self.clock()<body['expires_at']<=body['issued_at']+600,'remote_permit_expired')
        require(type(body['fence']) is int and body['fence']>0,'remote_generation')
        sha(body['operation_key']); sha(body['compose_digest']); sha(body['config_digest'])
        artifacts=tuple(Artifact(**a) for a in body['artifacts'])
        rendered=DockerHostRuntime.compose(artifacts,body['config_digest'],tuple(body['secret_refs']),digest(body['scope']))
        require(digest(rendered)==body['compose_digest'],'remote_compose_not_canonical')
        manifest=self.root/'bundles'/(body['compose_digest'][7:]+'.json')
        require(read_owned(manifest,1_000_000)==rendered,'remote_bundle_integrity')
        config=self.root/'config'/body['config_digest'][7:]
        require(digest(read_owned(config,1_000_000))==body['config_digest'],'remote_config_integrity')
        require(type(body['probes']) is list and 0<len(body['probes'])<=100,'remote_probe_bounds')
        require(len({p.get('id') for p in body['probes']})==len(body['probes']),'remote_duplicate_probe')
        DockerHostRuntime.argv(body['compose_digest'],body['project_name'],
                               'cleanup' if action=='cleanup' else 'apply')
        for probe in body['probes']:
            require(set(probe)=={'id','port','path','status','body_digest'} and
                    type(probe['port']) is int and probe['port'] in {a.port for a in artifacts},'remote_probe_contract')
            require(type(probe['path']) is str and probe['path'].startswith('/') and len(probe['path'])<=2048
                    and '\r' not in probe['path'] and '\n' not in probe['path'],'remote_probe_path')
            require(type(probe['status']) is int and 200<=probe['status']<300,'remote_probe_status')
            if probe['body_digest'] is not None: sha(probe['body_digest'])
        return body

    def execute(self, envelope, expected_operation, action):
        require(action in {'apply','restore','verify','preflight','cleanup'},'remote_action_not_allowed')
        body=self.validate(envelope,expected_operation,action)
        permit_digest=digest(envelope)
        with self.connection(isolation_level=None) as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT permit_digest,state,result FROM operations WHERE key=?',(expected_operation,)).fetchone()
            if old:
                require(old[0]==permit_digest,'remote_idempotency_conflict')
                c.commit()
                return json.loads(old[2]) if old[1]=='COMPLETE' else {'status':'UNKNOWN','operation_key':expected_operation}
            previous=c.execute('SELECT fence FROM fences WHERE target=?',(self.instance_id,)).fetchone()
            require(previous is None or body['fence']>previous[0],'remote_stale_fence')
            try:
                c.execute('INSERT INTO operations VALUES(?,?,?,?,?,NULL)',
                          (expected_operation,permit_digest,self.instance_id,body['fence'],'DISPATCHING'))
            except sqlite3.IntegrityError:
                raise Denied('remote_unreconciled_target') from None
            c.execute('INSERT INTO fences VALUES(?,?) ON CONFLICT(target) DO UPDATE SET fence=excluded.fence',
                      (self.instance_id,body['fence']))
            c.commit()
        # Crash here leaves DISPATCHING. Neither a new operation nor a replay
        # can touch this target until the host reconciles the recorded intent.
        if action in {'apply','restore','cleanup'}:
            args=DockerHostRuntime.argv(body['compose_digest'],body['project_name'],'cleanup' if action=='cleanup' else 'apply')
            # Runtime paths are fixed for the deployed agent, tests inject runner.
            try:
                timeout=min(120,body['expires_at']-int(self.clock()))
                require(timeout>0,'remote_permit_expired')
                exit_code=self.runner(args,timeout)
                require(type(exit_code) is int,'invalid_runtime_exit_code')
            except Exception:
                return {'status':'UNKNOWN','operation_key':expected_operation}
            results={}
        elif action=='preflight':
            import shutil
            available=shutil.disk_usage(self.root).free
            exit_code=0 if available>=1024*1024*1024 else 1
            results={'disk':'PASS' if exit_code==0 else 'FAIL'}
        else:
            def probe(case,timeout):
                spec=next(p for p in body['probes'] if p['id']==case)
                connection=http.client.HTTPConnection('127.0.0.1',spec['port'],timeout=min(timeout,10))
                try:
                    connection.request('GET',spec['path'])
                    response=connection.getresponse(); content=response.read(1_000_001)
                    return 'PASS' if (response.status==spec['status'] and len(content)<=1_000_000 and
                        (spec['body_digest'] is None or digest(content)==spec['body_digest'])) else 'FAIL'
                finally:
                    connection.close()
            remaining=min(120,body['expires_at']-int(self.clock()))
            require(remaining>0,'remote_permit_expired')
            results=HealthVerifier(probe,self.clock,time.sleep).verify([p['id'] for p in body['probes']],deadline_seconds=remaining)
            exit_code=0 if all(v=='PASS' for v in results.values()) else 1
        result={'status':'PASS' if exit_code==0 else 'FAIL','operation_key':expected_operation,
                'exit_code':exit_code,'compose_digest':body['compose_digest'],'config_digest':body['config_digest'],
                'probes':results,'finished_at':int(self.clock())}
        with self.connection() as c:
            c.execute('UPDATE operations SET state=?,result=? WHERE key=?',('COMPLETE',canonical(result),expected_operation))
        return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['apply','restore','verify','preflight','cleanup'])
    parser.add_argument('--bundle',required=True)
    parser.add_argument('--operation',required=True)
    args=parser.parse_args()
    try:
        require(os.name=='posix','linux_deployment_agent_required')
        sha(args.bundle); sha(args.operation)
        config=json.loads(read_owned(Path('/etc/elmos/deployment-trust.json'),65536,owner_uid=0))
        require(set(config)=={'keys','revoked_keys','scope','instance_id'},'agent_trust_config_fields')
        root=Path('/var/lib/elmos')
        raw=read_owned(root/'permits'/(args.bundle[7:]+'.json'),262144)
        require(digest(raw)==args.bundle,'remote_permit_digest')
        agent=RemoteAgent(root,Ed25519Trust(config['keys'],config['revoked_keys']),config['scope'],config['instance_id'])
        result=agent.execute(json.loads(raw),args.operation,args.action)
        print(canonical(result).decode())
        return 0 if result['status']=='PASS' else 1
    except Exception:
        print('{"status":"DENIED","error":"remote_execution_not_authorized_or_reconciled"}')
        return 1


if __name__=='__main__': raise SystemExit(main())
