"""The implementation ledger must never hide missing code or promote declarations."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import unittest

from elmos_foundry.local_semantics import LOCAL_SEMANTIC_SKILLS, LocalSemanticRuntime
from elmos_foundry.readiness import (
    ReadinessValidationError,
    build_readiness,
    render_markdown,
)


CATALOG_PATH = Path(__file__).resolve().parents[1] / "catalog/compiled-catalog.json"


class FoundryReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(CATALOG_PATH.read_bytes())
        cls.report = build_readiness(cls.catalog)
        cls.rows = {row["name"]: row for row in cls.report["skills"]}
        view = SimpleNamespace(
            content_sha256="a" * 64,
            discovery=cls.catalog["discovery"],
            atomic_skills={row["name"]: row for row in cls.catalog["atomic_skills"]},
            meta_skills={row["name"]: row for row in cls.catalog["meta_skills"]},
        )
        cls.handlers = LocalSemanticRuntime(view).handlers

    def test_every_exact_identity_preserves_source_work(self) -> None:
        self.assertEqual(1310, len(self.report["skills"]))
        self.assertEqual(1310, len(self.rows))
        for source in self.catalog["atomic_skills"]:
            row = self.rows[source["name"]]
            for key in (
                "name", "pack", "version", "source_path", "source_sha256", "description",
                "workflow", "inputs", "outputs", "allowed_tools", "required_gates", "dependencies",
            ):
                self.assertEqual(source[key], row[key], (source["name"], key))

    def test_counts_follow_actual_handlers_without_whole_skill_promotion(self) -> None:
        summary = self.report["summary"]
        self.assertEqual(len(self.handlers), summary["local_semantic_handlers"])
        self.assertEqual(1310 - len(self.handlers), summary["prepare_only"])
        self.assertEqual(1310, summary["exact_adapter_bindings"])
        self.assertEqual(1310 - len(self.handlers), summary["host_route_bound"])
        self.assertEqual(0, summary["integration_unbound"])
        self.assertEqual(0, summary["whole_skills_complete"])
        self.assertEqual(9090, summary["dependency_edges"])
        self.assertEqual(31440, summary["source_acceptance_cases_required"])
        for name, row in self.rows.items():
            self.assertEqual(name not in self.handlers, row["code_missing"]["exact_semantic_handler"])
            self.assertEqual(
                "LOCAL_EXECUTABLE" if name in self.handlers else "HOST_ROUTE_BOUND",
                row["integration_binding"]["status"],
            )
            self.assertFalse(row["whole_skill_complete"])
            self.assertFalse(row["execution_authorized"])
            self.assertEqual("NOT_RUN", row["external_evidence_status"])
            self.assertEqual("NOT_CERTIFIED", row["certification_status"])
            self.assertEqual("NOT_RUN", row["verification_missing"]["independent_verification"])
            self.assertTrue(row["verification_missing"]["required_gates"])

    def test_local_code_does_not_erase_unbound_contracts_or_verification(self) -> None:
        local = self.rows["typed-skill-contract"]
        self.assertFalse(local["code_missing"]["exact_semantic_handler"])
        missing = local["code_missing"]["unbound_source_contract_fields"]
        self.assertIn("input_contracts[0].schema_binding", missing["input_contracts"])
        self.assertIn("tool_contract.parameter_schemas", missing["tool_contract"])
        self.assertTrue(all(
            gate["status"] == "NOT_RUN"
            for gate in local["verification_missing"]["required_gates"]
        ))
        self.assertEqual("NOT_EVALUATED_BY_THIS_INVENTORY", local["local_evidence_status"])

    def test_pack_totals_and_dependency_order_are_complete(self) -> None:
        source_packs = Counter(row["pack"] for row in self.catalog["atomic_skills"])
        self.assertEqual(41, len(self.report["packs"]))
        self.assertEqual(1310, sum(row["atomic_skills"] for row in self.report["packs"]))
        for pack in self.report["packs"]:
            self.assertEqual(source_packs[pack["pack"]], pack["atomic_skills"])
            self.assertEqual(pack["atomic_skills"], pack["local_semantic_handlers"] + pack["prepare_only"])
        order = {name: index for index, name in enumerate(self.report["implementation_order"])}
        self.assertEqual(set(self.rows), set(order))
        for name, row in self.rows.items():
            expected_missing = sorted(set(row["dependencies"]) - LOCAL_SEMANTIC_SKILLS)
            self.assertEqual(expected_missing, row["dependency_blockers"]["direct_missing_semantic_handlers"])
            for dependency in row["dependencies"]:
                self.assertLess(order[dependency], order[name])
                self.assertLess(self.rows[dependency]["dependency_stage"], row["dependency_stage"])
                for missing in self.rows[dependency]["dependency_blockers"]["transitive_missing_semantic_handlers"]:
                    self.assertIn(missing, row["dependency_blockers"]["transitive_missing_semantic_handlers"])

    def test_report_and_markdown_are_deterministic_and_keep_boundaries(self) -> None:
        again = build_readiness(self.catalog)
        self.assertEqual(self.report, again)
        text = render_markdown(again)
        self.assertEqual(render_markdown(self.report), text)
        self.assertIn("PREPARE_ONLY", text)
        self.assertIn("NOT_CERTIFIED", text)
        self.assertIn("code_missing", text)
        self.assertIn("integration_binding", text)
        self.assertIn("verification_missing", text)
        self.assertIn("requirements, not executed test cases", text)

    def test_missing_atomic_record_fails_closed(self) -> None:
        altered = deepcopy(self.catalog)
        altered["atomic_skills"].pop()
        with self.assertRaisesRegex(ReadinessValidationError, "exactly 1310"):
            build_readiness(altered)

    def test_duplicate_atomic_identity_fails_closed(self) -> None:
        altered = deepcopy(self.catalog)
        altered["atomic_skills"][-1] = altered["atomic_skills"][0]
        with self.assertRaisesRegex(ReadinessValidationError, "duplicate identity"):
            build_readiness(altered)

    def test_meta_cannot_hide_a_missing_identity(self) -> None:
        altered = deepcopy(self.catalog)
        altered["meta_skills"][0]["candidates"].pop()
        with self.assertRaisesRegex(ReadinessValidationError, "incomplete or foreign"):
            build_readiness(altered)

    def test_source_edges_cannot_be_removed(self) -> None:
        altered = deepcopy(self.catalog)
        next(row for row in altered["atomic_skills"] if row["dependencies"])["dependencies"].pop()
        with self.assertRaisesRegex(ReadinessValidationError, "exactly 9090"):
            build_readiness(altered)

    def test_duplicate_dependencies_cannot_inflate_coverage(self) -> None:
        altered = deepcopy(self.catalog)
        row = next(row for row in altered["atomic_skills"] if len(row["dependencies"]) > 1)
        row["dependencies"][0] = row["dependencies"][1]
        with self.assertRaisesRegex(ReadinessValidationError, "duplicate entries"):
            build_readiness(altered)

    def test_pipeline_runtime_claim_cannot_be_hidden_in_inventory(self) -> None:
        altered = deepcopy(self.catalog)
        altered["pipelines"][0]["execution_mode"] = "SUCCEEDED"
        with self.assertRaisesRegex(ReadinessValidationError, "cannot assert runtime execution"):
            build_readiness(altered)

    def test_unknown_dependencies_and_cycles_fail_closed(self) -> None:
        for new_dependency in ("unknown-skill", None):
            altered = deepcopy(self.catalog)
            row = next(row for row in altered["atomic_skills"] if row["dependencies"])
            row["dependencies"][0] = row["name"] if new_dependency is None else new_dependency
            with self.subTest(new_dependency=new_dependency):
                with self.assertRaisesRegex(ReadinessValidationError, "unknown dependency|cycle"):
                    build_readiness(altered)

    def test_missing_and_extra_observed_handlers_fail_closed(self) -> None:
        for extra in (False, True):
            handlers = dict(self.handlers)
            name = next(iter(handlers))
            if extra:
                handlers["pretend-implemented"] = handlers[name]
            else:
                del handlers[name]
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(ReadinessValidationError, "missing, extra, or stale"):
                    build_readiness(self.catalog, semantic_bindings=handlers)

    def test_swapped_observed_callable_fails_closed(self) -> None:
        handlers = dict(self.handlers)
        first, second = tuple(handlers)[:2]
        handlers[first] = handlers[second]
        with self.assertRaisesRegex(ReadinessValidationError, "callable identity"):
            build_readiness(self.catalog, semantic_bindings=handlers)

    def test_catalog_cannot_promote_prepare_only_or_hide_local_binding(self) -> None:
        for original, promoted in (("PREPARE_ONLY", "LOCAL"), ("LOCAL", "PREPARE_ONLY")):
            altered = deepcopy(self.catalog)
            row = next(row for row in altered["atomic_skills"] if row["capability_state"] == original)
            row["capability_state"] = promoted
            with self.subTest(original=original):
                with self.assertRaisesRegex(ReadinessValidationError, "capability state differs"):
                    build_readiness(altered)

    def test_wrong_adapter_binding_fails_closed(self) -> None:
        altered = deepcopy(self.catalog)
        row = next(row for row in altered["atomic_skills"] if row["capability_state"] == "LOCAL")
        row["semantic_handler_binding"] = "local.some-other-skill"
        with self.assertRaisesRegex(ReadinessValidationError, "semantic binding differs"):
            build_readiness(altered)

    def test_external_and_certification_claims_are_rejected(self) -> None:
        for field, value in (
            ("external_evidence_status", "PASS"),
            ("certification_status", "CERTIFIED"),
        ):
            altered = deepcopy(self.catalog)
            altered["atomic_skills"][0][field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ReadinessValidationError, "cannot assert"):
                    build_readiness(altered)

    def test_invalid_acceptance_denominator_fails_closed(self) -> None:
        altered: dict[str, Any] = deepcopy(self.catalog)
        altered["atomic_skills"][0]["activation_contract"]["positive_required"] = True
        with self.assertRaisesRegex(ReadinessValidationError, "invalid positive corpus"):
            build_readiness(altered)


if __name__ == "__main__":
    unittest.main()
