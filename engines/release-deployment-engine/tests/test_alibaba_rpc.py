import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
from elmos_release_deployment.alibaba_rpc import AlibabaRpcTransport, StsSession, flatten
from elmos_release_deployment.contracts import CapabilityLease, Scope, digest, Denied, Pending


class RpcTests(unittest.TestCase):
    def setUp(self):
        self.lease = CapabilityLease('lease', Scope('t','w','p','e','a'), 'deploy', digest(b'plan'),
                                    ('i-a',), frozenset({'remote.poll'}), 1, 200, 'session')
        self.recorded = []
        self.transport = AlibabaRpcTransport('cn-shanghai', '123', self, lambda:100)

    def authorize_call(self, lease, request):
        self.assertEqual(self.lease, lease)
        return StsSession('test-id','test-secret','test-token','123','session',200)

    def record_response(self, *args):
        self.recorded.append(args)

    def test_request_uses_exact_https_endpoint_and_ephemeral_token(self):
        observed = {}
        class Connection:
            sock = None
            def __init__(self, endpoint, timeout): observed.update(endpoint=endpoint, timeout=timeout)
            def request(self, method, path, body, headers): observed.update(method=method,path=path,body=body)
            def getresponse(self):
                response = unittest.mock.Mock(status=200)
                response.getheader.return_value = 'identity'
                response.read1.side_effect = [b'{"RequestId":"request"}', b'']
                return response
            def close(self): observed['closed'] = True
        with patch('elmos_release_deployment.alibaba_rpc.http.client.HTTPSConnection', Connection):
            result = self.transport.call('ecs','2014-05-26','DescribeInvocationResults', {'RegionId':'cn-shanghai'},self.lease)
        self.assertEqual('request', result['RequestId'])
        self.assertEqual('ecs.cn-shanghai.aliyuncs.com', observed['endpoint'])
        params = parse_qs(observed['body'].decode())
        self.assertEqual(['test-token'], params['SecurityToken'])
        self.assertNotIn('test-secret', observed['body'].decode())
        self.assertTrue(observed['closed'])
        self.assertEqual(1,len(self.recorded))

    def test_unknown_action_and_region_never_open_connection(self):
        with patch('elmos_release_deployment.alibaba_rpc.http.client.HTTPSConnection') as connection:
            with self.assertRaises(Denied):
                self.transport.call('ecs','2014-05-26','DeleteInstance',{},self.lease)
            with self.assertRaises(Denied):
                self.transport.call('ecs','2014-05-26','DescribeInstances',{'RegionId':'us-east-1'},self.lease)
            connection.assert_not_called()

    def test_nested_backend_list_uses_rpc_indexed_fields(self):
        self.assertEqual({'Servers.1.ServerId':'i-a','Servers.1.Weight':'50','DryRun':'false'},
                         flatten({'Servers':[{'ServerId':'i-a','Weight':50}],'DryRun':False}))


if __name__ == '__main__': unittest.main()
