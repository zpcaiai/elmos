"""Single, versioned registry for public multimodal Skill operations.

The registry is deliberately data-only.  It is the authority used by the API
boundary and is mirrored by the OpenAPI and checked-in SDKs.  Unknown pairs are
adapter requirements, not permissive extension points.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import binascii
import hashlib
import re
from types import MappingProxyType
from typing import Any, Mapping

from .canonical import canonical_digest
from .errors import ValidationError

OPERATION_REGISTRY_SCHEMA_VERSION = "multimodal-operation-registry-v1"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_EVALUATION_SUBJECT_FIELDS = frozenset(
    {"subject_id", "subject_kind", "artifact_digest", "implementation_version", "configuration_digest"}
)
_EVALUATION_EVIDENCE_FIELDS = frozenset({"case_id", "media_type", "content_base64"})
_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class OperationSpec:
    skill: str
    operation: str
    input_fields: frozenset[str]
    required_input_fields: frozenset[str] = frozenset()

    def document(self) -> dict[str, Any]:
        return {
            "skill": self.skill,
            "operation": self.operation,
            "input_fields": sorted(self.input_fields),
            "required_input_fields": sorted(self.required_input_fields),
        }


def _spec(skill: str, operation: str, fields: str = "", required: str = "") -> OperationSpec:
    allowed = frozenset(fields.split())
    mandatory = frozenset(required.split())
    if mandatory - allowed:
        raise RuntimeError(f"required fields are not allowed for {skill}/{operation}")
    return OperationSpec(skill, operation, allowed, mandatory)


def _single(skill: str, operation: str, fields: str) -> tuple[OperationSpec, ...]:
    return (_spec(skill, operation, fields),)


_SPECS = (
    _spec("elmos-multimodal-input-orchestrator", "bootstrap_project"),
    _spec("elmos-multimodal-input-orchestrator", "create_session", "requested_role"),
    _spec("elmos-multimodal-input-orchestrator", "process_session", "session_id max_attempts expected_asset_generation_digest", "session_id"),
    _spec("elmos-multimodal-input-orchestrator", "resume_job", "job_id", "job_id"),
    _spec("elmos-multimodal-input-orchestrator", "cancel_job", "job_id", "job_id"),
    _spec("elmos-multimodal-input-orchestrator", "get_session", "session_id", "session_id"),
    _spec("elmos-secure-resumable-upload", "start", "session_id display_name declared_media_type expected_size expected_sha256 part_size ttl_seconds", "session_id display_name declared_media_type expected_size expected_sha256"),
    _spec("elmos-secure-resumable-upload", "upload_part", "upload_session_id upload_id part_number byte_offset data_b64 bytes_b64 sha256 part_sha256", "part_number byte_offset"),
    _spec("elmos-secure-resumable-upload", "commit", "upload_session_id upload_id"),
    _spec("elmos-secure-resumable-upload", "status", "upload_session_id upload_id"),
    _spec("elmos-secure-resumable-upload", "abort", "upload_session_id upload_id"),
    _spec("elmos-file-type-detection-and-validation", "inspect", "asset_id", "asset_id"),
    _spec("elmos-file-type-detection-and-validation", "process_asset", "asset_id", "asset_id"),
    _spec("elmos-malware-quarantine-and-sandbox", "inspect", "asset_id", "asset_id"),
    _spec("elmos-malware-quarantine-and-sandbox", "process_asset", "asset_id", "asset_id"),
    *(_spec(skill, operation, "asset_id revision_mode", "asset_id") for skill in (
        "elmos-audio-asr-and-diarization", "elmos-image-ocr-and-preprocessing",
        "elmos-pdf-layout-table-parser", "elmos-word-document-parser",
        "elmos-markdown-text-log-parser",
    ) for operation in ("parse", "process_asset")),
    *(_spec(skill, operation, "asset_id", "asset_id") for skill in (
        "elmos-visual-ui-understanding", "elmos-diagram-and-architecture-understanding",
    ) for operation in ("parse", "process_asset", "understand")),
    *_single("elmos-unified-multimodal-content-ir", "normalize", "blocks relations source_schema_version document_id"),
    *_single("elmos-source-anchor-and-provenance", "anchor", "anchors derivations critical_item_ids"),
    _spec("elmos-multimodal-requirement-extraction", "extract", "sources package_version projection_key task_id", "package_version"),
    _spec("elmos-multi-asset-content-fusion", "fuse", "assets package_version projection_key task_id", "package_version"),
    _spec("elmos-document-version-and-conflict-detection", "detect_conflicts", "claims package_version projection_key task_id", "package_version"),
    *(
        _spec("elmos-human-review-and-correction", operation, fields, required)
        for operation, fields, required in (
            (
                "correct",
                "content_id expected_version value reason expected_digest",
                "content_id expected_version value reason",
            ),
            ("enqueue", "content_id expected_asset_version target_kind target_digest expected_head_version expected_snapshot_id expected_snapshot_digest expected_head_value_digest original_value_digest reason", "content_id expected_asset_version target_kind target_digest expected_head_version expected_snapshot_id expected_snapshot_digest expected_head_value_digest original_value_digest reason"),
            ("enqueue_prepare", "recovery_handle execute_idempotency_key content_id expected_asset_version target_kind target_digest expected_head_version expected_snapshot_id expected_snapshot_digest expected_head_value_digest original_value_digest reason", "recovery_handle execute_idempotency_key content_id expected_asset_version target_kind target_digest expected_head_version expected_snapshot_id expected_snapshot_digest expected_head_value_digest original_value_digest reason"),
            ("enqueue_execute", "recovery_handle", "recovery_handle"),
            ("source_register", "content_id expected_asset_version target_kind target original_value confidence provenance", "content_id expected_asset_version target_kind target original_value confidence provenance"),
            ("source_list", "content_id expected_asset_version kinds limit cursor", "content_id expected_asset_version"),
            ("source_get", "content_id expected_asset_version target_kind target_digest expected_head_version", "content_id expected_asset_version target_kind target_digest expected_head_version"),
            ("list", "kinds states confidence_lte limit cursor", ""),
            ("get", "task_id", "task_id"),
            ("current_correction", "task_id", "task_id"),
            ("claim", "task_id expected_version claim_token lease_seconds", "task_id expected_version claim_token"),
            ("edit", "task_id expected_version expected_correction_version claim_token claim_fence correction", "task_id expected_version expected_correction_version claim_token claim_fence correction"),
            ("approve", "task_id expected_version claim_token claim_fence reason", "task_id expected_version claim_token claim_fence reason"),
            ("reject", "task_id expected_version claim_token claim_fence reason", "task_id expected_version claim_token claim_fence reason"),
            ("reopen", "task_id expected_version reason", "task_id expected_version reason"),
            ("revert", "task_id expected_version reason", "task_id expected_version reason"),
            ("propagation_status", "task_id", "task_id"),
            ("reservation_status", "task_id", "task_id"),
            ("propagation_claim", "propagation_id owner_token lease_seconds", "propagation_id owner_token"),
            ("propagation_dispatch", "propagation_id owner_token claim_fence", "propagation_id owner_token claim_fence"),
            ("propagation_complete", "propagation_id owner_token claim_fence outcome result failure_code", "propagation_id owner_token claim_fence outcome"),
            ("propagation_reconcile", "propagation_id outcome result failure_code", "propagation_id outcome"),
        )
    ),
    *_single("elmos-prompt-injection-defense", "evaluate", "text requested_tools"),
    *_single("elmos-provider-routing-and-fallback", "route", "asset_id modality data_classification parameters"),
    *(_spec("elmos-storage-index-and-retrieval", operation, fields) for operation, fields in (
        ("upsert", "branch package_version document_id text content_digest source_digest source_anchor required_permissions expected_version confidence"),
        ("query", "branch package_version query limit"), ("delete", "branch package_version source_digest"),
        ("repair", "branch package_version"), ("rebuild_status", "branch package_version status limit"),
    )),
    *(_spec("elmos-durable-processing-and-recovery", operation, fields) for operation, fields in (
        ("transition", "task_id target_state current_state payload checkpoint_digest attempted_effect_receipts recorded_effect_receipts"),
        ("process_durable_transition", "task_id target_state current_state payload checkpoint_digest attempted_effect_receipts recorded_effect_receipts"),
        ("get_task_state", "task_id"), ("list_outbox", "aggregate_type aggregate_id published limit"),
        ("mark_outbox_published", "event_id publisher_capability transport_receipt"),
    )),
    *_single("elmos-processing-cost-and-eta-estimation", "estimate", "currency stages history prices"),
    *_single("elmos-multimodal-observability", "observe", "events trace_id"),
    _spec("elmos-multimodal-evaluation-framework", "evaluate", "subject evidence", "subject evidence"),
    _spec("elmos-multimodal-evaluation-framework", "verify", "run_id", "run_id"),
    _spec("elmos-multimodal-evaluation-framework", "get_run", "run_id", "run_id"),
    _spec("elmos-multimodal-evaluation-framework", "catalog"),
    *(_spec("elmos-multimodal-input-workbench-ui", operation, "entries" if operation == "build_preview" else "") for operation in ("describe", "capabilities", "health", "build_preview")),
    *(_spec("elmos-ingestion-api-and-sdk", operation) for operation in ("describe", "capabilities", "health", "build_contract")),
    *(_spec("elmos-data-retention-and-governance", operation, fields) for operation, fields in (
        ("evaluate", ""), ("provider_access", "asset_id"), ("delete", ""), ("export", ""), ("delete_status", "job_id"),
    )),
    _spec("elmos-downstream-agent-integration", "build_context", "task_id subject_id package_version source_receipt_ids tool_receipt_ids", "task_id subject_id package_version source_receipt_ids"),
    _spec("elmos-downstream-agent-integration", "get_context", "context_id", "context_id"),
    _spec("elmos-downstream-agent-integration", "get_grant", "context_id grant_id", "context_id grant_id"),
    _spec("elmos-downstream-agent-integration", "revoke_grant", "context_id grant_id reason", "context_id grant_id reason"),
    _spec("elmos-downstream-agent-integration", "link_result", "context_id grant_id result_receipt_id", "context_id grant_id result_receipt_id"),
    _spec("elmos-downstream-agent-integration", "list_result_links", "context_id", "context_id"),
    *_single("elmos-codex-context-capacity-parity", "check", "capability_snapshot task_id"),
    *_single("elmos-context-budget-manager", "calculate", "capability_snapshot reserved_output_tokens safety_headroom_tokens usage task_id"),
    *_single("elmos-multimodal-token-accounting", "account", "estimator_version items model_id model_version tokenizer_id tokenizer_version task_id current_window_output_reserved_tokens model_snapshot_id"),
    *_single("elmos-long-context-packing-and-ranking", "pack", "candidates effective_input_budget task_id"),
    *_single("elmos-context-pressure-monitor", "monitor", "effective_input_budget previous_state used_tokens task_id forecast_horizon next_turn_tokens pending_tool_tokens pending_test_log_tokens"),
    *_single("elmos-structured-context-compaction", "compact", "source_history_digest state task_id raw_history package_version model_snapshot_id rollback_checkpoint_id side_effect_cursor cost_cursor input_tokens output_tokens"),
    _spec("elmos-context-checkpoint-and-recovery", "create", "state payload task_id raw_history package_version model_snapshot_id rollback_checkpoint_id side_effect_cursor cost_cursor input_tokens output_tokens"),
    _spec("elmos-context-checkpoint-and-recovery", "list", "task_id"),
    _spec("elmos-context-checkpoint-and-recovery", "diff", "left_checkpoint_id right_checkpoint_id task_id", "left_checkpoint_id right_checkpoint_id"),
    _spec("elmos-context-checkpoint-and-recovery", "restore", "checkpoint_id task_id", "checkpoint_id"),
    _spec("elmos-context-checkpoint-and-recovery", "rollback", "checkpoint_id task_id", "checkpoint_id"),
    *_single("elmos-context-rehydration", "rehydrate", "package_version remaining_budget_tokens source_ids task_id"),
    *(_spec("elmos-project-memory-and-retrieval", operation, fields) for operation, fields in (
        ("write", "branch package_version memory_key value source_digest source_anchor required_permissions expected_version memory_kind semantic_state confidence"),
        ("query", "branch package_version query limit"), ("delete", "branch package_version source_digest"),
        ("repair", "branch package_version"), ("rebuild_status", "branch package_version status limit"),
    )),
    _spec("elmos-repository-context-map", "rebuild", "package_version source_input", "package_version source_input"),
    _spec("elmos-repository-context-map", "status", "package_version", "package_version"),
    _spec("elmos-repository-context-map", "rollback", "package_version artifact_version", "package_version artifact_version"),
    _spec("elmos-model-capability-discovery", "discover", "observation previous_snapshot task_id"),
    _spec("elmos-model-capability-discovery", "history", "provider model_id", "provider model_id"),
    _spec("elmos-model-capability-discovery", "rollback", "snapshot_id", "snapshot_id"),
    *_single("elmos-context-integrity-and-loss-detection", "verify", "after before task_id checkpoint_id"),
    _spec("elmos-folder-tree-input", "begin", "session_id expected_entry_count", "expected_entry_count"),
    _spec("elmos-folder-tree-input", "append", "session_id chunk_index entries", "session_id chunk_index entries"),
    _spec("elmos-folder-tree-input", "finalize", "session_id", "session_id"),
    _spec("elmos-folder-tree-input", "status", "session_id", "session_id"),
    _spec("elmos-folder-tree-input", "page", "package_version limit cursor", "package_version"),
    _spec("elmos-resumable-multi-file-folder-upload", "negotiate", "session_id path byte_count content_digest part_size", "session_id path byte_count content_digest"),
    _spec("elmos-resumable-multi-file-folder-upload", "confirm_part", "session_id path part_number byte_count part_digest data_base64", "session_id path part_number byte_count part_digest data_base64"),
    _spec("elmos-resumable-multi-file-folder-upload", "status", "session_id path", "session_id"),
    _spec("elmos-project-package-manifest", "finalize", "session_id", "session_id"),
    _spec("elmos-project-package-manifest", "page", "package_version limit cursor", "package_version"),
    _spec("elmos-project-package-manifest", "diff", "old_version new_version", "old_version new_version"),
    *(_spec("elmos-secure-zip-tar-extraction", operation, "archive_bytes_b64 format output_name password_handle archive_parent") for operation in ("extract", "publish", "expand_nested")),
    *_single("elmos-archive-bomb-and-path-traversal-defense", "inspect", "entries"),
    *(_spec(skill, operation, fields, required) for skill in (
        "elmos-project-root-language-framework-detection",
        "elmos-ignore-generated-vendored-file-classification",
        "elmos-repository-map-and-symbol-indexing",
    ) for operation, fields, required in (
        ("rebuild", "package_version source_input", "package_version source_input"),
        ("status", "package_version", "package_version"),
        ("rollback", "package_version artifact_version", "package_version artifact_version"),
    )),
    _spec("elmos-project-package-version-and-incremental-update", "diff", "old_version new_version", "old_version new_version"),
    _spec("elmos-project-package-preview-and-review-ui", "page", "package_version limit cursor", "package_version"),
    _spec("elmos-project-package-preview-and-review-ui", "override", "package_version path expected_override_version role model_read_allowed reason", "package_version path expected_override_version reason"),
    _spec("elmos-project-package-preview-and-review-ui", "undo", "package_version path expected_override_version audit_id reason", "package_version path expected_override_version audit_id reason"),
)

_registry = {(item.skill, item.operation): item for item in _SPECS}
if len(_registry) != len(_SPECS):
    raise RuntimeError("multimodal operation registry contains a duplicate pair")

OPERATION_REGISTRY: Mapping[tuple[str, str], OperationSpec] = MappingProxyType(_registry)
REGISTERED_SKILLS = frozenset(item.skill for item in _SPECS)
OPERATION_REGISTRY_DOCUMENT = {
    "schema_version": OPERATION_REGISTRY_SCHEMA_VERSION,
    "skill_count": len(REGISTERED_SKILLS),
    "operation_count": len(_SPECS),
    "operations": [item.document() for item in sorted(_SPECS, key=lambda value: (value.skill, value.operation))],
}
OPERATION_REGISTRY_DIGEST = canonical_digest(OPERATION_REGISTRY_DOCUMENT)


def require_operation(skill: str, operation: str, payload: Mapping[str, Any]) -> OperationSpec:
    """Validate one public pair and its exact top-level input field set."""

    spec = OPERATION_REGISTRY.get((skill, operation))
    if spec is None:
        raise ValidationError("REQUIRES_ADAPTER")
    actual = frozenset(payload)
    if actual - spec.input_fields or spec.required_input_fields - actual:
        raise ValidationError("OPERATION_INPUT_FIELDS_INVALID")
    if skill == "elmos-multimodal-evaluation-framework" and operation == "evaluate":
        _validate_evaluation_input(payload)
    if skill == "elmos-resumable-multi-file-folder-upload" and operation == "confirm_part":
        _validate_confirmed_part(payload)
    if skill == "elmos-downstream-agent-integration":
        _validate_downstream_input(operation, payload)
    return spec


def _bounded_text(value: Any, field: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value.encode("utf-8")) > maximum:
        raise ValidationError("OPERATION_INPUT_SHAPE_INVALID", details={"field": field})
    return value


def _validate_evaluation_input(payload: Mapping[str, Any]) -> None:
    subject = payload.get("subject")
    evidence = payload.get("evidence")
    if not isinstance(subject, Mapping) or frozenset(subject) != _EVALUATION_SUBJECT_FIELDS:
        raise ValidationError("OPERATION_INPUT_SHAPE_INVALID", details={"field": "subject"})
    for field in ("subject_id", "subject_kind", "implementation_version"):
        _bounded_text(subject.get(field), f"subject.{field}")
    if subject["subject_kind"] not in {"parser", "provider", "model", "runtime", "configuration"}:
        raise ValidationError("OPERATION_INPUT_SHAPE_INVALID", details={"field": "subject.subject_kind"})
    for field in ("artifact_digest", "configuration_digest"):
        if not isinstance(subject.get(field), str) or _SHA256.fullmatch(subject[field]) is None:
            raise ValidationError("OPERATION_INPUT_SHAPE_INVALID", details={"field": f"subject.{field}"})
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 240:
        raise ValidationError("OPERATION_INPUT_SHAPE_INVALID", details={"field": "evidence"})
    seen: set[str] = set()
    for index, item in enumerate(evidence):
        if not isinstance(item, Mapping) or frozenset(item) != _EVALUATION_EVIDENCE_FIELDS:
            raise ValidationError("OPERATION_INPUT_SHAPE_INVALID", details={"field": f"evidence[{index}]"})
        case_id = _bounded_text(item.get("case_id"), f"evidence[{index}].case_id", 128)
        _bounded_text(item.get("media_type"), f"evidence[{index}].media_type", 256)
        encoded = item.get("content_base64")
        if case_id in seen or not isinstance(encoded, str) or not encoded or len(encoded) > 16 * 1024 * 1024:
            raise ValidationError("OPERATION_INPUT_SHAPE_INVALID", details={"field": f"evidence[{index}]"})
        try:
            base64.b64decode(encoded.encode("ascii"), validate=True)
        except (UnicodeEncodeError, binascii.Error, ValueError) as error:
            raise ValidationError("OPERATION_INPUT_SHAPE_INVALID", details={"field": f"evidence[{index}].content_base64"}) from error
        seen.add(case_id)


def _validate_confirmed_part(payload: Mapping[str, Any]) -> None:
    encoded = payload.get("data_base64")
    byte_count = payload.get("byte_count")
    part_number = payload.get("part_number")
    part_digest = payload.get("part_digest")
    if (
        not isinstance(encoded, str)
        or not encoded
        or len(encoded) > 16 * 1024 * 1024
        or not isinstance(byte_count, int)
        or isinstance(byte_count, bool)
        or byte_count < 0
        or not isinstance(part_number, int)
        or isinstance(part_number, bool)
        or part_number < 1
        or not isinstance(part_digest, str)
        or _SHA256.fullmatch(part_digest) is None
    ):
        raise ValidationError("OPERATION_INPUT_SHAPE_INVALID", details={"field": "data_base64"})
    try:
        decoded = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as error:
        raise ValidationError("OPERATION_INPUT_SHAPE_INVALID", details={"field": "data_base64"}) from error
    actual_digest = "sha256:" + hashlib.sha256(decoded).hexdigest()
    if len(decoded) != byte_count or actual_digest != part_digest:
        raise ValidationError("OPERATION_INPUT_SHAPE_INVALID", details={"field": "part_digest"})


def _validate_downstream_input(operation: str, payload: Mapping[str, Any]) -> None:
    id_fields = {
        "build_context": ("task_id", "subject_id"),
        "get_context": ("context_id",),
        "get_grant": ("context_id", "grant_id"),
        "revoke_grant": ("context_id", "grant_id"),
        "link_result": ("context_id", "grant_id", "result_receipt_id"),
        "list_result_links": ("context_id",),
    }[operation]
    if any(not isinstance(payload.get(field), str) or _RESOURCE_ID.fullmatch(payload[field]) is None for field in id_fields):
        raise ValidationError("OPERATION_INPUT_SHAPE_INVALID")
    if operation == "build_context":
        package_version = payload.get("package_version")
        if not isinstance(package_version, int) or isinstance(package_version, bool) or package_version < 1:
            raise ValidationError("OPERATION_INPUT_SHAPE_INVALID", details={"field": "package_version"})
        for field, required in (("source_receipt_ids", True), ("tool_receipt_ids", False)):
            values = payload.get(field, [])
            if (
                not isinstance(values, list)
                or (required and not values)
                or len(values) > 256
                or any(not isinstance(value, str) or _RESOURCE_ID.fullmatch(value) is None for value in values)
                or len(values) != len(set(values))
            ):
                raise ValidationError("OPERATION_INPUT_SHAPE_INVALID", details={"field": field})
    if operation == "revoke_grant":
        _bounded_text(payload.get("reason"), "reason", 512)


def require_operation_pair(skill: str, operation: str) -> OperationSpec:
    spec = OPERATION_REGISTRY.get((skill, operation))
    if spec is None:
        raise ValidationError("REQUIRES_ADAPTER")
    return spec


__all__ = [
    "OPERATION_REGISTRY", "OPERATION_REGISTRY_DIGEST",
    "OPERATION_REGISTRY_DOCUMENT", "OPERATION_REGISTRY_SCHEMA_VERSION",
    "REGISTERED_SKILLS", "OperationSpec", "require_operation", "require_operation_pair",
]
