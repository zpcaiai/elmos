import unittest
from elmos_mature_platform.types import (
    SemVer, ComponentVersionMatrix, RunnerHandshakeRequest, SchemaBreakingChange
)
from elmos_mature_platform.version_compatibility_engine import VersionCompatibilityEngine

class TestVersionCompatibilityEngine(unittest.TestCase):
    def setUp(self):
        self.engine = VersionCompatibilityEngine()
        self.matrix = ComponentVersionMatrix(
            control_plane_version=SemVer(2, 1, 0),
            min_runner_version=SemVer(2, 0, 0),
            max_runner_version=SemVer(2, 2, 0),
            supported_api_versions=["v1", "v2"],
            supported_schema_versions=["v1", "v2"],
            deprecated_features=[]
        )
        self.engine.set_control_plane_version(SemVer(2, 1, 0), self.matrix)

    def test_runner_v2_0_accepted_by_v2_1(self):
        req = RunnerHandshakeRequest(runner_id="r1", runner_version=SemVer(2, 0, 0), protocol_version=2)
        resp = self.engine.negotiate_runner_handshake(req)
        self.assertTrue(resp.accepted)

    def test_runner_v1_0_rejected(self):
        req = RunnerHandshakeRequest(runner_id="r1", runner_version=SemVer(1, 0, 0), protocol_version=2)
        resp = self.engine.negotiate_runner_handshake(req)
        self.assertFalse(resp.accepted)
        self.assertEqual(resp.rejection_reason, "Runner version too old")

    def test_runner_v3_0_rejected(self):
        req = RunnerHandshakeRequest(runner_id="r1", runner_version=SemVer(3, 0, 0), protocol_version=2)
        resp = self.engine.negotiate_runner_handshake(req)
        self.assertFalse(resp.accepted)
        self.assertEqual(resp.rejection_reason, "Runner version too new")

    def test_protocol_negotiation(self):
        req = RunnerHandshakeRequest(runner_id="r1", runner_version=SemVer(2, 0, 0), protocol_version=2)
        resp = self.engine.negotiate_runner_handshake(req)
        self.assertTrue(resp.accepted)
        self.assertEqual(resp.negotiated_protocol, 2)

    def test_protocol_negotiation_runner_v3(self):
        req = RunnerHandshakeRequest(runner_id="r1", runner_version=SemVer(2, 1, 0), protocol_version=4)
        resp = self.engine.negotiate_runner_handshake(req)
        self.assertTrue(resp.accepted)
        self.assertEqual(resp.negotiated_protocol, 3)  # max supported is 3

    def test_mixed_cluster_in_range(self):
        res = self.engine.validate_mixed_version_cluster([SemVer(2, 0, 0), SemVer(2, 1, 0), SemVer(2, 2, 0)])
        self.assertTrue(res["valid"])

    def test_mixed_cluster_out_of_range(self):
        res = self.engine.validate_mixed_version_cluster([SemVer(2, 1, 0), SemVer(2, 3, 0)])
        self.assertFalse(res["valid"])
        self.assertIn("2.3.0", res["out_of_range_nodes"])

    def test_mixed_cluster_out_of_range_old(self):
        res = self.engine.validate_mixed_version_cluster([SemVer(2, 1, 0), SemVer(1, 9, 0)])
        self.assertFalse(res["valid"])

    def test_task_compatible(self):
        res = self.engine.check_runner_task_compatibility(["CAP_A"], ["CAP_A", "CAP_B"], SemVer(2, 1, 0))
        self.assertTrue(res["compatible"])

    def test_task_incompatible_missing_cap(self):
        res = self.engine.check_runner_task_compatibility(["GPU_SANDBOX_V2"], ["CPU"], SemVer(2, 1, 0))
        self.assertFalse(res["compatible"])
        self.assertIn("Missing capabilities", res["reason"])

    def test_task_incompatible_version(self):
        res = self.engine.check_runner_task_compatibility(["CAP_A"], ["CAP_A"], SemVer(1, 0, 0))
        self.assertFalse(res["compatible"])
        self.assertIn("version range", res["reason"])

    def test_schema_field_removed(self):
        cur = {"fields": {"a": {"type": "string"}, "b": {"type": "int"}}}
        cand = {"fields": {"a": {"type": "string"}}}
        changes = self.engine.detect_schema_breaking_changes(cur, cand)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, "FIELD_REMOVED")

    def test_schema_type_changed(self):
        cur = {"fields": {"a": {"type": "string"}}}
        cand = {"fields": {"a": {"type": "int"}}}
        changes = self.engine.detect_schema_breaking_changes(cur, cand)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, "TYPE_CHANGED")

    def test_schema_required_added(self):
        cur = {"fields": {"a": {"type": "string"}}}
        cand = {"fields": {"a": {"type": "string"}, "b": {"type": "int", "required": True}}}
        changes = self.engine.detect_schema_breaking_changes(cur, cand)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, "REQUIRED_ADDED")
        
    def test_schema_optional_added_ok(self):
        cur = {"fields": {"a": {"type": "string"}}}
        cand = {"fields": {"a": {"type": "string"}, "b": {"type": "int", "required": False}}}
        changes = self.engine.detect_schema_breaking_changes(cur, cand)
        self.assertEqual(len(changes), 0)

    def test_wire_compatibility(self):
        res = self.engine.check_wire_compatibility({"a": 1, "b": 2}, ["a"])
        self.assertTrue(res.unknown_fields_preserved)

    def test_deprecation_tracking(self):
        self.engine.register_deprecation("old_api", SemVer(2, 0, 0), SemVer(3, 0, 0))
        warns = self.engine.get_deprecation_warnings(SemVer(2, 1, 0))
        self.assertEqual(len(warns), 1)
        self.assertEqual(warns[0]["feature"], "old_api")

    def test_upgrade_path_valid(self):
        res = self.engine.is_upgrade_path_valid(SemVer(2, 0, 0), SemVer(2, 2, 0))
        self.assertTrue(res["valid"])

    def test_upgrade_path_invalid_jump(self):
        res = self.engine.is_upgrade_path_valid(SemVer(2, 0, 0), SemVer(2, 4, 0))
        self.assertFalse(res["valid"])

    def test_upgrade_path_invalid_major(self):
        res = self.engine.is_upgrade_path_valid(SemVer(2, 0, 0), SemVer(3, 0, 0))
        self.assertFalse(res["valid"])

    def test_compatibility_report(self):
        rep = self.engine.get_compatibility_report()
        self.assertIn("control_plane", rep)
        self.assertIn("supported_runners", rep)
        self.assertEqual(rep["control_plane"], "2.1.0")

    def test_no_matrix_handshake(self):
        e = VersionCompatibilityEngine()
        resp = e.negotiate_runner_handshake(RunnerHandshakeRequest("r", SemVer(1,0,0), 1))
        self.assertFalse(resp.accepted)

    def test_no_matrix_mixed(self):
        e = VersionCompatibilityEngine()
        res = e.validate_mixed_version_cluster([])
        self.assertFalse(res["valid"])

    def test_no_matrix_task(self):
        e = VersionCompatibilityEngine()
        res = e.check_runner_task_compatibility([], [], SemVer(1,0,0))
        self.assertFalse(res["compatible"])

    def test_no_matrix_report(self):
        e = VersionCompatibilityEngine()
        rep = e.get_compatibility_report()
        self.assertEqual(rep["status"], "unconfigured")
