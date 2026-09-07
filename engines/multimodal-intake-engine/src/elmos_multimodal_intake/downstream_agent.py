"""Durable Skill 28 context, Tool Gateway PEP, and result provenance.

The public bridge can select only opaque receipts from a host-owned verified
registry.  It cannot choose commands, modules, plugins, subprocesses, tool
implementations, or raw asset bytes.  The separately constructed
``DownstreamToolGateway`` is the only execution PEP and every result remains
unlinked until an independent verified receipt is recorded.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, TYPE_CHECKING

from .canonical import (
    canonical_digest,
    canonical_json,
    new_id,
    normalize_sha256,
    require_actor_id,
    require_idempotency_key,
    require_resource_id,
    utc_now,
)
from .errors import (
    AuthorizationError,
    ConflictError,
    IntegrityError,
    NotFoundError,
    ValidationError,
)
from .models import TenantContext, UNTRUSTED_CONTENT
from .store import IntakeStore

if TYPE_CHECKING:
    from .skill_runtime import RuntimeContext


SKILL_NAME = "elmos-downstream-agent-integration"
_SOURCE_KINDS = frozenset({"CONTENT_BLOCK", "REQUIREMENT", "REPOSITORY_MAP"})
_VERIFICATION_METHODS = frozenset({"HOST_VERIFIED", "SIGNATURE_VERIFIED"})
_MAX_RECEIPTS = 256
_MAX_CONTEXT_CHARS = 262_144
_MAX_RESULT_BYTES = 1_073_741_824
_MUTATIONS = frozenset({"build_context", "revoke_grant", "link_result"})
_INTERNAL_FIELDS = frozenset({"operation", "idempotency_key", "trace_id"})
_PUBLIC_FIELDS = {
    "build_context": frozenset(
        {
            "operation",
            "task_id",
            "subject_id",
            "package_version",
            "source_receipt_ids",
            "tool_receipt_ids",
        }
    ),
    "get_context": frozenset({"operation", "context_id"}),
    "get_grant": frozenset({"operation", "context_id", "grant_id"}),
    "revoke_grant": frozenset({"operation", "context_id", "grant_id", "reason"}),
    "link_result": frozenset(
        {"operation", "context_id", "grant_id", "result_receipt_id"}
    ),
    "list_result_links": frozenset({"operation", "context_id"}),
}
_FORBIDDEN_KEYS = frozenset(
    {
        "argv",
        "asset_bytes",
        "binary",
        "blob",
        "capability",
        "capabilities",
        "command",
        "content_base64",
        "content_blocks",
        "executable",
        "file_bytes",
        "module",
        "plugin",
        "raw",
        "raw_asset",
        "raw_bytes",
        "requested_tools",
        "shell",
        "subprocess",
        "tool",
        "tool_id",
    }
)
_SOURCE_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "receipt_id",
        "tenant_id",
        "project_id",
        "subject_id",
        "package_version",
        "source_kind",
        "source_id",
        "normalized",
        "source_digest",
        "verified",
        "prompt_safe",
        "raw_asset_included",
        "expires_at",
        "issuer_id",
        "verifier_id",
        "receipt_digest",
    }
)
_TOOL_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "receipt_id",
        "tenant_id",
        "project_id",
        "subject_id",
        "package_version",
        "tool_id",
        "capability_version",
        "input_digest",
        "scope_digest",
        "issued_at",
        "expires_at",
        "single_use",
        "revoked",
        "verification_state",
        "issuer_id",
        "verifier_id",
        "receipt_digest",
    }
)
_RESULT_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "receipt_id",
        "tenant_id",
        "project_id",
        "context_id",
        "grant_id",
        "execution_id",
        "tool_id",
        "subject_id",
        "input_digest",
        "claim_fence",
        "executor_id",
        "verifier_id",
        "verification_method",
        "verification_state",
        "result_digest",
        "result_byte_count",
        "result_locator",
        "completed_at",
        "receipt_digest",
    }
)


def _text(value: Any, field: str, *, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > maximum
    ):
        raise ValidationError("DOWNSTREAM_FIELD_INVALID", details={"field": field})
    return value


def _identifier(value: Any, field: str) -> str:
    return require_resource_id(_text(value, field, maximum=128), field)


def _integer(value: object, field: str, *, minimum: int = 0, maximum: int = 1_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValidationError("DOWNSTREAM_INTEGER_INVALID", details={"field": field})
    return value


def _sequence(value: Any, field: str, *, maximum: int = _MAX_RECEIPTS) -> list[Any]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or len(value) > maximum
    ):
        raise ValidationError("DOWNSTREAM_COLLECTION_INVALID", details={"field": field})
    return list(value)


def _identifier_list(value: Any, field: str, *, required: bool) -> list[str]:
    values = [_identifier(item, f"{field}[]") for item in _sequence(value, field)]
    if required and not values:
        raise ValidationError("DOWNSTREAM_COLLECTION_REQUIRED", details={"field": field})
    if len(set(values)) != len(values):
        raise ValidationError("DOWNSTREAM_COLLECTION_DUPLICATE", details={"field": field})
    return values


def _timestamp(value: Any, field: str) -> datetime:
    raw = _text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise ValidationError("DOWNSTREAM_TIMESTAMP_INVALID", details={"field": field}) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError("DOWNSTREAM_TIMESTAMP_INVALID", details={"field": field})
    canonical = parsed.astimezone(UTC).replace(microsecond=0)
    if canonical.isoformat() != raw:
        raise ValidationError("DOWNSTREAM_TIMESTAMP_NON_CANONICAL", details={"field": field})
    return canonical


def _digest(value: Any, field: str) -> str:
    try:
        raw = _text(value, field, maximum=71)
        normalized = normalize_sha256(raw)
    except ValidationError as error:
        raise ValidationError("DOWNSTREAM_DIGEST_INVALID", details={"field": field}) from error
    if raw != normalized:
        raise ValidationError("DOWNSTREAM_DIGEST_NON_CANONICAL", details={"field": field})
    return normalized


def _decoded(raw: Any, digest: Any, code: str) -> dict[str, Any]:
    if not isinstance(raw, str) or not isinstance(digest, str):
        raise IntegrityError(code)
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise IntegrityError(code) from error
    if (
        not isinstance(value, dict)
        or canonical_json(value) != raw
        or canonical_digest(value) != digest
    ):
        raise IntegrityError(code)
    return value


def _without_digest(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "receipt_digest"}


def _verify_receipt_digest(value: Mapping[str, Any]) -> str:
    observed = _digest(value.get("receipt_digest"), "receipt_digest")
    if canonical_digest(_without_digest(value)) != observed:
        raise IntegrityError("DOWNSTREAM_RECEIPT_DIGEST_MISMATCH")
    return observed


def _reject_unsafe_tree(value: Any, *, field: str) -> None:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValidationError("DOWNSTREAM_RAW_ASSET_FORBIDDEN", details={"field": field})
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValidationError("DOWNSTREAM_OBJECT_KEY_INVALID", details={"field": field})
            normalized = key.strip().lower().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS:
                raise ValidationError(
                    "DOWNSTREAM_AUTHORITY_OR_RAW_INPUT_FORBIDDEN",
                    details={"field": f"{field}.{key}"},
                )
            _reject_unsafe_tree(item, field=f"{field}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, str):
        for index, item in enumerate(value):
            _reject_unsafe_tree(item, field=f"{field}[{index}]")


def _tool_input(value: Mapping[str, Any]) -> dict[str, Any]:
    """Accept references and bounded scalar selectors, never content bytes/text."""

    if set(value) != {
        "schema_version",
        "operation_id",
        "source_set_digest",
        "source_receipt_ids",
        "parameters",
    }:
        raise ValidationError("DOWNSTREAM_TOOL_INPUT_SCHEMA_INVALID")
    if value.get("schema_version") != "elmos-downstream-tool-input-v1":
        raise ValidationError("DOWNSTREAM_TOOL_INPUT_SCHEMA_INVALID")
    operation_id = _identifier(value.get("operation_id"), "tool_input.operation_id")
    source_set_digest = _digest(
        value.get("source_set_digest"), "tool_input.source_set_digest"
    )
    source_ids = _identifier_list(
        value.get("source_receipt_ids"), "tool_input.source_receipt_ids", required=True
    )
    raw_parameters = value.get("parameters")
    if not isinstance(raw_parameters, Mapping) or len(raw_parameters) > 64:
        raise ValidationError("DOWNSTREAM_TOOL_PARAMETERS_INVALID")
    parameters: dict[str, bool | int | str | None] = {}
    for raw_key, raw_value in raw_parameters.items():
        key = _identifier(raw_key, "tool_input.parameter")
        if raw_value is None or isinstance(raw_value, bool):
            parameters[key] = raw_value
        elif isinstance(raw_value, int) and not isinstance(raw_value, bool):
            parameters[key] = _integer(
                raw_value, f"tool_input.parameters.{key}", minimum=0,
                maximum=1_000_000_000,
            )
        elif isinstance(raw_value, str):
            # Strings are identifiers/selectors only.  Normalized source text
            # is already in the immutable context and raw/base64 payloads have
            # no representation in this invocation contract.
            parameters[key] = _identifier(
                raw_value, f"tool_input.parameters.{key}"
            )
        else:
            raise ValidationError("DOWNSTREAM_TOOL_PARAMETERS_INVALID")
    return {
        "schema_version": "elmos-downstream-tool-input-v1",
        "operation_id": operation_id,
        "source_set_digest": source_set_digest,
        "source_receipt_ids": source_ids,
        "parameters": parameters,
    }


def _scope(ctx: "RuntimeContext") -> tuple[str, str]:
    return ctx.tenant_id, ctx.project_id


def _tenant(ctx: "RuntimeContext") -> TenantContext:
    return TenantContext(ctx.tenant_id, ctx.project_id, ctx.actor_id)


def _envelope(state: str, code: str, outputs: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "state": state,
        "code": code,
        "outputs": dict(outputs),
        "metrics": {},
        "retryable": False,
    }


@dataclass(frozen=True)
class DownstreamToolInvocation:
    tenant_id: str
    project_id: str
    context_id: str
    grant_id: str
    execution_id: str
    tool_id: str
    subject_id: str
    input_document: Mapping[str, Any]
    input_digest: str
    claim_fence: int


class DownstreamToolAdapter(Protocol):
    """Host-provisioned exact adapter; never selected or loaded by repository content."""

    def execute(self, invocation: DownstreamToolInvocation, /) -> Mapping[str, Any]: ...


class DownstreamResultVerifier(Protocol):
    """Host-owned verifier that checks result bytes/signature independently."""

    def verify(
        self,
        invocation: DownstreamToolInvocation,
        candidate: Mapping[str, Any],
        /,
    ) -> Mapping[str, Any]: ...


class _GatewayAuthority:
    __slots__ = ()


class DownstreamAgentBridge:
    """Public, durable Skill bridge; execution remains outside request dispatch."""

    def __init__(self, store: IntakeStore) -> None:
        if not isinstance(store, IntakeStore):
            raise ValidationError("DOWNSTREAM_STORE_INVALID")
        self._store = store
        self._gateway_authority = _GatewayAuthority()
        self._validate_schema()

    def _validate_schema(self) -> None:
        required = {
            "downstream_agent_contexts",
            "downstream_context_sources",
            "downstream_tool_grants",
            "downstream_tool_executions",
            "downstream_agent_result_links",
            "downstream_agent_operation_receipts",
            "downstream_agent_outbox",
        }
        with self._store.read_transaction() as connection:
            observed = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table'"
                ).fetchall()
            }
        if not required <= observed:
            raise IntegrityError("DOWNSTREAM_SCHEMA_INVALID")

    def create_tool_gateway(
        self,
        adapters: Mapping[str, DownstreamToolAdapter],
        *,
        result_verifier: DownstreamResultVerifier,
        verifier_id: str,
    ) -> "DownstreamToolGateway":
        """Trusted composition seam; not reachable through ``handle``."""

        return DownstreamToolGateway(
            self._store,
            adapters,
            result_verifier=result_verifier,
            verifier_id=verifier_id,
            authority=self._gateway_authority,
            expected_authority=self._gateway_authority,
        )

    @staticmethod
    def _operation(payload: Mapping[str, Any]) -> str:
        raw = payload.get("operation")
        operation = _text(raw, "operation", maximum=64).lower().replace("-", "_")
        allowed = _PUBLIC_FIELDS.get(operation)
        if allowed is None:
            raise ValidationError("DOWNSTREAM_OPERATION_UNSUPPORTED")
        unknown = set(payload) - set(allowed) - set(_INTERNAL_FIELDS)
        if unknown:
            raise ValidationError(
                "DOWNSTREAM_PUBLIC_FIELD_FORBIDDEN",
                details={"fields": sorted(unknown)},
            )
        _reject_unsafe_tree(payload, field="inputs")
        return operation

    @staticmethod
    def _policy(ctx: "RuntimeContext") -> dict[str, Any]:
        raw = ctx.policy.get("downstream_agent")
        if not isinstance(raw, Mapping):
            raise AuthorizationError("DOWNSTREAM_POLICY_UNAVAILABLE")
        if (
            raw.get("schema_version") != "elmos-downstream-agent-policy-v1"
            or raw.get("tenant_id") != ctx.tenant_id
            or raw.get("project_id") != ctx.project_id
        ):
            raise AuthorizationError("DOWNSTREAM_POLICY_SCOPE_INVALID")
        version = _identifier(raw.get("version"), "policy.version")
        allowed_tools = _identifier_list(
            raw.get("allowed_tool_ids", []), "policy.allowed_tool_ids", required=False
        )
        max_sources = _integer(
            raw.get("max_context_sources"), "policy.max_context_sources", minimum=3, maximum=256
        )
        max_chars = _integer(
            raw.get("max_context_chars"),
            "policy.max_context_chars",
            minimum=1,
            maximum=_MAX_CONTEXT_CHARS,
        )
        ttl = _integer(
            raw.get("max_grant_ttl_seconds"),
            "policy.max_grant_ttl_seconds",
            minimum=1,
            maximum=900,
        )
        return {
            "version": version,
            "allowed_tool_ids": allowed_tools,
            "max_context_sources": max_sources,
            "max_context_chars": max_chars,
            "max_grant_ttl_seconds": ttl,
            "policy_digest": canonical_digest(dict(raw)),
        }

    @staticmethod
    def _registry(ctx: "RuntimeContext") -> Mapping[str, Any]:
        raw = ctx.capabilities.get("downstream_agent_receipts")
        if not isinstance(raw, Mapping):
            raise AuthorizationError("DOWNSTREAM_HOST_RECEIPTS_UNAVAILABLE")
        if (
            raw.get("schema_version") != "elmos-downstream-agent-receipts-v1"
            or raw.get("tenant_id") != ctx.tenant_id
            or raw.get("project_id") != ctx.project_id
            or raw.get("verified") is not True
        ):
            raise AuthorizationError("DOWNSTREAM_HOST_RECEIPTS_UNVERIFIED")
        return raw

    @staticmethod
    def _receipt_index(
        registry: Mapping[str, Any], collection: str
    ) -> dict[str, Mapping[str, Any]]:
        rows = _sequence(registry.get(collection, []), f"capabilities.{collection}")
        indexed: dict[str, Mapping[str, Any]] = {}
        for item in rows:
            if not isinstance(item, Mapping):
                raise IntegrityError("DOWNSTREAM_HOST_RECEIPT_INVALID")
            receipt_id = _identifier(item.get("receipt_id"), f"{collection}.receipt_id")
            if receipt_id in indexed:
                raise IntegrityError("DOWNSTREAM_HOST_RECEIPT_DUPLICATE")
            indexed[receipt_id] = item
        return indexed

    @staticmethod
    def _source_receipt(
        ctx: "RuntimeContext",
        raw: Mapping[str, Any],
        *,
        subject_id: str,
        package_version: int,
    ) -> dict[str, Any]:
        if set(raw) != set(_SOURCE_RECEIPT_KEYS):
            raise IntegrityError("DOWNSTREAM_SOURCE_RECEIPT_SCHEMA_INVALID")
        if raw.get("schema_version") != "elmos-downstream-source-receipt-v1":
            raise IntegrityError("DOWNSTREAM_SOURCE_RECEIPT_SCHEMA_INVALID")
        if (
            raw.get("tenant_id") != ctx.tenant_id
            or raw.get("project_id") != ctx.project_id
            or raw.get("subject_id") != subject_id
            or raw.get("package_version") != package_version
        ):
            raise AuthorizationError("DOWNSTREAM_SOURCE_RECEIPT_SCOPE_INVALID")
        if (
            raw.get("verified") is not True
            or raw.get("prompt_safe") is not True
            or raw.get("raw_asset_included") is not False
        ):
            raise AuthorizationError("DOWNSTREAM_SOURCE_RECEIPT_UNVERIFIED")
        issuer = _identifier(raw.get("issuer_id"), "source.issuer_id")
        verifier = _identifier(raw.get("verifier_id"), "source.verifier_id")
        if issuer == verifier:
            raise AuthorizationError("DOWNSTREAM_SOURCE_SELF_VERIFICATION_FORBIDDEN")
        if _timestamp(raw.get("expires_at"), "source.expires_at") <= datetime.now(UTC):
            raise AuthorizationError("DOWNSTREAM_SOURCE_RECEIPT_EXPIRED")
        source_kind = _text(raw.get("source_kind"), "source.source_kind", maximum=32)
        if source_kind not in _SOURCE_KINDS:
            raise IntegrityError("DOWNSTREAM_SOURCE_KIND_INVALID")
        source_id = _identifier(raw.get("source_id"), "source.source_id")
        normalized = raw.get("normalized")
        if (
            not isinstance(normalized, Mapping)
            or set(normalized) != {"summary", "anchors", "trust_label"}
            or normalized.get("trust_label") != UNTRUSTED_CONTENT
        ):
            raise IntegrityError("DOWNSTREAM_NORMALIZED_SOURCE_INVALID")
        _reject_unsafe_tree(normalized, field="normalized")
        summary = _text(normalized.get("summary"), "normalized.summary", maximum=65_536)
        anchors_raw = _sequence(normalized.get("anchors"), "normalized.anchors", maximum=1_000)
        if not anchors_raw:
            raise IntegrityError("DOWNSTREAM_SOURCE_PROVENANCE_REQUIRED")
        anchors: list[dict[str, str]] = []
        for anchor in anchors_raw:
            if not isinstance(anchor, Mapping) or set(anchor) != {"source_id", "locator", "source_digest"}:
                raise IntegrityError("DOWNSTREAM_SOURCE_ANCHOR_INVALID")
            anchors.append(
                {
                    "source_id": _identifier(anchor.get("source_id"), "anchor.source_id"),
                    "locator": _text(anchor.get("locator"), "anchor.locator", maximum=1024),
                    "source_digest": _digest(anchor.get("source_digest"), "anchor.source_digest"),
                }
            )
        projection = {
            "summary": summary,
            "anchors": anchors,
            "trust_label": UNTRUSTED_CONTENT,
        }
        if not any(anchor["source_id"] == source_id for anchor in anchors):
            raise IntegrityError("DOWNSTREAM_SOURCE_ANCHOR_BINDING_MISMATCH")
        source_digest = _digest(raw.get("source_digest"), "source.source_digest")
        if canonical_digest(projection) != source_digest:
            raise IntegrityError("DOWNSTREAM_SOURCE_DIGEST_MISMATCH")
        receipt_digest = _verify_receipt_digest(raw)
        return {
            "receipt_id": _identifier(raw.get("receipt_id"), "source.receipt_id"),
            "source_kind": source_kind,
            "source_id": source_id,
            "source_digest": source_digest,
            "receipt_digest": receipt_digest,
            "normalized": projection,
        }

    @staticmethod
    def _tool_receipt(
        ctx: "RuntimeContext",
        raw: Mapping[str, Any],
        *,
        subject_id: str,
        package_version: int,
        policy: Mapping[str, Any],
    ) -> dict[str, Any]:
        if set(raw) != set(_TOOL_RECEIPT_KEYS):
            raise IntegrityError("DOWNSTREAM_TOOL_RECEIPT_SCHEMA_INVALID")
        if raw.get("schema_version") != "elmos-downstream-tool-receipt-v1":
            raise IntegrityError("DOWNSTREAM_TOOL_RECEIPT_SCHEMA_INVALID")
        if (
            raw.get("tenant_id") != ctx.tenant_id
            or raw.get("project_id") != ctx.project_id
            or raw.get("subject_id") != subject_id
            or raw.get("package_version") != package_version
        ):
            raise AuthorizationError("DOWNSTREAM_TOOL_RECEIPT_SCOPE_INVALID")
        tool_id = _identifier(raw.get("tool_id"), "tool.tool_id")
        if tool_id not in policy["allowed_tool_ids"]:
            raise AuthorizationError("DOWNSTREAM_TOOL_NOT_ALLOWLISTED")
        if (
            raw.get("single_use") is not True
            or raw.get("revoked") is not False
            or raw.get("verification_state") != "VERIFIED"
        ):
            raise AuthorizationError("DOWNSTREAM_TOOL_RECEIPT_UNVERIFIED")
        issuer = _identifier(raw.get("issuer_id"), "tool.issuer_id")
        verifier = _identifier(raw.get("verifier_id"), "tool.verifier_id")
        if issuer == verifier:
            raise AuthorizationError("DOWNSTREAM_TOOL_SELF_VERIFICATION_FORBIDDEN")
        issued = _timestamp(raw.get("issued_at"), "tool.issued_at")
        expires = _timestamp(raw.get("expires_at"), "tool.expires_at")
        now = datetime.now(UTC)
        if issued > now or expires <= now or expires <= issued:
            raise AuthorizationError("DOWNSTREAM_TOOL_RECEIPT_EXPIRED")
        if (expires - issued).total_seconds() > int(policy["max_grant_ttl_seconds"]):
            raise AuthorizationError("DOWNSTREAM_TOOL_RECEIPT_TTL_EXCESSIVE")
        input_digest = _digest(raw.get("input_digest"), "tool.input_digest")
        scope_digest = _digest(raw.get("scope_digest"), "tool.scope_digest")
        expected_scope = canonical_digest(
            {
                "tenant_id": ctx.tenant_id,
                "project_id": ctx.project_id,
                "subject_id": subject_id,
                "package_version": package_version,
                "tool_id": tool_id,
            }
        )
        if scope_digest != expected_scope:
            raise AuthorizationError("DOWNSTREAM_TOOL_SCOPE_DIGEST_MISMATCH")
        return {
            "receipt_id": _identifier(raw.get("receipt_id"), "tool.receipt_id"),
            "tool_id": tool_id,
            "capability_version": _identifier(
                raw.get("capability_version"), "tool.capability_version"
            ),
            "input_digest": input_digest,
            "scope_digest": scope_digest,
            "receipt_digest": _verify_receipt_digest(raw),
            "expires_at": expires.isoformat(),
        }

    @staticmethod
    def _result_receipt(
        raw: Mapping[str, Any],
        *,
        tenant_id: str,
        project_id: str,
        context_id: str,
        grant: Mapping[str, Any],
        execution: Mapping[str, Any],
    ) -> dict[str, Any]:
        if set(raw) != set(_RESULT_RECEIPT_KEYS):
            raise IntegrityError("DOWNSTREAM_RESULT_RECEIPT_SCHEMA_INVALID")
        if raw.get("schema_version") != "elmos-downstream-result-receipt-v1":
            raise IntegrityError("DOWNSTREAM_RESULT_RECEIPT_SCHEMA_INVALID")
        exact = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "context_id": context_id,
            "grant_id": str(grant["grant_id"]),
            "execution_id": str(execution["execution_id"]),
            "tool_id": str(grant["tool_id"]),
            "subject_id": str(grant["subject_id"]),
            "input_digest": str(grant["input_digest"]),
            "claim_fence": int(execution["claim_fence"]),
            "executor_id": str(execution["executor_id"]),
        }
        if any(raw.get(key) != value for key, value in exact.items()):
            raise AuthorizationError("DOWNSTREAM_RESULT_RECEIPT_BINDING_MISMATCH")
        if raw.get("verification_state") != "VERIFIED":
            raise AuthorizationError("DOWNSTREAM_RESULT_RECEIPT_UNVERIFIED")
        method = _text(raw.get("verification_method"), "result.verification_method", maximum=32)
        if method not in _VERIFICATION_METHODS:
            raise AuthorizationError("DOWNSTREAM_RESULT_VERIFICATION_METHOD_INVALID")
        executor = require_actor_id(_text(raw.get("executor_id"), "result.executor_id", maximum=200))
        verifier = require_actor_id(_text(raw.get("verifier_id"), "result.verifier_id", maximum=200))
        if executor == verifier:
            raise AuthorizationError("DOWNSTREAM_RESULT_SELF_VERIFICATION_FORBIDDEN")
        result_digest = _digest(raw.get("result_digest"), "result.result_digest")
        byte_count = _integer(
            raw.get("result_byte_count"),
            "result.result_byte_count",
            minimum=0,
            maximum=_MAX_RESULT_BYTES,
        )
        locator = _text(raw.get("result_locator"), "result.result_locator", maximum=256)
        if locator != f"cas://sha256/{result_digest}":
            raise IntegrityError("DOWNSTREAM_RESULT_LOCATOR_INVALID")
        completed = _timestamp(raw.get("completed_at"), "result.completed_at")
        started = _timestamp(execution["started_at"], "execution.started_at")
        if completed < started or completed > datetime.now(UTC):
            raise IntegrityError("DOWNSTREAM_RESULT_COMPLETION_TIME_INVALID")
        return {
            **dict(raw),
            "receipt_id": _identifier(raw.get("receipt_id"), "result.receipt_id"),
            "result_digest": result_digest,
            "result_byte_count": byte_count,
            "result_locator": locator,
            "executor_id": executor,
            "verifier_id": verifier,
            "verification_method": method,
            "receipt_digest": _verify_receipt_digest(raw),
        }

    @staticmethod
    def _idempotency(ctx: "RuntimeContext") -> str:
        if ctx.idempotency_key is None:
            raise ValidationError("IDEMPOTENCY_KEY_REQUIRED")
        key = require_idempotency_key(ctx.idempotency_key)
        if len(key.encode("utf-8")) < 8:
            raise ValidationError("IDEMPOTENCY_KEY_INVALID")
        return key

    @staticmethod
    def _prior_operation(
        connection: Any,
        ctx: "RuntimeContext",
        operation: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """SELECT request_digest,response_json,response_digest
                 FROM downstream_agent_operation_receipts
                WHERE tenant_id=? AND project_id=? AND actor_id=?
                  AND operation=? AND idempotency_key=?""",
            (*_scope(ctx), ctx.actor_id, operation, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        if str(row["request_digest"]) != request_digest:
            raise ConflictError("DOWNSTREAM_IDEMPOTENCY_CONFLICT")
        return _decoded(
            row["response_json"], row["response_digest"],
            "DOWNSTREAM_OPERATION_RECEIPT_CORRUPT",
        )

    @staticmethod
    def _record_operation(
        connection: Any,
        ctx: "RuntimeContext",
        operation: str,
        idempotency_key: str,
        request_digest: str,
        response: Mapping[str, Any],
    ) -> None:
        body = dict(response)
        connection.execute(
            "INSERT INTO downstream_agent_operation_receipts VALUES (?,?,?,?,?,?,?,?,?)",
            (
                *_scope(ctx), ctx.actor_id, operation, idempotency_key, request_digest,
                canonical_json(body), canonical_digest(body), utc_now(),
            ),
        )

    @staticmethod
    def _outbox(
        connection: Any,
        ctx: "RuntimeContext",
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        idempotency_key: str,
        payload: Mapping[str, Any],
    ) -> None:
        body = dict(payload)
        connection.execute(
            """INSERT INTO downstream_agent_outbox
               (tenant_id,project_id,event_id,aggregate_type,aggregate_id,event_type,
                idempotency_key,payload_json,payload_digest,delivery_state,attempt_count,
                claim_token_digest,claim_expires_at,created_at,published_at)
               VALUES (?,?,?,?,?,?,?,?,?,'PENDING',0,NULL,NULL,?,NULL)""",
            (
                *_scope(ctx), new_id("downstream-event"), aggregate_type, aggregate_id,
                event_type, idempotency_key, canonical_json(body), canonical_digest(body),
                utc_now(),
            ),
        )

    def handle(
        self,
        skill_name: str,
        ctx: "RuntimeContext",
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if skill_name != SKILL_NAME:
            raise ValidationError("DOWNSTREAM_SKILL_UNSUPPORTED")
        operation = self._operation(payload)
        if payload.get("idempotency_key", ctx.idempotency_key) != ctx.idempotency_key:
            raise IntegrityError("DOWNSTREAM_INTERNAL_IDEMPOTENCY_BINDING_MISMATCH")
        if payload.get("trace_id", ctx.trace_id) != ctx.trace_id:
            raise IntegrityError("DOWNSTREAM_INTERNAL_TRACE_BINDING_MISMATCH")
        context = _tenant(ctx)
        self._store.require(context, self._store.READ)
        if operation in _MUTATIONS:
            self._store.require(context, self._store.WRITE)
        if operation == "build_context":
            return self._build_context(ctx, payload)
        if operation == "get_context":
            return self._get_context(ctx, payload)
        if operation == "get_grant":
            return self._get_grant(ctx, payload)
        if operation == "revoke_grant":
            return self._revoke_grant(ctx, payload)
        if operation == "link_result":
            return self._link_result(ctx, payload)
        return self._list_result_links(ctx, payload)

    def _build_context(
        self, ctx: "RuntimeContext", payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        key = self._idempotency(ctx)
        task_id = _identifier(payload.get("task_id"), "task_id")
        subject_id = _identifier(payload.get("subject_id"), "subject_id")
        package_version = _integer(
            payload.get("package_version"), "package_version", minimum=1
        )
        source_ids = _identifier_list(
            payload.get("source_receipt_ids"), "source_receipt_ids", required=True
        )
        tool_ids = _identifier_list(
            payload.get("tool_receipt_ids", []), "tool_receipt_ids", required=False
        )
        policy = self._policy(ctx)
        if len(source_ids) > int(policy["max_context_sources"]):
            raise AuthorizationError("DOWNSTREAM_CONTEXT_SOURCE_LIMIT")
        registry = self._registry(ctx)
        source_index = self._receipt_index(registry, "source_receipts")
        tool_index = self._receipt_index(registry, "tool_receipts")
        try:
            sources = [
                self._source_receipt(
                    ctx, source_index[receipt_id],
                    subject_id=subject_id, package_version=package_version,
                )
                for receipt_id in source_ids
            ]
            tools = [
                self._tool_receipt(
                    ctx, tool_index[receipt_id], subject_id=subject_id,
                    package_version=package_version, policy=policy,
                )
                for receipt_id in tool_ids
            ]
        except KeyError as error:
            raise AuthorizationError("DOWNSTREAM_RECEIPT_NOT_ALLOWLISTED") from error
        observed_kinds = {item["source_kind"] for item in sources}
        if not _SOURCE_KINDS <= observed_kinds:
            raise ValidationError(
                "DOWNSTREAM_CONTEXT_SOURCE_KINDS_INCOMPLETE",
                details={"missing": sorted(_SOURCE_KINDS - observed_kinds)},
            )
        source_projections = [item["normalized"] for item in sources]
        if sum(len(canonical_json(item).encode("utf-8")) for item in source_projections) > int(
            policy["max_context_chars"]
        ):
            raise AuthorizationError("DOWNSTREAM_CONTEXT_SIZE_LIMIT")
        request_binding = {
            "schema_version": "elmos-downstream-build-request-v1",
            "tenant_id": ctx.tenant_id,
            "project_id": ctx.project_id,
            "actor_id": ctx.actor_id,
            "task_id": task_id,
            "subject_id": subject_id,
            "package_version": package_version,
            "source_receipt_ids": source_ids,
            "tool_receipt_ids": tool_ids,
            "policy_digest": policy["policy_digest"],
            "source_receipt_digests": [item["receipt_digest"] for item in sources],
            "tool_receipt_digests": [item["receipt_digest"] for item in tools],
        }
        request_digest = canonical_digest(request_binding)
        with self._store.transaction() as connection:
            prior = self._prior_operation(connection, ctx, "build_context", key, request_digest)
            if prior is not None:
                return prior
            package = connection.execute(
                """SELECT state,manifest_digest FROM project_package_versions
                    WHERE tenant_id=? AND project_id=? AND package_version=?""",
                (*_scope(ctx), package_version),
            ).fetchone()
            if package is None or str(package["state"]) == "ROLLED_BACK":
                raise NotFoundError("DOWNSTREAM_PROJECT_PACKAGE_NOT_STABLE")
            context_id = new_id("agent-context")
            source_set_digest = canonical_digest(
                [item["receipt_digest"] for item in sources]
            )
            context_body = {
                "schema_version": "elmos-agent-context-v1",
                "context_id": context_id,
                "task_id": task_id,
                "subject_id": subject_id,
                "package_version": package_version,
                "package_manifest_digest": str(package["manifest_digest"]),
                "source_set_digest": source_set_digest,
                "sources": [
                    {
                        "source_receipt_id": item["receipt_id"],
                        "source_kind": item["source_kind"],
                        "source_id": item["source_id"],
                        "source_digest": item["source_digest"],
                        "normalized": item["normalized"],
                        "trust_label": UNTRUSTED_CONTENT,
                        "verification_state": "HOST_VERIFIED_FOR_CONTEXT_ONLY",
                    }
                    for item in sources
                ],
                "tool_authority_from_content": False,
                "raw_assets_in_prompt": False,
                "repository_content_executed": False,
                "downstream_execution_state": "NOT_RUN",
                "external_evidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
                "policy_version": policy["version"],
            }
            context_digest = canonical_digest(context_body)
            now = utc_now()
            connection.execute(
                """INSERT INTO downstream_agent_contexts VALUES
                   (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    *_scope(ctx), context_id, task_id, subject_id, package_version,
                    ctx.actor_id, key, request_digest, policy["version"],
                    source_set_digest, canonical_json(context_body), context_digest,
                    "ACTIVE", now, None,
                ),
            )
            for ordinal, source in enumerate(sources):
                normalized_json = canonical_json(source["normalized"])
                connection.execute(
                    "INSERT INTO downstream_context_sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        *_scope(ctx), context_id, ordinal, source["receipt_id"],
                        source["source_kind"], source["source_id"], source["source_digest"],
                        source["receipt_digest"], normalized_json,
                        canonical_digest(source["normalized"]), 0, now,
                    ),
                )
            grant_outputs: list[dict[str, Any]] = []
            for tool in tools:
                grant_id = new_id("context-grant")
                connection.execute(
                    """INSERT INTO downstream_tool_grants VALUES
                       (?,?,?,?,?,?,?,?,?,?,?,?,'ISSUED',?,1,0,NULL,NULL,NULL,?,NULL,NULL,NULL)""",
                    (
                        *_scope(ctx), context_id, grant_id, tool["receipt_id"],
                        tool["tool_id"], tool["capability_version"], subject_id,
                        tool["input_digest"], tool["scope_digest"], tool["receipt_digest"],
                        policy["version"], tool["expires_at"], now,
                    ),
                )
                grant_outputs.append(
                    {
                        "grant_id": grant_id,
                        "tool_id": tool["tool_id"],
                        "capability_version": tool["capability_version"],
                        "input_digest": tool["input_digest"],
                        "expires_at": tool["expires_at"],
                        "state": "ISSUED",
                        "single_use": True,
                    }
                )
            outputs = {
                "context": context_body,
                "context_digest": context_digest,
                "grants": grant_outputs,
                "execution_state": "NOT_RUN",
                "result_link_state": "NOT_RUN",
                "external_evidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            }
            response = _envelope("SUCCEEDED", "DOWNSTREAM_CONTEXT_BUILT", outputs)
            self._outbox(
                connection, ctx, aggregate_type="downstream_context",
                aggregate_id=context_id, event_type="agent.context.built",
                idempotency_key=f"agent-context-built:{key}",
                payload={
                    "context_id": context_id,
                    "context_digest": context_digest,
                    "subject_id": subject_id,
                    "package_version": package_version,
                    "grant_count": len(grant_outputs),
                },
            )
            self._record_operation(
                connection, ctx, "build_context", key, request_digest, response
            )
            return response

    @staticmethod
    def _context_row(connection: Any, ctx: "RuntimeContext", context_id: str) -> Any:
        row = connection.execute(
            """SELECT * FROM downstream_agent_contexts
                WHERE tenant_id=? AND project_id=? AND context_id=?""",
            (*_scope(ctx), context_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("DOWNSTREAM_CONTEXT_NOT_FOUND")
        return row

    @staticmethod
    def _grant_row(
        connection: Any, ctx: "RuntimeContext", context_id: str, grant_id: str
    ) -> Any:
        row = connection.execute(
            """SELECT * FROM downstream_tool_grants
                WHERE tenant_id=? AND project_id=? AND context_id=? AND grant_id=?""",
            (*_scope(ctx), context_id, grant_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("DOWNSTREAM_GRANT_NOT_FOUND")
        return row

    def _get_context(
        self, ctx: "RuntimeContext", payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        context_id = _identifier(payload.get("context_id"), "context_id")
        with self._store.read_transaction() as connection:
            row = self._context_row(connection, ctx, context_id)
            context_body = _decoded(
                row["context_json"], row["context_digest"], "DOWNSTREAM_CONTEXT_CORRUPT"
            )
            grants = [
                {
                    "grant_id": str(item["grant_id"]),
                    "tool_id": str(item["tool_id"]),
                    "capability_version": str(item["capability_version"]),
                    "input_digest": str(item["input_digest"]),
                    "state": str(item["state"]),
                    "expires_at": str(item["expires_at"]),
                    "single_use": bool(item["single_use"]),
                }
                for item in connection.execute(
                    """SELECT * FROM downstream_tool_grants
                        WHERE tenant_id=? AND project_id=? AND context_id=?
                        ORDER BY grant_id""",
                    (*_scope(ctx), context_id),
                ).fetchall()
            ]
        return _envelope(
            "SUCCEEDED", "DOWNSTREAM_CONTEXT_FOUND",
            {
                "context": context_body,
                "context_digest": str(row["context_digest"]),
                "context_state": str(row["state"]),
                "grants": grants,
            },
        )

    def _get_grant(
        self, ctx: "RuntimeContext", payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        context_id = _identifier(payload.get("context_id"), "context_id")
        grant_id = _identifier(payload.get("grant_id"), "grant_id")
        with self._store.read_transaction() as connection:
            row = self._grant_row(connection, ctx, context_id, grant_id)
        return _envelope(
            "SUCCEEDED", "DOWNSTREAM_GRANT_FOUND",
            {
                "grant": {
                    "context_id": context_id,
                    "grant_id": grant_id,
                    "tool_id": str(row["tool_id"]),
                    "capability_version": str(row["capability_version"]),
                    "subject_id": str(row["subject_id"]),
                    "input_digest": str(row["input_digest"]),
                    "state": str(row["state"]),
                    "expires_at": str(row["expires_at"]),
                    "single_use": bool(row["single_use"]),
                    "claim_fence": int(row["claim_fence"]),
                }
            },
        )

    def _revoke_grant(
        self, ctx: "RuntimeContext", payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        key = self._idempotency(ctx)
        context_id = _identifier(payload.get("context_id"), "context_id")
        grant_id = _identifier(payload.get("grant_id"), "grant_id")
        reason = _text(payload.get("reason"), "reason", maximum=512)
        request_digest = canonical_digest(
            {"context_id": context_id, "grant_id": grant_id, "reason": reason}
        )
        with self._store.transaction() as connection:
            prior = self._prior_operation(connection, ctx, "revoke_grant", key, request_digest)
            if prior is not None:
                return prior
            self._context_row(connection, ctx, context_id)
            grant = self._grant_row(connection, ctx, context_id, grant_id)
            if str(grant["state"]) not in {"ISSUED", "CLAIMED", "UNKNOWN"}:
                raise ConflictError("DOWNSTREAM_GRANT_NOT_REVOCABLE")
            now = utc_now()
            connection.execute(
                """UPDATE downstream_tool_grants
                      SET state='REVOKED',terminal_at=?,revocation_reason=?
                    WHERE tenant_id=? AND project_id=? AND grant_id=?""",
                (now, reason, *_scope(ctx), grant_id),
            )
            response = _envelope(
                "SUCCEEDED", "DOWNSTREAM_GRANT_REVOKED",
                {"context_id": context_id, "grant_id": grant_id, "state": "REVOKED"},
            )
            self._outbox(
                connection, ctx, aggregate_type="downstream_grant", aggregate_id=grant_id,
                event_type="agent.tool.revoked",
                idempotency_key=f"agent-tool-revoked:{key}",
                payload={"context_id": context_id, "grant_id": grant_id, "reason": reason},
            )
            self._record_operation(
                connection, ctx, "revoke_grant", key, request_digest, response
            )
            return response

    def _link_result(
        self, ctx: "RuntimeContext", payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        key = self._idempotency(ctx)
        context_id = _identifier(payload.get("context_id"), "context_id")
        grant_id = _identifier(payload.get("grant_id"), "grant_id")
        receipt_id = _identifier(payload.get("result_receipt_id"), "result_receipt_id")
        registry = self._registry(ctx)
        result_index = self._receipt_index(registry, "result_receipts")
        try:
            raw_receipt = result_index[receipt_id]
        except KeyError as error:
            raise AuthorizationError("DOWNSTREAM_RESULT_RECEIPT_NOT_ALLOWLISTED") from error
        request_digest = canonical_digest(
            {
                "context_id": context_id,
                "grant_id": grant_id,
                "result_receipt_id": receipt_id,
                "receipt_digest": raw_receipt.get("receipt_digest"),
            }
        )
        with self._store.transaction() as connection:
            prior = self._prior_operation(connection, ctx, "link_result", key, request_digest)
            if prior is not None:
                return prior
            context = self._context_row(connection, ctx, context_id)
            if str(context["state"]) != "ACTIVE":
                raise ConflictError("DOWNSTREAM_CONTEXT_INACTIVE")
            grant = self._grant_row(connection, ctx, context_id, grant_id)
            execution = connection.execute(
                """SELECT * FROM downstream_tool_executions
                    WHERE tenant_id=? AND project_id=? AND execution_id=? AND grant_id=?""",
                (
                    *_scope(ctx), _identifier(raw_receipt.get("execution_id"), "execution_id"),
                    grant_id,
                ),
            ).fetchone()
            if execution is None:
                raise AuthorizationError("DOWNSTREAM_GATEWAY_EXECUTION_EVIDENCE_REQUIRED")
            receipt = self._result_receipt(
                raw_receipt, tenant_id=ctx.tenant_id, project_id=ctx.project_id,
                context_id=context_id, grant=grant, execution=execution,
            )
            execution_state = str(execution["state"])
            grant_state = str(grant["state"])
            if execution_state == "UNKNOWN" and grant_state == "UNKNOWN":
                response_body = {
                    "execution_id": str(execution["execution_id"]),
                    "result_receipt_id": receipt_id,
                    "state": "VERIFIED",
                }
                connection.execute(
                    """UPDATE downstream_tool_executions
                          SET state='VERIFIED',result_receipt_id=?,result_receipt_json=?,
                              result_receipt_digest=?,response_json=?,response_digest=?,completed_at=?
                        WHERE tenant_id=? AND project_id=? AND execution_id=?""",
                    (
                        receipt_id, canonical_json(receipt), receipt["receipt_digest"],
                        canonical_json(response_body), canonical_digest(response_body), utc_now(),
                        *_scope(ctx), execution["execution_id"],
                    ),
                )
                connection.execute(
                    """UPDATE downstream_tool_grants
                          SET state='VERIFIED',execution_receipt_id=?,terminal_at=?
                        WHERE tenant_id=? AND project_id=? AND grant_id=?""",
                    (receipt_id, utc_now(), *_scope(ctx), grant_id),
                )
            elif execution_state == "VERIFIED" and grant_state == "VERIFIED":
                try:
                    stored_receipt = json.loads(str(execution["result_receipt_json"]))
                except (TypeError, ValueError) as error:
                    raise IntegrityError("DOWNSTREAM_GATEWAY_RECEIPT_CORRUPT") from error
                if (
                    not isinstance(stored_receipt, dict)
                    or canonical_json(stored_receipt) != execution["result_receipt_json"]
                    or _verify_receipt_digest(stored_receipt)
                    != str(execution["result_receipt_digest"])
                    or stored_receipt != receipt
                ):
                    raise IntegrityError("DOWNSTREAM_GATEWAY_RECEIPT_CORRUPT")
            else:
                raise ConflictError("DOWNSTREAM_RESULT_NOT_VERIFIED")
            existing = connection.execute(
                """SELECT link_json,link_digest FROM downstream_agent_result_links
                    WHERE tenant_id=? AND project_id=? AND grant_id=?""",
                (*_scope(ctx), grant_id),
            ).fetchone()
            if existing is not None:
                raise ConflictError("DOWNSTREAM_RESULT_ALREADY_LINKED")
            link_id = new_id("result-link")
            now = utc_now()
            link_body = {
                "schema_version": "elmos-result-provenance-v1",
                "link_id": link_id,
                "context_id": context_id,
                "context_digest": str(context["context_digest"]),
                "subject_id": str(context["subject_id"]),
                "package_version": int(context["package_version"]),
                "source_set_digest": str(context["source_set_digest"]),
                "grant_id": grant_id,
                "tool_id": str(grant["tool_id"]),
                "capability_version": str(grant["capability_version"]),
                "input_digest": str(grant["input_digest"]),
                "execution_id": str(execution["execution_id"]),
                "result_receipt_id": receipt_id,
                "result_digest": receipt["result_digest"],
                "result_byte_count": receipt["result_byte_count"],
                "result_locator": receipt["result_locator"],
                "executor_id": receipt["executor_id"],
                "verifier_id": receipt["verifier_id"],
                "verification_method": receipt["verification_method"],
                "original_sources_mutated": False,
            }
            connection.execute(
                """INSERT INTO downstream_agent_result_links VALUES
                   (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    *_scope(ctx), link_id, context_id, grant_id,
                    execution["execution_id"], receipt_id, receipt["result_digest"],
                    receipt["result_byte_count"], receipt["result_locator"],
                    receipt["executor_id"], receipt["verifier_id"],
                    receipt["verification_method"], receipt["receipt_digest"],
                    canonical_json(link_body), canonical_digest(link_body), ctx.actor_id, now,
                ),
            )
            connection.execute(
                """UPDATE downstream_tool_grants SET state='LINKED'
                    WHERE tenant_id=? AND project_id=? AND grant_id=?""",
                (*_scope(ctx), grant_id),
            )
            response = _envelope(
                "SUCCEEDED", "DOWNSTREAM_RESULT_LINKED", {"result_link": link_body}
            )
            self._outbox(
                connection, ctx, aggregate_type="downstream_result", aggregate_id=link_id,
                event_type="agent.result.recorded",
                idempotency_key=f"agent-result-recorded:{key}", payload=link_body,
            )
            self._record_operation(
                connection, ctx, "link_result", key, request_digest, response
            )
            return response

    def _list_result_links(
        self, ctx: "RuntimeContext", payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        context_id = _identifier(payload.get("context_id"), "context_id")
        with self._store.read_transaction() as connection:
            self._context_row(connection, ctx, context_id)
            rows = connection.execute(
                """SELECT link_json,link_digest FROM downstream_agent_result_links
                    WHERE tenant_id=? AND project_id=? AND context_id=? ORDER BY created_at,link_id""",
                (*_scope(ctx), context_id),
            ).fetchall()
            links = [
                _decoded(row["link_json"], row["link_digest"], "DOWNSTREAM_RESULT_LINK_CORRUPT")
                for row in rows
            ]
        return _envelope(
            "SUCCEEDED", "DOWNSTREAM_RESULT_LINKS_LISTED",
            {"context_id": context_id, "result_links": links},
        )


class DownstreamToolGateway:
    """Host-only allowlisted worker and sole downstream tool execution PEP."""

    def __init__(
        self,
        store: IntakeStore,
        adapters: Mapping[str, DownstreamToolAdapter],
        *,
        result_verifier: DownstreamResultVerifier,
        verifier_id: str,
        authority: object,
        expected_authority: object,
    ) -> None:
        if authority is not expected_authority or not isinstance(authority, _GatewayAuthority):
            raise AuthorizationError("DOWNSTREAM_GATEWAY_COMPOSITION_FORBIDDEN")
        if not isinstance(adapters, Mapping) or len(adapters) > _MAX_RECEIPTS:
            raise ValidationError("DOWNSTREAM_GATEWAY_ADAPTERS_INVALID")
        validated: dict[str, DownstreamToolAdapter] = {}
        for raw_tool_id, adapter in adapters.items():
            tool_id = _identifier(raw_tool_id, "adapter.tool_id")
            if not callable(getattr(adapter, "execute", None)):
                raise ValidationError("DOWNSTREAM_GATEWAY_ADAPTER_INVALID")
            validated[tool_id] = adapter
        if not callable(getattr(result_verifier, "verify", None)):
            raise ValidationError("DOWNSTREAM_RESULT_VERIFIER_INVALID")
        verifier_object: object = result_verifier
        if any(verifier_object is adapter for adapter in validated.values()):
            raise AuthorizationError("DOWNSTREAM_EXECUTOR_VERIFIER_SEPARATION_REQUIRED")
        self._store = store
        self._adapters = validated
        self._result_verifier = result_verifier
        self._verifier_id = require_actor_id(verifier_id)

    @staticmethod
    def _unknown_response(execution_id: str, grant_id: str) -> dict[str, Any]:
        return {
            "state": "UNKNOWN",
            "code": "DOWNSTREAM_TOOL_OUTCOME_RECONCILIATION_REQUIRED",
            "execution_id": execution_id,
            "grant_id": grant_id,
            "automatic_retry_allowed": False,
            "result_link_state": "NOT_RUN",
        }

    @staticmethod
    def _denied_event(
        connection: Any,
        context: TenantContext,
        *,
        grant_id: str,
        code: str,
        idempotency_key: str,
    ) -> None:
        payload = {
            "grant_id": grant_id,
            "decision": "DENY",
            "code": code,
            "side_effect_authorized": False,
        }
        connection.execute(
            """INSERT INTO downstream_agent_outbox
               (tenant_id,project_id,event_id,aggregate_type,aggregate_id,event_type,
                idempotency_key,payload_json,payload_digest,delivery_state,attempt_count,
                claim_token_digest,claim_expires_at,created_at,published_at)
               VALUES (?,?,?,?,?,?,?,?,?,'PENDING',0,NULL,NULL,?,NULL)""",
            (
                context.tenant_id, context.project_id, new_id("downstream-event"),
                "downstream_grant", grant_id, "agent.tool.denied", idempotency_key,
                canonical_json(payload), canonical_digest(payload), utc_now(),
            ),
        )

    def execute(
        self,
        context: TenantContext,
        *,
        context_id: str,
        grant_id: str,
        input_document: Mapping[str, Any],
        executor_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Execute one exact grant; repository content cannot select an adapter."""

        self._store.require(context, self._store.ADMIN)
        safe_context_id = _identifier(context_id, "context_id")
        safe_grant_id = _identifier(grant_id, "grant_id")
        safe_executor = require_actor_id(executor_id)
        safe_key = require_idempotency_key(idempotency_key)
        if len(safe_key.encode("utf-8")) < 8:
            raise ValidationError("IDEMPOTENCY_KEY_INVALID")
        if not isinstance(input_document, Mapping):
            raise ValidationError("DOWNSTREAM_TOOL_INPUT_INVALID")
        _reject_unsafe_tree(input_document, field="tool_input")
        input_body = _tool_input(input_document)
        input_digest = canonical_digest(input_body)
        request_digest = canonical_digest(
            {
                "context_id": safe_context_id,
                "grant_id": safe_grant_id,
                "executor_id": safe_executor,
                "input_digest": input_digest,
            }
        )
        tenant_id, project_id = context.tenant_id, context.project_id
        now = utc_now()
        with self._store.transaction() as connection:
            prior = connection.execute(
                """SELECT * FROM downstream_tool_executions
                    WHERE tenant_id=? AND project_id=? AND grant_id=? AND idempotency_key=?""",
                (tenant_id, project_id, safe_grant_id, safe_key),
            ).fetchone()
            if prior is not None:
                if str(prior["request_digest"]) != request_digest:
                    raise ConflictError("DOWNSTREAM_GATEWAY_IDEMPOTENCY_CONFLICT")
                if str(prior["state"]) in {"VERIFIED", "BLOCKED"}:
                    return _decoded(
                        prior["response_json"], prior["response_digest"],
                        "DOWNSTREAM_GATEWAY_RECEIPT_CORRUPT",
                    )
                raise ConflictError(
                    "DOWNSTREAM_TOOL_OUTCOME_RECONCILIATION_REQUIRED",
                    details={"automatic_retry_allowed": False},
                )
            context_row = connection.execute(
                """SELECT state,source_set_digest FROM downstream_agent_contexts
                    WHERE tenant_id=? AND project_id=? AND context_id=?""",
                (tenant_id, project_id, safe_context_id),
            ).fetchone()
            if context_row is None:
                raise NotFoundError("DOWNSTREAM_CONTEXT_NOT_FOUND")
            if str(context_row["state"]) != "ACTIVE":
                raise ConflictError("DOWNSTREAM_CONTEXT_INACTIVE")
            if str(context_row["source_set_digest"]) != input_body["source_set_digest"]:
                raise AuthorizationError("DOWNSTREAM_TOOL_SOURCE_SET_DIGEST_MISMATCH")
            allowed_sources = {
                str(row[0])
                for row in connection.execute(
                    """SELECT source_receipt_id FROM downstream_context_sources
                        WHERE tenant_id=? AND project_id=? AND context_id=?""",
                    (tenant_id, project_id, safe_context_id),
                ).fetchall()
            }
            if not set(input_body["source_receipt_ids"]) <= allowed_sources:
                raise AuthorizationError("DOWNSTREAM_TOOL_SOURCE_SCOPE_MISMATCH")
            grant = connection.execute(
                """SELECT * FROM downstream_tool_grants
                    WHERE tenant_id=? AND project_id=? AND context_id=? AND grant_id=?""",
                (tenant_id, project_id, safe_context_id, safe_grant_id),
            ).fetchone()
            if grant is None:
                raise NotFoundError("DOWNSTREAM_GRANT_NOT_FOUND")
            if str(grant["state"]) != "ISSUED":
                raise ConflictError("DOWNSTREAM_GRANT_NOT_EXECUTABLE")
            if _timestamp(grant["expires_at"], "grant.expires_at") <= datetime.now(UTC):
                execution_id = new_id("tool-execution")
                claim_fence = int(grant["claim_fence"]) + 1
                response = {
                    "state": "BLOCKED",
                    "code": "DOWNSTREAM_GRANT_EXPIRED",
                    "execution_id": execution_id,
                    "grant_id": safe_grant_id,
                    "side_effect_authorized": False,
                    "automatic_retry_allowed": False,
                }
                connection.execute(
                    """UPDATE downstream_tool_grants
                          SET state='EXPIRED',claim_fence=?,terminal_at=?
                        WHERE tenant_id=? AND project_id=? AND grant_id=?""",
                    (claim_fence, now, tenant_id, project_id, safe_grant_id),
                )
                connection.execute(
                    """INSERT INTO downstream_tool_executions VALUES
                       (?,?,?,?,?,?,?,?,?,'BLOCKED',NULL,NULL,NULL,?,?,?,?)""",
                    (
                        tenant_id, project_id, execution_id, safe_context_id, safe_grant_id,
                        safe_key, request_digest, safe_executor, claim_fence,
                        canonical_json(response), canonical_digest(response), now, now,
                    ),
                )
                self._denied_event(
                    connection, context, grant_id=safe_grant_id,
                    code="DOWNSTREAM_GRANT_EXPIRED",
                    idempotency_key=f"agent-tool-denied:{safe_grant_id}:{safe_key}",
                )
                return response
            if str(grant["input_digest"]) != input_digest:
                raise AuthorizationError("DOWNSTREAM_TOOL_INPUT_DIGEST_MISMATCH")
            tool_id = str(grant["tool_id"])
            adapter = self._adapters.get(tool_id)
            if adapter is None:
                execution_id = new_id("tool-execution")
                claim_fence = int(grant["claim_fence"]) + 1
                response = {
                    "state": "BLOCKED",
                    "code": "DOWNSTREAM_TOOL_ADAPTER_NOT_ALLOWLISTED",
                    "execution_id": execution_id,
                    "grant_id": safe_grant_id,
                    "side_effect_authorized": False,
                    "automatic_retry_allowed": False,
                }
                connection.execute(
                    """UPDATE downstream_tool_grants
                          SET state='BLOCKED',claim_fence=?,terminal_at=?
                        WHERE tenant_id=? AND project_id=? AND grant_id=?""",
                    (claim_fence, now, tenant_id, project_id, safe_grant_id),
                )
                connection.execute(
                    """INSERT INTO downstream_tool_executions VALUES
                       (?,?,?,?,?,?,?,?,?,'BLOCKED',NULL,NULL,NULL,?,?,?,?)""",
                    (
                        tenant_id, project_id, execution_id, safe_context_id, safe_grant_id,
                        safe_key, request_digest, safe_executor, claim_fence,
                        canonical_json(response), canonical_digest(response), now, now,
                    ),
                )
                self._denied_event(
                    connection, context, grant_id=safe_grant_id,
                    code="DOWNSTREAM_TOOL_ADAPTER_NOT_ALLOWLISTED",
                    idempotency_key=f"agent-tool-denied:{safe_grant_id}:{safe_key}",
                )
                return response
            execution_id = new_id("tool-execution")
            claim_fence = int(grant["claim_fence"]) + 1
            claim_token_digest = canonical_digest(
                {"execution_id": execution_id, "nonce": new_id("claim")}
            )
            connection.execute(
                """UPDATE downstream_tool_grants
                      SET state='CLAIMED',claim_fence=?,claim_token_digest=?,claimed_by=?,claimed_at=?
                    WHERE tenant_id=? AND project_id=? AND grant_id=?""",
                (
                    claim_fence, claim_token_digest, safe_executor, now,
                    tenant_id, project_id, safe_grant_id,
                ),
            )
            connection.execute(
                """INSERT INTO downstream_tool_executions VALUES
                   (?,?,?,?,?,?,?,?,?,'IN_PROGRESS',NULL,NULL,NULL,NULL,NULL,?,NULL)""",
                (
                    tenant_id, project_id, execution_id, safe_context_id, safe_grant_id,
                    safe_key, request_digest, safe_executor, claim_fence, now,
                ),
            )
            invocation = DownstreamToolInvocation(
                tenant_id=tenant_id,
                project_id=project_id,
                context_id=safe_context_id,
                grant_id=safe_grant_id,
                execution_id=execution_id,
                tool_id=tool_id,
                subject_id=str(grant["subject_id"]),
                input_document=input_body,
                input_digest=input_digest,
                claim_fence=claim_fence,
            )
        try:
            candidate = adapter.execute(invocation)
            if not isinstance(candidate, Mapping):
                raise IntegrityError("DOWNSTREAM_RESULT_RECEIPT_INVALID")
            verified_candidate = self._result_verifier.verify(invocation, candidate)
            if not isinstance(verified_candidate, Mapping):
                raise IntegrityError("DOWNSTREAM_RESULT_RECEIPT_INVALID")
            if verified_candidate.get("verifier_id") != self._verifier_id:
                raise AuthorizationError("DOWNSTREAM_RESULT_VERIFIER_IDENTITY_MISMATCH")
            # Re-read immutable bindings and verify the exact host receipt before
            # any state can become VERIFIED.
            with self._store.transaction() as connection:
                grant = connection.execute(
                    """SELECT * FROM downstream_tool_grants
                        WHERE tenant_id=? AND project_id=? AND grant_id=?""",
                    (tenant_id, project_id, safe_grant_id),
                ).fetchone()
                execution = connection.execute(
                    """SELECT * FROM downstream_tool_executions
                        WHERE tenant_id=? AND project_id=? AND execution_id=?""",
                    (tenant_id, project_id, execution_id),
                ).fetchone()
                if (
                    grant is None
                    or execution is None
                    or str(grant["state"]) != "CLAIMED"
                    or str(execution["state"]) != "IN_PROGRESS"
                ):
                    raise ConflictError("DOWNSTREAM_GATEWAY_CLAIM_LOST")
                receipt = DownstreamAgentBridge._result_receipt(
                    verified_candidate, tenant_id=tenant_id, project_id=project_id,
                    context_id=safe_context_id, grant=grant, execution=execution,
                )
                response = {
                    "state": "VERIFIED",
                    "code": "DOWNSTREAM_TOOL_RESULT_VERIFIED",
                    "execution_id": execution_id,
                    "grant_id": safe_grant_id,
                    "result_receipt_id": receipt["receipt_id"],
                    "result_digest": receipt["result_digest"],
                    "result_link_state": "NOT_RUN",
                    "automatic_retry_allowed": False,
                }
                connection.execute(
                    """UPDATE downstream_tool_executions
                          SET state='VERIFIED',result_receipt_id=?,result_receipt_json=?,
                              result_receipt_digest=?,response_json=?,response_digest=?,completed_at=?
                        WHERE tenant_id=? AND project_id=? AND execution_id=?""",
                    (
                        receipt["receipt_id"], canonical_json(receipt), receipt["receipt_digest"],
                        canonical_json(response), canonical_digest(response), utc_now(),
                        tenant_id, project_id, execution_id,
                    ),
                )
                connection.execute(
                    """UPDATE downstream_tool_grants
                          SET state='VERIFIED',execution_receipt_id=?,terminal_at=?
                        WHERE tenant_id=? AND project_id=? AND grant_id=?""",
                    (
                        receipt["receipt_id"], utc_now(), tenant_id, project_id,
                        safe_grant_id,
                    ),
                )
                return response
        except Exception:
            response = self._unknown_response(execution_id, safe_grant_id)
            with self._store.transaction() as connection:
                execution = connection.execute(
                    """SELECT state FROM downstream_tool_executions
                        WHERE tenant_id=? AND project_id=? AND execution_id=?""",
                    (tenant_id, project_id, execution_id),
                ).fetchone()
                if execution is not None and str(execution["state"]) == "IN_PROGRESS":
                    connection.execute(
                        """UPDATE downstream_tool_executions
                              SET state='UNKNOWN',response_json=?,response_digest=?,completed_at=?
                            WHERE tenant_id=? AND project_id=? AND execution_id=?""",
                        (
                            canonical_json(response), canonical_digest(response), utc_now(),
                            tenant_id, project_id, execution_id,
                        ),
                    )
                    connection.execute(
                        """UPDATE downstream_tool_grants SET state='UNKNOWN',terminal_at=?
                            WHERE tenant_id=? AND project_id=? AND grant_id=? AND state='CLAIMED'""",
                        (utc_now(), tenant_id, project_id, safe_grant_id),
                    )
            return response


__all__ = [
    "DownstreamAgentBridge",
    "DownstreamToolAdapter",
    "DownstreamToolGateway",
    "DownstreamToolInvocation",
    "DownstreamResultVerifier",
    "SKILL_NAME",
]
