from dataclasses import replace
from datetime import datetime, timezone
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

from elmos_release_deployment.alibaba_sts import AlibabaStsProvider, AssumeRoleHttps, RoleGrant
from elmos_release_deployment.alibaba_rpc import StsSession
from elmos_release_deployment.contracts import CapabilityLease, Scope, Denied, Pending, canonical, digest


class StsTests(unittest.TestCase):
    def setUp(self):
        self.now=1800000000
        self.lease=CapabilityLease('lease',Scope('t','w','p','e','a'),'deployment',digest(b'plan'),
            ('i-a',),frozenset({'remote.poll'}),1,self.now+60,'session')
        self.request={'service':'ecs','version':'2014-05-26','action':'DescribeInstances',
            'parameters':{'InstanceIds':'["i-a"]'},'region':'cn-shanghai','cloud_account_id':'123'}
        self.grant=RoleGrant(self.lease.scope,'lease',1,'session',digest(self.request),'123','deployment-reader',
            ('ecs:DescribeInstances',),('acs:ecs:cn-shanghai:123:instance/i-a',),self.now+60)
        self.sessions={}; self.claims=set(); self.records=[]; self.requests=[]; self.revoked=False
        self.broker=AlibabaStsProvider(AssumeRoleHttps('cn-shanghai','123',self,lambda:self.now),
            self,self,self,lambda:self.now)

    def require_role(self,lease,request):
        if self.revoked: raise Denied('revoked')
        return self.grant
    def authorize_call(self,lease,request):
        return StsSession('bootstrap-id','bootstrap-secret','bootstrap-token','123','session',self.now+1200)
    def record_response(self,*args): pass
    def read(self,scope,lease,binding): return self.sessions.get((scope,lease,binding))
    def save(self,scope,lease,binding,session): self.sessions[scope,lease,binding]=session
    def claim(self,scope,lease,binding):
        key=(scope,lease,binding)
        if key in self.claims: return False
        self.claims.add(key); return True
    def record(self,*args): self.records.append(args)

    def connection(self, wrong_identity=False, fail=False):
        owner=self
        class Connection:
            sock=None
            def __init__(self,endpoint,timeout): owner.endpoint=endpoint
            def request(self,method,path,body,headers): owner.requests.append(parse_qs(body.decode()))
            def getresponse(self):
                if fail: raise OSError('fixture lost response')
                params=owner.requests[-1]
                result={'RequestId':'provider-request','AssumedRoleUser':{'Arn':
                    ('wrong' if wrong_identity else 'acs:ram::123:role/deployment-reader/'+params['RoleSessionName'][0])},
                    'Credentials':{'AccessKeyId':'issued-id','AccessKeySecret':'issued-secret','SecurityToken':'issued-token',
                        'Expiration':datetime.fromtimestamp(owner.now+900,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}}
                response=unittest.mock.Mock(status=200)
                response.getheader.return_value='identity'
                response.read1.side_effect=[canonical(result),b'']
                return response
            def close(self): pass
        return Connection

    def test_actual_transport_signs_and_binds_assume_role_without_secret_audit(self):
        with patch('elmos_release_deployment.alibaba_rpc.http.client.HTTPSConnection',self.connection()):
            session=self.broker.authorize_call(self.lease,self.request)
            self.assertEqual(session,self.broker.authorize_call(self.lease,self.request))
        self.assertEqual('sts.cn-shanghai.aliyuncs.com',self.endpoint)
        self.assertEqual(['900'],self.requests[0]['DurationSeconds'])
        self.assertEqual(1,len(self.requests))
        self.assertEqual(self.now+900,session.expires_at)
        self.assertNotIn('issued-token',repr(self.records))
        self.assertNotIn('issued-secret',repr(session))

    def test_revocation_blocks_cached_credentials(self):
        with patch('elmos_release_deployment.alibaba_rpc.http.client.HTTPSConnection',self.connection()):
            self.broker.authorize_call(self.lease,self.request)
        self.revoked=True
        with self.assertRaises(Denied): self.broker.authorize_call(self.lease,self.request)

    def test_unknown_issuance_cannot_issue_again(self):
        with patch('elmos_release_deployment.alibaba_rpc.http.client.HTTPSConnection',self.connection(fail=True)):
            with self.assertRaises(Pending): self.broker.authorize_call(self.lease,self.request)
            with self.assertRaisesRegex(Denied,'not_claimed'): self.broker.authorize_call(self.lease,self.request)
        self.assertEqual(1,len(self.requests))

    def test_wrong_provider_identity_never_saves_secret(self):
        with patch('elmos_release_deployment.alibaba_rpc.http.client.HTTPSConnection',self.connection(wrong_identity=True)):
            with self.assertRaisesRegex(Denied,'assumed_identity'): self.broker.authorize_call(self.lease,self.request)
        self.assertEqual({},self.sessions)

    def test_cross_scope_and_wildcard_grants_never_issue(self):
        original=self.grant
        for grant in (replace(original,lease_id='other'),replace(original,request_digest=digest(b'other')),
                      replace(original,resources=('*',)),replace(original,actions=('ecs:*',))):
            self.grant=grant
            with self.assertRaises(Denied): self.broker.authorize_call(self.lease,self.request)
        self.assertEqual([],self.requests)
