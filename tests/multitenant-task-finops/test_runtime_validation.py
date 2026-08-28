from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPOSITORY_ROOT / "tooling/validate_multitenant_task_finops_runtime.py"
SPEC = importlib.util.spec_from_file_location("mtf_runtime_validator", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

FIXTURE_FILES = (
    validator.TASK_CATALOG,
    validator.SOURCE_RISK_REGISTER,
    validator.COMPILED_MANIFEST,
    validator.SOURCE_MATRIX,
    validator.INSTALLED_MANIFEST,
    validator.TASK_RESULTS,
    validator.RECONCILIATION_REGISTER,
    validator.DEPENDENCY_BINDINGS,
    Path("tooling/validate_multitenant_task_finops_runtime.py"),
    Path("tests/multitenant-task-finops/test_runtime_validation.py"),
)


class RuntimeResultValidationTest(unittest.TestCase):
    def temporary_repository(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        for relative in FIXTURE_FILES:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPOSITORY_ROOT / relative, destination)
        return temporary, root

    @staticmethod
    def load(root: Path, relative: Path) -> dict[str, object]:
        return json.loads((root / relative).read_text(encoding="utf-8"))

    @staticmethod
    def write(root: Path, relative: Path, payload: dict[str, object]) -> None:
        (root / relative).write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_checked_in_layer_is_complete_and_fail_closed(self) -> None:
        result = validator.validate_repository(REPOSITORY_ROOT)

        self.assertEqual("PASS", result["status"], result["errors"])
        self.assertEqual(144, result["task_count"])
        self.assertEqual({"NOT_RUN": 144}, result["task_execution"])
        self.assertEqual({"NOT_EVALUATED": 11}, result["source_findings"])
        self.assertEqual({"UNRESOLVED": 4}, result["external_dependencies"])
        self.assertEqual("NOT_RUN", result["external_evidence_status"])
        self.assertEqual("NOT_CERTIFIED", result["production_certification"])

    def test_missing_task_fails_exact_completeness(self) -> None:
        temporary, root = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        results = self.load(root, validator.TASK_RESULTS)
        results["tasks"] = results["tasks"][:-1]
        self.write(root, validator.TASK_RESULTS, results)

        checked = validator.validate_repository(root)

        self.assertEqual("FAIL", checked["status"])
        self.assertTrue(
            any("task IDs must exactly match" in error for error in checked["errors"]),
            checked["errors"],
        )

    def test_forged_pass_without_receipt_fails_closed(self) -> None:
        temporary, root = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        results = self.load(root, validator.TASK_RESULTS)
        task = results["tasks"][0]
        task["implementation_state"] = "IMPLEMENTED"
        task["execution_state"] = "PASS"
        task["evidence_state"] = "LOCAL_SELF_ATTESTED"
        task["blockers"] = []
        task["implementation_bindings"] = []
        task["result_receipts"] = []
        self.write(root, validator.TASK_RESULTS, results)

        checked = validator.validate_repository(root)

        self.assertEqual("FAIL", checked["status"])
        self.assertTrue(
            any("requires a non-NONE evidence state and receipts" in error for error in checked["errors"]),
            checked["errors"],
        )

    def test_immutable_source_matrix_promotion_is_rejected(self) -> None:
        temporary, root = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        matrix = self.load(root, validator.SOURCE_MATRIX)
        matrix["tasks"][0]["status"] = "PASS"
        self.write(root, validator.SOURCE_MATRIX, matrix)

        checked = validator.validate_repository(root)

        self.assertEqual("FAIL", checked["status"])
        self.assertTrue(
            any("source matrix tasks must remain NOT_RUN" in error for error in checked["errors"]),
            checked["errors"],
        )

    def test_source_risk_cannot_be_mitigated_without_evidence(self) -> None:
        temporary, root = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        register = self.load(root, validator.RECONCILIATION_REGISTER)
        register["findings"][0]["repository_resolution_state"] = "MITIGATED_LOCAL"
        register["findings"][0]["blockers"] = []
        self.write(root, validator.RECONCILIATION_REGISTER, register)

        checked = validator.validate_repository(root)

        self.assertEqual("FAIL", checked["status"])
        self.assertTrue(
            any("MITIGATED_LOCAL requires bindings" in error for error in checked["errors"]),
            checked["errors"],
        )

    def test_dependency_cannot_be_resolved_without_exact_dual_root_skill_and_receipt(self) -> None:
        temporary, root = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        bindings = self.load(root, validator.DEPENDENCY_BINDINGS)
        bindings["dependencies"][0]["binding_state"] = "RESOLVED_LOCAL"
        bindings["dependencies"][0]["blockers"] = []
        self.write(root, validator.DEPENDENCY_BINDINGS, bindings)

        checked = validator.validate_repository(root)

        self.assertEqual("FAIL", checked["status"])
        self.assertTrue(
            any("requires both exact installed Skill interfaces" in error for error in checked["errors"]),
            checked["errors"],
        )


if __name__ == "__main__":
    unittest.main()
