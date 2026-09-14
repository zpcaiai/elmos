from dataclasses import replace
import copy
import unittest
from elmos_release_deployment.contracts import Scope, CapabilityLease, Denied, Pending, digest
from elmos_release_deployment.flux_adapter import FluxBinding, FluxAdapter
from test_runtime import FixtureAuthority


class FluxTests(unittest.TestCase):
    def setUp(self):
        self.scope=Scope('t','w','p','e','a')
        self.lease=CapabilityLease('l',self.scope,'d',digest(b'p'),('app','repo'),
                                   frozenset({'gitops.reconcile'}),0,1100,'session')
        revision='main@sha1:'+('a'*40)
        spec={'prune':False,'wait':True,'sourceRef':{'kind':'GitRepository','name':'repo'},'path':'./deploy'}
        source_spec={'url':'https://github.com/example/repo','ref':{'branch':'main'}}
        self.binding=FluxBinding(self.scope,'app','repo','flux-system','app','app-uid',digest(spec),
                                 'repo','source-uid',digest(source_spec),('test/Deployment/app',))
        ready={'observedGeneration':1,'conditions':[{'type':'Ready','status':'True','observedGeneration':1}]}
        self.app={'metadata':{'namespace':'flux-system','name':'app','uid':'app-uid','generation':1},
            'spec':spec,'status':{**copy.deepcopy(ready),'lastAppliedRevision':revision,'lastAttemptedRevision':revision,
                'inventory':{'entries':[{'id':'test_app_apps_Deployment','v':'v1'}]},
                'history':[{'lastReconciled':'1970-01-01T00:16:40Z','lastReconciledStatus':'ReconciliationSucceeded',
                            'metadata':{'revision':revision},'digest':digest(b'manifests')}]}}
        self.source={'metadata':{'namespace':'flux-system','name':'repo','uid':'source-uid','generation':1},
                     'spec':source_spec,'status':{**copy.deepcopy(ready),'artifact':{'revision':revision}}}
        self.calls=[]
        self.adapter=FluxAdapter([self.binding],self,FixtureAuthority(),lambda:1000)
        self.race=False

    def read(self,binding,source,lease):
        self.calls.append(source)
        result=copy.deepcopy(self.source if source else self.app)
        if self.race and len(self.calls)==3: result['metadata']['generation']=2
        return result

    def test_exact_flux_revision_and_inventory(self):
        body=self.adapter.observe('app',self.lease)['body']
        self.assertEqual('a'*40,body['commit'])
        self.assertEqual(['test/Deployment/app'],body['resources'])
        self.assertEqual([False,True,False],self.calls)

    def test_wrong_scope_before_provider(self):
        with self.assertRaises(Denied):
            self.adapter.observe('app',replace(self.lease,scope=replace(self.scope,tenant_id='other')))
        self.assertEqual([],self.calls)

    def test_stale_history_and_racing_observation_pending(self):
        self.app['status']['history'][0]['lastReconciled']='1970-01-01T00:00:00Z'
        with self.assertRaises(Pending): self.adapter.observe('app',self.lease)
        self.app['status']['history'][0]['lastReconciled']='1970-01-01T00:16:40Z'
        self.calls=[]; self.race=True
        with self.assertRaises(Pending): self.adapter.observe('app',self.lease)

    def test_prune_inventory_and_source_drift_rejected(self):
        original=copy.deepcopy(self.app)
        for mutate in (lambda d:d['spec'].update(prune=True),
                       lambda d:d['status']['inventory']['entries'].append({'id':'other_x_apps_Deployment','v':'v1'}),
                       lambda d:d['metadata'].update(uid='replacement')):
            self.app=copy.deepcopy(original); mutate(self.app)
            with self.assertRaises(Denied): self.adapter.observe('app',self.lease)

    def test_source_not_at_applied_revision_and_unobserved_generation_pending(self):
        self.source['status']['artifact']['revision']='main@sha1:'+('b'*40)
        with self.assertRaises(Pending): self.adapter.observe('app',self.lease)
        self.source['status']['artifact']['revision']='main@sha1:'+('a'*40)
        self.app['metadata']['generation']=2
        with self.assertRaises(Pending): self.adapter.observe('app',self.lease)
