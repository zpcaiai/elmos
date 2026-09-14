import copy
from dataclasses import asdict, replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import unittest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from elmos_release_deployment.contracts import Scope, CapabilityLease, digest, Denied, Pending
from elmos_release_deployment.journal import Journal
from elmos_release_deployment.tls_controller import AlibabaTlsController, TlsProbe
from test_runtime import FixtureAuthority


class TlsControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.scope=Scope('t','w','p','e','a')
        self.journal=Journal(Path(self.tmp.name)/'db')
        self.journal.admit(self.scope,'deployment','key','ticket',{},('listener','lb','new-cert'),1)
        self.lease=CapabilityLease('lease',self.scope,'deployment',digest(b'plan'),('listener','lb','new-cert'),
                                  frozenset({'tls.rotate'}),0,1200,'session')
        self.authority=FixtureAuthority()
        self.observed={'ListenerId':'listener','LoadBalancerId':'lb','ListenerProtocol':'HTTPS',
                       'ListenerPort':443,'SecurityPolicyId':'policy','ListenerStatus':'Running',
                       'Certificates':[{'CertificateId':'old-cert'}]}
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'app.example.test')])
        cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
              .serial_number(1).not_valid_before(datetime.fromtimestamp(1,timezone.utc))
              .not_valid_after(datetime.fromtimestamp(2000,timezone.utc))
              .add_extension(x509.SubjectAlternativeName([x509.DNSName('app.example.test')]),False)
              .sign(key,hashes.SHA256()))
        self.der=cert.public_bytes(serialization.Encoding.DER)
        self.plan={'scope':asdict(self.scope),'listener_id':'listener','load_balancer_id':'lb',
                   'domain':'app.example.test','before_certificate_id':'old-cert','after_certificate_id':'new-cert',
                   'certificate_digest':digest(self.der),'invariant_digest':digest({k:v for k,v in self.observed.items()
                                                if k not in {'Certificates','ListenerStatus','RequestId'}})}
        self.approval=self.authority.seal('cloud_controller_approval',{'scope':asdict(self.scope),
            'region':'cn-shanghai','cloud_account_id':'123','deployment_id':'deployment',
            'deployment_plan_digest':self.lease.plan_digest,'operation_digest':digest(self.plan),
            'kind':'tls.rotate','generation':0,'expires_at':1100})
        self.controller=AlibabaTlsController(self.journal,self,self.authority,lambda:1000,self.scope,'cn-shanghai','123')
        self.calls=[]
        self.lost=False

    def call(self,service,version,action,parameters,lease):
        self.calls.append(action)
        if action=='UpdateListenerAttribute':
            self.assertEqual({'ListenerId','ClientToken','Certificates'},set(parameters))
            self.observed['Certificates']=parameters['Certificates']
            if self.lost: raise TimeoutError()
            return {'RequestId':'write'}
        return copy.deepcopy(self.observed)

    def verify(self,domain,certificate_digest):
        return {'domain':domain,'certificate_digest':certificate_digest,'chain_and_hostname_verified':True}

    def test_rotation_and_replay(self):
        result=self.controller.rotate(self.plan,self.approval,self.lease,self.der,self)
        self.assertEqual('PROVIDER_STATE_OBSERVED',result['status'])
        self.assertEqual(result,self.controller.rotate(self.plan,self.approval,self.lease,self.der,self))
        self.assertEqual(1,self.calls.count('UpdateListenerAttribute'))

    def test_security_policy_drift_blocks_write(self):
        self.observed['SecurityPolicyId']='weakened'
        with self.assertRaises(Denied): self.controller.rotate(self.plan,self.approval,self.lease,self.der,self)
        self.assertNotIn('UpdateListenerAttribute',self.calls)

    def test_lost_response_does_not_retry(self):
        self.lost=True
        with self.assertRaises(TimeoutError): self.controller.rotate(self.plan,self.approval,self.lease,self.der,self)
        with self.assertRaises(Pending): self.controller.rotate(self.plan,self.approval,self.lease,self.der,self)
        self.assertEqual(1,self.calls.count('UpdateListenerAttribute'))

    def test_wrong_certificate_bytes_never_call_provider(self):
        with self.assertRaises(Denied): self.controller.rotate(self.plan,self.approval,self.lease,b'wrong',self)
        self.assertEqual([],self.calls)


class LiveLocalTlsTests(unittest.TestCase):
    def test_actual_tls_handshake_checks_chain_hostname_and_leaf_digest(self):
        import socket, ssl, threading
        with tempfile.TemporaryDirectory() as directory:
            key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
            name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'local.example.test')])
            now=datetime.now(timezone.utc)
            cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(42).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(hours=1))
                .add_extension(x509.BasicConstraints(ca=True,path_length=None),True)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName('local.example.test')]),False)
                .sign(key,hashes.SHA256()))
            cert_path=Path(directory)/'cert.pem'
            key_path=Path(directory)/'key.pem'
            cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
                                                   serialization.NoEncryption()))
            server_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_context.num_tickets=0
            server_context.load_cert_chain(cert_path,key_path)
            client_context=ssl.create_default_context(cafile=str(cert_path))
            listener=socket.socket()
            listener.bind(('127.0.0.1',0))
            listener.listen(2)
            listener.settimeout(5)
            errors=[]
            def serve():
                try:
                    for _ in range(2):
                        stream,_=listener.accept()
                        try:
                            with stream:
                                with server_context.wrap_socket(stream,server_side=True) as secured:
                                    secured.settimeout(5)
                                    secured.recv(1)
                        except (ConnectionResetError,BrokenPipeError,ssl.SSLEOFError):
                            # A probe closes after verification without an HTTP request.
                            pass
                except Exception as error: errors.append(type(error).__name__)
                finally: listener.close()
            port=listener.getsockname()[1]
            thread=threading.Thread(target=serve,daemon=True)
            thread.start()
            probe=TlsProbe({'local.example.test':[{'ip':'127.0.0.1','port':port}]},client_context)
            try:
                result=probe.verify('local.example.test',digest(cert.public_bytes(serialization.Encoding.DER)))
                self.assertTrue(result['chain_and_hostname_verified'])
                with self.assertRaisesRegex(Denied,'peer_certificate'):
                    probe.verify('local.example.test',digest(b'wrong'))
            finally:
                thread.join(6)
            self.assertFalse(thread.is_alive())
            self.assertEqual([],errors)
