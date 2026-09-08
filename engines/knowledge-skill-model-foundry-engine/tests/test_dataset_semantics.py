"""Calculated local Dataset Foundry cases, including malformed and leakage cases."""

from __future__ import annotations

from collections.abc import Mapping
import copy
from datetime import datetime
from pathlib import Path
import tempfile
from typing import Any
import unittest

from elmos_foundry.canonical import canonical_digest
from elmos_foundry.dataset_semantics import DATASET_SEMANTIC_SKILLS, build_dataset_handlers
from elmos_foundry.domain import TenantScope


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def fixture_inputs(skill_name: str, scope: TenantScope) -> dict[str, Any]:
    """Exact pack inputs reusable by the public service acceptance suite."""
    bound = {"tenant_id": scope.tenant_id, "project_id": scope.project_id}
    result: dict[str, Any] = {
        "experience episode": {},
        "knowledge object": {},
        "human feedback": {},
        "verification evidence": {},
    }
    if skill_name == "repo-org-time-split-builder":
        samples = []
        for i, date in enumerate(("2026-01-01", "2026-02-01", "2026-03-01")):
            samples.append(
                {
                    **bound,
                    "sample_id": f"sample-{i}",
                    "repository_id": f"repo-{i}",
                    "organization_id": f"org-{i}",
                    "fork_family_id": f"fork-{i}",
                    "task_family_id": f"family-{i}",
                    "observed_at": date + "T00:00:00Z",
                    "content_digest": _digest(str(i)),
                }
            )
        result["experience episode"] = {"samples": samples}
        result["knowledge object"] = {
            "train_before": "2026-02-01T00:00:00Z",
            "validation_before": "2026-03-01T00:00:00Z",
        }
    elif skill_name in {"dataset-lineage-and-provenance", "dataset-revocation-unlearning-index"}:
        names = [
            "source-a",
            "source-b",
            "sample-a",
            "sample-b",
            "dataset-a",
            "checkpoint-a",
            "adapter-a",
        ]
        kinds = ["object", "object", "sample", "sample", "dataset", "checkpoint", "adapter"]
        nodes = [
            {
                **bound,
                "node_id": name,
                "kind": kind,
                "version": "1.0.0",
                "content_digest": _digest(str(index)),
            }
            for index, (name, kind) in enumerate(zip(names, kinds, strict=True))
        ]
        edge_specs = [
            ("source-a", "sample-a", "derived-from"),
            ("source-b", "sample-b", "derived-from"),
            ("sample-a", "dataset-a", "member-of"),
            ("sample-b", "dataset-a", "member-of"),
            ("dataset-a", "checkpoint-a", "trained-into"),
            ("checkpoint-a", "adapter-a", "adapted-into"),
        ]
        result["experience episode"] = {
            "nodes": nodes,
            "edges": [
                {"parent": parent, "child": child, "relation": relation}
                for parent, child, relation in edge_specs
            ],
        }
        if skill_name == "dataset-revocation-unlearning-index":
            result["knowledge object"] = {"revoked_ids": ["source-a"]}
    elif skill_name == "preference-pair-builder":
        candidates = [
            {
                **bound,
                "candidate_id": name,
                "task_id": "task-one",
                "prompt_digest": _digest("c"),
                "content_digest": _digest(digest),
            }
            for name, digest in (("fixed", "a"), ("broken", "b"))
        ]
        checks = [
            {
                "candidate_id": candidate["candidate_id"],
                "content_digest": candidate["content_digest"],
                "checks": [{"check_id": "arithmetic", "status": "PASS" if index == 0 else "FAIL"}],
            }
            for index, candidate in enumerate(candidates)
        ]
        result["experience episode"] = {"candidates": candidates}
        result["verification evidence"] = {"results": checks}
        result["human feedback"] = {
            "decisions": [
                {
                    "decision_id": "decision-one",
                    "actor_id": "reviewer-one",
                    "task_id": "task-one",
                    "chosen_id": "fixed",
                    "rejected_id": "broken",
                    "reason": "repair-over-failed",
                    "chosen_evidence_digest": canonical_digest(checks[0]),
                    "rejected_evidence_digest": canonical_digest(checks[1]),
                }
            ]
        }
    elif skill_name == "active-learning-sample-selection":
        result["knowledge object"] = {
            "weights": {
                "uncertainty": 0.4,
                "business_value": 0.3,
                "failure_frequency": 0.2,
                "information_gain": 0.1,
            },
            "budget_units": 5,
            "limit": 3,
        }
        metrics = [
            ("expensive", [1, 1, 1, 1], 7),
            ("valuable", [0.5, 1, 0.5, 1], 4),
            ("uncertain", [1, 0, 0, 0], 1),
            ("routine", [0.1, 0.1, 0.1, 0.1], 1),
        ]
        metric_names = ["uncertainty", "business_value", "failure_frequency", "information_gain"]
        result["experience episode"] = {
            "samples": [
                {
                    **bound,
                    "sample_id": name,
                    "content_digest": _digest(str(index)),
                    "cost_units": cost,
                    "metrics": dict(zip(metric_names, values, strict=True)),
                }
                for index, (name, values, cost) in enumerate(metrics)
            ]
        }
    elif skill_name == "semantic-and-ast-deduplication":
        result["experience episode"] = {
            "samples": [
                {**bound, "sample_id": "a", "source": "value = 1 + 2\n"},
                {**bound, "sample_id": "b", "source": "# comment\nvalue=1+2\n"},
                {**bound, "sample_id": "c", "source": "value = 1 - 2\n"},
            ]
        }
        result["knowledge object"] = {"language": "python"}
    else:
        raise ValueError(f"unknown dataset fixture: {skill_name}")
    if not result["knowledge object"]:
        result["knowledge object"] = {
            "experience_digest": canonical_digest(result["experience episode"])
        }
    for key in ("human feedback", "verification evidence"):
        if not result[key]:
            result[key] = {"status": "NOT_RUN"}
    return result


class _UnitCatalog:
    """Only the allowlist contract used by these pure algorithm unit tests.

    Public service acceptance uses the real pinned catalog and the same inputs.
    """

    content_sha256 = "sha256:" + "0" * 64
    discovery: Mapping[str, Any] = {}
    atomic_skills: Mapping[str, Mapping[str, Any]] = {name: {} for name in DATASET_SEMANTIC_SKILLS}
    meta_skills: Mapping[str, Mapping[str, Any]] = {}


class DatasetSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scope = TenantScope(tenant_id="tenant-dataset", project_id="project-dataset")
        cls.handlers = build_dataset_handlers(_UnitCatalog(), None)

    def execute(self, name: str, values: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        return self.handlers[name](
            name,
            {"inputs": values if values is not None else fixture_inputs(name, self.scope)},
            self.scope,
            "invocation-dataset",
        )

    def test_exact_six_bindings_outputs_and_no_training_authority(self) -> None:
        self.assertEqual(len(self.handlers), 6)
        self.assertEqual(set(self.handlers), DATASET_SEMANTIC_SKILLS)
        for name in sorted(self.handlers):
            with self.subTest(skill=name):
                result = self.execute(name)
                self.assertEqual(result["status"], "SUCCEEDED")
                outputs = result["outputs"]
                self.assertEqual(
                    set(outputs),
                    {
                        "versioned dataset",
                        "dataset card",
                        "lineage graph",
                        "training eligibility decision",
                    },
                )
                decision = outputs["training eligibility decision"]
                self.assertFalse(decision["eligible"])
                self.assertFalse(decision["training_authorized"])
                self.assertEqual(decision["external_evidence_status"], "NOT_RUN")
                self.assertEqual(decision["certification_status"], "NOT_CERTIFIED")
                self.assertFalse(outputs["dataset card"]["caller_facts_verified"])
                self.assertEqual(result, self.execute(name))

    def test_split_exact_cutoffs_and_independent_calendar_oracle(self) -> None:
        name = "repo-org-time-split-builder"
        values = fixture_inputs(name, self.scope)
        items = self.execute(name, values)["outputs"]["versioned dataset"]["items"]
        actual = {item["sample_id"]: item["split"] for item in items}
        expected = {}
        for sample in values["experience episode"]["samples"]:
            month = datetime.fromisoformat(sample["observed_at"].replace("Z", "+00:00")).month
            expected[sample["sample_id"]] = {1: "train", 2: "validation", 3: "holdout"}[month]
        self.assertEqual(actual, expected)

    def test_split_transitive_org_fork_family_and_duplicate_content_leakage(self) -> None:
        name = "repo-org-time-split-builder"
        values = fixture_inputs(name, self.scope)
        samples = values["experience episode"]["samples"]
        # A and B share an organization, B and C share a fork. Transitive
        # leakage is detected even though A and C share no direct group value.
        samples[1]["organization_id"] = samples[0]["organization_id"]
        samples[2]["fork_family_id"] = samples[1]["fork_family_id"]
        items = self.execute(name, values)["outputs"]["versioned dataset"]["items"]
        self.assertEqual({item["split"] for item in items}, {"quarantine"})
        self.assertEqual(len({item["group_id"] for item in items}), 1)
        for grouping in (
            "repository_id",
            "organization_id",
            "fork_family_id",
            "task_family_id",
            "content_digest",
        ):
            with self.subTest(grouping=grouping):
                isolated = fixture_inputs(name, self.scope)
                a, b, _ = isolated["experience episode"]["samples"]
                b[grouping] = a[grouping]
                result = self.execute(name, isolated)["outputs"]["versioned dataset"]["items"]
                self.assertEqual(
                    [item["split"] for item in result], ["quarantine", "quarantine", "holdout"]
                )

    def test_split_rejects_unknown_identity_naive_time_and_reversed_cutoffs(self) -> None:
        name = "repo-org-time-split-builder"
        for mutation in ("unknown", "time", "cutoff", "duplicate"):
            values = fixture_inputs(name, self.scope)
            samples = values["experience episode"]["samples"]
            if mutation == "unknown":
                samples[0]["fork_family_id"] = None
            elif mutation == "time":
                samples[0]["observed_at"] = "2026-01-01T00:00:00"
            elif mutation == "cutoff":
                values["knowledge object"]["train_before"] = "2026-04-01T00:00:00Z"
            else:
                samples.append(copy.deepcopy(samples[0]))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.execute(name, values)

    def test_lineage_calculated_ancestors_and_revocation_exact_descendants(self) -> None:
        lineage = self.execute("dataset-lineage-and-provenance")["outputs"]
        self.assertEqual(
            {
                item["sample_id"]: item["source_node_ids"]
                for item in lineage["versioned dataset"]["items"]
            },
            {"sample-a": ["source-a"], "sample-b": ["source-b"]},
        )
        revoked = self.execute("dataset-revocation-unlearning-index")["outputs"][
            "versioned dataset"
        ]
        self.assertEqual(
            [item["node_id"] for item in revoked["items"]],
            ["adapter-a", "checkpoint-a", "dataset-a", "sample-a", "source-a"],
        )
        self.assertEqual(revoked["analysis"]["affected_checkpoint_ids"], ["checkpoint-a"])
        self.assertEqual(revoked["analysis"]["affected_adapter_ids"], ["adapter-a"])
        self.assertFalse(revoked["analysis"]["unlearning_executed"])
        self.assertFalse(revoked["analysis"]["deletion_executed"])
        self.assertFalse(revoked["analysis"]["retraining_executed"])

    def test_lineage_rejects_dangling_typed_edge_cycle_orphan_and_duplicates(self) -> None:
        for mutation in ("dangling", "type", "cycle", "orphan", "duplicate", "kind"):
            values = fixture_inputs("dataset-lineage-and-provenance", self.scope)
            graph = values["experience episode"]
            if mutation == "dangling":
                graph["edges"][0]["parent"] = "absent"
            elif mutation == "type":
                graph["edges"][0]["relation"] = "trained-into"
            elif mutation == "cycle":
                graph["edges"].append(
                    {"parent": "sample-a", "child": "sample-a", "relation": "derived-from"}
                )
            elif mutation == "orphan":
                graph["edges"].pop(0)
            elif mutation == "duplicate":
                graph["edges"].append(copy.deepcopy(graph["edges"][0]))
            else:
                graph["nodes"][0]["kind"] = "unknown-kind"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.execute("dataset-lineage-and-provenance", values)

    def test_revocation_multiple_roots_and_unknown_or_disallowed_roots(self) -> None:
        name = "dataset-revocation-unlearning-index"
        values = fixture_inputs(name, self.scope)
        values["knowledge object"]["revoked_ids"] = ["source-a", "sample-b"]
        dataset = self.execute(name, values)["outputs"]["versioned dataset"]
        checkpoint = next(item for item in dataset["items"] if item["node_id"] == "checkpoint-a")
        self.assertEqual(checkpoint["revocation_sources"], ["sample-b", "source-a"])
        for roots in (["unknown"], ["adapter-a"], ["source-a", "source-a"], []):
            with self.subTest(roots=roots), self.assertRaises(ValueError):
                values["knowledge object"]["revoked_ids"] = roots
                self.execute(name, values)

    def test_lineage_preserves_task_model_skill_human_edit_and_transform_sources(self) -> None:
        name = "dataset-lineage-and-provenance"
        values = fixture_inputs(name, self.scope)
        graph = values["experience episode"]
        for kind in ("task", "model", "skill", "human-edit", "transform"):
            graph["nodes"].append(
                {
                    "node_id": kind + "-one",
                    "kind": kind,
                    "content_digest": _digest("a"),
                    "version": "2.0.0",
                    "tenant_id": self.scope.tenant_id,
                    "project_id": self.scope.project_id,
                }
            )
            if kind != "transform":
                graph["edges"].append(
                    {
                        "parent": kind + "-one",
                        "child": "transform-one",
                        "relation": "contributed-to",
                    }
                )
        graph["edges"].append(
            {"parent": "transform-one", "child": "sample-a", "relation": "derived-from"}
        )
        values["knowledge object"]["experience_digest"] = canonical_digest(graph)
        dataset = self.execute(name, values)["outputs"]["versioned dataset"]
        sample = next(item for item in dataset["items"] if item["sample_id"] == "sample-a")
        self.assertEqual(
            sample["source_node_ids"],
            [
                "human-edit-one",
                "model-one",
                "skill-one",
                "source-a",
                "task-one",
                "transform-one",
            ],
        )

    def test_preference_roles_are_bound_to_matching_task_prompt_content_and_checks(self) -> None:
        name = "preference-pair-builder"
        result = self.execute(name)["outputs"]["versioned dataset"]
        self.assertEqual(
            (result["items"][0]["chosen_id"], result["items"][0]["rejected_id"]),
            ("fixed", "broken"),
        )
        self.assertFalse(result["analysis"]["human_identity_verified"])
        for mutation in (
            "task",
            "prompt",
            "content",
            "digest",
            "unknown",
            "same",
            "both-pass",
            "unresolved",
            "suite",
            "duplicate",
        ):
            values = fixture_inputs(name, self.scope)
            candidates = values["experience episode"]["candidates"]
            checks = values["verification evidence"]["results"]
            decision = values["human feedback"]["decisions"][0]
            if mutation == "task":
                candidates[1]["task_id"] = "other-task"
            elif mutation == "prompt":
                candidates[1]["prompt_digest"] = _digest("d")
            elif mutation == "content":
                checks[0]["content_digest"] = _digest("e")
            elif mutation == "digest":
                decision["chosen_evidence_digest"] = _digest("f")
            elif mutation == "unknown":
                decision["rejected_id"] = "absent"
            elif mutation == "same":
                decision["rejected_id"] = "fixed"
            elif mutation == "both-pass":
                checks[1]["checks"][0]["status"] = "PASS"
            elif mutation == "unresolved":
                checks[0]["checks"][0]["status"] = "NOT_RUN"
            elif mutation == "suite":
                checks[1]["checks"][0]["check_id"] = "other-suite"
                decision["rejected_evidence_digest"] = canonical_digest(checks[1])
            else:
                duplicate = copy.deepcopy(decision)
                duplicate["decision_id"] = "decision-two"
                values["human feedback"]["decisions"].append(duplicate)
            values["knowledge object"]["experience_digest"] = canonical_digest(
                values["experience episode"]
            )
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.execute(name, values)

    def test_selection_independently_calculated_scores_and_budget(self) -> None:
        dataset = self.execute("active-learning-sample-selection")["outputs"]["versioned dataset"]
        self.assertEqual(
            dataset["analysis"]["ranking"], ["expensive", "valuable", "uncertain", "routine"]
        )
        self.assertEqual(
            [item["sample_id"] for item in dataset["items"]], ["valuable", "uncertain"]
        )
        # Decimal hand calculation: .4*.5 + .3*1 + .2*.5 + .1*1 = .7.
        self.assertEqual([item["score_fraction"] for item in dataset["items"]], ["7/10", "2/5"])
        self.assertEqual(dataset["analysis"]["used_units"], 5)
        self.assertEqual(dataset["analysis"]["remaining_units"], 0)

    def test_selection_rejects_nonfinite_unnormalized_weights_metrics_and_budget(self) -> None:
        name = "active-learning-sample-selection"
        for value in (float("nan"), float("inf"), -0.01, 1.01, True):
            for field in ("metric", "weight"):
                values = fixture_inputs(name, self.scope)
                if field == "metric":
                    values["experience episode"]["samples"][0]["metrics"]["uncertainty"] = value
                else:
                    values["knowledge object"]["weights"]["uncertainty"] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.execute(name, values)
        for field, value in (("budget_units", -1), ("budget_units", True), ("limit", 1.5)):
            values = fixture_inputs(name, self.scope)
            values["knowledge object"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.execute(name, values)
        values = fixture_inputs(name, self.scope)
        values["knowledge object"]["weights"]["uncertainty"] = 0.3
        with self.assertRaisesRegex(ValueError, "sum exactly"):
            self.execute(name, values)

    def test_selection_zero_budget_and_stable_tie_order(self) -> None:
        name = "active-learning-sample-selection"
        values = fixture_inputs(name, self.scope)
        values["knowledge object"]["budget_units"] = 0
        self.assertEqual(self.execute(name, values)["outputs"]["versioned dataset"]["items"], [])
        values["knowledge object"]["budget_units"] = 10
        for sample in values["experience episode"]["samples"]:
            sample["metrics"] = {metric: 0.5 for metric in sample["metrics"]}
        self.assertEqual(
            self.execute(name, values)["outputs"]["versioned dataset"]["analysis"]["ranking"],
            ["expensive", "routine", "uncertain", "valuable"],
        )

    def test_ast_structural_duplicates_preserve_operators_identifiers_and_literals(self) -> None:
        name = "semantic-and-ast-deduplication"
        dataset = self.execute(name)["outputs"]["versioned dataset"]
        self.assertEqual(dataset["analysis"]["duplicate_count"], 1)
        self.assertEqual(
            {item["sample_id"]: item["duplicate_ids"] for item in dataset["items"]},
            {"a": ["b"], "c": []},
        )
        self.assertFalse(dataset["analysis"]["source_executed"])
        self.assertFalse(dataset["analysis"]["behavioral_equivalence_proven"])
        for source in ("other = 1 + 2", "value = 1 + 3", 'value = "1" + "2"', "value = 3"):
            values = fixture_inputs(name, self.scope)
            values["experience episode"]["samples"][1]["source"] = source
            with self.subTest(source=source):
                self.assertEqual(
                    self.execute(name, values)["outputs"]["versioned dataset"]["analysis"][
                        "duplicate_count"
                    ],
                    0,
                )

    def test_ast_rejects_languages_syntax_depth_and_oversize_without_execution(self) -> None:
        name = "semantic-and-ast-deduplication"
        for mutation in ("language", "syntax", "depth", "size"):
            values = fixture_inputs(name, self.scope)
            if mutation == "language":
                values["knowledge object"]["language"] = "typescript"
            else:
                values["experience episode"]["samples"][0]["source"] = {
                    "syntax": "def invalid(:",
                    "depth": "value=" + "+".join(["1"] * 150),
                    "size": "#" + "x" * 40_000,
                }[mutation]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.execute(name, values)
        with tempfile.TemporaryDirectory() as temporary:
            sentinel = Path(temporary) / "must-not-exist"
            values = fixture_inputs(name, self.scope)
            values["experience episode"]["samples"][0]["source"] = (
                f"open({str(sentinel)!r}, 'w').write('executed')"
            )
            self.execute(name, values)
            self.assertFalse(sentinel.exists())

    def test_all_handlers_reject_foreign_records_and_unknown_top_level_fields(self) -> None:
        for name in sorted(self.handlers):
            values = fixture_inputs(name, self.scope)
            episode = values["experience episode"]
            records = episode[next(iter(episode))]
            records[0]["tenant_id"] = "other-tenant"
            with self.subTest(skill=name, mutation="tenant"), self.assertRaises(ValueError):
                self.execute(name, values)
            values = fixture_inputs(name, self.scope)
            values["extra"] = True
            with self.subTest(skill=name, mutation="extra"), self.assertRaises(ValueError):
                self.execute(name, values)

    def test_empty_required_inputs_and_unbound_or_fabricated_evidence_fail_closed(self) -> None:
        for name in sorted(self.handlers):
            for key in fixture_inputs(name, self.scope):
                values = fixture_inputs(name, self.scope)
                values[key] = {}
                with (
                    self.subTest(skill=name, key=key),
                    self.assertRaisesRegex(ValueError, "non-empty"),
                ):
                    self.execute(name, values)
        for name in ("dataset-lineage-and-provenance", "preference-pair-builder"):
            values = fixture_inputs(name, self.scope)
            values["knowledge object"]["experience_digest"] = _digest("f")
            with self.subTest(skill=name), self.assertRaisesRegex(ValueError, "bind"):
                self.execute(name, values)
        values = fixture_inputs("repo-org-time-split-builder", self.scope)
        values["verification evidence"]["status"] = "PASS"
        with self.assertRaisesRegex(ValueError, "cannot claim"):
            self.execute("repo-org-time-split-builder", values)


if __name__ == "__main__":
    unittest.main()
