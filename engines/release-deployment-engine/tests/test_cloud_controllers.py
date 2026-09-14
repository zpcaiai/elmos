from dataclasses import asdict, replace
from pathlib import Path
import tempfile
import unittest

from elmos_release_deployment.cloud_controllers import AlibabaCloudControllers
from elmos_release_deployment.contracts import Scope, CapabilityLease, digest, Pending, Denied
from elmos_release_deployment.journal import Journal
from test_runtime import FixtureAuthority


class CloudControllersTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.scope = Scope('tenant', 'workspace', 'project', 'env', 'account')
        self.journal = Journal(Path(self.tmp.name) / 'journal.db')
        self.journal.admit(self.scope, 'deployment', 'idem', 'ticket', {}, ('sgp-a','i-a','record'), 1)
        self.authority = FixtureAuthority()
        self.lease = CapabilityLease('lease', self.scope, 'deployment', digest(b'plan'),
                    ('sgp-a','i-a','record'), frozenset({'traffic.apply','dns.apply'}), 1, 1200, 'session')
        self.calls = []
        self.weight, self.pending, self.lose_response = 100, False, False
        self.controller = AlibabaCloudControllers(self.journal, self, self.authority, lambda:1000,
                                                   self.scope, 'cn-shanghai', '123')
        self.plan = {'scope':asdict(self.scope), 'server_group_id':'sgp-a',
                     'backends':[{'server_id':'i-a','port':8080,'before':100,'after':50}]}

    def approval(self, kind, plan):
        return self.authority.seal('cloud_controller_approval', {
            'scope':asdict(self.scope),'region':'cn-shanghai','cloud_account_id':'123',
            'deployment_id':'deployment','deployment_plan_digest':self.lease.plan_digest,
            'operation_digest':digest(plan),'kind':kind,'generation':1,'expires_at':1100})

    def call(self, service, version, action, parameters, lease):
        self.calls.append((action, parameters))
        if action == 'ListServerGroupServers':
            return {'RequestId':'read', 'Servers':[{'ServerId':'i-a','ServerType':'Ecs','Port':8080,
                     'Weight':self.weight,'Status':'Configuring' if self.pending else 'Available'}]}
        if action == 'UpdateServerGroupServersAttribute':
            self.weight = parameters['Servers'][0]['Weight']
            if self.lose_response:
                raise TimeoutError('simulated_response_loss')
            return {'RequestId':'write','JobId':'job'}
        if action == 'DescribeDomainRecordInfo':
            return {'RequestId':'read','RecordId':'record','DomainName':'example.test','RR':'www',
                    'Status':'ENABLE', **self.record}
        if action == 'UpdateDomainRecord':
            self.record = {key:parameters[key] for key in ('Type','Value','TTL','Line')}
            return {'RequestId':'write','RecordId':'record'}
        raise AssertionError(action)

    def test_alb_readback_and_replay_do_not_repeat_mutation(self):
        approval = self.approval('traffic.apply', self.plan)
        result = self.controller.traffic(self.plan, approval, self.lease)
        self.assertEqual('PROVIDER_STATE_OBSERVED', result['status'])
        self.assertEqual(result, self.controller.traffic(self.plan, approval, self.lease))
        self.assertEqual(1, sum(action == 'UpdateServerGroupServersAttribute' for action,_ in self.calls))

    def test_unknown_dispatch_never_resubmits_or_infers_success(self):
        self.lose_response = True
        approval = self.approval('traffic.apply', self.plan)
        with self.assertRaises(TimeoutError):
            self.controller.traffic(self.plan, approval, self.lease)
        with self.assertRaises(Pending):
            self.controller.traffic(self.plan, approval, self.lease)
        self.assertEqual(1, sum(action == 'UpdateServerGroupServersAttribute' for action,_ in self.calls))

    def test_wrong_before_image_prevents_mutation(self):
        self.weight = 60
        with self.assertRaisesRegex(Denied, 'before_image'):
            self.controller.traffic(self.plan, self.approval('traffic.apply', self.plan), self.lease)
        self.assertEqual(['ListServerGroupServers'], [action for action,_ in self.calls])

    def test_cross_scope_expired_and_missing_resource_denied_before_provider(self):
        for lease in (replace(self.lease, scope=replace(self.scope, tenant_id='other')),
                      replace(self.lease, expires_at=999), replace(self.lease, resources=('i-a',))):
            with self.subTest(lease=lease), self.assertRaises(Denied):
                self.controller.traffic(self.plan, self.approval('traffic.apply', self.plan), lease)
        self.assertEqual([], self.calls)

    def test_dns_exact_record_readback_and_explicit_compensation(self):
        self.record = {'Type':'A','Value':'192.0.2.1','TTL':600,'Line':'default'}
        plan = {'scope':asdict(self.scope),'record_id':'record','domain':'example.test','rr':'www',
                'before':dict(self.record),'after':{**self.record,'Value':'192.0.2.2'}}
        self.controller.dns(plan, self.approval('dns.apply', plan), self.lease)
        compensation = {**plan,'before':plan['after'],'after':plan['before']}
        self.controller.dns(compensation, self.approval('dns.apply', compensation), self.lease)
        self.assertEqual('192.0.2.1', self.record['Value'])
        self.assertEqual(2, sum(action == 'UpdateDomainRecord' for action,_ in self.calls))


if __name__ == '__main__': unittest.main()
