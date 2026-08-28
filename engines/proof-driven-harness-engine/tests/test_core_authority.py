from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from elmos_proof_harness.authority import Capability, EnvironmentAuthority, NetworkMode, ToolRequest
from elmos_proof_harness.contracts import SecurityContext
from elmos_proof_harness.errors import AuthorizationError
from elmos_proof_harness.policy import PolicyDecision, PolicyEngine, PolicyRule


NOW = datetime(2026, 8, 28, 6, 0, tzinfo=UTC)


class AuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.policy = PolicyEngine(
            [
                PolicyRule(
                    rule_id="allow-read",
                    decision=PolicyDecision.ALLOW,
                    capabilities=frozenset({"repository.read"}),
                    tools=frozenset({"reader"}),
                    operations=frozenset({"read"}),
                    tenants=frozenset({"tenant-a"}),
                    projects=frozenset({"project-a"}),
                    reason="repository inventory is approved",
                )
            ]
        )
        self.authority = EnvironmentAuthority(
            authority_id="authority-1",
            tenant_id="tenant-a",
            project_id="project-a",
            actor_id="actor-a",
            run_id="run-1",
            execution_epoch=2,
            fencing_generation=7,
            environment_id="environment-1",
            execution_source="VERIFIER",
            capabilities=(
                Capability(
                    name="repository.read",
                    tools=frozenset({"reader"}),
                    operations=frozenset({"read"}),
                    path_prefixes=(str(self.root),),
                    network_hosts=frozenset({"packages.example.test"}),
                ),
            ),
            read_paths=(str(self.root),),
            write_paths=(),
            network_mode=NetworkMode.ALLOWLIST,
            network_allowlist=frozenset({"packages.example.test"}),
            valid_from=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(minutes=10),
            policy_bundle_sha256=self.policy.revision,
        )
        self.context = SecurityContext(
            "tenant-a",
            "project-a",
            "actor-a",
            run_id="run-1",
            execution_epoch=2,
            fencing_generation=7,
            authority_revision=self.authority.revision,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_exact_bound_request_is_authorized(self) -> None:
        decision = self.authority.authorize(
            ToolRequest(
                context=self.context,
                capability="repository.read",
                tool="reader",
                operation="read",
                path=str(self.root / "source.py"),
            ),
            now=NOW,
            policy=self.policy,
        )
        self.assertEqual(self.authority.revision, decision.authority_revision)
        network_decision = self.authority.authorize(
            ToolRequest(
                context=self.context,
                capability="repository.read",
                tool="reader",
                operation="read",
                network_url="https://packages.example.test/package",
                resolved_ip="93.184.216.34",
            ),
            now=NOW,
            policy=self.policy,
        )
        self.assertEqual(self.policy.revision, network_decision.policy_revision)
        with self.assertRaises(AuthorizationError) as missing_policy:
            self.authority.authorize(
                ToolRequest(
                    context=self.context,
                    capability="repository.read",
                    tool="reader",
                    operation="read",
                    path=str(self.root / "source.py"),
                ),
                now=NOW,
            )
        self.assertEqual("POLICY_UNAVAILABLE", missing_policy.exception.code)
        unbound = SecurityContext(
            "tenant-a",
            "project-a",
            "actor-a",
            run_id="run-1",
            execution_epoch=2,
            fencing_generation=7,
        )
        with self.assertRaises(AuthorizationError) as missing_revision:
            self.authority.authorize(
                ToolRequest(
                    context=unbound,
                    capability="repository.read",
                    tool="reader",
                    operation="read",
                    path=str(self.root / "source.py"),
                ),
                now=NOW,
                policy=self.policy,
            )
        self.assertEqual("AUTHORITY_REVISION_STALE", missing_revision.exception.code)

    def test_stale_fence_path_escape_network_and_time_are_denied(self) -> None:
        stale = self.context.for_run("run-1", fencing_generation=6)
        with self.assertRaises(AuthorizationError) as raised:
            self.authority.authorize(
                ToolRequest(stale, "repository.read", "reader", "read", path=str(self.root / "a")),
                now=NOW,
            )
        self.assertEqual("STALE_FENCE", raised.exception.code)
        with self.assertRaises(AuthorizationError):
            self.authority.authorize(
                ToolRequest(self.context, "repository.read", "reader", "read", path=str(self.root / ".." / "escape")),
                now=NOW,
            )
        with self.assertRaises(AuthorizationError) as network:
            self.authority.authorize(
                ToolRequest(
                    self.context,
                    "repository.read",
                    "reader",
                    "read",
                    network_url="https://evil.example.test/package",
                ),
                now=NOW,
            )
        self.assertEqual("NETWORK_HOST_DENIED", network.exception.code)
        with self.assertRaises(AuthorizationError) as unpinned:
            self.authority.authorize(
                ToolRequest(
                    self.context,
                    "repository.read",
                    "reader",
                    "read",
                    network_url="https://packages.example.test/package",
                ),
                now=NOW,
            )
        self.assertEqual("NETWORK_IP_REQUIRED", unpinned.exception.code)
        with self.assertRaises(AuthorizationError) as expired:
            self.authority.authorize(
                ToolRequest(self.context, "repository.read", "reader", "read", path=str(self.root / "a")),
                now=NOW + timedelta(hours=1),
            )
        self.assertEqual("AUTHORITY_EXPIRED", expired.exception.code)


if __name__ == "__main__":
    unittest.main()
