from __future__ import annotations

import unittest

from elmos_ai_optimization.contracts import ContextRequest
from elmos_ai_optimization.evidence_context import Document, EvidenceContextService
from elmos_ai_optimization.scope import HostAuthority, ScopeResolver


class EvidenceContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = HostAuthority()
        self.authority.register_grant("tenant-1", "repo-1", ["dev-1"], generation="gen-1")
        self.authority.create_session("tenant-1", "dev-1", "tok-1")
        self.resolver = ScopeResolver(self.authority)
        self.scope = self.resolver.resolve("tenant-1", "dev-1", "tok-1", [("repo-1", "snap-1")])

        self.service = EvidenceContextService(self.resolver)
        self.doc1 = Document.create(
            doc_id="d1",
            tenant="tenant-1",
            repository="repo-1",
            snapshot="snap-1",
            generation="gen-1",
            path="src/order/service.py",
            symbol="OrderService",
            text="class OrderService:\n    def create_order(self):\n        pass",
            vector=[0.1, 0.2, 0.3],
        )
        self.doc2 = Document.create(
            doc_id="d2",
            tenant="tenant-1",
            repository="repo-1",
            snapshot="snap-1",
            generation="gen-1",
            path="src/order/models.py",
            symbol="OrderModel",
            text="class OrderModel:\n    id: str\n    total: float",
            vector=[0.2, 0.1, 0.4],
        )
        self.doc_cjk = Document.create(
            doc_id="d3",
            tenant="tenant-1",
            repository="repo-1",
            snapshot="snap-1",
            generation="gen-1",
            path="src/payment/alipay.py",
            symbol="AlipayGateway",
            text="class AlipayGateway:\n    # 支付宝支付网关实现\n    def pay(self): pass",
            vector=[0.0, 0.5, 0.5],
        )
        self.service.add_document(self.doc1)
        self.service.add_document(self.doc2)
        self.service.add_document(self.doc_cjk)

    def test_exact_fast_path_by_symbol(self) -> None:
        req = ContextRequest(
            request_id="req-1",
            query="OrderService",
            mode="exact",
            top_k=5,
            context_token_budget=1000,
            selector={"symbol": "OrderService"},
        )
        ctx = self.service.query(self.scope, req)
        self.assertEqual(ctx.status, "ok")
        self.assertEqual(len(ctx.items), 1)
        self.assertEqual(ctx.items[0].anchor.symbol, "OrderService")
        self.assertEqual(ctx.items[0].anchor.path, "src/order/service.py")
        self.assertFalse(ctx.items[0].truncated)

    def test_fts_lexical_cjk_search(self) -> None:
        req = ContextRequest(
            request_id="req-2",
            query="支付宝",
            mode="lexical",
            top_k=5,
            context_token_budget=1000,
        )
        ctx = self.service.query(self.scope, req)
        self.assertEqual(ctx.status, "ok")
        self.assertEqual(len(ctx.items), 1)
        self.assertEqual(ctx.items[0].anchor.symbol, "AlipayGateway")

    def test_token_budget_truncation(self) -> None:
        # Request with very tiny budget (e.g. 5 tokens => ~20 chars)
        req = ContextRequest(
            request_id="req-3",
            query="OrderService",
            mode="exact",
            top_k=5,
            context_token_budget=5,
            selector={"symbol": "OrderService"},
        )
        ctx = self.service.query(self.scope, req)
        self.assertEqual(ctx.status, "ok")
        self.assertEqual(len(ctx.items), 1)
        self.assertTrue(ctx.items[0].truncated)
        self.assertLessEqual(len(ctx.items[0].text), 25)

    def test_tombstoned_document_not_returned(self) -> None:
        self.service.tombstone_document("tenant-1", "d1")
        req = ContextRequest(
            request_id="req-4",
            query="OrderService",
            mode="exact",
            top_k=5,
            context_token_budget=1000,
            selector={"symbol": "OrderService"},
        )
        ctx = self.service.query(self.scope, req)
        self.assertEqual(ctx.status, "insufficient_evidence")
        self.assertEqual(len(ctx.items), 0)


if __name__ == "__main__":
    unittest.main()
