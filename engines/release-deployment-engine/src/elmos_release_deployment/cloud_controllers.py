"""Executable cloud controllers with durable dispatch and read-after-write checks.

Only host-injected transports perform provider calls. A response lost after send
remains UNKNOWN; observing a desired state alone cannot manufacture attribution.
Rollback is a separately approved operation with its own immutable before image.
"""
from dataclasses import asdict
import json

from .contracts import Pending, digest, identifier, require
from .service import verified


class AlibabaCloudControllers:
    def __init__(self, journal, transport, trust, clock, scope, region, cloud_account_id):
        self.journal, self.transport, self.trust, self.clock = journal, transport, trust, clock
        self.scope, self.region, self.account = scope, region, cloud_account_id

    def _authorize(self, kind, plan, approval, lease, resources):
        body = verified(self.trust, 'cloud_controller_approval', approval)
        require(body == {'scope': asdict(self.scope), 'region': self.region, 'cloud_account_id': self.account,
                         'deployment_id': lease.deployment_id, 'deployment_plan_digest': lease.plan_digest,
                         'operation_digest': digest(plan), 'kind': kind, 'generation': lease.generation,
                         'expires_at': body.get('expires_at')}, 'cloud_approval_binding')
        require(type(body['expires_at']) is int and self.clock() < body['expires_at'], 'cloud_approval_expired')
        lease.check(self.scope, lease.deployment_id, lease.plan_digest, resources,
                    kind, self.clock(), lease.generation)
        require(plan['scope'] == asdict(self.scope), 'cloud_plan_scope')
        return kind + ':' + digest(plan)[7:]

    def _step(self, operation, plan, lease):
        row, fresh = self.journal.begin_step(self.scope, lease.deployment_id, operation,
                                             plan, self.clock(), True)
        if row['status'] == 'COMPLETE':
            return row, fresh, json.loads(row['result'])
        return row, fresh, None

    def _finish(self, operation, plan, lease, invocation, observed):
        result = {'operation_digest': digest(plan), 'provider_request_id': invocation,
                  'observed_digest': digest(observed), 'scope': asdict(self.scope),
                  'region': self.region, 'cloud_account_id': self.account,
                  'status': 'PROVIDER_STATE_OBSERVED', 'certification': 'NOT_CERTIFIED'}
        self.journal.complete_step(self.scope, lease.deployment_id, operation, result, self.clock())
        return result

    def _alb_read(self, group, lease):
        result = self.transport.call('alb', '2020-06-16', 'ListServerGroupServers',
                                     {'ServerGroupId': group, 'MaxResults': 100}, lease)
        require(not result.get('NextToken'), 'alb_inventory_incomplete')
        servers = result.get('Servers')
        require(type(servers) is list and 0 < len(servers) <= 40, 'alb_backend_bounds')
        weights = {}
        for server in servers:
            require(server.get('ServerType') == 'Ecs' and type(server.get('Port')) is int,
                    'alb_backend_type')
            key = (server['ServerId'], server['Port'])
            require(key not in weights, 'alb_duplicate_backend')
            require(type(server.get('Weight')) is int and 0 <= server['Weight'] <= 100, 'alb_weight')
            weights[key] = (server['Weight'], server.get('Status'))
        return weights, result

    def traffic(self, plan, approval, lease):
        require(set(plan) == {'scope','server_group_id','backends'}, 'alb_plan_fields')
        identifier(plan['server_group_id'])
        backends = plan['backends']
        require(type(backends) is list and 0 < len(backends) <= 40, 'alb_backend_bounds')
        before, after = {}, {}
        for backend in backends:
            require(set(backend) == {'server_id','port','before','after'}, 'alb_backend_fields')
            identifier(backend['server_id'])
            require(type(backend['port']) is int and 1 <= backend['port'] <= 65535, 'alb_port')
            require(all(type(backend[k]) is int and 0 <= backend[k] <= 100 for k in ('before','after')), 'alb_weight')
            key = (backend['server_id'], backend['port'])
            require(key not in before, 'alb_duplicate_backend')
            before[key], after[key] = backend['before'], backend['after']
        require(sum(after.values()) > 0, 'alb_no_live_backend')
        resources = (plan['server_group_id'], *sorted({b['server_id'] for b in backends}))
        operation = self._authorize('traffic.apply', plan, approval, lease, resources)
        row, fresh, complete = self._step(operation, plan, lease)
        if complete is not None:
            return complete
        if fresh:
            observed, _ = self._alb_read(plan['server_group_id'], lease)
            require({k:v[0] for k,v in observed.items()} == before
                    and all(v[1] == 'Available' for v in observed.values()), 'alb_before_image_conflict')
            response = self.transport.call('alb', '2020-06-16', 'UpdateServerGroupServersAttribute',
                {'ServerGroupId': plan['server_group_id'], 'ClientToken': digest(plan)[7:],
                 'Servers': [{'ServerId': b['server_id'], 'ServerType':'Ecs', 'Port': b['port'],
                              'Weight': b['after']} for b in backends]}, lease)
            invocation = response.get('RequestId')
            identifier(invocation)
            self.journal.accepted(self.scope, lease.deployment_id, operation, invocation)
        else:
            invocation = row['invocation']
            if invocation is None:
                raise Pending('alb_dispatch_unknown_requires_host_reconciliation')
        observed, raw = self._alb_read(plan['server_group_id'], lease)
        require(set(observed) == set(after), 'alb_backend_drift')
        if any(observed[k] != (weight, 'Available') for k, weight in after.items()):
            raise Pending('alb_update_in_progress_or_drift')
        return self._finish(operation, plan, lease, invocation, raw)

    def dns(self, plan, approval, lease):
        require(set(plan) == {'scope','record_id','domain','rr','before','after'}, 'dns_plan_fields')
        identifier(plan['record_id'])
        import re
        import ipaddress
        require(re.fullmatch(r'[a-z0-9.-]{1,253}', plan['domain']) is not None
                and re.fullmatch(r'@|[a-z0-9_-]+(?:\.[a-z0-9_-]+)*', plan['rr']) is not None, 'dns_name')
        for record in (plan['before'], plan['after']):
            require(set(record) == {'Type','Value','TTL','Line'} and record['Type'] in {'A','AAAA','CNAME'}
                    and type(record['TTL']) is int and 30 <= record['TTL'] <= 86400
                    and record['Line'] == 'default', 'dns_record_contract')
            if record['Type'] in {'A','AAAA'}:
                require(ipaddress.ip_address(record['Value']).version == (4 if record['Type'] == 'A' else 6), 'dns_ip')
            else:
                require(re.fullmatch(r'[a-z0-9.-]{1,253}', record['Value']) is not None, 'dns_cname')
        operation = self._authorize('dns.apply', plan, approval, lease, (plan['record_id'],))
        row, fresh, complete = self._step(operation, plan, lease)
        if complete is not None:
            return complete
        def read():
            result = self.transport.call('alidns', '2015-01-09', 'DescribeDomainRecordInfo',
                                          {'RecordId':plan['record_id']}, lease)
            require(result.get('RecordId') == plan['record_id'] and result.get('DomainName') == plan['domain']
                    and result.get('RR') == plan['rr'] and result.get('Status') == 'ENABLE', 'dns_record_binding')
            return {k:result.get(k) for k in ('Type','Value','TTL','Line')}, result
        if fresh:
            observed, _ = read()
            require(observed == plan['before'], 'dns_before_image_conflict')
            response = self.transport.call('alidns', '2015-01-09', 'UpdateDomainRecord',
                    {'RecordId':plan['record_id'], 'RR':plan['rr'], **plan['after']}, lease)
            require(response.get('RecordId') == plan['record_id'], 'dns_update_binding')
            invocation = response.get('RequestId')
            identifier(invocation)
            self.journal.accepted(self.scope, lease.deployment_id, operation, invocation)
        else:
            invocation = row['invocation']
            if invocation is None:
                raise Pending('dns_dispatch_unknown_requires_host_reconciliation')
        observed, raw = read()
        if observed != plan['after']:
            raise Pending('dns_update_in_progress_or_drift')
        # API observation is not resolver convergence, TLS validity or application health.
        return self._finish(operation, plan, lease, invocation, raw)
