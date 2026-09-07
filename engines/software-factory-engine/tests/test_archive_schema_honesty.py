from __future__ import annotations

import copy
import json
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    import jsonschema  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - dependency-free suite records the skip
    jsonschema = None


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = (
    ROOT / "engines" / "software-factory-engine" / "schemas" / "archive-contract-inspection.schema.json"
)
RECEIPT_PATH = (
    ROOT
    / "verification-packs"
    / "elmos-7plus1-local-contract-v1"
    / "certification"
    / "local-evidence"
    / "archive-contract-inspection.json"
)


@unittest.skipIf(jsonschema is None, "jsonschema is needed for schema honesty checks")
class ArchiveInspectionSchemaHonestyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(cls.schema)
        cls.validator = jsonschema.Draft202012Validator(cls.schema)

    def assert_rejected(self, mutate: Callable[[dict[str, Any]], None]) -> None:
        forged = copy.deepcopy(self.receipt)
        mutate(forged)
        with self.assertRaises(jsonschema.ValidationError):
            self.validator.validate(forged)

    def test_current_emitted_receipt_is_accepted(self) -> None:
        self.validator.validate(self.receipt)

    def test_external_state_promotions_and_extra_fields_are_rejected(self) -> None:
        promotions = {
            "independent_holdout": "PASSED",
            "provider_execution": "PASSED",
            "production_execution": "PASSED",
            "independent_verification": "PASSED",
            "certification": "CERTIFIED",
        }
        for field, promoted in promotions.items():
            with self.subTest(field=field):
                self.assert_rejected(
                    lambda receipt, field=field, promoted=promoted: receipt["external_states"].__setitem__(
                        field, promoted
                    )
                )
        self.assert_rejected(lambda receipt: receipt["external_states"].__setitem__("review", "PASSED"))

    def test_archive_script_execution_or_identity_forgery_is_rejected(self) -> None:
        mutations: tuple[Callable[[dict[str, Any]], None], ...] = (
            lambda receipt: receipt["archive_scripts"][0].__setitem__("execution_state", "EXECUTED"),
            lambda receipt: receipt["archive_scripts"][0].__setitem__(
                "implementation_state", "ARCHIVE_SCRIPT_EXECUTED"
            ),
            lambda receipt: receipt["archive_scripts"][0].__setitem__("materialized_mode", "0755"),
            lambda receipt: receipt["archive_scripts"][1].__setitem__("logical_path", "scripts/unknown.py"),
            lambda receipt: receipt["archive_scripts"][1].__setitem__("executed_at", "now"),
            lambda receipt: receipt.__setitem__(
                "archive_scripts", list(reversed(receipt["archive_scripts"]))
            ),
            lambda receipt: receipt.__setitem__("archive_scripts_executed", True),
            lambda receipt: receipt.__setitem__("active_archive_executables", ["scripts/score_readiness.py"]),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                self.assert_rejected(mutate)

    def test_readiness_claims_are_exact_and_cannot_be_promoted(self) -> None:
        self.assert_rejected(lambda receipt: receipt["readiness_checks"][8].__setitem__("status", "PASSED"))
        self.assert_rejected(lambda receipt: receipt["readiness_checks"][8].__setitem__("weight", 0))
        self.assert_rejected(lambda receipt: receipt["readiness_checks"][0].__setitem__("claim", "certified"))
        self.assert_rejected(lambda receipt: receipt.__setitem__("source_blueprint_presence_score", 100))
        self.assert_rejected(
            lambda receipt: receipt.__setitem__(
                "readiness_checks", list(reversed(receipt["readiness_checks"]))
            )
        )

    def test_safe_validation_counts_errors_and_shape_are_exact(self) -> None:
        self.assert_rejected(
            lambda receipt: receipt["safe_validation"].__setitem__("package_validation_count", 9)
        )
        self.assert_rejected(lambda receipt: receipt["safe_validation"].__setitem__("errors", ["suppressed"]))
        self.assert_rejected(lambda receipt: receipt["safe_validation"].__setitem__("certified", True))
        self.assert_rejected(lambda receipt: receipt.__setitem__("unexpected", "field"))


if __name__ == "__main__":
    unittest.main()
