"""Flux v1 Kustomization + GitRepository observation through scoped Kubernetes HTTPS.

Only existing, non-pruning, wait-enabled Kustomizations with reconciliation
history are supported. This adapter never reconciles, patches or creates objects.
"""
from dataclasses import asdict, dataclass
from datetime import datetime
import http.client
import re
import time

from .contracts import Scope, Pending, digest, require, sha
from .host_bridge import strict_json
from .kubernetes_controller import KubernetesHttpsTransport


@dataclass(frozen=True)
class FluxBinding:
    scope: Scope
    application_id: str
    repository_id: str
    namespace: str
    name: str
    uid: str
    spec_digest: str
    source_name: str
    source_uid: str
    source_spec_digest: str
    resources: tuple[str, ...]

    def __post_init__(self):
        for value in (self.namespace, self.name, self.source_name):
            require(type(value) is str and re.fullmatch(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?', value)
                    and len(value) <= 63, 'flux_name')
        require(all(type(v) is str and 0 < len(v) <= 128 for v in
                    (self.application_id, self.repository_id, self.uid, self.source_uid)), 'flux_identity')
        sha(self.spec_digest); sha(self.source_spec_digest)
        require(type(self.resources) is tuple and 0 < len(self.resources) <= 100
                and len(set(self.resources)) == len(self.resources), 'flux_resources')
        for value in self.resources:
            require(re.fullmatch(r'[a-z0-9-]{1,63}/Deployment/[a-z0-9-]{1,63}', value), 'flux_resource')


class FluxHttpsTransport(KubernetesHttpsTransport):
    def read(self, binding, source, lease):
        lease.check(binding.scope, lease.deployment_id, lease.plan_digest,
                    (binding.application_id, binding.repository_id), 'gitops.reconcile', self.clock(), lease.generation)
        require(binding.namespace == self.namespace, 'flux_cluster_namespace')
        group, collection, name, kind = (
            ('source', 'gitrepositories', binding.source_name, 'GitRepository') if source else
            ('kustomize', 'kustomizations', binding.name, 'Kustomization'))
        path = f'/apis/{group}.toolkit.fluxcd.io/v1/namespaces/{binding.namespace}/{collection}/{name}'
        request = {'cluster_id': self.cluster, 'method': 'GET', 'path': path,
                   'binding_digest': digest(asdict(binding))}
        session = self.broker.authorize_call(lease, request)
        require(type(session) is dict and set(session) == {'token','expires_at','session_identity','cluster_id'}
                and session['cluster_id'] == self.cluster and session['session_identity'] == lease.session_identity
                and type(session['expires_at']) is int and self.clock() < session['expires_at']
                and type(session['token']) is str and re.fullmatch(r'[!-~]{1,16384}', session['token']), 'flux_session')
        connection = http.client.HTTPSConnection(self.host, self.port, context=self.context, timeout=15)
        started = time.monotonic()
        try:
            connection.request('GET', path, headers={'Authorization': 'Bearer '+session['token'],
                'Accept': 'application/json', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            require(response.status == 200 and response.getheader('Content-Encoding','identity') == 'identity',
                    'flux_http_rejected')
            raw = bytearray()
            while True:
                remaining = 15-(time.monotonic()-started)
                if remaining <= 0: raise TimeoutError()
                if connection.sock: connection.sock.settimeout(remaining)
                chunk = response.read1(min(65536, 1048577-len(raw)))
                if not chunk: break
                raw.extend(chunk)
                require(len(raw) <= 1048576, 'flux_response_bounds')
            result = strict_json(bytes(raw))
            require(type(result) is dict and result.get('kind') == kind
                    and result.get('apiVersion') == group+'.toolkit.fluxcd.io/v1', 'flux_api_kind')
            self.broker.record_response(lease, digest(request), digest(bytes(raw)), result.get('metadata',{}).get('uid'))
            return result
        except (OSError, http.client.HTTPException):
            raise Pending('flux_observation_unavailable') from None
        finally:
            connection.close()


class FluxAdapter:
    def __init__(self, bindings, transport, signer, clock=time.time):
        bindings = tuple(bindings)
        self.bindings = {(b.scope.key,b.application_id):b for b in bindings}
        require(len(self.bindings) == len(bindings), 'flux_duplicate_binding')
        self.transport,self.signer,self.clock = transport,signer,clock

    def observe(self, application_id, lease):
        b = self.bindings.get((lease.scope.key,application_id))
        require(b is not None, 'flux_application_not_bound')
        lease.check(b.scope,lease.deployment_id,lease.plan_digest,(b.application_id,b.repository_id),
                    'gitops.reconcile',self.clock(),lease.generation)
        app = self.transport.read(b,False,lease)
        source = self.transport.read(b,True,lease)
        for obj,name,uid,expected in ((app,b.name,b.uid,b.spec_digest),
                                      (source,b.source_name,b.source_uid,b.source_spec_digest)):
            meta,spec,status = (obj.get(k,{}) for k in ('metadata','spec','status'))
            require(all(type(v) is dict for v in (meta,spec,status)), 'flux_document')
            require(meta.get('name') == name and meta.get('namespace') == b.namespace and meta.get('uid') == uid
                    and not meta.get('deletionTimestamp') and digest(spec) == expected, 'flux_identity_or_spec_drift')
            require(not spec.get('suspend'), 'flux_suspended')
            generation = meta.get('generation')
            require(type(generation) is int and generation > 0, 'flux_generation')
            if status.get('observedGeneration') != generation: raise Pending('flux_generation_pending')
            items = status.get('conditions',[])
            require(type(items) is list and all(type(c) is dict for c in items), 'flux_conditions')
            conditions = {c.get('type'):c for c in items}
            require(len(conditions) == len(items), 'flux_duplicate_condition')
            ready = conditions.get('Ready',{})
            if ready.get('status') != 'True' or ready.get('observedGeneration') != generation or any(
                    conditions.get(k,{}).get('status') == 'True' for k in ('Reconciling','Stalled')):
                raise Pending('flux_not_ready')
        spec,status = app['spec'],app['status']
        require(spec.get('prune') is False and spec.get('wait') is True and not spec.get('force')
                and not spec.get('kubeConfig'), 'flux_unsupported_apply_policy')
        ref = spec.get('sourceRef',{})
        require(ref.get('kind') == 'GitRepository' and ref.get('name') == b.source_name
                and ref.get('namespace',b.namespace) == b.namespace, 'flux_source_binding')
        revision = status.get('lastAppliedRevision')
        require(type(revision) is str and re.fullmatch(r'[^\s@]{1,200}@sha1:[0-9a-f]{40}',revision), 'flux_revision')
        if status.get('lastAttemptedRevision') != revision or source['status'].get('artifact',{}).get('revision') != revision:
            raise Pending('flux_source_revision_pending')
        history = status.get('history')
        require(type(history) is list and 0 < len(history) <= 5, 'flux_history_required')
        latest = history[0]
        require(latest.get('lastReconciledStatus') == 'ReconciliationSucceeded'
                and latest.get('metadata',{}).get('revision') == revision, 'flux_history_binding')
        sha(latest.get('digest'))
        try:
            timestamp = datetime.fromisoformat(latest['lastReconciled'].replace('Z','+00:00'))
            require(timestamp.tzinfo is not None, 'flux_timestamp_timezone')
            observed = timestamp.timestamp()
        except (KeyError,TypeError,ValueError):
            raise Pending('flux_reconciliation_time_unavailable') from None
        if not self.clock()-60 <= observed <= self.clock(): raise Pending('flux_stale_observation')
        expected = sorted([{'id':ns+'_'+name+'_apps_Deployment','v':'v1'} for ns,_,name in
                          (value.split('/') for value in b.resources)], key=lambda x:x['id'])
        entries = status.get('inventory',{}).get('entries')
        require(type(entries) is list and all(type(v) is dict and set(v) == {'id','v'} for v in entries)
                and sorted(entries,key=lambda x:x['id']) == expected, 'flux_inventory_drift')
        again = self.transport.read(b,False,lease)
        if again != app: raise Pending('flux_observation_changed')
        return self.signer.seal('gitops_runtime_receipt', {'scope':asdict(b.scope),
            'application_id':application_id,'repository_id':b.repository_id,'observed_at':int(observed),
            'commit':revision.rsplit(':',1)[1],'sync':'Synced','health':'Healthy',
            'resources':sorted(b.resources),'pruned_resources':[],
            'provider_observation_digest':digest([app,source,again]),'independent_verification':'NOT_RUN'})
