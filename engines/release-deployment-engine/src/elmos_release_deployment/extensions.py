"""Bounded P1/P2 planning and verification components, not cloud-effect authority.

Every returned program is digest-bound input to the existing host policy,
execution, evidence and lifecycle services. No planner manufactures receipts.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from decimal import Decimal, InvalidOperation
import re
from .contracts import Scope, canonical, digest, identifier, require, sha
from .service import verified


def exact_decimal(value):
    require(type(value) is str, 'decimal_string_required')
    try:
        result = Decimal(value)
    except InvalidOperation:
        require(False, 'invalid_decimal')
    require(result.is_finite(), 'nonfinite_decimal')
    return result


class RolloutPlanner:
    @staticmethod
    def batches(resources: tuple[str, ...], strategy, batch_size=1, canary_count=1):
        require(type(resources) is tuple and 1 <= len(resources) <= 100 and len(set(resources)) == len(resources), 'rollout_resources')
        for resource in resources: identifier(resource)
        require(type(batch_size) is int and 1 <= batch_size <= len(resources), 'rollout_batch_size')
        require(strategy in {'single_replace','compose_replace','rolling','canary','blue_green'}, 'rollout_strategy')
        if strategy in {'single_replace','compose_replace'}:
            require(len(resources)==1, 'single_target_required')
            return (resources,)
        if strategy == 'canary':
            require(type(canary_count) is int and 1 <= canary_count < len(resources), 'canary_size')
            return (resources[:canary_count],) + tuple(resources[i:i+batch_size] for i in range(canary_count,len(resources),batch_size))
        if strategy == 'blue_green':
            require(len(resources) >= 2, 'blue_green_requires_separate_groups')
            return (resources,)
        return tuple(resources[i:i+batch_size] for i in range(0,len(resources),batch_size))


class TrafficController:
    @staticmethod
    def plan(scope, route_id, before: dict[str,int], after: dict[str,int], authorized_resources,
             verified_health: dict[str,str], strategy):
        identifier(route_id)
        require(strategy in {'rolling','canary','blue_green','single_replace','compose_replace'}, 'traffic_strategy')
        for mapping in (before,after):
            require(mapping and len(mapping)<=100 and set(mapping)<=set(authorized_resources), 'traffic_resource_fence')
            require(all(type(v) is int and 0 <= v <= 100 for v in mapping.values()) and sum(mapping.values())==100, 'traffic_weights')
        promoted={resource for resource,weight in after.items() if weight>0}
        require(all(verified_health.get(r)=='PASS' for r in promoted), 'unverified_backend')
        return {'scope':asdict(scope),'route_id':route_id,'strategy':strategy,
                'before':before,'after':after,'compensation':before,
                'operation_digest':digest([asdict(scope),route_id,before,after])}


class DnsTlsPlanner:
    @staticmethod
    def plan(scope, domain, old_record, new_record, certificate_digest, *, allowed_domains,
             exposure_before, exposure_after, icp_verified, region):
        require(domain in allowed_domains and re.fullmatch(r'[a-z0-9.-]{1,253}',domain) is not None, 'domain_scope')
        require(exposure_before==exposure_after and exposure_after in {'private','public'}, 'network_exposure_change_requires_separate_policy')
        require(type(icp_verified) is bool, 'invalid_icp_evidence')
        if exposure_after=='public' and region.startswith('cn-') and region!='cn-hongkong':
            require(icp_verified, 'mainland_public_icp_required')
        sha(certificate_digest)
        for record in (old_record,new_record):
            require(set(record)=={'type','value','ttl'} and record['type'] in {'A','AAAA','CNAME'} and
                    type(record['ttl']) is int and 30<=record['ttl']<=86400, 'dns_record_contract')
            if record['type'] in {'A','AAAA'}:
                import ipaddress
                ip=ipaddress.ip_address(record['value'])
                require(ip.version==(4 if record['type']=='A' else 6), 'dns_address_family')
            else:
                require(re.fullmatch(r'[a-z0-9.-]{1,253}',record['value']) is not None,'dns_cname')
        return {'scope':asdict(scope),'domain':domain,'before':old_record,'after':new_record,
                'certificate_digest':certificate_digest,'compensation':old_record}


class InfrastructureProvisioner:
    @staticmethod
    def authorize_plan(trust, scope, plan_bytes: bytes, approval: dict, now):
        require(type(plan_bytes) is bytes and len(plan_bytes)<=16_000_000,'iac_plan_bounds')
        body=verified(trust,'infrastructure_approval',approval)
        require(body.get('scope')==asdict(scope) and body.get('plan_digest')==digest(plan_bytes), 'iac_approval_binding')
        require(type(body.get('expires_at')) is int and now<body['expires_at'], 'iac_approval_expired')
        require(body.get('rollback_verified') is True and body.get('destroy_plan_digest') and
                body.get('network_change')=='NONE' and body.get('iam_change')=='NONE', 'iac_requires_separate_network_iam_review')
        sha(body['destroy_plan_digest'])
        return {'scope':asdict(scope),'plan_digest':digest(plan_bytes),'destroy_plan_digest':body['destroy_plan_digest'],
                'authorization_digest':digest(approval),'status':'READY_FOR_HOST_EXECUTION'}


class ArtifactSecurityGate:
    @staticmethod
    def verify(trust, scope, image_digest, scan, signature, now):
        sha(image_digest)
        for purpose,envelope in [('artifact_scan',scan),('artifact_signature',signature)]:
            body=verified(trust,purpose,envelope)
            require(body.get('scope')==asdict(scope) and body.get('image_digest')==image_digest, 'artifact_security_binding')
            require(type(body.get('expires_at')) is int and now<body['expires_at'] and
                    body.get('decision')=='PASS', 'artifact_security_failed')
        return {'image_digest':image_digest,'scan_receipt':digest(scan),'signature_receipt':digest(signature)}


@dataclass(frozen=True)
class PreviewEnvironment:
    scope: Scope
    environment_id: str
    created_at: int
    expires_at: int
    resource_ids: tuple[str,...]
    creation_receipt: str

    def __post_init__(self):
        identifier(self.environment_id); sha(self.creation_receipt)
        require(type(self.created_at) is int and type(self.expires_at) is int and
                0 < self.expires_at-self.created_at <= 86400, 'preview_ttl_bounds')
        require(type(self.resource_ids) is tuple and 0<len(self.resource_ids)<=100, 'preview_resource_bounds')
        for resource in self.resource_ids: identifier(resource)

    def cleanup_plan(self, now, observed_resources, active_deployments):
        require(now>=self.expires_at,'preview_not_expired')
        require(active_deployments==0 and type(active_deployments) is int,'preview_has_active_deployments')
        require(set(observed_resources)==set(self.resource_ids),'preview_orphan_reconciliation_required')
        return {'scope':asdict(self.scope),'resources':list(self.resource_ids),'creation_receipt':self.creation_receipt,
                'operation_key':digest(asdict(self)),'action':'destroy_expired_preview'}


class RetentionPlanner:
    @staticmethod
    def candidates(releases, keep_stable, now, protected_digests):
        require(type(keep_stable) is int and keep_stable>=1 and len(releases)<=10000,'retention_bounds')
        ordered=sorted(releases,key=lambda r:r['created_at'],reverse=True)
        stable=[r['digest'] for r in ordered if r['state']=='VERIFIED_STABLE'][:keep_stable]
        protected=set(stable)|set(protected_digests)
        candidates=[]
        for item in ordered:
            require(set(item)=={'digest','created_at','expires_at','state','reference_count'},'retention_record')
            sha(item['digest'])
            require(type(item['reference_count']) is int and item['reference_count']>=0,'retention_reference_count')
            require(item['state'] in {'VERIFIED_STABLE','DEPRECATED','REVOKED'},'unknown_release_state')
            if item['digest'] not in protected and item['reference_count']==0 and item['expires_at']<=now:
                candidates.append(item['digest'])
        return candidates


class ObservabilityPublisher:
    @staticmethod
    def annotations(scope, deployment_id, release_id, commit, image_digests, environment, target):
        for value in (deployment_id,release_id,environment,target): identifier(value)
        require(re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',commit) is not None,'observability_commit')
        for value in image_digests: sha(value)
        return {'tenant_id':scope.tenant_id,'project_id':scope.project_id,'deployment_id':deployment_id,
                'release_id':release_id,'commit':commit,'image_digests':list(image_digests),
                'environment_id':environment,'target_id':target}


class KubernetesProvider:
    @staticmethod
    def deployment(scope, namespace, name, artifacts, replicas, config_map_name, secret_names):
        for value in (namespace,name,config_map_name,*secret_names):
            require(re.fullmatch(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?',value) is not None and len(value)<=63,'kubernetes_name')
        require(type(replicas) is int and 1<=replicas<=100 and 1<=len(artifacts)<=16,'kubernetes_bounds')
        require(len({a.name for a in artifacts})==len(artifacts),'duplicate_container')
        labels={'app.kubernetes.io/name':name,'elmos.io/scope':scope.key[7:][:63]}
        containers=[]
        for a in artifacts:
            containers.append({'name':a.name,'image':a.image,'ports':[{'containerPort':a.port}],
                'securityContext':{'runAsNonRoot':True,'runAsUser':10001,'readOnlyRootFilesystem':True,
                                   'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},
                'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'512Mi'}},
                'envFrom':[{'configMapRef':{'name':config_map_name}},
                           *({'secretRef':{'name':s}} for s in secret_names)],
                'readinessProbe':{'tcpSocket':{'port':a.port},'initialDelaySeconds':5,'periodSeconds':5},
                'livenessProbe':{'tcpSocket':{'port':a.port},'initialDelaySeconds':30,'periodSeconds':10}})
        return {'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':name,'namespace':namespace,'labels':labels},
                'spec':{'replicas':replicas,'selector':{'matchLabels':labels},
                        'strategy':{'type':'RollingUpdate','rollingUpdate':{'maxUnavailable':0,'maxSurge':1}},
                        'template':{'metadata':{'labels':labels},'spec':{'automountServiceAccountToken':False,
                             'securityContext':{'seccompProfile':{'type':'RuntimeDefault'}},'containers':containers}}}}

    @staticmethod
    def apply_request(manifest, expected_resource_version):
        require(manifest.get('kind')=='Deployment' and manifest.get('apiVersion')=='apps/v1','unsupported_kubernetes_kind')
        identifier(expected_resource_version)
        result=json_copy(manifest)
        result['metadata']['resourceVersion']=expected_resource_version
        return {'method':'PATCH','path':f"/apis/apps/v1/namespaces/{result['metadata']['namespace']}/deployments/{result['metadata']['name']}",
                'content_type':'application/apply-patch+yaml','query':{'fieldManager':'elmos-release-deployment'},
                'body':result,'force':False}


def json_copy(value):
    import json
    return json.loads(canonical(value))


class HelmGitOpsBridge:
    @staticmethod
    def proposal(scope, chart_digest, rendered_manifests, allowed_namespaces, base_commit):
        sha(chart_digest)
        require(re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',base_commit) is not None,'gitops_base_commit')
        require(type(rendered_manifests) is list and 0<len(rendered_manifests)<=100,'helm_manifest_bounds')
        seen=set()
        for manifest in rendered_manifests:
            require(manifest.get('apiVersion')=='apps/v1' and manifest.get('kind')=='Deployment','helm_kind_not_allowlisted')
            meta=manifest.get('metadata',{})
            require(meta.get('namespace') in allowed_namespaces and not meta.get('annotations'),'helm_namespace_or_hook')
            key=(meta.get('namespace'),meta.get('name'))
            require(key not in seen,'helm_duplicate_resource'); seen.add(key)
            pod=manifest['spec']['template']['spec']
            require(not any(pod.get(k) for k in ('hostNetwork','hostPID','hostIPC','volumes','initContainers')),
                    'helm_pod_privilege')
            require(pod.get('automountServiceAccountToken') is False,'helm_service_account_token')
            for container in pod['containers']:
                require('@sha256:' in container['image'],'helm_image_not_pinned')
                sha('sha256:'+container['image'].rsplit('@sha256:',1)[1])
                security=container.get('securityContext',{})
                require(security.get('allowPrivilegeEscalation') is False and security.get('runAsNonRoot') is True
                        and security.get('readOnlyRootFilesystem') is True and not security.get('privileged') and
                        security.get('capabilities')=={'drop':['ALL']},'helm_container_privilege')
        return {'scope':asdict(scope),'chart_digest':chart_digest,'manifest_digest':digest(rendered_manifests),
                'base_commit':base_commit,'operation':'propose_gitops_change','merge_authorized':False}


class ProgressiveDelivery:
    @staticmethod
    def decide(samples, max_error_rate, max_p95_ms, minimum_samples, required_window_seconds):
        rate,latency=exact_decimal(max_error_rate),exact_decimal(max_p95_ms)
        require(0<=rate<=1 and latency>0 and type(minimum_samples) is int and minimum_samples>0 and
                type(required_window_seconds) is int and required_window_seconds>0,'slo_policy')
        require(0<len(samples)<=10000,'slo_samples')
        requests=errors=0; intervals=[]
        for sample in samples:
            require(set(sample)=={'start','end','requests','errors','p95_ms','evidence_digest'},'slo_sample_fields')
            sha(sample['evidence_digest'])
            require(all(type(sample[k]) is int for k in ('start','end','requests','errors')) and
                    sample['start']<sample['end'] and 0<=sample['errors']<=sample['requests'],'slo_sample_invalid')
            intervals.append((sample['start'],sample['end']))
            requests+=sample['requests']; errors+=sample['errors']
            if exact_decimal(sample['p95_ms'])>latency:
                return 'ROLLBACK'
        intervals.sort()
        require(all(intervals[i][1]==intervals[i+1][0] for i in range(len(intervals)-1)),'slo_gaps_or_overlap')
        if requests<minimum_samples or intervals[-1][1]-intervals[0][0]<required_window_seconds:
            return 'OBSERVE'
        return 'ROLLBACK' if Decimal(errors)>rate*Decimal(requests) else 'PROMOTE'


class ProviderRegistry:
    def __init__(self, host_adapters):
        self.adapters=dict(host_adapters)

    def resolve(self, provider, version, region, account, operation):
        key=(provider,version,region,account,operation)
        require(all(type(k) is str and k and k not in {'*','latest','current'} for k in key),'exact_provider_tuple_required')
        require(key in self.adapters,'provider_tuple_not_configured')
        return self.adapters[key]
