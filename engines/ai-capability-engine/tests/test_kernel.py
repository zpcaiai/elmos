"""Comprehensive unit tests for elmos_ai_capability.kernel."""

from __future__ import annotations

import unittest
from elmos_ai_capability.kernel import (
    FeatureRequirement,
    TargetProfile,
    negotiate,
    validate_trace,
    compare_traces,
    ProofResult,
    CertificationInput,
    certify,
    validate_skill_ir,
    permission_expansions,
    portability_decision,
    TriggerObservation,
    evaluate_trigger,
    trigger_gate,
    McpTaskBridge,
    Calibration,
    calibrate,
    judge_use_decision,
    BudgetLimit,
    RunawayGuard,
    backward_compatibility,
    evolution_decision,
    compare_fingerprints,
    recertification_decision,
    RetrievalCandidate,
    authorize_candidates,
    deletion_reconciled,
    MemoryRecord,
    authorize_memory,
    isolation_probe,
    validate_topology,
    dependency_cycle,
    PackageTrustInput,
    trust_decision,
    IncidentController,
    Control,
    profile_decision,
    CacheContext,
    semantic_key,
    cache_reuse_decision,
    ToolContract,
    compare_tools,
    QualityResult,
    quality_gate,
    Usage,
    Rates,
    calculate_cost,
    budget_decision,
    ProviderCandidate,
    select_provider,
    PolicyRule,
    validate_rules,
    default_decision,
    ActionPreview,
    ux_gate,
)


class KernelTests(unittest.TestCase):
    def test_capability_negotiation(self) -> None:
        reqs = [
            FeatureRequirement("chat", critical=True),
            FeatureRequirement("code_exec", critical=False),
        ]
        profiles = [
            TargetProfile("target-1", {"chat": "supported", "code_exec": "emulated"}, "1.0.0", "sha256:abc123"),
        ]
        res = negotiate(reqs, profiles)
        self.assertEqual(res.overall, "BOUNDED")
        self.assertEqual(len(res.targets), 1)

    def test_capability_negotiation_blocked_on_critical(self) -> None:
        reqs = [FeatureRequirement("tool_calling", critical=True)]
        profiles = [
            TargetProfile("target-legacy", {"tool_calling": "unsupported"}, "1.0.0", "sha256:abc123"),
        ]
        res = negotiate(reqs, profiles)
        self.assertEqual(res.overall, "BLOCKED")

    def test_trace_comparison(self) -> None:
        ref = {
            "events": [
                {"id": "e1", "kind": "input", "timestamp": "2026-08-28T00:00:00Z"},
                {"id": "e2", "kind": "state_write", "target": "db", "payload_hash": "hash1", "timestamp": "2026-08-28T00:00:01Z", "cause": "e1"},
            ]
        }
        cand = {
            "events": [
                {"id": "e1", "kind": "input", "timestamp": "2026-08-28T00:00:00Z"},
                {"id": "e2", "kind": "state_write", "target": "db", "payload_hash": "hash1", "timestamp": "2026-08-28T00:00:01Z", "cause": "e1"},
            ]
        }
        res = compare_traces(ref, cand)
        self.assertTrue(res["equivalent"])

    def test_trace_mismatch(self) -> None:
        ref = {
            "events": [
                {"id": "e1", "kind": "state_write", "target": "db1", "payload_hash": "hash1", "timestamp": "2026-08-28T00:00:00Z"},
            ]
        }
        cand = {
            "events": [
                {"id": "e1", "kind": "state_write", "target": "db2", "payload_hash": "hash1", "timestamp": "2026-08-28T00:00:00Z"},
            ]
        }
        res = compare_traces(ref, cand)
        self.assertFalse(res["equivalent"])

    def test_certify_all_proved(self) -> None:
        results = [
            ProofResult("obl-1", "PROVED", "sha256:111", "critical"),
            ProofResult("obl-2", "PROVED", "sha256:222", "medium"),
        ]
        inp = CertificationInput("goal-1", "target-1", results)
        dec = certify(inp)
        self.assertEqual(dec.status, "CERTIFIED")
        self.assertEqual(dec.certified_level, "E3")

    def test_certify_critical_unknown_blocks(self) -> None:
        results = [
            ProofResult("obl-1", "UNKNOWN", "sha256:111", "critical"),
        ]
        inp = CertificationInput("goal-1", "target-1", results)
        dec = certify(inp)
        self.assertEqual(dec.status, "BLOCKED")

    def test_skill_ir_and_portability(self) -> None:
        src = {"name": "skill-a", "permissions": ["read_data"], "tools": ["search"]}
        tgt = {"name": "skill-a", "permissions": ["read_data", "admin_write"], "tools": ["search"]}
        res = portability_decision(src, tgt)
        self.assertFalse(res["portable"])
        self.assertIn("permission expansion", res["reason"])

    def test_trigger_eval(self) -> None:
        obs = [
            TriggerObservation("skill-1", True, True),
            TriggerObservation("skill-1", True, True),
            TriggerObservation("skill-1", False, False),
            TriggerObservation("skill-1", False, True),
        ]
        metrics = evaluate_trigger(obs)
        self.assertGreater(metrics.precision, 0.5)
        self.assertEqual(metrics.total, 4)

    def test_mcp_task_bridge(self) -> None:
        bridge = McpTaskBridge()
        t = bridge.create_task("task-1")
        self.assertEqual(t.status, "INITIALIZED")
        bridge.checkpoint("task-1", "checkpoint-1")
        bridge.complete("task-1", {"result": 42})
        st = bridge.get_state("task-1")
        self.assertEqual(st.status, "COMPLETED")
        self.assertEqual(st.result, {"result": 42})

    def test_runaway_guard(self) -> None:
        guard = RunawayGuard(BudgetLimit(max_steps=3))
        guard.step(10, 0.01)
        guard.step(10, 0.01)
        guard.step(10, 0.01)
        with self.assertRaises(RuntimeError):
            guard.step(10, 0.01)

    def test_schema_evolution(self) -> None:
        old_s = {"required": ["id"], "properties": {"id": {"type": "string"}}}
        new_s = {"required": ["id", "new_req"], "properties": {"id": {"type": "string"}, "new_req": {"type": "string"}}}
        dec = evolution_decision(old_s, new_s, migration_plan_present=False)
        self.assertEqual(dec, "BLOCKED")
        dec_mig = evolution_decision(old_s, new_s, migration_plan_present=True)
        self.assertEqual(dec_mig, "APPLY_WITH_MIGRATION")

    def test_rag_security_and_tenant_isolation(self) -> None:
        cands = [
            RetrievalCandidate("doc-1", "t1", frozenset(["analyst"])),
            RetrievalCandidate("doc-2", "t2", frozenset(["analyst"])),
            RetrievalCandidate("doc-3", "t1", frozenset(["admin"])),
        ]
        auth = authorize_candidates(cands, "t1", frozenset(["analyst"]))
        self.assertEqual(len(auth), 1)
        self.assertEqual(auth[0].doc_id, "doc-1")

    def test_multi_agent_cycle_detection(self) -> None:
        nodes = ["A", "B", "C"]
        edges = {"A": ["B"], "B": ["C"], "C": ["A"]}
        self.assertTrue(dependency_cycle(nodes, edges))

        edges_dag = {"A": ["B"], "B": ["C"], "C": []}
        self.assertFalse(dependency_cycle(nodes, edges_dag))


if __name__ == "__main__":
    unittest.main()
