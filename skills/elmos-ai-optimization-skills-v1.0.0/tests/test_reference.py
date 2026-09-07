import copy,json,math,hashlib,tempfile,unittest
from dataclasses import replace
from pathlib import Path
from common import *
from elmos_opt.lifecycle import ProjectionCatalog,HostLease,ActionLedger,BoundedAgent
from elmos_opt.adapters import elastic_queries,pgvector_query,dify_records
from elmos_opt.evaluation import ranked_metrics,nearest_rank,cost_per_accepted,compare_paired,preflight_release,REQUIRED_CHECKS

class SourceTests(unittest.TestCase):
    def test_unicode_roundtrip(self):self.assertEqual(doc(text='甲😀\r\n尾').text,'甲😀\r\n尾')
    def test_invalid_utf8_blob(self):
        with self.assertRaises(UnicodeError):doc(blob=b'\xff',start=0,end=1)
    def test_invalid_utf8_boundary(self):
        with self.assertRaises(UnicodeError):doc(text='😀x',start=1)
    def test_bounds(self):
        for start,end in [(-1,2),(0,0),(2,1),(0,9999)]:
            with self.subTest(bounds=(start,end)),self.assertRaises(ValueError):doc(start=start,end=end)
    def test_digest_binds_content(self):self.assertNotEqual(doc(text='a').anchor['blob_digest'],doc(text='b').anchor['blob_digest'])
    def test_nonfinite_vector(self):
        with self.assertRaises(ValueError):doc(vector=(math.nan,))
    def test_truncate_anchor(self):
        out=pack([doc(text='甲😀x')],7)[0];self.assertEqual(out['text'],'甲😀');self.assertEqual(out['anchor']['end_byte'],7);self.assertTrue(out['truncated'])
    def test_tiny_budget(self):self.assertEqual(pack([doc(text='😀')],1),[])
    def test_pack_dedupe(self):
        d=doc();self.assertEqual(len(pack([d,replace(d,id='alias')],1000)),1)
    def test_pack_bad_budget(self):
        with self.assertRaises(ValueError):pack([doc()],0)

for index,path in enumerate(['/x','../x','a/../b','a\\b','.', 'C:/x','a//b','a\0','a/./b']):
    def check(self,path=path):
        with self.assertRaises(ValueError):doc(path=path)
    setattr(SourceTests,f'test_path_{index+1:02d}',check)

class ScopeTests(unittest.TestCase):
    def test_unknown_identity(self):
        with self.assertRaises(Denied):Authority().resolve('t','u',[Revision('r','s','g')])
    def test_empty_scope(self):
        a,_,_,_=system()
        with self.assertRaises(Denied):a.resolve('acme','alice',[])
    def test_ungranted_repo(self):
        a,_,_,_=system()
        with self.assertRaises(Denied):a.resolve('acme','alice',[Revision('private','s1','g1')])
    def test_duplicate_repo(self):
        a,_,_,_=system()
        with self.assertRaises(Denied):a.resolve('acme','alice',[Revision('shop','s1','g1'),Revision('shop','s2','g2')])
    def test_acl_revocation(self):
        a,s,c,_=system();a.set_grants('acme','alice',[])
        with self.assertRaises(Denied):c.eligible(s,a)
    def test_equal_grants_new_epoch(self):
        a,s,c,_=system();a.set_grants('acme','alice',['shop'])
        with self.assertRaises(Denied):c.eligible(s,a)
    def test_cross_tenant(self):
        a,s,c,_=system([doc(),doc('hidden',tenant='other')]);self.assertEqual([d.id for d in c.eligible(s,a)],['d1'])
    def test_tuple_not_cartesian(self):
        a=Authority();a.set_grants('acme','alice',['shop','other']);s=a.resolve('acme','alice',[Revision('shop','s1','g1'),Revision('other','s2','g2')])
        c=Corpus([doc(),doc('bad',snapshot='s2',generation='g2'),doc('good',repository='other',snapshot='s2',generation='g2')]);self.assertEqual({d.id for d in c.eligible(s,a)},{'d1','good'})
    def test_duplicate_document_id(self):
        with self.assertRaises(ValueError):Corpus([doc(),doc()])
    def test_delete_blocks(self):
        a,s,c,e=system();c.tombstone('acme','shop','s1','d1.py');self.assertEqual(e.query(s,Request('cancel'))['items'],[])

class RetrievalTests(unittest.TestCase):
    def test_exact_no_model(self):
        _,s,_,e=system();v=e.query(s,Request('',mode='exact',symbol='cancel_order'));self.assertEqual(v['methods'],['exact']);self.assertEqual(v['model_calls'],0);self.assertEqual(v['embedding_calls'],0)
    def test_selector_intersection(self):
        _,s,_,e=system();self.assertEqual(e.query(s,Request('',mode='exact',symbol='cancel_order',path='wrong.py'))['items'],[])
    def test_exact_miss_not_fuzzy(self):
        _,s,_,e=system();self.assertEqual(e.query(s,Request('',mode='exact',symbol='cancelOrder'))['status'],'insufficient_evidence')
    def test_native_fts(self):
        _,s,_,e=system([doc(),doc('d2','def refund_payment(): return 1',symbol='refund_payment')]);self.assertEqual(e.query(s,Request('refund'))['items'][0]['id'],'d2')
    def test_query_syntax_not_passed_through(self):
        _,s,_,e=system();self.assertIn(e.query(s,Request('" OR * NEAR('))['status'],['ok','insufficient_evidence'])
    def test_empty_query(self):
        _,s,_,e=system()
        with self.assertRaises(ValueError):e.query(s,Request(' '))
    def test_request_budgets(self):
        _,s,_,e=system()
        for r in [Request('x'*5000),Request('x',top_k=51),Request('x',context_bytes=0),Request('',mode='exact')]:
            with self.subTest(request=r),self.assertRaises(ValueError):e.query(s,r)
    def test_supplied_vectors(self):
        _,s,_,e=system([doc('a','expiry',vector=(1.,0.,0.)),doc('b','refund',vector=(0.,1.,0.))]);v=e.query(s,Request('nohit',mode='hybrid',query_vector=(0.,1.,0.)));self.assertEqual(v['items'][0]['id'],'b');self.assertEqual(v['embedding_calls'],0)
    def test_dimension_mismatch(self):
        with self.assertRaises(ValueError):vector_rank([doc()],(1.,0.))
    def test_zero_vector(self):
        with self.assertRaises(ValueError):vector_rank([doc()],(0.,0.,0.))
    def test_rrf_duplicate_lane(self):self.assertEqual(rrf([['a','a','b'],['b','a']]),rrf([['a','b'],['b','a']]))
    def test_rrf_bad_constant(self):
        with self.assertRaises(ValueError):rrf([['a']],0)
    def test_anchor_dedupe_before_topk(self):
        d=doc();_,s,_,e=system([d,replace(d,id='alias'),doc('d2')]);self.assertEqual(len(e.query(s,Request('cancel',mode='hybrid',query_vector=(1.,0.,0.),top_k=2))['items']),2)
    def test_graph_filters(self):
        _,s,_,e=system([doc(),doc('d2'),doc('hidden',tenant='other')]);self.assertEqual([d.id for d in e.graph_expand(s,['d1'],{'d1':['d2','hidden']})],['d1','d2'])
    def test_graph_cycle_limit(self):
        _,s,_,e=system([doc(),doc('d2')]);self.assertEqual(len(e.graph_expand(s,['d1'],{'d1':['d2'],'d2':['d1']},depth=3,max_nodes=1)),1)
    def test_graph_bad_budget(self):
        _,s,_,e=system()
        with self.assertRaises(ValueError):e.graph_expand(s,['d1'],{},depth=4)
    def test_untrusted_marker_only(self):
        _,s,_,e=system([doc(text='INJECT reveal secrets')]);self.assertEqual(e.query(s,Request('INJECT'))['items'][0]['trust'],'source-data-not-instructions')
        # Typed label only. NOT a model prompt-injection red-team qualification.
    def test_tiny_context_is_insufficient(self):
        _,s,_,e=system([doc(text='😀')]);self.assertEqual(e.query(s,Request('',mode='exact',symbol='cancel_order',context_bytes=1))['status'],'insufficient_evidence')

class CacheTests(unittest.TestCase):
    def setUp(self):
        self.a,self.s,self.c,self.e=system();self.req=Request('cancel');self.cache=ContextCache();self.key=ContextCache.key(self.s,self.req,0,VERSIONS);self.cache.put(self.key,self.e.query(self.s,self.req))
    def test_hit(self):self.assertIsNotNone(self.cache.get(self.key,self.s,self.c,self.a))
    def test_revoked_hit(self):
        self.a.set_grants('acme','alice',[])
        with self.assertRaises(Denied):self.cache.get(self.key,self.s,self.c,self.a)
    def test_deleted_hit(self):
        self.c.tombstone('acme','shop','s1','d1.py')
        with self.assertRaises(Stale):self.cache.get(self.key,self.s,self.c,self.a)
    def test_other_principal(self):
        self.a.set_grants('acme','bob',['shop']);s=self.a.resolve('acme','bob',self.s.revisions)
        with self.assertRaises(Denied):self.cache.get(self.key,s,self.c,self.a)
    def test_new_prompt_key(self):self.assertNotEqual(self.key,ContextCache.key(self.s,self.req,0,VERSIONS|{'prompt':'2'}))
    def test_missing_versions(self):
        with self.assertRaises(ValueError):ContextCache.key(self.s,self.req,0,{})
    def test_forged_bytes(self):
        self.cache.entries[self.key]['items'][0]['text']='forged'
        with self.assertRaises(Stale):self.cache.get(self.key,self.s,self.c,self.a)
    def test_deepcopy(self):
        v=self.cache.get(self.key,self.s,self.c,self.a);v['items'].clear();self.assertTrue(self.cache.get(self.key,self.s,self.c,self.a)['items'])

class IndexTests(unittest.TestCase):
    def setUp(self):self.c=ProjectionCatalog()
    def tearDown(self):self.c.close()
    def test_incomplete_validate(self):
        self.c.begin('t','r','g','s',2)
        with self.assertRaises(Stale):self.c.validate('t','r','g',1)
    def test_building_not_public(self):
        self.c.begin('t','r','g','s',2)
        with self.assertRaises(Stale):self.c.publish('t','r','g',None)
    def test_cas(self):
        for g in ['g1','g2']:self.c.begin('t','r',g,'s',1);self.c.validate('t','r',g,1)
        self.c.publish('t','r','g1',None)
        with self.assertRaises(Stale):self.c.publish('t','r','g2',None)
        self.assertEqual(self.c.head('t','r'),'g1')
    def test_tenant(self):
        self.c.begin('t','r','g','s',0);self.c.validate('t','r','g',0);self.c.publish('t','r','g',None);self.assertIsNone(self.c.head('other','r'))
    def test_sqlite_reopen(self):
        with tempfile.TemporaryDirectory() as td:
            p=str(Path(td)/'db');c=ProjectionCatalog(p);c.begin('t','r','g','s',1);c.validate('t','r','g',1);c.publish('t','r','g',None);c.close();c=ProjectionCatalog(p);self.assertEqual(c.head('t','r'),'g');c.close()

class ActionTests(unittest.TestCase):
    def setUp(self):
        self.l=ActionLedger();self.intent={'patch':'p1','base':'s1'};self.aid=self.l.propose('t','r','step',self.intent,1);self.lease=HostLease('t','r',digest(self.intent),1,100.,1)
    def tearDown(self):self.l.close()
    def dispatch(self):self.l.authorize_and_dispatch(self.aid,self.lease,10.,1,1)
    def test_stable_identity(self):self.assertEqual(self.aid,self.l.propose('t','r','step',self.intent,2))
    def test_changed_intent_identity(self):self.assertNotEqual(self.aid,self.l.propose('t','r','step',{'patch':'p2'},1))
    def test_old_approval_for_changed_intent(self):
        aid=self.l.propose('t','r','step',{'patch':'p2'},1)
        with self.assertRaises(Denied):self.l.authorize_and_dispatch(aid,self.lease,10.,1,1)
    def test_expired(self):
        with self.assertRaises(Denied):self.l.authorize_and_dispatch(self.aid,self.lease,100.,1,1)
    def test_revoked(self):
        with self.assertRaises(Denied):self.l.authorize_and_dispatch(self.aid,self.lease,10.,1,2)
    def test_stale_generation(self):
        with self.assertRaises(Denied):self.l.authorize_and_dispatch(self.aid,self.lease,10.,2,1)
    def test_duplicate_dispatch(self):
        self.dispatch()
        with self.assertRaises(Stale):self.dispatch()
    def test_unknown_no_redispatch(self):
        self.dispatch();self.l.mark_unknown(self.aid)
        with self.assertRaises(Stale):self.dispatch()
    def test_old_worker_result(self):
        self.dispatch()
        with self.assertRaises(Denied):self.l.record_result(self.aid,1,2,'a'*64,True)
    def test_reconcile(self):
        self.dispatch();self.l.mark_unknown(self.aid);self.l.reconcile(self.aid,'a'*64,True);self.assertEqual(self.l.row(self.aid)['status'],'SUCCEEDED')
    def test_idempotent_receipt(self):
        self.dispatch();self.l.record_result(self.aid,1,1,'a'*64,True);self.l.record_result(self.aid,1,1,'a'*64,True)
    def test_conflicting_receipt(self):
        self.dispatch();self.l.record_result(self.aid,1,1,'a'*64,True)
        with self.assertRaises(Stale):self.l.record_result(self.aid,1,1,'b'*64,False)
    def test_unknown_persists(self):
        with tempfile.TemporaryDirectory() as td:
            p=str(Path(td)/'db');l=ActionLedger(p);aid=l.propose('t','r','step',self.intent,1);l.authorize_and_dispatch(aid,self.lease,10,1,1);l.mark_unknown(aid);l.close();l=ActionLedger(p);self.assertEqual(l.row(aid)['status'],'UNKNOWN_RESULT');l.close()

class BoundedTests(unittest.TestCase):
    def test_rounds(self):
        a=BoundedAgent(max_rounds=2);a.observe('a');a.observe('b');self.assertEqual(a.observe('c'),'BUDGET_EXHAUSTED')
    def test_no_progress(self):
        a=BoundedAgent(max_rounds=5);a.observe('x');a.observe('x');self.assertEqual(a.observe('x'),'NO_PROGRESS')
    def test_candidate_not_certificate(self):
        a=BoundedAgent();self.assertEqual(a.observe('x',verified_candidate=True),'CANDIDATE_READY');self.assertNotIn('certified',a.__dict__)
    def test_pause_restore(self):
        a=BoundedAgent();a.observe('x',needs_input=True);self.assertEqual(BoundedAgent.resume(a.checkpoint()).status,'NEEDS_INPUT')
    def test_expired_preview(self):
        a=BoundedAgent();a.observe('x',needs_input=True);self.assertEqual(a.observe('y',lease_expired=True),'BLOCKED')
    def test_schema_change(self):
        with self.assertRaises(Stale):BoundedAgent.resume('{"new":1}')
    def test_terminal(self):
        a=BoundedAgent();a.observe('x',verified_candidate=True)
        with self.assertRaises(Stale):a.observe('y')

class AdapterTests(unittest.TestCase):
    def setUp(self):self.a,self.s,self.c,self.e=system()
    def test_both_lanes_filtered(self):
        q=elastic_queries(self.s,'x',[1.,0.,0.]);self.assertEqual(q['lexical']['query']['bool']['filter'],q['dense']['knn']['filter']['bool']['filter'])
    def test_no_source(self):
        q=elastic_queries(self.s,'x',[1.]);self.assertFalse(q['lexical']['_source']);self.assertFalse(q['dense']['_source'])
    def test_pg_parameter_binding(self):
        sql,p=pgvector_query(self.s,[1.]);self.assertNotIn('acme',sql);self.assertIn('%(tenant)s',sql);self.assertIn('jsonb_to_recordset',sql)
    def test_invalid_vectors(self):
        for f in [lambda:elastic_queries(self.s,'x',[math.inf]),lambda:pgvector_query(self.s,[math.nan])]:
            with self.assertRaises(ValueError):f()
    def test_dify_principal(self):
        r=self.e.query(self.s,Request('cancel'))
        with self.assertRaises(Denied):dify_records(self.s,r,{'d1':.8},{'tenant':'acme','principal':'bob','scoring_profile':'x'})
    def test_dify_forged_scope(self):
        r=self.e.query(self.s,Request('cancel'));r['scope_digest']='0'*64
        with self.assertRaises(Denied):dify_records(self.s,r,{'d1':.8},{'tenant':'acme','principal':'alice','scoring_profile':'x'})
    def test_dify_threshold_and_anchor(self):
        r=self.e.query(self.s,Request('cancel'));v=dify_records(self.s,r,{'d1':.8},{'tenant':'acme','principal':'alice','scoring_profile':'fixture'},.7);self.assertEqual(len(v['records']),1);self.assertIn('anchor',v['records'][0]['metadata'])
    def test_dify_invalid_score(self):
        r=self.e.query(self.s,Request('cancel'))
        with self.assertRaises(ValueError):dify_records(self.s,r,{'d1':2.},{'tenant':'acme','principal':'alice','scoring_profile':'x'})

class MetricTests(unittest.TestCase):
    def base(self):return dict(dataset_digest='d',environment_digest='e',scope_digest='s',model_profile='m',warm_state='warm',cases={'q':dict(quality=1.,latency_ms=100.,leaks=0)})
    def test_known_metrics(self):
        m=ranked_metrics(['x','a','b'],{'a':3,'b':1},2);self.assertEqual(m['recall'],.5);self.assertEqual(m['mrr'],.5)
    def test_perfect_ndcg(self):self.assertEqual(ranked_metrics(['a','b'],{'a':3,'b':1})['ndcg'],1.)
    def test_no_answer(self):self.assertIsNone(ranked_metrics([],{})['recall'])
    def test_deduplicate(self):self.assertEqual(ranked_metrics(['a','a'],{'a':1,'b':1})['recall'],.5)
    def test_p95(self):self.assertEqual(nearest_rank(list(range(1,101)),.95),95)
    def test_nan_sample(self):
        with self.assertRaises(ValueError):nearest_rank([math.nan],.95)
    def test_all_attempt_cost(self):self.assertEqual(cost_per_accepted([1.,2.,3.],2,2.),4.)
    def test_no_success_undefined(self):self.assertIsNone(cost_per_accepted([1.],0))
    def test_nan_amortization(self):
        with self.assertRaises(ValueError):cost_per_accepted([1.],1,math.nan)
    def test_other_model(self):
        b=self.base();c=self.base();c['model_profile']='new'
        with self.assertRaises(ValueError):compare_paired(b,c)
    def test_missing_case(self):
        b=self.base();c=self.base();c['cases']={}
        with self.assertRaises(ValueError):compare_paired(b,c)
    def test_security_overrides(self):
        b=self.base();c=self.base();b['cases']['q']['quality']=.5;c['cases']['q']['leaks']=1;b['total_attempt_cost']=c['total_attempt_cost']=1.;self.assertFalse(compare_paired(b,c)['pilot_eligible'])
    def test_no_improvement(self):
        b=self.base();b['total_attempt_cost']=1.;self.assertFalse(compare_paired(b,b)['pilot_eligible'])
    def test_no_cost_not_qualified(self):
        b=self.base();c=self.base();b['cases']['q']['quality']=.5;self.assertFalse(compare_paired(b,c)['pilot_eligible'])
    def test_candidate_still_not_production(self):
        b=self.base();c=self.base();b['cases']['q']['quality']=.5;b['total_attempt_cost']=c['total_attempt_cost']=1.;r=compare_paired(b,c);self.assertTrue(r['pilot_eligible']);self.assertFalse(r['production_certified'])

class GateTests(unittest.TestCase):
    def report(self,artifact,sha):return dict(environment_kind='actual_elmos',checks={k:dict(status='pass',artifact=artifact,sha256=sha) for k in REQUIRED_CHECKS})
    def test_reference_blocked(self):
        with tempfile.TemporaryDirectory() as td:self.assertEqual(preflight_release({'environment_kind':'reference_only'},Path(td))['local_precheck'],'blocked')
    def test_all_evidence_only_precheck(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);(r/'p').write_bytes(b'fixture');v=preflight_release(self.report('p',hashlib.sha256(b'fixture').hexdigest()),r);self.assertEqual(v['local_precheck'],'ready_for_host_review');self.assertFalse(v['production_allowed'])
    def test_bad_digest(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);(r/'p').write_bytes(b'x');self.assertEqual(preflight_release(self.report('p','0'*64),r)['local_precheck'],'blocked')
    def test_escape(self):
        with tempfile.TemporaryDirectory() as td:self.assertEqual(preflight_release(self.report('../outside','0'*64),Path(td))['local_precheck'],'blocked')
    def test_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);(r/'p').write_bytes(b'x');(r/'link').symlink_to(r/'p');self.assertEqual(preflight_release(self.report('link',hashlib.sha256(b'x').hexdigest()),r)['local_precheck'],'blocked')
    def test_null(self):
        with tempfile.TemporaryDirectory() as td:self.assertEqual(preflight_release(self.report(None,None),Path(td))['local_precheck'],'blocked')
