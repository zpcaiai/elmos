from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from elmos_pi_harness.benchmark import CampaignDefinition, CampaignRunner
from elmos_pi_harness.evidence import (
    EvidenceChain,
    EvidenceItem,
    evaluate_certification,
)
from elmos_pi_harness.models import (
    AuthoritySnapshot,
    ConflictError,
    ExecutorIdentity,
    LeaseConflictError,
    NotFoundError,
    PolicyDeniedError,
    StaleGenerationError,
    TextContent,
    ToolInvocation,
    ToolResult,
    WorkspaceLease,
)
from elmos_pi_harness.persistence import DurableStore
from elmos_pi_harness.policy import effective_policy
from elmos_pi_harness.protocol import (
    ProtocolNegotiationError,
    locate_active_turn,
    negotiate,
)
from elmos_pi_harness.tool_runtime import ToolRegistry, ToolRuntime


def uid() -> str:
    return str(uuid.uuid4())


class HarnessCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="pi-harness-test-")
        self.store = DurableStore(":memory:", artifact_root=self.temp.name)
        self.tenant = uid()
        self.project = uid()
        self.task = uid()
        self.store.create_task(self.tenant, self.project, "test objective", idempotency_key="create-1", task_id=self.task, actor_id="test")

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def _runtime(self) -> tuple[ExecutorIdentity, str, AuthoritySnapshot]:
        environment_id = uid()
        self.store.create_environment(self.tenant, self.task, "local", config={"workspace": self.temp.name})
        # create_environment uses a generated id; find it through the database
        environment_id = self.store._connection.execute("SELECT environment_id FROM execution_environment").fetchone()[0]
        snapshot = AuthoritySnapshot(uid(), environment_id, "policy-v1", frozenset({"repo.read", "repo.write"}), frozenset({"network.egress"}), {"network": "deny"})
        snapshot_id = uid()
        self.store.create_authority_snapshot(self.tenant, snapshot_id, snapshot)
        executor = ExecutorIdentity("executor-a", 0, "registry-v1")
        self.store.register_executor(self.tenant, environment_id, executor)
        return executor, snapshot_id, snapshot

    def test_authority_is_intersection_and_denial_union(self) -> None:
        snapshot = AuthoritySnapshot(uid(), uid(), "p1", frozenset({"read", "write"}), frozenset({"write"}))
        policy = effective_policy(snapshot, {"allowed": ["read", "write", "network"], "denied": ["network"]})
        self.assertEqual(policy.allowed_capabilities, frozenset({"read"}))
        with self.assertRaises(PolicyDeniedError):
            effective_policy(snapshot, {"allowed": []})

    def test_task_idempotency_history_and_tenant_isolation(self) -> None:
        replay = self.store.create_task(self.tenant, self.project, "test objective", idempotency_key="create-1", task_id=uid(), actor_id="test")
        self.assertTrue(replay["replayed"])
        with self.assertRaises(ConflictError):
            self.store.create_task(self.tenant, self.project, "different", idempotency_key="create-1", actor_id="test")
        self.store.transition_task(self.tenant, self.task, "QUEUED", idempotency_key="queue-1", actor_id="test")
        self.store.transition_task(self.tenant, self.task, "PLANNING", idempotency_key="plan-1", actor_id="test")
        self.store.transition_task(self.tenant, self.task, "RUNNING", idempotency_key="run-1", actor_id="test")
        events = self.store.events(self.tenant, self.task)
        self.assertEqual([item["sequence"] for item in events["items"]], [1, 2, 3, 4])
        with self.assertRaises(NotFoundError):
            self.store.get_task(uid(), self.task)

    def test_success_requires_verification(self) -> None:
        self.store.transition_task(self.tenant, self.task, "QUEUED", idempotency_key="queue-1", actor_id="test")
        self.store.transition_task(self.tenant, self.task, "PLANNING", idempotency_key="plan-1", actor_id="test")
        self.store.transition_task(self.tenant, self.task, "RUNNING", idempotency_key="run-1", actor_id="test")
        self.store.transition_task(self.tenant, self.task, "VERIFYING", idempotency_key="verify-1", actor_id="test")
        self.store.set_required_verifications(self.tenant, self.task, 1)
        with self.assertRaises(ConflictError):
            self.store.transition_task(self.tenant, self.task, "SUCCEEDED", idempotency_key="done-1", actor_id="test", payload={"verification_passed": True})
        self.store.record_verification(self.tenant, self.task, True, actor_id="verifier", verification_type="unit")
        result = self.store.transition_task(self.tenant, self.task, "SUCCEEDED", idempotency_key="done-1", actor_id="test", payload={"verification_passed": True})
        self.assertEqual(result["status"], "SUCCEEDED")

    def test_executor_generation_fences_old_tool_result(self) -> None:
        old, snapshot_id, snapshot = self._runtime()
        self.store.register_executor(self.tenant, snapshot.environment_id, ExecutorIdentity("executor-b", 1, "registry-v2"))
        invocation = ToolInvocation(uid(), self.task, snapshot.environment_id, snapshot_id, "repo.read", {}, "call-1", 1000, "read-only")
        with self.assertRaises(StaleGenerationError):
            self.store.begin_tool_call(self.tenant, invocation, old)

    def test_workspace_is_exclusive_and_takeover_requires_checkpoint(self) -> None:
        first = WorkspaceLease("ws-1", self.task, 0, "repo-1", "rev-1", "BOUND")
        self.assertFalse(self.store.acquire_workspace(self.tenant, first)["idempotent"])
        self.assertTrue(self.store.acquire_workspace(self.tenant, first)["idempotent"])
        with self.assertRaises(LeaseConflictError):
            self.store.acquire_workspace(self.tenant, WorkspaceLease("ws-1", uid(), 0, "repo-1", "rev-1", "BOUND"))
        checkpoint = self.store.record_checkpoint(self.tenant, self.task, self.task, {"safe": True}, workspace_id="ws-1", checkpoint_id=uid())
        self.store._connection.execute("UPDATE workspace_lease SET lease_expires_at='2000-01-01T00:00:00Z' WHERE workspace_id='ws-1'")
        self.store._connection.commit()
        takeover = self.store.takeover_workspace(self.tenant, "ws-1", uid(), checkpoint["checkpoint_id"])
        self.assertEqual(takeover["lease"]["generation"], 1)

    def test_typed_tool_result_is_durable_and_replayable(self) -> None:
        executor, snapshot_id, snapshot = self._runtime()
        registry = ToolRegistry()
        registry.register("repo.read", lambda invocation, _policy: ToolResult(invocation.call_id, (TextContent("ok"),)))
        runtime = ToolRuntime(self.store, registry)
        invocation = ToolInvocation(uid(), self.task, snapshot.environment_id, snapshot_id, "repo.read", {"path": "README.md"}, "call-2", 1000, "read-only")
        first = runtime.execute(self.tenant, invocation, executor, upper_policy={"allowed": ["repo.read"]})
        second = runtime.execute(self.tenant, invocation, executor, upper_policy={"allowed": ["repo.read"]})
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.items[0].to_dict(), {"type": "text", "text": "ok"})

    def test_protocol_negotiation_and_evidence_gate(self) -> None:
        client = self._capabilities("Paginated")
        server = self._capabilities("Paginated")
        negotiated = negotiate(client, server)
        self.assertEqual(locate_active_turn(negotiated, lambda: "new", {"active_turn": "old"}), "new")
        with self.assertRaises(ProtocolNegotiationError):
            negotiate(client, self._capabilities("Paginated", version="v2.0"))
        item = EvidenceItem(uid(), "local-tests", "LOCAL_EXECUTED", ("sha256:" + "a" * 64,), "runner", None, "AUTH-1")
        self.assertEqual(evaluate_certification([item])["status"], "READY_FOR_EXTERNAL_GATE")
        chain = EvidenceChain(scope={"task_id": self.task})
        chain.append(item)
        manifest = chain.write(Path(self.temp.name) / "evidence.json")
        self.assertEqual(manifest["items"][0]["evidence_id"], item.evidence_id)

    @staticmethod
    def _capabilities(history: str, version: str = "v1.0"):
        from elmos_pi_harness.models import ProtocolCapabilities

        return ProtocolCapabilities(history, True, True, "https://json-schema.org/draft/2020-12/schema", "strong", version, True)


class CampaignTests(unittest.TestCase):
    def test_verifier_owns_success(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-campaign-") as root:
            store = DurableStore(":memory:", artifact_root=root)

            class Adapter:
                def discover(self):
                    return {"version": "fixture", "revision": "rev-1"}

                def run(self, **_kwargs):
                    return {"wall_clock_ms": 2, "adapter_claimed_success": True}

            campaign = CampaignDefinition.from_dict({"id": uid(), "name": "one", "mode": "golden-route", "systems": ["fixture"], "task_suite": "case-1", "repositories": [root], "repetitions": 1})
            result = CampaignRunner(store, {"fixture": Adapter()}).run("11111111-1111-4111-8111-111111111111", campaign)
            self.assertIsNone(result["runs"][0]["validated_success"])
            store.close()


if __name__ == "__main__":
    unittest.main()
