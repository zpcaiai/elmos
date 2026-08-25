from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from elmos_cache_ref.affinity import WorkerCandidate, choose_target
from elmos_cache_ref.context_ledger import RepositoryContextLedger
from elmos_cache_ref.environment_cache import EnvironmentInputs, choose_restore
from elmos_cache_ref.miss_diagnostics import classify_identity_change, first_difference
from elmos_cache_ref.parity import ParityThresholds, evaluate_metrics, weighted_reuse
from elmos_cache_ref.prompt_cache import (
    NormalizedTokenUsage,
    PromptSegment,
    cache_affinity_key,
    compile_prompt,
)


class PromptCacheTests(unittest.TestCase):
    def test_canonical_prefix_is_stable_for_map_order(self):
        left = compile_prompt(
            [
                PromptSegment("system", "GLOBAL_STABLE", {"b": 2, "a": 1}),
                PromptSegment("project", "PROJECT_STABLE", {"language": "java"}),
                PromptSegment("task", "TURN_VOLATILE", {"request": "convert"}),
            ],
            provider_namespace="tenant/project/provider",
            compatibility_group="v1",
            provider="openai",
            model="model-a",
            effort="high",
            tool_schema_digest="sha256:" + "1" * 64,
        )
        right = compile_prompt(
            [
                PromptSegment("system", "GLOBAL_STABLE", {"a": 1, "b": 2}),
                PromptSegment("project", "PROJECT_STABLE", {"language": "java"}),
                PromptSegment("task", "TURN_VOLATILE", {"request": "different"}),
            ],
            provider_namespace="tenant/project/provider",
            compatibility_group="v1",
            provider="openai",
            model="model-a",
            effort="high",
            tool_schema_digest="sha256:" + "1" * 64,
        )
        self.assertEqual(left.manifest["stable_prefix_digest"], right.manifest["stable_prefix_digest"])
        self.assertNotEqual(left.volatile_turn, right.volatile_turn)

    def test_prompt_order_violation_is_rejected(self):
        with self.assertRaises(ValueError):
            compile_prompt(
                [
                    PromptSegment("task", "TURN_VOLATILE", "x"),
                    PromptSegment("system", "GLOBAL_STABLE", "y"),
                ],
                provider_namespace="n",
                compatibility_group="v1",
                provider="p",
                model="m",
                effort="e",
                tool_schema_digest="sha256:" + "0" * 64,
            )

    def test_model_or_effort_changes_affinity_key(self):
        args = dict(
            tenant_scope="t",
            project_id="p",
            branch_lineage="main",
            provider="openai",
            model="m1",
            effort="high",
            tool_schema_digest="sha256:" + "1" * 64,
            compatibility_group="v1",
            stable_prefix_digest="sha256:" + "2" * 64,
        )
        first = cache_affinity_key(**args)
        second = cache_affinity_key(**{**args, "model": "m2"})
        third = cache_affinity_key(**{**args, "effort": "low"})
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, third)

    def test_normalized_usage_reports_reuse(self):
        usage = NormalizedTokenUsage(10_000, 9_200, 500, 300, 100)
        self.assertAlmostEqual(usage.cached_token_reuse_ratio, 0.92)


class ContextLedgerTests(unittest.TestCase):
    def test_append_only_staleness_and_reread(self):
        ledger = RepositoryContextLedger("stream-1")
        ledger.append(
            "FILE_READ",
            {"logical_path": "src/A.java", "content_digest": "sha256:" + "a" * 64, "snapshot_digest": "sha256:" + "1" * 64},
            idempotency_key="e1",
            occurred_at="2026-08-20T00:00:00Z",
        )
        ledger.append(
            "CONTENT_CHANGED",
            {"logical_path": "src/A.java", "new_content_digest": "sha256:" + "b" * 64},
            idempotency_key="e2",
            occurred_at="2026-08-20T00:00:01Z",
        )
        self.assertEqual(ledger.materialize_fresh_reads(), [])
        ledger.append(
            "CONTENT_REREAD",
            {"logical_path": "src/A.java", "content_digest": "sha256:" + "b" * 64, "snapshot_digest": "sha256:" + "2" * 64},
            idempotency_key="e3",
            occurred_at="2026-08-20T00:00:02Z",
        )
        self.assertFalse(ledger.current_file_state()["src/A.java"]["stale"])
        self.assertTrue(ledger.validate_chain())

    def test_idempotency_rejects_different_payload(self):
        ledger = RepositoryContextLedger("stream-1")
        ledger.append("TOOL_OBSERVED", {"value": 1}, idempotency_key="same", occurred_at="2026-08-20T00:00:00Z")
        with self.assertRaises(ValueError):
            ledger.append("TOOL_OBSERVED", {"value": 2}, idempotency_key="same", occurred_at="2026-08-20T00:00:00Z")

    def test_chain_detects_mutation(self):
        ledger = RepositoryContextLedger("stream-1")
        ledger.append("TOOL_OBSERVED", {"value": 1}, idempotency_key="e1", occurred_at="2026-08-20T00:00:00Z")
        ledger.corrupt_event_for_test(0, payload={"value": 2})
        self.assertFalse(ledger.validate_chain())


class EnvironmentAndAffinityTests(unittest.TestCase):
    def test_environment_key_is_order_stable_and_sensitive(self):
        base = EnvironmentInputs(
            base_image_digest="sha256:" + "1" * 64,
            setup_script_digest="sha256:" + "2" * 64,
            maintenance_script_digest="sha256:" + "3" * 64,
            lockfile_digests=("sha256:" + "5" * 64, "sha256:" + "4" * 64),
            toolchain_digests=("sha256:" + "6" * 64,),
            platform={"arch": "amd64", "os": "linux"},
            approved_environment={"LANG": "C.UTF-8"},
            secret_reference_versions={"API_TOKEN": "version-1"},
        )
        reordered = EnvironmentInputs(
            **{**base.__dict__, "lockfile_digests": tuple(reversed(base.lockfile_digests)), "platform": {"os": "linux", "arch": "amd64"}}
        )
        changed = EnvironmentInputs(**{**base.__dict__, "secret_reference_versions": {"API_TOKEN": "version-2"}})
        self.assertEqual(base.key(), reordered.key())
        self.assertNotEqual(base.key(), changed.key())

    def test_restore_bypasses_when_more_expensive(self):
        self.assertFalse(choose_restore(restore_ms=100, verify_ms=10, rebuild_ms=50).restore)
        self.assertTrue(choose_restore(restore_ms=10, verify_ms=5, rebuild_ms=100).restore)

    def test_affinity_uses_compatible_net_value(self):
        decision = choose_target(
            [
                WorkerCandidate("cold", True, True, queue_penalty_ms=1),
                WorkerCandidate("hot-overloaded", True, True, prompt_value_ms=100, queue_penalty_ms=150),
                WorkerCandidate("hot", True, True, prompt_value_ms=70, environment_value_ms=20, queue_penalty_ms=10),
                WorkerCandidate("incompatible", False, True, prompt_value_ms=1000),
            ]
        )
        self.assertEqual(decision.selected_target, "hot")
        self.assertIn("PREFIX_LOCAL", decision.reason_codes)
        self.assertIn("ENV_LOCAL", decision.reason_codes)


class DiagnosticsAndParityTests(unittest.TestCase):
    def test_first_difference_and_classification(self):
        before = {"model": "a", "effort": "high", "nested": {"x": 1}}
        after = {"model": "b", "effort": "high", "nested": {"x": 1}}
        reason, diff = classify_identity_change(before, after)
        self.assertEqual(reason, "MODEL_CHANGED")
        self.assertEqual(diff.path, "$.model")
        self.assertEqual(first_difference({"a": [1, 2]}, {"a": [1, 3]}).path, "$.a[1]")

    def test_weighted_reuse_values_expensive_hits(self):
        self.assertAlmostEqual(weighted_reuse([(True, 100), (False, 10)]), 100 / 110)

    def test_default_parity_metrics_pass(self):
        metrics = {
            "stable_turn_cached_token_reuse": 0.93,
            "unexpected_full_prefix_miss": 0.01,
            "exact_rerun_weighted_reuse": 0.995,
            "small_edit_weighted_reuse": 0.92,
            "unnecessary_invalidation": 0.03,
            "environment_snapshot_hit": 0.97,
            "warm_start_p95_reduction": 0.84,
            "restart_artifact_reuse": 0.9995,
            "stable_followup_wall_clock_saved": 0.74,
            "model_input_cost_saved": 0.83,
            "long_session_cached_token_reuse": 0.82,
            "false_hits": 0,
            "cross_tenant_hits": 0,
            "corrupt_executions": 0,
            "under_validated_publications": 0,
        }
        self.assertTrue(evaluate_metrics(metrics)["mandatory_pass"])

    def test_false_hit_always_fails(self):
        metrics = {
            "stable_turn_cached_token_reuse": 1.0,
            "unexpected_full_prefix_miss": 0.0,
            "exact_rerun_weighted_reuse": 1.0,
            "small_edit_weighted_reuse": 1.0,
            "unnecessary_invalidation": 0.0,
            "environment_snapshot_hit": 1.0,
            "warm_start_p95_reduction": 1.0,
            "restart_artifact_reuse": 1.0,
            "stable_followup_wall_clock_saved": 1.0,
            "model_input_cost_saved": 1.0,
            "long_session_cached_token_reuse": 1.0,
            "false_hits": 1,
            "cross_tenant_hits": 0,
            "corrupt_executions": 0,
            "under_validated_publications": 0,
        }
        result = evaluate_metrics(metrics)
        self.assertFalse(result["mandatory_pass"])
        self.assertTrue(any(item.startswith("false_hits") for item in result["failures"]))


if __name__ == "__main__":
    unittest.main()
