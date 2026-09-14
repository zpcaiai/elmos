import copy
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ssl
import tempfile
import threading
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from elmos_release_deployment.argocd_adapter import ArgoApplicationBinding, ArgoCdAdapter, ArgoCdHttpsTransport
from elmos_release_deployment.contracts import Scope, CapabilityLease, Denied, Pending, canonical, digest
from test_runtime import FixtureAuthority


class ArgoTests(unittest.TestCase):
    def setUp(self):
        self.scope = Scope('t', 'w', 'p', 'e', 'a')
        self.lease = CapabilityLease('lease', self.scope, 'deployment', digest(b'plan'), ('repo', 'app'),
                                     frozenset({'gitops.reconcile'}), 0, 1200, 'session')
        spec = {'project': 'project', 'source': {'repoURL': 'https://github.com/example/test.git',
                'path': 'deploy/test', 'targetRevision': 'main'},
                'destination': {'server': 'https://kubernetes.default.svc', 'namespace': 'test'}}
        self.binding = ArgoApplicationBinding(self.scope, 'app', 'app', 'argocd', 'uid', 'repo',
                                              'project', digest(spec), ('test/Deployment/app',))
        resource = {'group': 'apps', 'kind': 'Deployment', 'namespace': 'test', 'name': 'app',
                    'status': 'Synced', 'health': {'status': 'Healthy'}}
        self.document = {'metadata': {'name': 'app', 'namespace': 'argocd', 'uid': 'uid'}, 'spec': spec,
            'status': {'reconciledAt': '1970-01-01T00:16:40Z', 'health': {'status': 'Healthy'},
                'sync': {'status': 'Synced', 'revision': 'a'*40, 'comparedTo': {
                    'source': copy.deepcopy(spec['source']), 'destination': copy.deepcopy(spec['destination'])}},
                'resources': [resource], 'operationState': {'phase': 'Succeeded', 'operation': {'sync': {}},
                    'syncResult': {'revision': 'a'*40, 'resources': [copy.deepcopy(resource)]}}}}
        self.calls = 0
        self.authority = FixtureAuthority()
        self.adapter = ArgoCdAdapter([self.binding], self, self.authority, lambda: 1000)

    def get_application(self, binding, lease):
        self.calls += 1
        return copy.deepcopy(self.document), digest(self.document)

    def test_exact_application_observation(self):
        receipt = self.adapter.observe('app', self.lease)
        self.assertTrue(self.authority.verify('gitops_runtime_receipt', receipt['body'], receipt['signature']))
        self.assertEqual(['test/Deployment/app'], receipt['body']['resources'])
        self.assertEqual(digest(self.document), receipt['body']['provider_observation_digest'])
        self.assertEqual('NOT_RUN', receipt['body']['independent_verification'])

    def test_cross_tenant_and_expired_lease_before_network(self):
        with self.assertRaises(Denied):
            self.adapter.observe('app', replace(self.lease, scope=replace(self.scope, tenant_id='other')))
        with self.assertRaises(Denied):
            self.adapter.observe('app', replace(self.lease, expires_at=999))
        self.assertEqual(0, self.calls)

    def test_identity_spec_and_compared_source_drift(self):
        original = copy.deepcopy(self.document)
        for mutate in (
            lambda d: d['metadata'].update(uid='replacement'),
            lambda d: d['spec']['destination'].update(namespace='other'),
            lambda d: d['status']['sync']['comparedTo']['source'].update(path='other'),
        ):
            with self.subTest(mutate=mutate):
                self.document = copy.deepcopy(original)
                mutate(self.document)
                with self.assertRaises(Denied): self.adapter.observe('app', self.lease)

    def test_stale_and_running_are_pending(self):
        self.document['status']['reconciledAt'] = '1970-01-01T00:00:01Z'
        with self.assertRaises(Pending): self.adapter.observe('app', self.lease)
        self.document['status']['reconciledAt'] = '1970-01-01T00:16:40Z'
        self.document['status']['operationState']['phase'] = 'Running'
        with self.assertRaises(Pending): self.adapter.observe('app', self.lease)

    def test_prune_partial_duplicate_and_resource_drift_rejected(self):
        original = copy.deepcopy(self.document)
        mutations = [
            lambda d: d['status']['operationState']['operation']['sync'].update(prune=True),
            lambda d: d['status']['operationState']['operation']['sync'].update(resources=[{'name': 'app'}]),
            lambda d: d['status']['resources'].append(copy.deepcopy(d['status']['resources'][0])),
            lambda d: d['status']['resources'][0].update(requiresPruning=True),
            lambda d: d['status']['operationState']['syncResult'].update(revision='b'*40),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.document = copy.deepcopy(original)
                mutate(self.document)
                with self.assertRaises(Denied): self.adapter.observe('app', self.lease)

    def test_real_https_transport_and_rejected_redirect(self):
        test = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                test.paths.append(self.path)
                test.assertEqual('Bearer ephemeral-test-token', self.headers['Authorization'])
                raw = canonical(test.document)
                self.send_response(test.http_status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Location', 'https://must-not-follow.invalid')
                self.end_headers()
                self.wfile.write(raw)
            def log_message(self, *args): pass
        self.paths, self.responses, self.http_status = [], [], 200
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
                .not_valid_after(now+timedelta(hours=1))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), False)
                .sign(key, hashes.SHA256()))
        with tempfile.TemporaryDirectory() as folder:
            ca, private = Path(folder)/'ca.pem', Path(folder)/'key.pem'
            ca.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            private.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(ca, private)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                transport = ArgoCdHttpsTransport('https://localhost:'+str(server.server_port), ca,
                                                'provider', self, lambda: 1000)
                adapter = ArgoCdAdapter([self.binding], transport, self.authority, lambda: 1000)
                self.assertEqual('a'*40, adapter.observe('app', self.lease)['body']['commit'])
                self.assertEqual(1, len(self.responses))
                self.http_status = 302
                with self.assertRaisesRegex(Denied, 'argocd_http_rejected'):
                    adapter.observe('app', self.lease)
                self.assertEqual(2, len(self.paths))
                self.assertEqual('/api/v1/applications/app?project=project&appNamespace=argocd', self.paths[0])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(5)

    def authorize_call(self, lease, request):
        self.assertEqual('GET', request['method'])
        return {'provider_id': 'provider', 'session_identity': 'session', 'expires_at': 1100,
                'token': 'ephemeral-test-token'}

    def record_response(self, *args): self.responses.append(args)
