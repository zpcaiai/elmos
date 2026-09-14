"""Fixed extension API bindings; browser input cannot supply leases or artifacts."""
from dataclasses import asdict
from .contracts import canonical, digest, identifier, require, sha
from .host_bridge import strict_json


class DeploymentExtensionService:
    KINDS=frozenset({'tls-rotate','iac-apply','iac-destroy','gitops-proposal','gitops-reconcile'})

    def __init__(self,journal,authority,content_store,tls,iac,gitops,tls_probe):
        self.journal,self.authority,self.content_store=journal,authority,content_store
        self.tls,self.iac,self.gitops,self.tls_probe=tls,iac,gitops,tls_probe

    def execute(self,principal,deployment_id,kind,body):
        require(kind in self.KINDS,'extension_not_supported')
        require(type(body) is dict and set(body)=={'plan','approval'},'extension_request_fields')
        require(type(body['plan']) is dict and 'scope' not in body['plan'],'client_scope_forbidden')
        identifier(deployment_id)
        action=kind.replace('-','.',1)
        principal.allow(action)
        deployment=self.journal.load(principal.scope,deployment_id)
        require(deployment['active']==1,'extension_deployment_not_active')
        allowed_states = ({'REQUESTED','POLICY_CHECKED','PREFLIGHT'} if kind.startswith('iac-') else
                          {'TRAFFIC_PROMOTION'} if kind=='tls-rotate' else {'DEPLOYING'})
        require(deployment['state'] in allowed_states,'extension_phase_mismatch')
        plan={**body['plan'],'scope':asdict(principal.scope)}
        if kind=='tls-rotate':
            resources=(plan['listener_id'],plan['load_balancer_id'],plan['after_certificate_id'])
        elif kind.startswith('iac-'):
            require(plan.get('mode')==kind[4:],'extension_mode_mismatch')
            resources=tuple(plan['expected_resources'])
        else:
            require(plan.get('mode')==kind[7:],'extension_mode_mismatch')
            resources=(plan['repository_id'],plan['application_id'])
        require(0<len(resources)<=100 and all(type(r) is str and 0<len(r)<=256 for r in resources),
                'extension_resources')
        # Generation is the durable deployment CAS version, never an HTTP field.
        lease=self.authority.lease(principal,deployment_id,digest(deployment['plan']),resources,
                                   action,deployment['version'])
        if kind=='tls-rotate':
            raw=self._read(principal.scope,plan['certificate_digest'],65536)
            return self.tls.rotate(plan,body['approval'],lease,raw,self.tls_probe)
        if kind.startswith('iac-'):
            return self.iac.execute(plan,body['approval'],lease)
        manifests=strict_json(self._read(principal.scope,plan['manifest_digest'],1048576))
        return self.gitops.publish(plan,manifests,body['approval'],lease)

    def _read(self,scope,key,limit):
        sha(key)
        raw=self.content_store.read(scope,key)
        require(type(raw) is bytes and len(raw)<=limit and digest(raw)==key,'extension_content_binding')
        return raw
