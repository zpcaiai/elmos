"""Exact, allowlisted runtime for the 50 multimodal intake Skills.

The package manifest's Skill dependencies describe collaboration contracts and
contain strongly connected components.  This runtime never recursively runs
those dependencies.  It exposes an independent acyclic phase plan and exactly
one explicit callable per canonical Skill.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
from collections import deque
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

from .canonical import (
    MAX_SAFE_JSON_INTEGER,
    require_actor_id,
    require_idempotency_key,
    require_resource_id,
)
from .errors import IntakeError
from .content import (
    build_source_provenance,
    detect_version_conflicts,
    evaluate_prompt_injection,
    extract_requirements,
    fuse_assets,
    normalize_content_ir,
)
from .context import (
    account_multimodal_tokens,
    calculate_context_budget,
    check_codex_capacity_parity,
    checkpoint_and_recover,
    compact_context,
    discover_model_capabilities,
    monitor_context_pressure,
    pack_context,
    rehydrate_context,
    verify_context_integrity,
)
from .governance import route_provider
from .observability import build_multimodal_observability, estimate_processing_cost_eta
from .projects import (
    build_folder_manifest,
    build_package_review_view,
    build_project_manifest,
    build_repository_context_map,
    classify_project_entries,
    detect_project_profile,
    index_repository_symbols,
    inspect_archive_safety,
    plan_incremental_update,
    resume_folder_upload,
)


class SkillRuntimeError(ValueError):
    """Raised before dispatch when a request or Skill identity is invalid."""


class HandlerContractError(SkillRuntimeError):
    """Raised when trusted handler or bridge output violates its protocol."""


class SkillHandler(Protocol):
    def __call__(self, request: Mapping[str, Any], /) -> dict[str, Any]: ...


@dataclass(frozen=True)
class RuntimeContext(Mapping[str, Any]):
    tenant_id: str
    project_id: str
    actor_id: str
    request_id: str
    trace_id: str
    idempotency_key: str | None
    policy: Mapping[str, Any]
    capabilities: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        if key not in {
            "tenant_id", "project_id", "actor_id", "request_id", "trace_id",
            "idempotency_key", "policy", "capabilities",
        }:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(
            (
                "tenant_id", "project_id", "actor_id", "request_id", "trace_id",
                "idempotency_key", "policy", "capabilities",
            )
        )

    def __len__(self) -> int:
        return 8


class SkillBridge(Protocol):
    def handle(
        self,
        skill_name: str,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class HandlerBinding:
    ordinal: int
    skill: str
    handler_id: str
    phase: str
    handler: SkillHandler


_RESULT_STATES = frozenset({"SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED", "NOT_APPLICABLE", "NOT_RUN_EXTERNAL"})
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 250_000
_MAX_JSON_BYTES = 32 * 1024 * 1024
_REQUEST_KEYS = frozenset(
    {
        "schema_version",
        "request_id",
        "tenant_id",
        "project_id",
        "actor_id",
        "inputs",
        "idempotency_key",
        "trace_id",
        "policy",
        "capabilities",
    }
)
_BRIDGE_SKILLS = frozenset(
    {
        "elmos-multimodal-input-orchestrator",
        "elmos-secure-resumable-upload",
        "elmos-file-type-detection-and-validation",
        "elmos-malware-quarantine-and-sandbox",
        "elmos-audio-asr-and-diarization",
        "elmos-image-ocr-and-preprocessing",
        "elmos-visual-ui-understanding",
        "elmos-diagram-and-architecture-understanding",
        "elmos-pdf-layout-table-parser",
        "elmos-word-document-parser",
        "elmos-markdown-text-log-parser",
        "elmos-unified-multimodal-content-ir",
        "elmos-source-anchor-and-provenance",
        "elmos-durable-processing-and-recovery",
        "elmos-human-review-and-correction",
        "elmos-storage-index-and-retrieval",
        "elmos-project-memory-and-retrieval",
        "elmos-secure-zip-tar-extraction",
        "elmos-multimodal-input-workbench-ui",
        "elmos-ingestion-api-and-sdk",
        "elmos-data-retention-and-governance",
        "elmos-multimodal-evaluation-framework",
        "elmos-multimodal-requirement-extraction",
        "elmos-multi-asset-content-fusion",
        "elmos-document-version-and-conflict-detection",
        "elmos-processing-cost-and-eta-estimation",
        "elmos-multimodal-observability",
        "elmos-downstream-agent-integration",
        "elmos-codex-context-capacity-parity",
        "elmos-context-budget-manager",
        "elmos-multimodal-token-accounting",
        "elmos-long-context-packing-and-ranking",
        "elmos-context-pressure-monitor",
        "elmos-structured-context-compaction",
        "elmos-context-checkpoint-and-recovery",
        "elmos-context-rehydration",
        "elmos-model-capability-discovery",
        "elmos-context-integrity-and-loss-detection",
        "elmos-repository-context-map",
        "elmos-folder-tree-input",
        "elmos-resumable-multi-file-folder-upload",
        "elmos-project-package-manifest",
        "elmos-project-root-language-framework-detection",
        "elmos-ignore-generated-vendored-file-classification",
        "elmos-repository-map-and-symbol-indexing",
        "elmos-project-package-version-and-incremental-update",
        "elmos-project-package-preview-and-review-ui",
    }
)
_BRIDGES: dict[str, SkillBridge] = {}
_SCOPED_BRIDGES: ContextVar[Mapping[str, SkillBridge] | None] = ContextVar(
    "elmos_multimodal_intake_scoped_bridges",
    default=None,
)
_BRIDGE_LOCK = threading.RLock()


PHASE_DAG: Mapping[str, tuple[str, ...]] = {
    "secure-intake": ("normalization",),
    "normalization": ("content", "project-package"),
    "content": ("governance", "indexing"),
    "project-package": ("indexing",),
    "governance": ("context",),
    "indexing": ("context",),
    "context": ("review",),
    "review": ("delivery",),
    "delivery": ("evaluation",),
    "evaluation": (),
}


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SkillRuntimeError("request must contain finite canonical JSON values") from exc


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _strict_json(
    value: Any,
    field: str,
    *,
    error_type: type[SkillRuntimeError],
) -> Any:
    """Copy exact JSON types while enforcing bounded depth, nodes, keys, and bytes."""

    remaining = [_MAX_JSON_NODES]

    def visit(item: Any, depth: int) -> Any:
        remaining[0] -= 1
        if remaining[0] < 0:
            raise error_type(f"{field} exceeds the JSON node limit")
        if depth > _MAX_JSON_DEPTH:
            raise error_type(f"{field} exceeds the JSON depth limit")
        if isinstance(item, str):
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise error_type(f"{field} contains invalid Unicode") from exc
            return item
        if item is None or isinstance(item, bool):
            return item
        if isinstance(item, int):
            if abs(item) > MAX_SAFE_JSON_INTEGER:
                raise error_type(f"{field} contains an unsafe JSON integer")
            return item
        if isinstance(item, float):
            if (
                not math.isfinite(item)
                or item.is_integer() and abs(item) > MAX_SAFE_JSON_INTEGER
            ):
                raise error_type(f"{field} contains a non-interoperable JSON number")
            return item
        if isinstance(item, list):
            return [visit(child, depth + 1) for child in item]
        if isinstance(item, Mapping):
            copied: dict[str, Any] = {}
            for key, child in item.items():
                try:
                    encoded_key = key.encode("utf-8", errors="strict") if isinstance(key, str) else b""
                except UnicodeEncodeError as exc:
                    raise error_type(f"{field} contains invalid Unicode") from exc
                if not isinstance(key, str) or not key or len(encoded_key) > 256:
                    raise error_type(f"{field} contains an invalid object key")
                copied[key] = visit(child, depth + 1)
            return copied
        raise error_type(f"{field} contains unsupported JSON type: {type(item).__name__}")

    copied = visit(value, 0)
    try:
        encoded = _canonical(copied).encode("utf-8")
    except SkillRuntimeError as exc:
        raise error_type(str(exc)) from exc
    if len(encoded) > _MAX_JSON_BYTES:
        raise error_type(f"{field} exceeds the JSON byte limit")
    return copied


def _required_text(value: Any, field: str, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        raise SkillRuntimeError(f"{field} must be non-blank and at most {maximum} characters")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise SkillRuntimeError(f"{field} contains invalid Unicode") from exc
    if len(encoded) > maximum:
        raise SkillRuntimeError(f"{field} exceeds {maximum} UTF-8 bytes")
    return value


def _idempotency_key(value: Any) -> str:
    key = _required_text(value, "idempotency_key", 200)
    encoded = key.encode("utf-8")
    if not 8 <= len(encoded) <= 200 or any(byte < 32 or byte == 127 for byte in encoded):
        raise SkillRuntimeError(
            "idempotency_key must be printable and between 8 and 200 UTF-8 bytes"
        )
    return key


def validate_runtime_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Reject ambiguous envelopes before any handler or bridge is invoked."""

    if not isinstance(request, Mapping):
        raise SkillRuntimeError("request must be an object")
    unknown = set(request) - _REQUEST_KEYS
    if unknown:
        raise SkillRuntimeError(f"request contains unsupported fields: {sorted(unknown)}")
    if request.get("schema_version") != "1.0":
        raise SkillRuntimeError("schema_version must equal 1.0")
    inputs = request.get("inputs")
    if not isinstance(inputs, Mapping):
        raise SkillRuntimeError("inputs must be an object")
    policy = request.get("policy", {})
    capabilities = request.get("capabilities", {})
    if not isinstance(policy, Mapping) or not isinstance(capabilities, Mapping):
        raise SkillRuntimeError("policy and capabilities must be objects")
    normalized = dict(request)
    normalized["request_id"] = _required_text(request.get("request_id"), "request_id")
    raw_tenant_id = request.get("tenant_id")
    raw_project_id = request.get("project_id")
    if not isinstance(raw_tenant_id, str) or not isinstance(raw_project_id, str):
        raise SkillRuntimeError("tenant_id and project_id must be exact strings")
    normalized["tenant_id"] = require_resource_id(raw_tenant_id, "tenant_id")
    normalized["project_id"] = require_resource_id(raw_project_id, "project_id")
    if normalized["tenant_id"] != raw_tenant_id or normalized["project_id"] != raw_project_id:
        raise SkillRuntimeError("tenant_id and project_id must not require normalization")
    actor = request.get("actor_id")
    if actor is not None:
        if not isinstance(actor, str):
            raise SkillRuntimeError("actor_id must be an exact string")
        normalized["actor_id"] = require_actor_id(actor)
        if normalized["actor_id"] != actor:
            raise SkillRuntimeError("actor_id must not require normalization")
    key = request.get("idempotency_key")
    if key is not None:
        if not isinstance(key, str):
            raise SkillRuntimeError("idempotency_key must be an exact string")
        normalized["idempotency_key"] = require_idempotency_key(key)
        if normalized["idempotency_key"] != key:
            raise SkillRuntimeError("idempotency_key must not require normalization")
    trace = request.get("trace_id")
    normalized["trace_id"] = _required_text(trace, "trace_id", 256) if trace is not None else "trace_" + _digest({"request_id": normalized["request_id"], "tenant_id": normalized["tenant_id"]})[7:31]
    if normalized.get("idempotency_key") is not None:
        normalized["idempotency_key"] = _idempotency_key(normalized["idempotency_key"])
    normalized["inputs"] = _strict_json(
        inputs,
        "inputs",
        error_type=SkillRuntimeError,
    )
    normalized["policy"] = _strict_json(policy, "policy", error_type=SkillRuntimeError)
    normalized["capabilities"] = _strict_json(
        capabilities,
        "capabilities",
        error_type=SkillRuntimeError,
    )
    return normalized


def register_skill_bridge(skill: str, bridge: SkillBridge) -> None:
    """Bind one exact Skill to a bridge; the same bridge may own many exact keys."""

    if skill not in _BRIDGE_SKILLS:
        raise SkillRuntimeError(f"Skill does not permit a runtime bridge: {skill}")
    if not callable(getattr(bridge, "handle", None)):
        raise SkillRuntimeError("bridge must expose callable handle(skill_name, ctx, payload)")
    with _BRIDGE_LOCK:
        _BRIDGES[skill] = bridge


def unregister_skill_bridge(skill: str, bridge: SkillBridge | None = None) -> None:
    with _BRIDGE_LOCK:
        if bridge is None or _BRIDGES.get(skill) is bridge:
            _BRIDGES.pop(skill, None)


def _active_bridges() -> Mapping[str, SkillBridge]:
    scoped = _SCOPED_BRIDGES.get()
    if scoped is not None:
        return scoped
    with _BRIDGE_LOCK:
        return dict(_BRIDGES)


class SkillDispatcher:
    """Instance-scoped bridge composition over the immutable Skill registry."""

    def __init__(self) -> None:
        self._bridges: dict[str, SkillBridge] = {}

    def register_bridge(self, skill: str, bridge: SkillBridge) -> None:
        if skill not in _BRIDGE_SKILLS:
            raise SkillRuntimeError(f"Skill does not permit a runtime bridge: {skill}")
        if not callable(getattr(bridge, "handle", None)):
            raise SkillRuntimeError("bridge must expose callable handle(skill_name, ctx, payload)")
        self._bridges[skill] = bridge

    def dispatch(self, skill: str, request: Mapping[str, Any]) -> dict[str, Any]:
        token = _SCOPED_BRIDGES.set(dict(self._bridges))
        try:
            return dispatch_skill(skill, request)
        finally:
            _SCOPED_BRIDGES.reset(token)


def _normalize_operation(
    binding: HandlerBinding,
    request: Mapping[str, Any],
    operation: Mapping[str, Any],
    *,
    implementation_state: str = "CODE_IMPLEMENTED_LOCAL",
    http_status: int = 200,
) -> dict[str, Any]:
    state_aliases = {"SUCCESS": "SUCCEEDED", "READY": "SUCCEEDED", "ERROR": "FAILED"}
    raw_state = operation.get("state", "SUCCEEDED")
    if not isinstance(raw_state, str):
        raise HandlerContractError(f"handler {binding.skill} returned a non-string state")
    state = state_aliases.get(raw_state.upper(), raw_state.upper())
    if state not in _RESULT_STATES:
        raise HandlerContractError(f"handler {binding.skill} returned invalid state: {state}")
    outputs = operation.get("outputs", {})
    metrics = operation.get("metrics", {})
    if not isinstance(outputs, Mapping) or not isinstance(metrics, Mapping):
        raise HandlerContractError(f"handler {binding.skill} outputs and metrics must be objects")
    safe_outputs = _strict_json(outputs, "handler outputs", error_type=HandlerContractError)
    safe_metrics = _strict_json(metrics, "handler metrics", error_type=HandlerContractError)
    code = operation.get("code", "LOCAL_OPERATION_COMPLETED")
    if not isinstance(code, str) or not code or len(code.encode("utf-8")) > 256:
        raise HandlerContractError(f"handler {binding.skill} returned an invalid code")
    default_retryable = "UNAVAILABLE" in code or "TIMEOUT" in code
    retryable = operation.get("retryable", default_retryable)
    if not isinstance(retryable, bool):
        raise HandlerContractError(f"handler {binding.skill} returned a non-boolean retryable flag")
    if not isinstance(http_status, int) or isinstance(http_status, bool) or not 100 <= http_status <= 599:
        raise HandlerContractError("handler result has an invalid HTTP status")
    trusted_metrics = dict(safe_metrics)
    trusted_metrics.pop("http_status", None)
    if http_status != 200:
        trusted_metrics["http_status"] = http_status
    return {
        "schema_version": "1.0",
        "skill": binding.skill,
        "handler_id": binding.handler_id,
        "request_id": request["request_id"],
        "trace_id": request["trace_id"],
        "phase": binding.phase,
        "state": state,
        "code": code,
        "retryable": retryable,
        "outputs": dict(safe_outputs),
        "metrics": trusted_metrics,
        "implementation_state": implementation_state,
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


def _binding(skill: str) -> HandlerBinding:
    binding = SKILL_REGISTRY.get(skill)
    if binding is None:
        raise SkillRuntimeError(f"unknown multimodal intake Skill: {skill}")
    return binding


def _run_domain(
    skill: str,
    operation: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = validate_runtime_request(request)
    binding = _binding(skill)
    http_status = 200
    try:
        result = operation(normalized)
    except IntakeError as exc:
        http_status = int(exc.http_status)
        result = {
            "state": "FAILED" if http_status >= 500 else "BLOCKED",
            "code": exc.code,
            "outputs": {"error_type": type(exc).__name__},
            "metrics": {},
            "retryable": exc.retryable,
        }
    except (KeyError, TypeError, ValueError) as exc:
        http_status = 422
        result = {
            "state": "BLOCKED",
            "code": "DOMAIN_INPUT_REJECTED",
            "outputs": {"error_type": type(exc).__name__},
            "metrics": {},
            "retryable": False,
        }
    except Exception as exc:
        http_status = 500
        result = {
            "state": "FAILED",
            "code": "DOMAIN_EXECUTION_FAILED",
            "outputs": {"error_type": type(exc).__name__},
            "metrics": {},
            "retryable": False,
        }
    return _normalize_operation(binding, normalized, result, http_status=http_status)


def _run_bridge(skill: str, request: Mapping[str, Any]) -> dict[str, Any]:
    normalized = validate_runtime_request(request)
    binding = _binding(skill)
    actor_id = normalized.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id:
        return _normalize_operation(
            binding,
            normalized,
            {"state": "BLOCKED", "code": "ACTOR_ID_REQUIRED", "outputs": {"bridge_invoked": False}},
            implementation_state="BRIDGE_REQUIRED",
            http_status=422,
        )
    bridge = _active_bridges().get(skill)
    if bridge is None:
        return _normalize_operation(
            binding,
            normalized,
            {"state": "BLOCKED", "code": "BRIDGE_UNAVAILABLE", "outputs": {"bridge_invoked": False}},
            implementation_state="BRIDGE_REQUIRED",
            http_status=503,
        )
    context = RuntimeContext(
        tenant_id=normalized["tenant_id"],
        project_id=normalized["project_id"],
        actor_id=actor_id,
        request_id=normalized["request_id"],
        trace_id=normalized["trace_id"],
        idempotency_key=normalized.get("idempotency_key"),
        policy=normalized["policy"],
        capabilities=normalized["capabilities"],
    )
    http_status = 200
    try:
        result = bridge.handle(skill, context, normalized["inputs"])
    except IntakeError as exc:
        http_status = int(exc.http_status)
        result = {
            "state": "FAILED" if http_status >= 500 else "BLOCKED",
            "code": str(getattr(exc, "code", "BRIDGE_INPUT_REJECTED")),
            "outputs": {"error_type": type(exc).__name__},
            "metrics": {},
            "retryable": exc.retryable,
        }
    except (KeyError, TypeError, ValueError) as exc:
        http_status = 422
        result = {
            "state": "BLOCKED",
            "code": "BRIDGE_INPUT_REJECTED",
            "outputs": {"error_type": type(exc).__name__},
            "metrics": {},
            "retryable": False,
        }
    except Exception as exc:  # external boundary: never leak provider/tool details
        http_status = 500
        result = {
            "state": "FAILED",
            "code": "BRIDGE_EXECUTION_FAILED",
            "outputs": {"error_type": type(exc).__name__},
            "metrics": {},
            "retryable": False,
        }
    if not isinstance(result, Mapping):
        raise HandlerContractError(f"bridge for {skill} returned a non-object")
    required_keys = {"state", "code", "outputs", "metrics", "retryable"}
    actual_keys = set(result)
    if actual_keys != required_keys:
        missing = sorted(required_keys - actual_keys)
        unexpected = sorted(actual_keys - required_keys)
        raise HandlerContractError(
            f"bridge for {skill} returned an invalid envelope "
            f"(missing={missing}, unexpected={unexpected})"
        )
    return _normalize_operation(binding, normalized, result, http_status=http_status)


def _run_domain_or_bridge(
    skill: str,
    operation: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Prefer production composition while retaining direct pure-handler use."""

    if _active_bridges().get(skill) is not None:
        return _run_bridge(skill, request)
    return _run_domain(skill, operation, request)


# Explicit wrappers are intentional.  Do not generate them and do not replace
# them with a default/prefix dispatcher: registry identity is part of the gate.
def execute_multimodal_input_orchestrator(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-multimodal-input-orchestrator", request)


def execute_secure_resumable_upload(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-secure-resumable-upload", request)


def execute_file_type_detection_and_validation(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-file-type-detection-and-validation", request)


def execute_malware_quarantine_and_sandbox(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-malware-quarantine-and-sandbox", request)


def execute_audio_asr_and_diarization(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-audio-asr-and-diarization", request)


def execute_image_ocr_and_preprocessing(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-image-ocr-and-preprocessing", request)


def execute_visual_ui_understanding(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-visual-ui-understanding", request)


def execute_diagram_and_architecture_understanding(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-diagram-and-architecture-understanding", request)


def execute_pdf_layout_table_parser(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-pdf-layout-table-parser", request)


def execute_word_document_parser(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-word-document-parser", request)


def execute_markdown_text_log_parser(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-markdown-text-log-parser", request)


def execute_unified_multimodal_content_ir(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge(
        "elmos-unified-multimodal-content-ir",
        normalize_content_ir,
        request,
    )


def execute_source_anchor_and_provenance(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge(
        "elmos-source-anchor-and-provenance",
        build_source_provenance,
        request,
    )


def execute_multimodal_requirement_extraction(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge(
        "elmos-multimodal-requirement-extraction",
        extract_requirements,
        request,
    )


def execute_multi_asset_content_fusion(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge(
        "elmos-multi-asset-content-fusion",
        fuse_assets,
        request,
    )


def execute_document_version_and_conflict_detection(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge(
        "elmos-document-version-and-conflict-detection",
        detect_version_conflicts,
        request,
    )


def execute_human_review_and_correction(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-human-review-and-correction", request)


def execute_prompt_injection_defense(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain("elmos-prompt-injection-defense", evaluate_prompt_injection, request)


def execute_provider_routing_and_fallback(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain("elmos-provider-routing-and-fallback", route_provider, request)


def execute_storage_index_and_retrieval(request: Mapping[str, Any]) -> dict[str, Any]:
    # Persistent retrieval is a side-effecting/runtime-scoped capability.  The
    # pure planning helper remains directly unit-testable, but registry dispatch
    # must never silently downgrade to an ephemeral result when its bridge is
    # absent.
    return _run_bridge("elmos-storage-index-and-retrieval", request)


def execute_durable_processing_and_recovery(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-durable-processing-and-recovery", request)


def execute_processing_cost_and_eta_estimation(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-processing-cost-and-eta-estimation", estimate_processing_cost_eta, request)


def execute_multimodal_observability(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-multimodal-observability", build_multimodal_observability, request)


def execute_multimodal_evaluation_framework(request: Mapping[str, Any]) -> dict[str, Any]:
    # Dataset authorization, raw evidence bytes, evaluator execution, replay,
    # and independent verification require the durable runtime-owned bridge.
    return _run_bridge("elmos-multimodal-evaluation-framework", request)


def execute_multimodal_input_workbench_ui(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-multimodal-input-workbench-ui", request)


def execute_ingestion_api_and_sdk(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-ingestion-api-and-sdk", request)


def execute_data_retention_and_governance(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-data-retention-and-governance", request)


def execute_downstream_agent_integration(request: Mapping[str, Any]) -> dict[str, Any]:
    # Context grants and result links are durable authority-bearing state.  A
    # missing production bridge must fail closed instead of returning the old
    # ephemeral planner result.
    return _run_bridge("elmos-downstream-agent-integration", request)


def execute_codex_context_capacity_parity(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-codex-context-capacity-parity", check_codex_capacity_parity, request)


def execute_context_budget_manager(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-context-budget-manager", calculate_context_budget, request)


def execute_multimodal_token_accounting(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-multimodal-token-accounting", account_multimodal_tokens, request)


def execute_long_context_packing_and_ranking(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-long-context-packing-and-ranking", pack_context, request)


def execute_context_pressure_monitor(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-context-pressure-monitor", monitor_context_pressure, request)


def execute_structured_context_compaction(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-structured-context-compaction", compact_context, request)


def execute_context_checkpoint_and_recovery(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-context-checkpoint-and-recovery", checkpoint_and_recover, request)


def execute_context_rehydration(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-context-rehydration", rehydrate_context, request)


def execute_project_memory_and_retrieval(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-project-memory-and-retrieval", request)


def execute_repository_context_map(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-repository-context-map", build_repository_context_map, request)


def execute_model_capability_discovery(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-model-capability-discovery", discover_model_capabilities, request)


def execute_context_integrity_and_loss_detection(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-context-integrity-and-loss-detection", verify_context_integrity, request)


def execute_folder_tree_input(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-folder-tree-input", build_folder_manifest, request)


def execute_resumable_multi_file_folder_upload(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-resumable-multi-file-folder-upload", resume_folder_upload, request)


def execute_project_package_manifest(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-project-package-manifest", build_project_manifest, request)


def execute_secure_zip_tar_extraction(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_bridge("elmos-secure-zip-tar-extraction", request)


def execute_archive_bomb_and_path_traversal_defense(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain("elmos-archive-bomb-and-path-traversal-defense", inspect_archive_safety, request)


def execute_project_root_language_framework_detection(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-project-root-language-framework-detection", detect_project_profile, request)


def execute_ignore_generated_vendored_file_classification(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-ignore-generated-vendored-file-classification", classify_project_entries, request)


def execute_repository_map_and_symbol_indexing(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-repository-map-and-symbol-indexing", index_repository_symbols, request)


def execute_project_package_version_and_incremental_update(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-project-package-version-and-incremental-update", plan_incremental_update, request)


def execute_project_package_preview_and_review_ui(request: Mapping[str, Any]) -> dict[str, Any]:
    return _run_domain_or_bridge("elmos-project-package-preview-and-review-ui", build_package_review_view, request)


def _entry(ordinal: int, skill: str, phase: str, handler: SkillHandler) -> HandlerBinding:
    return HandlerBinding(ordinal, skill, getattr(handler, "__name__"), phase, handler)


SKILL_REGISTRY: dict[str, HandlerBinding] = {
    "elmos-multimodal-input-orchestrator": _entry(1, "elmos-multimodal-input-orchestrator", "secure-intake", execute_multimodal_input_orchestrator),
    "elmos-secure-resumable-upload": _entry(2, "elmos-secure-resumable-upload", "secure-intake", execute_secure_resumable_upload),
    "elmos-file-type-detection-and-validation": _entry(3, "elmos-file-type-detection-and-validation", "secure-intake", execute_file_type_detection_and_validation),
    "elmos-malware-quarantine-and-sandbox": _entry(4, "elmos-malware-quarantine-and-sandbox", "secure-intake", execute_malware_quarantine_and_sandbox),
    "elmos-audio-asr-and-diarization": _entry(5, "elmos-audio-asr-and-diarization", "secure-intake", execute_audio_asr_and_diarization),
    "elmos-image-ocr-and-preprocessing": _entry(6, "elmos-image-ocr-and-preprocessing", "secure-intake", execute_image_ocr_and_preprocessing),
    "elmos-visual-ui-understanding": _entry(7, "elmos-visual-ui-understanding", "content", execute_visual_ui_understanding),
    "elmos-diagram-and-architecture-understanding": _entry(8, "elmos-diagram-and-architecture-understanding", "content", execute_diagram_and_architecture_understanding),
    "elmos-pdf-layout-table-parser": _entry(9, "elmos-pdf-layout-table-parser", "secure-intake", execute_pdf_layout_table_parser),
    "elmos-word-document-parser": _entry(10, "elmos-word-document-parser", "secure-intake", execute_word_document_parser),
    "elmos-markdown-text-log-parser": _entry(11, "elmos-markdown-text-log-parser", "secure-intake", execute_markdown_text_log_parser),
    "elmos-unified-multimodal-content-ir": _entry(12, "elmos-unified-multimodal-content-ir", "normalization", execute_unified_multimodal_content_ir),
    "elmos-source-anchor-and-provenance": _entry(13, "elmos-source-anchor-and-provenance", "normalization", execute_source_anchor_and_provenance),
    "elmos-multimodal-requirement-extraction": _entry(14, "elmos-multimodal-requirement-extraction", "content", execute_multimodal_requirement_extraction),
    "elmos-multi-asset-content-fusion": _entry(15, "elmos-multi-asset-content-fusion", "content", execute_multi_asset_content_fusion),
    "elmos-document-version-and-conflict-detection": _entry(16, "elmos-document-version-and-conflict-detection", "content", execute_document_version_and_conflict_detection),
    "elmos-human-review-and-correction": _entry(17, "elmos-human-review-and-correction", "review", execute_human_review_and_correction),
    "elmos-prompt-injection-defense": _entry(18, "elmos-prompt-injection-defense", "governance", execute_prompt_injection_defense),
    "elmos-provider-routing-and-fallback": _entry(19, "elmos-provider-routing-and-fallback", "governance", execute_provider_routing_and_fallback),
    "elmos-storage-index-and-retrieval": _entry(20, "elmos-storage-index-and-retrieval", "indexing", execute_storage_index_and_retrieval),
    "elmos-durable-processing-and-recovery": _entry(21, "elmos-durable-processing-and-recovery", "governance", execute_durable_processing_and_recovery),
    "elmos-processing-cost-and-eta-estimation": _entry(22, "elmos-processing-cost-and-eta-estimation", "evaluation", execute_processing_cost_and_eta_estimation),
    "elmos-multimodal-observability": _entry(23, "elmos-multimodal-observability", "evaluation", execute_multimodal_observability),
    "elmos-multimodal-evaluation-framework": _entry(24, "elmos-multimodal-evaluation-framework", "evaluation", execute_multimodal_evaluation_framework),
    "elmos-multimodal-input-workbench-ui": _entry(25, "elmos-multimodal-input-workbench-ui", "review", execute_multimodal_input_workbench_ui),
    "elmos-ingestion-api-and-sdk": _entry(26, "elmos-ingestion-api-and-sdk", "delivery", execute_ingestion_api_and_sdk),
    "elmos-data-retention-and-governance": _entry(27, "elmos-data-retention-and-governance", "governance", execute_data_retention_and_governance),
    "elmos-downstream-agent-integration": _entry(28, "elmos-downstream-agent-integration", "delivery", execute_downstream_agent_integration),
    "elmos-codex-context-capacity-parity": _entry(29, "elmos-codex-context-capacity-parity", "context", execute_codex_context_capacity_parity),
    "elmos-context-budget-manager": _entry(30, "elmos-context-budget-manager", "context", execute_context_budget_manager),
    "elmos-multimodal-token-accounting": _entry(31, "elmos-multimodal-token-accounting", "context", execute_multimodal_token_accounting),
    "elmos-long-context-packing-and-ranking": _entry(32, "elmos-long-context-packing-and-ranking", "context", execute_long_context_packing_and_ranking),
    "elmos-context-pressure-monitor": _entry(33, "elmos-context-pressure-monitor", "context", execute_context_pressure_monitor),
    "elmos-structured-context-compaction": _entry(34, "elmos-structured-context-compaction", "context", execute_structured_context_compaction),
    "elmos-context-checkpoint-and-recovery": _entry(35, "elmos-context-checkpoint-and-recovery", "context", execute_context_checkpoint_and_recovery),
    "elmos-context-rehydration": _entry(36, "elmos-context-rehydration", "context", execute_context_rehydration),
    "elmos-project-memory-and-retrieval": _entry(37, "elmos-project-memory-and-retrieval", "context", execute_project_memory_and_retrieval),
    "elmos-repository-context-map": _entry(38, "elmos-repository-context-map", "indexing", execute_repository_context_map),
    "elmos-model-capability-discovery": _entry(39, "elmos-model-capability-discovery", "context", execute_model_capability_discovery),
    "elmos-context-integrity-and-loss-detection": _entry(40, "elmos-context-integrity-and-loss-detection", "context", execute_context_integrity_and_loss_detection),
    "elmos-folder-tree-input": _entry(41, "elmos-folder-tree-input", "project-package", execute_folder_tree_input),
    "elmos-resumable-multi-file-folder-upload": _entry(42, "elmos-resumable-multi-file-folder-upload", "project-package", execute_resumable_multi_file_folder_upload),
    "elmos-project-package-manifest": _entry(43, "elmos-project-package-manifest", "project-package", execute_project_package_manifest),
    "elmos-secure-zip-tar-extraction": _entry(44, "elmos-secure-zip-tar-extraction", "project-package", execute_secure_zip_tar_extraction),
    "elmos-archive-bomb-and-path-traversal-defense": _entry(45, "elmos-archive-bomb-and-path-traversal-defense", "secure-intake", execute_archive_bomb_and_path_traversal_defense),
    "elmos-project-root-language-framework-detection": _entry(46, "elmos-project-root-language-framework-detection", "project-package", execute_project_root_language_framework_detection),
    "elmos-ignore-generated-vendored-file-classification": _entry(47, "elmos-ignore-generated-vendored-file-classification", "project-package", execute_ignore_generated_vendored_file_classification),
    "elmos-repository-map-and-symbol-indexing": _entry(48, "elmos-repository-map-and-symbol-indexing", "indexing", execute_repository_map_and_symbol_indexing),
    "elmos-project-package-version-and-incremental-update": _entry(49, "elmos-project-package-version-and-incremental-update", "project-package", execute_project_package_version_and_incremental_update),
    "elmos-project-package-preview-and-review-ui": _entry(50, "elmos-project-package-preview-and-review-ui", "review", execute_project_package_preview_and_review_ui),
}


def phase_execution_plan() -> tuple[str, ...]:
    """Return a deterministic topological phase plan, independent of Skill SCCs."""

    indegree = {phase: 0 for phase in PHASE_DAG}
    for targets in PHASE_DAG.values():
        for target in targets:
            if target not in indegree:
                raise SkillRuntimeError(f"phase DAG references unknown phase: {target}")
            indegree[target] += 1
    ready = deque(sorted(phase for phase, degree in indegree.items() if degree == 0))
    ordered: list[str] = []
    while ready:
        phase = ready.popleft()
        ordered.append(phase)
        for target in sorted(PHASE_DAG[phase]):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    if len(ordered) != len(PHASE_DAG):
        raise SkillRuntimeError("execution phase graph contains a cycle")
    return tuple(ordered)


def validate_skill_registry() -> None:
    if len(SKILL_REGISTRY) != 50:
        raise SkillRuntimeError("SKILL_REGISTRY must contain exactly 50 entries")
    bindings = list(SKILL_REGISTRY.values())
    if sorted(item.ordinal for item in bindings) != list(range(1, 51)):
        raise SkillRuntimeError("Skill ordinals must be exactly 1 through 50")
    if len({item.handler_id for item in bindings}) != 50:
        raise SkillRuntimeError("handler IDs must be unique")
    if len({id(item.handler) for item in bindings}) != 50:
        raise SkillRuntimeError("every Skill must own a unique callable")
    if any(item.skill != key or item.phase not in PHASE_DAG for key, item in SKILL_REGISTRY.items()):
        raise SkillRuntimeError("registry identity or phase binding is invalid")
    phase_execution_plan()


def dispatch_skill(skill: str, request: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one exact Skill. Unknown names never reach a fallback handler."""

    binding = _binding(skill)
    try:
        return binding.handler(request)
    except HandlerContractError:
        request_id = str(request.get("request_id", "invalid-request")) if isinstance(request, Mapping) else "invalid-request"
        trace_id = str(request.get("trace_id", "unavailable")) if isinstance(request, Mapping) else "unavailable"
        return {
            "schema_version": "1.0",
            "skill": binding.skill,
            "handler_id": binding.handler_id,
            "request_id": request_id,
            "trace_id": trace_id,
            "phase": binding.phase,
            "state": "FAILED",
            "code": "HANDLER_OUTPUT_INVALID",
            "retryable": False,
            "outputs": {},
            "metrics": {"http_status": 500},
            "implementation_state": "CODE_IMPLEMENTED_LOCAL",
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
    except IntakeError as exc:
        request_id = str(request.get("request_id", "invalid-request")) if isinstance(request, Mapping) else "invalid-request"
        trace_id = str(request.get("trace_id", "unavailable")) if isinstance(request, Mapping) else "unavailable"
        http_status = int(exc.http_status)
        return {
            "schema_version": "1.0",
            "skill": binding.skill,
            "handler_id": binding.handler_id,
            "request_id": request_id,
            "trace_id": trace_id,
            "phase": binding.phase,
            "state": "FAILED" if http_status >= 500 else "BLOCKED",
            "code": exc.code,
            "retryable": exc.retryable,
            "outputs": {"error_type": type(exc).__name__},
            "metrics": {"http_status": http_status},
            "implementation_state": "CODE_IMPLEMENTED_LOCAL",
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
    except SkillRuntimeError as exc:
        request_id = str(request.get("request_id", "invalid-request")) if isinstance(request, Mapping) else "invalid-request"
        trace_id = str(request.get("trace_id", "unavailable")) if isinstance(request, Mapping) else "unavailable"
        return {
            "schema_version": "1.0",
            "skill": binding.skill,
            "handler_id": binding.handler_id,
            "request_id": request_id,
            "trace_id": trace_id,
            "phase": binding.phase,
            "state": "BLOCKED",
            "code": "REQUEST_CONTRACT_REJECTED",
            "retryable": False,
            "outputs": {"error_type": type(exc).__name__},
            "metrics": {"http_status": 422},
            "implementation_state": "CODE_IMPLEMENTED_LOCAL",
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }


validate_skill_registry()
