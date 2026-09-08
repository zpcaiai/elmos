from __future__ import annotations

import unittest

from elmos_repository_orchestrator.contracts import ContractError, sha256_payload
from elmos_repository_orchestrator.multiagent import (
    AgentAssignment,
    AgentRole,
    GovernedMultiAgentCoordinator,
)


def handler(payload):
    return {
        "idempotency_key": payload["idempotency_key"],
        "evidence_digest": sha256_payload(payload),
    }


class MultiAgentTests(unittest.TestCase):
    def coordinator(self, *, completed=None):
        return GovernedMultiAgentCoordinator(
            [
                AgentRole("retriever", "worker-retrieval", frozenset({"rag.search"}), handler, max_parallel=2),
                AgentRole("repairer", "worker-repair", frozenset({"patch.apply", "test.run"}), handler),
            ],
            verifier=lambda value: {"passed": value["worker_identity"] != "verifier-independent", "reasons": []},
            verifier_identity="verifier-independent",
            completed_effects=completed,
            max_concurrency=2,
        )

    def test_dependency_waves_scope_approval_and_deduplication(self) -> None:
        assignments = [
            AgentAssignment("search", "retriever", frozenset({"rag.search"}), "effect-search"),
            AgentAssignment(
                "repair",
                "repairer",
                frozenset({"patch.apply", "test.run"}),
                "effect-repair",
                dependencies=("search",),
                requires_human_approval=True,
            ),
        ]
        blocked = self.coordinator().run(
            assignments, tenant_id="tenant-a", project_id="project-a", revision_id="rev-1"
        )
        self.assertEqual(blocked.status, "BLOCKED")
        self.assertEqual(blocked.outcomes[1].reasons, ("human_approval_required",))
        self.assertEqual(blocked.waves, (("search",), ("repair",)))

        completed = {"effect-search"}
        verified = self.coordinator(completed=completed).run(
            assignments,
            tenant_id="tenant-a",
            project_id="project-a",
            revision_id="rev-1",
            human_approved_tasks=frozenset({"repair"}),
        )
        self.assertEqual(verified.status, "VERIFIED")
        self.assertTrue(verified.outcomes[0].deduplicated)
        self.assertIn("effect-repair", completed)

    def test_unknown_role_forbidden_tool_cycle_and_non_independent_verifier_fail(self) -> None:
        with self.assertRaisesRegex(ContractError, "independent"):
            GovernedMultiAgentCoordinator(
                [AgentRole("worker", "same", frozenset({"x"}), handler)],
                verifier=lambda value: {"passed": True},
                verifier_identity="same",
            )
        coordinator = self.coordinator()
        with self.assertRaisesRegex(ContractError, "lacks required tools"):
            coordinator.run(
                [AgentAssignment("bad", "retriever", frozenset({"shell.any"}), "effect")],
                tenant_id="tenant-a",
                project_id="project-a",
                revision_id="rev-1",
            )
        with self.assertRaisesRegex(ContractError, "cycle"):
            coordinator.run(
                [
                    AgentAssignment("a", "retriever", frozenset({"rag.search"}), "effect-a", dependencies=("b",)),
                    AgentAssignment("b", "retriever", frozenset({"rag.search"}), "effect-b", dependencies=("a",)),
                ],
                tenant_id="tenant-a",
                project_id="project-a",
                revision_id="rev-1",
            )


if __name__ == "__main__":
    unittest.main()
