import unittest
from elmos_ai_optimization.cache import ContextCache, CacheEntry
from elmos_ai_optimization.scope import HostAuthority
from elmos_ai_optimization.contracts import TrustedScope, ContextRequest, EvidenceContext, ContextItem, SourceAnchor, RevisionBinding

class TestCache(unittest.TestCase):
    def setUp(self):
        self.auth = HostAuthority()
        self.cache = ContextCache(self.auth)
        self.auth.register_grant("t1", "r1", ["p1"], "gen-1")
        self.auth.create_session("t1", "p1", "tok")

        self.scope = TrustedScope("t1", "p1", self.auth.get_acl_epoch("t1"), "sec_ref", (RevisionBinding("r1", "s1", "gen-1"),))
        self.request = ContextRequest("req1", "query", "auto", 10, 1000)
        
        anchor1 = SourceAnchor("r1", "s1", "gen-1", "path1", "a"*64, 0, 10, "sym")
        item1 = ContextItem(anchor1, "text", False, "ev1")
        self.context = EvidenceContext("ok", self.scope.digest, (item1,))

    def test_compute_key(self):
        key = self.cache.compute_key(self.scope, self.request)
        self.assertEqual(len(key), 64)

    def test_put_get_happy_path(self):
        key = self.cache.put(self.scope, self.request, self.context)
        cached = self.cache.get(key, self.scope)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.status, "ok")
        self.assertEqual(len(cached.items), 1)

    def test_get_not_found(self):
        self.assertIsNone(self.cache.get("invalid_key", self.scope))

    def test_tenant_mismatch(self):
        key = self.cache.put(self.scope, self.request, self.context)
        scope2 = TrustedScope("t2", "p1", self.auth.get_acl_epoch("t1"), "sec_ref", (RevisionBinding("r1", "s1", "gen-1"),))
        self.assertIsNone(self.cache.get(key, scope2))

    def test_principal_mismatch(self):
        key = self.cache.put(self.scope, self.request, self.context)
        scope2 = TrustedScope("t1", "p2", self.auth.get_acl_epoch("t1"), "sec_ref", (RevisionBinding("r1", "s1", "gen-1"),))
        self.assertIsNone(self.cache.get(key, scope2))

    def test_acl_epoch_invalidation(self):
        key = self.cache.put(self.scope, self.request, self.context)
        self.auth.bump_acl_epoch("t1")
        # Ensure that getting it with old scope fails because current epoch bumped
        self.assertIsNone(self.cache.get(key, self.scope))
        # getting with new scope also fails because cache entry was stored at old epoch
        scope2 = TrustedScope("t1", "p1", self.auth.get_acl_epoch("t1"), "sec_ref", (RevisionBinding("r1", "s1", "gen-1"),))
        self.assertIsNone(self.cache.get(key, scope2))

    def test_tombstone_eviction(self):
        key = self.cache.put(self.scope, self.request, self.context)
        # item1's blob is "a"*64
        self.cache.mark_tombstone("t1", "a"*64)
        self.assertIsNone(self.cache.get(key, self.scope))
        # Entry should be completely gone
        self.assertNotIn(key, self.cache._entries)

    def test_tombstone_on_get(self):
        key = self.cache.put(self.scope, self.request, self.context)
        # manually add tombstone without deleting entry to test lazy get deletion
        self.cache._tombstones.add(("t1", "a"*64))
        self.assertIsNone(self.cache.get(key, self.scope))
        self.assertNotIn(key, self.cache._entries)

    def test_invalidate_tenant(self):
        key = self.cache.put(self.scope, self.request, self.context)
        self.cache.invalidate_tenant("t1")
        self.assertIsNone(self.cache.get(key, self.scope))
        self.assertNotIn(key, self.cache._entries)

if __name__ == '__main__':
    unittest.main()
