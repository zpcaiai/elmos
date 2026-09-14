from dataclasses import asdict, replace
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from elmos_release_deployment.contracts import *
from elmos_release_deployment.extensions import *
from elmos_release_deployment.adapters import *
from elmos_release_deployment.api import DeploymentAPI
import test_runtime as fixture


class ExtensionsTest(unittest.TestCase):
    def setUp(self):
        self.scope=Scope('tenant','workspace','project','staging','123456789')

    def test_rolling_canary_exact_resource_partition(self):
        self.assertEqual((('a',),('b','c')),RolloutPlanner.batches(('a','b','c'),'canary',2,1))
        with self.assertRaises(Denied): RolloutPlanner.batches(('a','a'),'rolling')
        with self.assertRaises(Denied): RolloutPlanner.batches(('a','b'),'canary',1,2)

    def test_traffic_weights_health_and_compensation(self):
        plan=TrafficController.plan(self.scope,'route',{'a':100},{'a':90,'b':10},('a','b'),{'a':'PASS','b':'PASS'},'canary')
        self.assertEqual({'a':100},plan['compensation'])
        with self.assertRaises(Denied): TrafficController.plan(self.scope,'route',{'a':100},{'b':100},('a','b'),{'b':'UNKNOWN'},'canary')
        with self.assertRaises(Denied): TrafficController.plan(self.scope,'route',{'a':100},{'b':99},('a','b'),{'b':'PASS'},'canary')

    def test_dns_tls_icp_and_no_exposure_broadening(self):
        old={'type':'A','value':'10.0.0.1','ttl':300}; new={**old,'value':'10.0.0.2'}
        args=(self.scope,'app.example.test',old,new,digest(b'cert'))
        kwargs={'allowed_domains':['app.example.test'],'exposure_before':'public','exposure_after':'public','icp_verified':False,'region':'cn-shanghai'}
        with self.assertRaises(Denied): DnsTlsPlanner.plan(*args,**kwargs)
        kwargs['icp_verified']=True
        self.assertEqual(old,DnsTlsPlanner.plan(*args,**kwargs)['compensation'])
        kwargs['exposure_before']='private'
        with self.assertRaises(Denied): DnsTlsPlanner.plan(*args,**kwargs)

    def test_preview_ttl_and_orphan_reconciliation(self):
        preview=PreviewEnvironment(self.scope,'preview',100,700,('i-a',),digest(b'created'))
        with self.assertRaises(Denied): preview.cleanup_plan(699,['i-a'],0)
        with self.assertRaises(Denied): preview.cleanup_plan(700,['i-b'],0)
        with self.assertRaises(Denied): preview.cleanup_plan(700,['i-a'],1)
        self.assertEqual(['i-a'],preview.cleanup_plan(700,['i-a'],0)['resources'])

    def test_retention_protects_stable_and_referenced(self):
        rows=[{'digest':digest(str(n).encode()),'created_at':n,'expires_at':100,'state':'VERIFIED_STABLE','reference_count':0} for n in range(4)]
        eligible=RetentionPlanner.candidates(rows,2,200,{rows[0]['digest']})
        self.assertEqual([rows[1]['digest']],eligible)

    def test_kubernetes_and_helm_reject_privilege(self):
        artifact=Artifact('backend','registry.test/app',digest(b'image'),digest(b'sbom'),digest(b'prov'),digest(b'scan'),'spring',8080)
        manifest=KubernetesProvider.deployment(self.scope,'team-a','backend',(artifact,),2,'config-a',('secret-a',))
        request=KubernetesProvider.apply_request(manifest,'123')
        self.assertFalse(request['force'])
        self.assertEqual('123',request['body']['metadata']['resourceVersion'])
        proposal=HelmGitOpsBridge.proposal(self.scope,digest(b'chart'),[manifest],['team-a'],'a'*40)
        self.assertFalse(proposal['merge_authorized'])
        manifest['spec']['template']['spec']['containers'][0]['securityContext']['privileged']=True
        with self.assertRaises(Denied): HelmGitOpsBridge.proposal(self.scope,digest(b'chart'),[manifest],['team-a'],'a'*40)

    def test_slo_uses_exact_rates_and_requires_complete_windows(self):
        rows=[{'start':0,'end':60,'requests':100,'errors':1,'p95_ms':'120.0','evidence_digest':digest(b'obs')}]
        self.assertEqual('PROMOTE',ProgressiveDelivery.decide(rows,'0.01','200',100,60))
        self.assertEqual('OBSERVE',ProgressiveDelivery.decide(rows,'0.01','200',101,60))
        self.assertEqual('ROLLBACK',ProgressiveDelivery.decide(rows,'0.009','200',100,60))
        with self.assertRaises(Denied): ProgressiveDelivery.decide(rows,0.01,'200',100,60)
        with self.assertRaises(Denied): ProgressiveDelivery.decide(rows+rows,'0.01','200',100,60)

    def test_exact_provider_registry(self):
        adapter=object(); key=('alibaba_ecs','2014-05-26','cn-shanghai','123456789','runtime.activate')
        registry=ProviderRegistry({key:adapter})
        self.assertIs(adapter,registry.resolve(*key))
        with self.assertRaises(Denied): registry.resolve('aws','latest','*','*','*')

    def test_iac_and_artifact_gate_require_signed_exact_receipts(self):
        trust=fixture.FixtureAuthority(); plan=b'real-plan-bytes'
        body={'scope':asdict(self.scope),'plan_digest':digest(plan),'expires_at':1100,'rollback_verified':True,
              'destroy_plan_digest':digest(b'destroy'),'network_change':'NONE','iam_change':'NONE'}
        signed=trust.seal('infrastructure_approval',body)
        self.assertEqual('READY_FOR_HOST_EXECUTION',InfrastructureProvisioner.authorize_plan(trust,self.scope,plan,signed,1000)['status'])
        with self.assertRaises(Denied): InfrastructureProvisioner.authorize_plan(trust,self.scope,b'changed',signed,1000)
        image=digest(b'image'); body={'scope':asdict(self.scope),'image_digest':image,'expires_at':1100,'decision':'PASS'}
        ArtifactSecurityGate.verify(trust,self.scope,image,trust.seal('artifact_scan',body),trust.seal('artifact_signature',body),1000)
        with self.assertRaises(Denied): ArtifactSecurityGate.verify(trust,self.scope,image,trust.seal('artifact_scan',body),trust.seal('artifact_signature',body),1100)


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.f=fixture.RuntimeTest(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.principal=replace(self.f.principal,permissions=self.f.principal.permissions|{'deployment:read','deployment:rollback'})
        self.api=DeploymentAPI(self.f.service,lambda env:self.principal)

    def call(self,method,path,raw=b'{}'):
        status=[]
        body=b''.join(self.api({'REQUEST_METHOD':method,'PATH_INFO':path,'CONTENT_LENGTH':str(len(raw)),
                               'CONTENT_TYPE':'application/json',
                               'wsgi.input':io.BytesIO(raw)},lambda s,h:status.append(s)))
        return status[0],json.loads(body)

    def test_http_apply_status_timeline_evidence(self):
        code,response=self.call('POST','/v1/deployments',canonical({'ticket_id':self.f.ticket,'plan_digest':self.f.plan.plan_digest,'idempotency_key':'api-1'}))
        self.assertEqual('200 OK',code)
        dep=response['deployment_id']; self.f.finish(dep)
        for suffix in ('','/timeline','/evidence'):
            code,body=self.call('GET','/v1/deployments/'+dep+suffix)
            self.assertEqual('200 OK',code)
        self.assertEqual('SUCCEEDED',body['final_state'])

    def test_http_duplicate_keys_and_client_scope_rejected(self):
        self.assertEqual('403 Forbidden',self.call('POST','/v1/deployments',b'{"ticket_id":"a","ticket_id":"b"}')[0])
        body={'ticket_id':self.f.ticket,'plan_digest':self.f.plan.plan_digest,'idempotency_key':'api-1','scope':asdict(self.f.scope)}
        self.assertEqual('403 Forbidden',self.call('POST','/v1/deployments',canonical(body))[0])

    def test_missing_authentication_and_host_error_do_not_leak(self):
        self.api.authenticator=lambda env:None
        self.assertEqual('403 Forbidden',self.call('GET','/v1/releases/release-1')[0])
        def error(env): raise RuntimeError('provider secret-value')
        self.api.authenticator=error
        code,body=self.call('GET','/v1/releases/release-1')
        self.assertEqual('503 Service Unavailable',code)
        self.assertNotIn('secret-value',str(body))

    def test_operator_rollback_creates_separate_evidence(self):
        dep=self.f.deploy(); self.f.finish(dep)
        original=self.f.journal.evidence(self.f.scope,dep)
        ticket=self.f.service.issue_ticket(self.principal,self.f.plan.plan_digest,1500)
        self.f.service.approve_ticket(self.f.approver,ticket)
        result=self.f.service.rollback(self.principal,dep,ticket,'rollback-request')
        self.assertNotEqual(dep,result)
        self.assertEqual('ROLLED_BACK',self.f.finish(result))
        self.assertEqual(original,self.f.journal.evidence(self.f.scope,dep))

    def test_missing_smoke_case_cannot_be_hidden_by_other_passing_cases(self):
        self.f.host.bad_data['smoke.verify']={'cases':{'different-case':'PASS'},'policy_digest':self.f.release.health_policy_digest}
        self.assertEqual('ROLLED_BACK',self.f.finish(self.f.deploy()))


if __name__=='__main__': unittest.main()
