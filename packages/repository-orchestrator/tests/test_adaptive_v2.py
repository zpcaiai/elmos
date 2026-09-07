from __future__ import annotations

import json
from pathlib import Path
import unittest

from elmos_repository_orchestrator.catalog import SKILL_NAMES
from elmos_repository_orchestrator.contracts import Status
from elmos_repository_orchestrator.runtime import dispatch, handler_names


ROOT = Path(__file__).resolve().parents[3]


class AdaptiveV2RuntimeTests(unittest.TestCase):
    def test_catalog_registry_and_dispatcher_bind_all_54_exact_skills(self) -> None:
        registry = json.loads(
            (
                ROOT
                / "packages/repository-orchestrator/config/handler-registry.json"
            ).read_text(encoding="utf-8")
        )
        names = tuple(item["name"] for item in registry["skills"])
        self.assertEqual(54, len(SKILL_NAMES))
        self.assertEqual(SKILL_NAMES, handler_names())
        self.assertEqual(SKILL_NAMES, names)
        self.assertEqual("2.0.0", registry["package_version"])

    def test_all_17_v2_handlers_produce_bounded_structured_outcomes(self) -> None:
        cases = {
            "elmos-implicit-requirement-miner": {
                "candidates": [
                    {
                        "id": "IR1",
                        "statement": "Preserve API behavior",
                        "confidence": "0.9",
                        "evidence_refs": ["test_api.py:10"],
                    }
                ]
            },
            "elmos-behavioral-scenario-graph": {
                "scenarios": [
                    {"id": "S1", "kind": "happy", "statement": "request succeeds"},
                    {"id": "S2", "kind": "failure", "statement": "request fails closed"},
                ],
                "edges": [{"from": "S1", "to": "S2", "type": "precedes"}],
            },
            "elmos-repository-intelligence-graph": {
                "revision": "abc123",
                "nodes": [
                    {
                        "id": "N1",
                        "kind": "module",
                        "path": "src/core.py",
                        "evidence_refs": ["src/core.py:1"],
                    }
                ],
                "edges": [],
            },
            "elmos-architecture-invariant-ledger": {
                "invariants": [
                    {
                        "id": "I1",
                        "statement": "tenant scope is mandatory",
                        "risk": "critical",
                        "status": "VERIFIED",
                        "scope": ["src/auth.py"],
                        "evidence_refs": ["test_auth.py:20"],
                    }
                ]
            },
            "elmos-semantic-seam-detector": {
                "candidates": [
                    {
                        "id": "SEAM1",
                        "semantic_cohesion": "0.9",
                        "cross_boundary_coupling": "0.1",
                        "verification_locality": "0.9",
                    }
                ]
            },
            "elmos-adaptive-hierarchical-planner": {
                "run_id": "run-1",
                "revision": "rev-1",
                "nodes": [
                    {
                        "id": "G1",
                        "hierarchy_level": "goal",
                        "status": "ready",
                        "uncertainty": "high",
                        "risk": "high",
                    }
                ],
            },
            "elmos-task-granularity-controller": {
                "features": {
                    "context_demand": "0.8",
                    "write_surface": "0.8",
                    "semantic_breadth": "0.8",
                    "cross_boundary_coupling": "0.8",
                    "invariant_density": "0.8",
                    "verification_distance": "0.8",
                    "uncertainty": "0.8",
                }
            },
            "elmos-plan-graph-verifier": {
                "tasks": [
                    {
                        "id": "T1",
                        "owned_paths": ["src/core.py"],
                        "scenario_refs": ["S1"],
                        "invariant_refs": ["I1"],
                        "proof_obligation_refs": ["P1"],
                    }
                ],
                "edges": [],
                "required_scenarios": ["S1"],
                "required_invariants": ["I1"],
                "required_proofs": ["P1"],
            },
            "elmos-uncertainty-exploration-planner": {
                "run_budget": "100",
                "uncertainties": [
                    {
                        "question": "Which adapter is active?",
                        "decision_unblocked": "select target handler",
                        "estimated_cost": "5",
                    }
                ],
            },
            "elmos-proof-obligation-generator": {
                "boundaries": [
                    {
                        "id": "P1",
                        "kind": "authorization",
                        "statement": "cross-tenant access is denied",
                        "scope": ["src/auth.py"],
                    }
                ]
            },
            "elmos-integration-edge-planner": {
                "edges": [
                    {
                        "from": "T1",
                        "to": "T2",
                        "type": "contract",
                        "contract_ref": "C1",
                        "validator": "test_contract",
                    }
                ]
            },
            "elmos-dynamic-replanner": {
                "trigger": "contract_change",
                "still_valid_evidence": ["E1"],
                "invalidated_tasks": ["T2"],
            },
            "elmos-semantic-conflict-detector": {
                "patches": [
                    {"task_id": "T1", "paths": ["src/a.py"]},
                    {"task_id": "T2", "paths": ["src/b.py"]},
                ]
            },
            "elmos-critical-path-resource-scheduler": {
                "tasks": [
                    {"id": "T1", "duration_seconds": "2", "owned_paths": ["src/a.py"]},
                    {"id": "T2", "duration_seconds": "3", "owned_paths": ["src/b.py"]},
                ],
                "edges": [{"from": "T1", "to": "T2", "type": "dependency"}],
            },
            "elmos-baseline-golden-snapshotter": {
                "observations": {"api": "stable"},
                "environment": {"python": "3.12"},
                "known_failures": [],
            },
            "elmos-plan-diff-audit-journal": {
                "before": {"nodes": [{"id": "T1", "state": "coarse"}]},
                "after": {"nodes": [{"id": "T1", "state": "ready"}, {"id": "T2"}]},
            },
            "elmos-decomposition-telemetry-learner": {
                "records": [
                    {
                        "first_pass_success": True,
                        "replanned": False,
                        "integration_conflict": False,
                    }
                ]
            },
        }
        self.assertEqual(17, len(cases))
        for skill, payload in cases.items():
            with self.subTest(skill=skill):
                result = dispatch(skill, payload)
                self.assertIn(
                    result["status"],
                    {
                        Status.PLANNED.value,
                        Status.LOCAL_ENGINEERING_VALIDATED.value,
                    },
                )
                self.assertEqual(Status.NOT_CERTIFIED.value, result["certification"])
                self.assertFalse(result["side_effects_performed"])
                self.assertIsInstance(result["output"], dict)

    def test_plan_graph_rejects_cycle_overlap_missing_handoff_and_coverage(self) -> None:
        result = dispatch(
            "elmos-plan-graph-verifier",
            {
                "tasks": [
                    {"id": "T1", "owned_paths": ["src"]},
                    {"id": "T2", "owned_paths": ["src/core.py"]},
                ],
                "edges": [
                    {"from": "T1", "to": "T2", "type": "contract"},
                    {"from": "T2", "to": "T1", "type": "dependency"},
                ],
                "required_scenarios": ["S1"],
            },
        )
        self.assertEqual(Status.BLOCKED.value, result["status"])
        errors = result["output"]["errors"]
        self.assertIn("cycle_detected", errors)
        self.assertTrue(any(item.startswith("overlapping_owned_path:") for item in errors))
        self.assertTrue(any(item.startswith("missing_handoff_contract:") for item in errors))
        self.assertIn("missing_scenario:S1", errors)

    def test_exact_decimal_and_evidence_boundaries_fail_closed(self) -> None:
        invalid_cost = dispatch(
            "elmos-uncertainty-exploration-planner",
            {"run_budget": 10.5, "uncertainties": []},
        )
        self.assertEqual(Status.BLOCKED.value, invalid_cost["status"])
        self.assertTrue(invalid_cost["reasons"][0].startswith("invalid_decimal:"))

        no_evidence = dispatch(
            "elmos-architecture-invariant-ledger",
            {
                "invariants": [
                    {
                        "id": "I1",
                        "statement": "authorization holds",
                        "risk": "critical",
                        "status": "VERIFIED",
                    }
                ]
            },
        )
        self.assertEqual(Status.BLOCKED.value, no_evidence["status"])
        self.assertTrue(no_evidence["reasons"][0].startswith("verified_without_evidence:"))

    def test_semantic_conflict_is_blocking_and_never_auto_resolved(self) -> None:
        result = dispatch(
            "elmos-semantic-conflict-detector",
            {
                "patches": [
                    {"task_id": "T1", "paths": ["src/core"]},
                    {"task_id": "T2", "paths": ["src/core/model.py"]},
                ]
            },
        )
    def test_example_hierarchical_plan_e2e(self) -> None:
        plan_path = (
            ROOT
            / "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/examples/adaptive-hierarchical-plan.json"
        )
        plan = json.loads(plan_path.read_text(encoding="utf-8"))

        # 1. Hierarchical planner accepts plan with object risk/uncertainty
        planned = dispatch("elmos-adaptive-hierarchical-planner", plan)
        self.assertEqual(Status.PLANNED.value, planned["status"])
        self.assertEqual(["C1", "G0"], planned["output"]["refinement_frontier"])
        self.assertTrue(planned["output"]["lazy_refinement"])

        # 2. Plan graph verifier accepts hierarchical plan nodes and verifies coverage
        verified = dispatch("elmos-plan-graph-verifier", plan)
        self.assertEqual(Status.LOCAL_ENGINEERING_VALIDATED.value, verified["status"])
        self.assertTrue(verified["output"]["executable"])
        self.assertEqual([], verified["output"]["errors"])
        self.assertEqual([], verified["output"]["coverage"]["missing_scenarios"])
        self.assertEqual([], verified["output"]["coverage"]["missing_invariants"])
        self.assertEqual([], verified["output"]["coverage"]["missing_proofs"])

        # 3. Granularity controller matches reference decisions
        expected_granularity = {
            "G0": "split",
            "C1": "split",
            "T10": "keep",
            "T20": "keep",
            "T30": "keep",
        }
        for node in plan["nodes"]:
            features = node.get("granularity_features")
            if features:
                gran = dispatch(
                    "elmos-task-granularity-controller",
                    {
                        "features": {k: str(v) for k, v in features.items()},
                        "indivisible_invariant": node.get("indivisible_invariant", False),
                    },
                )
                self.assertEqual(
                    expected_granularity[node["id"]],
                    gran["output"]["decision"],
                    f"node {node['id']} granularity decision mismatch",
                )

        # 4. CLI validate-plan succeeds on the real example plan
        from elmos_repository_orchestrator.cli import main

        exit_code = main(["validate-plan", "--input", str(plan_path)])
        self.assertEqual(0, exit_code)


if __name__ == "__main__":
    unittest.main()
