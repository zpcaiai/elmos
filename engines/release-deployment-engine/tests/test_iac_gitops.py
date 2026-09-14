from dataclasses import asdict, replace
from pathlib import Path
import tempfile
import unittest
from elmos_release_deployment.contracts import Scope, CapabilityLease, Artifact, digest, Pending, Denied
from elmos_release_deployment.journal import Journal
from elmos_release_deployment.extensions import KubernetesProvider
from elmos_release_deployment.native_iac import TerraformController
from elmos_release_deployment.gitops_controller import GitOpsController
from test_runtime import FixtureAuthority


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.scope=Scope('t','w','p','e','a')
        self.authority=FixtureAuthority()
        self.journal=Journal(Path(self.tmp.name)/'db')
        self.journal.admit(self.scope,'deployment','idem','ticket',{},('resource','repo','app'),1)
        self.lease=CapabilityLease('lease',self.scope,'deployment',digest(b'plan'),('resource','repo','app'),
                                  frozenset({'iac.apply','iac.destroy','gitops.proposal','gitops.reconcile'}),0,1200,'session')
        self.submits=0
        self.lost=False
        self.wrong_resources=False
        self.merged=False
        self.runtime_commit='a'*40

    def approval(self,purpose,plan):
        fields={'operation_digest':digest(plan),'deployment_id':'deployment','generation':0,'expires_at':1100}
        fields['deployment_plan_digest' if purpose=='native_iac_approval' else 'plan_digest']=self.lease.plan_digest
        return self.authority.seal(purpose,fields)

    def admit(self,request,lease):
        return self.authority.seal('iac_sandbox_admission',{'request_digest':digest(request),'isolated':True,
            'providers_pinned':True,'plan_mode':request['mode'],'plan_resources':['resource'],
            'before_state_digest':request['before_state_digest']})

    def submit(self,request,lease):
        self.submits+=1
        if self.lost: raise TimeoutError()
        return 'invocation'

    propose=submit

    def reconcile(self,request,lease): return None

    def poll(self,invocation,request,lease):
        if 'mode' in request:
            return self.authority.seal('iac_native_result',{'request_digest':digest(request),'invocation_id':invocation,
                'exit_code':0,'state_digest':digest(b'state'),'resource_addresses':
                ['wrong'] if self.wrong_resources else ([] if request['mode']=='destroy' else ['resource']),
                'state_lineage':'lineage','state_serial':2,'stdout_digest':digest(b''),'stderr_digest':digest(b''),
                'refresh_verified':True})
        return self.authority.seal('gitops_scm_receipt',{'request_digest':digest(request),'invocation_id':invocation,
            'repository_id':'repo','base_commit':request['plan']['base_commit'],'commit':'a'*40,
            'files_digest':digest(request['files']),'proposal_id':'pr-1','merged':self.merged})

    def observe(self,application,lease):
        return self.authority.seal('gitops_runtime_receipt',{'scope':asdict(self.scope),'application_id':'app',
            'repository_id':'repo','observed_at':1000,'commit':self.runtime_commit,'sync':'Synced','health':'Healthy',
            'resources':['ns/Deployment/app'],'pruned_resources':[]})

    def iac_plan(self,mode='apply'):
        return {'scope':asdict(self.scope),'workspace_id':'w','runtime_digest':digest(b'runtime'),
                'configuration_digest':digest(b'config'),'lock_digest':digest(b'lock'),
                'saved_plan_digest':digest(mode),'before_state_digest':digest(b'before'),
                'expected_resources':['resource'],'mode':mode}

    def test_saved_apply_and_destroy_plans_have_separate_approvals(self):
        controller=TerraformController(self.journal,self,self.authority,lambda:1000,self.scope)
        for mode in ('apply','destroy'):
            plan=self.iac_plan(mode)
            receipt=controller.execute(plan,self.approval('native_iac_approval',plan),self.lease)
            self.assertEqual([] if mode=='destroy' else ['resource'],receipt['resource_addresses'])
        self.assertEqual(2,self.submits)

    def test_iac_unknown_never_resubmits(self):
        controller=TerraformController(self.journal,self,self.authority,lambda:1000,self.scope)
        plan=self.iac_plan()
        self.lost=True
        with self.assertRaises(TimeoutError): controller.execute(plan,self.approval('native_iac_approval',plan),self.lease)
        with self.assertRaises(Pending): controller.execute(plan,self.approval('native_iac_approval',plan),self.lease)
        self.assertEqual(1,self.submits)

    def test_unknown_extension_blocks_primary_workflow_and_new_effects(self):
        plan=self.iac_plan()
        self.lost=True
        controller=TerraformController(self.journal,self,self.authority,lambda:1000,self.scope)
        with self.assertRaises(TimeoutError): controller.execute(plan,self.approval('native_iac_approval',plan),self.lease)
        with self.assertRaises(Pending):
            self.journal.transition(self.scope,'deployment','REQUESTED','POLICY_CHECKED',1000)
        with self.assertRaises(Pending):
            self.journal.begin_step(self.scope,'deployment','runtime.activate',{},1000,True)
        self.assertEqual(1,self.journal.load(self.scope,'deployment')['active'])

    def test_api_derives_scope_and_lease_from_authenticated_deployment(self):
        from elmos_release_deployment.api import DeploymentAPI
        from elmos_release_deployment.contracts import Principal
        from elmos_release_deployment.extension_service import DeploymentExtensionService
        self.lease=replace(self.lease,plan_digest=digest({}))
        controller=TerraformController(self.journal,self,self.authority,lambda:1000,self.scope)
        extensions=DeploymentExtensionService(self.journal,self.authority,None,None,controller,None,None)
        api=DeploymentAPI(None,None,extensions=extensions)
        principal=Principal('actor',self.scope,frozenset({'iac.apply'}))
        plan=self.iac_plan()
        body={'plan':{k:v for k,v in plan.items() if k!='scope'},'approval':self.approval('native_iac_approval',plan)}
        result=api.dispatch(principal,'POST','/v1/deployments/deployment/extensions/iac-apply',body)
        self.assertEqual(['resource'],result['resource_addresses'])
        with self.assertRaises(Denied):
            api.dispatch(principal,'POST','/v1/deployments/deployment/extensions/iac-apply',
                         {**body,'plan':plan})

    def test_completed_iac_integrates_with_full_workflow_evidence(self):
        import json, jsonschema
        from test_runtime import RuntimeTest
        fixture=RuntimeTest('test_success_commits_immutable_exact_evidence')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        deployment=fixture.deploy()
        plan={**self.iac_plan(),'scope':asdict(fixture.scope),'workspace_id':fixture.scope.workspace_id}
        lease=fixture.authority.lease(fixture.principal,deployment,fixture.plan.plan_digest,
                                       ('resource',),'iac.apply',0)
        approval=fixture.authority.seal('native_iac_approval',{'operation_digest':digest(plan),
            'deployment_id':deployment,'deployment_plan_digest':fixture.plan.plan_digest,
            'generation':0,'expires_at':1100})
        TerraformController(fixture.journal,self,fixture.authority,lambda:1000,fixture.scope).execute(plan,approval,lease)
        self.assertEqual('SUCCEEDED',fixture.finish(deployment))
        evidence=fixture.journal.evidence(fixture.scope,deployment)
        extension=next(step for step in evidence['steps'] if step['name'].startswith('iac.'))
        self.assertEqual('IAC_STATE_RECONCILED',extension['observed_status'])
        self.assertNotIn('artifact_uri',extension)
        schema_path=Path(__file__).resolve().parents[3]/'skills/elmos-release-deployment-skills-v1.0.0/elmos-release-deployment/schemas/deployment-evidence.schema.json'
        jsonschema.validate(evidence,json.loads(schema_path.read_text()))

    def test_iac_resource_drift_does_not_complete(self):
        self.wrong_resources=True
        plan=self.iac_plan()
        with self.assertRaises(Denied):
            TerraformController(self.journal,self,self.authority,lambda:1000,self.scope).execute(
                plan,self.approval('native_iac_approval',plan),self.lease)
        self.assertEqual('ACCEPTED',self.journal.steps(self.scope,'deployment')[0]['status'])

    def gitops_plan(self,mode):
        artifact=Artifact('app','registry.example.test/app',*(digest(b'x') for _ in range(4)),'python',8080)
        manifests=[KubernetesProvider.deployment(self.scope,'ns','app',(artifact,),1,'config',())]
        plan={'scope':asdict(self.scope),'repository_id':'repo','branch':'codex/deploy','base_commit':'b'*40,
              'directory':'deploy/app','chart_digest':digest(b'chart'),'manifest_digest':digest(manifests),
              'namespace':'ns','application_id':'app','mode':mode}
        return plan,manifests

    def test_proposal_never_claims_runtime_execution(self):
        plan,manifests=self.gitops_plan('proposal')
        result=GitOpsController(self.journal,self,self,self.authority,self.scope,lambda:1000).publish(
            plan,manifests,self.approval('gitops_publication_approval',plan),self.lease)
        self.assertEqual('NOT_RUN',result['runtime'])

    def test_manifest_name_cannot_escape_authorized_directory(self):
        plan,manifests=self.gitops_plan('proposal')
        manifests[0]['metadata']['name']='../../outside'
        plan['manifest_digest']=digest(manifests)
        with self.assertRaisesRegex(Denied,'resource_name'):
            GitOpsController(self.journal,self,self,self.authority,self.scope,lambda:1000).publish(
                plan,manifests,self.approval('gitops_publication_approval',plan),self.lease)
        self.assertEqual(0,self.submits)

    def test_reconcile_requires_governed_merge_and_exact_runtime_commit(self):
        plan,manifests=self.gitops_plan('reconcile')
        controller=GitOpsController(self.journal,self,self,self.authority,self.scope,lambda:1000)
        approval=self.approval('gitops_publication_approval',plan)
        with self.assertRaises(Pending): controller.publish(plan,manifests,approval,self.lease)
        self.merged=True
        self.runtime_commit='c'*40
        with self.assertRaises(Pending): controller.publish(plan,manifests,approval,self.lease)
        self.runtime_commit='a'*40
        self.assertEqual('GITOPS_CONVERGED',controller.publish(plan,manifests,approval,self.lease)['status'])
        self.assertEqual(1,self.submits)
