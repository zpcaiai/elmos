import unittest
from datetime import datetime
from elmos_mature_platform.api_compatibility_gate_engine import ApiCompatibilityGateEngine
from elmos_mature_platform.types import (
    ApiCompatChangeType,
    CompatibilityVerdict,
    ApiChange,
    SdkCompatibilityMatrix,
    EventSchemaChange,
    CompatibilityGateResult
)

class TestApiCompatibilityGateEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ApiCompatibilityGateEngine()
        
    def test_register_api_version(self):
        self.engine.register_api_version("v1", [{"path": "/users", "fields": {"id": "int"}}])
        self.assertIn("v1", self.engine._api_versions)
        
    def test_compare_versions_endpoint_added(self):
        self.engine.register_api_version("v1", [])
        self.engine.register_api_version("v2", [{"path": "/users", "fields": {}}])
        changes = self.engine.compare_api_versions("v1", "v2")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, ApiCompatChangeType.ENDPOINT_ADDED)
        self.assertEqual(changes[0].verdict, CompatibilityVerdict.COMPATIBLE)
        
    def test_compare_versions_endpoint_removed(self):
        self.engine.register_api_version("v1", [{"path": "/users", "fields": {}}])
        self.engine.register_api_version("v2", [])
        changes = self.engine.compare_api_versions("v1", "v2")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, ApiCompatChangeType.ENDPOINT_REMOVED)
        self.assertEqual(changes[0].verdict, CompatibilityVerdict.BREAKING)
        
    def test_compare_versions_field_added_optional(self):
        self.engine.register_api_version("v1", [{"path": "/users", "fields": {"id": "int"}}])
        self.engine.register_api_version("v2", [{"path": "/users", "fields": {"id": "int", "name": "str"}}])
        changes = self.engine.compare_api_versions("v1", "v2")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, ApiCompatChangeType.FIELD_ADDED)
        self.assertEqual(changes[0].verdict, CompatibilityVerdict.COMPATIBLE)
        
    def test_compare_versions_field_added_required(self):
        self.engine.register_api_version("v1", [{"path": "/users", "fields": {"id": "int"}}])
        self.engine.register_api_version("v2", [{"path": "/users", "fields": {"id": "int", "name": "str"}, "required_fields": ["name"]}])
        changes = self.engine.compare_api_versions("v1", "v2")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, ApiCompatChangeType.REQUIRED_FIELD_ADDED)
        self.assertEqual(changes[0].verdict, CompatibilityVerdict.BREAKING)
        
    def test_compare_versions_field_removed(self):
        self.engine.register_api_version("v1", [{"path": "/users", "fields": {"id": "int", "name": "str"}}])
        self.engine.register_api_version("v2", [{"path": "/users", "fields": {"id": "int"}}])
        changes = self.engine.compare_api_versions("v1", "v2")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, ApiCompatChangeType.FIELD_REMOVED)
        self.assertEqual(changes[0].verdict, CompatibilityVerdict.BREAKING)
        
    def test_compare_versions_field_type_changed(self):
        self.engine.register_api_version("v1", [{"path": "/users", "fields": {"id": "int"}}])
        self.engine.register_api_version("v2", [{"path": "/users", "fields": {"id": "str"}}])
        changes = self.engine.compare_api_versions("v1", "v2")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, ApiCompatChangeType.FIELD_TYPE_CHANGED)
        self.assertEqual(changes[0].verdict, CompatibilityVerdict.BREAKING)

    def test_evaluate_compatibility_gate_pass(self):
        changes = [
            ApiChange(change_id="1", change_type=ApiCompatChangeType.ENDPOINT_ADDED, path="/new", description="", verdict=CompatibilityVerdict.COMPATIBLE)
        ]
        res = self.engine.evaluate_compatibility_gate(changes)
        self.assertTrue(res.passed)
        self.assertEqual(res.compatible_changes, 1)

    def test_evaluate_compatibility_gate_fail_breaking_no_migration(self):
        changes = [
            ApiChange(change_id="2", change_type=ApiCompatChangeType.FIELD_TYPE_CHANGED, path="/users, field: id", description="", verdict=CompatibilityVerdict.BREAKING)
        ]
        res = self.engine.evaluate_compatibility_gate(changes)
        self.assertFalse(res.passed)
        self.assertEqual(len(res.blocking_changes), 1)

    def test_evaluate_compatibility_gate_fail_removal_no_deprecation(self):
        changes = [
            ApiChange(change_id="3", change_type=ApiCompatChangeType.ENDPOINT_REMOVED, path="/old", description="", verdict=CompatibilityVerdict.BREAKING, migration_guide="Use /new")
        ]
        # Has migration guide, but it's an ENDPOINT_REMOVED without prior deprecation registration
        res = self.engine.evaluate_compatibility_gate(changes)
        self.assertFalse(res.passed)
        self.assertEqual(len(res.blocking_changes), 1)

    def test_evaluate_compatibility_gate_pass_removal_with_deprecation(self):
        self.engine.register_deprecation("/old", "v1", "v2", "Use /new")
        changes = [
            ApiChange(change_id="4", change_type=ApiCompatChangeType.ENDPOINT_REMOVED, path="/old", description="", verdict=CompatibilityVerdict.BREAKING, migration_guide="Use /new")
        ]
        res = self.engine.evaluate_compatibility_gate(changes)
        self.assertTrue(res.passed)

    def test_register_sdk(self):
        m = SdkCompatibilityMatrix("java-sdk", "1.0.0")
        self.engine.register_sdk(m)
        self.assertEqual(len(self.engine._sdks), 1)

    def test_check_sdk_impact_no_breaking(self):
        m = SdkCompatibilityMatrix("java-sdk", "1.0.0")
        self.engine.register_sdk(m)
        changes = [ApiChange(change_id="1", change_type=ApiCompatChangeType.ENDPOINT_ADDED, path="/new", description="", verdict=CompatibilityVerdict.COMPATIBLE)]
        impacts = self.engine.check_sdk_impact(changes)
        self.assertEqual(len(impacts), 0)

    def test_check_sdk_impact_with_breaking(self):
        m = SdkCompatibilityMatrix("java-sdk", "1.0.0")
        self.engine.register_sdk(m)
        changes = [ApiChange(change_id="2", change_type=ApiCompatChangeType.FIELD_REMOVED, path="/users", description="", verdict=CompatibilityVerdict.BREAKING)]
        impacts = self.engine.check_sdk_impact(changes)
        self.assertEqual(len(impacts), 1)
        self.assertEqual(impacts[0]["sdk_name"], "java-sdk")
        self.assertEqual(m.breaking_changes_affected[0], "/users")

    def test_detect_event_schema_changes_field_added(self):
        old = {"properties": {"a": "str"}}
        new = {"properties": {"a": "str", "b": "int"}}
        changes = self.engine.detect_event_schema_changes(old, new, "user.created")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change, ApiCompatChangeType.FIELD_ADDED)
        self.assertTrue(changes[0].backward_compatible)

    def test_detect_event_schema_changes_required_added(self):
        old = {"properties": {"a": "str"}}
        new = {"properties": {"a": "str", "b": "int"}, "required": ["b"]}
        changes = self.engine.detect_event_schema_changes(old, new, "user.created")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change, ApiCompatChangeType.REQUIRED_FIELD_ADDED)
        self.assertFalse(changes[0].backward_compatible)

    def test_detect_event_schema_changes_type_changed(self):
        old = {"properties": {"a": "str"}}
        new = {"properties": {"a": "int"}}
        changes = self.engine.detect_event_schema_changes(old, new, "user.created")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change, ApiCompatChangeType.FIELD_TYPE_CHANGED)
        self.assertFalse(changes[0].backward_compatible)
        self.assertFalse(changes[0].forward_compatible)

    def test_detect_event_schema_changes_field_removed(self):
        old = {"properties": {"a": "str"}}
        new = {"properties": {}}
        changes = self.engine.detect_event_schema_changes(old, new, "user.created")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change, ApiCompatChangeType.FIELD_REMOVED)
        self.assertTrue(changes[0].backward_compatible)
        self.assertFalse(changes[0].forward_compatible)

    def test_register_deprecation(self):
        self.engine.register_deprecation("/old", "v1", "v3", "Use /new")
        deps = self.engine.get_active_deprecations()
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0]["api_path"], "/old")

    def test_validate_removal_no_deprecation(self):
        res = self.engine.validate_removal("/not_deprecated", "v2")
        self.assertFalse(res["valid"])

    def test_validate_removal_too_early(self):
        self.engine.register_deprecation("/old", "v1", "v3", "Use /new")
        res = self.engine.validate_removal("/old", "v2")
        self.assertFalse(res["valid"])

    def test_validate_removal_valid(self):
        self.engine.register_deprecation("/old", "v1", "v3", "Use /new")
        res = self.engine.validate_removal("/old", "v3")
        self.assertTrue(res["valid"])

    def test_generate_migration_guide(self):
        self.engine.register_api_version("v1", [{"path": "/old", "fields": {}}])
        self.engine.register_api_version("v2", [])
        self.engine.register_deprecation("/old", "v1", "v2", "Use /new")
        guide = self.engine.generate_migration_guide("v1", "v2")
        self.assertEqual(guide["from_version"], "v1")
        self.assertEqual(guide["to_version"], "v2")
        self.assertEqual(len(guide["steps"]), 1)
        self.assertIn("Use /new", guide["steps"][0])

    def test_get_compatibility_report(self):
        self.engine.register_api_version("v1", [])
        self.engine.register_sdk(SdkCompatibilityMatrix("java-sdk", "1.0"))
        self.engine.register_deprecation("/old", "v1", "v2", "")
        rep = self.engine.get_compatibility_report()
        self.assertEqual(rep["versions_registered"], ["v1"])
        self.assertEqual(rep["total_sdks_registered"], 1)
        self.assertEqual(rep["active_deprecations"], 1)

if __name__ == '__main__':
    unittest.main()
