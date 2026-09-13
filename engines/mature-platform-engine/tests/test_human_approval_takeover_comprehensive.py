import unittest
from datetime import datetime, timedelta
from elmos_mature_platform.types import ApprovalRequest, ApprovalStatus, TakeoverEvent, TakeoverReason
from elmos_mature_platform.human_approval_takeover_engine import HumanApprovalTakeoverEngine

class TestHumanApprovalTakeoverEngine(unittest.TestCase):
    def setUp(self):
        self.engine = HumanApprovalTakeoverEngine()

    def test_submit_approval_pending(self):
        req = ApprovalRequest(request_id="req1", action_description="test", requester="sys", risk_level="high")
        self.engine.submit_approval(req)
        self.assertEqual(req.status, ApprovalStatus.PENDING)

    def test_submit_approval_auto_approved(self):
        req = ApprovalRequest(request_id="req2", action_description="test", requester="sys", risk_level="low", auto_approve_threshold="medium")
        self.engine.submit_approval(req)
        self.assertEqual(req.status, ApprovalStatus.AUTO_APPROVED)
        self.assertTrue(bool(req.decision_reason))

    def test_submit_approval_equal_threshold(self):
        req = ApprovalRequest(request_id="req3", action_description="test", requester="sys", risk_level="medium", auto_approve_threshold="medium")
        self.engine.submit_approval(req)
        self.assertEqual(req.status, ApprovalStatus.AUTO_APPROVED)

    def test_submit_approval_above_threshold(self):
        req = ApprovalRequest(request_id="req4", action_description="test", requester="sys", risk_level="critical", auto_approve_threshold="high")
        self.engine.submit_approval(req)
        self.assertEqual(req.status, ApprovalStatus.PENDING)

    def test_approve_pending(self):
        req = ApprovalRequest(request_id="req5", action_description="test", requester="sys")
        self.engine.submit_approval(req)
        res = self.engine.approve("req5", "alice", "lgtm")
        self.assertEqual(res.status, ApprovalStatus.APPROVED)
        self.assertEqual(res.approver, "alice")
        self.assertEqual(res.decision_reason, "lgtm")

    def test_approve_nonexistent(self):
        with self.assertRaises(ValueError):
            self.engine.approve("nonexistent", "alice", "lgtm")

    def test_approve_already_approved(self):
        req = ApprovalRequest(request_id="req6", action_description="test", requester="sys")
        self.engine.submit_approval(req)
        self.engine.approve("req6", "alice", "lgtm")
        with self.assertRaises(ValueError):
            self.engine.approve("req6", "bob", "lgtm again")

    def test_reject_pending(self):
        req = ApprovalRequest(request_id="req7", action_description="test", requester="sys")
        self.engine.submit_approval(req)
        res = self.engine.reject("req7", "bob", "no way")
        self.assertEqual(res.status, ApprovalStatus.REJECTED)
        self.assertEqual(res.approver, "bob")

    def test_reject_nonexistent(self):
        with self.assertRaises(ValueError):
            self.engine.reject("nope", "bob", "no")

    def test_reject_auto_approved(self):
        req = ApprovalRequest(request_id="req8", action_description="test", requester="sys", risk_level="low", auto_approve_threshold="medium")
        self.engine.submit_approval(req)
        with self.assertRaises(ValueError):
            self.engine.reject("req8", "bob", "no")

    def test_escalate_pending(self):
        req = ApprovalRequest(request_id="req9", action_description="test", requester="sys")
        self.engine.submit_approval(req)
        res = self.engine.escalate("req9", "need director approval")
        self.assertEqual(res.status, ApprovalStatus.ESCALATED)

    def test_escalate_nonexistent(self):
        with self.assertRaises(ValueError):
            self.engine.escalate("nope", "escalate")

    def test_escalate_approved(self):
        req = ApprovalRequest(request_id="req10", action_description="test", requester="sys")
        self.engine.submit_approval(req)
        self.engine.approve("req10", "alice", "lgtm")
        with self.assertRaises(ValueError):
            self.engine.escalate("req10", "escalate")

    def test_check_expiry_none(self):
        req = ApprovalRequest(request_id="req11", action_description="test", requester="sys")
        self.engine.submit_approval(req)
        expired = self.engine.check_expiry()
        self.assertEqual(expired, [])

    def test_check_expiry_future(self):
        fut = (datetime.utcnow() + timedelta(days=1)).isoformat()
        req = ApprovalRequest(request_id="req12", action_description="test", requester="sys", expires_at=fut)
        self.engine.submit_approval(req)
        expired = self.engine.check_expiry()
        self.assertEqual(expired, [])

    def test_check_expiry_past(self):
        past = (datetime.utcnow() - timedelta(days=1)).isoformat()
        req = ApprovalRequest(request_id="req13", action_description="test", requester="sys", expires_at=past)
        self.engine.submit_approval(req)
        expired = self.engine.check_expiry()
        self.assertEqual(expired, ["req13"])
        self.assertEqual(self.engine._approvals["req13"].status, ApprovalStatus.EXPIRED)

    def test_initiate_takeover(self):
        event = TakeoverEvent(event_id="evt1", reason=TakeoverReason.SAFETY, triggered_by="charlie", agent_id="agent1")
        eid = self.engine.initiate_takeover(event)
        self.assertEqual(eid, "evt1")
        self.assertTrue(bool(self.engine._takeovers["evt1"].started_at))

    def test_initiate_takeover_no_agent(self):
        event = TakeoverEvent(event_id="evt2", reason=TakeoverReason.SAFETY, triggered_by="charlie", agent_id="")
        with self.assertRaises(ValueError):
            self.engine.initiate_takeover(event)

    def test_end_takeover(self):
        event = TakeoverEvent(event_id="evt3", reason=TakeoverReason.SAFETY, triggered_by="charlie", agent_id="agent1")
        self.engine.initiate_takeover(event)
        res = self.engine.end_takeover("evt3", "resolved")
        self.assertEqual(res.outcome, "resolved")
        self.assertTrue(bool(res.ended_at))

    def test_end_takeover_nonexistent(self):
        with self.assertRaises(ValueError):
            self.engine.end_takeover("nope", "resolved")

    def test_end_takeover_already_ended(self):
        event = TakeoverEvent(event_id="evt4", reason=TakeoverReason.SAFETY, triggered_by="charlie", agent_id="agent1")
        self.engine.initiate_takeover(event)
        self.engine.end_takeover("evt4", "resolved")
        with self.assertRaises(ValueError):
            self.engine.end_takeover("evt4", "escalated")

    def test_record_takeover_action(self):
        event = TakeoverEvent(event_id="evt5", reason=TakeoverReason.SAFETY, triggered_by="charlie", agent_id="agent1")
        self.engine.initiate_takeover(event)
        self.engine.record_takeover_action("evt5", "paused operations")
        self.assertIn("paused operations", self.engine._takeovers["evt5"].actions_taken)

    def test_record_takeover_action_ended(self):
        event = TakeoverEvent(event_id="evt6", reason=TakeoverReason.SAFETY, triggered_by="charlie", agent_id="agent1")
        self.engine.initiate_takeover(event)
        self.engine.end_takeover("evt6", "resolved")
        with self.assertRaises(ValueError):
            self.engine.record_takeover_action("evt6", "too late")

    def test_get_pending_approvals_all(self):
        r1 = ApprovalRequest(request_id="req14", action_description="test", requester="sys", risk_level="high", auto_approve_threshold="low")
        r2 = ApprovalRequest(request_id="req15", action_description="test", requester="sys", risk_level="high", auto_approve_threshold="low")
        self.engine.submit_approval(r1)
        self.engine.submit_approval(r2)
        pending = self.engine.get_pending_approvals()
        self.assertEqual(len(pending), 2)

    def test_get_pending_approvals_filtered(self):
        r1 = ApprovalRequest(request_id="req16", action_description="test", requester="sys", risk_level="low", auto_approve_threshold="none")
        r2 = ApprovalRequest(request_id="req17", action_description="test", requester="sys", risk_level="high", auto_approve_threshold="none")
        self.engine.submit_approval(r1)
        self.engine.submit_approval(r2)
        pending = self.engine.get_pending_approvals(risk_level="high")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].request_id, "req17")

    def test_get_approval_stats(self):
        r1 = ApprovalRequest(request_id="req18", action_description="test", requester="sys", risk_level="low", auto_approve_threshold="medium")
        r2 = ApprovalRequest(request_id="req19", action_description="test", requester="sys", risk_level="high", auto_approve_threshold="medium")
        self.engine.submit_approval(r1)  # auto
        self.engine.submit_approval(r2)  # pending -> approve
        self.engine.approve("req19", "alice", "ok")
        
        stats = self.engine.get_approval_stats()
        self.assertEqual(stats["by_status"][ApprovalStatus.AUTO_APPROVED.value], 1)
        self.assertEqual(stats["by_status"][ApprovalStatus.APPROVED.value], 1)
        self.assertEqual(stats["auto_vs_manual"]["auto"], 1)
        self.assertEqual(stats["auto_vs_manual"]["manual"], 1)

    def test_get_takeover_history(self):
        event = TakeoverEvent(event_id="evt7", reason=TakeoverReason.SAFETY, triggered_by="charlie", agent_id="agent1")
        self.engine.initiate_takeover(event)
        history = self.engine.get_takeover_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].event_id, "evt7")

    def test_get_approval_audit_trail(self):
        r1 = ApprovalRequest(request_id="req20", action_description="test", requester="sys", risk_level="high", auto_approve_threshold="none")
        self.engine.submit_approval(r1)
        self.engine.approve("req20", "alice", "ok")
        
        audit = self.engine.get_approval_audit_trail("req20")
        self.assertEqual(audit["request_id"], "req20")
        self.assertEqual(audit["approver"], "alice")
        self.assertEqual(audit["status"], "approved")

    def test_get_approval_audit_trail_missing(self):
        with self.assertRaises(ValueError):
            self.engine.get_approval_audit_trail("missing")
            
    def test_invalid_risk_level_fallback(self):
        # 'unknown' should fallback to medium
        req = ApprovalRequest(request_id="req21", action_description="test", requester="sys", risk_level="unknown", auto_approve_threshold="high")
        self.engine.submit_approval(req)
        # medium <= high, so it should be auto approved
        self.assertEqual(req.status, ApprovalStatus.AUTO_APPROVED)

    def test_invalid_threshold_fallback(self):
        # 'unknown' threshold should fallback to low
        req = ApprovalRequest(request_id="req22", action_description="test", requester="sys", risk_level="medium", auto_approve_threshold="unknown")
        self.engine.submit_approval(req)
        # medium (1) <= low (0) is False, should be pending
        self.assertEqual(req.status, ApprovalStatus.PENDING)

    def test_check_expiry_already_decided(self):
        past = (datetime.utcnow() - timedelta(days=1)).isoformat()
        req = ApprovalRequest(request_id="req23", action_description="test", requester="sys", expires_at=past, risk_level="low", auto_approve_threshold="medium")
        self.engine.submit_approval(req) # auto approves
        expired = self.engine.check_expiry()
        self.assertEqual(expired, [])
        self.assertEqual(self.engine._approvals["req23"].status, ApprovalStatus.AUTO_APPROVED)
        
if __name__ == '__main__':
    unittest.main()
