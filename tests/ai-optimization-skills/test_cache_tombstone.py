from __future__ import annotations

import unittest

from elmos_ai_optimization.cache import ContextCache
from elmos_ai_optimization.contracts import ContextItem, ContextRequest, EvidenceContext, SourceAnchor
from elmos_ai_optimization.scope import HostAuthority, ScopeResolver


class CacheTombstoneTest(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = HostAuthority()
        self.authority.register_grant("tenant-1", "repo-1", ["alice", "bob"], generation="gen-1")
        self.authority.create_session("tenant-1", "alice", "tok-a")
        self.authority.create_session("tenant-1", "bob", "tok-b")
        self.resolver = ScopeResolver(self.authority)
        self.scope_alice = self.resolver.resolve("tenant-1", "alice", "tok-a", [("repo-1", "snap-1")])
        self.scope_bob = self.resolver.resolve("tenant-1", "bob", "tok-b", [("repo-1", "snap-1")])

        self.cache = ContextCache(self.authority)
        self.req = ContextRequest(
            request_id="r1",
            query="OrderService",
            mode="exact",
            top_k=5,
            context_token_budget=1000,
        )
        anchor = SourceAnchor(
            repository="repo-1",
            snapshot="snap-1",
            generation="gen-1",
            path="src/order.py",
            blob_digest="a" * 64,
            start_byte=0,
            end_byte=20,
            symbol="Order",
        )
        self.ctx = EvidenceContext(
            status="ok",
            scope_digest=self.scope_alice.digest,
            items=(ContextItem(anchor=anchor, text="class Order: pass", truncated=False, evidence_ref="ev-1"),),
        )

    def test_cache_put_and_get(self) -> None:
        key = self.cache.put(self.scope_alice, self.req, self.ctx)
        cached = self.cache.get(key, self.scope_alice)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.status, "ok")
        self.assertEqual(len(cached.items), 1)

    def test_other_principal_cache_miss(self) -> None:
        key = self.cache.put(self.scope_alice, self.req, self.ctx)
        cached = self.cache.get(key, self.scope_bob)
        self.assertIsNone(cached)

    def test_acl_epoch_bump_invalidates_cache(self) -> None:
        key = self.cache.put(self.scope_alice, self.req, self.ctx)
        self.authority.bump_acl_epoch("tenant-1")
        cached = self.cache.get(key, self.scope_alice)
        self.assertIsNone(cached)

    def test_tombstone_invalidates_cache(self) -> None:
        key = self.cache.put(self.scope_alice, self.req, self.ctx)
        self.cache.mark_tombstone("tenant-1", "a" * 64)
        cached = self.cache.get(key, self.scope_alice)
        self.assertIsNone(cached)


if __name__ == "__main__":
    unittest.main()
