"""Independent local reconciliation cases; native qualification remains NOT_RUN."""

from __future__ import annotations

from collections.abc import Mapping
import copy
from pathlib import Path
import tempfile
from typing import Any
import unittest

from elmos_foundry.canonical import canonical_digest, digest_bytes
from elmos_foundry.domain import TenantScope
from elmos_foundry.ir_reconciliation_semantics import SKILLS, build_ir_reconciliation_handlers


NAME = "semantic-ir-reconciliation"
PATH = "src/calc.py"


def _fact(
    kind: str,
    subject: str,
    value: Mapping[str, Any],
    *,
    file: str = PATH,
    source: str = "def add(value):\n    return value + 1\n",
) -> dict[str, Any]:
    return {
        "file": file,
        "kind": kind,
        "subject": subject,
        "value": dict(value),
        "status": "OBSERVED",
        "confidence": 0.95,
        "origin": {
            "content_digest": digest_bytes(source.encode()),
            "start_line": 1,
            "start_column": 1,
            "end_line": 1,
            "end_column": len(source.splitlines()[0]) + 1,
        },
    }


def _fact_id(fact: Mapping[str, Any]) -> str:
    return canonical_digest({key: fact[key] for key in ("file", "kind", "subject")})


def _bind(values: dict[str, Any]) -> None:
    digest = canonical_digest(values["normalized repository artifact"])
    for key in ("build metadata", "runtime trace", "test result"):
        values[key]["repository_digest"] = digest


def fixture_inputs(skill_name: str, scope: TenantScope) -> dict[str, Any]:
    if skill_name != NAME:
        raise ValueError("unknown IR reconciliation fixture")
    source = "def add(value):\n    return value + 1\n"
    facts = [
        _fact("symbol", "calc.add", {"qualified_name": "calc.add", "symbol_kind": "function"}),
        _fact(
            "type",
            "calc.add",
            {
                "kind": "integer",
                "bits": "unbounded",
                "signed": True,
                "overflow": "unbounded",
                "nullable": False,
            },
        ),
        _fact("control-node", "calc.add/entry", {"function": "calc.add", "node_kind": "entry"}),
        _fact("control-node", "calc.add/return", {"function": "calc.add", "node_kind": "return"}),
        _fact(
            "control-edge",
            "calc.add/edge",
            {
                "function": "calc.add",
                "from": "calc.add/entry",
                "to": "calc.add/return",
                "edge_kind": "next",
            },
        ),
    ]
    parsers = []
    for index in range(2):
        observations = copy.deepcopy(facts)
        for fact in observations:
            fact["confidence"] = 0.95 - 0.05 * index
        parsers.append(
            {
                "parser_id": f"parser-{index}",
                "version": "1.2.3",
                "implementation_digest": "sha256:" + str(index) * 64,
                "covered_files": [PATH],
                "coverage_status": "COMPLETE",
                "facts": observations,
            }
        )
    values: dict[str, Any] = {
        "normalized repository artifact": {
            "schema_version": "elmos.foundry.reconciliation-input.v1",
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "repository_id": "repository-one",
            "workspace_digest": scope.workspace_digest,
            "revision_set_id": scope.revision_set_id,
            "files": [
                {
                    "path": PATH,
                    "language": "python",
                    "source": source,
                    "content_digest": digest_bytes(source.encode()),
                }
            ],
        },
        "build metadata": {"repository_digest": "", "minimum_confidence": 0.8, "parsers": parsers},
        "runtime trace": {"repository_digest": "", "status": "NOT_RUN", "records": []},
        "test result": {"repository_digest": "", "status": "NOT_RUN", "records": []},
    }
    _bind(values)
    return values


class _Catalog:
    atomic_skills: Mapping[str, Mapping[str, Any]] = {NAME: {}}
    meta_skills: Mapping[str, Mapping[str, Any]] = {}
    discovery: Mapping[str, Any] = {}
    content_sha256 = "sha256:" + "0" * 64


class IRReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scope = TenantScope(
            "tenant-ir",
            "project-ir",
            workspace_digest="sha256:" + "a" * 64,
            revision_set_id="sha256:" + "b" * 64,
        )
        self.handler = build_ir_reconciliation_handlers(_Catalog(), None)[NAME]

    def execute(self, values: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        response = self.handler(
            NAME,
            {"inputs": fixture_inputs(NAME, self.scope) if values is None else values},
            self.scope,
            "invocation-ir",
        )
        self.assertEqual(response["status"], "SUCCEEDED")
        self.assertEqual(response["external_evidence_status"], "NOT_RUN")
        self.assertEqual(response["certification_status"], "NOT_CERTIFIED")
        outputs: Mapping[str, Any] = response["outputs"]
        self.assertEqual(
            set(outputs),
            {"semantic graph", "architecture model", "semantic diff", "confidence report"},
        )
        self.assertFalse(outputs["confidence report"]["language_equivalence_proven"])
        self.assertFalse(outputs["confidence report"]["effects_authorized"])
        rows = outputs["semantic graph"]["facts"]
        resolved = [row for row in rows if row["state"] == "RESOLVED_LOCAL"]
        unresolved = [row for row in rows if row["state"] == "UNRESOLVED"]
        report = outputs["confidence report"]
        self.assertEqual(report["resolved_fact_count"], len(resolved))
        self.assertEqual(report["unresolved_fact_count"], len(unresolved))
        self.assertEqual(report["distinct_fact_count"], len(resolved) + len(unresolved))
        self.assertEqual(
            {row["fact_id"] for row in unresolved},
            {row["fact_id"] for row in outputs["semantic diff"]["fact_differences"]},
        )
        for module in outputs["architecture model"]["modules"]:
            for kind in ("symbol", "type"):
                self.assertEqual(
                    module[f"resolved_{kind}_count"],
                    sum(row["file"] == module["path"] and row["kind"] == kind for row in resolved),
                )
        self.assertEqual(
            {row["fact_id"] for row in resolved if row["kind"] == "call"},
            {row["fact_id"] for row in outputs["architecture model"]["calls"]},
        )
        return outputs

    def test_consensus_has_calculated_counts_and_conservative_confidence(self) -> None:
        self.assertEqual(SKILLS, {NAME})
        outputs = self.execute()
        report = outputs["confidence report"]
        self.assertEqual(
            (
                report["input_fact_count"],
                report["distinct_fact_count"],
                report["resolved_fact_count"],
            ),
            (10, 5, 5),
        )
        self.assertEqual(report["reconciliation_status"], "RECONCILED_LOCAL")
        self.assertEqual(report["observed_parse_coverage"], "NOT_RUN")
        for fact in outputs["semantic graph"]["facts"]:
            self.assertAlmostEqual(fact["declared_confidence_floor"], 0.90)
            self.assertEqual(fact["variants"][0]["parser_ids"], ["parser-0", "parser-1"])

    def test_parser_and_fact_reordering_preserves_results(self) -> None:
        before = self.execute()
        values = fixture_inputs(NAME, self.scope)
        values["build metadata"]["parsers"].reverse()
        for parser in values["build metadata"]["parsers"]:
            parser["facts"].reverse()
        after = self.execute(values)
        for output in ("semantic graph", "architecture model", "semantic diff"):
            self.assertEqual(before[output], after[output])
        # Preserve semantic ordering while binding the exact raw input sequence.
        self.assertNotEqual(
            before["confidence report"]["input_digest"], after["confidence report"]["input_digest"]
        )
        for key in set(before["confidence report"]) - {"input_digest", "content_digest"}:
            self.assertEqual(before["confidence report"][key], after["confidence report"][key])

    def test_integer_width_overflow_and_nullability_are_not_erased(self) -> None:
        values = fixture_inputs(NAME, self.scope)
        declared = {
            "kind": "integer",
            "bits": 32,
            "signed": True,
            "overflow": "wrap",
            "nullable": True,
        }
        for parser in values["build metadata"]["parsers"]:
            parser["facts"][1]["value"] = declared
        fact = next(
            fact
            for fact in self.execute(values)["semantic graph"]["facts"]
            if fact["kind"] == "type"
        )
        self.assertEqual(fact["variants"][0]["value"], declared)

    def test_multiple_languages_keep_distinct_nominal_types_and_modules(self) -> None:
        values = fixture_inputs(NAME, self.scope)
        source = "class Main {}\n"
        path = "src/Main.java"
        values["normalized repository artifact"]["files"].append(
            {
                "path": path,
                "language": "java",
                "source": source,
                "content_digest": digest_bytes(source.encode()),
            }
        )
        for parser in values["build metadata"]["parsers"]:
            parser["covered_files"].append(path)
            parser["facts"] += [
                _fact(
                    "symbol",
                    "Main",
                    {"qualified_name": "Main", "symbol_kind": "class"},
                    file=path,
                    source=source,
                ),
                _fact(
                    "type",
                    "Main",
                    {"kind": "nominal", "language": "java", "name": "Main", "nullable": True},
                    file=path,
                    source=source,
                ),
            ]
        _bind(values)
        outputs = self.execute(values)
        self.assertEqual(
            {module["language"] for module in outputs["architecture model"]["modules"]},
            {"python", "java"},
        )
        self.assertEqual(outputs["confidence report"]["resolved_fact_count"], 7)

    def test_recursive_call_graph_preserves_call_edges(self) -> None:
        values = fixture_inputs(NAME, self.scope)
        for parser in values["build metadata"]["parsers"]:
            parser["facts"].append(
                _fact(
                    "call",
                    "calc.add/call-1",
                    {"caller": "calc.add", "callee_file": PATH, "callee": "calc.add"},
                )
            )
        outputs = self.execute(values)
        self.assertEqual(outputs["architecture model"]["calls"][0]["callee"], "calc.add")
        self.assertEqual(outputs["confidence report"]["reconciliation_status"], "RECONCILED_LOCAL")

    def test_valid_branch_edges_reconcile_without_language_execution(self) -> None:
        values = fixture_inputs(NAME, self.scope)
        for parser in values["build metadata"]["parsers"]:
            facts = parser["facts"]
            facts[-1]["value"]["to"] = "branch"
            facts += [
                _fact("control-node", "branch", {"function": "calc.add", "node_kind": "branch"}),
                _fact(
                    "control-node", "other-return", {"function": "calc.add", "node_kind": "return"}
                ),
                _fact(
                    "control-edge",
                    "true-edge",
                    {
                        "function": "calc.add",
                        "from": "branch",
                        "to": "calc.add/return",
                        "edge_kind": "true",
                    },
                ),
                _fact(
                    "control-edge",
                    "false-edge",
                    {
                        "function": "calc.add",
                        "from": "branch",
                        "to": "other-return",
                        "edge_kind": "false",
                    },
                ),
            ]
        self.assertEqual(
            self.execute(values)["confidence report"]["reconciliation_status"], "RECONCILED_LOCAL"
        )

    def test_trace_matches_declared_fact_but_does_not_verify_it_independently(self) -> None:
        values = fixture_inputs(NAME, self.scope)
        fact = values["build metadata"]["parsers"][0]["facts"][1]
        artifact = {"observed_value": fact["value"], "occurrences": 3}
        values["runtime trace"].update(
            status="COLLECTED_SELF_ATTESTED",
            records=[
                {
                    "record_id": "trace-one",
                    "fact_id": _fact_id(fact),
                    "artifact": artifact,
                    "artifact_digest": canonical_digest(artifact),
                }
            ],
        )
        outputs = self.execute(values)
        self.assertEqual(
            outputs["semantic diff"]["trace_reconciliation"][0]["disposition"],
            "MATCHES_DECLARED_VARIANT",
        )
        self.assertEqual(outputs["confidence report"]["independent_verification"], "NOT_RUN")

    def test_test_artifact_accepts_repeated_argv_without_execution(self) -> None:
        values = fixture_inputs(NAME, self.scope)
        fact = values["build metadata"]["parsers"][0]["facts"][0]
        artifact = {
            "command": ["pytest", "-p", "no:cacheprovider", "-p", "no:warnings"],
            "outcome": "PASS",
            "exit_code": 0,
        }
        values["test result"].update(
            status="COLLECTED_SELF_ATTESTED",
            records=[
                {
                    "record_id": "check-one",
                    "fact_id": _fact_id(fact),
                    "artifact": artifact,
                    "artifact_digest": canonical_digest(artifact),
                }
            ],
        )
        self.assertEqual(
            self.execute(values)["semantic diff"]["test_reconciliation"][0]["disposition"], "PASS"
        )

    def test_source_digest_mismatch_rejects_tampered_bytes(self) -> None:
        values = fixture_inputs(NAME, self.scope)
        values["normalized repository artifact"]["files"][0]["source"] += "# altered\n"
        _bind(values)
        with self.assertRaisesRegex(ValueError, "source digest"):
            self.execute(values)

    def test_all_scope_bindings_are_checked(self) -> None:
        for field in ("tenant_id", "project_id", "workspace_digest", "revision_set_id"):
            values = fixture_inputs(NAME, self.scope)
            values["normalized repository artifact"][field] = "foreign"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "authenticated"):
                self.execute(values)

    def test_unsafe_and_ambiguous_source_paths_are_rejected(self) -> None:
        for path in (
            "../secret.py",
            "/tmp/source.py",
            "src//calc.py",
            "src/./calc.py",
            "src\\calc.py",
            ".",
            "src/\ncalc.py",
            "src/\tcalc.py",
        ):
            values = fixture_inputs(NAME, self.scope)
            values["normalized repository artifact"]["files"][0]["path"] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.execute(values)

    def test_origin_digest_and_span_are_exact(self) -> None:
        for field, value in (
            ("content_digest", "sha256:" + "f" * 64),
            ("start_line", 3),
            ("start_column", True),
            ("end_column", 999),
            ("end_column", 1),
            ("end_line", 0),
        ):
            values = fixture_inputs(NAME, self.scope)
            values["build metadata"]["parsers"][0]["facts"][0]["origin"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.execute(values)

    def test_source_range_disagreement_invalidates_an_otherwise_identical_type(self) -> None:
        values = fixture_inputs(NAME, self.scope)
        fact = values["build metadata"]["parsers"][1]["facts"][1]
        fact["origin"].update(start_line=2, start_column=1, end_line=2, end_column=5)
        outputs = self.execute(values)
        report = outputs["confidence report"]
        self.assertEqual((report["resolved_fact_count"], report["unresolved_fact_count"]), (4, 1))
        row = next(row for row in outputs["semantic graph"]["facts"] if row["kind"] == "type")
        self.assertEqual(row["state"], "UNRESOLVED")
        self.assertEqual(len(row["variants"]), 1)
        self.assertEqual(len(row["variants"][0]["origins"]), 2)
        self.assertEqual(
            outputs["semantic diff"]["fact_differences"][0]["reason_codes"],
            ["SOURCE_ORIGIN_MISMATCH"],
        )
        self.assertEqual(outputs["architecture model"]["modules"][0]["resolved_type_count"], 0)

    def test_unresolved_function_invalidates_dependent_type_cfg_and_calls(self) -> None:
        values = fixture_inputs(NAME, self.scope)
        for parser in values["build metadata"]["parsers"]:
            parser["facts"].append(
                _fact(
                    "call",
                    "recursive",
                    {"caller": "calc.add", "callee_file": PATH, "callee": "calc.add"},
                )
            )
        fact = values["build metadata"]["parsers"][1]["facts"][0]
        fact["origin"].update(start_line=2, start_column=1, end_line=2, end_column=5)
        outputs = self.execute(values)
        report = outputs["confidence report"]
        self.assertEqual((report["resolved_fact_count"], report["unresolved_fact_count"]), (0, 6))
        codes = {issue["code"] for issue in outputs["semantic diff"]["consistency_issues"]}
        self.assertTrue(
            {
                "TYPE_WITHOUT_RESOLVED_SYMBOL",
                "CFG_WITHOUT_RESOLVED_FUNCTION",
                "DANGLING_CONTROL_EDGE",
                "UNRESOLVED_CALL_TARGET",
            }
            <= codes
        )
        self.assertEqual(outputs["architecture model"]["calls"], [])

    def test_handler_rejects_a_different_exact_skill_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported exact"):
            self.handler(
                "build-and-dependency-graph",
                {"inputs": fixture_inputs(NAME, self.scope)},
                self.scope,
                "wrong-skill",
            )

    def test_unpinned_or_duplicate_parsers_cannot_fake_corroboration(self) -> None:
        for version in (
            "latest",
            "LATEST",
            "3.x",
            "unknown",
            "main",
            "master",
            "stable",
            "head",
            "release",
        ):
            values = fixture_inputs(NAME, self.scope)
            values["build metadata"]["parsers"][0]["version"] = version
            with self.subTest(version=version), self.assertRaises(ValueError):
                self.execute(values)
        values = fixture_inputs(NAME, self.scope)
        values["build metadata"]["parsers"][1]["parser_id"] = "parser-0"
        with self.assertRaisesRegex(ValueError, "duplicate parser"):
            self.execute(values)

    def test_duplicate_fact_and_unknown_kind_reject_ambiguous_shapes(self) -> None:
        values = fixture_inputs(NAME, self.scope)
        facts = values["build metadata"]["parsers"][0]["facts"]
        facts.append(copy.deepcopy(facts[0]))
        with self.assertRaisesRegex(ValueError, "two facts"):
            self.execute(values)
        facts.pop()
        facts[0]["kind"] = "generic-dictionary"
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.execute(values)

    def test_malformed_type_algebra_is_rejected(self) -> None:
        for field, value in (
            ("bits", 0),
            ("bits", True),
            ("bits", 7),
            ("nullable", 1),
            ("signed", "yes"),
            ("overflow", "ignore"),
        ):
            values = fixture_inputs(NAME, self.scope)
            values["build metadata"]["parsers"][0]["facts"][1]["value"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.execute(values)

    def test_nonfinite_confidence_and_missing_outer_inputs_reject(self) -> None:
        for score in (float("nan"), float("inf"), True, -0.1, 1.1):
            values = fixture_inputs(NAME, self.scope)
            values["build metadata"]["parsers"][0]["facts"][0]["confidence"] = score
            with self.subTest(score=score), self.assertRaises(ValueError):
                self.execute(values)
        for key in fixture_inputs(NAME, self.scope):
            values = fixture_inputs(NAME, self.scope)
            values[key] = {}
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.execute(values)

    def test_conflicting_types_are_preserved_without_selecting_a_winner(self) -> None:
        values = fixture_inputs(NAME, self.scope)
        values["build metadata"]["parsers"][1]["facts"][1]["value"] = {
            "kind": "integer",
            "bits": 32,
            "signed": True,
            "overflow": "wrap",
            "nullable": False,
        }
        outputs = self.execute(values)
        report = outputs["confidence report"]
        self.assertEqual(
            (report["reconciliation_status"], report["unresolved_fact_count"]), ("PARTIAL", 1)
        )
        fact = next(f for f in outputs["semantic graph"]["facts"] if f["kind"] == "type")
        self.assertEqual(fact["state"], "UNRESOLVED")
        self.assertEqual(len(fact["variants"]), 2)

    def test_missing_parser_fact_is_not_silently_dropped(self) -> None:
        values = fixture_inputs(NAME, self.scope)
        values["build metadata"]["parsers"][1]["facts"].pop(1)
        diff = self.execute(values)["semantic diff"]["fact_differences"]
        self.assertEqual(diff[0]["missing_parsers"], ["parser-1"])
        self.assertIn("MISSING_PARSER_FACT", diff[0]["reason_codes"])

    def test_unknown_and_unsupported_facts_stay_explicit(self) -> None:
        for status in ("UNKNOWN", "UNSUPPORTED"):
            values = fixture_inputs(NAME, self.scope)
            for parser in values["build metadata"]["parsers"]:
                parser["facts"][1].update(
                    status=status, value={"reason": "dynamic type not resolved"}
                )
            outputs = self.execute(values)
            self.assertEqual(outputs["confidence report"]["unresolved_fact_count"], 1)
            fact = next(f for f in outputs["semantic graph"]["facts"] if f["kind"] == "type")
            self.assertEqual(fact["variants"][0]["status"], status)

    def test_partial_parser_coverage_and_low_confidence_are_not_success(self) -> None:
        for defect in ("coverage", "confidence", "no-facts"):
            values = fixture_inputs(NAME, self.scope)
            parser = values["build metadata"]["parsers"][1]
            if defect == "coverage":
                parser["coverage_status"] = "PARTIAL"
            elif defect == "confidence":
                parser["facts"][0]["confidence"] = 0.1
            else:
                parser["facts"] = []
            with self.subTest(defect=defect):
                self.assertEqual(
                    self.execute(values)["confidence report"]["reconciliation_status"], "PARTIAL"
                )

    def test_caller_trace_cannot_override_a_parser_conflict(self) -> None:
        values = fixture_inputs(NAME, self.scope)
        fact = values["build metadata"]["parsers"][0]["facts"][1]
        values["build metadata"]["parsers"][1]["facts"][1]["value"] = {
            "kind": "string",
            "encoding": "unicode-codepoints",
            "nullable": False,
        }
        artifact = {"observed_value": fact["value"], "occurrences": 10000}
        values["runtime trace"].update(
            status="COLLECTED_SELF_ATTESTED",
            records=[
                {
                    "record_id": "trace-one",
                    "fact_id": _fact_id(fact),
                    "artifact": artifact,
                    "artifact_digest": canonical_digest(artifact),
                }
            ],
        )
        self.assertEqual(self.execute(values)["confidence report"]["unresolved_fact_count"], 1)

    def test_trace_contradiction_invalidates_only_the_affected_type(self) -> None:
        values = fixture_inputs(NAME, self.scope)
        fact = values["build metadata"]["parsers"][0]["facts"][1]
        artifact = {"observed_value": {**fact["value"], "nullable": True}, "occurrences": 1}
        values["runtime trace"].update(
            status="COLLECTED_SELF_ATTESTED",
            records=[
                {
                    "record_id": "contradiction",
                    "fact_id": _fact_id(fact),
                    "artifact": artifact,
                    "artifact_digest": canonical_digest(artifact),
                }
            ],
        )
        outputs = self.execute(values)
        report = outputs["confidence report"]
        self.assertEqual((report["resolved_fact_count"], report["unresolved_fact_count"]), (4, 1))
        self.assertEqual(
            outputs["semantic diff"]["fact_differences"][0]["reason_codes"],
            ["TRACE_CONTRADICTS_ALL_PARSER_FACTS"],
        )
        module = outputs["architecture model"]["modules"][0]
        self.assertEqual((module["resolved_symbol_count"], module["resolved_type_count"]), (1, 0))

    def test_forged_evidence_digest_and_dangling_references_are_rejected(self) -> None:
        for defect in ("digest", "reference"):
            values = fixture_inputs(NAME, self.scope)
            fact = values["build metadata"]["parsers"][0]["facts"][0]
            artifact = {"observed_value": fact["value"], "occurrences": 1}
            record = {
                "record_id": "trace-one",
                "fact_id": _fact_id(fact),
                "artifact": artifact,
                "artifact_digest": canonical_digest(artifact),
            }
            record["artifact_digest" if defect == "digest" else "fact_id"] = "sha256:" + "f" * 64
            values["runtime trace"].update(status="COLLECTED_SELF_ATTESTED", records=[record])
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                self.execute(values)

    def test_evidence_cannot_assert_independent_status_or_pass_a_failed_command(self) -> None:
        values = fixture_inputs(NAME, self.scope)
        values["runtime trace"]["status"] = "VERIFIED_INDEPENDENT"
        with self.assertRaises(ValueError):
            self.execute(values)
        values = fixture_inputs(NAME, self.scope)
        fact = values["build metadata"]["parsers"][0]["facts"][0]
        artifact = {"command": ["python", "-V"], "outcome": "PASS", "exit_code": 1}
        values["test result"].update(
            status="COLLECTED_SELF_ATTESTED",
            records=[
                {
                    "record_id": "test-one",
                    "fact_id": _fact_id(fact),
                    "artifact": artifact,
                    "artifact_digest": canonical_digest(artifact),
                }
            ],
        )
        with self.assertRaisesRegex(ValueError, "exit code"):
            self.execute(values)

    def test_repository_instructions_and_replay_commands_are_never_executed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "must-not-exist"
            values = fixture_inputs(NAME, self.scope)
            source = f"open({str(marker)!r}, 'w').write('unexpected')\n"
            file = values["normalized repository artifact"]["files"][0]
            file.update(source=source, content_digest=digest_bytes(source.encode()))
            for parser in values["build metadata"]["parsers"]:
                for fact in parser["facts"]:
                    fact["origin"]["content_digest"] = file["content_digest"]
            _bind(values)
            self.execute(values)
            self.assertFalse(marker.exists())

    def test_dangling_and_incomplete_control_flow_are_reported(self) -> None:
        for defect, code, expected_counts in (
            ("dangling", "DANGLING_CONTROL_EDGE", (2, 3)),
            ("branch", "BRANCH_REQUIRES_TRUE_AND_FALSE", (2, 3)),
            ("unreachable", "UNREACHABLE_CONTROL_NODE", (5, 1)),
            ("no-entry", "CFG_REQUIRES_ONE_ENTRY", (2, 3)),
            ("two-entries", "CFG_REQUIRES_ONE_ENTRY", (2, 3)),
        ):
            values = fixture_inputs(NAME, self.scope)
            for parser in values["build metadata"]["parsers"]:
                if defect == "dangling":
                    parser["facts"][-1]["value"]["to"] = "absent"
                elif defect == "branch":
                    parser["facts"][3]["value"]["node_kind"] = "branch"
                elif defect == "no-entry":
                    parser["facts"][2]["value"]["node_kind"] = "statement"
                elif defect == "two-entries":
                    parser["facts"][3]["value"]["node_kind"] = "entry"
                else:
                    parser["facts"].append(
                        _fact(
                            "control-node", "dead", {"function": "calc.add", "node_kind": "return"}
                        )
                    )
            with self.subTest(defect=defect):
                outputs = self.execute(values)
                self.assertIn(
                    code,
                    {issue["code"] for issue in outputs["semantic diff"]["consistency_issues"]},
                )
                self.assertEqual(outputs["confidence report"]["reconciliation_status"], "PARTIAL")
                report = outputs["confidence report"]
                self.assertEqual(
                    (report["resolved_fact_count"], report["unresolved_fact_count"]),
                    expected_counts,
                )

    def test_fail_and_missing_test_results_remain_nonpassing(self) -> None:
        for outcome, exit_code, code in (
            ("FAIL", 1, "TEST_FAILED"),
            ("NOT_RUN", None, "TEST_NOT_RUN"),
        ):
            values = fixture_inputs(NAME, self.scope)
            fact = values["build metadata"]["parsers"][0]["facts"][0]
            artifact = {"command": ["pytest"], "outcome": outcome, "exit_code": exit_code}
            values["test result"].update(
                status="COLLECTED_SELF_ATTESTED",
                records=[
                    {
                        "record_id": "test-one",
                        "fact_id": _fact_id(fact),
                        "artifact": artifact,
                        "artifact_digest": canonical_digest(artifact),
                    }
                ],
            )
            outputs = self.execute(values)
            self.assertIn(
                code,
                {issue["code"] for issue in outputs["semantic diff"]["consistency_issues"]},
            )
            report = outputs["confidence report"]
            self.assertEqual(
                (report["resolved_fact_count"], report["unresolved_fact_count"]), (0, 5)
            )


if __name__ == "__main__":
    unittest.main()
