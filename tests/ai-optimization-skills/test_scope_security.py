from __future__ import annotations

import unittest

from elmos_ai_optimization.contracts import (
    ScopeDeniedError,
    StaleVersionError,
    TrustedScope,
)
from elmos_ai_optimization.scope import HostAuthority, ScopeResolver


class ScopeSecurityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = HostAuthority()
        self.authority.register_grant("tenant-a", "repo-1", ["alice", "bob"], generation="gen-1")
        self.authority.register_grant("tenant-a", "repo-2", ["alice"], generation="gen-1")
        self.authority.register_grant("tenant-b", "repo-x", ["carol"], generation="gen-1")
        self.authority.create_session("tenant-a", "alice", "token-alice-1")
        self.resolver = ScopeResolver(self.authority)

    def test_valid_scope_resolution(self) -> None:
        scope = self.resolver.resolve(
            "tenant-a",
            "alice",
            "token-alice-1",
            [("repo-1", "snap-1"), ("repo-2", "snap-2")],
        )
        self.assertEqual(scope.tenant, "tenant-a")
        self.assertEqual(scope.principal, "alice")
        self.assertEqual(len(scope.revisions), 2)
        self.assertEqual(scope.revisions[0].repository, "repo-1")
        self.assertEqual(scope.revisions[0].generation, "gen-1")
        self.assertEqual(len(scope.digest), 64)

    def test_unknown_session_fails_closed(self) -> None:
        with self.assertRaises(ScopeDeniedError):
            self.resolver.resolve("tenant-a", "alice", "invalid-token", [("repo-1", "snap-1")])

    def test_ungranted_repository_fails_closed(self) -> None:
        with self.assertRaises(ScopeDeniedError):
            self.resolver.resolve("tenant-a", "alice", "token-alice-1", [("repo-unknown", "snap-1")])

    def test_unauthorized_principal_fails_closed(self) -> None:
        self.authority.create_session("tenant-a", "bob", "token-bob-1")
        with self.assertRaises(ScopeDeniedError):
            self.resolver.resolve("tenant-a", "bob", "token-bob-1", [("repo-2", "snap-1")])

    def test_duplicate_repository_rejected(self) -> None:
        with self.assertRaises(ScopeDeniedError):
            self.resolver.resolve(
                "tenant-a",
                "alice",
                "token-alice-1",
                [("repo-1", "snap-1"), ("repo-1", "snap-2")],
            )

    def test_acl_revocation_invalidates_scope(self) -> None:
        scope = self.resolver.resolve("tenant-a", "alice", "token-alice-1", [("repo-1", "snap-1")])
        self.resolver.revalidate(scope)

        # Bump ACL epoch in host authority
        self.authority.bump_acl_epoch("tenant-a")
        with self.assertRaises(ScopeDeniedError):
            self.resolver.revalidate(scope)

    def test_stale_generation_rejected(self) -> None:
        with self.assertRaises(StaleVersionError):
            self.resolver.resolve(
                "tenant-a",
                "alice",
                "token-alice-1",
                [("repo-1", "snap-1", "gen-stale")],
            )


if __name__ == "__main__":
    unittest.main()
