"""Digest-bound Helm rendering and governed GitOps publication/reconciliation."""
from dataclasses import asdict
import json
import re

from .contracts import Pending, canonical, digest, require, sha
from .extensions import HelmGitOpsBridge
from .service import verified


class GitOpsController:
    def __init__(self,journal,scm,gitops,trust,scope,clock):
        self.journal,self.scm,self.gitops,self.trust,self.scope,self.clock=journal,scm,gitops,trust,scope,clock

    def publish(self,plan,manifests,approval,lease):
        require(set(plan)=={'scope','repository_id','branch','base_commit','directory','chart_digest',
                            'manifest_digest','namespace','application_id','mode'},'gitops_plan_fields')
        require(plan['scope']==asdict(self.scope),'gitops_scope')
        require(plan['mode'] in {'proposal','reconcile'},'gitops_mode')
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_/-]{0,127}',plan['branch']) is not None
                and '..' not in plan['branch'] and '//' not in plan['branch']
                and not plan['branch'].endswith('/'),'gitops_branch')
        require(re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*',plan['directory']) is not None
                and len(plan['directory'])<=200,'gitops_directory')
        require(digest(manifests)==plan['manifest_digest'],'gitops_manifest_binding')
        HelmGitOpsBridge.proposal(self.scope,plan['chart_digest'],manifests,{plan['namespace']},plan['base_commit'])
        for manifest in manifests:
            name=manifest['metadata'].get('name')
            require(type(name) is str and len(name)<=63 and
                    re.fullmatch(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?',name) is not None,'gitops_resource_name')
        files={plan['directory']+'/'+m['metadata']['name']+'.json':m for m in manifests}
        require(len(files)==len(manifests),'gitops_filename_collision')
        body=verified(self.trust,'gitops_publication_approval',approval)
        require(body=={'operation_digest':digest(plan),'deployment_id':lease.deployment_id,
                       'plan_digest':lease.plan_digest,'generation':lease.generation,
                       'expires_at':body.get('expires_at')},'gitops_approval_binding')
        require(type(body['expires_at']) is int and self.clock()<body['expires_at'],'gitops_approval_expired')
        lease.check(self.scope,lease.deployment_id,lease.plan_digest,(plan['repository_id'],plan['application_id']),
                    'gitops.'+plan['mode'],self.clock(),lease.generation)
        operation='gitops.'+plan['mode']+':'+digest(plan)[7:]
        request={'plan':plan,'files':files,'operation_key':operation}
        row,fresh=self.journal.begin_step(self.scope,lease.deployment_id,operation,request,self.clock(),True,
            expected_version=lease.generation,
            resource_locks=(digest(['gitops',plan['repository_id'],plan['branch'],plan['directory']]),))
        if row['status']=='COMPLETE': return json.loads(row['result'])
        if fresh:
            # Host SCM checks provider-instance/native repository ID, base commit,
            # exact path grant and current branch protection before publication.
            invocation=self.scm.propose(request,lease)
            self.journal.accepted(self.scope,lease.deployment_id,operation,invocation)
        else:
            invocation=row['invocation']
            if invocation is None:
                invocation=self.scm.reconcile(request,lease)
                if invocation is None: raise Pending('gitops_publication_unknown')
                self.journal.accepted(self.scope,lease.deployment_id,operation,invocation)
        envelope=self.scm.poll(invocation,request,lease)
        if envelope is None: raise Pending('gitops_proposal_pending')
        receipt=verified(self.trust,'gitops_scm_receipt',envelope)
        require(set(receipt)=={'request_digest','invocation_id','repository_id','base_commit','commit','files_digest',
                               'proposal_id','merged'},'gitops_receipt_fields')
        require(receipt['request_digest']==digest(request) and receipt['invocation_id']==invocation
                and receipt['repository_id']==plan['repository_id'] and receipt['base_commit']==plan['base_commit']
                and receipt['files_digest']==digest(files) and type(receipt['merged']) is bool,'gitops_scm_binding')
        require(re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',receipt['commit']) is not None,'gitops_commit')
        if plan['mode']=='proposal':
            require(receipt['merged'] is False,'gitops_unexpected_merge')
            result={'status':'PROPOSED','scm_receipt':receipt,'runtime':'NOT_RUN'}
        else:
            if not receipt['merged']: raise Pending('gitops_waiting_for_governed_merge')
            observed=verified(self.trust,'gitops_runtime_receipt',self.gitops.observe(plan['application_id'],lease))
            expected_resources=sorted(m['metadata']['namespace']+'/Deployment/'+m['metadata']['name'] for m in manifests)
            require(observed.get('scope')==asdict(self.scope) and observed.get('application_id')==plan['application_id']
                    and observed.get('repository_id')==plan['repository_id'],'gitops_application_binding')
            require(type(observed.get('observed_at')) is int and self.clock()-60<=observed['observed_at']<=self.clock(),
                    'gitops_stale_observation')
            if observed.get('commit')!=receipt['commit'] or observed.get('sync')!='Synced' or observed.get('health')!='Healthy':
                raise Pending('gitops_runtime_not_converged')
            require(observed.get('resources')==expected_resources and observed.get('pruned_resources')==[],
                    'gitops_resource_scope_drift')
            result={'status':'GITOPS_CONVERGED','scm_receipt':receipt,'runtime_receipt':observed,'business_smoke':'NOT_RUN'}
        self.journal.complete_step(self.scope,lease.deployment_id,operation,result,self.clock())
        return result


class HelmRenderer:
    def __init__(self,runner,trust,clock): self.runner,self.trust,self.clock=runner,trust,clock

    def render(self,scope,chart_digest,values_digest,lock_digest,runtime_digest,namespace,release_name,lease):
        for value in (chart_digest,values_digest,lock_digest,runtime_digest): sha(value)
        for value in (namespace,release_name):
            require(re.fullmatch(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?',value) is not None and len(value)<=53,'helm_name')
        lease.check(scope,lease.deployment_id,lease.plan_digest,(chart_digest,),
                    'helm.render',self.clock(),lease.generation)
        request={'scope':asdict(scope),'chart_digest':chart_digest,'values_digest':values_digest,
                 'lock_digest':lock_digest,'runtime_digest':runtime_digest,
                 'argv':['helm','template',release_name,'/input/chart','--namespace',namespace,
                         '--values','/input/values.json','--skip-tests'],
                 'network':'none','timeout_seconds':60,'max_output_bytes':1048576}
        result=verified(self.trust,'helm_render_receipt',self.runner.render(request,lease))
        require(result.get('request_digest')==digest(request) and type(result.get('exit_code')) is int
                and result['exit_code']==0
                and result.get('dependencies_verified') is True,'helm_render_failed')
        manifests=result.get('manifests')
        require(len(canonical(manifests))<=1048576,'helm_output_bounds')
        HelmGitOpsBridge.proposal(scope,chart_digest,manifests,{namespace},'0'*40)
        return manifests
