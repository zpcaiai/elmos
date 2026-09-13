import unittest
from elmos_ai_optimization.scope import HostAuthority, ScopeResolver, Grant
from elmos_ai_optimization.contracts import ScopeDeniedError, StaleVersionError, TrustedScope, RevisionBinding

class TestScope(unittest.TestCase):
    def setUp(self):
        self.auth = HostAuthority()
        self.resolver = ScopeResolver(self.auth)

    def test_host_authority_crud(self):
        self.auth.register_grant("t1", "repo1", ["p1"], "gen-1")
        grant = self.auth.get_grant("t1", "repo1")
        self.assertIsNotNone(grant)
        self.assertEqual(grant.tenant, "t1")
        self.assertEqual(grant.repository, "repo1")
        self.assertIn("p1", grant.allowed_principals)
        self.assertEqual(grant.current_generation, "gen-1")

        self.auth.create_session("t1", "p1", "tok")
        self.assertTrue(self.auth.is_session_valid("t1", "p1", "tok"))
        self.auth.revoke_session("t1", "p1", "tok")
        self.assertFalse(self.auth.is_session_valid("t1", "p1", "tok"))

        epoch = self.auth.bump_acl_epoch("t1")
        self.assertEqual(epoch, 2)
        self.assertEqual(self.auth.get_acl_epoch("t1"), 2)

    def test_resolve_happy_path(self):
        self.auth.register_grant("t1", "repo1", ["p1"], "gen-1")
        self.auth.create_session("t1", "p1", "tok")
        scope = self.resolver.resolve("t1", "p1", "tok", [("repo1", "snap1")])
        self.assertEqual(scope.tenant, "t1")
        self.assertEqual(scope.principal, "p1")
        self.assertEqual(len(scope.revisions), 1)
        self.assertEqual(scope.revisions[0].repository, "repo1")
        self.assertEqual(scope.revisions[0].snapshot, "snap1")
        self.assertEqual(scope.revisions[0].generation, "gen-1")

    def test_resolve_happy_path_with_gen(self):
        self.auth.register_grant("t1", "repo1", ["p1"], "gen-1")
        self.auth.create_session("t1", "p1", "tok")
        scope = self.resolver.resolve("t1", "p1", "tok", [("repo1", "snap1", "gen-1")])
        self.assertEqual(scope.revisions[0].generation, "gen-1")

    def test_resolve_revoked_session(self):
        self.auth.register_grant("t1", "repo1", ["p1"], "gen-1")
        with self.assertRaises(ScopeDeniedError):
            self.resolver.resolve("t1", "p1", "tok", [("repo1", "snap1")])

    def test_resolve_empty_revisions(self):
        self.auth.create_session("t1", "p1", "tok")
        with self.assertRaises(ScopeDeniedError):
            self.resolver.resolve("t1", "p1", "tok", [])

    def test_resolve_invalid_revision_tuple(self):
        self.auth.create_session("t1", "p1", "tok")
        with self.assertRaises(ScopeDeniedError):
            self.resolver.resolve("t1", "p1", "tok", [("repo1",)]) # type: ignore

    def test_resolve_duplicate_repo(self):
        self.auth.register_grant("t1", "repo1", ["p1"], "gen-1")
        self.auth.create_session("t1", "p1", "tok")
        with self.assertRaises(ScopeDeniedError):
            self.resolver.resolve("t1", "p1", "tok", [("repo1", "snap1"), ("repo1", "snap2")])

    def test_resolve_no_grant(self):
        self.auth.create_session("t1", "p1", "tok")
        with self.assertRaises(ScopeDeniedError):
            self.resolver.resolve("t1", "p1", "tok", [("repo1", "snap1")])

    def test_resolve_principal_not_authorized(self):
        self.auth.register_grant("t1", "repo1", ["p2"], "gen-1")
        self.auth.create_session("t1", "p1", "tok")
        with self.assertRaises(ScopeDeniedError):
            self.resolver.resolve("t1", "p1", "tok", [("repo1", "snap1")])

    def test_resolve_stale_generation(self):
        self.auth.register_grant("t1", "repo1", ["p1"], "gen-2")
        self.auth.create_session("t1", "p1", "tok")
        with self.assertRaises(StaleVersionError):
            self.resolver.resolve("t1", "p1", "tok", [("repo1", "snap1", "gen-1")])

    def test_revalidate_happy_path(self):
        self.auth.register_grant("t1", "repo1", ["p1"], "gen-1")
        self.auth.create_session("t1", "p1", "tok")
        scope = self.resolver.resolve("t1", "p1", "tok", [("repo1", "snap1")])
        self.resolver.revalidate(scope)

    def test_revalidate_stale_epoch(self):
        self.auth.register_grant("t1", "repo1", ["p1"], "gen-1")
        self.auth.create_session("t1", "p1", "tok")
        scope = self.resolver.resolve("t1", "p1", "tok", [("repo1", "snap1")])
        self.auth.bump_acl_epoch("t1")
        with self.assertRaises(ScopeDeniedError):
            self.resolver.revalidate(scope)

    def test_revalidate_permission_revoked_no_grant(self):
        self.auth.register_grant("t1", "repo1", ["p1"], "gen-1")
        self.auth.create_session("t1", "p1", "tok")
        scope = self.resolver.resolve("t1", "p1", "tok", [("repo1", "snap1")])
        # Simulate grant deletion by registering an empty one or directly modifying dict
        self.auth._grants.pop(("t1", "repo1"))
        with self.assertRaises(ScopeDeniedError):
            self.resolver.revalidate(scope)

    def test_revalidate_permission_revoked_principal(self):
        self.auth.register_grant("t1", "repo1", ["p1"], "gen-1")
        self.auth.create_session("t1", "p1", "tok")
        scope = self.resolver.resolve("t1", "p1", "tok", [("repo1", "snap1")])
        self.auth.register_grant("t1", "repo1", ["p2"], "gen-1") # Re-register without p1
        # Need to fix acl epoch so it doesn't fail on epoch check
        scope = TrustedScope(scope.tenant, scope.principal, self.auth.get_acl_epoch("t1"), scope.security_context_ref, scope.revisions)
        with self.assertRaises(ScopeDeniedError):
            self.resolver.revalidate(scope)

    def test_revalidate_stale_generation(self):
        self.auth.register_grant("t1", "repo1", ["p1"], "gen-1")
        self.auth.create_session("t1", "p1", "tok")
        scope = self.resolver.resolve("t1", "p1", "tok", [("repo1", "snap1")])
        self.auth.register_grant("t1", "repo1", ["p1"], "gen-2")
        scope = TrustedScope(scope.tenant, scope.principal, self.auth.get_acl_epoch("t1"), scope.security_context_ref, scope.revisions)
        with self.assertRaises(StaleVersionError):
            self.resolver.revalidate(scope)

if __name__ == '__main__':
    unittest.main()
