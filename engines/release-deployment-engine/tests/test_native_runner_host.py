from dataclasses import asdict, replace
from uuid import uuid4
import unittest
from elmos_release_deployment.contracts import Scope, CapabilityLease, Pending, Denied, digest
from elmos_release_deployment.canonical_native_ledger import CanonicalNativeLedger
from elmos_release_deployment.native_runner_host import NativeRunnerHost
from test_runtime import FixtureAuthority


class NativeHostTests(unittest.TestCase):
    def setUp(self):
        self.scope=Scope(str(uuid4()),'workspace',str(uuid4()),'test',str(uuid4()))
        self.lease=CapabilityLease('l',self.scope,'d',digest(b'plan'),('resource',),frozenset({'iac.apply'}),0,1100,'session')
        self.request={'scope':asdict(self.scope),'mode':'apply','runtime_digest':digest(b'runtime')}
        self.context={'tenantId':self.scope.tenant_id,'accountId':self.scope.account_id,'projectId':self.scope.project_id,
                      **{name:str(uuid4()) for name in ('jobId','stageId','workItemId','attemptId')}}
        self.id,self.artifact=str(uuid4()),str(uuid4())
        self.receipt=None; self.envelope=None; self.executions=0; self.inspections=0
        self.failure=False; self.lost_complete=False; self.lost_claim=False; self.bad_attestation=False
        self.trust=FixtureAuthority()
        self.ledger=CanonicalNativeLedger(self,lambda lease:self.context)
        self.host=NativeRunnerHost(self,self,self.ledger,self,self.trust,self.trust,lambda:1000)

    def require(self,request,lease,action):
        if lease.scope != self.scope: raise Denied('test_scope')

    def resolve(self,scope,request,kind): return self

    def attest(self,request,lease):
        return self.trust.seal('native_sandbox_attestation',{'scope':asdict(self.scope),'request_digest':digest(request),
            'runtime_digest':request['runtime_digest'],'generation':lease.generation,'isolated':not self.bad_attestation,
            'providers_pinned':True,'expires_at':1100})

    def inspect(self,request):
        self.inspections+=1
        return {'plan_mode':'apply','plan_resources':['resource'],'before_state_digest':digest(b'state')}

    def execute(self,request):
        self.executions+=1
        if self.failure: raise RuntimeError('provider outcome unknown')
        return {'exit_code':0,'state_digest':digest(b'state'),'state_lineage':'lineage','state_serial':1,
                'resource_addresses':['resource'],'stdout_digest':digest(b''),'stderr_digest':digest(b''),'refresh_verified':True}

    def post(self,route,body):
        if route.endswith('/lookup'): return dict(self.receipt) if self.receipt else {'status':'NOT_FOUND'}
        if route.endswith('/tool-calls'):
            self.receipt={'toolCallId':self.id,'status':'CREATED','responseArtifactId':None,'providerRequestId':None}
            return dict(self.receipt)
        if route.endswith('/claim-provider-dispatch'):
            if self.receipt['status'] != 'CREATED': raise Denied('already_claimed')
            self.receipt['status']='UNKNOWN'
            if self.lost_claim: raise Pending('lost_claim')
        elif route.endswith('/accepted'):
            self.receipt.update(status='PROVIDER_ACCEPTED',providerRequestId=body['providerRequestId'])
        elif route.endswith('/unknown'): self.receipt['status']='UNKNOWN'
        elif route.endswith('/complete'):
            self.assertIsNotNone(self.receipt['providerRequestId'])
            self.receipt.update(status='COMPLETE',responseArtifactId=body['responseArtifactId'])
            if self.lost_complete:
                self.lost_complete=False
                raise Pending('lost_complete')
        else: raise AssertionError(route)

    def commit(self,scope,invocation,request_digest,envelope):
        self.envelope=envelope
        return self.artifact

    def find(self,scope,invocation,request_digest): return self.artifact if self.envelope else None
    def read(self,scope,invocation,request_digest,reference): return self.envelope
    def require_verified(self,scope,invocation,request_digest,reference):
        self.assertEqual(self.scope,scope)
        self.assertEqual(self.artifact,reference)
        self.assertEqual(request_digest,self.envelope['body']['request_digest'])

    def test_dispatch_completes_only_after_canonical_claim_and_evidence(self):
        invocation=self.host.submit(self.request,self.lease)
        self.assertEqual(self.id,invocation)
        self.assertEqual('COMPLETE',self.receipt['status'])
        self.assertEqual(1,self.executions)
        self.assertEqual(invocation,self.host.poll(invocation,self.request,self.lease)['body']['invocation_id'])

    def test_lost_claim_never_executes_native_tool(self):
        self.lost_claim=True
        with self.assertRaises(Pending): self.host.submit(self.request,self.lease)
        self.assertEqual(0,self.executions)
        self.assertEqual(self.id,self.host.reconcile(self.request,self.lease))
        self.assertIsNone(self.host.poll(self.id,self.request,self.lease))

    def test_unknown_native_outcome_is_not_retried(self):
        self.failure=True
        with self.assertRaises(Pending): self.host.submit(self.request,self.lease)
        self.assertEqual(self.id,self.host.reconcile(self.request,self.lease))
        with self.assertRaises(Denied): self.host.submit(self.request,self.lease)
        self.assertEqual(1,self.executions)

    def test_lost_completion_reconciles_existing_artifact(self):
        self.lost_complete=True
        with self.assertRaises(Pending): self.host.submit(self.request,self.lease)
        self.assertEqual(self.id,self.host.reconcile(self.request,self.lease))
        self.assertIsNotNone(self.host.poll(self.id,self.request,self.lease))
        self.assertEqual(1,self.executions)

    def test_invalid_sandbox_proof_denied_before_inspection(self):
        self.bad_attestation=True
        with self.assertRaises(Denied): self.host.admit(self.request,self.lease)
        self.assertEqual(0,self.inspections)

    def test_canonical_context_cannot_cross_tenant(self):
        self.context['tenantId']=str(uuid4())
        with self.assertRaises(Denied): self.host.submit(self.request,self.lease)
        self.assertEqual(0,self.executions)
