"""AssumeRole provider over bounded HTTPS and host-owned credential storage.

Bootstrap credentials come from the installed cloud connection broker. No default
credential chain, long-lived key file, environment lookup or automatic retry.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import re

from .alibaba_rpc import AlibabaRpcTransport, StsSession
from .contracts import Scope, canonical, digest, require


class AssumeRoleHttps(AlibabaRpcTransport):
    ACTIONS = {('sts','2015-04-01'):frozenset({'AssumeRole'})}


@dataclass(frozen=True)
class RoleGrant:
    scope: Scope
    lease_id: str
    generation: int
    session_identity: str
    request_digest: str
    cloud_account_id: str
    role_name: str
    actions: tuple[str, ...]
    resources: tuple[str, ...]
    expires_at: int

    def policy(self):
        require(re.fullmatch(r'[0-9]{1,32}',self.cloud_account_id) is not None, 'sts_account')
        require(re.fullmatch(r'[a-zA-Z0-9.@_-]{1,64}',self.role_name) is not None, 'sts_role')
        require(0 < len(self.actions) <= 30 and len(set(self.actions)) == len(self.actions)
                and all(re.fullmatch(r'[a-z]+:[A-Za-z][A-Za-z0-9]+',a) for a in self.actions), 'sts_exact_actions')
        require(0 < len(self.resources) <= 100 and len(set(self.resources)) == len(self.resources)
                and all(type(r) is str and r.startswith('acs:') and '*' not in r and '?' not in r
                        and len(r) <= 512 for r in self.resources), 'sts_exact_resources')
        policy={'Version':'1','Statement':[{'Effect':'Allow','Action':sorted(self.actions),
                                          'Resource':sorted(self.resources)}]}
        require(len(canonical(policy)) <= 2048, 'sts_policy_bounds')
        return policy


class AlibabaStsProvider:
    """Uses canonical host authority, durable credential claims and secret storage.

    store.claim must durably fence the exact lease/request before issuing. An
    ambiguous claim or AssumeRole result cannot be retried by this adapter.
    store.read returns a session only for that scope/lease/request; store.save
    writes credentials to the canonical secret service, not the deployment journal.
    """
    def __init__(self, transport, authority, store, audit, clock):
        require(isinstance(transport,AssumeRoleHttps), 'sts_fixed_transport')
        self.transport,self.authority,self.store,self.audit,self.clock=transport,authority,store,audit,clock

    def authorize_call(self, lease, request):
        now=int(self.clock())
        require(now < lease.expires_at, 'lease_expired')
        grant=self.authority.require_role(lease,request)
        require(isinstance(grant,RoleGrant) and grant.scope == lease.scope
                and grant.lease_id == lease.lease_id and grant.generation == lease.generation
                and grant.session_identity == lease.session_identity and grant.request_digest == digest(request)
                and grant.cloud_account_id == request.get('cloud_account_id')
                and grant.cloud_account_id == self.transport.account
                and request.get('region') == self.transport.region
                and now < grant.expires_at <= lease.expires_at, 'sts_grant_binding')
        policy=grant.policy()
        action=request.get('service','')+':'+request.get('action','')
        require(action in grant.actions, 'sts_call_action')
        binding=digest({'scope':lease.scope.key,'lease':lease.lease_id,'generation':lease.generation,
                        'request':digest(request),'policy':policy,'role':grant.role_name})
        existing=self.store.read(lease.scope,lease.lease_id,binding)
        if existing is not None:
            self._session(existing,lease,now)
            return existing
        # The canonical credential ledger owns retries/reconciliation; never use
        # an in-memory cache as dispatch authority for token issuance.
        require(self.store.claim(lease.scope,lease.lease_id,binding) is True, 'sts_issuance_not_claimed')
        session_name='elmos-'+binding[7:39]
        result=self.transport.call('sts','2015-04-01','AssumeRole',{
            'RoleArn':'acs:ram::'+grant.cloud_account_id+':role/'+grant.role_name,
            'RoleSessionName':session_name,'Policy':canonical(policy).decode(),'DurationSeconds':900},lease)
        user=result.get('AssumedRoleUser',{})
        expected='acs:ram::'+grant.cloud_account_id+':role/'+grant.role_name+'/'+session_name
        require(user.get('Arn') == expected, 'sts_assumed_identity')
        credentials=result.get('Credentials',{})
        expiration=credentials.get('Expiration')
        require(type(expiration) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',expiration),
                'sts_expiration_format')
        expires=int(datetime.strptime(expiration,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp())
        require(now < expires <= int(self.clock())+930, 'sts_provider_lifetime')
        session=StsSession(credentials.get('AccessKeyId'),credentials.get('AccessKeySecret'),
                           credentials.get('SecurityToken'),grant.cloud_account_id,lease.session_identity,expires)
        self._session(session,lease,int(self.clock()))
        # Re-check current revocation before publishing a newly obtained token.
        require(self.authority.require_role(lease,request) == grant and int(self.clock()) < grant.expires_at,
                'sts_grant_revoked_during_issue')
        self.store.save(lease.scope,lease.lease_id,binding,session)
        require(self.store.read(lease.scope,lease.lease_id,binding) == session, 'sts_secret_store_readback')
        self.audit.record(lease.scope,lease.lease_id,{'operation':'sts.AssumeRole','binding':binding,
            'request_id':result.get('RequestId'),'expires_at':expires,'cloud_token_revoked':False})
        return session

    def _session(self, session, lease, now):
        require(isinstance(session,StsSession) and session.account_id == self.transport.account
                and session.session_identity == lease.session_identity and now < session.expires_at
                and now < lease.expires_at and all(type(v) is str and 0 < len(v) <= 16384
                    for v in (session.access_key_id,session.access_key_secret,session.security_token)), 'sts_session_binding')

    def record_response(self, lease, request_digest, response_digest, request_id):
        require(int(self.clock()) < lease.expires_at, 'lease_expired')
        self.audit.record(lease.scope,lease.lease_id,{'operation':'cloud.response','request_digest':request_digest,
            'response_digest':response_digest,'request_id':request_id})
