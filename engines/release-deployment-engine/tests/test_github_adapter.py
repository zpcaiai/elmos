import base64
from dataclasses import asdict, replace
import copy
import unittest

from elmos_release_deployment.contracts import Scope, CapabilityLease, Denied, Pending, canonical, digest
from elmos_release_deployment.github_adapter import GitHubRepositoryBinding, GitHubProposalAdapter
from test_runtime import FixtureAuthority


class GitHubTests(unittest.TestCase):
    def setUp(self):
        self.scope = Scope('t','w','p','e','a')
        self.lease = CapabilityLease('lease', self.scope, 'deployment', digest(b'plan'), ('repo','app'),
                                    frozenset({'gitops.proposal','gitops.reconcile'}), 0, 1200, 'session')
        self.binding = GitHubRepositoryBinding(self.scope,'repo',42,'owner','repo','main','deploy/test','app')
        self.authority = FixtureAuthority()
        self.adapter = GitHubProposalAdapter([self.binding],self,self.authority,lambda:1000)
        self.request = {'plan': {'scope': asdict(self.scope), 'repository_id':'repo','branch':'main',
            'base_commit':'a'*40, 'directory':'deploy/test','application_id':'app','mode':'proposal'},
            'files': {'deploy/test/app.json': {'kind':'Deployment'}}, 'operation_key':'key'}
        self.calls, self.lost, self.merged, self.drift, self.proposals = [], False, False, False, []

    def call(self,binding,method,route,body,query,lease):
        self.calls.append((method,route,body))
        if method == 'POST':
            if route == '/git/trees': return {'sha':'b'*40}
            if route == '/git/commits': return {'sha':'c'*40}
            if route == '/git/refs': return {'ref':body['ref'],'object':{'sha':body['sha']}}
            if route == '/pulls':
                self.proposals = [{'number':1}]
                if self.lost: raise Pending('lost_response')
                return {'number':1}
        if route == '': return {'id':42}
        if route == '/branches/main': return {'protected':True,'commit':{'sha':'a'*40}}
        if route == '/git/commits/'+'a'*40: return {'sha':'a'*40,'tree':{'sha':'b'*40}}
        if route in ('/git/commits/'+'c'*40, '/git/commits/'+'d'*40):
            return {'sha':route.rsplit('/',1)[1],'tree':{'sha':'b'*40},'parents':[{'sha':'a'*40}]}
        if route == '/git/trees/'+'b'*40: return {'truncated':False,'tree':[
            {'path':'deploy/test/app.json','mode':'100644','type':'blob','sha':'e'*40}]}
        if route == '/pulls': return self.proposals
        if route == '/pulls/1': return {'number':1,'head':{'ref':self.adapter._head(self.request),
            'sha':'c'*40,'repo':{'id':42}},'base':{'ref':'main','repo':{'id':42}},'changed_files':1,
            'merged':self.merged,'merge_commit_sha':'d'*40 if self.merged else None,'state':'closed' if self.merged else 'open'}
        if route == '/pulls/1/files': return [{'filename':'deploy/test/app.json','status':'modified'}]
        if route == '/contents/deploy/test/app.json': return {'type':'file','path':'deploy/test/app.json',
            'encoding':'base64','sha':'e'*40,'content':base64.b64encode(b'changed' if self.drift else
                canonical(self.request['files']['deploy/test/app.json'])).decode()}
        raise AssertionError((method,route))

    def test_proposal_creates_only_immutable_objects_branch_and_pr(self):
        invocation = self.adapter.propose(self.request,self.lease)
        receipt = self.adapter.poll(invocation,self.request,self.lease)['body']
        self.assertFalse(receipt['merged'])
        self.assertEqual('c'*40,receipt['commit'])
        self.assertEqual(['/git/trees','/git/commits','/git/refs','/pulls'],
                         [route for method,route,body in self.calls if method=='POST'])

    def test_lost_pr_response_reconciles_without_writes(self):
        self.lost=True
        with self.assertRaises(Pending): self.adapter.propose(self.request,self.lease)
        self.calls=[]
        self.assertEqual('1',self.adapter.reconcile(self.request,self.lease))
        self.adapter.poll('1',self.request,self.lease)
        self.assertTrue(all(method=='GET' for method,_,_ in self.calls))

    def test_reconcile_mode_reuses_same_proposal_and_observes_merged_commit(self):
        self.adapter.propose(self.request,self.lease)
        request = copy.deepcopy(self.request)
        request['plan']['mode']='reconcile'
        self.merged=True
        self.calls=[]
        invocation=self.adapter.propose(request,self.lease)
        receipt=self.adapter.poll(invocation,request,self.lease)['body']
        self.assertEqual('d'*40,receipt['commit'])
        self.assertTrue(all(method=='GET' for method,_,_ in self.calls))

    def test_missing_proposal_stays_pending(self):
        self.request['plan']['mode']='reconcile'
        with self.assertRaises(Pending): self.adapter.propose(self.request,self.lease)
        self.assertTrue(all(method=='GET' for method,_,_ in self.calls))

    def test_content_drift_and_path_escape_rejected(self):
        self.drift=True
        with self.assertRaisesRegex(Denied,'github_file_content_drift'):
            self.adapter.poll('1',self.request,self.lease)
        self.calls=[]
        self.request['files']={'deploy/test/../secret.json':{}}
        with self.assertRaises(Denied): self.adapter.propose(self.request,self.lease)
        self.assertEqual([],self.calls)

    def test_cross_tenant_lease_has_no_provider_calls(self):
        with self.assertRaises(Denied):
            self.adapter.propose(self.request,replace(self.lease,scope=replace(self.scope,tenant_id='other')))
        self.assertEqual([],self.calls)
