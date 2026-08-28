from __future__ import annotations

import unittest
from elmos_proof_harness.delta import (
    DeltaInvocation,
    DeltaSkillRuntime,
    ResultStatus,
)


class DeltaSkillsImplementationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = DeltaSkillRuntime()

    def _invoke(self, skill_name: str, payload: dict) -> dict:
        invocation = DeltaInvocation(
            tenant_id="tenant-alpha",
            goal_id="goal-001",
            run_id="run-9999",
            execution_epoch=1,
            step_id="step-001",
            invocation_id="inv-12345",
            revision_set_id="revset-001",
            extension_skill=skill_name,
            payload=payload,
        )
        result = self.runtime.execute(invocation)
        self.assertEqual(result.status, ResultStatus.COMMITTED)
        return result.to_wire()

    def test_01_tool_result_interception_commit(self) -> None:
        wire = self._invoke(
            "elmos-tool-result-interception-commit",
            {
                "rawResult": {
                    "identity": {
                        "invocationId": "inv-12345",
                        "callId": "call-1",
                        "executionPlanHash": "a" * 64,
                        "environmentId": "env-prod",
                        "authoritySnapshotId": "auth-1",
                    },
                    "ok": True,
                    "content": {"result": "success"},
                },
                "attempt": 1,
            },
        )
        self.assertEqual(wire["status"], "COMMITTED")

    def test_02_step_finalized_execution_plan(self) -> None:
        wire = self._invoke(
            "elmos-step-finalized-execution-plan",
            {
                "modelSnapshot": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "revision": "2024-08-06",
                },
                "tools": ["read_file", "run_command"],
                "environmentSnapshotId": "env-snap-1",
                "authoritySnapshotId": "auth-snap-1",
                "toolMode": "NATIVE",
                "planId": "plan-101",
            },
        )
        self.assertEqual(wire["status"], "COMMITTED")

    def test_03_lossless_permission_replay(self) -> None:
        wire = self._invoke(
            "elmos-lossless-permission-replay",
            {
                "profileId": "profile-001",
                "canonicalProfile": {
                    "filesystemRoots": ["/workspace"],
                    "network": "deny",
                    "mutable": False,
                },
                "provider": "codex",
            },
        )
        self.assertEqual(wire["status"], "COMMITTED")

    def test_04_invocation_scoped_capability_lease(self) -> None:
        wire = self._invoke(
            "elmos-invocation-scoped-capability-lease",
            {
                "leaseId": "lease-777",
                "environmentId": "env-1",
                "authoritySnapshotId": "auth-1",
                "capabilities": ["fs.read", "cmd.exec"],
                "delegationAllowed": False,
            },
        )
        self.assertEqual(wire["status"], "COMMITTED")

    def test_05_host_minted_security_context(self) -> None:
        wire = self._invoke(
            "elmos-host-minted-security-context",
            {
                "eligible": True,
                "accountStable": True,
                "bindings": {
                    "pluginId": "plugin-1",
                    "toolId": "tool-1",
                    "accountId": "acc-1",
                    "tenantId": "tenant-alpha",
                    "environmentId": "env-1",
                    "invocationId": "inv-12345",
                    "policyVersion": "v1.0",
                },
                "entitlements": {"role": "admin"},
            },
        )
        self.assertEqual(wire["status"], "COMMITTED")

    def test_06_environment_attachment_authority(self) -> None:
        wire = self._invoke(
            "elmos-environment-attachment-authority",
            {
                "ownerSnapshotId": "owner-snap",
                "ownerPermissions": ["read", "write"],
                "ownerId": "user-1",
                "parentSnapshotId": "parent-snap",
                "parentPermissions": ["read"],
                "parentOwnerId": "root-user",
                "environmentId": "env-001",
                "policyPermissions": ["read"],
                "snapshotId": "snap-final",
            },
        )
        self.assertEqual(wire["status"], "COMMITTED")

    def test_07_executor_generation_fencing(self) -> None:
        wire = self._invoke(
            "elmos-executor-generation-fencing",
            {
                "generation": 1,
                "connectionEpoch": 1,
                "environmentId": "env-01",
                "executorIdentity": "exec-01",
                "action": "reconnect",
            },
        )
        self.assertEqual(wire["status"], "COMMITTED")

    def test_08_workspace_ownership_lease(self) -> None:
        wire = self._invoke(
            "elmos-workspace-ownership-lease",
            {
                "workspaceId": "ws-100",
                "ownerExecutionId": "exec-100",
                "generation": 1,
                "repositoryId": "repo-elmos",
                "baseRevision": "rev-001",
                "writeScopes": ["src/"],
                "action": "bind",
            },
        )
        self.assertEqual(wire["status"], "COMMITTED")

    def test_09_harness_transport_version_negotiation(self) -> None:
        wire = self._invoke(
            "elmos-harness-transport-version-negotiation",
            {
                "provider": "elmos",
                "version": "3.1.0",
                "features": ["grpc", "json-schema"],
                "transport": "REMOTE_GATEWAY",
                "requiredFeatures": ["grpc"],
            },
        )
        self.assertEqual(wire["status"], "COMMITTED")

    def test_10_skill_trust_domain_provenance(self) -> None:
        wire = self._invoke(
            "elmos-skill-trust-domain-provenance",
            {
                "provenance": {
                    "skillId": "skill-001",
                    "publisher": "elmos-team",
                    "origin": "repo",
                    "canonicalUri": "https://elmos.ai/skills/001",
                    "packageDigest": "a" * 64,
                    "trustDomain": "REPOSITORY",
                    "installScope": "system",
                    "verified": True,
                    "signature": "sig-12345",
                }
            },
        )
        self.assertEqual(wire["status"], "COMMITTED")

    def test_11_registered_durable_plugin_events(self) -> None:
        wire = self._invoke(
            "elmos-registered-durable-plugin-events",
            {
                "registration": {
                    "type": "event.tool.executed",
                    "owner": "system",
                    "schemaVersion": 1,
                    "semantics": "REQUIRED_STATE",
                    "validator": "schema-v1",
                    "upgrader": "none",
                    "projections": ["audit_log"],
                    "compatibility": "STRICT",
                }
            },
        )
        self.assertEqual(wire["status"], "COMMITTED")

    def test_12_typed_external_ingress(self) -> None:
        wire = self._invoke(
            "elmos-typed-external-ingress",
            {
                "ingress": {
                    "ingressId": "ing-01",
                    "kind": "EXTERNAL_EVENT",
                    "producerExecutionId": "exec-producer",
                    "eventId": "evt-100",
                    "causationId": "cause-100",
                    "correlationId": "corr-100",
                    "content": "payload data",
                },
                "pendingCalls": [],
            },
        )
        self.assertEqual(wire["status"], "COMMITTED")

    def test_13_subagent_model_execution_spec(self) -> None:
        wire = self._invoke(
            "elmos-subagent-model-execution-spec",
            {
                "provider": "anthropic",
                "model": "claude-3-5-sonnet",
                "reasoningEffort": "medium",
                "maxOutputTokens": 4096,
                "parentExecutionId": "parent-exec-01",
                "environmentId": "env-001",
                "authoritySnapshotId": "auth-001",
                "budgetReservationId": "budget-001",
                "parentAuthority": ["fs.read"],
                "childAuthority": ["fs.read"],
                "parentTools": ["read_file"],
                "childTools": ["read_file"],
            },
        )
        self.assertEqual(wire["status"], "COMMITTED")

    def test_unknown_skill_fails_closed(self) -> None:
        invocation = DeltaInvocation(
            tenant_id="tenant-err",
            goal_id="goal-err",
            run_id="run-err",
            execution_epoch=1,
            step_id="step-err",
            invocation_id="inv-err",
            revision_set_id="rev-err",
            extension_skill="non-existent-skill",
            payload={},
        )
        result = self.runtime.execute(invocation)
        self.assertEqual(result.status, ResultStatus.UNSUPPORTED)


if __name__ == "__main__":
    unittest.main()
