"""Existing-Deployment SSA controller. No namespace, RBAC or network expansion."""
from dataclasses import asdict
import json
import re

from .contracts import Pending, canonical, digest, require
from .extensions import HelmGitOpsBridge, KubernetesProvider
from .service import verified


def contains_contract(observed, expected):
    if type(expected) is dict:
        return type(observed) is dict and all(k in observed and contains_contract(observed[k],v)
                                              for k,v in expected.items())
    if type(expected) is list:
        return type(observed) is list and len(observed) == len(expected) and all(
            contains_contract(a,b) for a,b in zip(observed,expected))
    return type(observed) is type(expected) and observed == expected


class KubernetesDeploymentController:
    def __init__(self, journal, transport, trust, scope, cluster_id, namespace, clock):
        self.journal, self.transport, self.trust = journal, transport, trust
        self.scope, self.cluster, self.namespace, self.clock = scope, cluster_id, namespace, clock

    def apply(self, manifest, expected_uid, expected_version, approval, lease):
        # Reuse the restricted manifest validator before accepting an effect.
        HelmGitOpsBridge.proposal(self.scope, digest(b'controller-manifest'), [manifest],
                                  {self.namespace}, '0'*40)
        name = manifest['metadata']['name']
        require(re.fullmatch(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?', name) is not None and len(name)<=63,
                'kubernetes_name')
        require(manifest['metadata'].get('labels',{}).get('elmos.io/scope') == self.scope.key[7:][:63],
                'kubernetes_scope_label')
        request = KubernetesProvider.apply_request(manifest, expected_version)
        request['body']['metadata']['uid'] = expected_uid
        plan = {'scope':asdict(self.scope),'cluster_id':self.cluster,'namespace':self.namespace,
                'expected_uid':expected_uid,'request':request}
        body = verified(self.trust,'kubernetes_apply_approval',approval)
        require(body == {'operation_digest':digest(plan),'deployment_id':lease.deployment_id,
                         'plan_digest':lease.plan_digest,'generation':lease.generation,
                         'expires_at':body.get('expires_at')}, 'kubernetes_approval_binding')
        require(type(body['expires_at']) is int and self.clock()<body['expires_at'], 'kubernetes_approval_expired')
        resource = self.cluster + '/' + self.namespace + '/deployments/' + name
        lease.check(self.scope,lease.deployment_id,lease.plan_digest,(resource,),
                    'kubernetes.apply',self.clock(),lease.generation)
        operation = 'kubernetes.apply:' + digest(plan)[7:]
        row, fresh = self.journal.begin_step(self.scope,lease.deployment_id,operation,plan,self.clock(),True)
        if row['status']=='COMPLETE':
            return json.loads(row['result'])
        def read():
            result = self.transport.request('GET',request['path'],{},None,lease)
            meta = result.get('metadata',{})
            require(meta.get('uid')==expected_uid and meta.get('namespace')==self.namespace
                    and meta.get('name')==name and not meta.get('deletionTimestamp'), 'kubernetes_identity_drift')
            return result
        if fresh:
            observed = read()
            require(observed['metadata'].get('resourceVersion')==expected_version, 'kubernetes_version_conflict')
            result = self.transport.request('PATCH',request['path'],request['query'],request['body'],lease)
            require(result.get('metadata',{}).get('uid')==expected_uid
                    and contains_contract(result.get('spec'),manifest['spec']), 'kubernetes_admission_contract_changed')
            generation = result['metadata'].get('generation')
            require(type(generation) is int and generation>0, 'kubernetes_generation')
            invocation = json.dumps({'uid':expected_uid,'generation':generation},separators=(',',':'))
            self.journal.accepted(self.scope,lease.deployment_id,operation,invocation)
        else:
            if row['invocation'] is None:
                raise Pending('kubernetes_dispatch_unknown_requires_host_reconciliation')
            invocation = row['invocation']
            generation = json.loads(invocation)['generation']
        observed = read()
        require(observed['metadata'].get('generation')==generation
                and contains_contract(observed.get('spec'),manifest['spec']), 'kubernetes_spec_drift')
        status = observed.get('status',{})
        replicas = manifest['spec']['replicas']
        require(type(replicas) is int and replicas>0,'kubernetes_replicas')
        if status.get('observedGeneration') != generation or any(status.get(k,0)!=replicas
                for k in ('replicas','updatedReplicas','readyReplicas','availableReplicas')):
            raise Pending('kubernetes_rollout_in_progress')
        conditions = {c.get('type'):c.get('status') for c in status.get('conditions',[])}
        require(conditions.get('Available')=='True' and conditions.get('Progressing')=='True'
                and conditions.get('ReplicaFailure') != 'True', 'kubernetes_rollout_conditions')
        result = {'operation_digest':digest(plan),'uid':expected_uid,'generation':generation,
                  'observed_digest':digest(observed),'status':'ROLLOUT_OBSERVED',
                  'business_smoke':'NOT_RUN','certification':'NOT_CERTIFIED'}
        self.journal.complete_step(self.scope,lease.deployment_id,operation,result,self.clock())
        return result


class KubernetesHttpsTransport:
    """Pinned cluster endpoint/CA; host broker supplies short-lived scoped tokens."""
    def __init__(self, endpoint, ca_file, cluster_id, namespace, broker, clock):
        from urllib.parse import urlsplit
        import ssl
        uri = urlsplit(endpoint)
        require(uri.scheme=='https' and uri.hostname and not uri.username and not uri.password
                and not uri.query and not uri.fragment and uri.path in ('','/'), 'kubernetes_endpoint')
        require(re.fullmatch(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?',namespace) is not None, 'kubernetes_namespace')
        self.host,self.port,self.cluster,self.namespace,self.broker,self.clock = (
            uri.hostname,uri.port or 443,cluster_id,namespace,broker,clock)
        self.context = ssl.create_default_context(cafile=str(ca_file))

    def request(self, method, path, query, body, lease):
        import http.client
        import time
        from urllib.parse import urlencode
        from .host_bridge import strict_json
        require(method in {'GET','PATCH'} and re.fullmatch(
            '/apis/apps/v1/namespaces/'+re.escape(self.namespace)+'/deployments/[a-z0-9-]{1,63}',path),
            'kubernetes_route')
        require((method=='GET' and not query and body is None) or
                (method=='PATCH' and query=={'fieldManager':'elmos-release-deployment'} and type(body) is dict),
                'kubernetes_request_contract')
        require(self.clock()<lease.expires_at,'lease_expired')
        binding = {'cluster_id':self.cluster,'namespace':self.namespace,'method':method,'path':path,
                   'query':query,'body_digest':digest(body) if body is not None else None}
        session = self.broker.authorize_call(lease,binding)
        require(set(session)=={'token','expires_at','session_identity','cluster_id'} and
                session['session_identity']==lease.session_identity and session['cluster_id']==self.cluster
                and type(session['expires_at']) is int and self.clock()<session['expires_at']
                and type(session['token']) is str and 0<len(session['token'])<=16384
                and '\n' not in session['token'] and '\r' not in session['token'], 'kubernetes_session')
        encoded = canonical(body) if body is not None else None
        require(encoded is None or len(encoded)<=262144,'kubernetes_body_bounds')
        connection = http.client.HTTPSConnection(self.host,self.port,context=self.context,timeout=15)
        started=time.monotonic()
        try:
            connection.request(method,path+('?' + urlencode(query) if query else ''),encoded,
                {'Authorization':'Bearer '+session['token'],'Content-Type':'application/apply-patch+yaml',
                 'Accept':'application/json','Accept-Encoding':'identity'})
            response=connection.getresponse()
            require(response.getheader('Content-Encoding','identity')=='identity','kubernetes_encoding')
            raw=bytearray()
            while True:
                remaining=15-(time.monotonic()-started)
                if remaining<=0: raise TimeoutError()
                if connection.sock: connection.sock.settimeout(remaining)
                chunk=response.read1(min(65536,1048577-len(raw)))
                if not chunk: break
                raw.extend(chunk)
                require(len(raw)<=1048576,'kubernetes_response_bounds')
            require(response.status==200,'kubernetes_request_rejected')
            result=strict_json(bytes(raw))
            require(type(result) is dict and result.get('kind')=='Deployment','kubernetes_response_kind')
            self.broker.record_response(lease,digest(binding),digest(bytes(raw)),result['metadata']['uid'])
            return result
        except (OSError,http.client.HTTPException):
            raise Pending('kubernetes_outcome_unknown') from None
        finally:
            connection.close()
