import unittest
from elmos_mature_platform.types import (
    EventSchemaVersion,
    EventSchemaChangeType as SchemaChangeType,
    SchemaCompatResult
)
from elmos_mature_platform.event_schema_compatibility_engine import EventSchemaCompatibilityEngine

class TestEventSchemaCompatibilityEngine(unittest.TestCase):
    def setUp(self):
        self.engine = EventSchemaCompatibilityEngine()

    def _create_schema(self, schema_id, event_type, version, fields=None, required=None, enums=None, registered_at=None):
        return EventSchemaVersion(
            schema_id=schema_id,
            event_type=event_type,
            version=version,
            fields=fields or {},
            required_fields=required or [],
            enum_fields=enums or {},
            registered_at=registered_at or ""
        )

    # 1. Register schema success
    def test_register_schema_success(self):
        schema = self._create_schema("s1", "UserEvent", "v1")
        res = self.engine.register_schema(schema)
        self.assertEqual(res, "s1")
        self.assertEqual(len(self.engine._schemas), 1)

    # 2. Register duplicate
    def test_register_schema_duplicate(self):
        schema = self._create_schema("s1", "UserEvent", "v1")
        self.engine.register_schema(schema)
        with self.assertRaises(ValueError):
            self.engine.register_schema(schema)

    # 3. Deprecate schema
    def test_deprecate_schema(self):
        schema = self._create_schema("s1", "UserEvent", "v1")
        self.engine.register_schema(schema)
        s = self.engine.deprecate_schema("s1")
        self.assertTrue(s.deprecated)

    # 4. Deprecate unknown schema
    def test_deprecate_unknown(self):
        with self.assertRaises(ValueError):
            self.engine.deprecate_schema("unknown")

    # 5. Diff field added
    def test_diff_field_added(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"})
        s2 = self._create_schema("s2", "E", "v2", {"f1": "str", "f2": "int"})
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        changes = self.engine.diff_schemas("s1", "s2")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, SchemaChangeType.FIELD_ADDED)
        self.assertEqual(changes[0].field_name, "f2")
        self.assertFalse(changes[0].breaking)

    # 6. Diff field removed (optional)
    def test_diff_field_removed_optional(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str", "f2": "int"})
        s2 = self._create_schema("s2", "E", "v2", {"f1": "str"})
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        changes = self.engine.diff_schemas("s1", "s2")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, SchemaChangeType.FIELD_REMOVED)
        self.assertFalse(changes[0].breaking)

    # 7. Diff field removed (required)
    def test_diff_field_removed_required(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str", "f2": "int"}, ["f2"])
        s2 = self._create_schema("s2", "E", "v2", {"f1": "str"}, [])
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        changes = self.engine.diff_schemas("s1", "s2")
        # Removing required field gives FIELD_REMOVED (breaking) and REQUIRED_REMOVED (non-breaking)
        removals = [c for c in changes if c.change_type == SchemaChangeType.FIELD_REMOVED]
        self.assertTrue(removals[0].breaking)

    # 8. Diff type changed
    def test_diff_type_changed(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"})
        s2 = self._create_schema("s2", "E", "v2", {"f1": "int"})
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        changes = self.engine.diff_schemas("s1", "s2")
        self.assertEqual(changes[0].change_type, SchemaChangeType.TYPE_CHANGED)
        self.assertTrue(changes[0].breaking)

    # 9. Diff required added
    def test_diff_required_added(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"})
        s2 = self._create_schema("s2", "E", "v2", {"f1": "str"}, ["f1"])
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        changes = self.engine.diff_schemas("s1", "s2")
        self.assertEqual(changes[0].change_type, SchemaChangeType.REQUIRED_ADDED)
        self.assertTrue(changes[0].breaking)

    # 10. Diff required removed
    def test_diff_required_removed(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"}, ["f1"])
        s2 = self._create_schema("s2", "E", "v2", {"f1": "str"})
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        changes = self.engine.diff_schemas("s1", "s2")
        self.assertEqual(changes[0].change_type, SchemaChangeType.REQUIRED_REMOVED)
        self.assertFalse(changes[0].breaking)

    # 11. Diff enum value added
    def test_diff_enum_value_added(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"}, [], {"f1": ["A"]})
        s2 = self._create_schema("s2", "E", "v2", {"f1": "str"}, [], {"f1": ["A", "B"]})
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        changes = self.engine.diff_schemas("s1", "s2")
        self.assertEqual(changes[0].change_type, SchemaChangeType.ENUM_VALUE_ADDED)
        self.assertFalse(changes[0].breaking)

    # 12. Diff enum value removed
    def test_diff_enum_value_removed(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"}, [], {"f1": ["A", "B"]})
        s2 = self._create_schema("s2", "E", "v2", {"f1": "str"}, [], {"f1": ["A"]})
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        changes = self.engine.diff_schemas("s1", "s2")
        self.assertEqual(changes[0].change_type, SchemaChangeType.ENUM_VALUE_REMOVED)
        self.assertTrue(changes[0].breaking)

    # 13. Compat check FULLY_COMPATIBLE
    def test_compat_fully(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"})
        s2 = self._create_schema("s2", "E", "v2", {"f1": "str"})
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        res = self.engine.check_compatibility("s1", "s2")
        self.assertEqual(res, SchemaCompatResult.FULLY_COMPATIBLE)

    # 14. Compat check BACKWARD_COMPATIBLE
    def test_compat_backward(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"})
        s2 = self._create_schema("s2", "E", "v2", {"f1": "str", "f2": "int"})
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        res = self.engine.check_compatibility("s1", "s2")
        self.assertEqual(res, SchemaCompatResult.BACKWARD_COMPATIBLE)

    # 15. Compat check FORWARD_COMPATIBLE
    def test_compat_forward(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str", "f2": "int"})
        s2 = self._create_schema("s2", "E", "v2", {"f1": "str"})
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        res = self.engine.check_compatibility("s1", "s2")
        self.assertEqual(res, SchemaCompatResult.FORWARD_COMPATIBLE)

    # 16. Compat check BREAKING
    def test_compat_breaking(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"})
        s2 = self._create_schema("s2", "E", "v2", {"f1": "int"})
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        res = self.engine.check_compatibility("s1", "s2")
        self.assertEqual(res, SchemaCompatResult.BREAKING)

    # 17. Compat check UNKNOWN
    def test_compat_unknown(self):
        res = self.engine.check_compatibility("s1", "unknown")
        self.assertEqual(res, SchemaCompatResult.UNKNOWN)

    # 18. History ordering
    def test_schema_history(self):
        s1 = self._create_schema("s1", "E", "v1", registered_at="2023-01-01T00:00:00Z")
        s2 = self._create_schema("s2", "E", "v2", registered_at="2023-01-02T00:00:00Z")
        self.engine.register_schema(s2)
        self.engine.register_schema(s1)
        history = self.engine.get_schema_history("E")
        self.assertEqual(history[0].schema_id, "s1")
        self.assertEqual(history[1].schema_id, "s2")

    # 19. History empty
    def test_schema_history_empty(self):
        self.assertEqual(self.engine.get_schema_history("E"), [])

    # 20. Latest schema
    def test_latest_schema(self):
        s1 = self._create_schema("s1", "E", "v1", registered_at="2023-01-01T00:00:00Z")
        s2 = self._create_schema("s2", "E", "v2", registered_at="2023-01-02T00:00:00Z")
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        latest = self.engine.get_latest_schema("E")
        self.assertEqual(latest.schema_id, "s2")

    # 21. Latest schema not found
    def test_latest_schema_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_latest_schema("E")

    # 22. Validate evolution valid
    def test_validate_evolution_valid(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"})
        s2 = self._create_schema("s2", "E", "v2", {"f1": "str", "f2": "int"})
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        res = self.engine.validate_evolution("E")
        self.assertTrue(res["valid"])
        self.assertEqual(len(res["breaking_changes"]), 0)

    # 23. Validate evolution breaking
    def test_validate_evolution_breaking(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"})
        s2 = self._create_schema("s2", "E", "v2", {"f1": "int"})
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        res = self.engine.validate_evolution("E")
        self.assertFalse(res["valid"])
        self.assertEqual(len(res["breaking_changes"]), 1)

    # 24. Validate evolution single schema
    def test_validate_evolution_single(self):
        s1 = self._create_schema("s1", "E", "v1")
        self.engine.register_schema(s1)
        res = self.engine.validate_evolution("E")
        self.assertTrue(res["valid"])

    # 25. Get breaking changes
    def test_get_breaking_changes(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"})
        s2 = self._create_schema("s2", "E", "v2", {"f1": "int"})
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        changes = self.engine.get_breaking_changes("E")
        self.assertEqual(len(changes), 1)

    # 26. Get consumers deterministic
    def test_get_consumers(self):
        c1 = self.engine.get_consumers("E", "v1")
        c2 = self.engine.get_consumers("E", "v1")
        self.assertEqual(c1, c2)
        self.assertTrue(1 <= c1 <= 100)

    # 27. Compatibility report
    def test_compat_report(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"})
        s2 = self._create_schema("s2", "E", "v2", {"f1": "int"})
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        self.engine.deprecate_schema("s1")
        report = self.engine.get_compatibility_report()
        self.assertEqual(report["event_types"], 1)
        self.assertEqual(report["total_schemas"], 2)
        self.assertEqual(report["breaking_changes"], 1)
        self.assertEqual(report["deprecated"], 1)

    # 28. Mixed non-breaking changes backward
    def test_mixed_non_breaking_backward(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"}, ["f1"])
        s2 = self._create_schema("s2", "E", "v2", {"f1": "str", "f2": "int"}, [])
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        # Added f2 (backward), removed required from f1 (backward)
        res = self.engine.check_compatibility("s1", "s2")
        self.assertEqual(res, SchemaCompatResult.BACKWARD_COMPATIBLE)

    # 29. Diff schemas not found
    def test_diff_schemas_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.diff_schemas("a", "b")
            
    # 30. Diff schema same
    def test_diff_schemas_same(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"})
        self.engine.register_schema(s1)
        changes = self.engine.diff_schemas("s1", "s1")
        self.assertEqual(len(changes), 0)

    # 31. Diff required added newly added field
    def test_diff_required_added_new_field(self):
        s1 = self._create_schema("s1", "E", "v1", {"f1": "str"})
        s2 = self._create_schema("s2", "E", "v2", {"f1": "str", "f2": "int"}, ["f2"])
        self.engine.register_schema(s1)
        self.engine.register_schema(s2)
        changes = self.engine.diff_schemas("s1", "s2")
        req_add = [c for c in changes if c.change_type == SchemaChangeType.REQUIRED_ADDED]
        self.assertEqual(len(req_add), 1)
        self.assertTrue(req_add[0].breaking)

if __name__ == '__main__':
    unittest.main()
