from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from elmos_spring_golden_route.catalog import CatalogValidationError, load_catalog
from elmos_spring_golden_route.errors import (
    ExternalAdapterRequired,
    RequestValidationError,
    UnknownSkillError,
)
from elmos_spring_golden_route.runtime import DOMAIN_PHASES, build_registry, validate_request

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

    def test_installed_schema_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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
            schema = (
                root
                / manifest["skills"][0]["runtime_path"]
            ).parent / "schemas/skill-contract.schema.json"
            schema.write_bytes(b"{}\n")
            with self.assertRaises(CatalogValidationError):
                load_catalog(root)


if __name__ == "__main__":
    unittest.main()

