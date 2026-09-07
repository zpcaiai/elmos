from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from elmos_proof_harness.assurance_policies import (
    HostSecurityContextSigner,
    ManagedWorktreeRegistry,
    PrivilegedPathContract,
    PrivilegedPathPolicy,
    SkillTrustDomainPolicy,
)
from elmos_proof_harness.errors import IntegrityError, ValidationError


class AssurancePolicyTests(unittest.TestCase):
    def test_security_context_signature_is_restart_stable_and_key_bound(self) -> None:
        payload = {
            "contextId": "ctx-1",
            "bindings": {"tenantId": "tenant-1"},
            "entitlements": {"role": "operator"},
        }
        first = HostSecurityContextSigner(
            b"a" * 32, key_id="key-2026-08", issuer="host"
        )
        reconstructed = HostSecurityContextSigner(
            b"a" * 32,
            key_id="key-2026-08",
            issuer="host",
        )
        other = HostSecurityContextSigner(
            b"b" * 32, key_id="key-2026-09", issuer="host"
        )

        signature = first.sign(payload)
        self.assertTrue(reconstructed.verify(payload, signature))
        self.assertFalse(other.verify(payload, signature))
        self.assertFalse(
            reconstructed.verify(payload | {"contextId": "ctx-2"}, signature)
        )

    def test_privileged_paths_are_exact_and_default_deny(self) -> None:
        policy = PrivilegedPathPolicy(
            (
                PrivilegedPathContract(
                    "/workspace/read",
                    "FILESYSTEM",
                    allowed_arguments=("stat", "read"),
                ),
                PrivilegedPathContract(
                    "/sandbox/exec",
                    "SANDBOX",
                    mutable=True,
                    allowed_arguments=("compile",),
                ),
            )
        )
        policy.validate_entitlements(
            {
                "privilegedPaths": [
                    {
                        "path": "/workspace/read",
                        "kind": "FILESYSTEM",
                        "remote": False,
                        "mutable": False,
                        "arguments": ["read"],
                    }
                ]
            }
        )
        denied = (
            {
                "path": "/undeclared",
                "kind": "FILESYSTEM",
                "remote": False,
                "mutable": False,
                "arguments": [],
            },
            {
                "path": "/workspace/read",
                "kind": "FILESYSTEM",
                "remote": True,
                "mutable": False,
                "arguments": ["read"],
            },
            {
                "path": "/workspace/read",
                "kind": "FILESYSTEM",
                "remote": False,
                "mutable": False,
                "arguments": ["write"],
            },
        )
        for request in denied:
            with self.subTest(request=request), self.assertRaises(ValidationError):
                policy.validate_entitlements({"privilegedPaths": [request]})

    def test_trust_domains_bind_roots_and_publishers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            enterprise = base / "enterprise"
            repository.mkdir()
            enterprise.mkdir()
            alias = base / "repository-alias"
            alias.symlink_to(repository, target_is_directory=True)
            with self.assertRaises(ValueError):
                SkillTrustDomainPolicy(
                    {"REPOSITORY": alias},
                    publishers={"REPOSITORY": ("repo-owner",)},
                )
            policy = SkillTrustDomainPolicy(
                {"REPOSITORY": repository, "ENTERPRISE": enterprise},
                publishers={
                    "REPOSITORY": ("repo-owner",),
                    "ENTERPRISE": ("enterprise-publisher",),
                },
            )
            self.assertEqual(
                policy.authorize(domain="REPOSITORY", publisher="repo-owner"),
                repository.resolve(),
            )
            with self.assertRaises(ValidationError):
                policy.authorize(
                    domain="ENTERPRISE",
                    publisher="repo-owner",
                )
            envelope = SkillTrustDomainPolicy.signature_envelope(
                skill_id="skill-1",
                publisher="enterprise-publisher",
                origin="managed",
                canonical_uri="file:///enterprise/skill-1",
                package_digest="sha256:" + "a" * 64,
                trust_domain="ENTERPRISE",
                install_scope="tenant:t-1",
                authorization_semantics=("filesystem:read",),
            )
            self.assertIn(b"enterprise-publisher", envelope)
            self.assertIn(b"tenant:t-1", envelope)

    def test_managed_worktree_registry_rejects_primary_nested_and_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            checkout = base / "linked"
            checkout.mkdir()
            git_dir = base / "common" / "worktrees" / "linked"
            git_dir.mkdir(parents=True)
            (checkout / ".git").write_text(
                f"gitdir: {git_dir}\n",
                encoding="utf-8",
            )
            identity = ManagedWorktreeRegistry.discover(
                workspace_id="ws-1",
                repository_id="repo-1",
                base_revision="a" * 40,
                checkout_path=checkout,
            )
            registry = ManagedWorktreeRegistry((identity,))
            self.assertEqual(registry.require("ws-1"), identity)

            nested = checkout / "nested"
            nested.mkdir()
            nested_git_dir = base / "common" / "worktrees" / "nested"
            nested_git_dir.mkdir(parents=True)
            (nested / ".git").write_text(
                f"gitdir: {nested_git_dir}\n",
                encoding="utf-8",
            )
            nested_identity = ManagedWorktreeRegistry.discover(
                workspace_id="ws-2",
                repository_id="repo-1",
                base_revision="a" * 40,
                checkout_path=nested,
            )
            with self.assertRaises(ValueError):
                ManagedWorktreeRegistry((identity, nested_identity))

            primary = base / "primary"
            (primary / ".git").mkdir(parents=True)
            with self.assertRaises(ValidationError):
                ManagedWorktreeRegistry.discover(
                    workspace_id="ws-primary",
                    repository_id="repo-1",
                    base_revision="a" * 40,
                    checkout_path=primary,
                )

            moved = base / "moved"
            checkout.rename(moved)
            with self.assertRaises(IntegrityError):
                registry.require("ws-1")


if __name__ == "__main__":
    unittest.main()
