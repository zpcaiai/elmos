"""Bounded CLI and composition root for the multimodal intake runtime."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import stat
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from threading import Event, Thread
from typing import Any, cast
from uuid import uuid4

from . import MultimodalIntakeRuntime, TenantContext, create_runtime
from .api import MultimodalIntakeApi
from .archive_publication import publish_archive_to_cas
from .canonical import canonical_digest, canonical_json, normalize_sha256, require_resource_id
from .contracts import (
    EXECUTION_CONTRACT_VERSION,
    MAX_RESPONSE_BYTES,
    SkillExecutionRequest,
    execution_result,
    validate_execution_result_document,
)
from .content_projection import (
    CONTENT_PROJECTION_SKILLS,
    ContentProjectionBridge,
    ContentProjectionStore,
)
from .errors import AuthorizationError, ConflictError, IntakeError, NotFoundError, ValidationError
from .durable_evaluation import EvaluationSkillBridge, EvaluationStore
from .downstream_agent import DownstreamAgentBridge
from .human_review import HumanReviewCorrectionBridge
from .governance import GovernanceDeletionBridge
from .context_lifecycle import CONTEXT_LIFECYCLE_SKILLS, ContextLifecycleBridge
from .persistent_knowledge import PersistentKnowledgeStore
from .project_package_lifecycle import ProjectPackageLifecycleBridge
from .providers import execution_component_identity
from .skill_runtime import (
    SKILL_REGISTRY,
    RuntimeContext,
    SkillDispatcher,
)
from .surface_bridge import SurfaceSkillBridge
from .telemetry_lifecycle import TELEMETRY_SKILLS, TelemetryLifecycleBridge

MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_JSON_PART_BYTES = 1024 * 1024
MAX_TRUSTED_CONTEXT_BYTES = 1024 * 1024
TRUSTED_CONTEXT_FILENAME = "trusted-context-v1.json"
EXECUTION_LEASE_SECONDS = 15 * 60
EXECUTION_HEARTBEAT_SECONDS = 60
EXECUTION_COMPLETION_ATTEMPTS = 3
# IntakeStore's bounded SQLite busy timeout is 30 seconds.  The join remains
# bounded but exceeds that limit so a heartbeat cannot outlive runtime.close().
EXECUTION_HEARTBEAT_JOIN_SECONDS = 35
CORE_SKILLS = tuple(
    name
    for name, binding in sorted(SKILL_REGISTRY.items(), key=lambda item: item[1].ordinal)
    if binding.ordinal <= 11 or binding.ordinal == 21
)
RuntimeFactory = Callable[[Path, Path], MultimodalIntakeRuntime]


_WRITE_OPERATION_PAIRS = frozenset(
    {
        # Durable content projections and ledgers.
        (skill, operation)
        for skill, operations in {
            "elmos-multimodal-requirement-extraction": {"extract"},
            "elmos-multi-asset-content-fusion": {"fuse"},
            "elmos-document-version-and-conflict-detection": {"detect_conflicts"},
            "elmos-storage-index-and-retrieval": {"upsert", "delete", "repair"},
            "elmos-project-memory-and-retrieval": {"write", "delete", "repair"},
            "elmos-durable-processing-and-recovery": {
                "transition",
                "process_durable_transition",
                "mark_outbox_published",
            },
            "elmos-processing-cost-and-eta-estimation": {"estimate"},
            "elmos-multimodal-observability": {"observe"},
            "elmos-multimodal-evaluation-framework": {"evaluate", "verify"},
            "elmos-data-retention-and-governance": {"delete"},
            "elmos-downstream-agent-integration": {
                "build_context",
                "revoke_grant",
                "link_result",
            },
            "elmos-model-capability-discovery": {"discover", "rollback"},
            "elmos-codex-context-capacity-parity": {"check"},
            "elmos-context-budget-manager": {"calculate"},
            "elmos-multimodal-token-accounting": {"account"},
            "elmos-long-context-packing-and-ranking": {"pack"},
            "elmos-context-pressure-monitor": {"monitor"},
            "elmos-structured-context-compaction": {"compact"},
            "elmos-context-checkpoint-and-recovery": {"create", "restore", "rollback"},
            "elmos-context-rehydration": {"rehydrate"},
            "elmos-context-integrity-and-loss-detection": {"verify"},
            "elmos-folder-tree-input": {"begin", "append", "finalize"},
            "elmos-resumable-multi-file-folder-upload": {"negotiate", "confirm_part"},
            "elmos-project-package-manifest": {"finalize"},
            "elmos-secure-zip-tar-extraction": {"extract", "publish", "expand_nested"},
            "elmos-repository-context-map": {"rebuild", "rollback"},
            "elmos-project-root-language-framework-detection": {"rebuild", "rollback"},
            "elmos-ignore-generated-vendored-file-classification": {"rebuild", "rollback"},
            "elmos-repository-map-and-symbol-indexing": {"rebuild", "rollback"},
            "elmos-project-package-preview-and-review-ui": {"override", "undo"},
        }.items()
        for operation in operations
    }
)


def _operation_permission(
    runtime: MultimodalIntakeRuntime,
    request: SkillExecutionRequest,
) -> str:
    """Resolve one exact public operation to its least-privileged ACL."""

    operation = request.operation.strip().lower().replace("-", "_")
    if (
        request.skill == "elmos-multimodal-input-orchestrator"
        and operation == "bootstrap_project"
    ):
        return runtime.store.ADMIN
    if request.skill == "elmos-human-review-and-correction":
        return runtime.store.REVIEW
    if runtime._is_mutating_operation(request.skill, operation):
        return runtime.store.WRITE
    if (request.skill, operation) in _WRITE_OPERATION_PAIRS:
        return runtime.store.WRITE
    return runtime.store.READ


def runtime_execution_environment_identity(
    runtime: MultimodalIntakeRuntime,
    *,
    runtime_factory: RuntimeFactory,
) -> dict[str, Any]:
    """Return the canonical runtime/provider identity without paths or secrets."""

    external_tools = runtime.providers.execution_environment_identity()
    if not isinstance(external_tools, Mapping):
        raise ValidationError("MULTIMODAL_EXECUTION_ENVIRONMENT_INVALID")
    upload_policy = runtime.uploads.policy
    progress_store = getattr(runtime, "progress_deliveries", None)
    identity = {
        "schema_version": "elmos-multimodal-execution-environment-v1",
        "runtime": execution_component_identity(runtime, component_kind="multimodal-runtime"),
        "runtime_factory": execution_component_identity(
            runtime_factory,
            component_kind="runtime-factory",
        ),
        "metadata_store": execution_component_identity(
            runtime.store,
            component_kind="metadata-store",
        ),
        "content_store": execution_component_identity(
            runtime.cas,
            component_kind="content-store",
        ),
        "external_tools": dict(external_tools),
        "upload_policy": {
            "maximum_asset_bytes": upload_policy.maximum_asset_bytes,
            "default_part_size": upload_policy.default_part_size,
            "maximum_part_size": upload_policy.maximum_part_size,
            "maximum_parts": upload_policy.maximum_parts,
            "default_ttl_seconds": upload_policy.default_ttl_seconds,
            "maximum_ttl_seconds": upload_policy.maximum_ttl_seconds,
        },
        "archive_password_provider": execution_component_identity(
            runtime.archive_password_provider,
            component_kind="archive-password-provider",
        ),
        "progress_delivery_store": execution_component_identity(
            progress_store,
            component_kind="progress-delivery-store",
        ),
        "progress_webhook_transport": execution_component_identity(
            getattr(progress_store, "_transport", None),
            component_kind="progress-webhook-transport",
        ),
        "progress_webhook_signer": execution_component_identity(
            getattr(progress_store, "_signer", None),
            component_kind="progress-webhook-signer",
        ),
    }
    # Validation is deliberate: a host component cannot smuggle a path, secret,
    # non-I-JSON value, or unstable object into the outer receipt identity.
    canonical_json(identity)
    return identity


def runtime_execution_environment_digest(
    runtime: MultimodalIntakeRuntime,
    *,
    runtime_factory: RuntimeFactory,
) -> str:
    return canonical_digest(
        runtime_execution_environment_identity(
            runtime,
            runtime_factory=runtime_factory,
        )
    )


def _close_runtime_after_composition_failure(runtime: MultimodalIntakeRuntime) -> None:
    """Close exactly once while preserving the active composition exception."""

    try:
        runtime.close()
    except BaseException:
        # The composition exception is authoritative.  A cleanup failure must
        # never replace it and make the actual failed boundary undiscoverable.
        pass


def _runtime_root(value: str | Path) -> Path:
    root = Path(value).expanduser()
    if not root.is_absolute() or root == Path(root.anchor):
        raise ValidationError("MULTIMODAL_DATA_ROOT_INVALID")
    existed = root.exists() or root.is_symlink()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise ValidationError("MULTIMODAL_DATA_ROOT_INVALID")
    if not existed:
        try:
            root.chmod(0o700)
        except OSError:
            pass
    metadata = root.stat()
    wrong_owner = hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
    if wrong_owner or metadata.st_mode & 0o077:
        raise ValidationError("MULTIMODAL_DATA_ROOT_PERMISSIONS_INVALID")
    return root


def _reject_non_finite_json(value: str) -> None:
    raise ValidationError("MULTIMODAL_JSON_NON_FINITE", f"Non-finite JSON number is forbidden: {value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key: {key}")
        value[key] = item
    return value


def _trusted_context(
    root: Path,
    context: TenantContext,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Load a host-owned exact-scope policy/capability binding, never request-supplied grants."""

    path = root / TRUSTED_CONTEXT_FILENAME
    if not path.exists() and not path.is_symlink():
        return {}, {}, "unbound-v1"
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ValidationError("TRUSTED_CONTEXT_FILE_INVALID") from error
    try:
        metadata = os.fstat(descriptor)
        wrong_owner = hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > MAX_TRUSTED_CONTEXT_BYTES
            or metadata.st_mode & 0o022
            or wrong_owner
        ):
            raise ValidationError("TRUSTED_CONTEXT_FILE_INVALID")
        raw = os.read(descriptor, MAX_TRUSTED_CONTEXT_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(raw) > MAX_TRUSTED_CONTEXT_BYTES or len(raw) != metadata.st_size:
        raise ValidationError("TRUSTED_CONTEXT_FILE_INVALID")
    try:
        document = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_non_finite_json,
            object_pairs_hook=_unique_json_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValidationError("TRUSTED_CONTEXT_FILE_INVALID") from error
    if not isinstance(document, Mapping) or set(document) != {"schema_version", "bindings"}:
        raise ValidationError("TRUSTED_CONTEXT_SCHEMA_INVALID")
    if document.get("schema_version") != "1.0":
        raise ValidationError("TRUSTED_CONTEXT_SCHEMA_INVALID")
    bindings = document.get("bindings")
    if not isinstance(bindings, Sequence) or isinstance(bindings, (str, bytes, bytearray)) or len(bindings) > 10_000:
        raise ValidationError("TRUSTED_CONTEXT_SCHEMA_INVALID")
    matched: tuple[dict[str, Any], dict[str, Any], str] | None = None
    seen: set[tuple[str, str, str]] = set()
    for raw_binding in bindings:
        if not isinstance(raw_binding, Mapping) or set(raw_binding) != {
            "tenant_id", "project_id", "actor_id", "context_epoch", "policy", "capabilities"
        }:
            raise ValidationError("TRUSTED_CONTEXT_SCHEMA_INVALID")
        raw_tenant_id = raw_binding.get("tenant_id")
        raw_project_id = raw_binding.get("project_id")
        raw_actor_id = raw_binding.get("actor_id")
        raw_context_epoch = raw_binding.get("context_epoch")
        if (
            not isinstance(raw_tenant_id, str)
            or not isinstance(raw_project_id, str)
            or not isinstance(raw_actor_id, str)
            or not isinstance(raw_context_epoch, str)
        ):
            raise ValidationError("TRUSTED_CONTEXT_SCHEMA_INVALID")
        binding_context = TenantContext(
            raw_tenant_id,
            raw_project_id,
            raw_actor_id,
        )
        if (
            binding_context.tenant_id != raw_tenant_id
            or binding_context.project_id != raw_project_id
            or binding_context.actor_id != raw_actor_id
        ):
            raise ValidationError("TRUSTED_CONTEXT_SCHEMA_INVALID")
        identity = (binding_context.tenant_id, binding_context.project_id, binding_context.actor_id)
        if identity in seen:
            raise ValidationError("TRUSTED_CONTEXT_DUPLICATE_BINDING")
        seen.add(identity)
        policy = raw_binding.get("policy")
        capabilities = raw_binding.get("capabilities")
        if not isinstance(policy, Mapping) or not isinstance(capabilities, Mapping):
            raise ValidationError("TRUSTED_CONTEXT_SCHEMA_INVALID")
        context_epoch = require_resource_id(
            raw_context_epoch,
            "context_epoch",
        )
        if context_epoch != raw_context_epoch:
            raise ValidationError("TRUSTED_CONTEXT_SCHEMA_INVALID")
        if binding_context == context:
            matched = dict(policy), dict(capabilities), context_epoch
    return matched or ({}, {}, "unbound-v1")


def _execution_receipt_digest(
    request: SkillExecutionRequest,
    *,
    policy: Mapping[str, Any],
    capabilities: Mapping[str, Any],
    context_epoch: str,
    execution_environment_digest: str,
) -> str:
    """Bind replay to code, host capabilities, and trusted authorization facts."""

    binding = SKILL_REGISTRY[request.skill]
    safe_environment_digest = normalize_sha256(execution_environment_digest)
    return canonical_digest(
        {
            "execution_contract": EXECUTION_CONTRACT_VERSION,
            "request_digest": request.request_digest,
            "handler_id": binding.handler_id,
            "handler_phase": binding.phase,
            "runtime_build_digest": _runtime_build_digest(),
            "execution_environment_digest": safe_environment_digest,
            "context_epoch": context_epoch,
            "policy_digest": canonical_digest(policy),
            "capabilities_digest": canonical_digest(capabilities),
        }
    )


def _dispatch_with_execution_heartbeat(
    runtime: MultimodalIntakeRuntime,
    request: SkillExecutionRequest,
    *,
    request_digest: str,
    owner_token: str,
    required_permission: str,
    dispatch: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Keep the outer fence live and make an invoked outcome non-retryable.

    A failure before ``dispatch`` is called is side-effect free and releases the
    claim.  Once dispatch starts, any handler or heartbeat uncertainty is
    converted into a terminal reconciliation result so a lost response can
    never cause the outer idempotency key to invoke the handler blindly again.
    """

    def renew() -> str:
        return runtime.store.renew_skill_execution(
            request.context,
            skill=request.skill,
            idempotency_key=request.idempotency_key,
            request_digest=request_digest,
            owner_token=owner_token,
            lease_seconds=EXECUTION_LEASE_SECONDS,
            required_permission=required_permission,
        )

    def release_before_dispatch() -> None:
        runtime.store.release_skill_execution(
            request.context,
            skill=request.skill,
            idempotency_key=request.idempotency_key,
            request_digest=request_digest,
            owner_token=owner_token,
            required_permission=required_permission,
        )

    def mark_dispatched() -> str:
        return runtime.store.mark_skill_execution_dispatched(
            request.context,
            skill=request.skill,
            idempotency_key=request.idempotency_key,
            request_digest=request_digest,
            owner_token=owner_token,
            required_permission=required_permission,
        )

    def reconciliation_result() -> dict[str, Any]:
        binding = SKILL_REGISTRY[request.skill]
        return {
            "schema_version": "1.0",
            "skill": request.skill,
            "handler_id": binding.handler_id,
            "request_id": request.request_digest,
            "trace_id": request.trace_id,
            "phase": binding.phase,
            "state": "BLOCKED",
            "code": "EXECUTION_OUTCOME_RECONCILIATION_REQUIRED",
            "retryable": False,
            "outputs": {
                "reconciliation": {
                    "state": "REQUIRED",
                    "automatic_retry_allowed": False,
                    "reason": "DISPATCH_OUTCOME_UNCONFIRMED",
                }
            },
            "metrics": {},
            "implementation_state": "CODE_IMPLEMENTED_LOCAL",
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }

    # Renew synchronously before dispatch so even short executions prove they
    # own a current lease and every external invocation starts with a full
    # bounded lease window.
    try:
        renew()
    except BaseException:
        try:
            release_before_dispatch()
        except BaseException:
            # Preserve the authoritative renewal failure.  A failed cleanup
            # leaves only a bounded, side-effect-free lease which can expire.
            pass
        raise
    stopped = Event()
    failures: list[Exception] = []

    def heartbeat() -> None:
        while not stopped.wait(EXECUTION_HEARTBEAT_SECONDS):
            try:
                renew()
            except Exception as error:  # ownership loss must fence completion
                failures.append(error)
                stopped.set()

    worker = Thread(
        target=heartbeat,
        name="multimodal-intake-execution-heartbeat",
        daemon=True,
    )
    try:
        worker.start()
    except BaseException:
        stopped.set()
        try:
            release_before_dispatch()
        except BaseException:
            pass
        raise
    try:
        # This commit is the last side-effect-free boundary.  A crash after it
        # must reconcile the prior attempt and can never reclaim by lease age.
        mark_dispatched()
    except BaseException:
        stopped.set()
        worker.join(timeout=EXECUTION_HEARTBEAT_JOIN_SECONDS)
        try:
            release_before_dispatch()
        except BaseException:
            # If the marker committed, release correctly fails closed.  If it
            # did not, expiry leaves a side-effect-free claim reclaimable.
            pass
        raise
    result: dict[str, Any] | None = None
    dispatch_failure = False
    try:
        result = dispatch()
    except Exception:
        # The bridge may already have called an external tool.  Do not expose
        # details and, crucially, do not release a claim that could be retried.
        dispatch_failure = True
    finally:
        stopped.set()
        worker.join(timeout=EXECUTION_HEARTBEAT_JOIN_SECONDS)
    if worker.is_alive() or failures or dispatch_failure or result is None:
        return reconciliation_result()
    return result


@lru_cache(maxsize=1)
def _runtime_build_digest() -> str:
    """Bind receipts to the exact checked-in Python implementation bytes."""

    package_root = Path(__file__).resolve().parent
    engine_root = package_root.parent.parent
    python_sources = tuple(package_root.glob("*.py"))
    migration_sources = tuple(engine_root.glob("migrations/*.sql"))
    if not python_sources or not migration_sources:
        raise ValidationError("MULTIMODAL_RUNTIME_BUILD_ID_UNAVAILABLE")
    sources = sorted(
        (*python_sources, *migration_sources),
        key=lambda path: path.relative_to(engine_root).as_posix(),
    )
    digest = hashlib.sha256()
    for source in sources:
        if source.is_symlink() or not source.is_file():
            raise ValidationError("MULTIMODAL_RUNTIME_BUILD_ID_UNAVAILABLE")
        name = source.relative_to(engine_root).as_posix().encode("utf-8")
        data = source.read_bytes()
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _result_state(value: Mapping[str, Any]) -> tuple[str, str]:
    candidates: list[Mapping[str, Any]] = [value]
    for key in ("job", "report", "provider_result", "detection"):
        nested = value.get(key)
        if isinstance(nested, Mapping):
            candidates.append(nested)
    raw_state = ""
    code = "LOCAL_OPERATION_COMPLETED"
    for candidate in candidates:
        for key in ("result_status", "status", "decision", "state"):
            item = candidate.get(key)
            if isinstance(item, str) and item:
                raw_state = item.upper()
                break
        for key in ("failure_code", "error_code", "code"):
            item = candidate.get(key)
            if isinstance(item, str) and item:
                code = item
                break
        if raw_state:
            break
    if raw_state in {"PASSED", "READY", "COMPLETED", "ALLOW", "ACCEPTED", "DUPLICATE_IDENTICAL"}:
        return "SUCCEEDED", code
    if raw_state in {"PARTIAL", "PARTIAL_READY", "NEEDS_REVIEW", "NOT_RUN", "UPLOADING", "PROCESSING"}:
        return "PARTIAL", code if code != "LOCAL_OPERATION_COMPLETED" else raw_state
    if raw_state in {"BLOCKED", "QUARANTINE", "QUARANTINED", "CANCELLED"}:
        return "BLOCKED", code if code != "LOCAL_OPERATION_COMPLETED" else raw_state
    if raw_state in {"FAILED", "ERROR"}:
        return "FAILED", code if code != "LOCAL_OPERATION_COMPLETED" else raw_state
    if raw_state:
        return "FAILED", "CORE_RESULT_STATE_UNMAPPED"
    return "SUCCEEDED", code


_WORKFLOW_SUMMARY_LIMIT = 100
_WORKFLOW_WARNING_LIMIT = 20


def _selected(value: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {field: value[field] for field in fields if field in value}


def _bounded_workflow_output(value: Mapping[str, Any]) -> dict[str, Any]:
    raw_assets = value.get("assets", [])
    assets = list(raw_assets) if isinstance(raw_assets, list) else []
    visible_assets = assets[:_WORKFLOW_SUMMARY_LIMIT]
    asset_summaries = [
        _selected(
            asset,
            (
                "asset_id", "session_id", "display_name", "detected_media_type", "kind",
                "byte_size", "sha256", "status", "security_decision", "version", "failure_code",
            ),
        )
        for asset in visible_assets
    ]
    raw_reports = value.get("reports", {})
    reports = raw_reports if isinstance(raw_reports, Mapping) else {}
    report_summaries: dict[str, Any] = {}
    for asset in asset_summaries:
        asset_id = asset.get("asset_id")
        if not isinstance(asset_id, str):
            continue
        report = reports.get(asset_id)
        if not isinstance(report, Mapping):
            continue
        blocks = report.get("blocks", [])
        block_values = blocks if isinstance(blocks, list) else []
        warnings = report.get("warnings", [])
        warning_values = warnings if isinstance(warnings, list) else []
        report_summaries[asset_id] = {
            **_selected(report, ("parser", "status", "error_code")),
            "block_count": len(block_values),
            "anchor_count": sum(
                len(block.get("anchors", []))
                for block in block_values
                if isinstance(block, Mapping) and isinstance(block.get("anchors", []), list)
            ),
            "warning_count": len(warning_values),
            "warnings": warning_values[:_WORKFLOW_WARNING_LIMIT],
            "warnings_truncated": len(warning_values) > _WORKFLOW_WARNING_LIMIT,
        }
    return {
        "job_id": value.get("job_id"),
        "session_id": value.get("session_id"),
        "job": _selected(
            value.get("job"),
            (
                "job_id", "session_id", "status", "stage", "attempt", "max_attempts",
                "result_status", "failure_code", "created_at", "updated_at",
            ),
        ),
        "session": _selected(
            value.get("session"),
            ("session_id", "requested_role", "status", "version", "created_at", "updated_at"),
        ),
        "asset_count": len(assets),
        "assets": asset_summaries,
        "assets_truncated": len(assets) > _WORKFLOW_SUMMARY_LIMIT,
        "report_count": len(reports),
        "reports": report_summaries,
        "reports_truncated": len(reports) > len(report_summaries),
        "summary_limit": _WORKFLOW_SUMMARY_LIMIT,
    }


class CoreSkillBridge:
    """Converts the stable registry bridge protocol into the durable core facade."""

    def __init__(self, runtime: MultimodalIntakeRuntime) -> None:
        self._runtime = runtime

    def handle(
        self,
        skill_name: str,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        trusted_payload = dict(payload)
        operation = str(trusted_payload.get("operation", "")).strip().lower().replace("-", "_")
        if skill_name == "elmos-secure-resumable-upload" and trusted_payload.get("operation") == "start":
            requested_part_size = trusted_payload.get("part_size", MAX_JSON_PART_BYTES)
            if (
                not isinstance(requested_part_size, int)
                or isinstance(requested_part_size, bool)
                or not 1 <= requested_part_size <= MAX_JSON_PART_BYTES
            ):
                raise ValidationError("JSON_UPLOAD_PART_SIZE_OUTSIDE_TRANSPORT")
            trusted_payload["part_size"] = requested_part_size
        if skill_name == "elmos-multimodal-input-orchestrator" and operation == "process_session":
            try:
                trusted_payload["expected_asset_generation_digest"] = normalize_sha256(
                    str(trusted_payload.get("expected_asset_generation_digest", ""))
                )
            except ValidationError as error:
                raise ValidationError("ASSET_GENERATION_DIGEST_REQUIRED") from error
        if ctx.idempotency_key is not None:
            trusted_payload["idempotency_key"] = ctx.idempotency_key
        trusted_payload["trace_id"] = ctx.trace_id
        output = self._runtime.handle(
            skill_name,
            {
                "tenant_id": ctx.tenant_id,
                "project_id": ctx.project_id,
                "actor_id": ctx.actor_id,
            },
            trusted_payload,
        )
        state, code = _result_state(output)
        if (
            skill_name == "elmos-multimodal-input-orchestrator"
            and operation in {"process_session", "resume_job", "cancel_job"}
        ):
            output = _bounded_workflow_output(output)
        return {
            "state": state,
            "code": code,
            "outputs": output,
            "metrics": {},
            "retryable": False,
        }


class _ArchiveExternalEffectTracker:
    _PROVIDER_FAILURE_CODES = frozenset(
        {
            "PROVIDER_COMMAND_FAILED",
            "PROVIDER_OUTPUT_ENCODING_INVALID",
            "PROVIDER_OUTPUT_JSON_INVALID",
            "PROVIDER_OUTPUT_LIMIT_EXCEEDED",
            "SANDBOX_EXECUTION_FAILED",
            "SANDBOX_RECEIPT_INVALID",
        }
    )

    def __init__(self) -> None:
        self.scanner_invoked = False
        self.password_provider_invoked = False
        self.cas_publish_invoked = False
        self.scanner_failed = False
        self.password_provider_failed = False
        self.cas_publish_failed = False

    def observe_provider_result(self, result: object) -> None:
        status = getattr(getattr(result, "status", None), "value", None)
        code = getattr(result, "error_code", None)
        receipt = getattr(result, "receipt", None)
        if status == "PASSED" or (isinstance(receipt, Mapping) and bool(receipt)):
            self.scanner_invoked = True
        if isinstance(code, str) and code in self._PROVIDER_FAILURE_CODES:
            self.scanner_invoked = True
            self.scanner_failed = True

    @property
    def effects_started(self) -> bool:
        return self.scanner_invoked or self.password_provider_invoked or self.cas_publish_invoked

    @property
    def reconciliation_required(self) -> bool:
        return self.scanner_failed or self.password_provider_failed or self.cas_publish_failed

    def public_summary(self) -> dict[str, bool]:
        return {
            "scanner_invoked": self.scanner_invoked,
            "password_provider_invoked": self.password_provider_invoked,
            "cas_publish_invoked": self.cas_publish_invoked,
        }


class _TrackedArchiveProvider:
    def __init__(self, delegate: object, tracker: _ArchiveExternalEffectTracker) -> None:
        self._delegate = delegate
        self._tracker = tracker

    def run(self, *args: Any, **kwargs: Any) -> Any:
        try:
            result = self._delegate.run(*args, **kwargs)  # type: ignore[attr-defined]
        except BaseException:
            self._tracker.scanner_invoked = True
            self._tracker.scanner_failed = True
            raise
        self._tracker.observe_provider_result(result)
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class _TrackedArchivePasswordProvider:
    def __init__(self, delegate: object, tracker: _ArchiveExternalEffectTracker) -> None:
        self._delegate = delegate
        self._tracker = tracker

    def resolve_archive_password(self, handle: str, **scope: Any) -> Any:
        self._tracker.password_provider_invoked = True
        try:
            return self._delegate.resolve_archive_password(handle, **scope)  # type: ignore[attr-defined]
        except BaseException:
            self._tracker.password_provider_failed = True
            raise


class _TrackedArchiveCas:
    def __init__(self, delegate: object, tracker: _ArchiveExternalEffectTracker) -> None:
        self._delegate = delegate
        self._tracker = tracker

    def publish_generation(self, *args: Any, **kwargs: Any) -> Any:
        self._tracker.cas_publish_invoked = True
        try:
            return self._delegate.publish_generation(*args, **kwargs)  # type: ignore[attr-defined]
        except BaseException:
            self._tracker.cas_publish_failed = True
            raise

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class KnowledgeArchiveSkillBridge:
    """Durable adapters for Skills 20, 37 and 44 over runtime-owned capabilities."""

    _RESERVED_INPUT_FIELDS = frozenset({"operation", "idempotency_key", "trace_id"})
    _ARCHIVE_RECEIPT_SKILL = "archive-publication-bridge.v1"
    _ARCHIVE_RECEIPT_LEASE_SECONDS = 24 * 60 * 60
    _MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
    _MAX_ARCHIVE_ENCODED_CHARS = ((_MAX_ARCHIVE_BYTES + 2) // 3) * 4

    def __init__(
        self,
        runtime: MultimodalIntakeRuntime,
        *,
        execution_environment_digest: str | None = None,
    ) -> None:
        self._runtime = runtime
        self._knowledge = PersistentKnowledgeStore(runtime.store)
        if execution_environment_digest is None:
            execution_environment_digest = runtime_execution_environment_digest(
                runtime,
                runtime_factory=create_runtime,
            )
        self._execution_environment_digest = normalize_sha256(execution_environment_digest)

    @staticmethod
    def _envelope(
        state: str,
        code: str,
        outputs: Mapping[str, Any],
        *,
        metrics: Mapping[str, Any] | None = None,
        retryable: bool = False,
    ) -> dict[str, Any]:
        return {
            "state": state,
            "code": code,
            "outputs": dict(outputs),
            "metrics": dict(metrics or {}),
            "retryable": retryable,
        }

    @classmethod
    def _expect_fields(
        cls,
        payload: Mapping[str, Any],
        allowed: frozenset[str],
    ) -> None:
        unexpected = set(payload) - allowed - cls._RESERVED_INPUT_FIELDS
        if unexpected:
            raise ValidationError(
                "PERSISTENT_SKILL_INPUT_FIELDS_INVALID",
                details={"unexpected_fields": sorted(unexpected)},
            )

    @staticmethod
    def _context(ctx: RuntimeContext) -> TenantContext:
        return TenantContext(ctx.tenant_id, ctx.project_id, ctx.actor_id)

    @staticmethod
    def _idempotency_key(ctx: RuntimeContext) -> str:
        if ctx.idempotency_key is None:
            raise ValidationError("PERSISTENT_IDEMPOTENCY_KEY_REQUIRED")
        return ctx.idempotency_key

    @staticmethod
    def _required_string(payload: Mapping[str, Any], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str):
            raise ValidationError(
                "PERSISTENT_SKILL_INPUT_TYPE_INVALID",
                details={"field": field, "expected": "string"},
            )
        return value

    @staticmethod
    def _required_mapping(
        payload: Mapping[str, Any],
        field: str,
    ) -> Mapping[str, Any]:
        value = payload.get(field)
        if not isinstance(value, Mapping):
            raise ValidationError(
                "PERSISTENT_SKILL_INPUT_TYPE_INVALID",
                details={"field": field, "expected": "object"},
            )
        return value

    @classmethod
    def _archive_content_identity(cls, payload: Mapping[str, Any]) -> tuple[str, int]:
        encoded = payload.get("archive_bytes_b64")
        if not isinstance(encoded, str):
            raise ValidationError("ARCHIVE_CONTENT_REQUIRED")
        if (
            not encoded
            or len(encoded) > cls._MAX_ARCHIVE_ENCODED_CHARS
            or len(encoded) % 4
        ):
            raise ValidationError("ARCHIVE_INPUT_SIZE_LIMIT")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, UnicodeEncodeError, ValueError) as error:
            raise ValidationError("ARCHIVE_INPUT_SIZE_LIMIT") from error
        if not decoded or len(decoded) > cls._MAX_ARCHIVE_BYTES:
            raise ValidationError("ARCHIVE_INPUT_SIZE_LIMIT")
        return hashlib.sha256(decoded).hexdigest(), len(decoded)

    def _archive_request_digest(
        self,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
        operation: str,
        *,
        archive_digest: str,
        archive_bytes: int,
    ) -> str:
        canonical_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"archive_bytes_b64", "trace_id", "idempotency_key", "operation"}
        }
        canonical_payload["operation"] = operation
        canonical_payload["archive"] = {
            "content_digest": f"sha256:{archive_digest}",
            "byte_count": archive_bytes,
        }
        return canonical_digest(
            {
                "schema_version": "elmos-archive-bridge-receipt-v1",
                "tenant_id": ctx.tenant_id,
                "project_id": ctx.project_id,
                "actor_id": ctx.actor_id,
                "job_id": ctx.request_id,
                "payload": canonical_payload,
                "policy_digest": f"sha256:{canonical_digest(ctx.policy)}",
                "capability_digest": f"sha256:{canonical_digest(ctx.capabilities)}",
                "execution_environment_digest": (
                    f"sha256:{self._execution_environment_digest}"
                ),
            }
        )

    def _complete_archive_receipt(
        self,
        context: TenantContext,
        *,
        idempotency_key: str,
        request_digest: str,
        owner_token: str,
        response: Mapping[str, Any],
    ) -> dict[str, Any]:
        _http_status, stored = self._runtime.store.complete_skill_execution(
            context,
            skill=self._ARCHIVE_RECEIPT_SKILL,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            owner_token=owner_token,
            http_status=200,
            response=response,
        )
        return stored

    def _release_archive_receipt(
        self,
        context: TenantContext,
        *,
        idempotency_key: str,
        request_digest: str,
        owner_token: str,
    ) -> None:
        try:
            self._runtime.store.release_skill_execution(
                context,
                skill=self._ARCHIVE_RECEIPT_SKILL,
                idempotency_key=idempotency_key,
                request_digest=request_digest,
                owner_token=owner_token,
            )
        except BaseException:
            # The original, side-effect-free failure remains authoritative.
            pass

    def _archive_reconciliation_envelope(
        self,
        tracker: _ArchiveExternalEffectTracker,
        *,
        archive_digest: str,
        archive_bytes: int,
        request_digest: str,
    ) -> dict[str, Any]:
        return self._envelope(
            "BLOCKED",
            "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED",
            {
                "publication_state": "RECONCILIATION_REQUIRED",
                "reconciliation_state": "REQUIRED",
                "external_effects": tracker.public_summary(),
                "archive_digest": f"sha256:{archive_digest}",
                "archive_bytes": archive_bytes,
                "readable_generation_state": (
                    "UNKNOWN" if tracker.cas_publish_invoked else "NOT_RUN"
                ),
                "host_paths_returned": False,
                "raw_content_returned": False,
            },
            metrics={
                "archive_bridge_request_digest": f"sha256:{request_digest}",
                "execution_environment_digest": (
                    f"sha256:{self._execution_environment_digest}"
                ),
            },
            retryable=False,
        )

    @staticmethod
    def _archive_result_requires_reconciliation(
        result: Mapping[str, Any],
        tracker: _ArchiveExternalEffectTracker,
    ) -> bool:
        code = result.get("code")
        return (
            tracker.reconciliation_required
            or (tracker.effects_started and code == "ARCHIVE_EXTRACTION_BLOCKED")
            or (
                tracker.password_provider_invoked
                and code
                in {
                    "ARCHIVE_PASSWORD_LEASE_INVALID",
                    "ARCHIVE_PASSWORD_SECRET_CHANNEL_REQUIRED",
                    "ARCHIVE_PASSWORD_SECRET_RESOLUTION_FAILED",
                }
            )
        )

    def _storage(
        self,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
        operation: str,
    ) -> Mapping[str, Any]:
        context = self._context(ctx)
        if operation == "upsert":
            self._expect_fields(
                payload,
                frozenset(
                    {
                        "branch",
                        "package_version",
                        "document_id",
                        "text",
                        "content_digest",
                        "source_digest",
                        "source_anchor",
                        "required_permissions",
                        "expected_version",
                        "confidence",
                    }
                ),
            )
            output = self._knowledge.upsert_document(
                context,
                branch=payload.get("branch", "main"),
                package_version=self._required_string(payload, "package_version"),
                document_id=self._required_string(payload, "document_id"),
                text=self._required_string(payload, "text"),
                content_digest=self._required_string(payload, "content_digest"),
                source_digest=self._required_string(payload, "source_digest"),
                source_anchor=self._required_mapping(payload, "source_anchor"),
                required_permissions=payload.get("required_permissions", []),
                idempotency_key=self._idempotency_key(ctx),
                expected_version=payload.get("expected_version"),
                confidence=payload.get("confidence", 1.0),
            )
            code = (
                "KNOWLEDGE_DOCUMENT_PERSISTED"
                if output.get("changed") is True
                else "KNOWLEDGE_DOCUMENT_UNCHANGED"
            )
            return self._envelope(
                "SUCCEEDED",
                code,
                output,
                metrics={"persisted_document_count": 1},
            )
        if operation == "query":
            self._expect_fields(
                payload,
                frozenset({"branch", "package_version", "query", "limit"}),
            )
            output = self._knowledge.query_documents(
                context,
                branch=payload.get("branch", "main"),
                package_version=self._required_string(payload, "package_version"),
                query=self._required_string(payload, "query"),
                limit=payload.get("limit", 20),
            )
            return self._envelope(
                "PARTIAL",
                "LOCAL_LEXICAL_RETRIEVAL_COMPLETED",
                output,
                metrics={
                    "candidate_count": output.get("candidate_count", 0),
                    "result_count": len(output.get("results", [])),
                    "permission_filtered_count": output.get(
                        "permission_filtered_count",
                        0,
                    ),
                },
            )
        if operation == "delete":
            self._expect_fields(
                payload,
                frozenset({"branch", "package_version", "source_digest"}),
            )
            output = self._knowledge.delete_by_source_digest(
                context,
                branch=payload.get("branch", "main"),
                package_version=self._required_string(payload, "package_version"),
                source_digest=self._required_string(payload, "source_digest"),
                idempotency_key=self._idempotency_key(ctx),
            )
            pending = output.get("deletion_propagation_state") == "PENDING"
            return self._envelope(
                "PARTIAL" if pending else "SUCCEEDED",
                (
                    "KNOWLEDGE_DELETION_PROPAGATION_PENDING"
                    if pending
                    else "KNOWLEDGE_SOURCE_ABSENT"
                ),
                output,
            )
        if operation == "repair":
            self._expect_fields(
                payload,
                frozenset({"branch", "package_version"}),
            )
            output = self._knowledge.rebuild_lexical_index(
                context,
                branch=payload.get("branch", "main"),
                package_version=self._required_string(payload, "package_version"),
                target="content-index",
                idempotency_key=self._idempotency_key(ctx),
            )
            return self._envelope(
                "PARTIAL",
                "LOCAL_LEXICAL_INDEX_REBUILT",
                output,
                metrics={
                    "record_count": output.get("record_count", 0),
                    "term_count": output.get("term_count", 0),
                },
            )
        if operation == "rebuild_status":
            self._expect_fields(
                payload,
                frozenset({"branch", "package_version", "status", "limit"}),
            )
            jobs = self._knowledge.list_rebuild_jobs(
                context,
                branch=payload.get("branch", "main"),
                package_version=self._required_string(payload, "package_version"),
                status=payload.get("status"),
                limit=payload.get("limit", 100),
            )
            return self._envelope(
                "SUCCEEDED",
                "KNOWLEDGE_REBUILD_JOBS_LOADED",
                {"jobs": jobs},
                metrics={"job_count": len(jobs)},
            )
        raise ValidationError(
            "STORAGE_INDEX_OPERATION_UNSUPPORTED",
            details={"operation": operation},
        )

    def _memory(
        self,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
        operation: str,
    ) -> Mapping[str, Any]:
        context = self._context(ctx)
        if operation == "write":
            self._expect_fields(
                payload,
                frozenset(
                    {
                        "branch",
                        "package_version",
                        "memory_key",
                        "value",
                        "source_digest",
                        "source_anchor",
                        "required_permissions",
                        "expected_version",
                        "memory_kind",
                        "semantic_state",
                        "confidence",
                    }
                ),
            )
            output = self._knowledge.write_memory(
                context,
                branch=payload.get("branch", "main"),
                package_version=self._required_string(payload, "package_version"),
                memory_key=self._required_string(payload, "memory_key"),
                value=payload.get("value"),
                source_digest=self._required_string(payload, "source_digest"),
                source_anchor=self._required_mapping(payload, "source_anchor"),
                required_permissions=payload.get("required_permissions", []),
                idempotency_key=self._idempotency_key(ctx),
                expected_version=payload.get("expected_version"),
                memory_kind=payload.get("memory_kind", "FACT"),
                semantic_state=payload.get("semantic_state", "ACTIVE"),
                confidence=payload.get("confidence", 1.0),
            )
            code = (
                "PROJECT_MEMORY_PERSISTED"
                if output.get("changed") is True
                else "PROJECT_MEMORY_UNCHANGED"
            )
            return self._envelope("SUCCEEDED", code, output)
        if operation == "query":
            self._expect_fields(
                payload,
                frozenset({"branch", "package_version", "query", "limit"}),
            )
            output = self._knowledge.query_memory(
                context,
                branch=payload.get("branch", "main"),
                package_version=self._required_string(payload, "package_version"),
                query=self._required_string(payload, "query"),
                limit=payload.get("limit", 20),
            )
            return self._envelope(
                "PARTIAL",
                "PROJECT_MEMORY_LOCAL_LEXICAL_RETRIEVAL_COMPLETED",
                output,
                metrics={
                    "candidate_count": output.get("candidate_count", 0),
                    "result_count": len(output.get("results", [])),
                    "permission_filtered_count": output.get(
                        "permission_filtered_count",
                        0,
                    ),
                },
            )
        if operation == "delete":
            return self._storage(ctx, payload, operation)
        if operation == "repair":
            self._expect_fields(
                payload,
                frozenset({"branch", "package_version"}),
            )
            output = self._knowledge.rebuild_lexical_index(
                context,
                branch=payload.get("branch", "main"),
                package_version=self._required_string(payload, "package_version"),
                target="project-memory",
                idempotency_key=self._idempotency_key(ctx),
            )
            return self._envelope(
                "PARTIAL",
                "PROJECT_MEMORY_LOCAL_LEXICAL_INDEX_REBUILT",
                output,
                metrics={
                    "record_count": output.get("record_count", 0),
                    "term_count": output.get("term_count", 0),
                },
            )
        if operation == "rebuild_status":
            return self._storage(ctx, payload, operation)
        raise ValidationError(
            "PROJECT_MEMORY_OPERATION_UNSUPPORTED",
            details={"operation": operation},
        )

    def _archive(
        self,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
        operation: str,
    ) -> Mapping[str, Any]:
        if operation not in {"extract", "publish", "expand_nested"}:
            raise ValidationError(
                "ARCHIVE_PUBLICATION_OPERATION_UNSUPPORTED",
                details={"operation": operation},
            )
        self._expect_fields(
            payload,
            frozenset(
                {
                    "archive_bytes_b64",
                    "format",
                    "output_name",
                    "password_handle",
                    "archive_parent",
                }
            ),
        )
        if operation == "expand_nested" and "archive_parent" not in payload:
            raise ValidationError("ARCHIVE_PARENT_LINEAGE_REQUIRED")
        idempotency_key = self._idempotency_key(ctx)
        archive_digest, archive_bytes = self._archive_content_identity(payload)
        context = self._context(ctx)
        self._runtime.store.require(context, self._runtime.store.WRITE)
        request_digest = self._archive_request_digest(
            ctx,
            payload,
            operation,
            archive_digest=archive_digest,
            archive_bytes=archive_bytes,
        )
        owner_token = f"archive-{uuid4()}"
        claim_state, replay = self._runtime.store.claim_skill_execution(
            context,
            skill=self._ARCHIVE_RECEIPT_SKILL,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            owner_token=owner_token,
            lease_seconds=self._ARCHIVE_RECEIPT_LEASE_SECONDS,
        )
        if claim_state == "REPLAY":
            if replay is None or replay[0] != 200 or not isinstance(replay[1], Mapping):
                raise ValidationError("ARCHIVE_PUBLICATION_RECEIPT_INVALID")
            return dict(replay[1])
        if claim_state == "IN_PROGRESS":
            raise ConflictError("ARCHIVE_PUBLICATION_IN_PROGRESS", retryable=True)
        if claim_state != "CLAIMED" or replay is not None:
            raise ValidationError("ARCHIVE_PUBLICATION_CLAIM_INVALID")

        tracker = _ArchiveExternalEffectTracker()
        providers = _TrackedArchiveProvider(self._runtime.providers, tracker)
        cas = _TrackedArchiveCas(self._runtime.cas, tracker)
        password_provider = self._runtime.archive_password_provider
        tracked_password_provider = (
            _TrackedArchivePasswordProvider(password_provider, tracker)
            if password_provider is not None
            else None
        )
        try:
            result = publish_archive_to_cas(
                {
                    "inputs": dict(payload),
                    "policy": dict(ctx.policy),
                    "capabilities": dict(ctx.capabilities),
                },
                providers=cast(Any, providers),
                cas=cast(Any, cas),
                tenant_id=ctx.tenant_id,
                project_id=ctx.project_id,
                job_id=ctx.request_id,
                password_provider=cast(Any, tracked_password_provider),
                store=self._runtime.store,
            )
            if not isinstance(result, Mapping):
                raise ValidationError("ARCHIVE_PUBLICATION_RESULT_INVALID")
            if self._archive_result_requires_reconciliation(result, tracker):
                response = self._archive_reconciliation_envelope(
                    tracker,
                    archive_digest=archive_digest,
                    archive_bytes=archive_bytes,
                    request_digest=request_digest,
                )
            else:
                outputs = result.get("outputs", {})
                metrics = result.get("metrics", {})
                if not isinstance(outputs, Mapping) or not isinstance(metrics, Mapping):
                    raise ValidationError("ARCHIVE_PUBLICATION_RESULT_INVALID")
                receipt_metrics = dict(metrics)
                receipt_metrics.update(
                    {
                        "archive_bridge_request_digest": f"sha256:{request_digest}",
                        "execution_environment_digest": (
                            f"sha256:{self._execution_environment_digest}"
                        ),
                    }
                )
                response = self._envelope(
                    str(result.get("state", "FAILED")),
                    str(result.get("code", "ARCHIVE_PUBLICATION_FAILED")),
                    outputs,
                    metrics=receipt_metrics,
                    retryable=result.get("retryable") is True,
                )
        except BaseException as error:
            if tracker.effects_started:
                reconciliation = self._archive_reconciliation_envelope(
                    tracker,
                    archive_digest=archive_digest,
                    archive_bytes=archive_bytes,
                    request_digest=request_digest,
                )
                try:
                    stored = self._complete_archive_receipt(
                        context,
                        idempotency_key=idempotency_key,
                        request_digest=request_digest,
                        owner_token=owner_token,
                        response=reconciliation,
                    )
                except BaseException:
                    raise error
                if isinstance(error, Exception):
                    return stored
                raise
            self._release_archive_receipt(
                context,
                idempotency_key=idempotency_key,
                request_digest=request_digest,
                owner_token=owner_token,
            )
            raise

        try:
            return self._complete_archive_receipt(
                context,
                idempotency_key=idempotency_key,
                request_digest=request_digest,
                owner_token=owner_token,
                response=response,
            )
        except BaseException as error:
            if tracker.effects_started:
                reconciliation = self._archive_reconciliation_envelope(
                    tracker,
                    archive_digest=archive_digest,
                    archive_bytes=archive_bytes,
                    request_digest=request_digest,
                )
                try:
                    stored = self._complete_archive_receipt(
                        context,
                        idempotency_key=idempotency_key,
                        request_digest=request_digest,
                        owner_token=owner_token,
                        response=reconciliation,
                    )
                except BaseException:
                    raise error
                if isinstance(error, Exception):
                    return stored
                raise
            self._release_archive_receipt(
                context,
                idempotency_key=idempotency_key,
                request_digest=request_digest,
                owner_token=owner_token,
            )
            raise

    def handle(
        self,
        skill_name: str,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        operation = str(payload.get("operation", "")).strip().lower().replace("-", "_")
        if skill_name == "elmos-storage-index-and-retrieval":
            return self._storage(ctx, payload, operation)
        if skill_name == "elmos-project-memory-and-retrieval":
            return self._memory(ctx, payload, operation)
        if skill_name == "elmos-secure-zip-tar-extraction":
            return self._archive(ctx, payload, operation)
        raise ValidationError("DURABLE_SKILL_BRIDGE_UNSUPPORTED")


def _catalog() -> list[dict[str, Any]]:
    return [
        {
            "ordinal": binding.ordinal,
            "skill": binding.skill,
            "handler_id": binding.handler_id,
            "phase": binding.phase,
            "implementation_state": "CODE_IMPLEMENTED_LOCAL",
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
        for binding in sorted(SKILL_REGISTRY.values(), key=lambda item: item.ordinal)
    ]


def _compose(
    data_root: str | Path,
    *,
    bound_context: TenantContext | None = None,
    runtime_factory: RuntimeFactory | None = None,
) -> tuple[MultimodalIntakeRuntime, MultimodalIntakeApi]:
    root = _runtime_root(data_root)
    # The factory is supplied by the trusted host process, never by an intake
    # request.  It is the composition seam for sandbox executors, provisioned
    # tool digests, password providers, and other runtime-owned capabilities.
    factory = runtime_factory or create_runtime
    runtime = factory(root / "intake.sqlite3", root / "cas")
    if not isinstance(runtime, MultimodalIntakeRuntime):
        raise ValidationError("MULTIMODAL_RUNTIME_FACTORY_INVALID")
    try:
        execution_environment_digest = runtime_execution_environment_digest(
            runtime,
            runtime_factory=factory,
        )
        dispatcher = SkillDispatcher()
        content_projection_store = ContentProjectionStore(
            root / "content_projection.sqlite3"
        )
        runtime._register_close_callback(content_projection_store.close)
        content_projection_bridge = ContentProjectionBridge(
            content_projection_store,
            runtime.store,
            runtime.cas,
        )
        for skill in CONTENT_PROJECTION_SKILLS:
            dispatcher.register_bridge(skill, content_projection_bridge)
        core_bridge = CoreSkillBridge(runtime)
        for skill in CORE_SKILLS:
            dispatcher.register_bridge(skill, core_bridge)
        human_review_bridge = HumanReviewCorrectionBridge(runtime.store)
        dispatcher.register_bridge(
            "elmos-human-review-and-correction",
            human_review_bridge,
        )
        surface_bridge = SurfaceSkillBridge()
        dispatcher.register_bridge("elmos-multimodal-input-workbench-ui", surface_bridge)
        dispatcher.register_bridge("elmos-ingestion-api-and-sdk", surface_bridge)
        dispatcher.register_bridge(
            "elmos-multimodal-evaluation-framework",
            EvaluationSkillBridge(
                EvaluationStore(
                    root / "evaluation.sqlite3",
                    root / "evaluation-evidence",
                )
            ),
        )
        dispatcher.register_bridge(
            "elmos-data-retention-and-governance",
            GovernanceDeletionBridge(runtime.store),
        )
        dispatcher.register_bridge(
            "elmos-downstream-agent-integration",
            DownstreamAgentBridge(runtime.store),
        )
        telemetry_bridge = TelemetryLifecycleBridge(runtime.store)
        for skill in TELEMETRY_SKILLS:
            dispatcher.register_bridge(skill, telemetry_bridge)
        project_package_bridge = ProjectPackageLifecycleBridge(runtime.store, runtime.cas)
        for skill in sorted(project_package_bridge.SKILLS):
            dispatcher.register_bridge(skill, project_package_bridge)
        context_lifecycle_bridge = ContextLifecycleBridge(runtime.store, runtime.cas)
        for skill in CONTEXT_LIFECYCLE_SKILLS:
            dispatcher.register_bridge(skill, context_lifecycle_bridge)
        knowledge_archive_bridge = KnowledgeArchiveSkillBridge(
            runtime,
            execution_environment_digest=execution_environment_digest,
        )
        dispatcher.register_bridge("elmos-storage-index-and-retrieval", knowledge_archive_bridge)
        dispatcher.register_bridge("elmos-project-memory-and-retrieval", knowledge_archive_bridge)
        dispatcher.register_bridge("elmos-secure-zip-tar-extraction", knowledge_archive_bridge)
    except BaseException:
        _close_runtime_after_composition_failure(runtime)
        raise

    def execute(request: SkillExecutionRequest) -> Mapping[str, Any]:
        if bound_context is None:
            raise AuthorizationError("BOUND_IDENTITY_REQUIRED")
        if request.context != bound_context:
            raise AuthorizationError("BOUND_IDENTITY_MISMATCH")
        bootstrap = (
            request.skill == "elmos-multimodal-input-orchestrator"
            and request.operation.strip().lower().replace("-", "_") == "bootstrap_project"
        )
        if bootstrap:
            # Establishing the first owner is the one operation that cannot
            # require an existing ACL.  It is itself idempotent; once created,
            # the normal execution receipt below durably fences and replays the
            # complete public result just like every other mutation.
            runtime.store.bootstrap_project(request.context)
        if request.skill not in SKILL_REGISTRY:
            raise NotFoundError("MULTIMODAL_SKILL_UNKNOWN")
        required_permission = _operation_permission(runtime, request)
        # Resolve and prove business authority before an execution receipt,
        # child bridge, provider, or durable domain side effect can exist.
        runtime.store.require(request.context, required_permission)
        trusted_policy, trusted_capabilities, trusted_context_epoch = _trusted_context(
            root,
            request.context,
        )
        dispatch_inputs = dict(request.input)
        if (
            request.skill == "elmos-secure-resumable-upload"
            and request.operation == "upload_part"
        ):
            encoded_aliases = [
                name for name in ("data_b64", "bytes_b64") if name in dispatch_inputs
            ]
            if len(encoded_aliases) > 1:
                raise ValidationError("UPLOAD_PART_BYTES_AMBIGUOUS")
            if encoded_aliases:
                dispatch_inputs["data_base64"] = dispatch_inputs.pop(encoded_aliases[0])
        execution_receipt_digest = _execution_receipt_digest(
            request,
            policy=trusted_policy,
            capabilities=trusted_capabilities,
            context_epoch=trusted_context_epoch,
            execution_environment_digest=execution_environment_digest,
        )
        execution_owner = f"exec-{uuid4()}"
        claim_state, receipt = runtime.store.claim_skill_execution(
            request.context,
            skill=request.skill,
            idempotency_key=request.idempotency_key,
            request_digest=execution_receipt_digest,
            owner_token=execution_owner,
            lease_seconds=EXECUTION_LEASE_SECONDS,
            required_permission=required_permission,
        )
        if claim_state == "REPLAY" and receipt is not None:
            receipt_status, receipt_body = receipt
            if receipt_status == 200:
                # Validate the persisted envelope and its original result
                # digest before changing observability-only trace metadata.
                # Otherwise corrupt SQLite bytes could be silently re-signed
                # by the replay path with a fresh result_digest.
                stored_trace_id = receipt_body.get("trace_id")
                if not isinstance(stored_trace_id, str):
                    raise ValidationError("RESULT_CONTRACT_INVALID")
                stored_request = replace(request, trace_id=stored_trace_id)
                replayed = validate_execution_result_document(
                    receipt_body,
                    expected_request=stored_request,
                )
                # trace_id is observability metadata, deliberately excluded
                # from idempotent request identity.  Echo the retry's trace
                # while preserving the prior semantic result and side effects.
                replayed["trace_id"] = request.trace_id
                replayed.pop("result_digest", None)
                replayed["result_digest"] = canonical_digest(replayed)
                replayed = validate_execution_result_document(
                    replayed,
                    expected_request=request,
                )
            else:
                replayed = dict(receipt_body)
                replayed["_http_status"] = receipt_status
            return replayed
        if claim_state == "IN_PROGRESS":
            raise ConflictError("SKILL_EXECUTION_IN_PROGRESS", retryable=True)
        if claim_state == "RECONCILIATION_REQUIRED":
            binding = SKILL_REGISTRY[request.skill]
            reconciled = execution_result(
                request,
                status="BLOCKED",
                code="EXECUTION_OUTCOME_RECONCILIATION_REQUIRED",
                retryable=False,
                output={
                    "handler_id": binding.handler_id,
                    "phase": binding.phase,
                    "metrics": {},
                    "reconciliation": {
                        "state": "REQUIRED",
                        "automatic_retry_allowed": False,
                        "reason": "PRIOR_DISPATCH_OUTCOME_UNCONFIRMED",
                    },
                },
                implementation_state="CODE_IMPLEMENTED_LOCAL",
            )
            return validate_execution_result_document(
                reconciled,
                expected_request=request,
            )
        if claim_state != "CLAIMED" or receipt is not None:
            raise ValidationError("SKILL_EXECUTION_CLAIM_STATE_INVALID")
        inputs = dispatch_inputs
        inputs.update(
            {
                "operation": request.operation,
                "idempotency_key": request.idempotency_key,
                "trace_id": request.trace_id,
            }
        )
        internal_request = {
            "schema_version": "1.0",
            "request_id": request.request_digest,
            "tenant_id": request.context.tenant_id,
            "project_id": request.context.project_id,
            "actor_id": request.context.actor_id,
            "idempotency_key": request.idempotency_key,
            "trace_id": request.trace_id,
            "inputs": inputs,
            "policy": trusted_policy,
            "capabilities": trusted_capabilities,
        }
        internal = _dispatch_with_execution_heartbeat(
            runtime,
            request,
            request_digest=execution_receipt_digest,
            owner_token=execution_owner,
            required_permission=required_permission,
            dispatch=lambda: dispatcher.dispatch(request.skill, internal_request),
        )
        try:
            output = dict(internal.get("outputs", {}))
            output["handler_id"] = internal.get("handler_id")
            output["phase"] = internal.get("phase")
            metrics = dict(internal.get("metrics", {}))
            metrics.pop("http_status", None)
            output["metrics"] = metrics
            result = execution_result(
                request,
                status=str(internal.get("state", "FAILED")),
                code=str(internal.get("code", "SKILL_EXECUTION_FAILED")),
                retryable=bool(internal.get("retryable", False)),
                output=output,
                implementation_state=str(
                    internal.get("implementation_state", "CODE_IMPLEMENTED_LOCAL")
                ),
            )
            public_result = validate_execution_result_document(
                result,
                expected_request=request,
            )
        except Exception:
            # Dispatch has started, so even malformed handler output is an
            # uncertain execution outcome.  Persist one fixed, valid terminal
            # receipt instead of leaving a lease that permits blind replay.
            binding = SKILL_REGISTRY[request.skill]
            result = execution_result(
                request,
                status="BLOCKED",
                code="EXECUTION_OUTCOME_RECONCILIATION_REQUIRED",
                retryable=False,
                output={
                    "handler_id": binding.handler_id,
                    "phase": binding.phase,
                    "metrics": {},
                    "reconciliation": {
                        "state": "REQUIRED",
                        "automatic_retry_allowed": False,
                        "reason": "PUBLIC_RESULT_INVALID",
                    },
                },
                implementation_state="CODE_IMPLEMENTED_LOCAL",
            )
            public_result = validate_execution_result_document(
                result,
                expected_request=request,
            )
        # A dispatched handler always returns the versioned result envelope over
        # HTTP 200.  Boundary/auth/idempotency failures are the only transport
        # errors; callers must inspect the result state for business outcomes.
        transport_status = 200
        completion_error: Exception | None = None
        stored_receipt: tuple[int, dict[str, Any]] | None = None
        for _attempt in range(EXECUTION_COMPLETION_ATTEMPTS):
            try:
                stored_receipt = runtime.store.complete_skill_execution(
                    request.context,
                    skill=request.skill,
                    idempotency_key=request.idempotency_key,
                    request_digest=execution_receipt_digest,
                    owner_token=execution_owner,
                    http_status=transport_status,
                    response=public_result,
                    required_permission=required_permission,
                )
                break
            except Exception as error:
                # A commit response can be lost after SQLite has durably
                # completed the row.  Retrying the same fenced completion is
                # safe and replays that row; it never invokes the handler.
                completion_error = error
        else:
            assert completion_error is not None
            raise completion_error
        assert stored_receipt is not None
        stored_status, stored_body = stored_receipt
        replayable = dict(stored_body)
        if stored_status != 200:
            replayable["_http_status"] = stored_status
        return replayable

    def catalog() -> list[dict[str, Any]]:
        values = _catalog()
        for item in values:
            item["transport"] = {
                "maximum_request_bytes": MAX_REQUEST_BYTES,
                "maximum_json_part_bytes": MAX_JSON_PART_BYTES,
                "part_number_base": 0,
            }
        return values

    try:
        api = MultimodalIntakeApi(execute, catalog)
    except BaseException:
        _close_runtime_after_composition_failure(runtime)
        raise
    return runtime, api


def execute_document(
    document: Mapping[str, Any],
    data_root: str | Path,
    *,
    bound_context: TenantContext | None = None,
    runtime_factory: RuntimeFactory | None = None,
) -> tuple[int, dict[str, Any]]:
    runtime, api = _compose(
        data_root,
        bound_context=bound_context,
        runtime_factory=runtime_factory,
    )
    try:
        response = api.execute(document)
        return response.status_code, dict(response.body)
    finally:
        runtime.close()


def capabilities_document(
    data_root: str | Path,
    *,
    runtime_factory: RuntimeFactory | None = None,
) -> tuple[int, dict[str, Any]]:
    runtime, api = _compose(data_root, runtime_factory=runtime_factory)
    try:
        response = api.capabilities()
        return response.status_code, dict(response.body)
    finally:
        runtime.close()


def _read_stdin() -> Mapping[str, Any]:
    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        raise ValidationError("MULTIMODAL_REQUEST_TOO_LARGE")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_non_finite_json,
            object_pairs_hook=_unique_json_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
        raise ValidationError("MULTIMODAL_REQUEST_JSON_INVALID") from error
    if not isinstance(value, Mapping):
        raise ValidationError("MULTIMODAL_REQUEST_INVALID")
    return value


def _emit(status_code: int, body: Mapping[str, Any]) -> int:
    result = dict(body)
    result["_http_status"] = status_code
    fallback_code: str | None = None
    try:
        encoded = canonical_json(result).encode("utf-8")
    except IntakeError:
        encoded = b""
        fallback_code = "MULTIMODAL_INTERNAL_ERROR"
    if len(encoded) + 1 > MAX_RESPONSE_BYTES:
        fallback_code = "MULTIMODAL_RESPONSE_TOO_LARGE"
    if fallback_code is not None:
        status_code = 500
        encoded = canonical_json(
            {
                "schema_version": "1.0.0",
                "status": "FAILED",
                "code": fallback_code,
                "retryable": fallback_code == "MULTIMODAL_INTERNAL_ERROR",
                "_http_status": status_code,
            }
        ).encode("utf-8")
    sys.stdout.buffer.write(encoded + b"\n")
    return status_code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-multimodal-intake")
    commands = parser.add_subparsers(dest="command", required=True)
    execute = commands.add_parser("execute")
    execute.add_argument("--data-root", required=True)
    execute.add_argument("--tenant-id", required=True)
    execute.add_argument("--project-id", required=True)
    execute.add_argument("--actor-id", required=True)
    capabilities = commands.add_parser("capabilities")
    capabilities.add_argument("--data-root", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--data-root", required=True)
    serve.add_argument("--bind", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--tenant-id", required=True)
    serve.add_argument("--project-id", required=True)
    serve.add_argument("--actor-id", required=True)
    serve.add_argument("--token-env", default="ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "serve":
        from .http_server import serve

        token = os.environ.get(args.token_env, "")
        try:
            serve(
                data_root=args.data_root,
                bind=args.bind,
                port=args.port,
                bearer_token=token,
                tenant_id=args.tenant_id,
                project_id=args.project_id,
                actor_id=args.actor_id,
            )
            return 0
        except IntakeError as error:
            _emit(
                error.http_status,
                {
                    "schema_version": "1.0.0",
                    "status": "FAILED" if error.http_status >= 500 else "BLOCKED",
                    "code": error.code,
                    "retryable": error.retryable,
                },
            )
            return 2
    try:
        if args.command == "execute":
            bound_context = TenantContext(args.tenant_id, args.project_id, args.actor_id)
            status_code, body = execute_document(
                _read_stdin(),
                args.data_root,
                bound_context=bound_context,
            )
        else:
            status_code, body = capabilities_document(args.data_root)
    except IntakeError as error:
        status_code = error.http_status
        body = {
            "schema_version": "1.0.0",
            "status": "FAILED" if status_code >= 500 else "BLOCKED",
            "code": error.code,
            "retryable": error.retryable,
        }
    status_code = _emit(status_code, body)
    if status_code >= 400:
        return 2
    return 3 if body.get("status") in {"BLOCKED", "FAILED"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
