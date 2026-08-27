from __future__ import annotations

import unittest
import uuid

from elmos_pi_harness.agent import AgentLoop, ModelTurn
from elmos_pi_harness.models import TextContent, ToolResult
from elmos_pi_harness.multi_agent import AgentAssignment, FanoutCoordinator
from elmos_pi_harness.repair import RepairProposal, admit_repair
from elmos_pi_harness.telemetry import TelemetrySample, aggregate
from elmos_pi_harness.transformations import Recipe, RecipeRegistry


def uid() -> str:
    return str(uuid.uuid4())


class EpicContractTests(unittest.TestCase):
    def test_agent_loop_is_bounded_and_uses_typed_tool_results(self) -> None:
        calls = {"n": 0}

        def model(context):
            calls["n"] += 1
            if calls["n"] == 1:
                from elmos_pi_harness.models import ToolInvocation

                return ModelTurn("tool", tool=ToolInvocation(uid(), uid(), uid(), uid(), "read", {}, "agent-1", 1000, "read-only"))
            return ModelTurn("final", text="done")

        result = AgentLoop(max_turns=2).run([], model, lambda invocation: ToolResult(invocation.call_id, (TextContent("value"),)))
        self.assertEqual((result.status, result.turns, result.final_text), ("completed", 2, "done"))

    def test_fanout_rejects_workspace_collision_and_keeps_branch_errors(self) -> None:
        coordinator = FanoutCoordinator(max_workers=2)
        with self.assertRaises(ValueError):
            coordinator.validate([AgentAssignment("a", "same", "1"), AgentAssignment("b", "same", "2")])
        values = coordinator.run([AgentAssignment("a", "w1", "1"), AgentAssignment("b", "w2", "2")], lambda item: 1 / 0 if item.agent_id == "b" else item.task_id)
        self.assertEqual(values["a"], "1")
        self.assertIsInstance(values["b"], ZeroDivisionError)

    def test_repairs_and_transformations_are_gated_and_digest_bound(self) -> None:
        proposal = RepairProposal("p1", "test_failure", ("src/a.py",), "sha256:" + "a" * 64)
        self.assertFalse(admit_repair(proposal, verification_passed=False, approved=False)["admitted"])
        registry = RecipeRegistry()
        registry.register(Recipe("r1", "old", "new", ("rule-1",)))
        plan = registry.plan("r1", b"source")
        transformed, report = registry.apply(plan, b"source", lambda source, _rules: source + b"-new")
        self.assertEqual(transformed, b"source-new")
        self.assertEqual(report["status"], "APPLIED_BY_PARSER_ADAPTER")
        with self.assertRaises(ValueError):
            registry.apply(plan, b"changed", lambda source, _rules: source)

    def test_telemetry_is_aggregated_without_transcript_payloads(self) -> None:
        result = aggregate([TelemetrySample("t", "task", "model", input_tokens=2, cached_input_tokens=1, output_tokens=3, wall_clock_ms=4)])
        self.assertEqual(result["sample_count"], 1)
        self.assertNotIn("prompt", result)


if __name__ == "__main__":
    unittest.main()
