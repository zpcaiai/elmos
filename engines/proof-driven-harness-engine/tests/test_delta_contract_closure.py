from __future__ import annotations

import asyncio
from dataclasses import fields as dataclass_fields
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
from typing import Any, Mapping
import unittest
from unittest import mock

from elmos_proof_harness.assurance_policies import (
    HostSecurityContextSigner,
    ManagedWorktreeRegistry,
    PrivilegedPathContract,
    PrivilegedPathPolicy,
    SkillTrustDomainPolicy,
)
from elmos_proof_harness.canonical import digest_bytes, digest_object
from elmos_proof_harness.contracts import SecurityContext
from elmos_proof_harness.delta import (
    AuthoritySnapshot,
    BaseSkillOriginBinding,
    CallIdentity,
    ContractError,
    DeltaEvidenceStore,
    DeltaInvocation,
    DeltaResult,
    DeltaSkillRuntime,
    DurableEventEnvelope,
    DurableEventRegistry,
    EnvironmentSettingsBinding,
    EventRegistration,
    IngressRouter,
    ModelSnapshot,
    PendingToolCallBinding,
    ProtocolCapabilities,
    ProtocolNegotiator,
    ResultStatus,
    ResultLifecycleCoordinator,
    RuntimeAssuranceAuthority,
    SecurityContextBroker,
    SubagentBudgetReservation,
    ToolResult,
    TypedIngress,
    UnsupportedContractError,
    WorkspaceAuthority,
    _builtin_protocol_profiles,
    _tool_result_commit_key,
)
from elmos_proof_harness.errors import ValidationError


AUTHORITY_REVISION = "sha256:" + "a" * 64
POLICY_DIGEST = "sha256:" + "b" * 64
PLAN_DIGEST = "sha256:" + "c" * 64
PARENT_AUTHORITY_REVISION = "sha256:" + "e" * 64
RESULT_AUTHORITY_REVISION = "sha256:" + "f" * 64


def context() -> SecurityContext:
    return SecurityContext(
        "tenant",
        "project",
        "actor",
        "run",
        1,
        authority_revision=AUTHORITY_REVISION,
    )


def invocation(
    skill: str,
    payload: dict[str, object],
    *,
    invocation_id: str,
) -> DeltaInvocation:
    return DeltaInvocation(
        "tenant",
        "goal",
        "run",
        1,
        "step",
        invocation_id,
        "revision-set",
        skill,
        payload,
    )


def authority(
    invocation_id: str,
    *,
    extension_skill: str = "elmos-step-finalized-execution-plan",
    event_registrations: tuple[EventRegistration, ...] = (),
    authorized_producers: frozenset[str] = frozenset({"producer"}),
) -> RuntimeAssuranceAuthority:
    owner = AuthoritySnapshot(
        AUTHORITY_REVISION,
        frozenset({"read", "write"}),
        "owner",
        "environment",
        "profile-v1",
        POLICY_DIGEST,
    )
    parent = AuthoritySnapshot(
        PARENT_AUTHORITY_REVISION,
        frozenset({"read"}),
        "parent",
        "environment",
        "profile-v1",
        POLICY_DIGEST,
    )
    receipt_ref = "base-origin-receipt"
    origin = BaseSkillOriginBinding.bind_host_receipt(
        skill_id="ELMOS-V3-007",
        skill_name="elmos-harness-runtime-kernel",
        owner_kernel="K7",
        execution_id="execution",
        tenant_id="tenant",
        project_id="project",
        actor_id="actor",
        run_id="run",
        execution_epoch=1,
        fencing_generation=1,
        authority_revision=AUTHORITY_REVISION,
        revision_set_id="revision-set",
        step_id="step",
        invocation_id=invocation_id,
        extension_skill=extension_skill,
        environment_id="environment",
        receipt_ref=receipt_ref,
        receipt_state="EXECUTING",
    )
    return RuntimeAssuranceAuthority(
        tenant_id="tenant",
        project_id="project",
        actor_id="actor",
        run_id="run",
        execution_epoch=1,
        fencing_generation=1,
        authority_revision=AUTHORITY_REVISION,
        revision_set_id="revision-set",
        step_id="step",
        execution_id="execution",
        originating_base_skill=origin,
        environment_ids=frozenset({"environment"}),
        environment_snapshot_ids=frozenset({"environment-snapshot"}),
        permission_profile_versions=frozenset({"profile-v1"}),
        capabilities=frozenset({"event.register", "ingress.accept"}),
        tools=frozenset({"read"}),
        tool_modes=frozenset({"NATIVE"}),
        selected_models=frozenset({ModelSnapshot("openai", "gpt-5", "v1")}),
        originating_plan_hashes=frozenset({PLAN_DIGEST}),
        security_eligible=True,
        account_stable=True,
        security_bindings={
            "pluginId": "plugin",
            "toolId": "tool",
            "accountId": "account",
            "tenantId": "tenant",
            "environmentId": "environment",
            "invocationId": invocation_id,
            "policyVersion": AUTHORITY_REVISION,
        },
        entitlements={"role": "operator", "limits": {"events": 100}},
        owner_authority=owner,
        parent_authority_snapshot=parent,
        policy_permissions=frozenset({"read"}),
        authority_result_snapshot_id=RESULT_AUTHORITY_REVISION,
        authorized_producers=authorized_producers,
        pending_calls=frozenset({"pending-call"}),
        verified_evidence_refs=frozenset({"evidence", receipt_ref}),
        executor_bindings=frozenset({("environment", "executor")}),
        event_registrations=event_registrations,
        parent_execution_id="parent-execution",
        parent_authority=frozenset({"read"}),
        parent_tools=frozenset({"read"}),
        parent_max_output_tokens=4096,
        budget_reservations=(("budget", 2048),),
        allowed_subagent_models=frozenset({("openai", "gpt-5")}),
        delegation_allowed_invocations=frozenset({"delegated-invocation"}),
        workspace_authorities=(
            WorkspaceAuthority(
                "workspace",
                "repository",
                "revision",
                ("src",),
                frozenset({"execution"}),
            ),
        ),
        pending_call_bindings=(
            PendingToolCallBinding(
                "pending-call",
                1,
                invocation_id,
                PLAN_DIGEST,
                "environment",
                "read",
                AUTHORITY_REVISION,
            ),
        ),
        tool_contracts={
            "read": {
                "inputSchema": {"type": "object"},
                "outputSchema": {"type": "object"},
            }
        },
        handler_digests={"read": "sha256:" + "d" * 64},
        subagent_budget_reservations=(
            SubagentBudgetReservation(
                "budget",
                invocation_id,
                "parent-execution",
                "environment",
                AUTHORITY_REVISION,
                "openai",
                "gpt-5",
                "high",
                frozenset({"read"}),
                frozenset({"read"}),
                2048,
                "2.0",
                datetime.now(UTC) + timedelta(hours=1),
                PLAN_DIGEST,
            ),
        ),
    )


def authority_for(
    request: DeltaInvocation,
    *,
    event_registrations: tuple[EventRegistration, ...] = (),
    authorized_producers: frozenset[str] = frozenset({"producer"}),
) -> RuntimeAssuranceAuthority:
    if request.extension_skill is None:
        raise AssertionError("internal request must select an extension Skill")
    return authority(
        request.invocation_id,
        extension_skill=request.extension_skill,
        event_registrations=event_registrations,
        authorized_producers=authorized_producers,
    )


def protocol_payload(
    profile: ProtocolCapabilities,
    *,
    offered: ProtocolCapabilities | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "provider": profile.provider,
        "version": profile.version,
        "requiredFeatures": [],
    }
    if offered is not None:
        payload["offered"] = {
            "features": sorted(offered.features),
            "transport": offered.transport,
            "authScheme": offered.auth_scheme,
            "historyMode": offered.history_mode,
            "typedToolResult": offered.typed_tool_result,
            "schemaDialect": offered.schema_dialect,
            "consistencyModel": offered.consistency_model,
        }
    return payload


def ingress(
    ingress_id: str,
    event_id: str,
    causation_id: str,
    *,
    correlation_id: str = "correlation",
    kind: str = "EXTERNAL_EVENT",
    producer: str = "producer",
    originating_call_id: str | None = None,
) -> TypedIngress:
    return TypedIngress(
        ingress_id,
        kind,
        producer,
        event_id,
        causation_id,
        correlation_id,
        ({"type": "text", "text": event_id},),
        originating_call_id,
    )


class ProtocolContractClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profiles = _builtin_protocol_profiles()
        self.negotiator = ProtocolNegotiator(self.profiles)

    def test_empty_requirements_do_not_activate_advertised_negative_features(
        self,
    ) -> None:
        for key in (
            ("openai-codex", "0.150.1"),
            ("deepseek-harness", "0.1.2-alpha.1"),
        ):
            profile = self.profiles[key]
            with self.subTest(profile=key):
                self.assertIs(
                    self.negotiator.negotiate(profile, required_features=()),
                    profile,
                )

    def test_negative_feature_boundaries_apply_only_when_requested(self) -> None:
        cases = (
            (("openai-codex", "0.150.1"), "resultInterception"),
            (("deepseek-harness", "0.1.2-alpha.1"), "ApiProxy"),
        )
        for key, required in cases:
            with self.subTest(profile=key, required=required):
                with self.assertRaisesRegex(
                    UnsupportedContractError, "unsupported protocol capabilities"
                ):
                    self.negotiator.negotiate(
                        self.profiles[key], required_features=(required,)
                    )

    def test_every_explicit_protocol_offer_dimension_is_exact(self) -> None:
        profile = self.profiles[("openai-codex", "main@2026-08-28")]
        variants = {
            "features": replace(profile, features=frozenset({"typedToolResult"})),
            "transport": replace(profile, transport="HTTP"),
            "historyMode": replace(profile, history_mode="PAGINATED"),
            "typedToolResult": replace(profile, typed_tool_result=False),
            "schemaDialect": replace(profile, schema_dialect="json-schema-draft-07"),
            "consistencyModel": replace(profile, consistency_model="EVENTUAL"),
            "authScheme": replace(profile, auth_scheme="bearer"),
        }
        for field_name, offered in variants.items():
            with self.subTest(field=field_name):
                with self.assertRaisesRegex(UnsupportedContractError, field_name):
                    self.negotiator.negotiate(offered)

    def test_runtime_accepts_exact_offer_and_rejects_transport_drift(self) -> None:
        calls: list[str] = []

        def provider(
            trusted_context: SecurityContext,
            request: DeltaInvocation,
        ) -> RuntimeAssuranceAuthority:
            del trusted_context
            calls.append(request.invocation_id)
            return authority_for(request)

        runtime = DeltaSkillRuntime(authority_provider=provider)
        profile = self.profiles[("openai-codex", "main@2026-08-28")]
        exact = invocation(
            "elmos-harness-transport-version-negotiation",
            protocol_payload(profile, offered=profile),
            invocation_id="protocol-exact",
        )
        self.assertEqual(runtime.execute(exact, context=context()).status, "COMMITTED")
        drifted = replace(profile, transport="HTTP")
        mismatch = invocation(
            "elmos-harness-transport-version-negotiation",
            protocol_payload(profile, offered=drifted),
            invocation_id="protocol-drift",
        )
        self.assertEqual(
            runtime.execute(mismatch, context=context()).status, "UNSUPPORTED"
        )
        self.assertEqual(calls, ["protocol-exact", "protocol-drift"])

    def test_deepseek_profiles_expose_only_canonical_tool_call_identity(self) -> None:
        for version in ("0.1.1-rc.2", "0.1.2-alpha.1"):
            features = self.profiles[("deepseek-harness", version)].to_wire()[
                "features"
            ]
            self.assertIn("ToolCallId", features)
            self.assertNotIn("CallId", features)


class DurableEventContractClosureTests(unittest.TestCase):
    @staticmethod
    def registry() -> DurableEventRegistry:
        def validate(payload: Mapping[str, Any]) -> bool:
            return isinstance(payload.get("value"), int)

        def upgrade(payload: Mapping[str, Any]) -> Mapping[str, Any]:
            value = payload.get("value")
            if not isinstance(value, int):
                raise ContractError("custom event value must be an integer")
            return {**payload, "value": value + 1, "version": 2}

        registry = DurableEventRegistry(
            validators={"custom.validator.v1": validate},
            upgraders={"custom.upgrader.v2": upgrade},
            optional_unknown_types={"optional.event", "custom.event"},
        )
        registry.register(
            EventRegistration(
                "custom.event",
                "owner",
                1,
                "OPTIONAL_OBSERVATION",
                "custom.validator.v1",
                "none",
                (),
                "FULL",
            )
        )
        registry.register(
            EventRegistration(
                "custom.event",
                "owner",
                2,
                "OPTIONAL_OBSERVATION",
                "custom.validator.v1",
                "custom.upgrader.v2",
                (),
                "FULL",
            )
        )
        return registry

    def test_injected_custom_validator_and_upgrader_are_used(self) -> None:
        registry = self.registry()
        self.assertEqual(
            registry.replay("custom.event", 1, {"value": 1}, target_version=2),
            {"value": 2, "version": 2},
        )
        with self.assertRaisesRegex(ContractError, "schema validation"):
            registry.replay("custom.event", 1, {"value": "not-an-int"})

    def test_runtime_registration_uses_the_injected_host_registry(self) -> None:
        registrations = self.registry()._items
        trusted = tuple(registrations[key] for key in sorted(registrations))

        def provider(
            trusted_context: SecurityContext,
            request: DeltaInvocation,
        ) -> RuntimeAssuranceAuthority:
            del trusted_context
            return authority_for(request, event_registrations=trusted)

        def validate(payload: Mapping[str, Any]) -> bool:
            return isinstance(payload.get("value"), int)

        def upgrade(payload: Mapping[str, Any]) -> Mapping[str, Any]:
            value = payload.get("value")
            if not isinstance(value, int):
                raise ContractError("custom event value must be an integer")
            return {**payload, "value": value + 1, "version": 2}

        runtime = DeltaSkillRuntime(
            authority_provider=provider,
            event_validators={"custom.validator.v1": validate},
            event_upgraders={"custom.upgrader.v2": upgrade},
        )
        for registration in trusted:
            request = invocation(
                "elmos-registered-durable-plugin-events",
                {"action": "register", "registration": registration.to_wire()},
                invocation_id=f"register-{registration.schema_version}",
            )
            self.assertEqual(
                runtime.execute(request, context=context()).status,
                ResultStatus.COMMITTED,
            )
        state = runtime._state(context(), "revision-set")
        self.assertEqual(
            state.event_registry.replay(
                "custom.event", 1, {"value": 3}, target_version=2
            ),
            {"value": 4, "version": 2},
        )

    def test_unregistered_custom_handler_stays_unsupported(self) -> None:
        registry = DurableEventRegistry()
        with self.assertRaises(UnsupportedContractError):
            registry.register(
                EventRegistration(
                    "custom.event",
                    "owner",
                    1,
                    "REQUIRED_STATE",
                    "missing.validator",
                    "none",
                )
            )

    def test_uninstall_preflight_is_explicit_conservative_and_audited(self) -> None:
        registry = self.registry()
        allowed = registry.preflight_uninstall("custom.event", persisted_events=())
        self.assertEqual(allowed["decision"], "ALLOW")
        persisted = DurableEventEnvelope(
            "event-1", "custom.event", 1, {"value": 1}, "correlation"
        )
        with self.assertRaisesRegex(ContractError, "persisted event history"):
            registry.preflight_uninstall("custom.event", persisted_events=(persisted,))
        self.assertEqual(registry.audit_records()[-1]["decision"], "BLOCK")

    def test_downgrade_preflight_requires_migration_of_newer_events(self) -> None:
        registry = self.registry()
        allowed = registry.preflight_downgrade("custom.event", 1, persisted_events=())
        self.assertEqual(allowed["decision"], "ALLOW")
        persisted = DurableEventEnvelope(
            "event-2", "custom.event", 2, {"value": 2}, "correlation"
        )
        with self.assertRaisesRegex(ContractError, "require migration"):
            registry.preflight_downgrade(
                "custom.event", 1, persisted_events=(persisted,)
            )

    def test_fork_replay_preserves_exact_causal_identity(self) -> None:
        registry = self.registry()
        events = (
            DurableEventEnvelope(
                "root", "custom.event", 1, {"value": 1}, "correlation"
            ),
            DurableEventEnvelope(
                "child",
                "custom.event",
                1,
                {"value": 2},
                "correlation",
                "root",
            ),
        )
        replayed = registry.replay_for_fork(events, fork_id="fork-1")
        self.assertEqual([item.event_id for item in replayed], ["root", "child"])
        self.assertEqual(replayed[1].causation_id, "root")
        self.assertEqual(replayed[1].correlation_id, "correlation")

    def test_migration_replay_upgrades_payload_without_changing_causality(self) -> None:
        registry = self.registry()
        events = (
            DurableEventEnvelope(
                "root", "custom.event", 1, {"value": 1}, "correlation"
            ),
            DurableEventEnvelope(
                "child",
                "custom.event",
                1,
                {"value": 2},
                "correlation",
                "root",
            ),
        )
        replayed = registry.replay_for_migration(
            events,
            migration_id="migration-1",
            target_versions={"custom.event": 2},
        )
        self.assertEqual([item.schema_version for item in replayed], [2, 2])
        self.assertEqual([item.payload["value"] for item in replayed], [2, 3])
        self.assertEqual(replayed[1].causation_id, "root")

    def test_causal_replay_rejects_missing_duplicate_and_cross_scope_parents(
        self,
    ) -> None:
        registry = self.registry()
        missing = DurableEventEnvelope(
            "child", "custom.event", 1, {"value": 1}, "correlation", "missing"
        )
        with self.assertRaisesRegex(ContractError, "predecessor is missing"):
            registry.replay_for_fork((missing,), fork_id="fork-missing")
        duplicate = DurableEventEnvelope(
            "root", "custom.event", 1, {"value": 2}, "correlation"
        )
        with self.assertRaisesRegex(ContractError, "duplicates"):
            registry.replay_for_fork((duplicate, duplicate), fork_id="fork-duplicate")
        crossed = DurableEventEnvelope(
            "child",
            "custom.event",
            1,
            {"value": 2},
            "other-correlation",
            "root",
        )
        with self.assertRaisesRegex(ContractError, "correlation boundaries"):
            registry.replay_for_fork(
                (
                    DurableEventEnvelope(
                        "root",
                        "custom.event",
                        1,
                        {"value": 1},
                        "correlation",
                    ),
                    crossed,
                ),
                fork_id="fork-crossed",
            )

    def test_optional_unknown_event_is_skipped_only_by_host_rule_and_audited(
        self,
    ) -> None:
        registry = self.registry()
        events = (
            DurableEventEnvelope(
                "optional-root",
                "optional.event",
                1,
                {"opaque": True},
                "correlation",
            ),
            DurableEventEnvelope(
                "known-child",
                "custom.event",
                1,
                {"value": 1},
                "correlation",
                "optional-root",
            ),
        )
        replayed = registry.replay_for_fork(events, fork_id="fork-optional")
        self.assertEqual([item.event_id for item in replayed], ["known-child"])
        self.assertEqual(replayed[0].causation_id, "optional-root")
        self.assertTrue(
            any(
                record.get("decision") == "SKIP_OPTIONAL_UNKNOWN"
                for record in registry.audit_records()
            )
        )
        runtime = DeltaSkillRuntime(optional_unknown_event_types=("optional.event",))
        state = runtime._state(context(), "revision-set")
        self.assertIsNone(
            state.event_registry.replay(
                "optional.event", 1, {"value": "opaque"}, unknown_optional=True
            )
        )


class TypedIngressContractClosureTests(unittest.TestCase):
    def test_legacy_producer_set_defaults_to_external_kinds_not_user_input(
        self,
    ) -> None:
        router = IngressRouter()
        self.assertTrue(
            router.accept(
                ingress("ingress-1", "event-1", "external-root"),
                tenant_id="tenant",
                project_id="project",
                authorized_producers={"producer"},
            )
        )
        with self.assertRaisesRegex(ContractError, "kind is not authorized"):
            router.accept(
                ingress(
                    "ingress-user",
                    "event-user",
                    "external-user",
                    kind="USER_INPUT",
                ),
                tenant_id="tenant",
                project_id="project",
                authorized_producers={"producer"},
            )

    def test_explicit_producer_policy_is_kind_scoped_and_cannot_grant_user(
        self,
    ) -> None:
        router = IngressRouter()
        tool_result = ingress(
            "ingress-tool",
            "event-tool",
            "external-tool",
            kind="TOOL_RESULT",
            originating_call_id="pending-call",
        )
        self.assertTrue(
            router.accept(
                tool_result,
                tenant_id="tenant",
                project_id="project",
                authorized_producers={"producer": {"TOOL_RESULT"}},
                pending_calls={"pending-call"},
            )
        )
        with self.assertRaisesRegex(ContractError, "kind is not authorized"):
            router.accept(
                ingress("ingress-event", "event-event", "external-event"),
                tenant_id="tenant",
                project_id="project",
                authorized_producers={"producer": {"TOOL_RESULT"}},
            )
        with self.assertRaisesRegex(ContractError, "cannot be granted USER_INPUT"):
            router.accept(
                ingress(
                    "ingress-user",
                    "event-user",
                    "external-user",
                    kind="USER_INPUT",
                ),
                tenant_id="tenant",
                project_id="project",
                authorized_producers={"producer": {"USER_INPUT"}},
            )

    def test_runtime_external_ingress_rejects_user_impersonation(self) -> None:
        def provider(
            trusted_context: SecurityContext,
            request: DeltaInvocation,
        ) -> RuntimeAssuranceAuthority:
            del trusted_context
            return authority_for(request)

        runtime = DeltaSkillRuntime(
            authority_provider=provider,
            authorized_producers={("tenant", "project"): {"producer"}},
        )

        def payload(item: TypedIngress) -> dict[str, object]:
            return {"action": "ingest", "ingress": item.to_wire()}

        denied = invocation(
            "elmos-typed-external-ingress",
            payload(
                ingress(
                    "user-ingress",
                    "user-event",
                    "external-user",
                    kind="USER_INPUT",
                )
            ),
            invocation_id="user-impersonation",
        )
        self.assertEqual(runtime.execute(denied, context=context()).status, "DENIED")
        accepted = invocation(
            "elmos-typed-external-ingress",
            payload(ingress("external-ingress", "external-event", "external-root")),
            invocation_id="external-event",
        )
        self.assertEqual(
            runtime.execute(accepted, context=context()).status,
            ResultStatus.COMMITTED,
        )

    def test_history_uses_stable_keyset_cursor_and_arrival_order(self) -> None:
        router = IngressRouter()
        root = ingress("ingress-root", "z-root", "outside")
        child = ingress("ingress-child", "a-child", "z-root")
        tail = ingress("ingress-tail", "m-tail", "a-child")
        for item in (root, child):
            router.accept(
                item,
                tenant_id="tenant",
                project_id="project",
                authorized_producers={"producer"},
            )
        first = router.history_page(
            "correlation",
            tenant_id="tenant",
            project_id="project",
            page_size=1,
        )
        self.assertEqual(first.events, (root,))
        self.assertTrue(first.has_more)
        self.assertIsNotNone(first.next_cursor)
        router.accept(
            tail,
            tenant_id="tenant",
            project_id="project",
            authorized_producers={"producer"},
        )
        remaining = router.history_page(
            "correlation",
            tenant_id="tenant",
            project_id="project",
            after_cursor=first.next_cursor,
            page_size=10,
        )
        self.assertEqual(remaining.events, (child, tail))
        self.assertEqual(
            [item.causation_id for item in remaining.events], ["z-root", "a-child"]
        )
        with self.assertRaisesRegex(ContractError, "scope-mismatched"):
            router.history_page(
                "correlation",
                tenant_id="tenant",
                project_id="other-project",
                after_cursor=first.next_cursor,
            )
        with self.assertRaisesRegex(ContractError, "offset ingress pagination"):
            router.history(
                "correlation",
                tenant_id="tenant",
                project_id="project",
                page=1,
            )

    def test_ingress_causation_rejects_cross_correlation_cycles_and_reused_ids(
        self,
    ) -> None:
        router = IngressRouter()
        root = ingress("ingress-root", "root", "outside")
        router.accept(
            root,
            tenant_id="tenant",
            project_id="project",
            authorized_producers={"producer"},
        )
        with self.assertRaisesRegex(ContractError, "correlation boundaries"):
            router.accept(
                ingress(
                    "crossed",
                    "crossed-event",
                    "root",
                    correlation_id="other-correlation",
                ),
                tenant_id="tenant",
                project_id="project",
                authorized_producers={"producer"},
            )
        with self.assertRaisesRegex(ContractError, "event ID is already bound"):
            router.accept(
                ingress("reused", "root", "outside"),
                tenant_id="tenant",
                project_id="project",
                authorized_producers={"producer"},
            )
        cyclic = IngressRouter()
        cyclic.accept(
            ingress("ingress-a", "event-a", "event-b"),
            tenant_id="tenant",
            project_id="project",
            authorized_producers={"producer"},
        )
        with self.assertRaisesRegex(ContractError, "cycle"):
            cyclic.accept(
                ingress("ingress-b", "event-b", "event-a"),
                tenant_id="tenant",
                project_id="project",
                authorized_producers={"producer"},
            )


class AuthorityAndExecutionClosureTests(unittest.TestCase):
    def test_internal_extension_requires_exact_base_skill_owner_receipt(self) -> None:
        request = invocation(
            "elmos-invocation-scoped-capability-lease",
            {
                "action": "issue",
                "leaseId": "owner-bound-lease",
                "environmentId": "environment",
                "authoritySnapshotId": AUTHORITY_REVISION,
                "capabilities": ["event.register"],
                "delegationAllowed": False,
                "expiresAt": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            },
            invocation_id="owner-bound-invocation",
        )
        trusted = authority_for(request)
        bad_origin = BaseSkillOriginBinding.bind_host_receipt(
            skill_id="ELMOS-V3-002",
            skill_name="elmos-repository-intelligence-kernel",
            owner_kernel="K2",
            execution_id="execution",
            tenant_id="tenant",
            project_id="project",
            actor_id="actor",
            run_id="run",
            execution_epoch=1,
            fencing_generation=1,
            authority_revision=AUTHORITY_REVISION,
            revision_set_id="revision-set",
            step_id="step",
            invocation_id=request.invocation_id,
            extension_skill=request.extension_skill or "",
            environment_id="environment",
            receipt_ref="base-origin-receipt",
            receipt_state="EXECUTING",
        )
        runtime = DeltaSkillRuntime()
        denied = runtime.execute(
            request,
            context=context(),
            trusted_authority=replace(
                trusted,
                originating_base_skill=bad_origin,
            ),
        )
        self.assertEqual(denied.status, ResultStatus.DENIED)
        self.assertIn("does not own", denied.message or "")
        self.assertEqual(runtime._states, {})

        committed = runtime.execute(
            request,
            context=context(),
            trusted_authority=trusted,
        )
        self.assertEqual(committed.status, ResultStatus.COMMITTED, committed.message)
        evidence = runtime.read_evidence(context(), committed.evidence_refs[0])
        self.assertEqual(evidence["authorityDigest"], trusted.authority_digest)
        self.assertEqual(
            evidence["originatingBaseSkill"],
            trusted.originating_base_skill.to_wire(),
        )

        cross_run = BaseSkillOriginBinding.bind_host_receipt(
            skill_id="ELMOS-V3-007",
            skill_name="elmos-harness-runtime-kernel",
            owner_kernel="K7",
            execution_id="execution",
            tenant_id="tenant",
            project_id="project",
            actor_id="actor",
            run_id="other-run",
            execution_epoch=1,
            fencing_generation=1,
            authority_revision=AUTHORITY_REVISION,
            revision_set_id="revision-set",
            step_id="step",
            invocation_id=request.invocation_id,
            extension_skill=request.extension_skill or "",
            environment_id="environment",
            receipt_ref="base-origin-receipt",
            receipt_state="EXECUTING",
        )
        with self.assertRaisesRegex(ContractError, "escaped trusted authority scope"):
            replace(trusted, originating_base_skill=cross_run)

    def test_authority_digest_contains_every_dataclass_field(self) -> None:
        snapshot = authority("digest-invocation")

        def camel(name: str) -> str:
            parts = name.split("_")
            return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])

        wire = snapshot.to_wire()
        expected_keys = {camel(item.name) for item in dataclass_fields(snapshot)}
        self.assertEqual(set(wire), expected_keys)
        self.assertEqual(
            snapshot.authority_digest,
            digest_object(wire, domain="delta-runtime-assurance-authority"),
        )
        for key in sorted(expected_keys):
            incomplete = dict(wire)
            del incomplete[key]
            with self.subTest(omitted=key):
                self.assertNotEqual(
                    snapshot.authority_digest,
                    digest_object(
                        incomplete, domain="delta-runtime-assurance-authority"
                    ),
                )
        self.assertIn("permissions", wire["ownerAuthority"])

    def test_authority_digest_changes_for_nested_grants_and_is_order_stable(
        self,
    ) -> None:
        baseline = authority("digest-nested")
        reordered = replace(
            baseline,
            capabilities=frozenset(reversed(sorted(baseline.capabilities))),
        )
        self.assertEqual(baseline.authority_digest, reordered.authority_digest)
        widened_owner = replace(
            baseline.owner_authority,
            permissions=frozenset({"read", "write", "admin"}),
        )
        self.assertNotEqual(
            baseline.authority_digest,
            replace(baseline, owner_authority=widened_owner).authority_digest,
        )
        extra_event = EventRegistration(
            "extra.event",
            "owner",
            1,
            "REQUIRED_STATE",
            "elmos.object.v1",
            "none",
        )
        self.assertNotEqual(
            baseline.authority_digest,
            replace(
                baseline,
                event_registrations=baseline.event_registrations + (extra_event,),
            ).authority_digest,
        )
        with self.assertRaisesRegex(ContractError, "stable handler identifiers"):
            replace(
                baseline,
                event_registrations=(
                    EventRegistration(
                        "callable.event",
                        "owner",
                        1,
                        "REQUIRED_STATE",
                        lambda payload: bool(payload),
                        "none",
                    ),
                ),
            )

    def test_trusted_authority_skips_second_provider_resolution(self) -> None:
        calls: list[str] = []

        def provider(
            trusted_context: SecurityContext,
            request: DeltaInvocation,
        ) -> RuntimeAssuranceAuthority:
            del trusted_context
            calls.append(request.invocation_id)
            return authority_for(request)

        runtime = DeltaSkillRuntime(authority_provider=provider)
        profile = _builtin_protocol_profiles()[("openai-codex", "main@2026-08-28")]
        direct = invocation(
            "elmos-harness-transport-version-negotiation",
            protocol_payload(profile),
            invocation_id="direct-authority",
        )
        self.assertEqual(runtime.execute(direct, context=context()).status, "COMMITTED")
        injected = invocation(
            "elmos-harness-transport-version-negotiation",
            protocol_payload(profile),
            invocation_id="injected-authority",
        )
        self.assertEqual(
            runtime.execute(
                injected,
                context=context(),
                trusted_authority=authority_for(injected),
            ).status,
            "COMMITTED",
        )
        self.assertEqual(calls, ["direct-authority"])

    def test_deadline_is_checked_before_and_after_dispatch(self) -> None:
        runtime = DeltaSkillRuntime()
        profile = _builtin_protocol_profiles()[("openai-codex", "main@2026-08-28")]
        expired = invocation(
            "elmos-harness-transport-version-negotiation",
            protocol_payload(profile),
            invocation_id="expired-before",
        )
        before = runtime.execute(
            expired,
            context=context(),
            trusted_authority=authority_for(expired),
            deadline=datetime.now(UTC) - timedelta(seconds=1),
        )
        self.assertEqual(before.status, ResultStatus.DENIED)
        self.assertIn("before dispatch", before.message or "")

        delayed = invocation(
            "elmos-harness-transport-version-negotiation",
            protocol_payload(profile),
            invocation_id="expired-after",
        )
        original_dispatch = runtime._dispatch

        def slow_dispatch(
            name: str,
            request: DeltaInvocation,
            trusted_context: SecurityContext,
            trusted_authority: RuntimeAssuranceAuthority,
            state: Any,
        ) -> Any:
            result = original_dispatch(
                name,
                request,
                trusted_context,
                trusted_authority,
                state,
            )
            time.sleep(0.02)
            return result

        with mock.patch.object(runtime, "_dispatch", side_effect=slow_dispatch):
            after = runtime.execute(
                delayed,
                context=context(),
                trusted_authority=authority_for(delayed),
                deadline=datetime.now(UTC) + timedelta(milliseconds=5),
            )
        self.assertEqual(after.status, ResultStatus.DENIED)
        self.assertIn("during dispatch", after.message or "")


class PrivilegedPathContractClosureTests(unittest.TestCase):
    def test_privileged_path_policy_rejects_remote_mutable_undeclared_and_argument_drift(
        self,
    ) -> None:
        policy = PrivilegedPathPolicy(
            (
                PrivilegedPathContract(
                    "/workspace/read",
                    "FILESYSTEM",
                    remote=False,
                    mutable=False,
                    allowed_arguments=("read", "stat"),
                ),
            )
        )
        exact = {
            "path": "/workspace/read",
            "kind": "FILESYSTEM",
            "remote": False,
            "mutable": False,
            "arguments": ["read"],
        }
        policy.validate_entitlements({"privilegedPaths": [exact]})

        denied = (
            exact | {"path": "/workspace/undeclared"},
            exact | {"remote": True},
            exact | {"mutable": True},
            exact | {"arguments": ["read", "write"]},
        )
        for request in denied:
            with self.subTest(request=request), self.assertRaises(ValidationError):
                policy.validate_entitlements({"privilegedPaths": [request]})


class DurableOutputContractClosureTests(unittest.TestCase):
    def output_for(
        self,
        runtime: DeltaSkillRuntime,
        request: DeltaInvocation,
    ) -> Mapping[str, Any]:
        result = runtime.execute(
            request,
            context=context(),
            trusted_authority=authority_for(request),
        )
        self.assertEqual(result.status, ResultStatus.COMMITTED, result.message)
        self.assertEqual(len(result.evidence_refs), 1)
        record = runtime.read_evidence(context(), result.evidence_refs[0])
        output = record.get("output")
        self.assertIsInstance(output, Mapping)
        assert isinstance(output, Mapping)
        return output

    def test_step_plan_hash_binds_exact_tool_contracts_and_handler_digests(
        self,
    ) -> None:
        runtime = DeltaSkillRuntime()
        payload: dict[str, object] = {
            "modelSnapshot": {
                "provider": "openai",
                "model": "gpt-5",
                "revision": "v1",
            },
            "tools": ["read"],
            "toolContracts": {
                "read": {
                    "inputSchema": {"type": "object"},
                    "outputSchema": {"type": "object"},
                }
            },
            "handlerDigests": {"read": "sha256:" + "d" * 64},
            "environmentSnapshotId": "environment-snapshot",
            "authoritySnapshotId": AUTHORITY_REVISION,
            "toolMode": "NATIVE",
            "capabilities": [],
            "planId": "plan-contract-bound",
        }
        request = invocation(
            "elmos-step-finalized-execution-plan",
            payload,
            invocation_id="plan-contract-bound",
        )
        output = self.output_for(runtime, request)
        expected_claim = {
            "modelSnapshot": payload["modelSnapshot"],
            "tools": ["read"],
            "toolContracts": payload["toolContracts"],
            "handlerDigests": payload["handlerDigests"],
            "environmentSnapshotId": "environment-snapshot",
            "authoritySnapshotId": AUTHORITY_REVISION,
            "mode": "NATIVE",
            "capabilities": [],
        }
        self.assertEqual(output["toolContracts"], payload["toolContracts"])
        self.assertEqual(output["handlerDigests"], payload["handlerDigests"])
        self.assertEqual(
            output["planHash"],
            digest_object(expected_claim, domain="delta-execution-plan"),
        )
        changed_contract = dict(expected_claim)
        changed_contract["toolContracts"] = {"read": {"inputSchema": False}}
        self.assertNotEqual(
            output["planHash"],
            digest_object(changed_contract, domain="delta-execution-plan"),
        )

        for missing in ("toolContracts", "handlerDigests"):
            denied_payload = dict(payload)
            del denied_payload[missing]
            denied = invocation(
                "elmos-step-finalized-execution-plan",
                denied_payload,
                invocation_id=f"plan-missing-{missing}",
            )
            result = runtime.execute(
                denied,
                context=context(),
                trusted_authority=authority_for(denied),
            )
            with self.subTest(missing=missing):
                self.assertEqual(result.status, ResultStatus.DENIED)
        invalid_bindings = (
            {**payload, "toolContracts": {}},
            {**payload, "handlerDigests": {}},
            {**payload, "handlerDigests": {"read": "d" * 64}},
        )
        for index, denied_payload in enumerate(invalid_bindings):
            denied = invocation(
                "elmos-step-finalized-execution-plan",
                denied_payload,
                invocation_id=f"plan-invalid-binding-{index}",
            )
            result = runtime.execute(
                denied,
                context=context(),
                trusted_authority=authority_for(denied),
            )
            with self.subTest(invalid_binding=index):
                self.assertEqual(result.status, ResultStatus.DENIED)

    def test_subagent_output_binds_budget_deadline_plan_model_and_child_scope(
        self,
    ) -> None:
        runtime = DeltaSkillRuntime(allowed_subagent_models=(("openai", "gpt-5"),))
        deadline = datetime.now(UTC) + timedelta(minutes=10)
        payload: dict[str, object] = {
            "provider": "openai",
            "model": "gpt-5",
            "reasoningEffort": "high",
            "maxOutputTokens": 1024,
            "parentExecutionId": "parent-execution",
            "environmentId": "environment",
            "parentEnvironmentId": "environment",
            "authoritySnapshotId": AUTHORITY_REVISION,
            "budgetReservationId": "budget",
            "parentAuthority": ["read"],
            "childAuthority": ["read"],
            "parentTools": ["read"],
            "childTools": ["read"],
            "parentMaxOutputTokens": 4096,
            "toolPlanHash": PLAN_DIGEST,
            "costBudget": "1.2500",
            "wallClockDeadline": deadline.isoformat(),
        }
        request = invocation(
            "elmos-subagent-model-execution-spec",
            payload,
            invocation_id="subagent-bound-output",
        )
        output = self.output_for(runtime, request)
        expected_keys = {
            "invocationId",
            "parentExecutionId",
            "provider",
            "model",
            "reasoningEffort",
            "authoritySnapshotId",
            "environmentId",
            "budgetReservationId",
            "maxOutputTokens",
            "toolPlanHash",
            "childAuthority",
            "childTools",
            "costBudget",
            "wallClockDeadline",
        }
        self.assertEqual(set(output), expected_keys)
        self.assertEqual(output["childAuthority"], ["read"])
        self.assertEqual(output["childTools"], ["read"])
        self.assertEqual(output["costBudget"], "1.2500")
        baseline_digest = digest_object(output, domain="delta-subagent-execution-spec")
        for field_name in (
            "provider",
            "model",
            "reasoningEffort",
            "childAuthority",
            "childTools",
            "costBudget",
            "wallClockDeadline",
            "toolPlanHash",
        ):
            changed = dict(output)
            changed[field_name] = "changed"
            with self.subTest(bound_field=field_name):
                self.assertNotEqual(
                    baseline_digest,
                    digest_object(changed, domain="delta-subagent-execution-spec"),
                )

        for missing in ("costBudget", "wallClockDeadline", "toolPlanHash"):
            denied_payload = dict(payload)
            del denied_payload[missing]
            denied = invocation(
                "elmos-subagent-model-execution-spec",
                denied_payload,
                invocation_id=f"subagent-missing-{missing}",
            )
            result = runtime.execute(
                denied,
                context=context(),
                trusted_authority=authority_for(denied),
            )
            with self.subTest(missing=missing):
                self.assertEqual(result.status, ResultStatus.DENIED)
        invalid_fields = (
            {**payload, "costBudget": "1e3"},
            {
                **payload,
                "wallClockDeadline": (
                    datetime.now(UTC) - timedelta(seconds=1)
                ).isoformat(),
            },
            {**payload, "toolPlanHash": "sha256:" + "f" * 64},
        )
        for index, denied_payload in enumerate(invalid_fields):
            denied = invocation(
                "elmos-subagent-model-execution-spec",
                denied_payload,
                invocation_id=f"subagent-invalid-field-{index}",
            )
            result = runtime.execute(
                denied,
                context=context(),
                trusted_authority=authority_for(denied),
            )
            with self.subTest(invalid_field=index):
                self.assertEqual(result.status, ResultStatus.DENIED)

    def test_interceptor_failure_cancel_and_timeout_are_typed_aborted_outputs(
        self,
    ) -> None:
        def rejected(_: ToolResult) -> ToolResult:
            raise ContractError("repository-controlled detail must not escape")

        def failed(_: ToolResult) -> ToolResult:
            raise RuntimeError("secret provider detail")

        def cancelled(_: ToolResult) -> ToolResult:
            raise asyncio.CancelledError

        def timed_out(_: ToolResult) -> ToolResult:
            raise TimeoutError("provider endpoint detail")

        def invalid(value: ToolResult) -> ToolResult:
            return ToolResult(replace(value.identity, call_id="changed"), True, {})

        cases = {
            "rejected": (rejected, "INTERCEPTOR_REJECTED"),
            "failed": (failed, "INTERCEPTOR_ERROR"),
            "cancelled": (cancelled, "CANCELLED"),
            "timed-out": (timed_out, "TIMED_OUT"),
            "invalid": (invalid, "VALIDATION_FAILED"),
        }
        for label, (callback, expected_kind) in cases.items():
            observed: list[Mapping[str, Any]] = []
            calls = [0]

            def instrumented(value: ToolResult) -> ToolResult:
                calls[0] += 1
                return callback(value)

            def durable_hook(
                trusted_context: SecurityContext,
                trusted_authority: RuntimeAssuranceAuthority,
                descriptor: Any,
                request: DeltaInvocation,
                output: Any,
            ) -> Any:
                del trusted_context, trusted_authority, descriptor, request
                if isinstance(output, Mapping):
                    observed.append(output)
                return output

            runtime = DeltaSkillRuntime(
                interceptors={"test-interceptor": ("v1", instrumented)},
                durable_commit_hook=durable_hook,
            )
            invocation_id = f"interceptor-{label}"
            request = invocation(
                "elmos-tool-result-interception-commit",
                {
                    "rawResult": {
                        "identity": {
                            "invocationId": invocation_id,
                            "callId": "pending-call",
                            "executionPlanHash": PLAN_DIGEST,
                            "environmentId": "environment",
                            "authoritySnapshotId": AUTHORITY_REVISION,
                        },
                        "ok": True,
                        "content": {"value": "untrusted"},
                    },
                    "attempt": 1,
                    "interceptorIds": ["test-interceptor"],
                },
                invocation_id=invocation_id,
            )
            output = self.output_for(runtime, request)
            with self.subTest(case=label):
                self.assertEqual(output["commitState"], "ABORTED")
                self.assertEqual(output["failureKind"], expected_kind)
                self.assertIsInstance(output["failureReason"], str)
                self.assertNotIn("secret", output["failureReason"])
                self.assertNotIn("repository-controlled", output["failureReason"])
                self.assertIn("rawResultRef", output)
                self.assertIn("effectiveResultRef", output)
                self.assertEqual(len(observed), 1)
                self.assertEqual(observed[0], output)
            replayed = self.output_for(runtime, request)
            with self.subTest(replay=label):
                self.assertEqual(replayed, output)
                self.assertEqual(calls, [1])
                self.assertEqual(observed, [output, output])


class HostPolicyAndTypedBindingClosureTests(unittest.TestCase):
    def test_tool_result_commit_key_is_collision_free_and_restart_safe(self) -> None:
        first_identity = CallIdentity(
            "a:b", "c", PLAN_DIGEST, "environment", AUTHORITY_REVISION
        )
        second_identity = CallIdentity(
            "a", "b:c", PLAN_DIGEST, "environment", AUTHORITY_REVISION
        )
        first_key = _tool_result_commit_key("a:b", "c", 1, 1)
        second_key = _tool_result_commit_key("a", "b:c", 1, 1)
        self.assertNotEqual(first_key, second_key)

        coordinator = ResultLifecycleCoordinator()
        first = coordinator.commit(
            ToolResult(first_identity, True, {"result": "first"}),
            (),
            attempt=1,
            epoch=1,
        )
        second = coordinator.commit(
            ToolResult(second_identity, True, {"result": "second"}),
            (),
            attempt=1,
            epoch=1,
        )
        self.assertEqual(first.commit_key, first_key)
        self.assertEqual(second.commit_key, second_key)

        restarted = ResultLifecycleCoordinator()
        restarted.restore(first, attempt=1, epoch=1)
        restarted.restore(second, attempt=1, epoch=1)
        self.assertEqual(restarted.publish(first_key).commit_state.value, "PUBLISHED")
        self.assertEqual(
            restarted.abort(
                second_key,
                failure_reason="independent lifecycle cancellation",
            ).commit_state.value,
            "ABORTED",
        )

    def test_resource_lifecycle_uses_persisted_identity_not_operation_id(self) -> None:
        runtime = DeltaSkillRuntime()
        commit_request = invocation(
            "elmos-tool-result-interception-commit",
            {
                "rawResult": {
                    "identity": {
                        "invocationId": "tool-commit-operation",
                        "callId": "pending-call",
                        "executionPlanHash": PLAN_DIGEST,
                        "environmentId": "environment",
                        "authoritySnapshotId": AUTHORITY_REVISION,
                    },
                    "ok": True,
                    "content": {"value": "committed"},
                },
                "attempt": 1,
                "interceptorIds": [],
            },
            invocation_id="tool-commit-operation",
        )
        committed = runtime.execute(
            commit_request,
            context=context(),
            trusted_authority=authority_for(commit_request),
        )
        self.assertEqual(committed.status, ResultStatus.COMMITTED)
        committed_record = runtime.read_evidence(context(), committed.evidence_refs[0])
        committed_output = committed_record["output"]
        self.assertIsInstance(committed_output, Mapping)
        assert isinstance(committed_output, Mapping)
        commit_key = _tool_result_commit_key(
            "tool-commit-operation", "pending-call", 1, 1
        )
        self.assertEqual(committed_output["commitState"], "COMMITTED")

        publish_request = invocation(
            "elmos-tool-result-interception-commit",
            {
                "action": "publish",
                "commitKey": commit_key,
                "callId": "pending-call",
                "attempt": 1,
                "executionEpoch": 1,
            },
            invocation_id="tool-publish-operation",
        )
        published = runtime.execute(
            publish_request,
            context=context(),
            trusted_authority=authority_for(publish_request),
        )
        self.assertEqual(published.status, ResultStatus.COMMITTED)
        published_output = runtime.read_evidence(context(), published.evidence_refs[0])[
            "output"
        ]
        self.assertIsInstance(published_output, Mapping)
        assert isinstance(published_output, Mapping)
        self.assertEqual(published_output["commitState"], "PUBLISHED")
        self.assertEqual(
            published_output["callIdentity"]["invocationId"],
            commit_request.invocation_id,
        )

        expires_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        issue_request = invocation(
            "elmos-invocation-scoped-capability-lease",
            {
                "action": "issue",
                "leaseId": "lease-across-operations",
                "environmentId": "environment",
                "authoritySnapshotId": AUTHORITY_REVISION,
                "capabilities": ["event.register"],
                "delegationAllowed": False,
                "expiresAt": expires_at,
            },
            invocation_id="lease-issue-operation",
        )
        self.assertEqual(
            runtime.execute(
                issue_request,
                context=context(),
                trusted_authority=authority_for(issue_request),
            ).status,
            ResultStatus.COMMITTED,
        )
        use_request = invocation(
            "elmos-invocation-scoped-capability-lease",
            {
                "action": "use",
                "leaseId": "lease-across-operations",
                "capability": "event.register",
            },
            invocation_id="lease-use-operation",
        )
        used = runtime.execute(
            use_request,
            context=context(),
            trusted_authority=authority_for(use_request),
        )
        self.assertEqual(used.status, ResultStatus.COMMITTED)
        used_output = runtime.read_evidence(context(), used.evidence_refs[0])["output"]
        self.assertIsInstance(used_output, Mapping)
        assert isinstance(used_output, Mapping)
        self.assertEqual(used_output["invocationId"], issue_request.invocation_id)
        revoke_request = invocation(
            "elmos-invocation-scoped-capability-lease",
            {
                "action": "revoke",
                "leaseId": "lease-across-operations",
                "reason": "COMPLETED",
            },
            invocation_id="lease-revoke-operation",
        )
        revoked = runtime.execute(
            revoke_request,
            context=context(),
            trusted_authority=authority_for(revoke_request),
        )
        self.assertEqual(revoked.status, ResultStatus.COMMITTED)
        revoked_output = runtime.read_evidence(context(), revoked.evidence_refs[0])[
            "output"
        ]
        self.assertIsInstance(revoked_output, Mapping)
        assert isinstance(revoked_output, Mapping)
        self.assertEqual(revoked_output["state"], "REVOKED")
        self.assertEqual(revoked_output["invocationId"], issue_request.invocation_id)

    def test_restart_safe_signer_and_required_working_directory(self) -> None:
        key = b"restart-safe-host-security-key-000001"
        bindings = authority("security-restart").security_bindings
        broker = SecurityContextBroker(
            HostSecurityContextSigner(key, key_id="key-1", issuer="host")
        )
        minted = broker.mint_context(
            eligible=True,
            account_stable=True,
            bindings=bindings,
            entitlements={"role": "operator"},
        )
        self.assertEqual(minted.status, "VERIFIED")
        restarted = SecurityContextBroker(
            HostSecurityContextSigner(key, key_id="key-1", issuer="host")
        )
        self.assertEqual(restarted.verify(minted), minted)
        self.assertEqual(
            SecurityContextBroker()
            .mint_context(
                eligible=True,
                account_stable=True,
                bindings=bindings,
                entitlements={},
            )
            .status,
            "UNKNOWN",
        )
        from elmos_proof_harness.delta import PermissionProfile

        with self.assertRaisesRegex(ContractError, "working_directory is required"):
            PermissionProfile(("/workspace",), "deny", False)
        with self.assertRaisesRegex(ContractError, "contained"):
            PermissionProfile(("/workspace",), "deny", False, "/outside")
        self.assertEqual(
            PermissionProfile(
                ("/workspace",), "deny", False, "/workspace/project"
            ).to_wire()["workingDirectory"],
            "/workspace/project",
        )

    def test_skill_signature_uses_actual_full_provenance_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "SKILL.md"
            skill.write_bytes(b"---\nname: signed\n---\n")
            package_digest = digest_bytes(
                skill.read_bytes(), domain="delta-skill-package"
            )
            policy = SkillTrustDomainPolicy(
                {"ENTERPRISE": root},
                publishers={"ENTERPRISE": {"publisher"}},
            )
            expected = policy.signature_envelope(
                skill_id="signed-skill",
                publisher="publisher",
                origin="catalog",
                canonical_uri=skill.resolve().as_uri(),
                package_digest=package_digest,
                trust_domain="ENTERPRISE",
                install_scope="project",
                authorization_semantics=("tool-authority",),
            )

            def verify(envelope: bytes, signature: str) -> bool:
                return envelope == expected and signature == "signature"

            runtime = DeltaSkillRuntime(
                skill_trust_policy=policy, skill_signature_verifier=verify
            )
            payload: dict[str, object] = {
                "skillPath": "SKILL.md",
                "provenance": {
                    "skillId": "signed-skill",
                    "publisher": "publisher",
                    "origin": "catalog",
                    "canonicalUri": skill.resolve().as_uri(),
                    "packageDigest": package_digest,
                    "trustDomain": "ENTERPRISE",
                    "installScope": "project",
                    "authorizationSemantics": ["tool-authority"],
                    "signature": "signature",
                },
            }
            exact = invocation(
                "elmos-skill-trust-domain-provenance",
                payload,
                invocation_id="skill-envelope",
            )
            self.assertEqual(
                runtime.execute(
                    exact,
                    context=context(),
                    trusted_authority=authority_for(exact),
                ).status,
                ResultStatus.COMMITTED,
            )
            drifted_payload = dict(payload)
            assert isinstance(payload["provenance"], Mapping)
            drifted_payload["provenance"] = dict(
                payload["provenance"], origin="drifted"
            )
            drifted = invocation(
                "elmos-skill-trust-domain-provenance",
                drifted_payload,
                invocation_id="skill-envelope-drift",
            )
            self.assertEqual(
                runtime.execute(
                    drifted,
                    context=context(),
                    trusted_authority=authority_for(drifted),
                ).status,
                ResultStatus.DENIED,
            )

    def test_pending_call_exact_binding_and_interceptor_lifecycle_order(self) -> None:
        order: list[str] = []

        def callback(result: ToolResult) -> ToolResult:
            del result
            order.append("callback")
            raise TimeoutError

        def begin(*args: Any) -> None:
            self.assertTrue(str(args[-1]).startswith("cas:"))
            order.append("begin")

        terminal: list[Mapping[str, Any]] = []

        def abort_hook(*args: Any) -> None:
            output = args[-1]
            assert isinstance(output, Mapping)
            terminal.append(output)
            order.append("terminal")

        runtime = DeltaSkillRuntime(
            interceptors={"timeout": ("1", callback)},
            tool_result_begin_hook=begin,
            tool_result_terminal_hook=abort_hook,
        )
        request = invocation(
            "elmos-tool-result-interception-commit",
            {
                "rawResult": {
                    "identity": {
                        "invocationId": "tool-lifecycle",
                        "callId": "pending-call",
                        "executionPlanHash": PLAN_DIGEST,
                        "environmentId": "environment",
                        "authoritySnapshotId": AUTHORITY_REVISION,
                    },
                    "ok": True,
                    "content": {},
                },
                "attempt": 1,
                "interceptorIds": ["timeout"],
            },
            invocation_id="tool-lifecycle",
        )
        result = runtime.execute(
            request,
            context=context(),
            trusted_authority=authority_for(request),
        )
        self.assertEqual(result.status, ResultStatus.COMMITTED)
        self.assertEqual(order, ["begin", "callback", "terminal"])
        self.assertEqual(terminal[0]["failureKind"], "TIMED_OUT")
        mixed_payload = dict(request.payload)
        raw = dict(mixed_payload["rawResult"])
        identity = dict(raw["identity"])
        identity["environmentId"] = "other-environment"
        raw["identity"] = identity
        mixed_payload["rawResult"] = raw
        mixed = invocation(
            "elmos-tool-result-interception-commit",
            mixed_payload,
            invocation_id="tool-lifecycle",
        )
        trusted = replace(
            authority_for(mixed),
            environment_ids=frozenset({"environment", "other-environment"}),
        )
        self.assertEqual(
            DeltaSkillRuntime()
            .execute(mixed, context=context(), trusted_authority=trusted)
            .status,
            ResultStatus.DENIED,
        )
        attempt_payload = dict(request.payload)
        attempt_payload["attempt"] = 2
        attempt_drift = invocation(
            "elmos-tool-result-interception-commit",
            attempt_payload,
            invocation_id="tool-lifecycle",
        )
        self.assertEqual(
            DeltaSkillRuntime()
            .execute(
                attempt_drift,
                context=context(),
                trusted_authority=authority_for(attempt_drift),
            )
            .status,
            ResultStatus.DENIED,
        )

    def test_production_readiness_requires_trusted_deadline_interceptor_and_hooks(
        self,
    ) -> None:
        class DurableEvidence(DeltaEvidenceStore):
            durable = True

        class TrustedInterceptor:
            trusted_for_production = True
            deadline_enforced = True

            def __call__(self, result: ToolResult) -> ToolResult:
                return result

        class ProductionAuthorityProvider:
            base_origin_receipt_verified = True
            host_envelope_signatures_verified = True
            host_envelope_issuer_durable = True

            def __call__(
                self,
                trusted_context: SecurityContext,
                request: DeltaInvocation,
            ) -> RuntimeAssuranceAuthority:
                del trusted_context
                return authority_for(request)

            def verify_origin_receipt(
                self,
                trusted_context: SecurityContext,
                request: DeltaInvocation,
                origin: BaseSkillOriginBinding,
                *,
                deadline: datetime | None,
            ) -> bool:
                del trusted_context, request, origin, deadline
                return True

            def issue_host_envelope(
                self,
                *,
                kind: str,
                payload: Mapping[str, Any],
            ) -> Any:
                del kind, payload
                raise AssertionError("readiness probe does not issue envelopes")

            def verify_host_envelope(
                self,
                *,
                kind: str,
                payload: Mapping[str, Any],
                envelope: Any,
            ) -> bool:
                del kind, payload, envelope
                return True

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            from elmos_proof_harness.delta import PermissionProfile

            runtime = DeltaSkillRuntime(
                permission_profiles={
                    ("provider", "1"): {
                        "locked": PermissionProfile(
                            ("/workspace",), "deny", False, "/workspace"
                        )
                    }
                },
                authorized_producers={("tenant", "project"): {"producer"}},
                allowed_subagent_models={("openai", "gpt-5")},
                skill_trust_policy=SkillTrustDomainPolicy(
                    {"REPOSITORY": root},
                    publishers={"REPOSITORY": {"publisher"}},
                ),
                skill_signature_verifier=lambda envelope, signature: bool(
                    envelope and signature
                ),
                host_security_signer=HostSecurityContextSigner(
                    b"production-host-security-key-00001",
                    key_id="production",
                    issuer="host",
                ),
                privileged_path_policy=PrivilegedPathPolicy(),
                managed_worktree_registry=ManagedWorktreeRegistry(),
                interceptors={"trusted": ("1", TrustedInterceptor())},
                authority_provider=ProductionAuthorityProvider(),
                evidence_store=DurableEvidence(),
                tool_result_begin_hook=lambda *args: None,
                tool_result_terminal_hook=lambda *args: None,
                durable_commit_hook=lambda *args: None,
            )
            self.assertEqual(runtime.readiness(production=True)[0], True)


class StatefulActionSurfaceClosureTests(unittest.TestCase):
    @staticmethod
    def output(
        runtime: DeltaSkillRuntime,
        request: DeltaInvocation,
        trusted: RuntimeAssuranceAuthority,
    ) -> Mapping[str, Any]:
        result = runtime.execute(request, context=context(), trusted_authority=trusted)
        if result.status != ResultStatus.COMMITTED:
            raise AssertionError(result.message)
        record = runtime.read_evidence(context(), result.evidence_refs[0])
        output = record["output"]
        assert isinstance(output, Mapping)
        return output

    def test_environment_refresh_is_digest_bound_and_narrowing_only(self) -> None:
        previous = {"network": "deny", "permissions": ["read", "write"], "limit": 10}
        narrowed = {"network": "deny", "permissions": ["read"], "limit": 5}
        binding = EnvironmentSettingsBinding(
            "server",
            "environment",
            narrowed,
            digest_object(narrowed, domain="delta-environment-settings-authority"),
            previous,
            digest_object(previous, domain="delta-environment-settings-authority"),
            "previous-snapshot",
        )
        payload = {
            "action": "refresh",
            "serverId": "server",
            "settingsAuthority": narrowed,
            "settingsDigest": binding.settings_digest,
            "expectedSnapshotId": "previous-snapshot",
            "expectedGeneration": 1,
            "ownerSnapshotId": AUTHORITY_REVISION,
            "ownerPermissions": ["read", "write"],
            "ownerId": "owner",
            "parentSnapshotId": PARENT_AUTHORITY_REVISION,
            "parentPermissions": ["read"],
            "parentOwnerId": "parent",
            "environmentId": "environment",
            "permissionProfileVersion": "profile-v1",
            "ownerEffectivePolicyHash": POLICY_DIGEST,
            "parentEffectivePolicyHash": POLICY_DIGEST,
            "policyPermissions": ["read"],
            "snapshotId": RESULT_AUTHORITY_REVISION,
        }
        request = invocation(
            "elmos-environment-attachment-authority",
            payload,
            invocation_id="environment-refresh",
        )
        trusted = replace(
            authority_for(request),
            environment_settings_bindings=(binding,),
        )
        output = self.output(DeltaSkillRuntime(), request, trusted)
        self.assertEqual(
            output["turnEnvironment"]["settingsDigest"], binding.settings_digest
        )
        widened = dict(narrowed, mutable=True)
        widened_binding = EnvironmentSettingsBinding(
            "server",
            "environment",
            widened,
            digest_object(widened, domain="delta-environment-settings-authority"),
            previous,
            digest_object(previous, domain="delta-environment-settings-authority"),
            "previous-snapshot",
        )
        denied_payload = dict(payload, settingsAuthority=widened)
        denied_payload["settingsDigest"] = widened_binding.settings_digest
        denied = invocation(
            "elmos-environment-attachment-authority",
            denied_payload,
            invocation_id="environment-widen",
        )
        self.assertEqual(
            DeltaSkillRuntime()
            .execute(
                denied,
                context=context(),
                trusted_authority=replace(
                    authority_for(denied),
                    environment_settings_bindings=(widened_binding,),
                ),
            )
            .status,
            ResultStatus.DENIED,
        )

    def test_executor_replace_emits_three_pending_effects_and_blocks_activation(
        self,
    ) -> None:
        runtime = DeltaSkillRuntime()
        bindings = frozenset(
            {("environment", "old-executor"), ("environment", "new-executor")}
        )

        def run(payload: dict[str, object], invocation_id: str) -> DeltaResult:
            request = invocation(
                "elmos-executor-generation-fencing",
                payload,
                invocation_id=invocation_id,
            )
            return runtime.execute(
                request,
                context=context(),
                trusted_authority=replace(
                    authority_for(request), executor_bindings=bindings
                ),
            )

        self.assertEqual(
            run(
                {
                    "generation": 1,
                    "connectionEpoch": 1,
                    "environmentId": "environment",
                    "executorIdentity": "old-executor",
                    "action": "activate",
                    "liveProbeEvidenceRef": "evidence",
                },
                "executor-old",
            ).status,
            ResultStatus.COMMITTED,
        )
        replacement = run(
            {
                "generation": 1,
                "connectionEpoch": 1,
                "environmentId": "environment",
                "executorIdentity": "new-executor",
                "action": "replace",
            },
            "executor-replace",
        )
        output = runtime.read_evidence(context(), replacement.evidence_refs[0])[
            "output"
        ]
        self.assertEqual(len(output["reconciliationEffects"]), 3)
        self.assertFalse(output["activationAllowed"])
        self.assertEqual(
            run(
                {
                    "generation": 2,
                    "connectionEpoch": 2,
                    "environmentId": "environment",
                    "executorIdentity": "new-executor",
                    "action": "activate",
                    "liveProbeEvidenceRef": "evidence",
                },
                "executor-early",
            ).status,
            ResultStatus.DENIED,
        )

    def test_workspace_crash_takeover_requires_verified_pending_state(self) -> None:
        registry = mock.Mock(spec=ManagedWorktreeRegistry)
        registry.require.return_value = SimpleNamespace(
            repository_id="repository", base_revision="revision"
        )
        runtime = DeltaSkillRuntime(managed_worktree_registry=registry)
        grant = WorkspaceAuthority(
            "workspace", "repository", "revision", ("src",), frozenset({"old", "new"})
        )

        def run(payload: dict[str, object], invocation_id: str) -> DeltaResult:
            request = invocation(
                "elmos-workspace-ownership-lease", payload, invocation_id=invocation_id
            )
            return runtime.execute(
                request,
                context=context(),
                trusted_authority=replace(
                    authority_for(request),
                    workspace_authorities=(grant,),
                    verified_evidence_refs=frozenset(
                        {"crash-evidence", "base-origin-receipt"}
                    ),
                ),
            )

        self.assertEqual(
            run(
                {
                    "workspaceId": "workspace",
                    "ownerExecutionId": "old",
                    "generation": 1,
                    "repositoryId": "repository",
                    "baseRevision": "revision",
                    "writeScopes": ["src"],
                    "action": "bind",
                },
                "workspace-bind",
            ).status,
            ResultStatus.COMMITTED,
        )
        takeover = {
            "workspaceId": "workspace",
            "newOwnerExecutionId": "new",
            "generation": 1,
            "action": "takeover",
        }
        self.assertEqual(run(takeover, "workspace-direct").status, ResultStatus.DENIED)
        self.assertEqual(
            run(
                {
                    "workspaceId": "workspace",
                    "generation": 1,
                    "action": "markTakeoverPending",
                    "crashEvidenceRef": "unverified",
                },
                "workspace-unverified",
            ).status,
            ResultStatus.DENIED,
        )
        self.assertEqual(
            run(
                {
                    "workspaceId": "workspace",
                    "generation": 1,
                    "action": "markTakeoverPending",
                    "crashEvidenceRef": "crash-evidence",
                },
                "workspace-pending",
            ).status,
            ResultStatus.COMMITTED,
        )
        self.assertEqual(
            run(takeover, "workspace-takeover").status, ResultStatus.COMMITTED
        )
        self.assertGreaterEqual(registry.require.call_count, 5)

    def test_durable_event_actions_and_ingress_page_are_hook_ready(self) -> None:
        registration = EventRegistration(
            "optional.event",
            "owner",
            1,
            "OPTIONAL_OBSERVATION",
            "elmos.object.v1",
            "none",
            (),
            "FULL",
        )
        runtime = DeltaSkillRuntime(optional_unknown_event_types=("optional.event",))

        def event_run(
            payload: dict[str, object], invocation_id: str
        ) -> Mapping[str, Any]:
            request = invocation(
                "elmos-registered-durable-plugin-events",
                payload,
                invocation_id=invocation_id,
            )
            return self.output(
                runtime,
                request,
                authority_for(request, event_registrations=(registration,)),
            )

        event_run(
            {"action": "register", "registration": registration.to_wire()},
            "event-register",
        )
        event = DurableEventEnvelope(
            "event-1", "optional.event", 1, {"value": 1}, "correlation"
        ).to_wire()
        actions: tuple[tuple[dict[str, object], str], ...] = (
            ({"action": "append", "event": event}, "event-append"),
            (
                {
                    "action": "replay",
                    "event": event,
                    "targetVersion": 1,
                    "unknownOptional": False,
                },
                "event-replay",
            ),
            (
                {"action": "forkReplay", "forkId": "fork", "events": [event]},
                "event-fork",
            ),
            (
                {
                    "action": "migrationReplay",
                    "migrationId": "migration",
                    "events": [event],
                    "targetVersions": {"optional.event": 1},
                },
                "event-migration",
            ),
            (
                {
                    "action": "preflightOwnerChange",
                    "operation": "UNINSTALL",
                    "eventType": "optional.event",
                    "persistedEvents": [],
                },
                "event-preflight",
            ),
        )
        for action_payload, invocation_id in actions:
            with self.subTest(action=action_payload["action"]):
                self.assertTrue(
                    event_run(action_payload, invocation_id)["durableRequired"]
                )
        page = invocation(
            "elmos-typed-external-ingress",
            {
                "action": "page",
                "correlationId": "correlation",
                "limit": 50,
                "afterOccurredAt": None,
                "afterIngressId": None,
            },
            invocation_id="ingress-page",
        )
        page_output = self.output(DeltaSkillRuntime(), page, authority_for(page))
        self.assertTrue(page_output["readOnly"])
        self.assertEqual(
            page_output["keysetCursor"],
            {"afterOccurredAt": None, "afterIngressId": None},
        )


if __name__ == "__main__":
    unittest.main()
