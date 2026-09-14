"""Read-only Argo CD application observation; no sync, prune or merge authority.

Operator bindings pin application UID and complete spec, including destination,
repository, project and source path. Credentials come only from the host broker.
Receipts attest observations, never independent verification or certification.
"""
from dataclasses import asdict, dataclass
from datetime import datetime
import http.client
import re
import ssl
import time
from urllib.parse import quote, urlencode, urlsplit

from .contracts import Pending, Scope, digest, require, sha
from .host_bridge import strict_json


@dataclass(frozen=True)
class ArgoApplicationBinding:
    scope: Scope
    application_id: str
    application_name: str
    application_namespace: str
    application_uid: str
    repository_id: str
    project: str
    spec_digest: str
    resources: tuple[str, ...]

    def __post_init__(self):
        for value in (self.application_name, self.application_namespace, self.project):
            require(type(value) is str and re.fullmatch(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?', value)
                    and len(value) <= 63, 'argocd_binding_name')
        require(bool(self.application_uid) and bool(self.application_id) and bool(self.repository_id),
                'argocd_binding_identity')
        sha(self.spec_digest)
        require(type(self.resources) is tuple and 0 < len(self.resources) <= 100
                and len(set(self.resources)) == len(self.resources), 'argocd_binding_resources')
        for value in self.resources:
            require(type(value) is str and re.fullmatch(
                r'[a-z0-9-]{1,63}/Deployment/[a-z0-9-]{1,63}', value), 'argocd_binding_resource')


class ArgoCdHttpsTransport:
    def __init__(self, endpoint, ca_file, provider_id, broker, clock=time.time):
        uri = urlsplit(endpoint)
        require(uri.scheme == 'https' and uri.hostname and not uri.username and not uri.password
                and not uri.query and not uri.fragment and uri.path in ('', '/'), 'argocd_endpoint')
        self.host, self.port = uri.hostname, uri.port or 443
        self.context = ssl.create_default_context(cafile=str(ca_file))
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.provider_id, self.broker, self.clock = provider_id, broker, clock

    def get_application(self, binding, lease):
        lease.check(binding.scope, lease.deployment_id, lease.plan_digest,
                    (binding.repository_id, binding.application_id), 'gitops.reconcile',
                    self.clock(), lease.generation)
        path = '/api/v1/applications/' + quote(binding.application_name, safe='')
        query = {'project': binding.project, 'appNamespace': binding.application_namespace}
        request = {'provider_id': self.provider_id, 'method': 'GET', 'path': path,
                   'query': query, 'binding_digest': digest(asdict(binding))}
        session = self.broker.authorize_call(lease, request)
        require(type(session) is dict and set(session) == {
            'token', 'expires_at', 'session_identity', 'provider_id'}, 'argocd_session_fields')
        require(session['session_identity'] == lease.session_identity
                and session['provider_id'] == self.provider_id
                and type(session['expires_at']) is int and self.clock() < session['expires_at']
                and type(session['token']) is str and re.fullmatch(r'[!-~]{1,16384}', session['token']),
                'argocd_session_binding')
        connection = http.client.HTTPSConnection(self.host, self.port, context=self.context, timeout=15)
        started = time.monotonic()
        try:
            connection.request('GET', path + '?' + urlencode(query), headers={
                'Authorization': 'Bearer ' + session['token'], 'Accept': 'application/json',
                'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            require(response.status == 200, 'argocd_http_rejected')
            require(response.getheader('Content-Encoding', 'identity') == 'identity', 'argocd_encoding')
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
                require(len(raw) <= 1048576, 'argocd_response_bounds')
            document = strict_json(bytes(raw))
            require(type(document) is dict, 'argocd_document')
            self.broker.record_response(lease, digest(request), digest(bytes(raw)), binding.application_uid)
            return document, digest(bytes(raw))
        except (OSError, http.client.HTTPException):
            raise Pending('argocd_observation_unavailable') from None
        finally:
            connection.close()


class ArgoCdAdapter:
    def __init__(self, bindings, transport, receipt_signer, clock=time.time):
        bindings = tuple(bindings)
        self.bindings = {(b.scope.key, b.application_id): b for b in bindings}
        require(len(self.bindings) == len(bindings), 'argocd_duplicate_binding')
        self.transport, self.signer, self.clock = transport, receipt_signer, clock

    def observe(self, application_id, lease):
        binding = self.bindings.get((lease.scope.key, application_id))
        require(binding is not None, 'argocd_application_not_bound')
        lease.check(binding.scope, lease.deployment_id, lease.plan_digest,
                    (binding.repository_id, application_id), 'gitops.reconcile', self.clock(), lease.generation)
        document, raw_digest = self.transport.get_application(binding, lease)
        sha(raw_digest)
        metadata, spec, status = (document.get(k, {}) for k in ('metadata', 'spec', 'status'))
        require(all(type(v) is dict for v in (metadata, spec, status)), 'argocd_document_fields')
        require(metadata.get('uid') == binding.application_uid
                and metadata.get('name') == binding.application_name
                and metadata.get('namespace') == binding.application_namespace
                and not metadata.get('deletionTimestamp'), 'argocd_application_identity')
        require(digest(spec) == binding.spec_digest and spec.get('project') == binding.project,
                'argocd_spec_drift')
        require(type(spec.get('source')) is dict and not spec.get('sources'), 'argocd_single_source_required')
        # The scoped controller supports existing Deployments only, with no pruning.
        require(not spec.get('syncPolicy', {}).get('automated', {}).get('prune'), 'argocd_prune_forbidden')
        try:
            timestamp = datetime.fromisoformat(status['reconciledAt'].replace('Z', '+00:00'))
            require(timestamp.tzinfo is not None, 'argocd_timestamp_timezone')
            reconciled = timestamp.timestamp()
        except (KeyError, TypeError, ValueError):
            raise Pending('argocd_reconciliation_time_unavailable') from None
        if not self.clock() - 60 <= reconciled <= self.clock():
            raise Pending('argocd_stale_observation')
        require(not status.get('conditions'), 'argocd_application_conditions')
        sync = status.get('sync', {})
        require(sync.get('comparedTo', {}).get('source') == spec['source']
                and sync.get('comparedTo', {}).get('destination') == spec.get('destination'),
                'argocd_compared_spec_drift')
        commit = sync.get('revision')
        require(type(commit) is str and re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit),
                'argocd_exact_revision')
        if sync.get('status') != 'Synced' or status.get('health', {}).get('status') != 'Healthy':
            raise Pending('argocd_application_not_converged')
        operation = status.get('operationState', {})
        if document.get('operation') or operation.get('phase') != 'Succeeded':
            raise Pending('argocd_operation_not_settled')
        operation_sync = operation.get('operation', {}).get('sync', {})
        require(not operation_sync.get('prune') and not operation_sync.get('resources'),
                'argocd_partial_or_pruning_operation')
        result = operation.get('syncResult', {})
        require(result.get('revision') == commit, 'argocd_operation_revision')
        resources = self._resources(status.get('resources'), False)
        completed = self._resources(result.get('resources'), True)
        require(resources == sorted(binding.resources) and completed == resources, 'argocd_resource_drift')
        return self.signer.seal('gitops_runtime_receipt', {
            'scope': asdict(binding.scope), 'application_id': application_id,
            'repository_id': binding.repository_id, 'observed_at': int(reconciled),
            'commit': commit, 'sync': 'Synced', 'health': 'Healthy', 'resources': resources,
            'pruned_resources': [], 'provider_observation_digest': raw_digest,
            'independent_verification': 'NOT_RUN'})

    @staticmethod
    def _resources(items, operation):
        require(type(items) is list and 0 < len(items) <= 100, 'argocd_resource_bounds')
        values = []
        for item in items:
            require(type(item) is dict and item.get('group') == 'apps' and item.get('kind') == 'Deployment'
                    and not item.get('hook') and not item.get('hookType') and not item.get('requiresPruning'),
                    'argocd_resource_type')
            require(item.get('status') == 'Synced', 'argocd_resource_not_synced')
            if not operation:
                require(item.get('health', {}).get('status') == 'Healthy', 'argocd_resource_not_healthy')
            namespace, name = item.get('namespace'), item.get('name')
            require(all(type(v) is str and re.fullmatch(r'[a-z0-9-]{1,63}', v)
                        for v in (namespace, name)), 'argocd_resource_identity')
            values.append(namespace + '/Deployment/' + name)
        require(len(set(values)) == len(values), 'argocd_duplicate_resource')
        return sorted(values)
