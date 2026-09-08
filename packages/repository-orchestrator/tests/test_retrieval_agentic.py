from __future__ import annotations

import unittest
import importlib.util

from elmos_repository_orchestrator.agentic import LangGraphRepairWorkflow, RepairTools
from elmos_repository_orchestrator.contracts import ContractError, sha256_payload
from elmos_repository_orchestrator.retrieval import (
    HybridIndex,
    RetrievalQuery,
    SearchDocument,
    SourceAnchor,
    ndcg_at_k,
    recall_at_k,
)
from elmos_repository_orchestrator.semantic import SemanticSkillRouter, SkillDescriptor


def document(
    identity: str,
    content: str,
    *,
    tenant: str = "tenant-a",
    project: str = "project-a",
    revision: str = "rev-1",
    principals: frozenset[str] = frozenset({"alice"}),
    vector: tuple[float, ...] | None = None,
    modality: str = "text",
) -> SearchDocument:
    return SearchDocument(
        document_id=identity,
        tenant_id=tenant,
        project_id=project,
        revision_id=revision,
        content=content,
        anchor=SourceAnchor(
            uri=f"repo://src/{identity}.py",
            kind="code-lines",
            content_sha256=sha256_payload(content),
            start=1,
            end=3,
        ),
        allowed_principals=principals,
        vector=vector,
        modality=modality,
    )


class HybridRetrievalTests(unittest.TestCase):
    def test_hybrid_ranking_is_scoped_cited_and_idempotent(self) -> None:
        index = HybridIndex()
        inserted, unchanged = index.upsert(
            [
                document("queue", "durable queue checkpoint resume", vector=(1.0, 0.0)),
                document("cache", "verified artifact cache digest", vector=(0.9, 0.1)),
                document("secret", "durable queue secret", tenant="tenant-b", vector=(1.0, 0.0)),
                document("private", "durable queue private", principals=frozenset({"bob"}), vector=(1.0, 0.0)),
            ]
        )
        self.assertEqual((inserted, unchanged), (4, 0))
        self.assertEqual(index.upsert([document("queue", "durable queue checkpoint resume", vector=(1.0, 0.0))]), (0, 1))
        hits = index.search(
            RetrievalQuery(
                tenant_id="tenant-a",
                project_id="project-a",
                revision_id="rev-1",
                principal_ids=frozenset({"alice"}),
                text="durable queue",
                vector=(1.0, 0.0),
                top_k=10,
            )
        )
        self.assertEqual([hit.document.document_id for hit in hits], ["queue", "cache"])
        for hit in hits:
            payload = hit.to_payload()
            self.assertEqual(payload["tenant_id"], "tenant-a")
            self.assertTrue(payload["anchor"]["content_sha256"].startswith("sha256:"))
            self.assertIn("alice", payload["allowed_principals"])

    def test_revision_deletion_and_vector_dimension_fail_closed(self) -> None:
        index = HybridIndex()
        index.upsert([document("a", "alpha", vector=(1.0, 0.0))])
        with self.assertRaisesRegex(ContractError, "different dimensions"):
            index.search(
                RetrievalQuery(
                    tenant_id="tenant-a",
                    project_id="project-a",
                    revision_id="rev-1",
                    principal_ids=frozenset({"alice"}),
                    text="alpha",
                    vector=(1.0,),
                )
            )
        self.assertEqual(index.delete_revision(tenant_id="tenant-a", project_id="project-a", revision_id="rev-1"), 1)
        self.assertEqual(
            index.search(
                RetrievalQuery(
                    tenant_id="tenant-a",
                    project_id="project-a",
                    revision_id="rev-1",
                    principal_ids=frozenset({"alice"}),
                    text="alpha",
                )
            ),
            (),
        )

    def test_retrieval_metrics(self) -> None:
        self.assertEqual(recall_at_k(["a", "x", "b"], frozenset({"a", "b"}), k=2), 0.5)
        self.assertAlmostEqual(ndcg_at_k(["a", "b"], {"a": 3.0, "b": 1.0}, k=2), 1.0)


class SemanticRouterTests(unittest.TestCase):
    def test_semantic_router_preserves_allowlist_caps_and_dependency_order(self) -> None:
        router = SemanticSkillRouter(
            [
                SkillDescriptor("source-anchor", "Source anchors", "provenance line evidence", vector=(0.0, 1.0)),
                SkillDescriptor(
                    "hybrid-rag",
                    "Hybrid RAG",
                    "semantic vector lexical retrieval",
                    dependencies=("source-anchor",),
                    vector=(1.0, 0.0),
                ),
                SkillDescriptor("billing", "Billing", "invoice and money", vector=(0.0, 1.0)),
            ]
        )
        plan = router.route("semantic retrieval", query_vector=(1.0, 0.0), discovery_limit=3, activation_limit=2)
        self.assertEqual(plan.discovered[0], "hybrid-rag")
        self.assertEqual(plan.activated, ("source-anchor", "hybrid-rag"))
        self.assertLessEqual(len(plan.discovered), 16)
        self.assertLessEqual(len(plan.activated), 8)
        self.assertTrue(all(name in {"source-anchor", "hybrid-rag", "billing"} for name in plan.activated))

    def test_unknown_dependency_and_excess_caps_are_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "unknown skill dependencies"):
            SemanticSkillRouter([SkillDescriptor("a", "A", "alpha", dependencies=("missing",))])
        router = SemanticSkillRouter([SkillDescriptor("a", "A", "alpha")])
        with self.assertRaisesRegex(ContractError, "between 1 and 16"):
            router.route("alpha", discovery_limit=17)


class LangGraphRepairTests(unittest.TestCase):
    @staticmethod
    def tools(executions: list[str]) -> RepairTools:
        def planner(state):
            return {"tool": "patch.apply", "risk": "low", "idempotency_key": f"{state['task_id']}:1"}

        def executor(state):
            key = state["plan"]["idempotency_key"]
            executions.append(key)
            return {"idempotency_key": key, "patch_digest": sha256_payload(key)}

        def verifier(state):
            return {"passed": state.get("attempt", 0) >= 2, "reasons": ["holdout_failed"]}

        def repairer(state):
            return {
                "plan": {
                    "tool": "patch.apply",
                    "risk": "low",
                    "idempotency_key": f"{state['task_id']}:{state['attempt'] + 1}",
                }
            }

        return RepairTools(
            planner=planner,
            executor=executor,
            verifier=verifier,
            repairer=repairer,
            executor_identity="executor-a",
            verifier_identity="verifier-b",
        )

    @unittest.skipUnless(importlib.util.find_spec("langgraph"), "agentic extra is not installed")
    def test_real_langgraph_repairs_checkpoints_and_stops(self) -> None:
        from langgraph.checkpoint.memory import InMemorySaver

        executions: list[str] = []
        workflow = LangGraphRepairWorkflow(self.tools(executions), allowed_tools=frozenset({"patch.apply"}))
        checkpointer = InMemorySaver()
        graph = workflow.compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": "repair-thread-1"}}
        result = graph.invoke(
            {
                "task_id": "T-1",
                "objective": "repair failing test",
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "revision_id": "rev-1",
                "attempt": 0,
                "max_attempts": 3,
                "human_approved": False,
                "duplicate_side_effects": 0,
            },
            config,
        )
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["attempt"], 2)
        self.assertEqual(executions, ["T-1:1", "T-1:2"])
        self.assertEqual(graph.get_state(config).values["status"], "VERIFIED")

    @unittest.skipUnless(importlib.util.find_spec("langgraph"), "agentic extra is not installed")
    def test_allowlist_approval_independence_and_idempotency(self) -> None:
        executions: list[str] = []
        with self.assertRaisesRegex(ContractError, "must differ"):
            RepairTools(lambda _: {}, lambda _: {}, lambda _: {}, lambda _: {}, "same", "same")
        tools = self.tools(executions)
        blocked_tools = RepairTools(
            planner=lambda state: {"tool": "shell.any", "risk": "low", "idempotency_key": "bad"},
            executor=tools.executor,
            verifier=tools.verifier,
            repairer=tools.repairer,
            executor_identity="executor-a",
            verifier_identity="verifier-b",
        )
        result = LangGraphRepairWorkflow(blocked_tools, allowed_tools=frozenset({"patch.apply"})).invoke(
            {"task_id": "T-2", "objective": "x", "max_attempts": 1}, thread_id="blocked"
        )
        self.assertEqual((result["status"], executions), ("BLOCKED", []))

        high_risk = RepairTools(
            planner=lambda state: {"tool": "patch.apply", "risk": "high", "idempotency_key": "T-3:1"},
            executor=tools.executor,
            verifier=lambda state: {"passed": True, "reasons": []},
            repairer=tools.repairer,
            executor_identity="executor-a",
            verifier_identity="verifier-b",
        )
        result = LangGraphRepairWorkflow(high_risk, allowed_tools=frozenset({"patch.apply"})).invoke(
            {"task_id": "T-3", "objective": "x", "max_attempts": 1, "human_approved": False},
            thread_id="approval",
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(executions, [])

        completed = {"T-4:1"}
        idempotent = RepairTools(
            planner=lambda state: {"tool": "patch.apply", "risk": "low", "idempotency_key": "T-4:1"},
            executor=tools.executor,
            verifier=lambda state: {"passed": True, "reasons": []},
            repairer=tools.repairer,
            executor_identity="executor-a",
            verifier_identity="verifier-b",
        )
        result = LangGraphRepairWorkflow(
            idempotent, allowed_tools=frozenset({"patch.apply"}), completed_effects=completed
        ).invoke({"task_id": "T-4", "objective": "x", "max_attempts": 1}, thread_id="dedupe")
        self.assertEqual(result["status"], "VERIFIED")
        self.assertTrue(result["execution"]["deduplicated"])
        self.assertEqual(executions, [])


if __name__ == "__main__":
    unittest.main()
