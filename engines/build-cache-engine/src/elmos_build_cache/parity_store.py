"""Tenant-scoped durable metadata for the v1.2 cache-parity plane.

The repository stores only canonical, content-free documents.  Prompt/source
bytes, provider request payloads, artifact bytes, and secret values are not
accepted by this API.  Every record ID is an immutable idempotency key: an
exact replay returns the original document and any drift raises
``IdempotencyConflict``.

Imported v1.2 JSON Schemas are the external persistence contract.  They are
intentionally not weakened to accept the different internal dataclass shapes;
callers must construct the explicit external document they intend to persist.
Provider usage is the one internal envelope because the source package has no
standalone schema for normalized counters.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from .canonical import canonical_json_text, digest_of, require_digest
from .db.store import MetadataStore
from .errors import (
    ConflictError,
    ContractViolation,
    CorruptObject,
    ElmosCacheError,
    IdempotencyConflict,
    NotFound,
    TenantMismatch,
)
from .parity import MANDATORY_SCENARIOS
from .prompt_cache import NormalizedTokenUsage
from .schemas import validate

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}$")
_FORBIDDEN_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "content",
        "credential",
        "messages",
        "password",
        "prompt",
        "prompt_text",
        "raw_prompt",
        "raw_secret",
        "raw_source",
        "secret",
        "secret_value",
        "source",
        "source_code",
        "source_text",
    }
)
_USAGE_KEYS = frozenset(
    {
        "provider",
        "total_input_tokens",
        "processed_input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "accounting",
    }
)
_INTERNAL_REPORT_KEYS = frozenset(
    {
        "binding",
        "checks",
        "claim_policy",
        "cohorts",
        "decision",
        "failures",
        "kind",
        "mandatory_pass",
        "metrics",
        "missing",
        "report_digest",
        "report_id",
        "scenarios",
        "schema_version",
        "thresholds",
    }
)
_INTERNAL_REPORT_DECISIONS = frozenset(
    {"NOT_RUN", "FAILED", "READY_FOR_EXTERNAL_GATE"}
)
_ENVIRONMENT_FIELDS = frozenset(
    {
        "schema_version",
        "snapshot_id",
        "snapshot_key",
        "platform",
        "base_image_digest",
        "setup_script_digest",
        "maintenance_script_digest",
        "lockfile_digests",
        "toolchain_digests",
        "approved_environment_digest",
        "secret_reference_digest",
        "layers",
        "trust_namespace",
        "status",
        "created_at",
        "expires_at",
    }
)
_ENVIRONMENT_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "snapshot_id",
        "snapshot_key",
        "platform",
        "layers",
        "trust_namespace",
        "status",
    }
)
_ENVIRONMENT_PLATFORM_FIELDS = frozenset({"os", "arch", "libc"})
_ENVIRONMENT_PLATFORM_REQUIRED_FIELDS = frozenset({"os", "arch"})
_ENVIRONMENT_LAYER_FIELDS = frozenset({"layer_type", "digest", "size_bytes"})
_ENVIRONMENT_STATUS_EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "snapshot_key",
        "manifest_digest",
        "sequence",
        "event_id",
        "expected_status",
        "new_status",
        "reason_digest",
        "previous_event_digest",
        "event_digest",
    }
)


@dataclass(frozen=True)
class _RecordSpec:
    table: str
    id_column: str
    digest_column: str
    timestamp_column: str = "recorded_at"
    bound_columns: tuple[str, ...] = ()


_PROMPT = _RecordSpec(
    "prompt_prefix_manifests",
    "manifest_id",
    "manifest_digest",
    bound_columns=(
        "provider",
        "provider_namespace",
        "compatibility_group",
        "stable_prefix_digest",
    ),
)
_USAGE = _RecordSpec(
    "provider_cache_usage",
    "observation_id",
    "usage_digest",
    "observed_at",
    (
        "prompt_manifest_digest",
        "provider",
        "total_input_tokens",
        "processed_input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "accounting",
    ),
)
_ENVIRONMENT = _RecordSpec(
    "environment_snapshot_manifests",
    "snapshot_id",
    "manifest_digest",
    bound_columns=("snapshot_key", "trust_namespace", "status"),
)
_OUTCOME = _RecordSpec(
    "cache_outcome_events_v12",
    "event_id",
    "event_digest",
    bound_columns=("request_id", "layer", "outcome", "reason_code", "eligible"),
)
_AFFINITY = _RecordSpec(
    "cache_affinity_decisions_v12",
    "decision_id",
    "decision_digest",
    bound_columns=("request_id", "affinity_key", "selected_target"),
)
_REPORT = _RecordSpec(
    "cache_parity_reports_v12",
    "report_id",
    "report_digest",
    bound_columns=("mandatory_pass",),
)


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(f"{field} must be a bounded identifier", field=field)
    return value


def _assert_content_free(value: Any, path: str = "$") -> None:
    """Reject fields that could smuggle prompt, source, or secret material."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ContractViolation("metadata document keys must be strings", path=path)
            normalized = key.casefold().replace("-", "_")
            raw_sensitive = normalized.startswith("raw_") and any(
                marker in normalized for marker in ("prompt", "source", "secret", "credential")
            )
            text_sensitive = normalized.endswith(("_content", "_text")) and any(
                marker in normalized for marker in ("prompt", "source", "secret")
            )
            if normalized in _FORBIDDEN_KEYS or raw_sensitive or text_sensitive:
                raise ContractViolation(
                    "cache-parity metadata must not contain raw prompt, source, or secret fields",
                    path=f"{path}/{key}",
                )
            _assert_content_free(child, f"{path}/{key}")
    elif isinstance(value, list | tuple):
        for index, child in enumerate(value):
            _assert_content_free(child, f"{path}/{index}")


def _canonical_document(document: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        raise ContractViolation("parity metadata must be a JSON object")
    copied = dict(document)
    _assert_content_free(copied)
    try:
        decoded = json.loads(canonical_json_text(copied))
    except (TypeError, ValueError) as exc:
        raise ContractViolation("parity metadata must be canonically serialisable") from exc
    if not isinstance(decoded, dict):  # defensive: canonical input is required to be a mapping
        raise ContractViolation("parity metadata must be a JSON object")
    return cast(dict[str, Any], decoded)


def _assert_closed_mapping(
    value: Any,
    *,
    allowed: frozenset[str],
    required: frozenset[str],
    path: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ContractViolation("environment manifest member must be an object", path=path)
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown or missing:
        raise ContractViolation(
            "environment manifest has an invalid closed shape",
            path=path,
            unknown=unknown,
            missing=missing,
        )
    return value


def validate_environment_manifest_document(document: Mapping[str, Any]) -> None:
    """Apply the runtime environment overlay without changing the source Schema.

    The imported contract leaves nested objects open. Persistence and restore
    nevertheless require a closed, content-free representation so innocuous
    field names cannot smuggle prompt, source, or secret values.
    """

    root = _assert_closed_mapping(
        document,
        allowed=_ENVIRONMENT_FIELDS,
        required=_ENVIRONMENT_REQUIRED_FIELDS,
        path="$",
    )
    _assert_content_free(root)
    _assert_closed_mapping(
        root["platform"],
        allowed=_ENVIRONMENT_PLATFORM_FIELDS,
        required=_ENVIRONMENT_PLATFORM_REQUIRED_FIELDS,
        path="$/platform",
    )
    layers = root["layers"]
    if not isinstance(layers, list):
        raise ContractViolation("environment manifest layers must be an array", path="$/layers")
    for index, layer in enumerate(layers):
        _assert_closed_mapping(
            layer,
            allowed=_ENVIRONMENT_LAYER_FIELDS,
            required=_ENVIRONMENT_LAYER_FIELDS,
            path=f"$/layers/{index}",
        )
    validate("environment-snapshot", root)


def _decode_document(value: Any) -> dict[str, Any]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, dict):
        raise ContractViolation("stored cache-parity metadata is not a JSON object")
    return cast(dict[str, Any], decoded)


def _matched(document: Mapping[str, Any], field: str, expected: str) -> None:
    if document.get(field) != expected:
        raise ContractViolation(
            "path identity does not match the persisted document",
            field=field,
            expected=expected,
            actual=document.get(field),
        )


def _validate_internal_parity_report(
    document: Mapping[str, Any],
    *,
    tenant_id: str,
    project_id: str,
) -> None:
    """Validate the content-free ``ParityReport.to_dict()`` representation.

    This is a separate internal contract, not an expansion of the imported
    external JSON Schema.  It lets an honest ``NOT_RUN`` report retain its
    missing checks without fabricating the external schema's scenario fields.
    """

    if set(document) != _INTERNAL_REPORT_KEYS:
        raise ContractViolation(
            "internal parity report has an unexpected shape",
            unknown=sorted(set(document) - _INTERNAL_REPORT_KEYS),
            missing=sorted(_INTERNAL_REPORT_KEYS - set(document)),
        )
    if document["schema_version"] != "1.2.0":
        raise ContractViolation("internal parity report schema version is unsupported")
    if document["kind"] != "elmos.cache-parity-report/v1.2":
        raise ContractViolation("internal parity report kind is unsupported")
    if document["claim_policy"] != "measured_only_external_gate_required":
        raise ContractViolation("internal parity report claim policy cannot be weakened")
    decision = document["decision"]
    if decision not in _INTERNAL_REPORT_DECISIONS:
        raise ContractViolation("internal parity report decision is unknown")
    mandatory_pass = document["mandatory_pass"]
    if not isinstance(mandatory_pass, bool):
        raise ContractViolation("internal parity mandatory_pass must be boolean")
    if mandatory_pass != (decision == "READY_FOR_EXTERNAL_GATE"):
        raise ContractViolation("internal parity decision and mandatory_pass disagree")

    binding = document["binding"]
    if not isinstance(binding, Mapping):
        raise ContractViolation("internal parity evidence binding is missing")
    legacy_binding_fields = frozenset(
        {
            "configuration_digest",
            "corpus_digest",
            "executor_identity",
            "generated_at",
            "platform_digest",
            "provider_profiles_digest",
            "source_digest",
            "verifier_identity",
        }
    )
    scoped_binding_fields = legacy_binding_fields | frozenset(
        {"tenant_scope_digest", "authorization_digest"}
    )
    if set(binding) not in {legacy_binding_fields, scoped_binding_fields}:
        raise ContractViolation("internal parity evidence binding has an unexpected shape")
    binding_digests = (
        "source_digest",
        "configuration_digest",
        "provider_profiles_digest",
        "corpus_digest",
        "platform_digest",
    )
    for field in binding_digests:
        require_digest(str(binding.get(field)))
    if set(binding) == scoped_binding_fields:
        expected_scope = digest_of(
            {
                "tenant_id": _identifier(tenant_id, "tenant_id"),
                "project_id": _identifier(project_id, "project_id"),
            }
        )
        if binding.get("tenant_scope_digest") != expected_scope:
            raise ContractViolation(
                "internal parity evidence binding does not match the authenticated scope"
            )
        require_digest(str(binding.get("authorization_digest")))
    elif decision == "READY_FOR_EXTERNAL_GATE":
        raise ContractViolation(
            "ready parity report requires authenticated scope and authorization"
        )
    executor = binding.get("executor_identity")
    verifier = binding.get("verifier_identity")
    if not isinstance(executor, str) or not executor or not isinstance(verifier, str) or not verifier:
        raise ContractViolation("internal parity executor/verifier binding is incomplete")
    if executor == verifier:
        raise ContractViolation("internal parity executor and verifier must be independent")
    if not isinstance(binding.get("generated_at"), str) or not binding["generated_at"]:
        raise ContractViolation("internal parity generated_at binding is missing")

    for field in ("metrics", "cohorts", "thresholds"):
        if not isinstance(document[field], Mapping):
            raise ContractViolation("internal parity metric documents must be objects", field=field)
    for field in ("checks", "scenarios", "failures", "missing"):
        if not isinstance(document[field], list):
            raise ContractViolation("internal parity result collections must be arrays", field=field)
    if any(not isinstance(value, str) for value in (*document["failures"], *document["missing"])):
        raise ContractViolation("internal parity failure/missing entries must be strings")

    metrics = cast(Mapping[str, Any], document["metrics"])
    thresholds = cast(Mapping[str, Any], document["thresholds"])
    for field, values in (("metrics", metrics), ("thresholds", thresholds)):
        for name, value in values.items():
            if not isinstance(name, str) or not name:
                raise ContractViolation("internal parity metric names cannot be empty", field=field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(float(value))
            ):
                raise ContractViolation("internal parity metrics must be finite numbers", field=field)
    cohorts = cast(Mapping[str, Any], document["cohorts"])
    for cohort, values in cohorts.items():
        if not isinstance(cohort, str) or not cohort or not isinstance(values, Mapping):
            raise ContractViolation("internal parity cohorts must be named metric objects")
        for name, value in values.items():
            if (
                not isinstance(name, str)
                or not name
                or isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(float(value))
            ):
                raise ContractViolation("internal parity cohort metrics must be finite numbers")

    checks = cast(list[Any], document["checks"])
    for check in checks:
        if not isinstance(check, Mapping) or set(check) != {
            "name",
            "actual",
            "expected",
            "operator",
            "passed",
            "scope",
        }:
            raise ContractViolation("internal parity metric check has an unexpected shape")
        if check["operator"] not in {"required", ">=", "<=", "=="}:
            raise ContractViolation("internal parity metric check operator is unknown")
        if not isinstance(check["passed"], bool):
            raise ContractViolation("internal parity metric check passed flag must be boolean")

    scenarios = cast(list[Any], document["scenarios"])
    seen_scenarios: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, Mapping) or set(scenario) != {
            "scenario_id",
            "status",
            "evidence_digests",
            "detail",
        }:
            raise ContractViolation("internal parity scenario has an unexpected shape")
        scenario_id = scenario["scenario_id"]
        if scenario_id not in MANDATORY_SCENARIOS or scenario_id in seen_scenarios:
            raise ContractViolation("internal parity scenario identity is unknown or duplicated")
        seen_scenarios.add(cast(str, scenario_id))
        status = scenario["status"]
        if status not in {"PASS", "FAIL", "NOT_RUN", "BLOCKED"}:
            raise ContractViolation("internal parity scenario status is unknown")
        evidence = scenario["evidence_digests"]
        if not isinstance(evidence, list):
            raise ContractViolation("internal parity scenario evidence must be an array")
        for evidence_digest in evidence:
            require_digest(str(evidence_digest))
        if status == "PASS" and not evidence:
            raise ContractViolation("passed internal parity scenario requires raw evidence")
        if not isinstance(scenario["detail"], Mapping):
            raise ContractViolation("internal parity scenario detail must be an object")

    failures = document["failures"]
    missing = document["missing"]
    for scenario_id in MANDATORY_SCENARIOS:
        if scenario_id not in seen_scenarios and f"scenario:{scenario_id}" not in missing:
            raise ContractViolation("internal parity report hides an unexecuted mandatory scenario")
    derived_decision = (
        "NOT_RUN" if missing else "FAILED" if failures else "READY_FOR_EXTERNAL_GATE"
    )
    if decision != derived_decision:
        raise ContractViolation("internal parity decision does not match missing/failure evidence")

    report_digest = require_digest(str(document["report_digest"]))
    digest_body = {
        "schema_version": document["schema_version"],
        "report_id": document["report_id"],
        "decision": decision,
        "binding": dict(binding),
        "metrics": document["metrics"],
        "cohorts": document["cohorts"],
        "checks": document["checks"],
        "scenarios": document["scenarios"],
        "failures": failures,
        "missing": missing,
        "thresholds": document["thresholds"],
    }
    if digest_of(digest_body) != report_digest:
        raise ContractViolation("internal parity report digest does not bind the report body")


def _validate_parity_report_document(
    document: Mapping[str, Any],
    *,
    tenant_id: str,
    project_id: str,
) -> None:
    if document.get("kind") == "elmos.cache-parity-report/v1.2":
        _validate_internal_parity_report(
            document,
            tenant_id=tenant_id,
            project_id=project_id,
        )
    else:
        validate("cache-parity-report", document)
    mandatory_pass = document.get("mandatory_pass")
    if mandatory_pass and document.get("decision") not in {
        None,
        "READY_FOR_EXTERNAL_GATE",
    }:
        raise ContractViolation("mandatory parity pass has an incompatible decision")
    if mandatory_pass and any(
        document.get(field, 0) != 0
        for field in ("false_hits", "cross_tenant_hits", "corrupt_executions")
    ):
        raise ContractViolation("mandatory parity cannot pass a zero-tolerance failure")


def _validate_document_for_spec(
    spec: _RecordSpec,
    document: Mapping[str, Any],
    *,
    tenant_id: str,
    project_id: str,
) -> None:
    _assert_content_free(document)
    if spec is _PROMPT:
        validate("prompt-prefix-manifest", document)
    elif spec is _ENVIRONMENT:
        validate_environment_manifest_document(document)
    elif spec is _OUTCOME:
        validate("cache-outcome-event", document)
    elif spec is _AFFINITY:
        validate("cache-affinity-decision", document)
    elif spec is _REPORT:
        _validate_parity_report_document(
            document,
            tenant_id=tenant_id,
            project_id=project_id,
        )


def _column_matches_document(column_value: Any, document_value: Any) -> bool:
    if isinstance(document_value, bool):
        return (
            isinstance(column_value, bool | int)
            and not isinstance(column_value, float)
            and column_value in {0, 1}
            and bool(column_value) is document_value
        )
    return bool(column_value == document_value)


def _stored_select(spec: _RecordSpec) -> str:
    columns = (
        "tenant_id",
        "project_id",
        spec.id_column,
        spec.digest_column,
        *spec.bound_columns,
        "document",
    )
    return ",".join(columns)


def _validated_stored_row(
    spec: _RecordSpec,
    row: Sequence[Any],
    *,
    tenant_id: str,
    project_id: str,
    record_id: str,
    expected_document_fields: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Validate every persisted identity and digest before returning metadata."""

    try:
        expected_length = 5 + len(spec.bound_columns)
        if len(row) != expected_length:
            raise ContractViolation("stored cache-parity row has an unexpected shape")
        if (
            str(row[0]) != tenant_id
            or str(row[1]) != project_id
            or str(row[2]) != record_id
        ):
            raise ContractViolation("stored cache-parity row identity does not match its path")
        stored_digest = require_digest(str(row[3]))
        document = _decode_document(row[-1])
        if digest_of(document) != stored_digest:
            raise ContractViolation("stored cache-parity document digest does not match")
        _matched(document, spec.id_column, record_id)
        for field, expected in (expected_document_fields or {}).items():
            _matched(document, field, expected)
        for index, field in enumerate(spec.bound_columns, start=4):
            if not _column_matches_document(row[index], document.get(field)):
                raise ContractViolation(
                    "stored cache-parity column does not match its document",
                    field=field,
                )
        _validate_document_for_spec(
            spec,
            document,
            tenant_id=tenant_id,
            project_id=project_id,
        )
    except CorruptObject:
        raise
    except (ElmosCacheError, IndexError, TypeError, ValueError) as exc:
        raise CorruptObject(
            "stored cache-parity metadata failed integrity validation",
            kind=spec.table,
            record_id=record_id,
        ) from exc
    return document


def _validated_environment_status_event(
    row: Sequence[Any],
    *,
    tenant_id: str,
    project_id: str,
    snapshot_key: str,
    manifest_digest: str,
    expected_sequence: int,
    expected_previous_digest: str | None,
    effective_status: str,
) -> dict[str, Any]:
    try:
        if len(row) != 11:
            raise ContractViolation("stored environment status row has an unexpected shape")
        if (
            str(row[0]) != tenant_id
            or str(row[1]) != project_id
            or str(row[2]) != snapshot_key
            or isinstance(row[3], bool)
            or not isinstance(row[3], int)
            or row[3] != expected_sequence
        ):
            raise ContractViolation("environment status sequence or scope is not contiguous")
        event_id = _identifier(str(row[4]), "event_id")
        expected_status = str(row[5])
        new_status = str(row[6])
        reason_digest = require_digest(str(row[7]))
        previous_digest = None if row[8] is None else require_digest(str(row[8]))
        event_digest = require_digest(str(row[9]))
        document = _decode_document(row[10])
        if set(document) != _ENVIRONMENT_STATUS_EVENT_FIELDS:
            raise ContractViolation("environment status document has an unexpected shape")
        _assert_content_free(document)
        if document.get("schema_version") != "1.2.0" or document.get("kind") != (
            "elmos.environment-snapshot-status/v1"
        ):
            raise ContractViolation("environment status document contract is unsupported")
        column_bindings = {
            "snapshot_key": snapshot_key,
            "sequence": expected_sequence,
            "event_id": event_id,
            "expected_status": expected_status,
            "new_status": new_status,
            "reason_digest": reason_digest,
            "previous_event_digest": previous_digest,
            "event_digest": event_digest,
        }
        if any(document.get(field) != value for field, value in column_bindings.items()):
            raise ContractViolation("environment status columns do not match their document")
        if document.get("manifest_digest") != manifest_digest:
            raise ContractViolation("environment status event is bound to another manifest")
        if previous_digest != expected_previous_digest:
            raise ContractViolation("environment status event chain digest is discontinuous")
        if expected_status != effective_status or expected_status != "AVAILABLE":
            raise ContractViolation("environment status transition predecessor is invalid")
        if new_status not in {"QUARANTINED", "REVOKED"}:
            raise ContractViolation("environment status transition is not terminal")
        event_body = {key: document[key] for key in document if key != "event_digest"}
        if digest_of(event_body) != event_digest:
            raise ContractViolation("environment status event digest does not bind its body")
    except CorruptObject:
        raise
    except (ElmosCacheError, IndexError, TypeError, ValueError) as exc:
        raise CorruptObject(
            "stored environment status chain failed integrity validation",
            snapshot_key=snapshot_key,
            sequence=expected_sequence,
        ) from exc
    return document


class ParityMetadataRepository:
    """Immutable persistence boundary shared by API, pipeline, and workers."""

    def __init__(self, store: MetadataStore, *, project_scope_claim: bool = True) -> None:
        self.store = store
        # ``projects.project_id`` is a *global* primary key, so writing a parity
        # record for a project nobody owns yet also claims that name forever.
        # That is a legitimate act for trusted in-process composition holding
        # the store directly -- the CLI, the pipeline bootstrap, the snapshot
        # sealer -- and never a legitimate side effect of serving a request.
        # Request-serving callers must therefore build this repository with
        # ``project_scope_claim=False``; :class:`~elmos_build_cache.api.
        # CacheControlPlane` enforces that for every repository it is given.
        self.project_scope_claim = project_scope_claim

    def without_project_claim(self) -> ParityMetadataRepository:
        """Return a view of this repository that can never claim a project."""

        if not self.project_scope_claim:
            return self
        return ParityMetadataRepository(self.store, project_scope_claim=False)

    def _ensure_scope(self, tenant_id: str, project_id: str) -> None:
        """Bind a parity write to a project scope this tenant may use.

        Without ``project_scope_claim`` this deliberately does *not* create the
        project: creating one here would make every cache-parity write double
        as a claim on a globally unique name, so a caller could bring another
        tenant's not-yet-created project into existence -- and permanently
        block it, because the rightful tenant's own ``ensure_project`` then
        fails closed -- merely by compiling a prompt prefix against it.
        Claiming scope is a deliberate act and belongs to
        ``MetadataStore.ensure_project``, reached from ``POST /runs``, which
        answers ``CONFLICT`` for a name it may not have.

        Absent and foreign are answered with the same refusal on purpose.  A
        distinguishable "does not exist" would let an unrelated tenant
        enumerate the global project namespace one probe at a time.
        """

        _identifier(tenant_id, "tenant_id")
        _identifier(project_id, "project_id")
        row = self.store.query_one(
            "SELECT tenant_id FROM projects WHERE project_id=?",
            (project_id,),
        )
        if row is None and self.project_scope_claim:
            self.store.ensure_project(tenant_id, project_id)
            return
        if row is None or str(row[0]) != tenant_id:
            raise TenantMismatch(
                "project does not exist in the requested tenant scope",
                tenant_id=tenant_id,
                project_id=project_id,
            )

    def _put_immutable(
        self,
        spec: _RecordSpec,
        tenant_id: str,
        project_id: str,
        record_id: str,
        document: dict[str, Any],
        extra_columns: Sequence[str],
        extra_values: Sequence[Any],
    ) -> dict[str, Any]:
        _identifier(record_id, spec.id_column)
        if tuple(extra_columns) != spec.bound_columns:
            raise ContractViolation("cache-parity record columns do not match their closed spec")
        document_digest = digest_of(document)
        with self.store.transaction():
            self._ensure_scope(tenant_id, project_id)
            existing = self.store.query_one(
                # Table/column names come only from closed module constants.
                f"SELECT {_stored_select(spec)} FROM {spec.table} "  # noqa: S608
                f"WHERE tenant_id=? AND project_id=? AND {spec.id_column}=?",
                (tenant_id, project_id, record_id),
            )
            if existing is not None:
                stored = _validated_stored_row(
                    spec,
                    existing,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    record_id=record_id,
                )
                if digest_of(stored) != document_digest or stored != document:
                    raise IdempotencyConflict(
                        "cache-parity record ID was reused for a different document",
                        kind=spec.table,
                        record_id=record_id,
                    )
                return stored

            columns = (
                "tenant_id",
                "project_id",
                spec.id_column,
                spec.digest_column,
                *extra_columns,
                "document",
                spec.timestamp_column,
            )
            placeholders = ",".join("?" for _ in columns)
            cursor = self.store.execute(
                # Identifiers come only from closed constants/call sites in this module.
                f"INSERT INTO {spec.table} ({','.join(columns)}) VALUES ({placeholders}) "  # noqa: S608
                "ON CONFLICT DO NOTHING",
                (
                    tenant_id,
                    project_id,
                    record_id,
                    document_digest,
                    *extra_values,
                    canonical_json_text(document),
                    self.store.now(),
                ),
            )
            if cursor.rowcount != 1:
                raced = self.store.query_one(
                    # Table/column names come only from closed module constants.
                    f"SELECT {_stored_select(spec)} FROM {spec.table} "  # noqa: S608
                    f"WHERE tenant_id=? AND project_id=? AND {spec.id_column}=?",
                    (tenant_id, project_id, record_id),
                )
                if raced is None:
                    raise IdempotencyConflict(
                        "cache-parity document conflicts with an existing unique identity",
                        kind=spec.table,
                        record_id=record_id,
                    )
                stored = _validated_stored_row(
                    spec,
                    raced,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    record_id=record_id,
                )
                if digest_of(stored) != document_digest or stored != document:
                    raise IdempotencyConflict(
                        "cache-parity record ID was reused for a different document",
                        kind=spec.table,
                        record_id=record_id,
                    )
                return stored
        return document

    def _get_by_id(
        self,
        spec: _RecordSpec,
        tenant_id: str,
        project_id: str,
        record_id: str,
    ) -> dict[str, Any] | None:
        _identifier(tenant_id, "tenant_id")
        _identifier(project_id, "project_id")
        _identifier(record_id, spec.id_column)
        row = self.store.query_one(
            # Table/column names come only from closed module constants.
            f"SELECT {_stored_select(spec)} FROM {spec.table} "  # noqa: S608
            f"WHERE tenant_id=? AND project_id=? AND {spec.id_column}=?",
            (tenant_id, project_id, record_id),
        )
        if row is None:
            return None
        return _validated_stored_row(
            spec,
            row,
            tenant_id=tenant_id,
            project_id=project_id,
            record_id=record_id,
        )

    def put_prompt_manifest(
        self,
        tenant_id: str,
        project_id: str,
        manifest_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]:
        prepared = _canonical_document(document)
        validate("prompt-prefix-manifest", prepared)
        _matched(prepared, "manifest_id", manifest_id)
        require_digest(str(prepared["stable_prefix_digest"]))
        return self._put_immutable(
            _PROMPT,
            tenant_id,
            project_id,
            manifest_id,
            prepared,
            ("provider", "provider_namespace", "compatibility_group", "stable_prefix_digest"),
            (
                prepared.get("provider"),
                prepared["provider_namespace"],
                prepared["compatibility_group"],
                prepared["stable_prefix_digest"],
            ),
        )

    def get_prompt_manifest(
        self,
        tenant_id: str,
        project_id: str,
        manifest_id: str,
    ) -> dict[str, Any] | None:
        return self._get_by_id(_PROMPT, tenant_id, project_id, manifest_id)

    def put_provider_usage(
        self,
        tenant_id: str,
        project_id: str,
        observation_id: str,
        prompt_manifest_digest: str,
        usage: Mapping[str, Any] | NormalizedTokenUsage,
    ) -> dict[str, Any]:
        """Persist normalized provider counters, never a provider response."""

        require_digest(prompt_manifest_digest)
        telemetry = usage.telemetry() if isinstance(usage, NormalizedTokenUsage) else dict(usage)
        if set(telemetry) != _USAGE_KEYS:
            raise ContractViolation(
                "provider usage must contain only normalized counter fields",
                unknown=sorted(set(telemetry) - _USAGE_KEYS),
                missing=sorted(_USAGE_KEYS - set(telemetry)),
            )
        provider = telemetry.get("provider")
        if not isinstance(provider, str) or not provider:
            raise ContractViolation("normalized provider usage requires a provider")
        for field in (
            "total_input_tokens",
            "processed_input_tokens",
            "output_tokens",
            "cache_read_tokens",
        ):
            value = telemetry.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ContractViolation("normalized usage counters must be non-negative integers", field=field)
        cache_write = telemetry.get("cache_write_tokens")
        if cache_write is not None and (
            isinstance(cache_write, bool) or not isinstance(cache_write, int) or cache_write < 0
        ):
            raise ContractViolation(
                "cache_write_tokens must be null or a non-negative integer"
            )
        accounting = telemetry.get("accounting")
        if accounting not in {"INCLUSIVE", "ADDITIVE"}:
            raise ContractViolation("normalized usage accounting is unknown")
        if accounting == "ADDITIVE" and cache_write is None:
            raise ContractViolation("additive accounting requires cache_write_tokens")
        if telemetry["total_input_tokens"] != (
            telemetry["processed_input_tokens"] + telemetry["cache_read_tokens"]
        ):
            raise ContractViolation("normalized input-token counters do not reconcile")

        document = _canonical_document(
            {
                "schema_version": "1.2.0",
                "kind": "elmos.provider-cache-usage/v1",
                "observation_id": observation_id,
                "prompt_manifest_digest": prompt_manifest_digest,
                **telemetry,
            }
        )
        with self.store.transaction():
            self._ensure_scope(tenant_id, project_id)
            prompt = self.store.query_one(
                "SELECT provider FROM prompt_prefix_manifests "
                "WHERE tenant_id=? AND project_id=? AND manifest_digest=?",
                (tenant_id, project_id, prompt_manifest_digest),
            )
        if prompt is None:
            raise NotFound(
                "prompt manifest digest is not present in the requested scope",
                prompt_manifest_digest=prompt_manifest_digest,
            )
        if prompt[0] is not None and str(prompt[0]) != provider:
            raise ContractViolation("provider usage does not match the prompt manifest provider")
        return self._put_immutable(
            _USAGE,
            tenant_id,
            project_id,
            observation_id,
            document,
            (
                "prompt_manifest_digest",
                "provider",
                "total_input_tokens",
                "processed_input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "accounting",
            ),
            (
                prompt_manifest_digest,
                provider,
                telemetry["total_input_tokens"],
                telemetry["processed_input_tokens"],
                telemetry["output_tokens"],
                telemetry["cache_read_tokens"],
                cache_write,
                accounting,
            ),
        )

    def put_environment_snapshot(
        self,
        tenant_id: str,
        project_id: str,
        snapshot_key: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]:
        require_digest(snapshot_key)
        prepared = _canonical_document(document)
        validate_environment_manifest_document(prepared)
        _matched(prepared, "snapshot_key", snapshot_key)
        snapshot_id = _identifier(str(prepared["snapshot_id"]), "snapshot_id")
        return self._put_immutable(
            _ENVIRONMENT,
            tenant_id,
            project_id,
            snapshot_id,
            prepared,
            ("snapshot_key", "trust_namespace", "status"),
            (snapshot_key, prepared["trust_namespace"], prepared["status"]),
        )

    def _read_environment_manifest(
        self,
        tenant_id: str,
        project_id: str,
        snapshot_key: str,
    ) -> tuple[dict[str, Any], str, str] | None:
        _identifier(tenant_id, "tenant_id")
        _identifier(project_id, "project_id")
        require_digest(snapshot_key)
        row = self.store.query_one(
            f"SELECT {_stored_select(_ENVIRONMENT)} FROM environment_snapshot_manifests "  # noqa: S608
            "WHERE tenant_id=? AND project_id=? AND snapshot_key=?",
            (tenant_id, project_id, snapshot_key),
        )
        if row is None:
            return None
        snapshot_id = str(row[2])
        document = _validated_stored_row(
            _ENVIRONMENT,
            row,
            tenant_id=tenant_id,
            project_id=project_id,
            record_id=snapshot_id,
            expected_document_fields={"snapshot_key": snapshot_key},
        )
        return document, str(row[3]), str(row[6])

    def get_environment_snapshot(
        self,
        tenant_id: str,
        project_id: str,
        snapshot_key: str,
    ) -> dict[str, Any] | None:
        stored = self._read_environment_manifest(tenant_id, project_id, snapshot_key)
        return None if stored is None else stored[0]

    def _read_environment_state(
        self,
        tenant_id: str,
        project_id: str,
        snapshot_key: str,
    ) -> tuple[dict[str, Any], str, str, tuple[dict[str, Any], ...]] | None:
        manifest = self._read_environment_manifest(tenant_id, project_id, snapshot_key)
        if manifest is None:
            return None
        document, manifest_digest, base_status = manifest
        rows = self.store.query(
            "SELECT tenant_id,project_id,snapshot_key,sequence,event_id,expected_status,"
            "new_status,reason_digest,previous_event_digest,event_digest,document "
            "FROM environment_snapshot_status_events "
            "WHERE tenant_id=? AND project_id=? AND snapshot_key=? ORDER BY sequence",
            (tenant_id, project_id, snapshot_key),
        )
        events: list[dict[str, Any]] = []
        previous_digest: str | None = None
        effective_status = base_status
        for sequence, row in enumerate(rows, start=1):
            event = _validated_environment_status_event(
                row,
                tenant_id=tenant_id,
                project_id=project_id,
                snapshot_key=snapshot_key,
                manifest_digest=manifest_digest,
                expected_sequence=sequence,
                expected_previous_digest=previous_digest,
                effective_status=effective_status,
            )
            events.append(event)
            previous_digest = str(event["event_digest"])
            effective_status = str(event["new_status"])
        return document, manifest_digest, effective_status, tuple(events)

    def append_environment_snapshot_status(
        self,
        tenant_id: str,
        project_id: str,
        snapshot_key: str,
        event_id: str,
        expected_status: str,
        new_status: str,
        reason_digest: str,
    ) -> dict[str, Any]:
        """Append a fenced terminal quarantine/revocation transition.

        The sealed manifest remains byte-for-byte immutable.  Recovery to
        ``AVAILABLE`` requires a newly sealed snapshot identity; status history
        is never edited or deleted.
        """

        require_digest(snapshot_key)
        require_digest(reason_digest)
        _identifier(event_id, "event_id")
        if expected_status != "AVAILABLE":
            raise ContractViolation("only an available snapshot may transition terminally")
        if new_status not in {"QUARANTINED", "REVOKED"}:
            raise ContractViolation("snapshot status may only become quarantined or revoked")

        with self.store.transaction():
            self._ensure_scope(tenant_id, project_id)
            state = self._read_environment_state(tenant_id, project_id, snapshot_key)
            if state is None:
                raise NotFound(
                    "environment snapshot is not present in the requested scope",
                    snapshot_key=snapshot_key,
                )
            _manifest_document, manifest_digest, current_status, events = state

            existing = next(
                (event for event in events if event["event_id"] == event_id),
                None,
            )
            if existing is not None:
                if (
                    existing.get("expected_status") != expected_status
                    or existing.get("new_status") != new_status
                    or existing.get("reason_digest") != reason_digest
                ):
                    raise IdempotencyConflict(
                        "environment status event ID was reused with drift",
                        event_id=event_id,
                    )
                return existing

            if current_status != expected_status:
                raise ConflictError(
                    "environment snapshot status compare-and-set failed",
                    expected_status=expected_status,
                    actual_status=current_status,
                )
            sequence = len(events) + 1
            previous_event_digest = (
                None if not events else str(events[-1]["event_digest"])
            )
            event_body = {
                "schema_version": "1.2.0",
                "kind": "elmos.environment-snapshot-status/v1",
                "snapshot_key": snapshot_key,
                "manifest_digest": manifest_digest,
                "sequence": sequence,
                "event_id": event_id,
                "expected_status": expected_status,
                "new_status": new_status,
                "reason_digest": reason_digest,
                "previous_event_digest": previous_event_digest,
            }
            event_document = {**event_body, "event_digest": digest_of(event_body)}
            cursor = self.store.execute(
                "INSERT INTO environment_snapshot_status_events "
                "(tenant_id, project_id, snapshot_key, sequence, event_id, expected_status, "
                "new_status, reason_digest, previous_event_digest, event_digest, document, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                (
                    tenant_id,
                    project_id,
                    snapshot_key,
                    sequence,
                    event_id,
                    expected_status,
                    new_status,
                    reason_digest,
                    previous_event_digest,
                    event_document["event_digest"],
                    canonical_json_text(event_document),
                    self.store.now(),
                ),
            )
            if cursor.rowcount != 1:
                raced_state = self._read_environment_state(
                    tenant_id,
                    project_id,
                    snapshot_key,
                )
                raced_events = () if raced_state is None else raced_state[3]
                raced = next(
                    (event for event in raced_events if event["event_id"] == event_id),
                    None,
                )
                if raced == event_document:
                    return event_document
                raise ConflictError(
                    "environment snapshot received a concurrent terminal transition",
                    snapshot_key=snapshot_key,
                )
        return event_document

    def get_environment_snapshot_state(
        self,
        tenant_id: str,
        project_id: str,
        snapshot_key: str,
    ) -> dict[str, Any] | None:
        state = self._read_environment_state(tenant_id, project_id, snapshot_key)
        if state is None:
            return None
        manifest, manifest_digest, effective_status, events = state
        return {
            "manifest": manifest,
            "manifest_digest": manifest_digest,
            "effective_status": effective_status,
            "latest_status_event": None if not events else events[-1],
        }

    def put_cache_outcome(
        self,
        tenant_id: str,
        project_id: str,
        request_id: str,
        event_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]:
        _identifier(request_id, "request_id")
        prepared = _canonical_document(document)
        validate("cache-outcome-event", prepared)
        _matched(prepared, "request_id", request_id)
        _matched(prepared, "event_id", event_id)
        return self._put_immutable(
            _OUTCOME,
            tenant_id,
            project_id,
            event_id,
            prepared,
            ("request_id", "layer", "outcome", "reason_code", "eligible"),
            (
                request_id,
                prepared["layer"],
                prepared["outcome"],
                prepared["reason_code"],
                prepared["eligible"],
            ),
        )

    def list_cache_outcomes(
        self,
        tenant_id: str,
        project_id: str,
        request_id: str,
    ) -> tuple[dict[str, Any], ...]:
        _identifier(tenant_id, "tenant_id")
        _identifier(project_id, "project_id")
        _identifier(request_id, "request_id")
        rows = self.store.query(
            f"SELECT {_stored_select(_OUTCOME)} FROM cache_outcome_events_v12 "  # noqa: S608
            "WHERE tenant_id=? AND project_id=? AND request_id=? "
            "ORDER BY recorded_at, event_id",
            (tenant_id, project_id, request_id),
        )
        return tuple(
            _validated_stored_row(
                _OUTCOME,
                row,
                tenant_id=tenant_id,
                project_id=project_id,
                record_id=str(row[2]),
                expected_document_fields={"request_id": request_id},
            )
            for row in rows
        )

    def put_affinity_decision(
        self,
        tenant_id: str,
        project_id: str,
        request_id: str,
        decision_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]:
        _identifier(request_id, "request_id")
        prepared = _canonical_document(document)
        validate("cache-affinity-decision", prepared)
        _matched(prepared, "request_id", request_id)
        _matched(prepared, "decision_id", decision_id)
        require_digest(str(prepared["affinity_key"]))
        return self._put_immutable(
            _AFFINITY,
            tenant_id,
            project_id,
            decision_id,
            prepared,
            ("request_id", "affinity_key", "selected_target"),
            (request_id, prepared["affinity_key"], prepared["selected_target"]),
        )

    def put_parity_report(
        self,
        tenant_id: str,
        project_id: str,
        report_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]:
        prepared = _canonical_document(document)
        _validate_parity_report_document(
            prepared,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        _matched(prepared, "report_id", report_id)
        return self._put_immutable(
            _REPORT,
            tenant_id,
            project_id,
            report_id,
            prepared,
            ("mandatory_pass",),
            (prepared["mandatory_pass"],),
        )

    def get_parity_report(
        self,
        tenant_id: str,
        project_id: str,
        report_id: str,
    ) -> dict[str, Any] | None:
        return self._get_by_id(_REPORT, tenant_id, project_id, report_id)


__all__ = ["ParityMetadataRepository"]
