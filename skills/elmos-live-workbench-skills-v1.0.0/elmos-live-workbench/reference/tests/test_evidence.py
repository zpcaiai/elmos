import unittest, copy
from lw_core.evidence import *

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.base={'tenant_id':'t','repository_id':'r','snapshot_id':'rev'}
        self.c={**self.base,'classification':'runtime-observed','source_anchor_ids':['a'],'runtime_event_ids':['e']}
        self.anchors={'a':dict(self.base)}
        self.events={'e':{**self.base,'commit_status':'committed'}}
    def test_bound_runtime_claim(self):validate_claim(self.c,self.anchors,self.events)
    def test_runtime_claim_needs_event(self):
        self.c['runtime_event_ids']=[]
        with self.assertRaises(ValueError):validate_claim(self.c,self.anchors,self.events)
    def test_stale_source(self):
        self.anchors['a']['snapshot_id']='older'
        with self.assertRaises(ValueError):validate_claim(self.c,self.anchors,self.events)
    def test_uncommitted_event(self):
        self.events['e']['commit_status']='raw'
        with self.assertRaises(ValueError):validate_claim(self.c,self.anchors,self.events)
    def test_cross_tenant_event(self):
        self.events['e']['tenant_id']='other'
        with self.assertRaises(ValueError):validate_claim(self.c,self.anchors,self.events)
    def test_unknown_does_not_require_fabricated_proof(self):
        self.c.update(classification='unknown',source_anchor_ids=[],runtime_event_ids=[])
        validate_claim(self.c,{}, {})
    def test_mapping_cardinality(self):
        m={'relation':'one-to-many','source_anchor_ids':['s'],'target_anchor_ids':['t1','t2'],'confidence':'inferred','evidence_ids':[]}
        validate_correspondence(m)
        m['target_anchor_ids']=['t1']
        with self.assertRaises(ValueError):validate_correspondence(m)
    def test_synthesized_is_not_fake_source(self):
        validate_correspondence({'relation':'synthesized','source_anchor_ids':[],'target_anchor_ids':['t'],'confidence':'inferred','evidence_ids':[]})
    def test_observed_mapping_needs_evidence(self):
        with self.assertRaises(ValueError):validate_correspondence({'relation':'one-to-one','source_anchor_ids':['s'],'target_anchor_ids':['t'],'confidence':'observed-scenario','evidence_ids':[]})
    def test_session_arithmetic(self):
        s={'first_ready_at':100,'expires_at':700,'created_at':0,'provider_hard_deadline':745,'state':'ready'}
        validate_session(s)
        s['expires_at']=800
        with self.assertRaises(ValueError):validate_session(s)
