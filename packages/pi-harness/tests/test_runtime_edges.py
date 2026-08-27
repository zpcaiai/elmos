from __future__ import annotations

import unittest
import uuid

from elmos_pi_harness.adapters import AdapterAPIVersion, AdapterBoundary
from elmos_pi_harness.environment import restore_environment, snapshot_environment
from elmos_pi_harness.executor import ExecutorConnection, refresh
from elmos_pi_harness.history import paginate
from elmos_pi_harness.models import (
    AuthoritySnapshot,
    EnvironmentRef,
    ExecutorIdentity,
    InstructionEnvelope,
    TextContent,
    ToolResult,
)
from elmos_pi_harness.routing import ModelCapability, RoutingRequest, route
from elmos_pi_harness.scheduler import ready_nodes, validate_acyclic
from elmos_pi_harness.verification import VerificationResult, evaluate


def uid() -> str:
    return str(uuid.uuid4())


class EdgeContractTests(unittest.TestCase):
    def test_resume_preserves_sandbox_and_replacement_requires_probe(self) -> None:
        ref = EnvironmentRef(uid(), uid(), 1, "local")
        authority = AuthoritySnapshot(uid(), ref.environment_id, "p1", frozenset({"read"}))
        snapshot = snapshot_environment(ref, authority, sandbox_overrides={"network": "deny"})
        restored = restore_environment(snapshot, ref, current_sandbox_overrides={"filesystem": "readonly"})
        self.assertEqual(restored["sandbox_overrides"], {"network": "deny", "filesystem": "readonly"})
        decision = refresh(ExecutorConnection(ExecutorIdentity("old", 0), True), ExecutorIdentity("new", 1), connection_healthy=False)
        self.assertTrue(decision["requires_live_status_probe"])

    def test_adapter_keeps_instruction_and_typed_result_at_boundary(self) -> None:
        adapter = AdapterBoundary(AdapterAPIVersion("pi", "v1", "upstream-5"), supported_capabilities={"read"}, approval_modes={"default"})
        self.assertFalse(adapter.validate_policy_mapping({"allowed": ["write"]})["valid"])
        envelope = adapter.instruction("do not widen", source="task", scope="tenant", provenance={"digest": "sha256:x"})
        self.assertIsInstance(envelope, InstructionEnvelope)
        result = ToolResult(uid(), (TextContent("typed"),))
        self.assertIs(adapter.result(result), result)

    def test_dag_routing_and_verification_are_conservative(self) -> None:
        nodes = [{"id": "a"}, {"id": "b", "depends_on": ["a"]}]
        validate_acyclic(nodes)
        self.assertEqual(ready_nodes(nodes, set()), ["a"])
        self.assertEqual(ready_nodes(nodes, {"a"}), ["b"])
        with self.assertRaises(ValueError):
            validate_acyclic([{"id": "a", "depends_on": ["b"]}, {"id": "b", "depends_on": ["a"]}])
        model = ModelCapability("m", "p", "native", 0.9, 1, 100, frozenset({"code"}))
        self.assertEqual(route(RoutingRequest(frozenset({"network"})), [model])["status"], "BLOCKED")
        result = evaluate([VerificationResult("unit", "PASS", None, None)], {"unit"})
        self.assertFalse(result["passed"])
        self.assertEqual(paginate([{"id": 1}, {"id": 2}], limit=1)["next_offset"], 1)


if __name__ == "__main__":
    unittest.main()
