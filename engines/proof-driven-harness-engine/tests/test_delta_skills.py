from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import tempfile
from typing import Mapping, cast
import unittest
from unittest import mock

from elmos_proof_harness.assurance_policies import (
    HostSecurityContextSigner,
    ManagedWorktreeRegistry,
    PrivilegedPathPolicy,
    SkillTrustDomainPolicy,
)
from elmos_proof_harness.canonical import digest_bytes, digest_object
from elmos_proof_harness.contracts import SecurityContext
from elmos_proof_harness.delta import (
    AuthoritySnapshot,
    BaseSkillOriginBinding,
    CallIdentity,
    CapabilityLeaseBroker,
    CommitState,
    ContractError,
    DeltaInvocation,
    DeltaResult,
    DeltaSkillRuntime,
    DurableEventRegistry,
    EnvironmentSettingsBinding,
    EventRegistration,
    ExecutionPlan,
    IngressRouter,
    ModelSnapshot,
    PermissionProfile,
    PendingToolCallBinding,
    ResultLifecycleCoordinator,
    ResultStatus,
    RuntimeAssuranceAuthority,
    SecurityContextBroker,
    StepExecutionPlanStore,
    SubagentBudgetReservation,
    ToolResult,
    TypedIngress,
    WorkspaceAuthority,
    WorkspaceLease,
)


class DeltaSkillsImplementationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.skill_root = Path(self.temporary.name)
        self.skill_file = self.skill_root / "skills" / "demo" / "SKILL.md"
        self.skill_file.parent.mkdir(parents=True)
        self.skill_file.write_bytes(b"---\nname: demo\n---\n")
        self.authority = digest_bytes(b"authority-v1", domain="authority-revision")
        self.context = SecurityContext(
            "tenant-alpha",
            "project-alpha",
            "actor-alpha",
            "run-9999",
            1,
            authority_revision=self.authority,
        )
        self.host_security_eligible = True
        self.plan_hash = "sha256:" + "a" * 64
        self.handler_digest = "sha256:" + "d" * 64
        self.settings_authority = {"network": "deny", "permissions": ["read"]}
        self.settings_digest = digest_object(
            self.settings_authority,
            domain="delta-environment-settings-authority",
        )
        permission = PermissionProfile(("/workspace",), "deny", False, "/workspace")

        def redact(result: ToolResult) -> ToolResult:
            return ToolResult(result.identity, result.ok, {"redacted": True})

        self.signer = HostSecurityContextSigner(
            b"test-host-security-context-key-0001",
            key_id="test-key",
            issuer="test-host",
        )
        worktree_registry = mock.Mock(spec=ManagedWorktreeRegistry)
        workspace_identities = {
            "ws-100": ("repo-elmos", "rev-001"),
            "ws-bad": ("repo", "rev"),
            "ws-handoff": ("repo", "rev"),
        }

        def live_workspace(workspace_id: str) -> SimpleNamespace:
            repository_id, base_revision = workspace_identities[workspace_id]
            return SimpleNamespace(
                repository_id=repository_id,
                base_revision=base_revision,
            )

        worktree_registry.require.side_effect = live_workspace

        self.runtime = DeltaSkillRuntime(
            permission_profiles={("codex", "1.0.0"): {"sandbox-locked": permission}},
            authorized_producers={("tenant-alpha", "project-alpha"): {"exec-producer"}},
            allowed_subagent_models={("anthropic", "claude-3-5-sonnet")},
            skill_trust_policy=SkillTrustDomainPolicy(
                {"REPOSITORY": self.skill_root},
                publishers={"REPOSITORY": {"elmos-team", "publisher"}},
            ),
            host_security_signer=self.signer,
            privileged_path_policy=PrivilegedPathPolicy(),
            managed_worktree_registry=worktree_registry,
            interceptors={"redact": ("1.0.0", redact)},
            authority_provider=self.authority_provider,
        )

    def authority_provider(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
    ) -> RuntimeAssuranceAuthority:
        owner = AuthoritySnapshot(
            self.authority,
            frozenset({"read", "write"}),
            "user-1",
            "env-001",
            "profile-v1",
            "b" * 64,
        )
        parent = AuthoritySnapshot(
            "sha256:" + "c" * 64,
            frozenset({"read"}),
            "root-user",
            "env-001",
            "profile-v1",
            "c" * 64,
        )
        receipt_ref = "base-origin-receipt"
        assert invocation.extension_skill is not None
        origin = BaseSkillOriginBinding.bind_host_receipt(
            skill_id="ELMOS-V3-007",
            skill_name="elmos-harness-runtime-kernel",
            owner_kernel="K7",
            execution_id="exec-01",
            tenant_id="tenant-alpha",
            project_id="project-alpha",
            actor_id="actor-alpha",
            run_id="run-9999",
            execution_epoch=1,
            fencing_generation=context.fencing_generation,
            authority_revision=self.authority,
            revision_set_id="revset-001",
            step_id="step-001",
            invocation_id=invocation.invocation_id,
            extension_skill=invocation.extension_skill,
            environment_id="env-1",
            receipt_ref=receipt_ref,
            receipt_state="EXECUTING",
        )
        return RuntimeAssuranceAuthority(
            tenant_id="tenant-alpha",
            project_id="project-alpha",
            actor_id="actor-alpha",
            run_id="run-9999",
            execution_epoch=1,
            fencing_generation=context.fencing_generation,
            authority_revision=self.authority,
            revision_set_id="revset-001",
            step_id="step-001",
            execution_id="exec-01",
            originating_base_skill=origin,
            environment_ids=frozenset(
                {"env", "env-1", "env-01", "env-001", "env-prod", "env-x"}
            ),
            environment_snapshot_ids=frozenset({"env-snap-1", "env"}),
            permission_profile_versions=frozenset({"codex@1.0.0", "profile-v1"}),
            capabilities=frozenset(
                {"fs.read", "cmd.exec", "event.register:event.tool.executed"}
            ),
            tools=frozenset({"read_file", "run_command", "read"}),
            tool_modes=frozenset({"NATIVE"}),
            selected_models=frozenset(
                {
                    ModelSnapshot("openai", "gpt-5", "2026-08-30"),
                    ModelSnapshot("p", "m", "r"),
                }
            ),
            originating_plan_hashes=frozenset({self.plan_hash}),
            security_eligible=self.host_security_eligible,
            account_stable=True,
            security_bindings=cast(
                Mapping[str, str], self.security_payload()["bindings"]
            ),
            entitlements={"role": "operator"},
            owner_authority=owner,
            parent_authority_snapshot=parent,
            policy_permissions=frozenset({"read"}),
            authority_result_snapshot_id="sha256:" + "e" * 64,
            authorized_producers=frozenset({"exec-producer"}),
            pending_calls=frozenset({"call-1"}),
            verified_evidence_refs=frozenset({"probe-ref", receipt_ref}),
            executor_bindings=frozenset({("env-01", "exec-01"), ("env-x", "exec-x")}),
            event_registrations=(
                EventRegistration(
                    "event.tool.executed",
                    "system",
                    1,
                    "REQUIRED_STATE",
                    "elmos.object.v1",
                    "none",
                    ("audit_log",),
                    "STRICT",
                ),
                EventRegistration(
                    "event.unknown",
                    "system",
                    1,
                    "REQUIRED_STATE",
                    "archive.claimed.validator",
                    "none",
                    (),
                    "STRICT",
                ),
            ),
            parent_execution_id="parent-exec-01",
            parent_authority=frozenset({"fs.read"}),
            parent_tools=frozenset({"read_file"}),
            parent_max_output_tokens=8192,
            budget_reservations=(("budget-001", 4096),),
            allowed_subagent_models=frozenset({("anthropic", "claude-3-5-sonnet")}),
            delegation_allowed_invocations=frozenset(),
            workspace_authorities=(
                WorkspaceAuthority(
                    "ws-100",
                    "repo-elmos",
                    "rev-001",
                    ("src",),
                    frozenset({"exec-100"}),
                ),
                WorkspaceAuthority(
                    "ws-bad",
                    "repo",
                    "rev",
                    ("src",),
                    frozenset({"exec"}),
                ),
                WorkspaceAuthority(
                    "ws-handoff",
                    "repo",
                    "rev",
                    ("src",),
                    frozenset({"old", "new"}),
                ),
            ),
            pending_call_bindings=(
                PendingToolCallBinding(
                    "call-1",
                    1,
                    "inv-12345",
                    self.plan_hash,
                    "env-prod",
                    "read_file",
                    self.authority,
                ),
            ),
            tool_contracts={
                "read_file": {"inputSchema": {"type": "object"}},
                "run_command": {"inputSchema": {"type": "object"}},
            },
            handler_digests={
                "read_file": self.handler_digest,
                "run_command": self.handler_digest,
            },
            subagent_budget_reservations=(
                SubagentBudgetReservation(
                    "budget-001",
                    "inv-12345",
                    "parent-exec-01",
                    "env-001",
                    self.authority,
                    "anthropic",
                    "claude-3-5-sonnet",
                    "medium",
                    frozenset({"fs.read"}),
                    frozenset({"read_file"}),
                    4096,
                    "5.0",
                    datetime.now(UTC) + timedelta(hours=1),
                    self.plan_hash,
                ),
            ),
            environment_settings_bindings=(
                EnvironmentSettingsBinding(
                    "server-001",
                    "env-001",
                    self.settings_authority,
                    self.settings_digest,
                ),
            ),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def request(
        self,
        skill: str,
        payload: dict[str, object],
        *,
        invocation_id: str = "inv-12345",
    ) -> DeltaInvocation:
        return DeltaInvocation(
            "tenant-alpha",
            "goal-001",
            "run-9999",
            1,
            "step-001",
            invocation_id,
            "revset-001",
            skill,
            payload,
        )

    def execute(
        self,
        skill: str,
        payload: dict[str, object],
        *,
        context: SecurityContext | None = None,
    ) -> DeltaResult:
        return self.runtime.execute(
            self.request(skill, payload),
            context=self.context if context is None else context,
        )

    def committed(self, skill: str, payload: dict[str, object]) -> None:
        result = self.execute(skill, payload)
        self.assertEqual(result.status, ResultStatus.COMMITTED, result.message)
        self.assertEqual(len(result.evidence_refs), 1)
        recorded = self.runtime.read_evidence(self.context, result.evidence_refs[0])
        self.assertEqual(recorded["status"], ResultStatus.COMMITTED.value)
        self.assertEqual(recorded["skillName"], skill)

    def tool_payload(
        self, *, ok: object = True, call_id: str = "call-1"
    ) -> dict[str, object]:
        return {
            "rawResult": {
                "identity": {
                    "invocationId": "inv-12345",
                    "callId": call_id,
                    "executionPlanHash": self.plan_hash,
                    "environmentId": "env-prod",
                    "authoritySnapshotId": self.authority,
                },
                "ok": ok,
                "content": {"result": "success"},
            },
            "attempt": 1,
            "interceptorIds": ["redact"],
        }

    def security_payload(self, *, eligible: bool = True) -> dict[str, object]:
        return {
            "eligible": eligible,
            "accountStable": True,
            "bindings": {
                "pluginId": "plugin-1",
                "toolId": "tool-1",
                "accountId": "acc-1",
                "tenantId": "tenant-alpha",
                "environmentId": "env-1",
                "invocationId": "inv-12345",
                "policyVersion": self.authority,
            },
            "entitlements": {"role": "operator"},
        }

    def ingress_payload(
        self,
        *,
        producer: str = "exec-producer",
        content: str = "payload",
        kind: str = "EXTERNAL_EVENT",
    ) -> dict[str, object]:
        ingress = {
            "ingressId": "ing-01",
            "kind": kind,
            "producerExecutionId": producer,
            "eventId": "evt-100",
            "causationId": "cause-100",
            "correlationId": "corr-100",
            "content": content,
        }
        return {"action": "ingest", "ingress": ingress}

    def subagent_payload(self) -> dict[str, object]:
        return {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet",
            "reasoningEffort": "medium",
            "maxOutputTokens": 4096,
            "parentExecutionId": "parent-exec-01",
            "environmentId": "env-001",
            "parentEnvironmentId": "env-001",
            "authoritySnapshotId": self.authority,
            "budgetReservationId": "budget-001",
            "parentAuthority": ["fs.read"],
            "childAuthority": ["fs.read"],
            "parentTools": ["read_file"],
            "childTools": ["read_file"],
            "parentMaxOutputTokens": 8192,
            "toolPlanHash": self.plan_hash,
            "costBudget": "2.5",
            "wallClockDeadline": (
                datetime.now(UTC) + timedelta(minutes=30)
            ).isoformat(),
        }

    def test_01_tool_result_interception_commit(self) -> None:
        self.committed("elmos-tool-result-interception-commit", self.tool_payload())

    def test_02_step_finalized_execution_plan(self) -> None:
        self.committed(
            "elmos-step-finalized-execution-plan",
            {
                "modelSnapshot": {
                    "provider": "openai",
                    "model": "gpt-5",
                    "revision": "2026-08-30",
                },
                "tools": ["read_file", "run_command"],
                "toolContracts": {
                    "read_file": {"inputSchema": {"type": "object"}},
                    "run_command": {"inputSchema": {"type": "object"}},
                },
                "handlerDigests": {
                    "read_file": self.handler_digest,
                    "run_command": self.handler_digest,
                },
                "environmentSnapshotId": "env-snap-1",
                "authoritySnapshotId": self.authority,
                "toolMode": "NATIVE",
                "planId": "plan-101",
            },
        )

    def test_03_permission_adapter_exact_replay(self) -> None:
        self.committed(
            "elmos-lossless-permission-replay",
            {
                "profileId": "profile-001",
                "canonicalProfile": {
                    "filesystemRoots": ["/workspace"],
                    "network": "deny",
                    "mutable": False,
                    "workingDirectory": "/workspace",
                },
                "provider": "codex",
                "version": "1.0.0",
            },
        )

    def test_04_invocation_scoped_capability_lease(self) -> None:
        self.committed(
            "elmos-invocation-scoped-capability-lease",
            {
                "leaseId": "lease-777",
                "environmentId": "env-1",
                "authoritySnapshotId": self.authority,
                "capabilities": ["fs.read", "cmd.exec"],
                "delegationAllowed": False,
                "expiresAt": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            },
        )

    def test_05_host_minted_security_context(self) -> None:
        self.committed("elmos-host-minted-security-context", self.security_payload())

    def test_06_environment_attachment_authority(self) -> None:
        self.committed(
            "elmos-environment-attachment-authority",
            {
                "action": "attach",
                "serverId": "server-001",
                "settingsAuthority": self.settings_authority,
                "settingsDigest": self.settings_digest,
                "expectedSnapshotId": None,
                "expectedGeneration": 0,
                "ownerSnapshotId": self.authority,
                "ownerPermissions": ["read", "write"],
                "ownerId": "user-1",
                "parentSnapshotId": "sha256:" + "c" * 64,
                "parentPermissions": ["read"],
                "parentOwnerId": "root-user",
                "environmentId": "env-001",
                "permissionProfileVersion": "profile-v1",
                "ownerEffectivePolicyHash": "b" * 64,
                "parentEffectivePolicyHash": "c" * 64,
                "policyPermissions": ["read"],
                "snapshotId": "sha256:" + "e" * 64,
            },
        )

    def test_07_executor_generation_fencing(self) -> None:
        self.committed(
            "elmos-executor-generation-fencing",
            {
                "generation": 1,
                "connectionEpoch": 1,
                "environmentId": "env-01",
                "executorIdentity": "exec-01",
                "action": "activate",
                "liveProbeEvidenceRef": "probe-ref",
            },
        )
        self.committed(
            "elmos-executor-generation-fencing",
            {
                "generation": 1,
                "connectionEpoch": 1,
                "environmentId": "env-01",
                "executorIdentity": "exec-01",
                "action": "reconnect",
            },
        )

    def test_08_workspace_ownership_lease(self) -> None:
        self.committed(
            "elmos-workspace-ownership-lease",
            {
                "workspaceId": "ws-100",
                "ownerExecutionId": "exec-100",
                "generation": 1,
                "repositoryId": "repo-elmos",
                "baseRevision": "rev-001",
                "writeScopes": ["src"],
                "action": "bind",
            },
        )

    def test_09_protocol_adapter_negotiation(self) -> None:
        self.committed(
            "elmos-harness-transport-version-negotiation",
            {
                "provider": "openai-codex",
                "version": "main@2026-08-28",
                "requiredVersion": "main@2026-08-28",
                "requiredFeatures": ["typedToolResult", "resultInterception"],
            },
        )

    def test_10_skill_trust_domain_provenance(self) -> None:
        self.committed(
            "elmos-skill-trust-domain-provenance",
            {
                "skillPath": "skills/demo/SKILL.md",
                "provenance": {
                    "skillId": "skill-001",
                    "publisher": "elmos-team",
                    "origin": "repository",
                    "canonicalUri": self.skill_file.resolve().as_uri(),
                    "packageDigest": digest_bytes(
                        self.skill_file.read_bytes(), domain="delta-skill-package"
                    ),
                    "trustDomain": "REPOSITORY",
                    "installScope": "project",
                    "authorizationSemantics": ["guidance-only"],
                    "verified": False,
                },
            },
        )

    def test_11_registered_durable_plugin_events(self) -> None:
        self.committed(
            "elmos-registered-durable-plugin-events",
            {
                "action": "register",
                "registration": {
                    "type": "event.tool.executed",
                    "owner": "system",
                    "schemaVersion": 1,
                    "semantics": "REQUIRED_STATE",
                    "validator": "elmos.object.v1",
                    "upgrader": "none",
                    "projections": ["audit_log"],
                    "compatibility": "STRICT",
                },
            },
        )

    def test_12_typed_external_ingress(self) -> None:
        self.committed("elmos-typed-external-ingress", self.ingress_payload())

    def test_13_subagent_model_execution_spec(self) -> None:
        self.committed("elmos-subagent-model-execution-spec", self.subagent_payload())

    def test_14_unknown_skill_fails_closed(self) -> None:
        result = self.runtime.execute(
            self.request("non-existent-skill", {}), context=self.context
        )
        self.assertEqual(result.status, ResultStatus.UNSUPPORTED)

    def test_15_trusted_context_is_mandatory(self) -> None:
        result = self.runtime.execute(
            self.request("elmos-tool-result-interception-commit", self.tool_payload())
        )
        self.assertEqual(result.status, ResultStatus.DENIED)

    def test_16_tenant_and_epoch_are_bound(self) -> None:
        wrong = SecurityContext(
            "tenant-other",
            "project-alpha",
            "actor",
            "run-9999",
            1,
            authority_revision=self.authority,
        )
        self.assertEqual(
            self.runtime.execute(
                self.request(
                    "elmos-tool-result-interception-commit", self.tool_payload()
                ),
                context=wrong,
            ).status,
            ResultStatus.DENIED,
        )
        stale = SecurityContext(
            "tenant-alpha",
            "project-alpha",
            "actor",
            "run-9999",
            2,
            authority_revision=self.authority,
        )
        self.assertEqual(
            self.runtime.execute(
                self.request(
                    "elmos-tool-result-interception-commit", self.tool_payload()
                ),
                context=stale,
            ).status,
            ResultStatus.DENIED,
        )

    def test_17_wire_types_are_not_coerced(self) -> None:
        wire = self.request(
            "elmos-tool-result-interception-commit", self.tool_payload()
        ).to_wire()
        wire["executionEpoch"] = "1"
        self.assertEqual(
            self.runtime.execute(wire, context=self.context).status,
            ResultStatus.UNKNOWN,
        )
        self.assertEqual(
            self.execute(
                "elmos-tool-result-interception-commit", self.tool_payload(ok="yes")
            ).status,
            ResultStatus.DENIED,
        )

    def test_18_unknown_payload_fields_are_denied(self) -> None:
        payload = self.tool_payload()
        payload["shell"] = "unauthorized"
        self.assertEqual(
            self.execute("elmos-tool-result-interception-commit", payload).status,
            ResultStatus.DENIED,
        )

    def test_19_permission_adapter_missing_is_unsupported(self) -> None:
        result = self.execute(
            "elmos-lossless-permission-replay",
            {
                "profileId": "profile-1",
                "canonicalProfile": {
                    "filesystemRoots": ["/workspace"],
                    "network": "deny",
                    "mutable": False,
                    "workingDirectory": "/workspace",
                },
                "provider": "unknown",
                "version": "1",
            },
        )
        self.assertEqual(result.status, ResultStatus.UNSUPPORTED)

    def test_20_permission_adapter_lossy_is_unsupported(self) -> None:
        result = self.execute(
            "elmos-lossless-permission-replay",
            {
                "profileId": "profile-1",
                "canonicalProfile": {
                    "filesystemRoots": ["/workspace"],
                    "network": "deny",
                    "mutable": True,
                    "workingDirectory": "/workspace",
                },
                "provider": "codex",
                "version": "1.0.0",
            },
        )
        self.assertEqual(result.status, ResultStatus.UNSUPPORTED)

    def test_21_capability_lease_requires_short_expiry(self) -> None:
        base = {
            "leaseId": "lease-x",
            "environmentId": "env",
            "authoritySnapshotId": self.authority,
            "capabilities": ["fs.read"],
            "delegationAllowed": False,
        }
        self.assertEqual(
            self.execute("elmos-invocation-scoped-capability-lease", base).status,
            ResultStatus.DENIED,
        )
        base["expiresAt"] = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        self.assertEqual(
            self.execute("elmos-invocation-scoped-capability-lease", base).status,
            ResultStatus.DENIED,
        )

    def test_22_unverified_host_context_stays_unknown(self) -> None:
        self.host_security_eligible = False
        result = self.execute(
            "elmos-host-minted-security-context", self.security_payload(eligible=False)
        )
        self.assertEqual(result.status, ResultStatus.UNKNOWN)
        self.assertEqual(len(result.evidence_refs), 1)
        self.assertEqual(
            self.runtime.read_evidence(self.context, result.evidence_refs[0])["status"],
            ResultStatus.UNKNOWN.value,
        )

    def test_23_security_context_signature_tampering_is_denied(self) -> None:
        broker = SecurityContextBroker(self.signer)
        minted = broker.mint_context(
            eligible=True,
            account_stable=True,
            bindings={
                "pluginId": "p",
                "toolId": "t",
                "accountId": "a",
                "tenantId": "tenant-alpha",
                "environmentId": "e",
                "invocationId": "i",
                "policyVersion": self.authority,
            },
            entitlements={},
        ).to_wire()
        minted["signature"] = "hmac-sha256:test-key:" + "0" * 64
        with self.assertRaises(ContractError):
            broker.verify(minted)

    def test_24_executor_stale_epoch_and_missing_probe_are_denied(self) -> None:
        activate_initial = {
            "generation": 1,
            "connectionEpoch": 1,
            "environmentId": "env-x",
            "executorIdentity": "exec-x",
            "action": "activate",
            "liveProbeEvidenceRef": "probe-ref",
        }
        self.assertEqual(
            self.execute("elmos-executor-generation-fencing", activate_initial).status,
            ResultStatus.COMMITTED,
        )
        base = {
            "generation": 1,
            "connectionEpoch": 1,
            "environmentId": "env-x",
            "executorIdentity": "exec-x",
            "action": "reconnect",
        }
        self.assertEqual(
            self.execute("elmos-executor-generation-fencing", base).status,
            ResultStatus.COMMITTED,
        )
        self.assertEqual(
            self.execute("elmos-executor-generation-fencing", base).status,
            ResultStatus.COMMITTED,
        )
        activate = {
            "generation": 1,
            "connectionEpoch": 2,
            "environmentId": "env-x",
            "executorIdentity": "exec-x",
            "action": "activate",
        }
        self.assertEqual(
            self.execute("elmos-executor-generation-fencing", activate).status,
            ResultStatus.DENIED,
        )

    def test_25_workspace_scope_traversal_is_denied(self) -> None:
        result = self.execute(
            "elmos-workspace-ownership-lease",
            {
                "workspaceId": "ws-bad",
                "ownerExecutionId": "exec",
                "generation": 1,
                "repositoryId": "repo",
                "baseRevision": "rev",
                "writeScopes": ["../outside"],
                "action": "bind",
            },
        )
        self.assertEqual(result.status, ResultStatus.DENIED)

    def test_26_workspace_takeover_requires_handoff(self) -> None:
        bind = {
            "workspaceId": "ws-handoff",
            "ownerExecutionId": "old",
            "generation": 2,
            "repositoryId": "repo",
            "baseRevision": "rev",
            "writeScopes": ["src"],
            "action": "bind",
        }
        self.assertEqual(
            self.execute("elmos-workspace-ownership-lease", bind).status,
            ResultStatus.COMMITTED,
        )
        takeover = {
            "workspaceId": "ws-handoff",
            "newOwnerExecutionId": "new",
            "generation": 2,
            "action": "takeover",
        }
        self.assertEqual(
            self.execute("elmos-workspace-ownership-lease", takeover).status,
            ResultStatus.DENIED,
        )
        handoff = {
            "workspaceId": "ws-handoff",
            "ownerExecutionId": "old",
            "generation": 2,
            "action": "handoff",
        }
        self.assertEqual(
            self.execute("elmos-workspace-ownership-lease", handoff).status,
            ResultStatus.COMMITTED,
        )
        normal_accept = dict(takeover, action="acceptHandoff")
        self.assertEqual(
            self.execute("elmos-workspace-ownership-lease", normal_accept).status,
            ResultStatus.COMMITTED,
        )

    def test_27_protocol_adapter_unknown_version_is_unsupported(self) -> None:
        result = self.execute(
            "elmos-harness-transport-version-negotiation",
            {"provider": "openai-codex", "version": "latest", "requiredFeatures": []},
        )
        self.assertEqual(result.status, ResultStatus.UNSUPPORTED)

    def test_28_protocol_adapter_missing_feature_is_unsupported(self) -> None:
        result = self.execute(
            "elmos-harness-transport-version-negotiation",
            {
                "provider": "openai-codex",
                "version": "main@2026-08-28",
                "requiredFeatures": ["rootShell"],
            },
        )
        self.assertEqual(result.status, ResultStatus.UNSUPPORTED)

    def test_29_skill_provenance_rejects_self_verification_and_bad_digest(self) -> None:
        provenance = {
            "skillId": "skill-1",
            "publisher": "publisher",
            "origin": "repository",
            "canonicalUri": "repo://skill",
            "packageDigest": "0" * 64,
            "trustDomain": "REPOSITORY",
            "installScope": "project",
            "authorizationSemantics": [],
            "verified": True,
        }
        self.assertEqual(
            self.execute(
                "elmos-skill-trust-domain-provenance",
                {"skillPath": "skills/demo/SKILL.md", "provenance": provenance},
            ).status,
            ResultStatus.DENIED,
        )
        provenance["verified"] = False
        self.assertEqual(
            self.execute(
                "elmos-skill-trust-domain-provenance",
                {"skillPath": "skills/demo/SKILL.md", "provenance": provenance},
            ).status,
            ResultStatus.DENIED,
        )

    def test_30_unknown_event_validator_is_unsupported(self) -> None:
        result = self.execute(
            "elmos-registered-durable-plugin-events",
            {
                "action": "register",
                "registration": {
                    "type": "event.unknown",
                    "owner": "system",
                    "schemaVersion": 1,
                    "semantics": "REQUIRED_STATE",
                    "validator": "archive.claimed.validator",
                    "upgrader": "none",
                    "projections": [],
                    "compatibility": "STRICT",
                },
            },
        )
        self.assertEqual(result.status, ResultStatus.UNSUPPORTED)

    def test_31_unknown_optional_event_is_not_caller_authority(self) -> None:
        with self.assertRaises(ContractError):
            DurableEventRegistry().replay("unknown", 1, {}, unknown_optional=True)

    def test_32_ingress_unauthorized_producer_is_denied(self) -> None:
        self.assertEqual(
            self.execute(
                "elmos-typed-external-ingress",
                self.ingress_payload(producer="attacker"),
            ).status,
            ResultStatus.DENIED,
        )

    def test_33_tool_result_ingress_requires_pending_call(self) -> None:
        payload = self.ingress_payload(kind="TOOL_RESULT")
        cast(dict[str, object], payload["ingress"])["originatingCallId"] = (
            "call-missing"
        )
        self.assertEqual(
            self.execute("elmos-typed-external-ingress", payload).status,
            ResultStatus.DENIED,
        )

    def test_34_conflicting_ingress_replay_is_denied(self) -> None:
        first = self.ingress_payload(content="one")
        cast(dict[str, object], first["ingress"])["deduplicationKey"] = "dedup"
        self.assertEqual(
            self.execute("elmos-typed-external-ingress", first).status,
            ResultStatus.COMMITTED,
        )
        second = self.ingress_payload(content="two")
        cast(dict[str, object], second["ingress"])["deduplicationKey"] = "dedup"
        self.assertEqual(
            self.execute("elmos-typed-external-ingress", second).status,
            ResultStatus.DENIED,
        )

    def test_35_subagent_authority_and_model_widening_fail_closed(self) -> None:
        payload = self.subagent_payload()
        payload["childAuthority"] = ["fs.write"]
        self.assertEqual(
            self.execute("elmos-subagent-model-execution-spec", payload).status,
            ResultStatus.DENIED,
        )
        payload["childAuthority"] = ["fs.read"]
        payload["model"] = "unregistered"
        self.assertEqual(
            self.execute("elmos-subagent-model-execution-spec", payload).status,
            ResultStatus.DENIED,
        )

    def test_36_two_calls_in_one_invocation_commit_independently(self) -> None:
        coordinator = ResultLifecycleCoordinator()
        first = coordinator.commit(
            ToolResult(
                CallIdentity("inv", "call-1", "a" * 64, "env", "auth"), True, {}
            ),
            (),
            attempt=1,
            epoch=1,
        )
        second = coordinator.commit(
            ToolResult(
                CallIdentity("inv", "call-2", "a" * 64, "env", "auth"), True, {}
            ),
            (),
            attempt=1,
            epoch=1,
        )
        self.assertNotEqual(first.commit_key, second.commit_key)

    def test_37_aborted_result_cannot_publish(self) -> None:
        coordinator = ResultLifecycleCoordinator()
        raw = ToolResult(CallIdentity("inv", "call", "a" * 64, "env", "auth"), True, {})
        committed = coordinator.commit(raw, (), attempt=0, epoch=1)
        self.assertEqual(
            coordinator.abort(committed.commit_key).commit_state, CommitState.ABORTED
        )
        with self.assertRaises(ContractError):
            coordinator.publish(committed.commit_key)

    def test_38_fabricated_finalized_plan_is_rejected(self) -> None:
        store = StepExecutionPlanStore()
        plan = ExecutionPlan(
            ModelSnapshot("p", "m", "r"), (), "env", "auth", "NATIVE", "FINALIZED"
        )
        with self.assertRaises(ContractError):
            store.finalize(plan)

    def test_39_capability_lease_expiration_is_monotonic(self) -> None:
        broker = CapabilityLeaseBroker()
        now = datetime.now(UTC)
        lease = broker.issue(
            lease_id="lease",
            invocation_id="inv",
            environment_id="env",
            authority_snapshot_id="auth",
            execution_epoch=1,
            capabilities=["read"],
            expires_at=now + timedelta(seconds=1),
            now=now,
        )
        with self.assertRaises(ContractError):
            lease.use("inv", 1, "read", now=now + timedelta(seconds=2))

    def test_40_workspace_scope_is_hierarchical(self) -> None:
        lease = WorkspaceLease("ws", "owner", 1, "repo", "rev", ("src",))
        self.assertTrue(lease.owns("owner", scope="src/module/file.py"))
        self.assertFalse(lease.owns("owner", scope="docs/file.md"))

    def test_41_authority_environment_mismatch_is_denied(self) -> None:
        left = AuthoritySnapshot(
            "sha256:" + "1" * 64,
            frozenset({"read"}),
            "owner",
            "env-a",
            "v1",
            "a" * 64,
        )
        right = AuthoritySnapshot(
            "sha256:" + "2" * 64,
            frozenset({"read"}),
            "parent",
            "env-b",
            "v1",
            "b" * 64,
        )
        with self.assertRaises(ContractError):
            AuthoritySnapshot.intersect(
                left, right, frozenset({"read"}), "sha256:" + "3" * 64
            )

    def test_42_ingress_history_is_tenant_project_scoped(self) -> None:
        router = IngressRouter()
        ingress = TypedIngress(
            "ing", "EXTERNAL_EVENT", "producer", "event", "cause", "corr", "payload"
        )
        router.accept(
            ingress,
            tenant_id="tenant-a",
            project_id="project-a",
            authorized_producers={"producer"},
        )
        self.assertEqual(
            len(router.history("corr", tenant_id="tenant-a", project_id="project-a")), 1
        )
        self.assertEqual(
            len(router.history("corr", tenant_id="tenant-a", project_id="project-b")), 0
        )

    def test_43_invocation_payload_is_snapshotted(self) -> None:
        payload: dict[str, object] = {"nested": {"items": [1]}}
        invocation = self.request("non-existent-skill", payload)
        nested = cast(dict[str, object], payload["nested"])
        cast(list[int], nested["items"]).append(2)
        self.assertEqual(invocation.to_wire()["payload"], {"nested": {"items": [1]}})

    def test_44_duplicate_plan_tools_are_denied(self) -> None:
        result = self.execute(
            "elmos-step-finalized-execution-plan",
            {
                "modelSnapshot": {"provider": "p", "model": "m", "revision": "r"},
                "tools": ["read", "read"],
                "environmentSnapshotId": "env",
                "authoritySnapshotId": self.authority,
                "toolMode": "NATIVE",
            },
        )
        self.assertEqual(result.status, ResultStatus.DENIED)

    def test_45_result_commit_replay_does_not_reinvoke_interceptor(self) -> None:
        calls: list[str] = []

        def once(result: ToolResult) -> ToolResult:
            calls.append(result.identity.call_id)
            return result

        coordinator = ResultLifecycleCoordinator()
        raw = ToolResult(CallIdentity("inv", "call", "a" * 64, "env", "auth"), True, {})
        chain = (("once", "1", once),)
        coordinator.commit(raw, chain, attempt=0, epoch=1)
        coordinator.commit(raw, chain, attempt=0, epoch=1)
        self.assertEqual(calls, ["call"])

    def test_46_skill_provenance_rejects_in_root_symlink(self) -> None:
        linked = self.skill_root / "skills" / "linked.md"
        linked.symlink_to(self.skill_file)
        result = self.execute(
            "elmos-skill-trust-domain-provenance",
            {
                "skillPath": "skills/linked.md",
                "provenance": {
                    "skillId": "skill-linked",
                    "publisher": "publisher",
                    "origin": "repository",
                    "canonicalUri": linked.resolve().as_uri(),
                    "packageDigest": digest_bytes(
                        self.skill_file.read_bytes(), domain="delta-skill-package"
                    ),
                    "trustDomain": "REPOSITORY",
                    "installScope": "project",
                    "authorizationSemantics": [],
                },
            },
        )
        self.assertEqual(result.status, ResultStatus.DENIED)


if __name__ == "__main__":
    unittest.main()
