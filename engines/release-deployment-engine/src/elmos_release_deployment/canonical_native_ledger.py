"""Native Runner adapter for the existing Java ProductionToolCallPort HTTP API."""
import base64
import http.client
import ssl
import time
from urllib.parse import urlsplit
from uuid import UUID
from .contracts import Pending, canonical, digest, require
from .host_bridge import strict_json


class ToolCallHttpClient:
    def __init__(self, endpoint, ca_file, credential_source):
        uri = urlsplit(endpoint)
        require(uri.scheme == 'https' and uri.hostname and not uri.username and not uri.password
                and not uri.query and not uri.fragment and uri.path in ('','/'), 'tool_host_endpoint')
        self.host,self.port,self.credentials = uri.hostname,uri.port or 443,credential_source
        self.context = ssl.create_default_context(cafile=str(ca_file))

    def post(self, route, body):
        import re
        require(re.fullmatch(r'/internal/v1/production-runtime/(?:deployment/lookup|billing/tool-calls(?:/[0-9a-f-]{36}/(?:claim-provider-dispatch|accepted|unknown|complete))?)',route),
                'tool_host_route')
        raw = canonical(body)
        require(len(raw) <= 1048576, 'tool_host_request_bounds')
        token = self.credentials.read()
        require(type(token) is str and re.fullmatch(r'[!-~]{1,16384}',token), 'tool_host_credential')
        connection = http.client.HTTPSConnection(self.host,self.port,context=self.context,timeout=15)
        started=time.monotonic()
        try:
            connection.request('POST',route,raw,{'Authorization':'Bearer '+token,
                'Content-Type':'application/json','Accept':'application/json','Accept-Encoding':'identity'})
            response=connection.getresponse()
            require(200 <= response.status < 300 and response.getheader('Content-Encoding','identity') == 'identity',
                    'tool_host_rejected')
            result=bytearray()
            while True:
                remaining=15-(time.monotonic()-started)
                if remaining <= 0: raise TimeoutError()
                if connection.sock: connection.sock.settimeout(remaining)
                chunk=response.read1(min(65536,1048577-len(result)))
                if not chunk: break
                result.extend(chunk)
                require(len(result) <= 1048576, 'tool_host_response_bounds')
            return strict_json(bytes(result)) if result else None
        except (OSError,http.client.HTTPException):
            raise Pending('tool_host_outcome_unknown') from None
        finally: connection.close()


class CanonicalNativeLedger:
    def __init__(self, client, context_resolver):
        self.client,self.context_resolver = client,context_resolver

    def _context(self, request, lease):
        context = dict(self.context_resolver(lease))
        require(set(context) == {'tenantId','accountId','projectId','jobId','stageId','workItemId','attemptId'},
                'native_canonical_context_fields')
        require(all(type(v) is str and str(UUID(v)) == v for v in context.values()), 'native_canonical_ids')
        require((context['tenantId'],context['accountId'],context['projectId']) ==
                (lease.scope.tenant_id,lease.scope.account_id,lease.scope.project_id), 'native_canonical_scope')
        action='iac.'+request['mode']
        require(action in lease.actions, 'native_canonical_action')
        return {**context,'tool':'release-deployment:'+action,'requestHash':digest(request),
                'idempotencyKey':'rd-native:'+digest([lease.scope.key,lease.deployment_id,lease.generation,request])[7:]}

    def _lookup(self, request, lease):
        context=self._context(request,lease)
        result=self.client.post('/internal/v1/production-runtime/deployment/lookup',{
            'context':context,'action':'iac.'+request['mode'],'payload':base64.b64encode(canonical(request)).decode()})
        require(type(result) is dict and 'status' in result, 'native_canonical_receipt')
        if result['status'] == 'NOT_FOUND': return None
        require(result['status'] in {'CREATED','PROVIDER_ACCEPTED','UNKNOWN','COMPLETE','FAILED'}
                and str(UUID(result['toolCallId'])) == result['toolCallId'], 'native_canonical_receipt')
        return result

    def prepare(self, request, lease):
        result=self._lookup(request,lease)
        if result is None:
            self.client.post('/internal/v1/production-runtime/billing/tool-calls',self._context(request,lease))
            result=self._lookup(request,lease)
        require(result is not None and result['status'] == 'CREATED', 'native_dispatch_already_claimed')
        return result['toolCallId']

    def _bound(self, invocation, request, lease):
        result=self._lookup(request,lease)
        require(result is not None and result['toolCallId'] == invocation, 'native_invocation_binding')
        return result

    def claim(self, invocation, request, lease):
        require(self._bound(invocation,request,lease)['status'] == 'CREATED', 'native_dispatch_already_claimed')
        self.client.post('/internal/v1/production-runtime/billing/tool-calls/'+invocation+'/claim-provider-dispatch',
                         {'tenantId':lease.scope.tenant_id})

    def unknown(self, invocation, request, lease):
        # A lost completion response must not overwrite an already committed result.
        if self._bound(invocation,request,lease)['status'] == 'COMPLETE': return
        self.client.post('/internal/v1/production-runtime/billing/tool-calls/'+invocation+'/unknown',
            {'tenantId':lease.scope.tenant_id,'providerRequestId':invocation,'providerStatus':'NATIVE_OUTCOME_UNKNOWN'})

    def complete(self, invocation, request, lease, reference):
        result=self._bound(invocation,request,lease)
        require(type(reference) is str and str(UUID(reference)) == reference, 'native_cas_artifact_id')
        if result['status'] == 'COMPLETE':
            require(result.get('responseArtifactId') == reference, 'native_completion_conflict')
            return
        self.client.post('/internal/v1/production-runtime/billing/tool-calls/'+invocation+'/accepted',
                         {'tenantId':lease.scope.tenant_id,'providerRequestId':invocation})
        self.client.post('/internal/v1/production-runtime/billing/tool-calls/'+invocation+'/complete',
                         {'tenantId':lease.scope.tenant_id,'responseArtifactId':reference})

    def find(self, request, lease):
        result=self._lookup(request,lease)
        return result['toolCallId'] if result else None

    def completed_reference(self, invocation, request, lease):
        result=self._bound(invocation,request,lease)
        require(result['status'] != 'FAILED', 'native_canonical_failed')
        return result.get('responseArtifactId') if result['status'] == 'COMPLETE' else None
