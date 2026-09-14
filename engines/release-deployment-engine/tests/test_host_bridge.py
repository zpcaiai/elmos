import base64
from dataclasses import asdict
import io
import json
from pathlib import Path
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from elmos_release_deployment.host_bridge import ReplayStore, SignedHostAuthenticator
from elmos_release_deployment.contracts import Scope, Denied, digest


class HostBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.key = Ed25519PrivateKey.generate()
        self.scope = Scope('tenant', 'workspace', 'project', 'test', 'account')
        self.auth = SignedHostAuthenticator({'host': (self.key.public_key().public_bytes_raw(), {self.scope.key})},
                    ReplayStore(Path(self.tmp.name) / 'replay.db'), 'worker', lambda: 100)

    def request(self, **overrides):
        body = b'{"value":1}'
        claim = dict(audience='worker', nonce='nonce', issued_at=95, expires_at=125,
                     method='POST', path='/v1/deployments', body_digest=digest(body),
                     actor_id='actor', scope=asdict(self.scope), permissions=['deployment:apply'])
        claim.update(overrides)
        raw = json.dumps(claim, ensure_ascii=False).encode()
        encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip('=')
        token = 'host.' + encode(raw) + '.' + encode(self.key.sign(b'elmos-deployment-host-v1\0' + raw))
        return dict(HTTP_X_ELMOS_HOST_AUTH=token, REQUEST_METHOD='POST', PATH_INFO='/v1/deployments',
                    CONTENT_LENGTH=str(len(body)), **{'wsgi.input': io.BytesIO(body)})

    def test_authenticates_and_preserves_exact_body(self):
        request = self.request()
        principal = self.auth(request)
        self.assertEqual(principal.scope, self.scope)
        principal.allow('deployment:apply')
        self.assertEqual(request['wsgi.input'].read(), b'{"value":1}')

    def test_replay_is_persistent_across_authenticator_instances(self):
        self.auth(self.request())
        auth = SignedHostAuthenticator(self.auth.keys, ReplayStore(Path(self.tmp.name) / 'replay.db'),
                                       'worker', lambda: 100)
        with self.assertRaisesRegex(Denied, 'replayed'):
            auth(self.request())

    def test_rejects_expiry_audience_scope_and_route_substitution(self):
        for override in ({'expires_at':100}, {'issued_at':101}, {'expires_at':200},
                         {'audience':'other'}, {'scope':{**asdict(self.scope),'tenant_id':'other'}},
                         {'path':'/v1/releases'}, {'method':'GET'}, {'body_digest':digest(b'other')}):
            with self.subTest(override=override), self.assertRaises(Denied):
                self.auth(self.request(**override))

    def test_rejects_unsigned_identity_and_transfer_encoding(self):
        request = self.request()
        request['HTTP_TRANSFER_ENCODING'] = 'chunked'
        with self.assertRaises(Denied):
            self.auth(request)
        request = self.request()
        request['HTTP_X_ELMOS_HOST_AUTH'] = ''
        request['HTTP_X_TENANT_ID'] = 'tenant'
        with self.assertRaises(Denied):
            self.auth(request)


if __name__ == '__main__':
    unittest.main()
