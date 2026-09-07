from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from elmos_multimodal_intake.canonical import canonical_digest, sha256_bytes
from elmos_multimodal_intake.downstream_agent import (
    DownstreamAgentBridge,
    DownstreamToolInvocation,
)
from elmos_multimodal_intake.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from elmos_multimodal_intake.models import TenantContext
from elmos_multimodal_intake.skill_runtime import RuntimeContext
from elmos_multimodal_intake.store import IntakeStore


def _receipt(body: dict[str, Any]) -> dict[str, Any]:
    value = dict(body)
    value["receipt_digest"] = canonical_digest(value)
    return value


def _source(
    *, tenant_id: str, project_id: str, subject_id: str, package_version: int,
    kind: str, suffix: str, expires_at: str,
) -> dict[str, Any]:
    normalized = {
        "summary": f"normalized {kind.lower()} {suffix}",
        "trust_label": "UNTRUSTED_CONTENT",
        "anchors": [
            {
                "source_id": f"source-{suffix}",
                "locator": f"package://{package_version}/{kind.lower()}/{suffix}",
                "source_digest": sha256_bytes(f"anchor-{suffix}".encode()),
            }
        ],
    }
    return _receipt(
        {
            "schema_version": "elmos-downstream-source-receipt-v1",
            "receipt_id": f"source-receipt-{suffix}",
            "tenant_id": tenant_id,
            "project_id": project_id,
            "subject_id": subject_id,
            "package_version": package_version,
            "source_kind": kind,
            "source_id": f"source-{suffix}",
            "normalized": normalized,
            "source_digest": canonical_digest(normalized),
            "verified": True,
            "prompt_safe": True,
            "raw_asset_included": False,
            "expires_at": expires_at,
            "issuer_id": "normalizer-1",
            "verifier_id": "source-verifier-1",
        }
    )


def _tool(
    *, tenant_id: str, project_id: str, subject_id: str, package_version: int,
    tool_id: str, input_document: dict[str, Any], issued_at: str, expires_at: str,
) -> dict[str, Any]:
    return _receipt(
        {
            "schema_version": "elmos-downstream-tool-receipt-v1",
            "receipt_id": "tool-receipt-1",
            "tenant_id": tenant_id,
            "project_id": project_id,
            "subject_id": subject_id,
            "package_version": package_version,
            "tool_id": tool_id,
            "capability_version": "1.0",
            "input_digest": canonical_digest(input_document),
            "scope_digest": canonical_digest(
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "subject_id": subject_id,
                    "package_version": package_version,
                    "tool_id": tool_id,
                }
            ),
            "issued_at": issued_at,
            "expires_at": expires_at,
            "single_use": True,
            "revoked": False,
            "verification_state": "VERIFIED",
            "issuer_id": "capability-issuer-1",
            "verifier_id": "capability-verifier-1",
        }
    )


def _result_receipt(
    invocation: DownstreamToolInvocation,
    *,
    verifier_id: str = "result-verifier-1",
) -> dict[str, Any]:
    result = b"verified downstream result"
    digest = sha256_bytes(result)
    return _receipt(
        {
            "schema_version": "elmos-downstream-result-receipt-v1",
            "receipt_id": f"result-receipt-{invocation.execution_id}",
            "tenant_id": invocation.tenant_id,
            "project_id": invocation.project_id,
            "context_id": invocation.context_id,
            "grant_id": invocation.grant_id,
            "execution_id": invocation.execution_id,
            "tool_id": invocation.tool_id,
            "subject_id": invocation.subject_id,
            "input_digest": invocation.input_digest,
            "claim_fence": invocation.claim_fence,
            "executor_id": "gateway-worker-1",
            "verifier_id": verifier_id,
            "verification_method": "HOST_VERIFIED",
            "verification_state": "VERIFIED",
            "result_digest": digest,
            "result_byte_count": len(result),
            "result_locator": f"cas://sha256/{digest}",
            "completed_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        }
    )


class _VerifiedAdapter:
    def __init__(self) -> None:
        self.receipt: dict[str, Any] | None = None

    def execute(self, invocation: DownstreamToolInvocation) -> dict[str, Any]:
        self.receipt = _result_receipt(invocation)
        return self.receipt


class _TimeoutAfterDispatchAdapter:
    def __init__(self) -> None:
        self.invocation: DownstreamToolInvocation | None = None

    def execute(self, invocation: DownstreamToolInvocation) -> dict[str, Any]:
        self.invocation = invocation
        raise TimeoutError("outcome deliberately unknown")


class _IndependentVerifier:
    def verify(
        self,
        invocation: DownstreamToolInvocation,
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        assert candidate["execution_id"] == invocation.execution_id
        assert candidate["result_locator"].endswith(candidate["result_digest"])
        return candidate


@pytest.fixture()
def downstream(tmp_path: Path) -> tuple[
    IntakeStore, DownstreamAgentBridge, RuntimeContext, TenantContext, dict[str, Any]
]:
    store = IntakeStore(tmp_path / "intake.sqlite3")
    tenant = TenantContext("tenant-a", "project-a", "owner-a")
    store.bootstrap_project(tenant)
    with store.transaction() as connection:
        connection.execute(
            "INSERT INTO project_package_versions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                tenant.tenant_id,
                tenant.project_id,
                1,
                None,
                "ACTIVE",
                3,
                "1" * 64,
                "2" * 64,
                tenant.actor_id,
                datetime.now(UTC).replace(microsecond=0).isoformat(),
            ),
        )
    now = datetime.now(UTC).replace(microsecond=0)
    expires = (now + timedelta(minutes=5)).isoformat()
    sources = [
        _source(
            tenant_id=tenant.tenant_id,
            project_id=tenant.project_id,
            subject_id="task-subject-1",
            package_version=1,
            kind=kind,
            suffix=str(index),
            expires_at=expires,
        )
        for index, kind in enumerate(
            ("CONTENT_BLOCK", "REQUIREMENT", "REPOSITORY_MAP"), start=1
        )
    ]
    input_document = {
        "schema_version": "elmos-downstream-tool-input-v1",
        "operation_id": "summarize",
        "source_set_digest": canonical_digest(
            [item["receipt_digest"] for item in sources]
        ),
        "source_receipt_ids": ["source-receipt-2"],
        "parameters": {"requirement_id": "req-1"},
    }
    tool = _tool(
        tenant_id=tenant.tenant_id,
        project_id=tenant.project_id,
        subject_id="task-subject-1",
        package_version=1,
        tool_id="summarize-v1",
        input_document=input_document,
        issued_at=now.isoformat(),
        expires_at=expires,
    )
    context = RuntimeContext(
        tenant_id=tenant.tenant_id,
        project_id=tenant.project_id,
        actor_id=tenant.actor_id,
        request_id="request-build-1",
        trace_id="trace-build-1",
        idempotency_key="build-context-key-0001",
        policy={
            "downstream_agent": {
                "schema_version": "elmos-downstream-agent-policy-v1",
                "tenant_id": tenant.tenant_id,
                "project_id": tenant.project_id,
                "version": "policy-v1",
                "allowed_tool_ids": ["summarize-v1"],
                "max_context_sources": 10,
                "max_context_chars": 100_000,
                "max_grant_ttl_seconds": 600,
            }
        },
        capabilities={
            "downstream_agent_receipts": {
                "schema_version": "elmos-downstream-agent-receipts-v1",
                "tenant_id": tenant.tenant_id,
                "project_id": tenant.project_id,
                "verified": True,
                "source_receipts": sources,
                "tool_receipts": [tool],
                "result_receipts": [],
            }
        },
    )
    try:
        yield store, DownstreamAgentBridge(store), context, tenant, input_document
    finally:
        store.close()


def _build(
    bridge: DownstreamAgentBridge,
    context: RuntimeContext,
    *,
    with_tool: bool = True,
) -> dict[str, Any]:
    return dict(
        bridge.handle(
            "elmos-downstream-agent-integration",
            context,
            {
                "operation": "build_context",
                "task_id": "task-1",
                "subject_id": "task-subject-1",
                "package_version": 1,
                "source_receipt_ids": [
                    "source-receipt-1",
                    "source-receipt-2",
                    "source-receipt-3",
                ],
                "tool_receipt_ids": ["tool-receipt-1"] if with_tool else [],
            },
        )
    )


def test_build_context_is_durable_exact_and_content_cannot_grant_tools(downstream) -> None:
    store, bridge, context, _tenant, _input = downstream
    first = _build(bridge, context)
    assert _build(bridge, context) == first
    assert first["outputs"]["context"]["raw_assets_in_prompt"] is False
    assert first["outputs"]["context"]["tool_authority_from_content"] is False
    assert first["outputs"]["context"]["downstream_execution_state"] == "NOT_RUN"
    assert first["outputs"]["context"]["external_evidence"] == "NOT_RUN"
    assert first["outputs"]["context"]["certification"] == "NOT_CERTIFIED"
    assert {
        source["trust_label"] for source in first["outputs"]["context"]["sources"]
    } == {"UNTRUSTED_CONTENT"}
    assert first["outputs"]["execution_state"] == "NOT_RUN"
    assert first["outputs"]["external_evidence"] == "NOT_RUN"
    assert first["outputs"]["certification"] == "NOT_CERTIFIED"
    with store.read_transaction() as connection:
        assert connection.execute("SELECT count(*) FROM downstream_agent_contexts").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM downstream_context_sources").fetchone()[0] == 3
        assert connection.execute("SELECT count(*) FROM downstream_tool_grants").fetchone()[0] == 1
        assert connection.execute(
            "SELECT event_type FROM downstream_agent_outbox"
        ).fetchone()[0] == "agent.context.built"


def test_idempotency_tamper_and_public_authority_fields_fail_closed(downstream) -> None:
    _store, bridge, context, _tenant, _input = downstream
    _build(bridge, context)
    with pytest.raises(ConflictError, match="DOWNSTREAM_IDEMPOTENCY_CONFLICT"):
        bridge.handle(
            "elmos-downstream-agent-integration",
            context,
            {
                "operation": "build_context",
                "task_id": "tampered-task",
                "subject_id": "task-subject-1",
                "package_version": 1,
                "source_receipt_ids": [
                    "source-receipt-1", "source-receipt-2", "source-receipt-3"
                ],
                "tool_receipt_ids": ["tool-receipt-1"],
            },
        )
    with pytest.raises(ValidationError, match="DOWNSTREAM_PUBLIC_FIELD_FORBIDDEN"):
        bridge.handle(
            "elmos-downstream-agent-integration",
            replace(context, idempotency_key="forged-command-key-1"),
            {
                "operation": "build_context",
                "task_id": "task-1",
                "subject_id": "task-subject-1",
                "package_version": 1,
                "source_receipt_ids": [
                    "source-receipt-1", "source-receipt-2", "source-receipt-3"
                ],
                "tool_receipt_ids": [],
                "command": ["sh", "-c", "id"],
            },
        )


def test_tenant_scope_hides_context_and_grants(downstream) -> None:
    store, bridge, context, _tenant, _input = downstream
    built = _build(bridge, context)
    context_id = built["outputs"]["context"]["context_id"]
    other = TenantContext("tenant-b", "project-b", "owner-b")
    store.bootstrap_project(other)
    other_ctx = replace(
        context,
        tenant_id=other.tenant_id,
        project_id=other.project_id,
        actor_id=other.actor_id,
        request_id="request-other-1",
        idempotency_key=None,
        policy={},
        capabilities={},
    )
    with pytest.raises(NotFoundError, match="DOWNSTREAM_CONTEXT_NOT_FOUND"):
        bridge.handle(
            "elmos-downstream-agent-integration",
            other_ctx,
            {"operation": "get_context", "context_id": context_id},
        )


def test_gateway_is_allowlisted_single_use_and_result_links_independently(downstream) -> None:
    _store, bridge, context, tenant, input_document = downstream
    built = _build(bridge, context)
    context_id = built["outputs"]["context"]["context_id"]
    grant_id = built["outputs"]["grants"][0]["grant_id"]
    adapter = _VerifiedAdapter()
    gateway = bridge.create_tool_gateway(
        {"summarize-v1": adapter},
        result_verifier=_IndependentVerifier(),
        verifier_id="result-verifier-1",
    )
    execution = gateway.execute(
        tenant,
        context_id=context_id,
        grant_id=grant_id,
        input_document=input_document,
        executor_id="gateway-worker-1",
        idempotency_key="gateway-execute-key-0001",
    )
    assert execution["state"] == "VERIFIED"
    assert execution["result_link_state"] == "NOT_RUN"
    assert gateway.execute(
        tenant,
        context_id=context_id,
        grant_id=grant_id,
        input_document=input_document,
        executor_id="gateway-worker-1",
        idempotency_key="gateway-execute-key-0001",
    ) == execution
    assert adapter.receipt is not None
    registry = dict(context.capabilities["downstream_agent_receipts"])
    registry["result_receipts"] = [adapter.receipt]
    link_context = replace(
        context,
        request_id="request-link-1",
        idempotency_key="link-result-key-0001",
        capabilities={"downstream_agent_receipts": registry},
    )
    linked = bridge.handle(
        "elmos-downstream-agent-integration",
        link_context,
        {
            "operation": "link_result",
            "context_id": context_id,
            "grant_id": grant_id,
            "result_receipt_id": adapter.receipt["receipt_id"],
        },
    )
    assert linked["outputs"]["result_link"]["original_sources_mutated"] is False
    assert linked["outputs"]["result_link"]["executor_id"] != linked["outputs"]["result_link"]["verifier_id"]
    with pytest.raises(ConflictError, match="DOWNSTREAM_GRANT_NOT_EXECUTABLE"):
        gateway.execute(
            tenant,
            context_id=context_id,
            grant_id=grant_id,
            input_document=input_document,
            executor_id="gateway-worker-1",
            idempotency_key="gateway-second-key-0002",
        )


def test_grant_revocation_is_durable_exact_and_prevents_gateway_use(downstream) -> None:
    _store, bridge, context, tenant, input_document = downstream
    built = _build(bridge, context)
    context_id = built["outputs"]["context"]["context_id"]
    grant_id = built["outputs"]["grants"][0]["grant_id"]
    revoke_context = replace(
        context,
        request_id="request-revoke-1",
        idempotency_key="revoke-grant-key-0001",
    )
    payload = {
        "operation": "revoke_grant",
        "context_id": context_id,
        "grant_id": grant_id,
        "reason": "host policy epoch revoked this grant",
    }
    first = bridge.handle("elmos-downstream-agent-integration", revoke_context, payload)
    assert bridge.handle("elmos-downstream-agent-integration", revoke_context, payload) == first
    assert first["outputs"]["state"] == "REVOKED"
    gateway = bridge.create_tool_gateway(
        {"summarize-v1": _VerifiedAdapter()},
        result_verifier=_IndependentVerifier(),
        verifier_id="result-verifier-1",
    )
    with pytest.raises(ConflictError, match="DOWNSTREAM_GRANT_NOT_EXECUTABLE"):
        gateway.execute(
            tenant,
            context_id=context_id,
            grant_id=grant_id,
            input_document=input_document,
            executor_id="gateway-worker-1",
            idempotency_key="revoked-execute-key-1",
        )


def test_missing_host_adapter_is_durable_deny_not_execution(downstream) -> None:
    _store, bridge, context, tenant, input_document = downstream
    built = _build(bridge, context)
    context_id = built["outputs"]["context"]["context_id"]
    grant_id = built["outputs"]["grants"][0]["grant_id"]
    gateway = bridge.create_tool_gateway(
        {}, result_verifier=_IndependentVerifier(), verifier_id="result-verifier-1"
    )
    denied = gateway.execute(
        tenant,
        context_id=context_id,
        grant_id=grant_id,
        input_document=input_document,
        executor_id="gateway-worker-1",
        idempotency_key="missing-adapter-key-1",
    )
    assert denied["state"] == "BLOCKED"
    assert denied["side_effect_authorized"] is False
    assert gateway.execute(
        tenant,
        context_id=context_id,
        grant_id=grant_id,
        input_document=input_document,
        executor_id="gateway-worker-1",
        idempotency_key="missing-adapter-key-1",
    ) == denied


def test_timeout_is_unknown_no_retry_then_verified_receipt_recovers(downstream) -> None:
    _store, bridge, context, tenant, input_document = downstream
    built = _build(bridge, context)
    context_id = built["outputs"]["context"]["context_id"]
    grant_id = built["outputs"]["grants"][0]["grant_id"]
    adapter = _TimeoutAfterDispatchAdapter()
    gateway = bridge.create_tool_gateway(
        {"summarize-v1": adapter},
        result_verifier=_IndependentVerifier(),
        verifier_id="result-verifier-1",
    )
    unknown = gateway.execute(
        tenant,
        context_id=context_id,
        grant_id=grant_id,
        input_document=input_document,
        executor_id="gateway-worker-1",
        idempotency_key="gateway-timeout-key-0001",
    )
    assert unknown["state"] == "UNKNOWN"
    assert unknown["automatic_retry_allowed"] is False
    with pytest.raises(ConflictError, match="RECONCILIATION_REQUIRED"):
        gateway.execute(
            tenant,
            context_id=context_id,
            grant_id=grant_id,
            input_document=input_document,
            executor_id="gateway-worker-1",
            idempotency_key="gateway-timeout-key-0001",
        )
    assert adapter.invocation is not None
    receipt = _result_receipt(adapter.invocation)
    registry = dict(context.capabilities["downstream_agent_receipts"])
    registry["result_receipts"] = [receipt]
    recovered = bridge.handle(
        "elmos-downstream-agent-integration",
        replace(
            context,
            request_id="request-reconcile-1",
            idempotency_key="reconcile-link-key-0001",
            capabilities={"downstream_agent_receipts": registry},
        ),
        {
            "operation": "link_result",
            "context_id": context_id,
            "grant_id": grant_id,
            "result_receipt_id": receipt["receipt_id"],
        },
    )
    assert recovered["code"] == "DOWNSTREAM_RESULT_LINKED"


def test_raw_tool_input_and_self_verified_results_are_rejected(downstream) -> None:
    _store, bridge, context, tenant, input_document = downstream
    built = _build(bridge, context)
    context_id = built["outputs"]["context"]["context_id"]
    grant_id = built["outputs"]["grants"][0]["grant_id"]
    gateway = bridge.create_tool_gateway(
        {"summarize-v1": _VerifiedAdapter()},
        result_verifier=_IndependentVerifier(),
        verifier_id="result-verifier-1",
    )
    with pytest.raises(ValidationError, match="AUTHORITY_OR_RAW_INPUT_FORBIDDEN"):
        gateway.execute(
            tenant,
            context_id=context_id,
            grant_id=grant_id,
            input_document={"command": "python -m untrusted"},
            executor_id="gateway-worker-1",
            idempotency_key="raw-tool-input-key-1",
        )
    self_verifying = _VerifiedAdapter()

    def execute(invocation: DownstreamToolInvocation) -> dict[str, Any]:
        return _result_receipt(invocation, verifier_id="gateway-worker-1")

    self_verifying.execute = execute  # type: ignore[method-assign]
    unknown_gateway = bridge.create_tool_gateway(
        {"summarize-v1": self_verifying},
        result_verifier=_IndependentVerifier(),
        verifier_id="gateway-worker-1",
    )
    unknown = unknown_gateway.execute(
        tenant,
        context_id=context_id,
        grant_id=grant_id,
        input_document=input_document,
        executor_id="gateway-worker-1",
        idempotency_key="self-verified-key-0001",
    )
    assert unknown["state"] == "UNKNOWN"


def test_migration_022_is_dual_root_and_version_bound() -> None:
    engine = Path(__file__).resolve().parents[1]
    root = engine / "migrations" / "022_downstream_agent_integration.sql"
    packaged = (
        engine
        / "src"
        / "elmos_multimodal_intake"
        / "migrations"
        / "022_downstream_agent_integration.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
    assert b"PRAGMA user_version = 22;" in root.read_bytes()
