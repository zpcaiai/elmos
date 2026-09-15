from dataclasses import asdict
from pathlib import Path
import socket
import ssl
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from elmos_release_deployment.contracts import Scope, CapabilityLease, Denied, digest
from elmos_release_deployment.connected_native_worker import ConnectedTerraformProcess, NetworkPolicy
from elmos_release_deployment.egress_proxy import EgressProxy, client_hello_name
from elmos_release_deployment.journal import Journal
from elmos_release_deployment.native_cleanup import NativeCleanupJournal
from elmos_release_deployment.native_worker import ProcessResult
from test_isolated_native_worker import DockerFixture


def hello(host):
    incoming,outgoing=ssl.MemoryBIO(),ssl.MemoryBIO()
    engine=ssl.create_default_context().wrap_bio(incoming,outgoing,server_hostname=host)
    try: engine.do_handshake()
    except ssl.SSLWantReadError: pass
    return outgoing.read()


class EgressTests(unittest.TestCase):
    def test_real_tls_client_hello_and_malformed_records(self):
        packet=hello('approved.example')
        self.assertEqual('approved.example',client_hello_name(packet))
        for bad in (packet[:4],packet[:-1],b'GET / HTTP/1.1\r\n'):
            with self.assertRaises(Denied): client_hello_name(bad)

    def test_private_metadata_endpoint_cannot_be_configured(self):
        for address in ('127.0.0.1','100.100.100.200','169.254.169.254','::1','239.1.1.1'):
            with self.assertRaises(Denied): EgressProxy(('127.0.0.1',0),{'approved.example':address},lambda:None)

    def test_actual_loopback_proxy_denies_host_and_sni_before_upstream(self):
        with EgressProxy(('127.0.0.1',0),{'approved.example':'1.1.1.1'},lambda:None) as proxy:
            thread=threading.Thread(target=proxy.serve_forever,daemon=True); thread.start()
            try:
                with socket.create_connection(proxy.server_address,timeout=3) as client:
                    client.sendall(b'CONNECT forbidden.example:443 HTTP/1.1\r\n\r\n')
                    self.assertEqual(b'',client.recv(4096))
                with socket.create_connection(proxy.server_address,timeout=3) as client:
                    client.sendall(b'CONNECT approved.example:443 HTTP/1.1\r\n\r\n')
                    self.assertIn(b'200',client.recv(4096))
                    client.sendall(hello('other.example'))
                    self.assertEqual(b'',client.recv(4096))
            finally: proxy.shutdown(); thread.join(3)


class ConnectedTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.root=Path(temp.name)
        self.scope=Scope('t','w','p','e','a'); self.request={'runtime_digest':digest(b'image')}
        self.lifecycle=NativeCleanupJournal(Journal(self.root/'journal.db'),self.scope,digest(self.request),self)
        self.policy=NetworkPolicy('a'*64,'b'*64,'registry.example/proxy@'+digest(b'proxy'),'172.20.0.2',
            (('approved.example','1.1.1.1'),),'secret-ref:cloud/v1','deployment',165531)
        self.lease=CapabilityLease('lease',self.scope,'d',digest(b'plan'),(),frozenset({'iac.apply'}),1,200,'session')
        with patch('sys.platform','linux'):
            self.process=ConnectedTerraformProcess(DockerFixture(self.root),'registry.example/tool@'+digest(b'image'),
                self.policy,self.root/'credential',self,self.lifecycle,lambda *args:None)
        self.process.bind_invocation(self.request,self.lease)
        self.fenced=True

    def require_network(self,*args): pass
    def require_fenced_cleanup(self,*args):
        if not self.fenced: raise Denied('old_worker_not_fenced')

    def test_network_and_credential_options_are_fixed_and_values_never_in_argv(self):
        with patch('elmos_release_deployment.connected_native_worker.private_tmpfs_file') as file_check:
            options=self.process.extra_options()
        file_check.assert_called_once_with(self.root/'credential',165531)
        self.assertIn('--env=NO_PROXY=',options)
        self.assertIn('--env=ALIBABA_CLOUD_CREDENTIALS_FILE=/run/elmos/credentials.json',options)
        self.assertTrue(options[-1].endswith(',readonly'))

    def test_writable_or_wrong_secret_mount_rejected(self):
        for mount in ({'Destination':'/run/elmos/credentials.json','Type':'bind','Source':str(self.root/'credential'),'RW':True},
                      {'Destination':'/run/elmos/credentials.json','Type':'bind','Source':'/other','RW':False}):
            with self.assertRaises(Denied): self.process.verify_mounts([mount])

    def test_public_network_is_rejected(self):
        self.process._json=lambda argv:[{'Id':self.policy.network_id,'Driver':'bridge','Internal':False}]
        with patch('elmos_release_deployment.connected_native_worker.private_tmpfs_file'):
            with self.assertRaisesRegex(Denied,'not_internal'): self.process.network()

    def test_exact_network_proxy_and_policy_required(self):
        network={'Id':self.policy.network_id,'Driver':'bridge','Internal':True,'Containers':{
            self.policy.proxy_id:{'IPv4Address':self.policy.proxy_ip+'/24'}}}
        proxy={'Id':self.policy.proxy_id,'State':{'Running':True},'Config':{'Image':self.policy.proxy_image,
            'Labels':{'io.elmos.egress-policy':digest(asdict(self.policy))}}}
        self.process._json=lambda argv:[network if argv[0]=='network' else proxy]
        with patch('elmos_release_deployment.connected_native_worker.private_tmpfs_file'):
            self.assertEqual(self.policy.network_id,self.process.network())
            proxy['Config']['Labels']={}
            with self.assertRaises(Denied): self.process.network()

    def test_durable_restart_cleanup_requires_fencing_and_exact_identity(self):
        name='elmos-deployment-'+'c'*32
        self.lifecycle.prepare(name,self.process.image)
        restarted=NativeCleanupJournal(Journal(self.root/'journal.db'),self.scope,digest(self.request),self)
        self.assertEqual([name],restarted.pending())
        self.process._json=lambda argv:({'Names':name} if argv[1]=='ls' else [{'Config':{
            'Image':self.process.image,'Labels':self.lifecycle.labels}}])
        self.process.client.run=Mock(return_value=ProcessResult(0,b'',b''))
        self.fenced=False
        with self.assertRaises(Denied): restarted.reconcile(self.process,name)
        self.process.client.run.assert_not_called()
        self.fenced=True
        self.assertEqual('REMOVED_AFTER_FENCE',restarted.reconcile(self.process,name))
        self.assertIsNotNone(restarted.journal.get(self.scope,'native-sandbox-cleaned',name))
        self.assertEqual([],restarted.pending())

    def test_cleanup_never_removes_foreign_container(self):
        name='elmos-deployment-'+'d'*32; self.lifecycle.prepare(name,self.process.image)
        self.process._json=lambda argv:({'Names':name} if argv[1]=='ls' else [{'Config':{'Image':'wrong'}}])
        self.process.client.run=Mock()
        with self.assertRaises(Denied): self.lifecycle.reconcile(self.process,name)
        self.process.client.run.assert_not_called()
