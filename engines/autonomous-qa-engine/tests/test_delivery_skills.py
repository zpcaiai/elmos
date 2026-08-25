from __future__ import annotations

import base64
import hashlib
import unittest

from elmos_autonomous_qa.adapters import ADAPTER_REGISTRY
from elmos_autonomous_qa.canonical import canonical_digest
from elmos_autonomous_qa.delivery_skills import (
    DeliveryContractError,
    emit_test_sources,
    plan_project_output_contract,
)


def policies() -> dict[str, object]:
    return {
        "retention_policy": {
            "policy_id": "retention-standard",
            "classification": "standard",
            "retention_days": 30,
            "legal_hold": False,
            "deletion_mode": "two-phase",
        },
        "permission_policy": {
            "policy_id": "permission-generated-tests",
            "owner_principals": ["qa-owner"],
            "reader_principals": ["qa-reviewer"],
            "writer_principals": ["qa-owner"],
            "publisher_service": "ArtifactPublisher",
        },
        "secret_policy": {
            "scan_required": True,
            "inline_secrets_allowed": False,
            "allowed_secret_refs": ["secret-ref:qa-runtime"],
            "redaction_required": True,
        },
    }


def output_request(**overrides: object) -> dict[str, object]:
    request: dict[str, object] = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "revision_id": "revision-17",
        "run_id": "run-36",
        "run_mode": "generate",
        "source_snapshot_digest": "a" * 64,
        "output_mode": "sidecar",
        "adapter_key": "python",
        "test_cases": [
            {
                "test_case_id": "TC-export",
                "test_type": "functional",
                "required": True,
                "requirement_refs": ["REQ-export"],
            }
        ],
        "existing_paths": [],
        **policies(),
    }
    request.update(overrides)
    return request


def dsl_case(adapter_key: str, *, case_id: str | None = None) -> dict[str, object]:
    parameters = (
        {"scheme": "ElmosQa"}
        if adapter_key in {"objective-c-xcode", "swift-xcode"}
        else {}
    )
    exact_case_id = case_id or f"TC-{adapter_key}"
    return {
        "test_case_id": exact_case_id,
        "title": f"{adapter_key} observes the tenant-scoped export contract",
        "test_type": "functional",
        "priority": "P0",
        "required": True,
        "requirement_refs": ["REQ-export"],
        "preconditions": ["authorized tenant operator is authenticated"],
        "steps": [
            {
                "step_id": "invoke-export",
                "action": "invoke-export",
                "input": {"tenant_id": "tenant-a"},
                "timeout_ms": 30_000,
                "side_effect": False,
            }
        ],
        "oracles": [
            {
                "oracle_id": "oracle-tenant",
                "kind": "invariant",
                "assertion": "every observed export row has tenant_id tenant-a",
                "source": "REQ-export",
            }
        ],
        "evidence_requirements": ["structured-observation", "raw-runner-output"],
        "cleanup": [],
        "executor": {
            "adapter_key": adapter_key,
            "capability": "unit",
            "parameters": parameters,
            "environment_profile": "isolated-local",
        },
    }


def emission_request(adapter_key: str = "python", **overrides: object) -> dict[str, object]:
    request: dict[str, object] = {
        "suite_id": f"suite-{adapter_key}",
        "adapter_key": adapter_key,
        "test_cases": [dsl_case(adapter_key)],
        "fixture_records": [],
        "mock_records": [],
        "synthetic_data_records": [],
        "config": {"runtime_profile": "isolated-local"},
        "existing_paths": [],
    }
    request.update(overrides)
    return request


class ProjectOutputContractTest(unittest.TestCase):
    def test_plans_outputplan_compatible_identity_paths_and_object_keys(self) -> None:
        result = plan_project_output_contract(output_request())
        identity = {
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "revision_id": "revision-17",
            "run_id": "run-36",
            "source_snapshot_digest": "a" * 64,
            "output_mode": "sidecar",
            "run_mode": "generate",
        }
        expected_output_id = f"out_{canonical_digest(identity)[:24]}"

        self.assertEqual("PARTIAL", result["state"])
        outputs = result["outputs"]
        self.assertEqual(expected_output_id, outputs["output_id"])
        self.assertEqual("revision-17", outputs["revision_id"])
        self.assertTrue(outputs["output_plan_compatibility"]["compatible"])
        self.assertFalse(
            outputs["output_plan_compatibility"]["filesystem_bound_constructor_used"]
        )
        mapping = outputs["logical_native_mappings"][0]
        self.assertEqual("tests/elmos_generated", mapping["target"]["native_root"])
        self.assertTrue(mapping["native_path"].startswith("tests/elmos_generated/test_"))
        self.assertTrue(mapping["artifact_id"].startswith("art_"))
        self.assertIn(f"/artifacts/{mapping['artifact_id']}/", mapping["object_key"])
        self.assertEqual("DRAFT", outputs["manifest_draft"]["status"])
        self.assertEqual("CREATE_ONLY", outputs["no_overwrite_policy"]["mode"])

    def test_rejects_unsafe_path_and_unsafe_policy(self) -> None:
        with self.assertRaises(DeliveryContractError):
            plan_project_output_contract(output_request(native_root="../tests"))

        unsafe_policies = policies()
        unsafe_policies["secret_policy"] = {
            "scan_required": True,
            "inline_secrets_allowed": True,
            "allowed_secret_refs": [],
            "redaction_required": True,
        }
        with self.assertRaises(DeliveryContractError):
            plan_project_output_contract(output_request(**unsafe_policies))

        with self.assertRaises(DeliveryContractError):
            plan_project_output_contract(
                output_request(
                    _runtime_context={
                        "tenant_id": "tenant-b",
                        "project_id": "project-a",
                        "actor_id": "actor-a",
                        "request_id": "request-a",
                        "idempotency_key": None,
                    }
                )
            )

    def test_existing_collision_blocks_and_external_effects_remain_not_run(self) -> None:
        planned = plan_project_output_contract(output_request())
        path = planned["outputs"]["logical_native_mappings"][0]["native_path"]
        blocked = plan_project_output_contract(output_request(existing_paths=[path]))

        self.assertEqual("BLOCKED", blocked["state"])
        self.assertEqual(
            "BLOCKED_NO_OVERWRITE",
            blocked["outputs"]["preflight"]["conflicts"][0]["decision"],
        )
        boundary = blocked["outputs"]["execution_boundary"]
        self.assertFalse(boundary["filesystem_access_performed"])
        self.assertEqual("NOT_RUN", boundary["staging"])
        self.assertEqual("NOT_RUN", boundary["materialization"])
        self.assertEqual("NOT_RUN", boundary["publication"])
        self.assertEqual(
            "EXTERNAL_ADAPTER_REQUIRED",
            boundary["trusted_artifact_publisher_service"],
        )


class TestSourceEmitterTest(unittest.TestCase):
    def test_emits_real_deterministic_source_for_every_adapter_profile(self) -> None:
        self.assertEqual(set(ADAPTER_REGISTRY), set(emission_profiles()))
        for adapter_key in sorted(ADAPTER_REGISTRY):
            with self.subTest(adapter_key=adapter_key):
                request = emission_request(adapter_key)
                first = emit_test_sources(request)
                second = emit_test_sources(request)
                self.assertEqual(first, second)
                outputs = first["outputs"]
                self.assertEqual(sorted(ADAPTER_REGISTRY), outputs["supported_adapter_profiles"])
                self.assertEqual(1, outputs["source_artifact_count"])
                source = next(
                    artifact
                    for artifact in outputs["artifacts"]
                    if artifact["category"] == "test-source"
                )
                raw = base64.b64decode(source["content_base64"], validate=True)
                self.assertEqual(source["source_text"].encode("utf-8"), raw)
                self.assertEqual(
                    "sha256:" + hashlib.sha256(raw).hexdigest(), source["sha256"]
                )
                self.assertIn("oracle-tenant", source["source_text"])
                lowered = source["source_text"].casefold()
                self.assertNotIn("todo", lowered)
                self.assertNotIn("assert true", lowered)
                self.assertNotIn("placeholder", lowered)
                self.assertTrue(source["diff"].startswith("--- /dev/null\n+++ b/"))
                self.assertTrue(source["replay_argv"])
                self.assertEqual(["TC-" + adapter_key], source["test_case_refs"])
                self.assertEqual(["REQ-export"], source["requirement_refs"])

    def test_emits_fixture_mock_synthetic_config_lineage_and_manifest(self) -> None:
        result = emit_test_sources(
            emission_request(
                fixture_records=[
                    {
                        "data_id": "fixture-export",
                        "content": {"tenant_id": "tenant-a", "rows": 2},
                        "test_case_refs": ["TC-python"],
                        "requirement_refs": ["REQ-export"],
                    }
                ],
                mock_records=[
                    {
                        "data_id": "mock-export-service",
                        "content": {"status": 200, "body": {"rows": 2}},
                        "test_case_refs": ["TC-python"],
                        "requirement_refs": ["REQ-export"],
                    }
                ],
                synthetic_data_records=[
                    {
                        "data_id": "synthetic-export",
                        "content": {"seed": 17, "tenant_ids": ["tenant-a"]},
                        "test_case_refs": ["TC-python"],
                        "requirement_refs": ["REQ-export"],
                    }
                ],
            )
        )
        outputs = result["outputs"]
        self.assertEqual(1, outputs["fixture_artifact_count"])
        self.assertEqual(1, outputs["mock_artifact_count"])
        self.assertEqual(1, outputs["synthetic_data_artifact_count"])
        self.assertEqual(1, outputs["config_artifact_count"])
        self.assertEqual(len(outputs["artifacts"]), len(outputs["manifest_draft"]["files"]))
        for artifact in outputs["artifacts"]:
            self.assertEqual(outputs["dsl_digest"], artifact["lineage"]["dsl_digest"])
            self.assertEqual(artifact["sha256"], artifact["lineage"]["content_sha256"])
            self.assertEqual([], artifact["quality_scan"]["findings"])

    def test_rejects_invalid_dsl_markers_secrets_unsafe_paths_and_collisions(self) -> None:
        trivial = dsl_case("python")
        trivial["oracles"][0]["assertion"] = "true"
        with self.assertRaises(DeliveryContractError):
            emit_test_sources(emission_request(test_cases=[trivial]))

        unresolved = dsl_case("python")
        unresolved["oracles"][0]["assertion"] = "export satisfies the TODO contract"
        with self.assertRaises(DeliveryContractError):
            emit_test_sources(emission_request(test_cases=[unresolved]))

        fixed_sleep = dsl_case("python")
        fixed_sleep["oracles"][0]["assertion"] = (
            "the observer calls time.sleep(5) before accepting the export"
        )
        with self.assertRaises(DeliveryContractError):
            emit_test_sources(emission_request(test_cases=[fixed_sleep]))

        with self.assertRaises(DeliveryContractError):
            emit_test_sources(emission_request(native_root="../tests"))

        planned = emit_test_sources(emission_request())
        source_path = next(
            artifact["path"]
            for artifact in planned["outputs"]["artifacts"]
            if artifact["category"] == "test-source"
        )
        with self.assertRaises(DeliveryContractError):
            emit_test_sources(emission_request(existing_paths=[source_path.upper()]))

        with self.assertRaises(DeliveryContractError):
            emit_test_sources(
                emission_request(config={"api_key": "sk-123456789012345678901234"})
            )

        with self.assertRaises(DeliveryContractError):
            emit_test_sources(emission_request(config={"disabled": True}))

        with self.assertRaises(DeliveryContractError):
            emit_test_sources(
                emission_request(_runtime_context={"tenant_id": "tenant-a"})
            )

    def test_truthfully_preserves_all_external_execution_boundaries(self) -> None:
        result = emit_test_sources(emission_request())
        self.assertEqual("PARTIAL", result["state"])
        self.assertEqual("LOCAL_EXECUTED", result["implementation_state"])
        boundary = result["outputs"]["execution_boundary"]
        for name in (
            "staging",
            "materialization",
            "formatter",
            "native_parser",
            "native_linter",
            "test_discovery",
            "native_build",
            "smoke_execution",
            "parser",
            "linter",
            "discovery",
            "build",
            "smoke",
        ):
            self.assertEqual("NOT_RUN", boundary[name])
        self.assertFalse(boundary["filesystem_access_performed"])
        self.assertFalse(boundary["materialization_authorized"])
        self.assertFalse(boundary["publication_authorized"])
        self.assertEqual("EXTERNAL_ADAPTER_REQUIRED", boundary["publisher_service"])
        self.assertEqual("EXTERNAL_ADAPTER_REQUIRED", boundary["runtime_binding"])
        self.assertTrue(boundary["trusted_artifact_publisher_service_required"])
        self.assertEqual("NOT_RUN", result["outputs"]["manifest_draft"]["publication_state"])
        self.assertEqual(
            "NOT_CERTIFIED", result["outputs"]["manifest_draft"]["certification_state"]
        )


def emission_profiles() -> tuple[str, ...]:
    """Expected complete registry snapshot owned by the delivery emitter contract."""

    return (
        "java-maven",
        "java-gradle",
        "kotlin-maven",
        "kotlin-gradle",
        "python",
        "dotnet",
        "go",
        "rust",
        "cmake-c-cpp",
        "php-composer",
        "javascript-node",
        "typescript-node",
        "react",
        "vue",
        "objective-c-xcode",
        "swift-package",
        "swift-xcode",
        "flutter",
    )


if __name__ == "__main__":
    unittest.main()
