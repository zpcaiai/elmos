import unittest
from datetime import datetime, timedelta
import time
from elmos_mature_platform.types import (
    ChangeRequest, ChangeFreezeWindow, ChangeRiskLevel,
    ChangeStatus, FreezeScope
)
from elmos_mature_platform.change_management_engine import ChangeManagementEngine

class TestChangeManagementEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ChangeManagementEngine()

    def test_submit_low_risk_change(self):
        req = ChangeRequest(
            change_id="CHG-1",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        chg = self.engine.submit_change(req)
        self.assertEqual(chg.status, ChangeStatus.SUBMITTED)
        self.assertEqual(len(self.engine.changes), 1)

    def test_submit_high_risk_missing_rollback(self):
        req = ChangeRequest(
            change_id="CHG-2",
            title="Database migration",
            description="Major migration",
            service_name="db-cluster",
            risk_level=ChangeRiskLevel.HIGH,
            requester="alice"
        )
        with self.assertRaises(ValueError):
            self.engine.submit_change(req)

    def test_submit_high_risk_with_rollback(self):
        req = ChangeRequest(
            change_id="CHG-3",
            title="Database migration",
            description="Major migration",
            service_name="db-cluster",
            risk_level=ChangeRiskLevel.HIGH,
            requester="alice",
            rollback_plan="Restore from snapshot"
        )
        chg = self.engine.submit_change(req)
        self.assertEqual(chg.status, ChangeStatus.SUBMITTED)

    def test_approve_change_success(self):
        req = ChangeRequest(
            change_id="CHG-4",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        self.engine.submit_change(req)
        chg = self.engine.approve_change("CHG-4", "bob")
        self.assertEqual(chg.status, ChangeStatus.APPROVED)
        self.assertEqual(chg.approver, "bob")

    def test_approve_change_self_approval(self):
        req = ChangeRequest(
            change_id="CHG-5",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        self.engine.submit_change(req)
        with self.assertRaises(PermissionError):
            self.engine.approve_change("CHG-5", "alice")

    def test_approve_unsubmitted_change(self):
        req = ChangeRequest(
            change_id="CHG-6",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        self.engine.changes[req.change_id] = req  # Bypass submit
        with self.assertRaises(ValueError):
            self.engine.approve_change("CHG-6", "bob")

    def test_reject_change_success(self):
        req = ChangeRequest(
            change_id="CHG-7",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        self.engine.submit_change(req)
        chg = self.engine.reject_change("CHG-7", "bob", "Not needed")
        self.assertEqual(chg.status, ChangeStatus.REJECTED)

    def test_reject_self_rejection(self):
        req = ChangeRequest(
            change_id="CHG-8",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        self.engine.submit_change(req)
        with self.assertRaises(PermissionError):
            self.engine.reject_change("CHG-8", "alice", "My bad")

    def test_start_change_success(self):
        req = ChangeRequest(
            change_id="CHG-9",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        self.engine.submit_change(req)
        self.engine.approve_change("CHG-9", "bob")
        chg = self.engine.start_change("CHG-9")
        self.assertEqual(chg.status, ChangeStatus.IN_PROGRESS)
        self.assertTrue(chg.started_at)

    def test_start_unapproved_change(self):
        req = ChangeRequest(
            change_id="CHG-10",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        self.engine.submit_change(req)
        with self.assertRaises(ValueError):
            self.engine.start_change("CHG-10")

    def test_start_change_during_freeze(self):
        freeze = ChangeFreezeWindow(
            freeze_id="FRZ-1",
            reason="Holiday freeze",
            scope=FreezeScope.GLOBAL,
            starts_at="2000-01-01T00:00:00Z",
            ends_at="2099-12-31T23:59:59Z"
        )
        self.engine.create_freeze(freeze)
        
        req = ChangeRequest(
            change_id="CHG-11",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        self.engine.submit_change(req)
        self.engine.approve_change("CHG-11", "bob")
        
        with self.assertRaises(PermissionError):
            self.engine.start_change("CHG-11")

    def test_start_change_during_freeze_with_exception(self):
        freeze = ChangeFreezeWindow(
            freeze_id="FRZ-2",
            reason="Holiday freeze",
            scope=FreezeScope.GLOBAL,
            starts_at="2000-01-01T00:00:00Z",
            ends_at="2099-12-31T23:59:59Z"
        )
        self.engine.create_freeze(freeze)
        self.engine.add_freeze_exception("FRZ-2", "CHG-12")
        
        req = ChangeRequest(
            change_id="CHG-12",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        self.engine.submit_change(req)
        self.engine.approve_change("CHG-12", "bob")
        
        chg = self.engine.start_change("CHG-12")
        self.assertEqual(chg.status, ChangeStatus.IN_PROGRESS)

    def test_complete_change_success(self):
        req = ChangeRequest(
            change_id="CHG-13",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        self.engine.submit_change(req)
        self.engine.approve_change("CHG-13", "bob")
        self.engine.start_change("CHG-13")
        chg = self.engine.complete_change("CHG-13", success=True)
        self.assertEqual(chg.status, ChangeStatus.COMPLETED)
        self.assertTrue(chg.completed_at)

    def test_complete_change_failed(self):
        req = ChangeRequest(
            change_id="CHG-14",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        self.engine.submit_change(req)
        self.engine.approve_change("CHG-14", "bob")
        self.engine.start_change("CHG-14")
        chg = self.engine.complete_change("CHG-14", success=False)
        self.assertEqual(chg.status, ChangeStatus.FAILED)

    def test_complete_not_in_progress(self):
        req = ChangeRequest(
            change_id="CHG-15",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        self.engine.submit_change(req)
        self.engine.approve_change("CHG-15", "bob")
        with self.assertRaises(ValueError):
            self.engine.complete_change("CHG-15", success=True)

    def test_rollback_in_progress(self):
        req = ChangeRequest(
            change_id="CHG-16",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        self.engine.submit_change(req)
        self.engine.approve_change("CHG-16", "bob")
        self.engine.start_change("CHG-16")
        chg = self.engine.rollback_change("CHG-16")
        self.assertEqual(chg.status, ChangeStatus.ROLLED_BACK)

    def test_rollback_completed(self):
        req = ChangeRequest(
            change_id="CHG-17",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        self.engine.submit_change(req)
        self.engine.approve_change("CHG-17", "bob")
        self.engine.start_change("CHG-17")
        self.engine.complete_change("CHG-17", success=True)
        chg = self.engine.rollback_change("CHG-17")
        self.assertEqual(chg.status, ChangeStatus.ROLLED_BACK)

    def test_rollback_unstarted(self):
        req = ChangeRequest(
            change_id="CHG-18",
            title="Update config",
            description="Minor update",
            service_name="api-gateway",
            risk_level=ChangeRiskLevel.LOW,
            requester="alice"
        )
        self.engine.submit_change(req)
        with self.assertRaises(ValueError):
            self.engine.rollback_change("CHG-18")

    def test_is_frozen_global(self):
        freeze = ChangeFreezeWindow(
            freeze_id="FRZ-3",
            reason="Holiday freeze",
            scope=FreezeScope.GLOBAL,
            starts_at="2000-01-01T00:00:00Z",
            ends_at="2099-12-31T23:59:59Z"
        )
        self.engine.create_freeze(freeze)
        self.assertTrue(self.engine.is_frozen("any-service", "any-region", "2050-01-01T00:00:00Z"))

    def test_is_frozen_region(self):
        freeze = ChangeFreezeWindow(
            freeze_id="FRZ-4",
            reason="Region migration",
            scope=FreezeScope.REGION,
            scope_value="us-east-1",
            starts_at="2000-01-01T00:00:00Z",
            ends_at="2099-12-31T23:59:59Z"
        )
        self.engine.create_freeze(freeze)
        self.assertTrue(self.engine.is_frozen("any-service", "us-east-1", "2050-01-01T00:00:00Z"))
        self.assertFalse(self.engine.is_frozen("any-service", "us-west-2", "2050-01-01T00:00:00Z"))

    def test_is_frozen_service(self):
        freeze = ChangeFreezeWindow(
            freeze_id="FRZ-5",
            reason="Service critical window",
            scope=FreezeScope.SERVICE,
            scope_value="db-cluster",
            starts_at="2000-01-01T00:00:00Z",
            ends_at="2099-12-31T23:59:59Z"
        )
        self.engine.create_freeze(freeze)
        self.assertTrue(self.engine.is_frozen("db-cluster", "any-region", "2050-01-01T00:00:00Z"))
        self.assertFalse(self.engine.is_frozen("api-gateway", "any-region", "2050-01-01T00:00:00Z"))

    def test_is_frozen_time_bounds(self):
        freeze = ChangeFreezeWindow(
            freeze_id="FRZ-6",
            reason="Short freeze",
            scope=FreezeScope.GLOBAL,
            starts_at="2020-01-01T00:00:00Z",
            ends_at="2020-01-02T00:00:00Z"
        )
        self.engine.create_freeze(freeze)
        self.assertFalse(self.engine.is_frozen("srv", "reg", "2019-12-31T23:59:59Z"))
        self.assertTrue(self.engine.is_frozen("srv", "reg", "2020-01-01T12:00:00Z"))
        self.assertFalse(self.engine.is_frozen("srv", "reg", "2020-01-02T00:00:01Z"))

    def test_get_pending_approvals(self):
        req1 = ChangeRequest("CHG-19", "Title", "Desc", "svc", ChangeRiskLevel.LOW, requester="alice")
        req2 = ChangeRequest("CHG-20", "Title", "Desc", "svc", ChangeRiskLevel.LOW, requester="bob")
        self.engine.submit_change(req1)
        self.engine.submit_change(req2)
        self.engine.approve_change("CHG-19", "charlie")
        
        pending = self.engine.get_pending_approvals()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].change_id, "CHG-20")

    def test_get_change_audit(self):
        req = ChangeRequest("CHG-21", "Title", "Desc", "svc", ChangeRiskLevel.LOW, requester="alice")
        self.engine.submit_change(req)
        self.engine.approve_change("CHG-21", "bob")
        
        audits = self.engine.get_change_audit("CHG-21")
        self.assertEqual(len(audits), 2)
        self.assertEqual(audits[0].action, "SUBMIT")
        self.assertEqual(audits[1].action, "APPROVE")

    def test_get_change_metrics(self):
        req = ChangeRequest("CHG-22", "Title", "Desc", "svc", ChangeRiskLevel.LOW, requester="alice")
        self.engine.submit_change(req)
        
        # Artificial delay simulation via time update in audit if possible, or just expect ~0
        self.engine.approve_change("CHG-22", "bob")
        
        metrics = self.engine.get_change_metrics()
        self.assertEqual(metrics["total_changes"], 1)
        self.assertEqual(metrics["status_counts"]["approved"], 1)
        self.assertEqual(metrics["risk_counts"]["low"], 1)
        self.assertIn("average_approval_time_seconds", metrics)

    def test_check_change_conflicts_no_conflict(self):
        req1 = ChangeRequest("CHG-23", "T", "D", "svc1", ChangeRiskLevel.LOW, requester="a")
        req2 = ChangeRequest("CHG-24", "T", "D", "svc2", ChangeRiskLevel.LOW, requester="a")
        self.engine.submit_change(req1)
        self.engine.submit_change(req2)
        self.engine.approve_change("CHG-23", "b")
        self.engine.approve_change("CHG-24", "b")
        self.engine.start_change("CHG-23")
        
        conflicts = self.engine.check_change_conflicts("CHG-24")
        self.assertEqual(len(conflicts), 0)

    def test_check_change_conflicts_direct_conflict(self):
        req1 = ChangeRequest("CHG-25", "T", "D", "svc1", ChangeRiskLevel.LOW, requester="a")
        req2 = ChangeRequest("CHG-26", "T", "D", "svc1", ChangeRiskLevel.LOW, requester="a")
        self.engine.submit_change(req1)
        self.engine.submit_change(req2)
        self.engine.approve_change("CHG-25", "b")
        self.engine.start_change("CHG-25")
        
        conflicts = self.engine.check_change_conflicts("CHG-26")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0], "CHG-25")

    def test_check_change_conflicts_impact_conflict(self):
        req1 = ChangeRequest("CHG-27", "T", "D", "svc1", ChangeRiskLevel.LOW, impact_services=["svc3"], requester="a")
        req2 = ChangeRequest("CHG-28", "T", "D", "svc2", ChangeRiskLevel.LOW, impact_services=["svc3"], requester="a")
        self.engine.submit_change(req1)
        self.engine.submit_change(req2)
        self.engine.approve_change("CHG-27", "b")
        self.engine.start_change("CHG-27")
        
        conflicts = self.engine.check_change_conflicts("CHG-28")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0], "CHG-27")

    def test_invalid_change_id_raises_keyerror(self):
        with self.assertRaises(KeyError):
            self.engine.approve_change("NON-EXISTENT", "bob")
            
        with self.assertRaises(KeyError):
            self.engine.start_change("NON-EXISTENT")
            
        with self.assertRaises(KeyError):
            self.engine.complete_change("NON-EXISTENT", True)
            
        with self.assertRaises(KeyError):
            self.engine.rollback_change("NON-EXISTENT")
            
        with self.assertRaises(KeyError):
            self.engine.check_change_conflicts("NON-EXISTENT")

    def test_add_freeze_exception_invalid_freeze(self):
        with self.assertRaises(KeyError):
            self.engine.add_freeze_exception("NON-EXISTENT", "CHG-1")

    def test_get_change_metrics_empty(self):
        metrics = self.engine.get_change_metrics()
        self.assertEqual(metrics["total_changes"], 0)
        self.assertEqual(metrics["average_approval_time_seconds"], 0.0)

if __name__ == '__main__':
    unittest.main()
