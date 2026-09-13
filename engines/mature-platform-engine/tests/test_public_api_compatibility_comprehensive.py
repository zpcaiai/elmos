import unittest
from elmos_mature_platform.types import (
    ApiChangeKind,
    ApiEndpointSpec,
    SdkVersionMatrix
)
from elmos_mature_platform.public_api_compatibility_engine import PublicApiCompatibilityEngine

class TestPublicApiCompatibilityComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = PublicApiCompatibilityEngine()

    def _create_spec(self, endpoint_id="ep-1", method="GET", path="/api/v1/users", version="v1.0", params=None, schema="hash-123"):
        return ApiEndpointSpec(
            endpoint_id=endpoint_id,
            method=method,
            path=path,
            version=version,
            parameters=params or {"limit": "int", "offset": "int"},
            response_schema_hash=schema
        )

    def test_register_and_get_endpoint(self):
        spec = self._create_spec()
        self.engine.register_endpoint_spec(spec)
        retrieved = self.engine.get_endpoint_spec("ep-1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.path, "/api/v1/users")

    def test_register_duplicate_endpoint_raises(self):
        spec = self._create_spec()
        self.engine.register_endpoint_spec(spec)
        with self.assertRaises(ValueError):
            self.engine.register_endpoint_spec(spec)

    def test_list_endpoint_specs_with_filter(self):
        self.engine.register_endpoint_spec(self._create_spec("ep-1", version="v1.0"))
        self.engine.register_endpoint_spec(self._create_spec("ep-2", version="v2.0"))
        v1_list = self.engine.list_endpoint_specs("v1.0")
        self.assertEqual(len(v1_list), 1)
        self.assertEqual(v1_list[0].endpoint_id, "ep-1")
        all_list = self.engine.list_endpoint_specs()
        self.assertEqual(len(all_list), 2)

    def test_deprecate_endpoint(self):
        spec = self._create_spec()
        self.engine.register_endpoint_spec(spec)
        updated = self.engine.deprecate_endpoint("ep-1", deprecated_in="v2.0", removal_in="v3.0")
        self.assertTrue(updated.is_deprecated)
        self.assertEqual(updated.deprecated_in, "v2.0")
        self.assertEqual(updated.removal_in, "v3.0")

    def test_deprecate_nonexistent_endpoint_raises(self):
        with self.assertRaises(ValueError):
            self.engine.deprecate_endpoint("nonexistent", "v2.0", "v3.0")

    def test_compare_endpoints_identical_is_compatible(self):
        ep1 = self._create_spec("ep-1", version="v1.0")
        ep2 = self._create_spec("ep-2", version="v2.0")
        assessment = self.engine.compare_endpoints(ep1, ep2)
        self.assertTrue(assessment.compatible)
        self.assertEqual(assessment.change_kind, ApiChangeKind.NON_BREAKING)
        self.assertEqual(len(assessment.breaking_changes), 0)

    def test_compare_endpoints_method_mismatch_is_breaking(self):
        ep1 = self._create_spec("ep-1", method="GET")
        ep2 = self._create_spec("ep-2", method="POST")
        assessment = self.engine.compare_endpoints(ep1, ep2)
        self.assertFalse(assessment.compatible)
        self.assertEqual(assessment.change_kind, ApiChangeKind.BREAKING)
        self.assertTrue(any("HTTP method" in b for b in assessment.breaking_changes))

    def test_compare_endpoints_path_mismatch_is_breaking(self):
        ep1 = self._create_spec("ep-1", path="/users")
        ep2 = self._create_spec("ep-2", path="/accounts")
        assessment = self.engine.compare_endpoints(ep1, ep2)
        self.assertFalse(assessment.compatible)
        self.assertEqual(assessment.change_kind, ApiChangeKind.BREAKING)

    def test_compare_endpoints_param_removal_is_breaking(self):
        ep1 = self._create_spec("ep-1", params={"id": "string", "filter": "string"})
        ep2 = self._create_spec("ep-2", params={"id": "string"})
        assessment = self.engine.compare_endpoints(ep1, ep2)
        self.assertFalse(assessment.compatible)
        self.assertTrue(any("Parameter 'filter' removed" in b for b in assessment.breaking_changes))

    def test_compare_endpoints_param_type_change_is_breaking(self):
        ep1 = self._create_spec("ep-1", params={"id": "int"})
        ep2 = self._create_spec("ep-2", params={"id": "uuid"})
        assessment = self.engine.compare_endpoints(ep1, ep2)
        self.assertFalse(assessment.compatible)
        self.assertTrue(any("Parameter 'id' type changed" in b for b in assessment.breaking_changes))

    def test_compare_endpoints_new_required_param_is_breaking(self):
        ep1 = self._create_spec("ep-1", params={"id": "int"})
        ep2 = self._create_spec("ep-2", params={"id": "int", "token": "string, required"})
        assessment = self.engine.compare_endpoints(ep1, ep2)
        self.assertFalse(assessment.compatible)
        self.assertTrue(any("New required parameter" in b for b in assessment.breaking_changes))

    def test_compare_endpoints_schema_hash_change_is_breaking(self):
        ep1 = self._create_spec("ep-1", schema="hash-A")
        ep2 = self._create_spec("ep-2", schema="hash-B")
        assessment = self.engine.compare_endpoints(ep1, ep2)
        self.assertFalse(assessment.compatible)
        self.assertTrue(any("Response schema altered" in b for b in assessment.breaking_changes))

    def test_compare_endpoints_new_deprecation(self):
        ep1 = self._create_spec("ep-1")
        ep2 = self._create_spec("ep-2")
        ep2.is_deprecated = True
        assessment = self.engine.compare_endpoints(ep1, ep2)
        self.assertTrue(assessment.compatible)
        self.assertEqual(assessment.change_kind, ApiChangeKind.DEPRECATION)

    def test_assess_version_compatibility_full_lifecycle(self):
        self.engine.register_endpoint_spec(self._create_spec("ep-1", method="GET", path="/users", version="v1.0"))
        self.engine.register_endpoint_spec(self._create_spec("ep-2", method="POST", path="/orders", version="v1.0"))

        # In v2.0: /users changed schema (breaking), /orders was deleted, and /items was added
        self.engine.register_endpoint_spec(self._create_spec("ep-3", method="GET", path="/users", version="v2.0", schema="hash-modified"))
        self.engine.register_endpoint_spec(self._create_spec("ep-4", method="GET", path="/items", version="v2.0"))

        summary = self.engine.generate_compatibility_summary("v1.0", "v2.0")
        self.assertFalse(summary["compatible"])
        self.assertEqual(summary["total_endpoints_evaluated"], 3)  # /users (modified), /orders (deleted), /items (new)
        self.assertEqual(summary["breaking_count"], 2)

    def test_sdk_version_matrix_registration_and_lookup(self):
        matrix = SdkVersionMatrix(
            matrix_id="sdk-py-1",
            platform_version="v2.0",
            language="python",
            sdk_version="1.2.0",
            supported=True,
            min_platform_version="v1.5",
            max_platform_version="v2.5"
        )
        self.engine.register_sdk_version(matrix)

        supports = self.engine.get_sdk_support("v2.0", "python")
        self.assertEqual(len(supports), 1)
        self.assertTrue(self.engine.is_sdk_supported("v2.0", "python", "1.2.0"))
        self.assertFalse(self.engine.is_sdk_supported("v2.0", "python", "9.9.9"))
        self.assertFalse(self.engine.is_sdk_supported("v2.0", "java", "1.2.0"))

    def test_register_duplicate_sdk_matrix_raises(self):
        matrix = SdkVersionMatrix(
            matrix_id="sdk-py-1",
            platform_version="v2.0",
            language="python",
            sdk_version="1.2.0"
        )
        self.engine.register_sdk_version(matrix)
        with self.assertRaises(ValueError):
            self.engine.register_sdk_version(matrix)

if __name__ == "__main__":
    unittest.main()
