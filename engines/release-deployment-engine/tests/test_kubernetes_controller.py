from dataclasses import asdict, replace
import copy
from pathlib import Path
import tempfile
import unittest
from elmos_release_deployment.contracts import Artifact, Scope, CapabilityLease, digest, Pending, Denied
from elmos_release_deployment.extensions import KubernetesProvider
from elmos_release_deployment.kubernetes_controller import KubernetesDeploymentController
from elmos_release_deployment.journal import Journal
from test_runtime import FixtureAuthority


class KubernetesControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.scope=Scope('t','w','p','e','a')
        self.journal=Journal(Path(self.tmp.name)/'db')
        self.resource='cluster/ns/deployments/app'
        self.journal.admit(self.scope,'deployment','idem','ticket',{},(self.resource,),1)
        self.lease=CapabilityLease('lease',self.scope,'deployment',digest(b'plan'),(self.resource,),
                                  frozenset({'kubernetes.apply'}),1,1200,'session')
        artifact=Artifact('app','registry.example.test/app',*(digest(x) for x in (b'i',b's',b'p',b'v')),'python',8080)
        self.manifest=KubernetesProvider.deployment(self.scope,'ns','app',(artifact,),2,'config',())
        self.authority=FixtureAuthority()
        self.controller=KubernetesDeploymentController(self.journal,self,self.authority,self.scope,'cluster','ns',lambda:1000)
        self.observed=copy.deepcopy(self.manifest)
        self.observed['metadata'].update(uid='uid',resourceVersion='1',generation=1)
        self.calls=[]
        self.lost=False

    def approval(self):
        request=KubernetesProvider.apply_request(self.manifest,'1')
        request['body']['metadata']['uid']='uid'
        plan={'scope':asdict(self.scope),'cluster_id':'cluster','namespace':'ns','expected_uid':'uid','request':request}
        return self.authority.seal('kubernetes_apply_approval',{'operation_digest':digest(plan),
            'deployment_id':'deployment','plan_digest':self.lease.plan_digest,'generation':1,'expires_at':1100})

    def request(self,method,path,query,body,lease):
        self.calls.append(method)
        if method=='PATCH':
            self.assertNotIn('force',query)
            self.observed=copy.deepcopy(body)
            self.observed['metadata'].update(generation=2,resourceVersion='2')
            self.observed['status']={'observedGeneration':2,'replicas':2,'updatedReplicas':2,
                'readyReplicas':2,'availableReplicas':2,'conditions':[{'type':'Available','status':'True'},
                                                                  {'type':'Progressing','status':'True'}]}
            if self.lost: raise TimeoutError()
        return copy.deepcopy(self.observed)

    def test_apply_waits_for_exact_generation_and_replay_is_read_only(self):
        result=self.controller.apply(self.manifest,'uid','1',self.approval(),self.lease)
        self.assertEqual('ROLLOUT_OBSERVED',result['status'])
        self.assertEqual(result,self.controller.apply(self.manifest,'uid','1',self.approval(),self.lease))
        self.assertEqual(1,self.calls.count('PATCH'))

    def test_unknown_never_reapplies(self):
        self.lost=True
        with self.assertRaises(TimeoutError): self.controller.apply(self.manifest,'uid','1',self.approval(),self.lease)
        with self.assertRaises(Pending): self.controller.apply(self.manifest,'uid','1',self.approval(),self.lease)
        self.assertEqual(1,self.calls.count('PATCH'))

    def test_uid_replacement_rejected_before_mutation(self):
        self.observed['metadata']['uid']='other'
        with self.assertRaises(Denied): self.controller.apply(self.manifest,'uid','1',self.approval(),self.lease)
        self.assertEqual(['GET'],self.calls)


if __name__=='__main__': unittest.main()
