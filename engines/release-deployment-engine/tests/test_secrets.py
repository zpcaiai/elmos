from dataclasses import replace
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from elmos_release_deployment.contracts import *
from elmos_release_deployment.adapters import DockerHostRuntime
from elmos_release_deployment.secrets import SecretResolver, RedactingEvidenceCapture


class SecretsTest(unittest.TestCase):
    def test_scope_bound_immutable_secret_mounts(self):
        with tempfile.TemporaryDirectory() as temp:
            scope=Scope('tenant','workspace','project','prod','account')
            lease=CapabilityLease('lease',scope,'dep',digest(b'plan'),('instance',),frozenset({'secrets.resolve'}),1,100,'session')
            values={scope.key:b'tenant-a-secret'}
            resolver=SecretResolver(temp,lambda s,r,l:values[s.key],lambda:10)
            first=resolver.materialize(scope,('secret-ref:db/v1',),lease,'dep',lease.plan_digest,1)
            self.assertEqual(first,resolver.materialize(scope,('secret-ref:db/v1',),lease,'dep',lease.plan_digest,1))
            self.assertNotIn('tenant-a-secret',str(first))
            other=replace(scope,tenant_id='other'); values[other.key]=b'tenant-b-secret'
            second=resolver.materialize(other,('secret-ref:db/v1',),replace(lease,scope=other),'dep',lease.plan_digest,1)
            self.assertNotEqual(first[0]['mount_key'],second[0]['mount_key'])
            values[scope.key]=b'rotated-under-same-reference'
            with self.assertRaises(Denied): resolver.materialize(scope,('secret-ref:db/v1',),lease,'dep',lease.plan_digest,1)

    def test_logs_redact_raw_encoded_and_bearer_values_before_cas(self):
        scope=Scope('tenant','workspace','project','prod','account')
        secret=b'private-key-value'; blobs=[]
        def sink(scope,key,blob): blobs.append(blob); return 'cas:'+key
        capture=RedactingEvidenceCapture(sink,(secret,))
        receipt=capture.capture(scope,digest(b'op'),b'output '+secret+b' '+base64.b64encode(secret),b'Authorization: Bearer token-value')
        decoded=json.loads(blobs[0])
        for stream in ('stdout','stderr'):
            raw=base64.b64decode(decoded[stream])
            self.assertNotIn(secret,raw); self.assertNotIn(b'token-value',raw)
        self.assertEqual('cas:'+digest(blobs[0]),receipt['artifact_uri'])
        with self.assertRaises(Denied): capture.capture(scope,digest(b'op'),b'a'*1_000_001,b'')


if __name__=='__main__': unittest.main()
