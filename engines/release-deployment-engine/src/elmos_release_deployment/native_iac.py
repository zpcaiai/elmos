"""Saved-plan Terraform execution through a pinned, durable sandbox runner.

The runner owns credentials, process isolation, persistent workspace and native
result artifacts. This controller never runs archive-supplied programs locally.
"""
from dataclasses import asdict
import json

from .contracts import Pending, digest, require, sha
from .service import verified


class TerraformController:
    def __init__(self,journal,runner,trust,clock,scope):
        self.journal,self.runner,self.trust,self.clock,self.scope=journal,runner,trust,clock,scope

    def execute(self,plan,approval,lease):
        require(set(plan)=={'scope','workspace_id','runtime_digest','configuration_digest','lock_digest',
                            'saved_plan_digest','before_state_digest','expected_resources','mode'},'iac_fields')
        require(plan['scope']==asdict(self.scope) and plan['workspace_id']==self.scope.workspace_id,'iac_scope')
        require(plan['mode'] in {'apply','destroy'},'iac_mode')
        for field in ('runtime_digest','configuration_digest','lock_digest','saved_plan_digest','before_state_digest'):
            sha(plan[field])
        resources=plan['expected_resources']
        require(type(resources) is list and 0<len(resources)<=100 and len(resources)==len(set(resources))
                and all(type(r) is str and 0<len(r)<=256 for r in resources),'iac_resources')
        body=verified(self.trust,'native_iac_approval',approval)
        require(body=={'operation_digest':digest(plan),'deployment_id':lease.deployment_id,
                       'deployment_plan_digest':lease.plan_digest,'generation':lease.generation,
                       'expires_at':body.get('expires_at')},'iac_approval_binding')
        require(type(body['expires_at']) is int and self.clock()<body['expires_at'],'iac_approval_expired')
        lease.check(self.scope,lease.deployment_id,lease.plan_digest,resources,
                    'iac.'+plan['mode'],self.clock(),lease.generation)
        operation='iac.'+plan['mode']+':'+digest(plan)[7:]
        request={'scope':asdict(self.scope),'operation_key':operation,'runtime_digest':plan['runtime_digest'],
                 'workspace_id':plan['workspace_id'],'configuration_digest':plan['configuration_digest'],
                 'lock_digest':plan['lock_digest'],'saved_plan_digest':plan['saved_plan_digest'],
                 'before_state_digest':plan['before_state_digest'],
                 'argv':['terraform','apply','-input=false','-lock=true','-lock-timeout=60s','/input/approved.tfplan'],
                 'timeout_seconds':1800,'mode':plan['mode']}
        row,fresh=self.journal.begin_step(self.scope,lease.deployment_id,operation,request,self.clock(),True,
            expected_version=lease.generation,
            resource_locks=(digest(['terraform-state',self.scope.tenant_id,plan['workspace_id']]),))
        if row['status']=='COMPLETE': return json.loads(row['result'])
        if fresh:
            # Admission verifies the native plan is derived from these exact source,
            # provider-lock and previous-state bytes, including a saved destroy plan.
            attestation=verified(self.trust,'iac_sandbox_admission',self.runner.admit(request,lease))
            require(attestation=={'request_digest':digest(request),'isolated':True,'providers_pinned':True,
                                  'plan_mode':plan['mode'],'plan_resources':sorted(resources),
                                  'before_state_digest':plan['before_state_digest']},'iac_sandbox_binding')
            invocation=self.runner.submit(request,lease)
            self.journal.accepted(self.scope,lease.deployment_id,operation,invocation)
        else:
            invocation=row['invocation']
            if invocation is None:
                invocation=self.runner.reconcile(request,lease)
                if invocation is None: raise Pending('iac_dispatch_unknown')
                self.journal.accepted(self.scope,lease.deployment_id,operation,invocation)
        envelope=self.runner.poll(invocation,request,lease)
        if envelope is None: raise Pending('iac_native_running')
        result=verified(self.trust,'iac_native_result',envelope)
        require(set(result)=={'request_digest','invocation_id','exit_code','state_digest','resource_addresses',
                              'state_lineage','state_serial','stdout_digest','stderr_digest','refresh_verified'},'iac_result_fields')
        require(result['request_digest']==digest(request) and result['invocation_id']==invocation
                and type(result['exit_code']) is int and result['exit_code']==0 and result['refresh_verified'] is True,
                'iac_native_failed')
        require(type(result['state_serial']) is int and result['state_serial']>=0
                and type(result['state_lineage']) is str and result['state_lineage'],'iac_state_identity')
        for field in ('state_digest','stdout_digest','stderr_digest'): sha(result[field])
        expected=[] if plan['mode']=='destroy' else sorted(resources)
        require(result['resource_addresses']==expected,'iac_resource_reconciliation')
        result={**result,'status':'IAC_STATE_RECONCILED'}
        self.journal.complete_step(self.scope,lease.deployment_id,operation,result,self.clock())
        return result
