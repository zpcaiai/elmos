"""Direct-ZIP audit and deterministic catalog-generation integration tests."""

from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tooling/integrate_knowledge_skill_model_foundry_skills.py"
MODULE_NAME = "_knowledge_skill_model_foundry_importer_under_test"
ENGINE_SOURCE = ROOT / "engines/knowledge-skill-model-foundry-engine/src"
if str(ENGINE_SOURCE) not in sys.path:
    sys.path.insert(0, str(ENGINE_SOURCE))


def load_tool():
    existing = sys.modules.get(MODULE_NAME)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(MODULE_NAME, TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Foundry importer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def audited_package(tool):
    result = getattr(tool, "_FOCUSED_TEST_AUDIT", None)
    if result is None:
        result = tool.audit_archive(tool.resolve_archive())
        setattr(tool, "_FOCUSED_TEST_AUDIT", result)
    return result


class PackageIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from elmos_foundry.local_semantics import LOCAL_SEMANTIC_SKILLS

        cls.tool = load_tool()
        cls.result = audited_package(cls.tool)
        cls.local_semantic_skills = LOCAL_SEMANTIC_SKILLS

    def test_pinned_archive_and_complete_direct_zip_audit(self) -> None:
        metrics = self.result.archive_metrics
        self.assertEqual(self.result.archive_sha256, self.tool.EXPECTED_ARCHIVE_SHA256)
        self.assertEqual(self.result.archive_bytes, 16_668_810)
        self.assertEqual((metrics.entries, metrics.files, metrics.directories), (16_007, 9_317, 6_690))
        self.assertEqual(metrics.controlled_files, 9_316)
        self.assertEqual(metrics.uncompressed_bytes, 23_561_976)
        self.assertEqual(metrics.compressed_member_bytes, 10_276_814)
        self.assertEqual(set(metrics.executable_files), set(self.tool.EXPECTED_EXECUTABLE_PATHS))

    def test_compiled_catalog_has_runtime_consumers_exact_shape(self) -> None:
        catalog = self.result.compiled_catalog
        self.assertEqual(
            set(catalog),
            {
                "schema_version",
                "package",
                "authority",
                "discovery",
                "atomic_skills",
                "meta_skills",
                "pipelines",
            },
        )
        self.assertEqual(
            catalog["schema_version"],
            "elmos.knowledge-skill-model-foundry.compiled-catalog.v2",
        )
        self.assertEqual(
            set(catalog["package"]),
            {"id", "name", "version", "archive_sha256", "archive_bytes"},
        )
        self.assertEqual(
            catalog["authority"]["auxiliary_json_status"],
            "STALE_NON_AUTHORITATIVE",
        )
        self.assertEqual(
            catalog["discovery"],
            {"startup": "meta-only", "candidate_limit": 16, "activation_limit": 8},
        )
        self.assertEqual(len(catalog["atomic_skills"]), 1_310)
        self.assertEqual(len(catalog["meta_skills"]), 41)
        self.assertEqual(len(catalog["pipelines"]), 14)

        expected_atomic_fields = {
            "name",
            "pack",
            "version",
            "priority",
            "risk_class",
            "maturity",
            "owner",
            "description",
            "kernel",
            "exposure",
            "source_path",
            "source_sha256",
            "source_bindings",
            "dependencies",
            "dependency_semantics",
            "inputs",
            "input_contracts",
            "outputs",
            "output_contracts",
            "preconditions",
            "workflow",
            "allowed_tools",
            "tool_contract",
            "required_gates",
            "evidence_contract",
            "rollback_contract",
            "execution_contract",
            "compatibility_contract",
            "maturity_contract",
            "learning_contract",
            "telemetry_contract",
            "support_contract",
            "business_lines",
            "capability_tags",
            "triggers",
            "negative_triggers",
            "invariants",
            "failure_modes",
            "contract_generation",
            "policy_contract",
            "conformance_contract",
            "activation_contract",
            "handler_id",
            "semantic_handler_binding",
            "capability_state",
            "external_evidence_status",
            "certification_status",
        }
        expected_meta_fields = {"name", "pack", "source_path", "source_sha256", "candidates"}
        expected_pipeline_fields = {
            "name",
            "kind",
            "source_path",
            "source_sha256",
            "execution_mode",
        }
        self.assertTrue(all(set(row) == expected_atomic_fields for row in catalog["atomic_skills"]))
        self.assertTrue(all(set(row) == expected_meta_fields for row in catalog["meta_skills"]))
        self.assertTrue(all(set(row) == expected_pipeline_fields for row in catalog["pipelines"]))
        compiled_local = {
            row["name"] for row in catalog["atomic_skills"]
            if row["capability_state"] == "LOCAL"
        }
        self.assertEqual(self.tool.LOCAL_CAPABILITY_ALLOWLIST, self.local_semantic_skills)
        self.assertEqual(compiled_local, self.local_semantic_skills)
        for row in catalog["atomic_skills"]:
            self.assertEqual(row["handler_id"], "pack." + row["pack"].replace("-", "_"))
            if row["name"] in self.local_semantic_skills:
                self.assertEqual(row["capability_state"], "LOCAL")
                self.assertEqual(
                    row["semantic_handler_binding"],
                    "local." + row["name"],
                )
            else:
                self.assertEqual(row["capability_state"], "PREPARE_ONLY")
                self.assertEqual(row["semantic_handler_binding"], "UNBOUND")
            self.assertEqual(row["external_evidence_status"], "NOT_RUN")
            self.assertEqual(row["certification_status"], "NOT_CERTIFIED")
            self.assertFalse(row["activation_contract"]["corpus_embedded"])
            self.assertEqual(row["tool_contract"]["parameter_schemas"], "UNBOUND")
            self.assertEqual(
                [contract["name"] for contract in row["input_contracts"]], row["inputs"]
            )
            self.assertEqual(
                [contract["name"] for contract in row["output_contracts"]], row["outputs"]
            )
            self.assertTrue(all(contract["required"] for contract in row["input_contracts"]))
            self.assertTrue(
                all(contract["content_addressed"] for contract in row["output_contracts"])
            )
            self.assertTrue(
                all(contract["schema_binding"] == "UNBOUND" for contract in row["input_contracts"])
            )
            self.assertTrue(
                all(contract["schema_binding"] == "UNBOUND" for contract in row["output_contracts"])
            )
            self.assertEqual(set(row["source_bindings"]), {
                "skill_markdown", "skill_contract", "execution_policy", "conformance",
                "eval_contract", "eval_cases",
            })
        self.assertTrue(all(row["execution_mode"] == "PREPARE_ONLY" for row in catalog["pipelines"]))

        generations = {"BASIC": 0, "ENHANCED": 0}
        bootstrap = set()
        for row in catalog["atomic_skills"]:
            generations[row["contract_generation"]] += 1
            if row["dependency_semantics"] == "bootstrap-dag":
                bootstrap.add(row["name"])
        self.assertEqual(generations, {"BASIC": 458, "ENHANCED": 852})
        self.assertEqual(bootstrap, set(self.tool.BOOTSTRAP_DEPENDENCY_SKILLS))

    def test_package_report_retains_declared_gaps(self) -> None:
        report = self.result.package_report
        self.assertEqual(report["validation_state"], "STRUCTURAL_VALIDATED_WITH_DECLARED_GAPS")
        self.assertEqual(report["source_execution"], "NEVER_EXECUTED")
        self.assertEqual(report["counts"]["dependency_edges"], 9_090)
        self.assertEqual(report["evaluation_counts"]["total"], 31_440)
        self.assertEqual(report["capability_states"], {"PREPARE_ONLY": 1_284, "LOCAL": 26})
        self.assertEqual(report["external_evidence_status"], "NOT_RUN")
        self.assertEqual(report["certification_status"], "NOT_CERTIFIED")
        gap_codes = {gap["code"] for gap in report["gaps"]}
        self.assertTrue(
            {
                "AUXILIARY_JSON_CATALOG_STALE",
                "DUPLICATE_SKILL_CONTRACT_SCHEMA",
                "POSTGRESQL_RLS_NOT_IMPLEMENTED",
                "LICENSE_TEXT_PLACEHOLDER",
                "PACKAGE_SIGNATURE_MISSING",
                "SBOM_MISSING",
                "PROVENANCE_ATTESTATION_MISSING",
                "SOURCE_PACKAGE_RUNTIME_IMPLEMENTATION_ABSENT",
            }
            <= gap_codes
        )

    def test_generation_is_deterministic_idempotent_and_collision_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "staging"
            self.assertEqual(
                self.tool.verify_generated_assets(self.result, output_root),
                {"status": "ABSENT", "verified": 0},
            )
            self.assertFalse(output_root.exists(), "read-only verification created output")
            first = self.tool.write_generated_assets(
                self.result, output_root, include_meta_wrappers=True
            )
            self.assertEqual(first["status"], "GENERATED")
            self.assertEqual(first["created"], 43)
            self.assertEqual(
                self.tool.verify_generated_assets(self.result, output_root),
                {"status": "VERIFIED", "verified": 43, "meta_wrappers": "VERIFIED"},
            )
            catalog_dir = output_root / self.tool.CATALOG_RELATIVE
            first_catalog = (catalog_dir / "compiled-catalog.json").read_bytes()
            second = self.tool.write_generated_assets(
                self.result, output_root, include_meta_wrappers=True
            )
            self.assertEqual(second["status"], "ALREADY_IDENTICAL")
            self.assertEqual(second["existing_identical"], 43)
            self.assertEqual((catalog_dir / "compiled-catalog.json").read_bytes(), first_catalog)
            changed = catalog_dir / "compiled-catalog.json"
            changed.write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(self.tool.IntegrationError, "refusing to overwrite"):
                self.tool.write_generated_assets(self.result, output_root)
            self.assertEqual(changed.read_text(encoding="utf-8"), "changed\n")

    def test_check_cli_path_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "must-remain-absent"
            stdout = io.StringIO()
            with (
                mock.patch.object(self.tool, "audit_archive", return_value=self.result),
                redirect_stdout(stdout),
            ):
                exit_code = self.tool.main(["--check", "--output-root", str(output_root)])
            self.assertEqual(exit_code, 0)
            response = json.loads(stdout.getvalue())
            self.assertEqual(response["mode"], "CHECK")
            self.assertEqual(response["generated_assets"]["status"], "ABSENT")
            self.assertFalse(output_root.exists())


if __name__ == "__main__":
    unittest.main()
