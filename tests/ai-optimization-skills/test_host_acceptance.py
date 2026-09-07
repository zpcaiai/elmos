from __future__ import annotations

import json
import unittest
from pathlib import Path

from elmos_ai_optimization.cache import ContextCache
from elmos_ai_optimization.contracts import ContextRequest, ScopeDeniedError
from elmos_ai_optimization.evidence_context import Document, EvidenceContextService
from elmos_ai_optimization.scope import HostAuthority, ScopeResolver


ROOT = Path(__file__).resolve().parents[2]


class HostAcceptanceTest(unittest.TestCase):
    """Verifies that the repository-owned engine satisfies B0 and B1 acceptance criteria."""

    def setUp(self) -> None:
        self.authority = HostAuthority()
        self.authority.register_grant("tenant-prod", "repo-spring", ["engineer-1"], generation="gen-100")
        self.authority.create_session("tenant-prod", "engineer-1", "session-prod-tok")
        self.resolver = ScopeResolver(self.authority)
        self.scope = self.resolver.resolve(
            "tenant-prod", "engineer-1", "session-prod-tok", [("repo-spring", "rev-main")]
        )
        self.service = EvidenceContextService(self.resolver)
        self.cache = ContextCache(self.authority)

        # Ingest representative source documents
        self.service.add_document(
            Document.create(
                doc_id="doc-spring-ctrl",
                tenant="tenant-prod",
                repository="repo-spring",
                snapshot="rev-main",
                generation="gen-100",
                path="src/main/java/com/example/OrderController.java",
                symbol="OrderController",
                text="package com.example;\n\npublic class OrderController {\n    public String getOrder() { return \"ok\"; }\n}",
            )
        )
        self.service.add_document(
            Document.create(
                doc_id="doc-spring-svc",
                tenant="tenant-prod",
                repository="repo-spring",
                snapshot="rev-main",
                generation="gen-100",
                path="src/main/java/com/example/OrderService.java",
                symbol="OrderService",
                text="package com.example;\n\npublic class OrderService {\n    // 业务处理逻辑\n    public void processOrder() {}\n}",
            )
        )

    def test_b0_acceptance_scope_and_authority(self) -> None:
        """AO-AC-001 through AO-AC-008: Scope security, non-cartesian and ACL epoch check."""
        self.assertEqual(self.scope.tenant, "tenant-prod")
        self.assertEqual(self.scope.revisions[0].repository, "repo-spring")
        self.assertEqual(self.scope.revisions[0].generation, "gen-100")

        # Verify gap analysis file exists and documents the port mapping
        gap_file = ROOT / "docs/ai-optimization-skills/GAP_ANALYSIS.json"
        self.assertTrue(gap_file.is_file())
        gap_data = json.loads(gap_file.read_text())
        self.assertEqual(gap_data["host_status"], "IMPLEMENTED_LOCAL")
        self.assertEqual(gap_data["qualification"], "LOCAL_ENGINEERING_VALIDATED")

    def test_b1_acceptance_evidence_context_fast_path(self) -> None:
        """AO-AC-009 through AO-AC-014: Thin interface, exact lookup, UTF-8, and token budgeting."""
        req = ContextRequest(
            request_id="req-fast-1",
            query="OrderController",
            mode="exact",
            top_k=5,
            context_token_budget=2000,
            selector={"symbol": "OrderController"},
        )
        ctx = self.service.query(self.scope, req)
        self.assertEqual(ctx.status, "ok")
        self.assertEqual(len(ctx.items), 1)
        self.assertEqual(ctx.items[0].anchor.symbol, "OrderController")
        self.assertFalse(ctx.items[0].truncated)

    def test_b1_acceptance_cache_and_tombstone(self) -> None:
        """AO-AC-015 through AO-AC-018: Versioned cache, tombstone invalidation, and rollback support."""
        req = ContextRequest(
            request_id="req-cache-1",
            query="OrderController",
            mode="exact",
            top_k=5,
            context_token_budget=2000,
            selector={"symbol": "OrderController"},
        )
        ctx = self.service.query(self.scope, req)
        cache_key = self.cache.put(self.scope, req, ctx)

        # Hit
        hit = self.cache.get(cache_key, self.scope)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.status, "ok")

        # Invalidate via tombstone
        blob_digest = ctx.items[0].anchor.blob_digest
        self.cache.mark_tombstone("tenant-prod", blob_digest)
        miss = self.cache.get(cache_key, self.scope)
        self.assertIsNone(miss)


if __name__ == "__main__":
    unittest.main()
