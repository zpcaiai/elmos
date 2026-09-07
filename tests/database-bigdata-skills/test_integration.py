from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
TOOLING = ROOT / "tooling"
if str(TOOLING) not in sys.path:
    sys.path.insert(0, str(TOOLING))


def load_integration_module():
    path = TOOLING / "integrate_database_bigdata_skills.py"
    spec = importlib.util.spec_from_file_location("database_bigdata_integration", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load integration module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


with mock.patch.object(
    subprocess,
    "run",
    side_effect=AssertionError(
        "importing the integration module executed package code"
    ),
):
    integration = load_integration_module()

PINNED_ARCHIVE_SHA256 = (
    "e5baae82593d84f4784900de7be93a7fa0b582dc081ac97bc35a4d6e12865e53"
)
PINNED_MANIFEST_SHA256 = (
    "285164d0264b2d5e141fd98c8a1ce3578bafdd5470463485ee1e8cb429ea5115"
)
EXPECTED_ALIASES = (
    "elmos-batch-processing-generator",
    "elmos-bigdata-api-dashboard",
    "elmos-bigdata-auto-repair",
    "elmos-bigdata-cost-autotuning",
    "elmos-bigdata-evidence-certification",
    "elmos-bigdata-infra-deployment",
    "elmos-bigdata-pattern-selector",
    "elmos-bigdata-performance-chaos",
    "elmos-bigdata-project-classifier",
    "elmos-bigdata-project-orchestrator",
    "elmos-bigdata-security-governance",
    "elmos-bigdata-test-validation",
    "elmos-cdc-event-backbone",
    "elmos-data-architecture-adr",
    "elmos-data-modeling-semantic-layer",
    "elmos-data-quality-observability",
    "elmos-data-requirement-intake",
    "elmos-database-benchmark-harness",
    "elmos-database-capability-registry",
    "elmos-database-constraint-filter",
    "elmos-database-cost-capacity-planner",
    "elmos-database-ha-dr",
    "elmos-database-mcda-ranker",
    "elmos-database-migration-modernization",
    "elmos-database-schema-physical-design",
    "elmos-database-security-multitenancy",
    "elmos-feature-store-ml-pipeline",
    "elmos-federated-query-data-fabric",
    "elmos-ingestion-connector-planner",
    "elmos-lakehouse-generator",
    "elmos-metadata-catalog-lineage",
    "elmos-orchestration-backfill-replay",
    "elmos-polyglot-persistence-planner",
    "elmos-stream-processing-generator",
    "elmos-template-cdc-migration-modernization",
    "elmos-template-data-governance-platform",
    "elmos-template-fraud-risk",
    "elmos-template-iot-timeseries",
    "elmos-template-log-observability",
    "elmos-template-offline-warehouse",
    "elmos-template-realtime-analytics",
    "elmos-template-realtime-user-profile",
    "elmos-template-recommendation-system",
    "elmos-template-vector-knowledge-analytics",
    "elmos-warehouse-olap-serving",
    "elmos-workload-profiler",
)
EXPECTED_PROFILE_NAMES = (
    "architecture",
    "artifacts",
    "bigdata-core",
    "bootstrap",
    "conversion",
    "database",
    "enterprise",
    "full",
    "reader",
    "templates",
)


class DatabaseBigDataSkillIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.subprocess_run_patcher = mock.patch.object(
            subprocess,
            "run",
            side_effect=AssertionError(
                "ordinary database/Big Data integration tests executed package code"
            ),
        )
        cls.subprocess_run = cls.subprocess_run_patcher.start()
        cls.addClassCleanup(cls.subprocess_run_patcher.stop)
        cls.expected = integration.build_expected(ROOT)

    def copy_archive(self, destination: Path) -> None:
        archive_source = ROOT / integration.ARCHIVE_RELATIVE
        archive_target = destination / integration.ARCHIVE_RELATIVE
        archive_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive_source, archive_target)
        engine_source = ROOT / integration.ENGINE_RELATIVE
        engine_target = destination / integration.ENGINE_RELATIVE
        engine_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(engine_source, engine_target)

    def make_minimal_repository(self, destination: Path) -> None:
        self.copy_archive(destination)

        source_source = ROOT / integration.SOURCE_RELATIVE
        source_target = destination / integration.SOURCE_RELATIVE
        source_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_source, source_target)

    def installed_snapshot(self, repository: Path) -> dict[str, bytes]:
        snapshot: dict[str, bytes] = {}
        for relative_root in (
            integration.RUNTIME_RELATIVE,
            integration.WORKSPACE_RELATIVE,
            integration.DOC_RELATIVE,
        ):
            root = repository / relative_root
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    snapshot[path.relative_to(repository).as_posix()] = (
                        path.read_bytes()
                    )
        return snapshot

    def transaction_residue(self, repository: Path) -> list[str]:
        markers = (".stage.", ".backup.", ".extract.")
        return sorted(
            path.relative_to(repository).as_posix()
            for path in repository.rglob("*")
            if any(marker in path.name for marker in markers)
        )

    def test_01_source_archive_and_contract_inventory_are_pinned(self) -> None:
        summary = self.expected["summary"]
        archive = ROOT / integration.ARCHIVE_RELATIVE
        source_manifest = ROOT / integration.SOURCE_RELATIVE / "MANIFEST.json"
        self.assertEqual(
            PINNED_ARCHIVE_SHA256, hashlib.sha256(archive.read_bytes()).hexdigest()
        )
        self.assertEqual(
            PINNED_MANIFEST_SHA256,
            hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
        )
        self.assertEqual(PINNED_ARCHIVE_SHA256, integration.EXPECTED_ARCHIVE_SHA256)
        self.assertEqual(PINNED_MANIFEST_SHA256, integration.EXPECTED_MANIFEST_SHA256)
        self.assertEqual(98, len(summary["inventory"]))
        self.assertEqual(
            EXPECTED_ALIASES, tuple(item["name"] for item in summary["skills"])
        )
        self.assertEqual(
            EXPECTED_ALIASES,
            tuple(item["name"] for item in self.expected["manifest"]["skills"]),
        )
        self.assertEqual(
            EXPECTED_PROFILE_NAMES,
            tuple(item["profile"] for item in summary["profiles"]),
        )
        self.assertEqual(554, self.expected["manifest"]["stable_task_id_count"])
        task_ids = [
            task_id
            for item in self.expected["manifest"]["skills"]
            for task_id in item["source_task_ids"]
        ]
        self.assertEqual(554, len(task_ids))
        self.assertEqual(554, len(set(task_ids)))
        self.assertEqual(7, self.expected["manifest"]["schema_count"])
        self.assertEqual(
            {
                "bigdata-core": 22,
                "bigdata-templates": 10,
                "database-intelligence": 13,
                "orchestration": 1,
            },
            summary["manifest"]["group_counts"],
        )
        self.assertEqual(
            {
                "technologies": 29,
                "patterns": 10,
                "templates": 10,
                "adapter_blueprints": 13,
            },
            summary["catalogs"],
        )
        self.assertTrue(
            summary["manifest"]["trust_boundary"]["catalog_is_seed_evidence"]
        )

    def test_02_all_normalized_skills_use_codex_frontmatter_and_fail_closed_claims(
        self,
    ) -> None:
        for root_relative in (
            integration.RUNTIME_RELATIVE,
            integration.WORKSPACE_RELATIVE,
        ):
            for record in self.expected["manifest"]["skills"]:
                skill_root = ROOT / root_relative / record["name"]
                valid, message = integration.skill_creator_tools.validate_skill(
                    skill_root
                )
                self.assertTrue(valid, f"{skill_root}: {message}")
                text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn('skill_implementation_state: "DECLARED"', text)
                self.assertIn(
                    'repository_runtime_binding: "BOUNDED_PLAN_SKELETON"', text
                )
                self.assertIn('repository_handler_runtime_evidence: "NOT_RUN"', text)
                self.assertIn('whole_skill_implementation_effect: "NONE"', text)
                self.assertIn('provider_runtime_evidence: "NOT_RUN"', text)
                self.assertIn('production_certification: "NOT_CERTIFIED"', text)
                self.assertIn("## Repository Integration Boundary", text)

    def test_03_dual_roots_are_byte_identical_and_installation_has_no_drift(
        self,
    ) -> None:
        checked = integration.check_install(ROOT)
        self.assertTrue(checked["manifest"]["dual_root_byte_identical"])
        for name in checked["trees"]:
            runtime = integration.read_tree(ROOT / integration.RUNTIME_RELATIVE / name)
            workspace = integration.read_tree(
                ROOT / integration.WORKSPACE_RELATIVE / name
            )
            self.assertEqual(runtime, workspace)

    def test_04_manifest_preserves_evidence_boundaries(self) -> None:
        manifest = self.expected["manifest"]
        self.assertEqual("CATALOG_ONLY", manifest["technology_catalog_state"])
        self.assertEqual(0, manifest["provider_adapter_implementation_count"])
        self.assertEqual("DECLARED", manifest["skill_implementation_state"])
        self.assertEqual(46, manifest["repository_bounded_handler_count"])
        self.assertEqual(
            "BOUND_PLAN_SKELETON_ONLY",
            manifest["repository_bounded_handler_state"],
        )
        self.assertEqual(
            "elmos-tree-digest-v2",
            manifest["repository_runtime_digest_algorithm"],
        )
        self.assertEqual(
            manifest["repository_runtime_file_count"],
            len(manifest["repository_runtime_files"]),
        )
        self.assertEqual(
            "STATIC_PLAN_SKELETON_BEST_EFFORT",
            manifest["repository_runtime_static_validation"],
        )
        self.assertEqual(
            "ISOLATED_DIRECT_LAUNCHER_VERIFIED_SOURCE_LOADER",
            manifest["repository_runtime_preimport_check"],
        )
        self.assertFalse(manifest["repository_external_effects_declared"])
        self.assertEqual("NOT_RUN", manifest["repository_handler_runtime_evidence"])
        self.assertEqual("NOT_RUN", manifest["reference_tool_state"])
        self.assertEqual("NOT_RUN", manifest["provider_runtime_evidence"])
        self.assertEqual("NOT_RUN", manifest["external_evidence_status"])
        self.assertEqual("NOT_CERTIFIED", manifest["production_certification"])
        self.assertEqual("ABSENT", manifest["source_license_status"])
        self.assertEqual("ABSENT", manifest["source_signature_status"])
        self.assertEqual("ABSENT", manifest["source_sbom_status"])
        self.assertEqual("ABSENT", manifest["source_provenance_attestation_status"])
        self.assertEqual("STRUCTURAL_SKILLS_INSTALLED", manifest["maximum_local_claim"])
        self.assertIsNone(manifest["local_qualification_path"])
        self.assertIsNone(manifest["local_qualification_sha256"])
        self.assertEqual(46, len(manifest["skills"]))
        self.assertEqual(3, len(manifest["reference_tools"]))
        self.assertTrue(
            all(
                item["qualification_state"] == "NOT_RUN"
                and item["whole_skill_implementation_effect"] == "NONE"
                for item in manifest["reference_tools"]
            )
        )
        self.assertTrue(
            all(
                item["reference_tool_state"] == "NOT_APPLICABLE_TO_WHOLE_SKILL"
                for item in manifest["skills"]
            )
        )
        self.assertTrue(
            all(
                item["skill_implementation_state"] == "DECLARED"
                and item["repository_runtime_binding"] == "BOUNDED_PLAN_SKELETON"
                and item["repository_handler_runtime_evidence"] == "NOT_RUN"
                and item["whole_skill_implementation_effect"] == "NONE"
                for item in manifest["skills"]
            )
        )

    def test_05_local_reference_qualification_is_optional_and_absent(self) -> None:
        self.assertIsNone(self.expected["qualification"])
        self.assertEqual({}, self.expected["qualification_files"])
        self.assertFalse(
            (ROOT / integration.DOC_RELATIVE / integration.QUALIFICATION_NAME).exists()
        )
        self.assertFalse(
            (
                ROOT
                / integration.DOC_RELATIVE
                / integration.QUALIFICATION_EVIDENCE_DIRECTORY
            ).exists()
        )

    def test_06_non_qualification_modes_never_execute_source_package_code(self) -> None:
        self.subprocess_run.reset_mock()
        with tempfile.TemporaryDirectory(
            prefix="elmos-database-bigdata-no-exec-"
        ) as temporary:
            repository = Path(temporary)
            self.copy_archive(repository)
            integration.extract_canonical_source(repository)
            integration.write_install(repository)
            integration.check_install(repository)
        self.subprocess_run.assert_not_called()

    def test_07_canonical_source_byte_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="elmos-database-bigdata-drift-"
        ) as temporary:
            repository = Path(temporary)
            self.make_minimal_repository(repository)
            target = repository / integration.SOURCE_RELATIVE / "README.md"
            target.write_text(
                target.read_text(encoding="utf-8") + "drift\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "byte count mismatch|differs from archive bytes",
            ):
                integration.validate_source(repository)

    def test_08_first_install_refuses_an_unowned_skill_collision(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="elmos-database-bigdata-collision-"
        ) as temporary:
            repository = Path(temporary)
            self.make_minimal_repository(repository)
            collision = (
                repository
                / integration.RUNTIME_RELATIVE
                / "elmos-data-requirement-intake"
            )
            collision.mkdir(parents=True)
            (collision / "SKILL.md").write_text("user-owned\n", encoding="utf-8")
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "unowned runtime Skill|symbolic-link component",
            ):
                integration.write_install(repository)
            self.assertEqual(
                "user-owned\n", (collision / "SKILL.md").read_text(encoding="utf-8")
            )
            self.assertFalse((repository / integration.WORKSPACE_RELATIVE).exists())
            self.assertFalse((repository / integration.DOC_RELATIVE).exists())
            self.assertEqual([], self.transaction_residue(repository))

    def test_09_clean_temporary_install_is_complete_and_reproducible(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="elmos-database-bigdata-install-"
        ) as temporary:
            repository = Path(temporary)
            self.copy_archive(repository)
            extracted = integration.extract_canonical_source(repository)
            self.assertEqual(
                integration.EXPECTED_SOURCE_FILES,
                len(integration.source_files(extracted)),
            )
            first = integration.write_install(repository)
            first_snapshot = self.installed_snapshot(repository)
            second = integration.write_install(repository)
            second_snapshot = self.installed_snapshot(repository)
            checked = integration.check_install(repository)
            self.assertEqual(first["manifest_bytes"], second["manifest_bytes"])
            self.assertEqual(second["manifest_bytes"], checked["manifest_bytes"])
            self.assertEqual(first_snapshot, second_snapshot)
            self.assertEqual([], self.transaction_residue(repository))
            manifest_path = (
                repository
                / integration.DOC_RELATIVE
                / integration.INSTALL_MANIFEST_NAME
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(46, manifest["skill_count"])
            self.assertEqual("NOT_RUN", manifest["reference_tool_state"])
            self.assertEqual("NOT_CERTIFIED", manifest["production_certification"])

    def test_10_extracted_executable_mode_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="elmos-database-bigdata-mode-"
        ) as temporary:
            repository = Path(temporary)
            self.make_minimal_repository(repository)
            target = (
                repository / integration.SOURCE_RELATIVE / "tools/database_selector.py"
            )
            target.chmod(0o644)
            with self.assertRaisesRegex(
                integration.IntegrationError, "mode differs from archive"
            ):
                integration.validate_source(repository)

    def test_11_tampered_previous_manifest_cannot_self_authorize_tree_overwrite(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="elmos-database-bigdata-owned-drift-"
        ) as temporary:
            repository = Path(temporary)
            self.copy_archive(repository)
            integration.write_install(repository)
            name = "elmos-data-requirement-intake"
            installed_trees: dict[str, dict[str, bytes]] = {}
            for label, relative_root in (
                ("runtime", integration.RUNTIME_RELATIVE),
                ("workspace", integration.WORKSPACE_RELATIVE),
            ):
                skill_root = repository / relative_root / name
                skill_path = skill_root / "SKILL.md"
                skill_path.write_bytes(
                    skill_path.read_bytes() + b"\nuser-owned drift\n"
                )
                installed_trees[label] = integration.read_tree(skill_root)
            self.assertEqual(installed_trees["runtime"], installed_trees["workspace"])

            manifest_path = (
                repository
                / integration.DOC_RELATIVE
                / integration.INSTALL_MANIFEST_NAME
            )
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
            record = next(item for item in previous["skills"] if item["name"] == name)
            record["runtime_skill_sha256"] = integration.digest(
                installed_trees["runtime"]["SKILL.md"]
            )
            record["workspace_skill_sha256"] = integration.digest(
                installed_trees["workspace"]["SKILL.md"]
            )
            record["runtime_interface_sha256"] = integration.digest(
                installed_trees["runtime"]["agents/openai.yaml"]
            )
            record["workspace_interface_sha256"] = integration.digest(
                installed_trees["workspace"]["agents/openai.yaml"]
            )
            record["installed_tree_sha256"] = integration.tree_digest(
                {name: installed_trees["runtime"]}
            )
            manifest_path.write_text(
                json.dumps(previous, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            tampered_snapshot = self.installed_snapshot(repository)

            with self.assertRaises(integration.IntegrationError):
                integration.write_install(repository)
            self.assertEqual(tampered_snapshot, self.installed_snapshot(repository))
            self.assertEqual([], self.transaction_residue(repository))

    def test_12_foreign_documentation_and_installed_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="elmos-database-bigdata-skill-link-"
        ) as temporary:
            repository = Path(temporary)
            self.make_minimal_repository(repository)
            foreign = repository / "user-owned-skill"
            foreign.mkdir()
            marker = foreign / "SKILL.md"
            marker.write_text("user-owned\n", encoding="utf-8")
            collision = (
                repository
                / integration.RUNTIME_RELATIVE
                / "elmos-data-requirement-intake"
            )
            collision.parent.mkdir(parents=True)
            collision.symlink_to(foreign, target_is_directory=True)
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "unowned runtime Skill|symbolic-link component",
            ):
                integration.write_install(repository)
            self.assertTrue(collision.is_symlink())
            self.assertEqual("user-owned\n", marker.read_text(encoding="utf-8"))
            self.assertEqual([], self.transaction_residue(repository))

        with tempfile.TemporaryDirectory(
            prefix="elmos-database-bigdata-doc-link-"
        ) as temporary:
            repository = Path(temporary)
            self.make_minimal_repository(repository)
            foreign = repository / "user-owned-document.md"
            foreign.write_text("user-owned\n", encoding="utf-8")
            doc_root = repository / integration.DOC_RELATIVE
            doc_root.mkdir(parents=True)
            collision = doc_root / integration.README_NAME
            collision.symlink_to(foreign)
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "unowned documentation|may not contain symbolic links",
            ):
                integration.write_install(repository)
            self.assertTrue(collision.is_symlink())
            self.assertEqual("user-owned\n", foreign.read_text(encoding="utf-8"))
            self.assertEqual([], self.transaction_residue(repository))

    def test_13_late_install_failure_rolls_back_without_transaction_residue(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="elmos-database-bigdata-rollback-"
        ) as temporary:
            repository = Path(temporary)
            self.copy_archive(repository)
            integration.write_install(repository)
            before = self.installed_snapshot(repository)
            original_replace = integration.os.replace
            staged_replacements = 0
            injected = False
            final_replacement = len(EXPECTED_ALIASES) * 2 + 2

            def flaky_replace(source, destination):
                nonlocal staged_replacements, injected
                if ".stage." in Path(source).name:
                    staged_replacements += 1
                    if staged_replacements == final_replacement and not injected:
                        injected = True
                        raise OSError("injected transaction failure")
                return original_replace(source, destination)

            with (
                mock.patch.object(integration.os, "replace", side_effect=flaky_replace),
                self.assertRaisesRegex(OSError, "injected transaction failure"),
            ):
                integration.write_install(repository)
            self.assertTrue(injected)
            integration.check_install(repository)
            self.assertEqual(before, self.installed_snapshot(repository))
            self.assertEqual([], self.transaction_residue(repository))

    def test_14_repository_runtime_drift_invalidates_the_installed_manifest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="elmos-database-bigdata-runtime-drift-"
        ) as temporary:
            repository = Path(temporary)
            self.make_minimal_repository(repository)
            integration.write_install(repository)
            handler = (
                repository
                / integration.ENGINE_PACKAGE_RELATIVE
                / "handlers/database_intelligence.py"
            )
            handler.write_text(
                handler.read_text(encoding="utf-8") + "\n# injected drift\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "installation drifted",
            ):
                integration.check_install(repository)

    def test_15_repository_runtime_side_effect_paths_fail_static_validation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="elmos-database-bigdata-runtime-side-effect-"
        ) as temporary:
            repository = Path(temporary)
            self.make_minimal_repository(repository)
            handler = (
                repository
                / integration.ENGINE_PACKAGE_RELATIVE
                / "handlers/database_intelligence.py"
            )
            handler.write_text(
                handler.read_text(encoding="utf-8")
                + "\nimport os\n"
                + "def injected_write():\n"
                + "    return Path('escape').write_text('unsafe')\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "outside the static allowlist|forbidden side-effect call",
            ):
                integration.write_install(repository)

    def test_16_repository_runtime_bytecode_fails_static_validation(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="elmos-database-bigdata-runtime-bytecode-"
        ) as temporary:
            repository = Path(temporary)
            self.make_minimal_repository(repository)
            bytecode = repository / integration.ENGINE_PACKAGE_RELATIVE / "__pycache__"
            bytecode.mkdir()
            (bytecode / "runtime.cpython-312.pyc").write_bytes(b"untrusted-bytecode")
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "forbidden bytecode",
            ):
                integration.write_install(repository)


if __name__ == "__main__":
    unittest.main(verbosity=2)
