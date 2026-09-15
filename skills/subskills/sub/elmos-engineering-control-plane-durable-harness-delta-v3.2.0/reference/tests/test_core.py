import unittest
from elmos_v32.core import *

class CoreTests(unittest.TestCase):
    def test_policy_intersection_and_hard_deny(self):
        a=Policy(frozenset({'repo.read','repo.write','network'}),frozenset())
        b=Policy(frozenset({'repo.read','repo.write','network'}),frozenset({'network'}))
        e=intersect_policies(a,b)
        self.assertEqual(e.allows,frozenset({'repo.read','repo.write'}))
        self.assertIn('network',e.denies)
    def test_authority_never_widens(self):
        self.assertTrue(monotonic_authority({'a','b'},{'a'}))
        self.assertFalse(monotonic_authority({'a'},{'a','b'}))
    def test_negotiation_narrows(self):
        result,eff=negotiate({'read','write'},{'read'})
        self.assertEqual(result,Negotiation.SUPPORTED_WITH_NARROWER_SCOPE)
        self.assertEqual(eff,frozenset({'read'}))
    def test_observe_has_no_connect_side_effect(self):
        o=RuntimeStatusObserver(RuntimeState.NOT_STARTED)
        self.assertEqual(o.observe(),RuntimeState.NOT_STARTED)
        self.assertEqual(o.connect_calls,0)
    def test_owner_epoch_fences_stale_transfer(self):
        r=OwnerRecord('e','owner-a',4); r.handoff_ready()
        with self.assertRaises(ValueError): r.transfer('owner-b',3)
        r.transfer('owner-b',4)
        self.assertEqual(r.epoch,5)
    def test_release_pending_blocks(self):
        self.assertFalse(release_gate([VerificationStatus.PASS,VerificationStatus.PENDING],True))
    def test_release_exact_bytes_required(self):
        self.assertFalse(release_gate([VerificationStatus.PASS],False))
    def test_approval_exact_binding(self):
        a={'execution_plan_digest':'x','action_kind':'WRITE_STDIN','resource_digest':'p'}
        self.assertTrue(approval_matches(a,dict(a)))
        b=dict(a); b['action_kind']='EXEC_COMMAND'
        self.assertFalse(approval_matches(a,b))

if __name__=='__main__': unittest.main()
