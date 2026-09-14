"""Bounded HTTPS RPC transport with host-scoped ephemeral STS credentials.

No environment credential chain, redirect, retry, arbitrary endpoint or logged
request body. The injected broker must verify/revoke leases and record canonical
dispatch authority before yielding credentials for this exact call.
"""
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import http.client
import time
import uuid
from urllib.parse import quote

from .contracts import Pending, digest, require
from .host_bridge import strict_json


@dataclass(frozen=True)
class StsSession:
    access_key_id: str = field(repr=False)
    access_key_secret: str = field(repr=False)
    security_token: str = field(repr=False)
    account_id: str
    session_identity: str
    expires_at: int


def encode_parameters(parameters):
    return '&'.join(quote(k, safe='~') + '=' + quote(v, safe='~') for k,v in sorted(parameters.items()))


def flatten(parameters, prefix=''):
    result = {}
    for key, value in parameters.items():
        name = prefix + key
        if isinstance(value, list):
            for index, item in enumerate(value, 1):
                if isinstance(item, dict):
                    result.update(flatten(item, name + '.' + str(index) + '.'))
                else:
                    result[name + '.' + str(index)] = str(item)
        elif type(value) is bool:
            result[name] = 'true' if value else 'false'
        elif type(value) in (str, int):
            result[name] = str(value)
        else:
            require(False, 'rpc_parameter_type')
    return result


class AlibabaRpcTransport:
    ACTIONS = {
        ('alb','2020-06-16'): frozenset({'ListServerGroupServers','UpdateServerGroupServersAttribute',
                                       'GetListenerAttribute','UpdateListenerAttribute'}),
        ('alidns','2015-01-09'): frozenset({'DescribeDomainRecordInfo','UpdateDomainRecord'}),
        ('ecs','2014-05-26'): frozenset({'DescribeInstances','DescribeCloudAssistantStatus','RunCommand',
                                       'DescribeInvocationResults','StopInvocation'}),
    }

    def __init__(self, region, cloud_account_id, credential_broker, clock=time.time):
        import re
        require(re.fullmatch(r'[a-z]{2}-[a-z]+-?\d*', region) is not None, 'rpc_region')
        require(re.fullmatch(r'[0-9]{1,32}', cloud_account_id) is not None, 'rpc_account')
        self.region, self.account, self.broker, self.clock = region, cloud_account_id, credential_broker, clock

    def call(self, service, version, action, parameters, lease):
        require(action in self.ACTIONS.get((service,version), ()), 'rpc_action_not_allowlisted')
        require(parameters.get('RegionId', self.region) == self.region, 'rpc_region_mismatch')
        now = int(self.clock())
        require(now < lease.expires_at, 'lease_expired')
        request_binding = {'service':service,'version':version,'action':action,'parameters':parameters,
                           'region':self.region,'cloud_account_id':self.account}
        # The canonical host resolves opaque session identity and exact action/resource permissions.
        session = self.broker.authorize_call(lease, request_binding)
        require(isinstance(session, StsSession) and session.account_id == self.account
                and session.session_identity == lease.session_identity and now < session.expires_at
                and all((session.access_key_id,session.access_key_secret,session.security_token)), 'rpc_session_binding')
        params = flatten(parameters)
        common = {'Action':action,'Version':version,'Format':'JSON','AccessKeyId':session.access_key_id,
                  'SecurityToken':session.security_token,'SignatureMethod':'HMAC-SHA1','SignatureVersion':'1.0',
                  'SignatureNonce':str(uuid.uuid4()),
                  'Timestamp':datetime.fromtimestamp(now,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
        require(not set(params) & set(common) and 'Signature' not in params, 'rpc_reserved_parameter')
        params.update(common)
        to_sign = 'POST&%2F&' + quote(encode_parameters(params), safe='~')
        params['Signature'] = base64.b64encode(hmac.new((session.access_key_secret+'&').encode(),
                                        to_sign.encode(), hashlib.sha1).digest()).decode()
        body = encode_parameters(params).encode()
        require(len(body) <= 262144, 'rpc_request_bounds')
        endpoint = 'alidns.aliyuncs.com' if service == 'alidns' else f'{service}.{self.region}.aliyuncs.com'
        connection = http.client.HTTPSConnection(endpoint, timeout=15)
        started = time.monotonic()
        try:
            connection.request('POST', '/', body, {'Content-Type':'application/x-www-form-urlencoded',
                                                  'Accept':'application/json','Accept-Encoding':'identity'})
            response = connection.getresponse()
            require(response.getheader('Content-Encoding', 'identity') == 'identity', 'rpc_response_encoding')
            raw = bytearray()
            while True:
                remaining = 15 - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError()
                if connection.sock:
                    connection.sock.settimeout(remaining)
                chunk = response.read1(min(65536, 1048577 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                require(len(raw) <= 1048576, 'rpc_response_bounds')
            if response.status != 200:
                # Do not expose provider messages, IDs, request parameters or credentials.
                raise Pending('rpc_provider_rejected_requires_reconciliation')
            result = strict_json(bytes(raw))
            require(type(result) is dict and 'Code' not in result, 'rpc_response_contract')
            self.broker.record_response(lease, digest(request_binding), digest(bytes(raw)), result.get('RequestId'))
            return result
        except (OSError, http.client.HTTPException) as error:
            raise Pending('rpc_outcome_unknown') from None
        finally:
            connection.close()
