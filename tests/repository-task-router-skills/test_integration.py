from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
import json
import shutil
import stat
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from typing import Any
from unittest import mock

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
IMPORTER_PATH = REPOSITORY_ROOT / "tooling/integrate_repository_task_router_skills.py"
ARCHIVE_PATH = REPOSITORY_ROOT / (
    "skills/subskills/"
    "elmos-repository-task-decomposition-cost-router-skills-v1.1.0.zip"
)

SPEC = importlib.util.spec_from_file_location(
    "integrate_repository_task_router_skills", IMPORTER_PATH
)
assert SPEC is not None and SPEC.loader is not None
integration = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = integration
SPEC.loader.exec_module(integration)


def _zip_info(
    name: str,
    *,
    kind: str = "file",
    mode: int | None = None,
    compression: int | None = None,
) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.create_system = 3
    if kind == "directory":
        info.external_attr = (stat.S_IFDIR | (mode if mode is not None else 0o2755)) << 16
        info.compress_type = zipfile.ZIP_STORED if compression is None else compression
    else:
        info.external_attr = (stat.S_IFREG | (mode if mode is not None else 0o644)) << 16
        info.compress_type = zipfile.ZIP_DEFLATED if compression is None else compression
    return info


def _write_synthetic_zip(path: Path, members: list[tuple[zipfile.ZipInfo, bytes]]) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w") as archive:
            for info, content in members:
                archive.writestr(info, content)


class RepositoryTaskRouterIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = integration.validate_archive(ARCHIVE_PATH)

    def temporary_repository(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory(prefix="repository-task-router-")
        root = Path(temporary.name)
        archive = root / integration.ARCHIVE_RELATIVE
        archive.parent.mkdir(parents=True)
        shutil.copy2(ARCHIVE_PATH, archive)
        return temporary, root, archive

    def test_archive_identity_inventory_skills_allowlist_and_dag_are_exact(self) -> None:
        snapshot = self.snapshot
        self.assertEqual(integration.EXPECTED_ARCHIVE_SHA256, snapshot.archive_sha256)
        self.assertEqual(72_565, snapshot.archive_bytes)
        self.assertEqual(108, snapshot.entry_count)
        self.assertEqual(63, len(snapshot.files))
        self.assertEqual(45, len(snapshot.directories))
        self.assertEqual(101_831, snapshot.uncompressed_bytes)
        self.assertEqual(
            integration.EXPECTED_SKILLS,
            tuple(skill.name for skill in snapshot.skills),
        )
        self.assertEqual(10, len(integration.EXPECTED_ALLOWLIST))
        self.assertEqual(set(integration.EXPECTED_SKILLS), set(integration.DAG_DEPENDENCIES))
        self.assertEqual(37, len(snapshot.topological_order))
        self.assertEqual(84, sum(map(len, integration.DAG_DEPENDENCIES.values())))
        positions = {name: index for index, name in enumerate(snapshot.topological_order)}
        for name, dependencies in integration.DAG_DEPENDENCIES.items():
            self.assertTrue(all(positions[dependency] < positions[name] for dependency in dependencies))

    def test_source_defects_are_explicit_and_compiled_contracts_repair_them(self) -> None:
        findings = {finding["code"]: finding for finding in self.snapshot.source_findings}
        self.assertEqual(
            {
                "SOURCE_TASK_EXAMPLE_SCHEMA_MISMATCH",
                "SOURCE_MANUAL_NULL_MODEL_ACCEPTED",
                "SOURCE_EXECUTION_MODEL_ALIAS_UNCONSTRAINED",
                "SOURCE_MANIFEST_HAS_NO_DEPENDENCY_DAG",
            },
            set(findings),
        )
        self.assertTrue(all(finding["immutable_source_rewritten"] is False for finding in findings.values()))
        compiled = integration._compiled_schemas()
        request_validator = integration._validator(
            compiled["model-selection-request.schema.json"]
        )
        manual_null = {
            "mode": "manual",
            "selected_model": None,
            "fallback_policy": "strict",
            "verification_policy": "system_required_verifiers",
        }
        self.assertTrue(list(request_validator.iter_errors(manual_null)))
        unknown = dict(manual_null, selected_model="unknown-model")
        self.assertTrue(list(request_validator.iter_errors(unknown)))
        manual = dict(manual_null, selected_model=integration.EXPECTED_ALLOWLIST[0])
        self.assertEqual([], list(request_validator.iter_errors(manual)))
        for forged_field, forged_value in (
            ("locked_by_user", True),
            ("selection_source", "api"),
            ("resolved_at", "2026-01-01T00:00:00Z"),
            ("registry_digest", "sha256:" + "0" * 64),
        ):
            with self.subTest(forged_field=forged_field):
                forged = {**manual, forged_field: forged_value}
                self.assertTrue(list(request_validator.iter_errors(forged)))

        resolved_validator = integration._validator(
            compiled["model-selection-resolved.schema.json"]
        )
        resolved = {
            **manual,
            "optimization_profile": "cost_performance",
            "selection_source": "api",
            "locked_by_user": True,
            "resolved_at": "2026-01-01T00:00:00Z",
            "registry_digest": "sha256:" + "0" * 64,
        }
        self.assertEqual([], list(resolved_validator.iter_errors(resolved)))
        missing_registry_provenance = dict(resolved)
        del missing_registry_provenance["registry_digest"]
        self.assertTrue(
            list(resolved_validator.iter_errors(missing_registry_provenance))
        )

        task_validator = integration._validator(compiled["task.schema.json"])
        valid_task = {
            "id": "T001",
            "title": "Bounded task",
            "objective": "Produce one bounded artifact",
            "owned_paths": ["src/bounded.py"],
            "acceptance": ["python -m unittest tests.test_bounded"],
        }
        self.assertEqual([], list(task_validator.iter_errors(valid_task)))
        unsafe_task = dict(valid_task, owned_paths=["../escape"])
        self.assertTrue(list(task_validator.iter_errors(unsafe_task)))
        missing_ownership = dict(valid_task)
        del missing_ownership["owned_paths"]
        self.assertTrue(list(task_validator.iter_errors(missing_ownership)))
        read_only_task = {**missing_ownership, "read_only": True}
        self.assertEqual([], list(task_validator.iter_errors(read_only_task)))

        execution_validator = integration._validator(
            compiled["execution-record.schema.json"]
        )
        execution = {
            "task_id": "T001",
            "model_alias": integration.EXPECTED_ALLOWLIST[0],
            "attempt": 1,
            "started_at": "2026-01-01T00:00:00Z",
            "result": "passed",
        }
        self.assertEqual([], list(execution_validator.iter_errors(execution)))
        float_cost = {**execution, "cost": 0.1}
        self.assertTrue(list(execution_validator.iter_errors(float_cost)))
        partial_cost = {**execution, "cost_amount": "0.1000"}
        self.assertTrue(list(execution_validator.iter_errors(partial_cost)))
        exact_cost = {
            **partial_cost,
            "cost_currency": "USD",
            "pricing_effective_at": "2026-01-01T00:00:00Z",
            "pricing_registry_digest": "sha256:" + "1" * 64,
        }
        self.assertEqual([], list(execution_validator.iter_errors(exact_cost)))

    def test_runtime_registry_binds_exact_names_without_claiming_execution(self) -> None:
        registry = integration.load_runtime_registry(REPOSITORY_ROOT)
        if not registry.present:
            self.skipTest("repository runtime registry is not present yet")
        self.assertEqual(integration.EXPECTED_SKILLS, registry.names)
        self.assertEqual(set(integration.EXPECTED_SKILLS), set(registry.handlers))
        self.assertEqual(set(integration.EXPECTED_SKILLS), set(registry.canonical_owners))
        expected = integration.build_expected(self.snapshot, REPOSITORY_ROOT)
        manifest = expected["installed_manifest"]
        self.assertEqual(37, manifest["implementation_states"]["IMPLEMENTED"])
        self.assertEqual(0, manifest["implementation_states"]["DECLARED"])
        self.assertEqual("NOT_RUN", manifest["local_evidence_status"])
        self.assertEqual("NOT_RUN", manifest["external_evidence_status"])
        self.assertEqual("NOT_CERTIFIED", manifest["certification_status"])
        for record in manifest["skills"]:
            self.assertEqual("IMPLEMENTED", record["implementation_state"])
            self.assertEqual("NOT_RUN", record["local_evidence_status"])
            self.assertTrue(record["runtime_handler"])
            self.assertTrue(record["canonical_owner"])

        runtime_source = (
            REPOSITORY_ROOT / "packages/repository-orchestrator/src"
        )
        if (runtime_source / "elmos_repository_orchestrator/runtime.py").is_file():
            sys.path.insert(0, str(runtime_source))
            self.addCleanup(lambda: sys.path.remove(str(runtime_source)))
            catalog = importlib.import_module("elmos_repository_orchestrator.catalog")
            runtime = importlib.import_module("elmos_repository_orchestrator.runtime")
            self.assertEqual(integration.EXPECTED_SKILLS, catalog.SKILL_NAMES)
            self.assertEqual(integration.EXPECTED_SKILLS, runtime.handler_names())
            self.assertTrue(callable(runtime.dispatch))
            for name in integration.EXPECTED_SKILLS:
                spec = catalog.SKILL_SPECS[name]
                self.assertEqual(registry.handlers[name], spec.handler)
                self.assertEqual(
                    registry.canonical_owners[name], spec.canonical_owner
                )
                self.assertEqual(
                    registry.adapter_requirements[name], spec.adapter_requirement
                )

    def test_normalized_skill_frontmatter_interface_and_provenance_are_codex_safe(self) -> None:
        expected = integration.build_expected(self.snapshot, REPOSITORY_ROOT)
        for skill in self.snapshot.skills:
            tree = expected["skill_trees"][skill.name]
            frontmatter, body = integration._split_frontmatter(
                tree.files["SKILL.md"].content,
                skill.name,
                integration._default_yaml_loader,
            )
            self.assertEqual({"name", "description", "metadata"}, set(frontmatter))
            self.assertEqual(skill.name, frontmatter["name"])
            self.assertNotIn("version", frontmatter)
            self.assertEqual(skill.version, frontmatter["metadata"]["source_version"])
            self.assertEqual("sha256:" + skill.source_sha256, frontmatter["metadata"]["source_sha256"])
            self.assertIn("Repository runtime binding", body)
            self.assertIn("Immutable package guidance", body)

            contract = json.loads(tree.files["compiled-contract.json"].content)
            if skill.name == "elmos-repository-orchestrator":
                model_selection_input = (
                    "`model_selection` (Smart or manual, validated by "
                    "`elmos-model-selection-controller`)"
                )
                self.assertIn(
                    model_selection_input,
                    contract["contract"]["inputs"],
                )
                self.assertNotIn(
                    "model_selection` (Smart or manual, validated by "
                    "`elmos-model-selection-controller`)",
                    contract["contract"]["inputs"],
                )

            interface_text = tree.files["agents/openai.yaml"].content.decode("utf-8")
            self.assertRegex(interface_text, r'^interface:\n  display_name: "')
            interface: Any = yaml.safe_load(interface_text)["interface"]
            self.assertGreaterEqual(len(interface["short_description"]), 25)
            self.assertLessEqual(len(interface["short_description"]), 64)
            self.assertIn(f"${skill.name}", interface["default_prompt"])
            self.assertTrue(interface["default_prompt"].endswith("."))

    def test_manifest_inventories_every_source_and_installed_file(self) -> None:
        expected = integration.build_expected(self.snapshot, REPOSITORY_ROOT)
        manifest = expected["installed_manifest"]
        self.assertEqual(63, len(manifest["canonical_source"]["files"]))
        self.assertEqual(45, len(manifest["canonical_source"]["directories"]))
        self.assertTrue(all(value is False for value in manifest["source_absence_facts"].values()))
        for record in manifest["canonical_source"]["files"]:
            self.assertRegex(record["sha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual("0644", record["installed_mode"])
        self.assertEqual(37, len(manifest["skills"]))
        self.assertTrue(all(len(record["installed_files"]) == 3 for record in manifest["skills"]))

    def test_archive_path_traversal_absolute_backslash_nfc_and_reserved_names_fail(self) -> None:
        unsafe = (
            f"{integration.ARCHIVE_ROOT}/../escape.txt",
            "/absolute.txt",
            f"{integration.ARCHIVE_ROOT}\\escape.txt",
            f"{integration.ARCHIVE_ROOT}/cafe\u0301.txt",
            f"{integration.ARCHIVE_ROOT}/CON.txt",
            f"{integration.ARCHIVE_ROOT}/trailing.",
        )
        for index, name in enumerate(unsafe):
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix=f"router-unsafe-{index}-"
            ) as temporary:
                archive = Path(temporary) / "unsafe.zip"
                _write_synthetic_zip(
                    archive,
                    [
                        (_zip_info(f"{integration.ARCHIVE_ROOT}/", kind="directory"), b""),
                        (_zip_info(name), b"payload"),
                    ],
                )
                with self.assertRaises(integration.IntegrationError):
                    integration.inspect_archive(
                        archive,
                        trusted_sha256=None,
                        expected_archive_bytes=None,
                        expected_entry_count=None,
                        expected_total_bytes=None,
                        expected_mode_counts=None,
                    )

    def test_archive_duplicate_casefold_symlink_encryption_and_ratio_fail(self) -> None:
        with tempfile.TemporaryDirectory(prefix="router-attacks-") as temporary:
            root = Path(temporary)
            common = [(_zip_info(f"{integration.ARCHIVE_ROOT}/", kind="directory"), b"")]
            cases = {
                "duplicate": [
                    *common,
                    (_zip_info(f"{integration.ARCHIVE_ROOT}/same.txt"), b"one"),
                    (_zip_info(f"{integration.ARCHIVE_ROOT}/same.txt"), b"two"),
                ],
                "casefold": [
                    *common,
                    (_zip_info(f"{integration.ARCHIVE_ROOT}/One.txt"), b"one"),
                    (_zip_info(f"{integration.ARCHIVE_ROOT}/one.txt"), b"two"),
                ],
                "ratio": [
                    *common,
                    (_zip_info(f"{integration.ARCHIVE_ROOT}/zeros.txt"), b"0" * 100_000),
                ],
            }
            for label, members in cases.items():
                with self.subTest(case=label):
                    archive = root / f"{label}.zip"
                    _write_synthetic_zip(archive, members)
                    with self.assertRaises(integration.IntegrationError):
                        integration.inspect_archive(
                            archive,
                            trusted_sha256=None,
                            expected_archive_bytes=None,
                            expected_entry_count=None,
                            expected_total_bytes=None,
                            expected_mode_counts=None,
                        )

        symlink = _zip_info(f"{integration.ARCHIVE_ROOT}/link")
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(integration.IntegrationError, "link, special"):
            integration._member_kind_and_mode(symlink)
        encrypted = _zip_info(f"{integration.ARCHIVE_ROOT}/encrypted")
        encrypted.flag_bits = 0x1
        with self.assertRaisesRegex(integration.IntegrationError, "encrypted"):
            integration._member_kind_and_mode(encrypted)
        oversized = _zip_info(f"{integration.ARCHIVE_ROOT}/oversized")
        oversized.file_size = integration.MAX_ARCHIVE_ENTRY_BYTES + 1
        with self.assertRaisesRegex(integration.IntegrationError, "size"):
            integration._member_kind_and_mode(oversized)

    def test_archive_digest_tamper_fails_before_package_parsing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="router-tamper-") as temporary:
            tampered = Path(temporary) / "tampered.zip"
            tampered.write_bytes(ARCHIVE_PATH.read_bytes() + b"tamper")
            with self.assertRaisesRegex(integration.IntegrationError, "byte count mismatch"):
                integration.validate_archive(tampered)

    def test_write_is_atomic_idempotent_dual_root_exact_and_checkable(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        first = integration.write_integration(root, archive)
        integration.check_integration(root, archive)
        second = integration.write_integration(root, archive)
        self.assertEqual(first.archive_sha256, second.archive_sha256)
        for name in integration.EXPECTED_SKILLS:
            left = integration._read_tree(root / integration.INSTALL_ROOTS[0] / name)
            right = integration._read_tree(root / integration.INSTALL_ROOTS[1] / name)
            self.assertEqual(left, right)
        source = integration._read_tree(root / integration.SOURCE_RELATIVE)
        self.assertEqual(63, len(source.files))
        self.assertEqual(44, len(source.directories))
        for path, record in first.files.items():
            installed = source.files[path]
            self.assertEqual(record.content, installed.content)
            self.assertEqual(record.sha256, hashlib.sha256(installed.content).hexdigest())

        sys.path.insert(0, str(REPOSITORY_ROOT))
        self.addCleanup(lambda: sys.path.remove(str(REPOSITORY_ROOT)))
        from tooling.skill_creator_tools import validate_skill

        for name in integration.EXPECTED_SKILLS:
            valid, reason = validate_skill(root / integration.INSTALL_ROOTS[0] / name)
            self.assertTrue(valid, f"{name}: {reason}")

    def test_preflight_collision_refuses_without_partial_installation(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        collision = root / integration.INSTALL_ROOTS[0] / integration.EXPECTED_SKILLS[-1]
        collision.mkdir(parents=True)
        (collision / "user.txt").write_text("owned by user", encoding="utf-8")
        with self.assertRaisesRegex(integration.IntegrationError, "refusing unowned"):
            integration.write_integration(root, archive)
        self.assertFalse((root / integration.SOURCE_RELATIVE).exists())
        self.assertFalse((root / integration.DOC_RELATIVE).exists())
        self.assertFalse((root / integration.INSTALL_ROOTS[1] / integration.EXPECTED_SKILLS[0]).exists())
        self.assertEqual("owned by user", (collision / "user.txt").read_text(encoding="utf-8"))

    def test_check_and_write_both_fail_closed_on_managed_drift(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        integration.write_integration(root, archive)
        skill = root / integration.INSTALL_ROOTS[0] / integration.EXPECTED_SKILLS[0] / "SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8") + "\ndrift\n", encoding="utf-8")
        with self.assertRaisesRegex(integration.IntegrationError, "drifted"):
            integration.check_integration(root, archive)
        with self.assertRaisesRegex(integration.IntegrationError, "refusing unowned"):
            integration.write_integration(root, archive)

    def test_documentation_refresh_requires_exact_prior_receipt(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        integration.write_integration(root, archive)
        documentation = root / integration.DOC_RELATIVE
        before = integration._read_tree(documentation)
        integration._verify_managed_documentation(documentation, self.snapshot)

        original_readme = integration._readme

        def revised_readme(*args: Any, **kwargs: Any) -> bytes:
            return original_readme(*args, **kwargs) + b"\nManaged refresh fixture.\n"

        with mock.patch.object(integration, "_readme", side_effect=revised_readme):
            integration.write_integration(root, archive)
            integration.check_integration(root, archive)
        after = integration._read_tree(documentation)
        self.assertNotEqual(before, after)
        self.assertIn(b"Managed refresh fixture", after.files["README.md"].content)

        readme = documentation / "README.md"
        readme.write_bytes(readme.read_bytes() + b"unreceipted drift\n")
        with self.assertRaisesRegex(integration.IntegrationError, "ownership file drifted"):
            integration.write_integration(root, archive)

    def test_dual_root_skill_refresh_requires_manifest_owned_prior_digest(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        integration.write_integration(root, archive)
        original_contract = integration._compiled_contract

        def revised_contract(*args: Any, **kwargs: Any) -> dict[str, Any]:
            contract = copy.deepcopy(original_contract(*args, **kwargs))
            contract["managed_refresh_fixture"] = True
            return contract

        with mock.patch.object(
            integration,
            "_compiled_contract",
            side_effect=revised_contract,
        ):
            integration.write_integration(root, archive)
            integration.check_integration(root, archive)
            for name in integration.EXPECTED_SKILLS:
                left = integration._read_tree(
                    root / integration.INSTALL_ROOTS[0] / name
                )
                right = integration._read_tree(
                    root / integration.INSTALL_ROOTS[1] / name
                )
                self.assertEqual(left, right)
                contract = json.loads(left.files["compiled-contract.json"].content)
                self.assertIs(contract["managed_refresh_fixture"], True)


if __name__ == "__main__":
    unittest.main()
