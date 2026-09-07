from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import elmos_spring_golden_route.catalog as catalog_module
from elmos_spring_golden_route.catalog import CatalogValidationError, load_catalog
from elmos_spring_golden_route.errors import (
    ExternalAdapterRequired,
    RequestValidationError,
    UnknownSkillError,
)
from elmos_spring_golden_route.runtime import (
    DOMAIN_PHASES,
    build_registry,
    output_media_type,
    validate_request,
)

from common import REPOSITORY_ROOT, request_for


class CatalogRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(REPOSITORY_ROOT)
        cls.registry = build_registry(cls.catalog)

    def test_real_catalog_and_196_distinct_handlers(self) -> None:
        self.assertEqual(self.catalog.skill_count, 196)
        self.assertEqual(len(self.catalog.topological_order), 196)
        self.assertEqual(len(self.registry.handlers), 196)
        self.assertEqual(len({id(handler) for handler in self.registry.handlers.values()}), 196)
        self.assertTrue(all(callable(handler) for handler in self.registry.handlers.values()))

    def test_foundation_batch_identity_normalization_and_plan_surface(self) -> None:
        expected_map = {f"{batch:02d}": f"F{batch:02d}" for batch in range(1, 11)}
        self.assertEqual(dict(self.catalog.foundation_batch_id_map), expected_map)
        self.assertEqual(
            self.catalog.batch_topological_order,
            tuple([f"F{batch:02d}" for batch in range(1, 11)] + [str(batch) for batch in range(11, 23)]),
        )
        examples = {
            "deterministic-first-router": "F10",
            "spring-route-orchestrator": "12",
        }
        for skill_name, expected_batch in examples.items():
            with self.subTest(skill=skill_name):
                result = self.registry.dispatch(request_for(skill_name))
                self.assertEqual(result["schema_version"], "elmos.spring-golden-route.response.v2")
                self.assertEqual(result["batch"], expected_batch)
                self.assertEqual(
                    [item["batch"] for item in result["batch_dependencies"]],
                    list(self.catalog.batch_dependencies[expected_batch]),
                )
                self.assertTrue(all(item["status"] == "NOT_RUN" for item in result["batch_dependencies"]))
                self.assertNotIn("01", [result["batch"], *[item["batch"] for item in result["batch_dependencies"]]])

    def test_every_handler_produces_only_draft_blueprints(self) -> None:
        for index, name in enumerate(self.catalog.topological_order):
            with self.subTest(skill=name):
                request = request_for(
                    name,
                    run_id=f"run-{index}",
                    task_id=f"task-{index}",
                    idempotency_key=f"idem-{index}",
                )
                result = self.registry.dispatch(request)
                self.assertEqual(result["decision"], "DRAFT_ONLY")
                self.assertEqual(result["control_plane_execution_status"], "LOCAL_EXECUTED_SELF_ATTESTED")
                self.assertEqual(set(result["domain_phase_status"]), set(DOMAIN_PHASES))
                self.assertEqual(set(result["domain_phase_status"].values()), {"NOT_RUN"})
                self.assertFalse(result["side_effects_performed"])
                self.assertEqual(result["runtime_evidence_status"], "NOT_RUN")
                self.assertEqual(result["customer_evidence_status"], "NOT_RUN")
                self.assertEqual(result["external_evidence_status"], "NOT_RUN")
                self.assertEqual(result["certification"], "NOT_CERTIFIED")
                self.assertTrue(all(not item["materialized"] for item in result["output_blueprints"]))

    def test_describe_and_unknown_or_extra_fields(self) -> None:
        name = self.catalog.topological_order[0]
        result = self.registry.dispatch(request_for(name, operation="describe"))
        self.assertEqual(result["contract"]["name"], name)
        unknown = request_for("not-a-real-skill", operation="describe")
        with self.assertRaises(UnknownSkillError):
            self.registry.dispatch(unknown)
        extra = request_for(name)
        extra["unexpected"] = True
        with self.assertRaises(RequestValidationError):
            validate_request(extra)
        nested_extra = request_for(name)
        nested_extra["input"]["unexpected"] = True
        with self.assertRaises(RequestValidationError):
            validate_request(nested_extra)

    def test_contract_data_is_deeply_immutable_and_describe_is_stable(self) -> None:
        name = self.catalog.topological_order[0]
        contract = self.catalog.contracts[name]
        before = self.registry.dispatch(request_for(name, operation="describe"))["contract"]
        with self.assertRaises(TypeError):
            contract.data["permissions"]["default"] = "allow"
        with self.assertRaises(AttributeError):
            contract.data["tests"].append("weakened")
        after = self.registry.dispatch(request_for(name, operation="describe"))["contract"]
        self.assertEqual(before, after)

    def test_output_media_types_are_conservative_and_extension_aware(self) -> None:
        self.assertEqual(output_media_type("result.json"), "application/json")
        self.assertEqual(output_media_type("policy.yaml"), "application/yaml")
        self.assertEqual(output_media_type("report.md"), "text/markdown")
        self.assertEqual(output_media_type("delivery.zip"), "application/zip")
        self.assertEqual(output_media_type("phase-events"), "application/octet-stream")

    def test_union_dag_repairs_reverse_edges_and_plans_effective_dependencies_once(self) -> None:
        positions = {name: index for index, name in enumerate(self.catalog.topological_order)}
        repaired_edges = (
            ("durable-tool-settlement", "typed-tool-registry"),
            ("multi-cycle-fixpoint", "recipe-change-attribution"),
            ("semantic-search-engine", "repository-knowledge-precompute"),
        )
        for dependent, dependency in repaired_edges:
            self.assertLess(positions[dependency], positions[dependent])
            contract = self.catalog.contracts[dependent]
            self.assertIn(dependency, contract.critical_dependencies)
            self.assertIn(dependency, contract.effective_dependencies)

        request = request_for("multi-cycle-fixpoint")
        dependencies = self.registry.dispatch(request)["dependencies"]
        names = [item["skill_name"] for item in dependencies]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(self.catalog.contracts["multi-cycle-fixpoint"].effective_dependencies))
        self.assertTrue(all(item["dependency_kinds"] for item in dependencies))

    def test_side_effecting_operations_fail_as_external_adapter_required(self) -> None:
        name = self.catalog.topological_order[0]
        for operation in ("execute", "build", "migrate", "provider-call", "repository-write", "certify"):
            with self.subTest(operation=operation), self.assertRaises(ExternalAdapterRequired) as caught:
                self.registry.dispatch(request_for(name, operation=operation))
            self.assertEqual(caught.exception.code, "EXTERNAL_ADAPTER_REQUIRED")

    def test_request_is_deeply_immutable_and_revalidated(self) -> None:
        request = validate_request(request_for(self.catalog.topological_order[0]))
        with self.assertRaises(TypeError):
            request.input["source"]["version"] = "latest"
        with self.assertRaises(AttributeError):
            request.input["constraints"].append("mutate")
        result = self.registry.dispatch(request)
        self.assertEqual(result["source"]["version"], "2.7.18")
        self.assertEqual(result["request_sha256"], request.digest)

    def test_versions_and_commits_must_be_exact(self) -> None:
        name = self.catalog.topological_order[0]
        for field, bad_values in (
            ("version", ("latest", "3.x", "*", ">=3.0", "3.2 - 3.3")),
            ("commit", ("HEAD", "main", "abc123", "refs/heads/main")),
        ):
            for bad in bad_values:
                with self.subTest(field=field, value=bad):
                    request = request_for(name)
                    request["input"]["source"][field] = bad
                    with self.assertRaises(RequestValidationError):
                        validate_request(request)

    def _docs_fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        target = root / "docs" / "spring-golden-route-commercial-skills"
        shutil.copytree(
            REPOSITORY_ROOT / "docs" / "spring-golden-route-commercial-skills",
            target,
        )
        return temporary, root

    def test_manifest_inventory_boundaries_fail_closed_when_tampered(self) -> None:
        changes = {
            "installed_namespace": "wrong",
            "archive_code_execution": "ALLOWED",
            "source_archive_entries": 595,
            "source_archive_bytes": 1,
            "source_archive_uncompressed_bytes": 1,
            "outer_checksum_entries": 1,
            "outer_checksum_sha256": "sha256:" + "0" * 64,
            "foundation_checksum_entries": 1,
            "quarantined_archive_members": [],
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                temporary, root = self._docs_fixture()
                with temporary:
                    path = root / "docs/spring-golden-route-commercial-skills/installed-manifest.json"
                    manifest = json.loads(path.read_text())
                    manifest[field] = value
                    path.write_text(json.dumps(manifest), encoding="utf-8")
                    with self.assertRaises(CatalogValidationError):
                        load_catalog(root, verify_repository_assets=False)

    def test_compiled_digest_name_and_dag_tampering_fail_closed(self) -> None:
        temporary, root = self._docs_fixture()
        with temporary:
            compiled_path = root / "docs/spring-golden-route-commercial-skills/compiled-contracts.json"
            compiled = json.loads(compiled_path.read_text())
            compiled["contracts"][0]["name"] = "tampered-name"
            compiled_path.write_text(json.dumps(compiled), encoding="utf-8")
            manifest_path = root / "docs/spring-golden-route-commercial-skills/installed-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["compiled_contracts_sha256"] = "sha256:" + hashlib.sha256(compiled_path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(CatalogValidationError):
                load_catalog(root, verify_repository_assets=False)

        temporary, root = self._docs_fixture()
        with temporary:
            manifest_path = root / "docs/spring-golden-route-commercial-skills/installed-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["topological_order"] = list(reversed(manifest["topological_order"]))
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(CatalogValidationError):
                load_catalog(root, verify_repository_assets=False)

    def test_source_digest_tampering_fails_closed(self) -> None:
        temporary, root = self._docs_fixture()
        with temporary:
            manifest_path = root / "docs/spring-golden-route-commercial-skills/installed-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["skills"][0]["source_sha256"] = "sha256:" + "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(CatalogValidationError):
                load_catalog(root, verify_repository_assets=False)

    def test_static_runtime_binding_cannot_manufacture_execution_evidence(self) -> None:
        temporary, root = self._docs_fixture()
        with temporary:
            registry_path = root / "docs/spring-golden-route-commercial-skills/runtime-registry.json"
            registry = json.loads(registry_path.read_text())
            registry["bindings"][0]["control_plane_evidence_status"] = "PASSED"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaises(CatalogValidationError):
                load_catalog(root, verify_repository_assets=False)

    def test_catalog_json_is_rejected_before_unbounded_read(self) -> None:
        temporary, root = self._docs_fixture()
        with temporary:
            registry_path = root / "docs/spring-golden-route-commercial-skills/runtime-registry.json"
            registry_path.write_bytes(b" " * 2_000_001)
            with self.assertRaises(CatalogValidationError):
                load_catalog(root, verify_repository_assets=False)

    def _repository_fixture(self, root: Path) -> dict[str, object]:
        shutil.copytree(
            REPOSITORY_ROOT / "docs/spring-golden-route-commercial-skills",
            root / "docs/spring-golden-route-commercial-skills",
        )
        manifest = json.loads(
            (root / "docs/spring-golden-route-commercial-skills/installed-manifest.json").read_text()
        )
        archive_rel = Path(manifest["canonical_source"])
        (root / archive_rel).parent.mkdir(parents=True)
        shutil.copy2(REPOSITORY_ROOT / archive_rel, root / archive_rel)
        for skill in manifest["skills"]:
            for key in ("runtime_path", "workspace_path"):
                source_dir = (REPOSITORY_ROOT / skill[key]).parent
                target_dir = (root / skill[key]).parent
                shutil.copytree(source_dir, target_dir)
        engine_source = REPOSITORY_ROOT / "engines/spring-golden-route-engine/src"
        shutil.copytree(engine_source, root / "engines/spring-golden-route-engine/src")
        return manifest

    def test_installed_schema_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self._repository_fixture(root)
            schema = (
                root
                / manifest["skills"][0]["runtime_path"]
            ).parent / "schemas/skill-contract.schema.json"
            schema.write_bytes(b"{}\n")
            with self.assertRaises(CatalogValidationError):
                load_catalog(root)

    def test_compiled_semantics_must_match_the_pinned_source_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._repository_fixture(root)
            compiled_path = root / "docs/spring-golden-route-commercial-skills/compiled-contracts.json"
            compiled = json.loads(compiled_path.read_text())
            compiled["contracts"][0]["description"] = "rewritten untrusted semantics"
            compiled_path.write_text(json.dumps(compiled), encoding="utf-8")
            manifest_path = root / "docs/spring-golden-route-commercial-skills/installed-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["compiled_contracts_sha256"] = "sha256:" + hashlib.sha256(compiled_path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(CatalogValidationError):
                load_catalog(root)

    def test_synchronized_dual_root_skill_interface_and_manifest_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self._repository_fixture(root)
            skill = manifest["skills"][0]
            for key in ("runtime_path", "workspace_path"):
                skill_path = root / skill[key]
                skill_path.write_bytes(skill_path.read_bytes() + b"\nUntrusted synchronized edit.\n")
                interface_path = skill_path.parent / "agents/openai.yaml"
                interface_path.write_bytes(interface_path.read_bytes() + b"\n# untrusted synchronized edit\n")
            runtime_skill = root / skill["runtime_path"]
            skill["installed_sha256"] = "sha256:" + hashlib.sha256(runtime_skill.read_bytes()).hexdigest()
            skill["interface_sha256"] = "sha256:" + hashlib.sha256(
                (runtime_skill.parent / "agents/openai.yaml").read_bytes()
            ).hexdigest()
            manifest_path = root / "docs/spring-golden-route-commercial-skills/installed-manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(CatalogValidationError):
                load_catalog(root)

    def test_synchronized_manifest_and_compiled_graph_tampering_fails_closed(self) -> None:
        temporary, root = self._docs_fixture()
        with temporary:
            docs = root / "docs/spring-golden-route-commercial-skills"
            compiled_path = docs / "compiled-contracts.json"
            manifest_path = docs / "installed-manifest.json"
            compiled = json.loads(compiled_path.read_text())
            manifest = json.loads(manifest_path.read_text())
            for document in (compiled, manifest):
                document["foundation_critical_skill_dependencies"]["multi-cycle-fixpoint"] = [
                    "deterministic-recipe-engine"
                ]
                document["effective_dependency_edge_count"] = 148
            compiled_path.write_text(json.dumps(compiled), encoding="utf-8")
            manifest["compiled_contracts_sha256"] = "sha256:" + hashlib.sha256(
                compiled_path.read_bytes()
            ).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(CatalogValidationError):
                load_catalog(root, verify_repository_assets=False)

    def test_synchronized_foundation_batch_mapping_coverage_and_topology_tampering_fails_closed(self) -> None:
        def exact_map_drift(manifest: dict[str, object], compiled: dict[str, object]) -> None:
            for document in (manifest, compiled):
                document["foundation_batch_id_map"]["01"] = "F10"

        def normalized_graph_drift(manifest: dict[str, object], compiled: dict[str, object]) -> None:
            for document in (manifest, compiled):
                document["normalized_foundation_batch_dependencies"]["F02"] = []

        def contract_coverage_drift(manifest: dict[str, object], compiled: dict[str, object]) -> None:
            manifest["skills"][0]["source_batch"] = "F02"
            compiled["contracts"][0]["batch"] = "F02"

        def topology_drift(manifest: dict[str, object], compiled: dict[str, object]) -> None:
            for document in (manifest, compiled):
                order = document["batch_topological_order"]
                order[0], order[1] = order[1], order[0]

        attacks = {
            "exact-map": exact_map_drift,
            "normalized-graph": normalized_graph_drift,
            "contract-coverage": contract_coverage_drift,
            "topology": topology_drift,
        }
        for label, mutate in attacks.items():
            with self.subTest(attack=label):
                temporary, root = self._docs_fixture()
                with temporary:
                    docs = root / "docs/spring-golden-route-commercial-skills"
                    manifest_path = docs / "installed-manifest.json"
                    compiled_path = docs / "compiled-contracts.json"
                    manifest = json.loads(manifest_path.read_text())
                    compiled = json.loads(compiled_path.read_text())
                    mutate(manifest, compiled)
                    compiled_path.write_text(json.dumps(compiled, sort_keys=True), encoding="utf-8")
                    compiled_digest = "sha256:" + hashlib.sha256(compiled_path.read_bytes()).hexdigest()
                    manifest["compiled_contracts_sha256"] = compiled_digest
                    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
                    manifest_digest = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                    with (
                        patch.object(catalog_module, "INSTALLED_MANIFEST_SHA256", manifest_digest),
                        patch.object(catalog_module, "COMPILED_CONTRACTS_SHA256", compiled_digest),
                        self.assertRaises(CatalogValidationError),
                    ):
                        load_catalog(root, verify_repository_assets=False)


if __name__ == "__main__":
    unittest.main()
