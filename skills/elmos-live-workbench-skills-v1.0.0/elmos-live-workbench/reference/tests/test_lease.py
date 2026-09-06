import unittest
from dataclasses import replace
from lw_core.lease import *

class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.s=PreviewLease('t','rev','s',1,0,1245)
        self.p=ReadinessProof('proof','t','rev','s',1,'independent-smoke-verifier',True,True)
    def test_prepare_not_deducted(self):
        self.assertEqual(self.s.mark_ready(200,self.p),800)
    def test_before_ready_denied(self):
        with self.assertRaises(LeaseError):self.s.authorize(1,'t',1)
    def test_exact_boundary(self):
        self.s.mark_ready(100,self.p)
        self.s.authorize(699.999,'t',1)
        with self.assertRaises(LeaseError):self.s.authorize(700,'t',1)
    def test_repeat_ready_does_not_reset(self):
        self.s.mark_ready(100,self.p)
        self.assertEqual(self.s.mark_ready(200,self.p),700)
    def test_different_ready_proof_rejected(self):
        self.s.mark_ready(100,self.p)
        with self.assertRaises(LeaseError):self.s.mark_ready(200,replace(self.p,proof_id='different'))
    def test_pause_does_not_extend(self):
        self.s.mark_ready(100,self.p);self.s.set_runtime_status(200,'paused')
        self.assertEqual(self.s.expires_at,700)
    def test_degraded_restart_does_not_extend(self):
        self.s.mark_ready(100,self.p);self.s.set_runtime_status(200,'degraded');self.s.set_runtime_status(300,'running')
        self.assertEqual(self.s.expires_at,700)
    def test_refresh_does_not_extend(self):
        self.s.mark_ready(100,self.p)
        for t in [200,300,400]:self.s.authorize(t,'t',1)
        self.assertEqual(self.s.expires_at,700)
    def test_wrong_tenant(self):
        self.s.mark_ready(100,self.p)
        with self.assertRaises(LeaseError):self.s.authorize(200,'other',1)
    def test_generation_fencing(self):
        self.s.mark_ready(100,self.p);self.assertEqual(self.s.replace_worker(200),2)
        with self.assertRaises(LeaseError):self.s.authorize(201,'t',1)
        self.s.authorize(202,'t',2)
        self.assertEqual(self.s.expires_at,700)
    def test_readiness_bindings(self):
        for kw in [{'tenant':'other'},{'revision':'old'},{'session_id':'different'},{'generation':2}]:
            with self.subTest(kw=kw),self.assertRaises(LeaseError):self.s.mark_ready(100,replace(self.p,**kw))
    def test_readiness_evidence_rejected(self):
        for kw in [{'committed':False},{'smoke_passed':False},{'verifier':'repository-stdout'}]:
            with self.subTest(kw=kw),self.assertRaises(LeaseError):self.s.mark_ready(100,replace(self.p,**kw))
    def test_prepare_timeout(self):
        with self.assertRaises(LeaseError):self.s.mark_ready(600,self.p)
    def test_insufficient_provider_remaining(self):
        s=PreviewLease('t','rev','s',1,0,650)
        with self.assertRaises(LeaseError):s.mark_ready(100,self.p)
    def test_clock_regression(self):
        self.s.mark_ready(100,self.p)
        with self.assertRaises(LeaseError):self.s.authorize(99,'t',1)
    def test_ready_after_expiry_cannot_renew(self):
        self.s.mark_ready(100,self.p)
        with self.assertRaises(LeaseError):self.s.mark_ready(700,self.p)
    def test_failed_cleanup_quarantined(self):
        self.assertEqual(self.s.close(1,{'proxy_revoked':True}),'quarantined')
    def test_complete_cleanup_closed(self):
        checks={x:True for x in ['proxy_revoked','connections_closed','processes_stopped','volumes_deleted','secrets_revoked','adapters_stopped','ports_closed']}
        self.assertEqual(self.s.close(1,checks),'closed')

    def test_nan_clock_denied(self):
        with self.assertRaises(LeaseError):self.s.mark_ready(float('nan'),self.p)
    def test_infinite_clock_denied(self):
        with self.assertRaises(LeaseError):self.s.mark_ready(float('inf'),self.p)
    def test_nonfinite_provider_denied(self):
        with self.assertRaises(LeaseError):PreviewLease('t','rev','s',1,0,float('inf'))
