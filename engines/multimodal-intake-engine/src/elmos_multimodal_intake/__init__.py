"""Public core facade for secure multimodal intake and durable processing."""

from __future__ import annotations

import base64
import binascii
import math
from collections.abc import Callable, Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .archive_publication import ArchivePasswordLease, ArchivePasswordProvider
from .canonical import canonical_digest, new_id, sha256_bytes
from .downstream_agent import (
    DownstreamAgentBridge,
    DownstreamResultVerifier,
    DownstreamToolAdapter,
    DownstreamToolGateway,
)
from .errors import AuthorizationError, ConflictError, IntegrityError, IntakeError, QuarantineError, ValidationError
from .models import (
    AssetKind,
    AssetStatus,
    ContentBlock,
    DetectionResult,
    GovernanceDeletionCommandState,
    GovernanceDeletionJobState,
    InputAsset,
    ResultStatus,
    SecurityDecision,
    SourceAnchor,
    TenantContext,
)
from .knowledge_worker import KnowledgeOutboxTransport, KnowledgeWorker
from .parsers import ParserRegistry
from .persistent_knowledge import PersistentKnowledgeStore
from .providers import (
    CommandReceipt,
    ExternalToolProvider,
    ProviderResult,
    ProvisionedTool,
    SandboxExecutor,
    ToolCapability,
)
from .progress_stream import job_progress_sequence
from .security import (
    FileSecurityInspector,
    apply_malware_scan,
    requires_malware_clearance,
    validate_malware_clearance,
)
from .store import IntakeStore, LocalCasStore
from .surface_bridge import ProgressDeliveryStore, ProgressWebhookTransport
from .skill_runtime import RuntimeContext
from .uploads import ResumableUploadManager, UploadPolicy, maximum_bytes_for_media_type
from .webhooks import WebhookSigner
from .workflow import MultimodalIntakeWorkflow

__version__ = "0.1.0"


SKILL_MULTIMODAL_INPUT_ORCHESTRATOR = "elmos-multimodal-input-orchestrator"
SKILL_SECURE_RESUMABLE_UPLOAD = "elmos-secure-resumable-upload"
SKILL_FILE_TYPE_DETECTION = "elmos-file-type-detection-and-validation"
SKILL_MALWARE_SANDBOX = "elmos-malware-quarantine-and-sandbox"
SKILL_AUDIO_ASR = "elmos-audio-asr-and-diarization"
SKILL_IMAGE_OCR = "elmos-image-ocr-and-preprocessing"
SKILL_VISUAL_UI = "elmos-visual-ui-understanding"
SKILL_DIAGRAM = "elmos-diagram-and-architecture-understanding"
SKILL_PDF = "elmos-pdf-layout-table-parser"
SKILL_WORD = "elmos-word-document-parser"
SKILL_TEXT = "elmos-markdown-text-log-parser"
SKILL_DURABLE_PROCESSING = "elmos-durable-processing-and-recovery"


class MultimodalIntakeRuntime:
    """JSON-facing facade; tenant/project identity is always explicit and authenticated upstream."""

    _MAX_UPLOAD_PART_ENVELOPE_BYTES = 8 * 1024 * 1024

    def __init__(
        self,
        database: str | Path,
        cas_root: str | Path,
        *,
        sandbox_executor: SandboxExecutor | None = None,
        provisioned_tools: Mapping[
            ToolCapability | str,
            ProvisionedTool | Mapping[str, str] | tuple[str, str] | str,
        ]
        | None = None,
        upload_policy: UploadPolicy | None = None,
        archive_password_provider: ArchivePasswordProvider | None = None,
        progress_webhook_transport: ProgressWebhookTransport | None = None,
        progress_webhook_signer: WebhookSigner | None = None,
    ) -> None:
        self._close_callbacks: list[Callable[[], None]] = []
        self._human_review_source_capability = object()
        self._deletion_worker_capability = object()
        self._deletion_verifier_capability = object()
        self._outbox_publisher_capability = object()
        self._outbox_response_verifier_capability = object()
        self.store = IntakeStore(
            database,
            human_review_source_capability=self._human_review_source_capability,
            deletion_worker_capability=self._deletion_worker_capability,
            deletion_verifier_capability=self._deletion_verifier_capability,
            outbox_publisher_capability=self._outbox_publisher_capability,
            outbox_response_verifier_capability=self._outbox_response_verifier_capability,
        )
        self._closed = False
        try:
            self.cas = LocalCasStore(cas_root)
            self.downstream_agent = DownstreamAgentBridge(self.store)
            self._progress_delivery_capability = object()
            self._progress_producer_capability = object()
            self.progress_deliveries = ProgressDeliveryStore(
                self.store.database.with_name(
                    self.store.database.name + ".progress-delivery.sqlite3"
                ),
                worker_capability=self._progress_delivery_capability,
                producer_capability=self._progress_producer_capability,
                transport=progress_webhook_transport,
                signer=progress_webhook_signer,
            )
            self.providers = ExternalToolProvider(sandbox_executor, provisioned_tools)
            self.archive_password_provider = archive_password_provider
            self.inspector = FileSecurityInspector()
            self.parsers = ParserRegistry(self.providers)
            self.uploads = ResumableUploadManager(self.store, self.cas, upload_policy)
            self.workflow = MultimodalIntakeWorkflow(
                self.store,
                self.cas,
                self.inspector,
                self.parsers,
                self.providers,
                human_review_source_capability=self._human_review_source_capability,
            )
            self._handlers = {
                SKILL_MULTIMODAL_INPUT_ORCHESTRATOR: self.handle_multimodal_input_orchestrator,
                SKILL_SECURE_RESUMABLE_UPLOAD: self.handle_secure_resumable_upload,
                SKILL_FILE_TYPE_DETECTION: self.handle_file_type_detection_and_validation,
                SKILL_MALWARE_SANDBOX: self.handle_malware_quarantine_and_sandbox,
                SKILL_AUDIO_ASR: self.handle_audio_asr_and_diarization,
                SKILL_IMAGE_OCR: self.handle_image_ocr_and_preprocessing,
                SKILL_VISUAL_UI: self.handle_visual_ui_understanding,
                SKILL_DIAGRAM: self.handle_diagram_and_architecture_understanding,
                SKILL_PDF: self.handle_pdf_layout_table_parser,
                SKILL_WORD: self.handle_word_document_parser,
                SKILL_TEXT: self.handle_markdown_text_log_parser,
                SKILL_DURABLE_PROCESSING: self.handle_durable_processing_and_recovery,
            }
        except Exception:
            progress_deliveries = getattr(self, "progress_deliveries", None)
            if progress_deliveries is not None:
                try:
                    progress_deliveries.close()
                except Exception:
                    pass
            try:
                self.store.close()
            except Exception:
                pass
            self._closed = True
            raise

    def _register_close_callback(self, callback: Callable[[], None]) -> None:
        """Register a trusted composition-owned resource for bounded shutdown."""

        if not callable(callback):
            raise ValidationError("MULTIMODAL_CLOSE_CALLBACK_INVALID")
        if self._closed:
            raise ConflictError("MULTIMODAL_RUNTIME_CLOSED")
        self._close_callbacks.append(callback)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        failure: BaseException | None = None
        for callback in reversed(self._close_callbacks):
            try:
                callback()
            except BaseException as error:
                if failure is None:
                    failure = error
        self._close_callbacks.clear()
        try:
            try:
                self.progress_deliveries.close()
            except BaseException as error:
                if failure is None:
                    failure = error
        finally:
            try:
                self.store.close()
            except BaseException as error:
                if failure is None:
                    failure = error
        if failure is not None:
            raise failure

    def create_knowledge_worker(
        self,
        context: TenantContext | Mapping[str, Any],
        *,
        branch: str,
        package_version: str,
        transport: KnowledgeOutboxTransport,
        executor_id: str,
        max_rebuild_targets: int = 2,
        max_outbox_events: int = 100,
    ) -> KnowledgeWorker:
        """Compose a request-inaccessible worker from trusted host inputs."""

        tenant_context = self._context(context)
        self.store.require(tenant_context, self.store.ADMIN)
        worker_capability = object()
        knowledge = PersistentKnowledgeStore(
            self.store,
            worker_capability=worker_capability,
        )
        return KnowledgeWorker(
            knowledge,
            context=tenant_context,
            branch=branch,
            package_version=package_version,
            worker_capability=worker_capability,
            transport=transport,
            executor_id=executor_id,
            max_rebuild_targets=max_rebuild_targets,
            max_outbox_events=max_outbox_events,
        )

    def create_downstream_tool_gateway(
        self,
        context: TenantContext | Mapping[str, Any],
        *,
        adapters: Mapping[str, DownstreamToolAdapter],
        result_verifier: DownstreamResultVerifier,
        verifier_id: str,
    ) -> DownstreamToolGateway:
        """Create the host-only Skill28 execution PEP from fixed adapters.

        This method is deliberately absent from Skill/API dispatch.  The host
        must already hold ADMIN for the exact tenant/project; request or
        repository content cannot register an adapter or verifier.
        """

        tenant_context = self._context(context)
        self.store.require(tenant_context, self.store.ADMIN)
        return self.downstream_agent.create_tool_gateway(
            adapters,
            result_verifier=result_verifier,
            verifier_id=verifier_id,
        )

    def deliver_progress_webhook(
        self,
        context: TenantContext | Mapping[str, Any],
        *,
        delivery_id: str,
        claim_token: str,
    ) -> dict[str, Any]:
        """Run one host-authorized delivery; no Skill payload can call this."""

        tenant_context = self._context(context)
        self.store.require(tenant_context, self.store.ADMIN)
        runtime_context = RuntimeContext(
            tenant_id=tenant_context.tenant_id,
            project_id=tenant_context.project_id,
            actor_id=tenant_context.actor_id,
            request_id="runtime-progress-delivery",
            trace_id="runtime-progress-delivery",
            idempotency_key=None,
            policy={},
            capabilities={},
        )
        return self.progress_deliveries.claim_and_deliver(
            runtime_context,
            delivery_id=delivery_id,
            claim_token=claim_token,
            capability=self._progress_delivery_capability,
        )

    def prepare_progress_webhook(
        self,
        context: TenantContext | Mapping[str, Any],
        *,
        endpoint_ref: str,
        event_type: str,
        event: Mapping[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Queue a trusted progress fact; this method has no Skill/HTTP route."""

        tenant_context = self._context(context)
        self.store.require(tenant_context, self.store.ADMIN)
        if event_type != "intake.job.progress" or not isinstance(event, Mapping):
            raise ValidationError("PROGRESS_EVENT_SOURCE_INVALID")
        job_id = event.get("job_id")
        if not isinstance(job_id, str):
            raise ValidationError("PROGRESS_EVENT_SOURCE_INVALID")
        job = self.store.get_job(tenant_context, job_id)
        expected_state = {
            "QUEUED": "PENDING",
            "RUNNING": "RUNNING",
            "COMPLETED": "SUCCEEDED",
            "PARTIAL": "PARTIAL",
            "NEEDS_REVIEW": "BLOCKED",
            "BLOCKED": "BLOCKED",
            "FAILED": "FAILED",
            "CANCELLED": "CANCELLED",
        }.get(job.status.value)
        if (
            expected_state is None
            or event.get("state") != expected_state
            or event.get("occurred_at") != job.updated_at
            or event.get("sequence") != job_progress_sequence(job)
        ):
            raise ValidationError("PROGRESS_EVENT_SOURCE_MISMATCH")
        runtime_context = RuntimeContext(
            tenant_id=tenant_context.tenant_id,
            project_id=tenant_context.project_id,
            actor_id=tenant_context.actor_id,
            request_id="runtime-progress-preparation",
            trace_id="runtime-progress-preparation",
            idempotency_key=idempotency_key,
            policy={},
            capabilities={},
        )
        return self.progress_deliveries.prepare(
            runtime_context,
            endpoint_ref=endpoint_ref,
            event_type=event_type,
            event=event,
            idempotency_key=idempotency_key,
            capability=self._progress_producer_capability,
        )

    def reconcile_progress_webhook(
        self,
        context: TenantContext | Mapping[str, Any],
        *,
        delivery_id: str,
        transport_receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Apply a host-obtained provider reconciliation result exactly once."""

        tenant_context = self._context(context)
        self.store.require(tenant_context, self.store.ADMIN)
        runtime_context = RuntimeContext(
            tenant_id=tenant_context.tenant_id,
            project_id=tenant_context.project_id,
            actor_id=tenant_context.actor_id,
            request_id="runtime-progress-reconciliation",
            trace_id="runtime-progress-reconciliation",
            idempotency_key=None,
            policy={},
            capabilities={},
        )
        return self.progress_deliveries.reconcile(
            runtime_context,
            delivery_id=delivery_id,
            capability=self._progress_delivery_capability,
            transport_receipt=transport_receipt,
        )

    def acknowledge_core_outbox_delivery(
        self,
        context: TenantContext | Mapping[str, Any],
        *,
        event_id: str,
        transport_receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Record a host-obtained, digest-bound delivery receipt exactly once."""

        tenant_context = self._context(context)
        self.store.require(tenant_context, self.store.ADMIN)
        return self.store.mark_outbox_published(
            tenant_context,
            event_id,
            publisher_capability=self._outbox_publisher_capability,
            response_verifier_capability=self._outbox_response_verifier_capability,
            transport_receipt=transport_receipt,
        )

    def claim_governance_deletion_command(
        self,
        context: TenantContext | Mapping[str, Any],
        *,
        job_id: str,
        claim_token: str,
    ) -> dict[str, Any]:
        """Claim one due deletion command through the runtime-owned worker capability."""

        tenant_context = self._context(context)
        return self.store.claim_governance_deletion_command(
            tenant_context,
            job_id=job_id,
            claim_token=claim_token,
            capability=self._deletion_worker_capability,
        )

    def record_governance_deletion_execution(
        self,
        context: TenantContext | Mapping[str, Any],
        *,
        command_id: str,
        claim_token: str,
        executor_id: str,
        disposition: str,
        observed_object_digest: str,
        deleted_byte_count: int,
        provider_evidence_digest: str,
        provider_evidence_byte_count: int,
    ) -> dict[str, Any]:
        """Record a real adapter receipt as UNKNOWN pending independent verification."""

        tenant_context = self._context(context)
        return self.store.record_governance_deletion_execution(
            tenant_context,
            command_id=command_id,
            claim_token=claim_token,
            executor_id=executor_id,
            disposition=disposition,
            observed_object_digest=observed_object_digest,
            deleted_byte_count=deleted_byte_count,
            provider_evidence_digest=provider_evidence_digest,
            provider_evidence_byte_count=provider_evidence_byte_count,
            capability=self._deletion_worker_capability,
        )

    def verify_governance_deletion_command(
        self,
        context: TenantContext | Mapping[str, Any],
        *,
        command_id: str,
        verifier_id: str,
        observed_absent: bool,
        verification_evidence_digest: str,
        verification_evidence_byte_count: int,
    ) -> dict[str, Any]:
        """Reconcile one UNKNOWN command through a distinct verifier capability."""

        tenant_context = self._context(context)
        return self.store.verify_governance_deletion_command(
            tenant_context,
            command_id=command_id,
            verifier_id=verifier_id,
            observed_absent=observed_absent,
            verification_evidence_digest=verification_evidence_digest,
            verification_evidence_byte_count=verification_evidence_byte_count,
            capability=self._deletion_verifier_capability,
        )

    def handle(
        self,
        skill_name: str,
        context: TenantContext | Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        name = str(skill_name).removeprefix("$")
        handler = self._handlers.get(name)
        if handler is None:
            raise ValidationError("MULTIMODAL_SKILL_HANDLER_NOT_FOUND", details={"skill_name": name})
        normalized = self._payload(payload)
        tenant_context = self._context(context)
        operation = self._operation(normalized)
        mutating = self._is_mutating_operation(name, operation)
        bootstrap = (
            name == SKILL_MULTIMODAL_INPUT_ORCHESTRATOR
            and operation == "bootstrap_project"
        )
        if bootstrap:
            self.store.bootstrap_project(tenant_context)
            permission = self.store.ADMIN
        else:
            permission = self.store.WRITE if mutating else self.store.READ
        # Authorization precedes the execution receipt and every handler,
        # including read-only inspection paths and provider-backed operations.
        self.store.require(tenant_context, permission)
        if not mutating:
            result = handler(tenant_context, normalized)
        else:
            idempotency_key = self._required_string(normalized, "idempotency_key")
            receipt_skill = self._receipt_skill(name, operation)
            request_digest = canonical_digest(
                {
                    "schema_version": "1.0.0",
                    "tenant_id": tenant_context.tenant_id,
                    "project_id": tenant_context.project_id,
                    "actor_id": tenant_context.actor_id,
                    "skill": name,
                    "operation": operation,
                    "payload": self._receipt_payload_identity(normalized),
                }
            )
            retry_safe_internal = (
                name == SKILL_MULTIMODAL_INPUT_ORCHESTRATOR
                and operation == "cancel_job"
            )
            owner_token = (
                f"execution-safe-{request_digest[:48]}"
                if retry_safe_internal
                else new_id("execution")
            )
            claim_state, replay = self.store.claim_skill_execution(
                tenant_context,
                skill=receipt_skill,
                idempotency_key=idempotency_key,
                request_digest=request_digest,
                owner_token=owner_token,
                lease_seconds=24 * 60 * 60,
                required_permission=permission,
                retry_safe_internal=retry_safe_internal,
            )
            if claim_state == "REPLAY":
                if replay is None:
                    raise IntegrityError("SKILL_EXECUTION_RECEIPT_CORRUPT")
                _status, body = replay
                trace_id = normalized.get("trace_id")
                if trace_id is not None:
                    body.setdefault("trace_id", str(trace_id))
                return body
            if claim_state == "IN_PROGRESS":
                raise ConflictError("SKILL_EXECUTION_IN_PROGRESS", retryable=True)
            if claim_state == "RECONCILIATION_REQUIRED":
                result = {
                    "state": "BLOCKED",
                    "code": "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED",
                    "retryable": False,
                    "outputs": {
                        "skill": name,
                        "operation": operation,
                        "reconciliation_state": "REQUIRED",
                        "automatic_retry_allowed": False,
                        **{
                            key: normalized[key]
                            for key in ("session_id", "job_id", "asset_id")
                            if isinstance(normalized.get(key), str)
                        },
                    },
                }
                trace_id = normalized.get("trace_id")
                if trace_id is not None:
                    result["trace_id"] = str(trace_id)
                return result
            if claim_state != "CLAIMED" or replay is not None:
                raise IntegrityError("SKILL_EXECUTION_CLAIM_STATE_INVALID")

            if retry_safe_internal:
                # Cancellation is a store-owned monotone mutation.  Its job,
                # session, actor metadata and audit event commit in one SQLite
                # transaction, so repeating it after any process-death window
                # is safe.  It must never inherit the provider-effect
                # dispatch-before-handler fence below.
                result = handler(tenant_context, normalized)
                _status, result = self.store.complete_skill_execution(
                    tenant_context,
                    skill=receipt_skill,
                    idempotency_key=idempotency_key,
                    request_digest=request_digest,
                    owner_token=owner_token,
                    http_status=200,
                    response=result,
                    required_permission=permission,
                )
                trace_id = normalized.get("trace_id")
                if trace_id is not None:
                    result.setdefault("trace_id", str(trace_id))
                return result

            # This is the last side-effect-free boundary for the in-process
            # facade.  A process death after the marker must reconcile the
            # prior dispatch and may never reclaim the receipt by lease age.
            try:
                self.store.mark_skill_execution_dispatched(
                    tenant_context,
                    skill=receipt_skill,
                    idempotency_key=idempotency_key,
                    request_digest=request_digest,
                    owner_token=owner_token,
                    required_permission=permission,
                )
            except BaseException:
                try:
                    self.store.release_skill_execution(
                        tenant_context,
                        skill=receipt_skill,
                        idempotency_key=idempotency_key,
                        request_digest=request_digest,
                        owner_token=owner_token,
                        required_permission=permission,
                    )
                except BaseException:
                    # If the marker committed but its response was lost, the
                    # release correctly fails and preserves reconciliation.
                    pass
                raise
            handler_error: Exception | None = None
            try:
                result = handler(tenant_context, normalized)
            except Exception as error:
                # Dispatch may already have committed a local or provider
                # effect.  Complete one fixed fail-closed result; never delete
                # a dispatched claim and make the handler eligible to repeat.
                handler_error = error
                result = {
                    "state": "BLOCKED",
                    "code": "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED",
                    "retryable": False,
                    "outputs": {
                        "skill": name,
                        "operation": operation,
                        "reconciliation_state": "REQUIRED",
                        "automatic_retry_allowed": False,
                        **{
                            key: normalized[key]
                            for key in ("session_id", "job_id", "asset_id")
                            if isinstance(normalized.get(key), str)
                        },
                    },
                }
            _status, result = self.store.complete_skill_execution(
                tenant_context,
                skill=receipt_skill,
                idempotency_key=idempotency_key,
                request_digest=request_digest,
                owner_token=owner_token,
                http_status=200,
                response=result,
                required_permission=permission,
            )
            if handler_error is not None and not self._may_have_external_effect(name, operation):
                # Preserve the public first-call validation/authorization
                # contract after durably fencing the idempotency key.  A retry
                # replays the fixed reconciliation result instead of invoking
                # the mutating handler again.
                raise handler_error
        trace_id = normalized.get("trace_id")
        if trace_id is not None:
            result.setdefault("trace_id", str(trace_id))
        return result

    def handle_multimodal_input_orchestrator(
        self,
        context: TenantContext,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        operation = self._operation(payload)
        if operation == "bootstrap_project":
            self.store.bootstrap_project(context)
            return {"tenant_id": context.tenant_id, "project_id": context.project_id, "bootstrapped": True}
        if operation == "create_session":
            session = self.store.create_session(
                context,
                idempotency_key=self._required_string(payload, "idempotency_key"),
                requested_role=str(payload.get("requested_role", "PRIMARY")),
                trace_id=str(payload["trace_id"]) if payload.get("trace_id") else None,
            )
            return {"session_id": session.session_id, "session": self._json(session)}
        if operation == "process_session":
            result = self.workflow.process_session(
                context,
                session_id=self._required_string(payload, "session_id"),
                idempotency_key=self._required_string(payload, "idempotency_key"),
                max_attempts=self._integer(payload.get("max_attempts", 3), "max_attempts"),
                expected_asset_generation_digest=(
                    self._required_string(payload, "expected_asset_generation_digest")
                    if payload.get("expected_asset_generation_digest") is not None
                    else None
                ),
            )
            encoded = self._json(result)
            return {"job_id": result.job.job_id, "session_id": result.session.session_id, **encoded}
        if operation == "resume_job":
            result = self.workflow.resume_job(context, self._required_string(payload, "job_id"))
            encoded = self._json(result)
            return {"job_id": result.job.job_id, "session_id": result.session.session_id, **encoded}
        if operation == "cancel_job":
            result = self.workflow.cancel_job(
                context,
                self._required_string(payload, "job_id"),
                reason=(
                    self._required_string(payload, "reason")
                    if payload.get("reason") is not None
                    else "CANCELLED_BY_CALLER"
                ),
            )
            encoded = self._json(result)
            return {"job_id": result.job.job_id, "session_id": result.session.session_id, **encoded}
        if operation == "get_session":
            session_id = self._required_string(payload, "session_id")
            return {
                "session": self._json(self.store.get_session(context, session_id)),
                "assets": self._json(self.store.list_assets(context, session_id)),
            }
        raise ValidationError("MULTIMODAL_ORCHESTRATOR_OPERATION_UNSUPPORTED", details={"operation": operation})

    def handle_secure_resumable_upload(
        self,
        context: TenantContext,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        operation = self._operation(payload)
        if operation == "start":
            asset, upload = self.uploads.start(
                context,
                session_id=self._required_string(payload, "session_id"),
                display_name=self._required_string(payload, "display_name"),
                declared_media_type=self._required_string(payload, "declared_media_type"),
                expected_size=self._integer(payload.get("expected_size"), "expected_size"),
                expected_sha256=self._required_string(payload, "expected_sha256"),
                idempotency_key=self._required_string(payload, "idempotency_key"),
                part_size=self._optional_integer(payload.get("part_size"), "part_size"),
                ttl_seconds=self._optional_integer(payload.get("ttl_seconds"), "ttl_seconds"),
            )
            return {
                "upload_session_id": upload.upload_id,
                "asset_id": asset.asset_id,
                "upload": self._json(upload),
                "asset": self._json(asset),
            }
        if operation == "upload_part":
            acknowledgement = self.uploads.upload_part(
                context,
                upload_id=self._upload_id(payload),
                part_number=self._integer(payload.get("part_number"), "part_number"),
                byte_offset=self._integer(payload.get("byte_offset"), "byte_offset"),
                data=self._bytes(payload),
                sha256=self._required_string(payload, "sha256", aliases=("part_sha256",)),
                idempotency_key=self._required_string(payload, "idempotency_key"),
            )
            encoded_acknowledgement = self._json(acknowledgement)
            if not isinstance(encoded_acknowledgement, dict):
                raise IntegrityError("UPLOAD_PART_ACKNOWLEDGEMENT_INVALID")
            return encoded_acknowledgement
        if operation == "commit":
            asset = self.uploads.commit(
                context,
                upload_id=self._upload_id(payload),
                idempotency_key=self._required_string(payload, "idempotency_key"),
            )
            return {"asset_id": asset.asset_id, "asset": self._json(asset)}
        if operation == "status":
            upload = self.uploads.status(context, self._upload_id(payload))
            return {"upload_session_id": upload.upload_id, "upload": self._json(upload)}
        if operation == "abort":
            upload = self.uploads.abort(context, self._upload_id(payload))
            return {"upload_session_id": upload.upload_id, "upload": self._json(upload)}
        raise ValidationError("SECURE_UPLOAD_OPERATION_UNSUPPORTED", details={"operation": operation})

    def handle_durable_processing_and_recovery(
        self,
        context: TenantContext,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        operation = self._operation(payload)
        if operation in {"transition", "process_durable_transition"}:
            transition_payload = payload.get("payload", {})
            if not isinstance(transition_payload, Mapping):
                raise ValidationError("DURABLE_PAYLOAD_INVALID")
            attempted = self._string_sequence(
                payload.get("attempted_effect_receipts", ()),
                "attempted_effect_receipts",
            )
            recorded = self._string_sequence(
                payload.get("recorded_effect_receipts", ()),
                "recorded_effect_receipts",
            )
            if attempted or recorded:
                raise AuthorizationError("DURABLE_EFFECT_RECEIPTS_REQUIRE_RECONCILER")
            event, replayed = self.store.apply_durable_transition(
                context,
                task_id=self._required_string(payload, "task_id"),
                idempotency_key=self._required_string(payload, "idempotency_key"),
                target_state=self._required_string(payload, "target_state"),
                current_state=(
                    self._required_string(payload, "current_state")
                    if payload.get("current_state") is not None
                    else None
                ),
                payload=transition_payload,
                checkpoint_digest=(
                    self._required_string(payload, "checkpoint_digest")
                    if payload.get("checkpoint_digest") is not None
                    else None
                ),
                attempted_effect_receipts=(),
                recorded_effect_receipts=(),
            )
            public_event = {
                key: value
                for key, value in event.items()
                if key not in {"effects_to_skip", "effects_to_reconcile"}
            }
            return {
                "state": "SUCCEEDED",
                "code": "DURABLE_TRANSITION_REPLAYED" if replayed else "DURABLE_TRANSITION_RECORDED",
                "outputs": {
                    "event": public_event,
                    "authoritative_state": event["target_state"],
                    "client_connection_controls_task": False,
                },
            }
        if operation == "get_task_state":
            task = self.store.durable_task_state(context, self._required_string(payload, "task_id"))
            return {"state": "SUCCEEDED", "code": "DURABLE_TASK_STATE_LOADED", "outputs": {"task": task}}
        if operation == "list_outbox":
            events = self.store.outbox_events(
                context,
                aggregate_type=(
                    self._required_string(payload, "aggregate_type")
                    if payload.get("aggregate_type") is not None
                    else None
                ),
                aggregate_id=(
                    self._required_string(payload, "aggregate_id")
                    if payload.get("aggregate_id") is not None
                    else None
                ),
                published=payload.get("published") if isinstance(payload.get("published"), bool) else None,
                limit=self._integer(payload.get("limit", 100), "limit"),
            )
            return {"state": "SUCCEEDED", "code": "OUTBOX_EVENTS_LOADED", "outputs": {"events": events}}
        if operation == "mark_outbox_published":
            raise AuthorizationError("OUTBOX_PUBLISHER_AUTHORITY_REQUIRED")
        raise ValidationError("DURABLE_PROCESSING_OPERATION_UNSUPPORTED", details={"operation": operation})

    def handle_file_type_detection_and_validation(
        self,
        context: TenantContext,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._inspect_asset(context, payload)

    def handle_malware_quarantine_and_sandbox(
        self,
        context: TenantContext,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        operation = self._operation(payload)
        if operation not in {"inspect", "process_asset"}:
            raise ValidationError("MALWARE_SCAN_OPERATION_UNSUPPORTED", details={"operation": operation})
        asset, data = self._asset_bytes(context, payload)
        passive = self.inspector.inspect(asset, data)
        scan = self.providers.run(
            ToolCapability.MALWARE_SCAN,
            data,
            passive.media_type,
            stage=f"direct-{operation}-malware-scan",
        )
        detection, verdict, scan_findings = apply_malware_scan(passive, scan)
        clearance_granted, clearance_reason = validate_malware_clearance(
            detection,
            scan,
            verdict,
            data,
        )
        combined_findings = detection.findings
        decision = detection.decision

        updated = asset
        if operation == "process_asset" and combined_findings:
            self.store.add_security_findings(context, asset.asset_id, decision, combined_findings)
        if operation == "process_asset" and decision is SecurityDecision.QUARANTINE:
            self.cas.quarantine_object(
                context.tenant_id,
                asset.cas_digest or asset.sha256 or "",
                combined_findings[0] if combined_findings else "SECURITY_QUARANTINE",
            )
            updated = self.store.set_asset_result(
                context,
                asset.asset_id,
                status=AssetStatus.QUARANTINED,
                kind=detection.kind,
                detected_media_type=detection.media_type,
                security_decision=detection.decision,
                failure_code=combined_findings[0] if combined_findings else "SECURITY_QUARANTINE",
            )
        return {
            "asset_id": asset.asset_id,
            "asset": self._json(updated),
            "detection": self._json(detection),
            "scan_proof": {
                "status": scan.status.value,
                "verdict": verdict,
                "capability": scan.capability.value,
                "findings": list(scan_findings),
                "error_code": scan.error_code,
                "receipt": self._json(scan.receipt),
                "sandbox_required": True,
                "network_allowed": False,
                "clearance_granted": clearance_granted,
                "clearance_reason": clearance_reason,
            },
        }

    def handle_audio_asr_and_diarization(
        self,
        context: TenantContext,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._parse_asset(context, payload, {AssetKind.AUDIO})

    def handle_image_ocr_and_preprocessing(
        self,
        context: TenantContext,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._parse_asset(context, payload, {AssetKind.IMAGE})

    def handle_visual_ui_understanding(
        self,
        context: TenantContext,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._provider_only_asset(context, payload, ToolCapability.VISUAL_UI, AssetKind.IMAGE)

    def handle_diagram_and_architecture_understanding(
        self,
        context: TenantContext,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._provider_only_asset(context, payload, ToolCapability.DIAGRAM, AssetKind.IMAGE)

    def handle_pdf_layout_table_parser(
        self,
        context: TenantContext,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._parse_asset(context, payload, {AssetKind.PDF})

    def handle_word_document_parser(
        self,
        context: TenantContext,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._parse_asset(context, payload, {AssetKind.DOCX})

    def handle_markdown_text_log_parser(
        self,
        context: TenantContext,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._parse_asset(context, payload, {AssetKind.TEXT, AssetKind.MARKDOWN, AssetKind.LOG})

    def _inspect_asset(self, context: TenantContext, payload: Mapping[str, Any]) -> dict[str, Any]:
        operation = self._operation(payload)
        if operation not in {"inspect", "process_asset"}:
            raise ValidationError("ASSET_INSPECTION_OPERATION_UNSUPPORTED", details={"operation": operation})
        asset, data = self._asset_bytes(context, payload)
        detection = self.inspector.inspect(asset, data)
        return {"asset_id": asset.asset_id, "detection": self._json(detection)}

    def _parse_asset(
        self,
        context: TenantContext,
        payload: Mapping[str, Any],
        accepted_kinds: set[AssetKind],
    ) -> dict[str, Any]:
        operation = self._operation(payload)
        if operation not in {"parse", "process_asset"}:
            raise ValidationError("ASSET_PARSE_OPERATION_UNSUPPORTED", details={"operation": operation})
        asset, data = self._asset_bytes(context, payload)
        passive = self.inspector.inspect(asset, data)
        detection, _scan, scan_proof = self._assess_malware(
            data,
            passive,
            stage=f"direct-{operation}-malware-scan",
        )
        if detection.kind not in accepted_kinds:
            raise ValidationError(
                "ASSET_KIND_MISMATCH",
                details={"detected_kind": detection.kind.value, "accepted_kinds": sorted(item.value for item in accepted_kinds)},
            )
        if detection.decision is SecurityDecision.QUARANTINE:
            if operation == "process_asset":
                self.store.add_security_findings(context, asset.asset_id, detection.decision, detection.findings)
                self.cas.quarantine_object(
                    context.tenant_id,
                    asset.cas_digest or asset.sha256 or "",
                    detection.findings[0] if detection.findings else "SECURITY_QUARANTINE",
                )
                self.store.set_asset_result(
                    context,
                    asset.asset_id,
                    status=AssetStatus.QUARANTINED,
                    kind=detection.kind,
                    detected_media_type=detection.media_type,
                    security_decision=detection.decision,
                    failure_code=detection.findings[0] if detection.findings else "SECURITY_QUARANTINE",
                )
            blocked_report = {
                "parser": "security-gate",
                "status": ResultStatus.BLOCKED.value,
                "blocks": [],
                "warnings": list(detection.findings),
                "error_code": "ASSET_QUARANTINED",
                "provider_receipt": {},
                "metadata": {"malware_scan": scan_proof},
            }
            return {
                "asset_id": asset.asset_id,
                "detection": self._json(detection),
                "report": blocked_report,
            }
        if requires_malware_clearance(detection.kind) and not scan_proof["clearance_granted"]:
            clearance_report = {
                "parser": "malware-clearance-gate",
                "status": ResultStatus.NEEDS_REVIEW.value,
                "blocks": [],
                "warnings": sorted(
                    set(detection.findings + (str(scan_proof["clearance_reason"]),))
                ),
                "error_code": "MALWARE_CLEARANCE_REQUIRED",
                "provider_receipt": {},
                "metadata": {"malware_scan": scan_proof},
            }
            return {
                "asset_id": asset.asset_id,
                "detection": self._json(detection),
                "report": clearance_report,
            }
        parse_report = self.parsers.parse(
            asset,
            data,
            detection,
            {"revision_mode": payload.get("revision_mode", "final")},
            stage=f"direct-{operation}-parse",
        )
        metadata = dict(parse_report.metadata)
        metadata["malware_scan"] = scan_proof
        if detection.decision is SecurityDecision.NEEDS_REVIEW and parse_report.status is ResultStatus.PASSED:
            parse_report = type(parse_report)(
                parser=parse_report.parser,
                status=ResultStatus.NEEDS_REVIEW,
                blocks=parse_report.blocks,
                warnings=tuple(sorted(set(parse_report.warnings + detection.findings))),
                error_code="SECURITY_REVIEW_REQUIRED",
                provider_receipt=parse_report.provider_receipt,
                metadata=metadata,
            )
        elif metadata != dict(parse_report.metadata):
            parse_report = type(parse_report)(
                parser=parse_report.parser,
                status=parse_report.status,
                blocks=parse_report.blocks,
                warnings=parse_report.warnings,
                error_code=parse_report.error_code,
                provider_receipt=parse_report.provider_receipt,
                metadata=metadata,
            )
        return {
            "asset_id": asset.asset_id,
            "detection": self._json(detection),
            "report": self._json(parse_report),
        }

    def _provider_only_asset(
        self,
        context: TenantContext,
        payload: Mapping[str, Any],
        capability: ToolCapability,
        accepted_kind: AssetKind,
    ) -> dict[str, Any]:
        operation = self._operation(payload)
        if operation not in {"parse", "process_asset", "understand"}:
            raise ValidationError("PROVIDER_ASSET_OPERATION_UNSUPPORTED", details={"operation": operation})
        asset, data = self._asset_bytes(context, payload)
        passive = self.inspector.inspect(asset, data)
        detection, _scan, scan_proof = self._assess_malware(
            data,
            passive,
            stage=f"direct-{operation}-malware-scan",
        )
        if detection.kind is not accepted_kind:
            raise ValidationError("ASSET_KIND_MISMATCH", details={"detected_kind": detection.kind.value})
        if detection.decision is SecurityDecision.QUARANTINE:
            return {
                "asset_id": asset.asset_id,
                "detection": self._json(detection),
                "malware_scan": scan_proof,
                "provider_result": self._json(
                    ProviderResult(
                        status=ResultStatus.BLOCKED,
                        capability=capability,
                        error_code="ASSET_QUARANTINED",
                        warnings=detection.findings,
                    )
                ),
            }
        if requires_malware_clearance(detection.kind) and not scan_proof["clearance_granted"]:
            return {
                "asset_id": asset.asset_id,
                "detection": self._json(detection),
                "malware_scan": scan_proof,
                "provider_result": self._json(
                    ProviderResult(
                        status=ResultStatus.NEEDS_REVIEW,
                        capability=capability,
                        error_code="MALWARE_CLEARANCE_REQUIRED",
                        warnings=tuple(
                            sorted(
                                set(
                                    detection.findings
                                    + (str(scan_proof["clearance_reason"]),)
                                )
                            )
                        ),
                    )
                ),
            }
        provider = self.providers.run(
            capability,
            data,
            detection.media_type,
            stage=f"direct-{operation}-{capability.value.lower()}",
        )
        if provider.status is ResultStatus.PASSED:
            provider = self._validated_understanding_provider(capability, provider, asset)
        if detection.decision is SecurityDecision.NEEDS_REVIEW and provider.status is ResultStatus.PASSED:
            provider = ProviderResult(
                status=ResultStatus.NEEDS_REVIEW,
                capability=capability,
                payload=provider.payload,
                error_code="SECURITY_REVIEW_REQUIRED",
                warnings=tuple(sorted(set(provider.warnings + detection.findings))),
                receipt=provider.receipt,
            )
        return {
            "asset_id": asset.asset_id,
            "detection": self._json(detection),
            "malware_scan": scan_proof,
            "provider_result": self._json(provider),
        }

    def _assess_malware(
        self,
        data: bytes,
        passive: DetectionResult,
        *,
        job_id: str | None = None,
        stage: str | None = None,
    ) -> tuple[DetectionResult, ProviderResult, dict[str, Any]]:
        scan = self.providers.run(
            ToolCapability.MALWARE_SCAN,
            data,
            passive.media_type,
            job_id=job_id,
            stage=stage,
        )
        detection, verdict, findings = apply_malware_scan(passive, scan)
        clearance_granted, clearance_reason = validate_malware_clearance(
            detection,
            scan,
            verdict,
            data,
        )
        proof = {
            "status": scan.status.value,
            "verdict": verdict,
            "capability": scan.capability.value,
            "findings": list(findings),
            "error_code": scan.error_code,
            "receipt": self._json(scan.receipt),
            "sandbox_required": True,
            "network_allowed": False,
            "clearance_granted": clearance_granted,
            "clearance_reason": clearance_reason,
        }
        return detection, scan, proof

    def _validated_understanding_provider(
        self,
        capability: ToolCapability,
        provider: ProviderResult,
        asset: InputAsset,
    ) -> ProviderResult:
        try:
            if capability is ToolCapability.VISUAL_UI:
                payload = self._normalize_ui_visual_ir(provider.payload, asset)
            elif capability is ToolCapability.DIAGRAM:
                payload = self._normalize_diagram_ir(provider.payload, asset)
            else:
                return provider
        except ValidationError as error:
            return ProviderResult(
                status=ResultStatus.NEEDS_REVIEW,
                capability=capability,
                error_code=error.code,
                warnings=(error.code,),
                receipt=provider.receipt,
            )
        return ProviderResult(
            status=ResultStatus.PASSED,
            capability=capability,
            payload=payload,
            receipt=provider.receipt,
        )

    def _normalize_ui_visual_ir(
        self,
        payload: Mapping[str, Any],
        asset: InputAsset,
    ) -> dict[str, Any]:
        raw_elements = payload.get("elements")
        if not isinstance(raw_elements, list) or len(raw_elements) > 10_000:
            raise ValidationError("UI_VISUAL_IR_ELEMENTS_INVALID")
        identifiers: set[str] = set()
        elements: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_elements):
            if not isinstance(raw, Mapping):
                raise ValidationError("UI_VISUAL_IR_ELEMENT_INVALID")
            identifier = self._bounded_text(raw.get("id"), "UI_VISUAL_IR_ELEMENT_ID_INVALID", 128)
            if identifier in identifiers:
                raise ValidationError("UI_VISUAL_IR_ELEMENT_ID_DUPLICATE")
            identifiers.add(identifier)
            bbox = self._validated_bbox(raw.get("bbox"), "UI_VISUAL_IR_ELEMENT_BBOX_INVALID")
            basis = str(raw.get("basis", "")).upper()
            if basis not in {"OBSERVED", "INFERRED"}:
                raise ValidationError("UI_VISUAL_IR_BASIS_REQUIRED")
            elements.append(
                {
                    "id": identifier,
                    "type": self._bounded_text(raw.get("type"), "UI_VISUAL_IR_ELEMENT_TYPE_INVALID", 128),
                    "label": self._optional_bounded_text(raw.get("label"), 2048),
                    "parent_id": self._optional_bounded_text(raw.get("parent_id"), 128),
                    "bbox": list(bbox),
                    "basis": basis,
                    "confidence": self._validated_confidence(raw.get("confidence")),
                    "state": self._optional_bounded_text(raw.get("state"), 128),
                    "interaction": self._optional_bounded_text(raw.get("interaction"), 512),
                    "source_anchor": {
                        "asset_id": asset.asset_id,
                        "source_sha256": asset.sha256,
                        "bbox": list(bbox),
                    },
                }
            )
        if any(item["parent_id"] is not None and item["parent_id"] not in identifiers for item in elements):
            raise ValidationError("UI_VISUAL_IR_PARENT_NOT_FOUND")
        assumptions = payload.get("assumptions", [])
        if not isinstance(assumptions, list) or len(assumptions) > 1_000:
            raise ValidationError("UI_VISUAL_IR_ASSUMPTIONS_INVALID")
        normalized_assumptions = [
            self._bounded_text(item, "UI_VISUAL_IR_ASSUMPTION_INVALID", 2048)
            for item in assumptions
        ]
        return {
            "schema_version": "1.0.0",
            "asset_id": asset.asset_id,
            "source_sha256": asset.sha256,
            "target_platform": self._optional_bounded_text(payload.get("target_platform"), 128),
            "elements": elements,
            "component_count": len(elements),
            "assumptions": normalized_assumptions,
            "facts_and_inferences_separated": True,
            "visual_regression": "NOT_RUN",
        }

    def _normalize_diagram_ir(
        self,
        payload: Mapping[str, Any],
        asset: InputAsset,
    ) -> dict[str, Any]:
        raw_nodes = payload.get("nodes")
        raw_edges = payload.get("edges")
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise ValidationError("DIAGRAM_IR_COLLECTIONS_INVALID")
        if len(raw_nodes) > 20_000 or len(raw_edges) > 50_000:
            raise ValidationError("DIAGRAM_IR_SIZE_LIMIT_EXCEEDED")
        nodes: list[dict[str, Any]] = []
        identifiers: set[str] = set()
        for raw in raw_nodes:
            if not isinstance(raw, Mapping):
                raise ValidationError("DIAGRAM_IR_NODE_INVALID")
            identifier = self._bounded_text(raw.get("id"), "DIAGRAM_IR_NODE_ID_INVALID", 128)
            if identifier in identifiers:
                raise ValidationError("DIAGRAM_IR_NODE_ID_DUPLICATE")
            identifiers.add(identifier)
            bbox = self._validated_bbox(raw.get("bbox"), "DIAGRAM_IR_NODE_BBOX_INVALID")
            nodes.append(
                {
                    "id": identifier,
                    "type": self._bounded_text(raw.get("type"), "DIAGRAM_IR_NODE_TYPE_INVALID", 128),
                    "label": self._bounded_text(raw.get("label"), "DIAGRAM_IR_NODE_LABEL_INVALID", 2048),
                    "bbox": list(bbox),
                    "confidence": self._validated_confidence(raw.get("confidence")),
                    "source_anchor": {
                        "asset_id": asset.asset_id,
                        "source_sha256": asset.sha256,
                        "bbox": list(bbox),
                    },
                }
            )
        edges: list[dict[str, Any]] = []
        edge_identifiers: set[str] = set()
        for raw in raw_edges:
            if not isinstance(raw, Mapping):
                raise ValidationError("DIAGRAM_IR_EDGE_INVALID")
            identifier = self._bounded_text(raw.get("id"), "DIAGRAM_IR_EDGE_ID_INVALID", 128)
            if identifier in edge_identifiers:
                raise ValidationError("DIAGRAM_IR_EDGE_ID_DUPLICATE")
            edge_identifiers.add(identifier)
            source = self._bounded_text(raw.get("source"), "DIAGRAM_IR_EDGE_SOURCE_INVALID", 128)
            target = self._bounded_text(raw.get("target"), "DIAGRAM_IR_EDGE_TARGET_INVALID", 128)
            if source not in identifiers or target not in identifiers:
                raise ValidationError("DIAGRAM_IR_EDGE_ENDPOINT_NOT_FOUND")
            direction = str(raw.get("direction", "")).upper()
            if direction not in {"DIRECTED", "UNDIRECTED", "AMBIGUOUS"}:
                raise ValidationError("DIAGRAM_IR_EDGE_DIRECTION_INVALID")
            bbox = self._validated_bbox(raw.get("bbox"), "DIAGRAM_IR_EDGE_BBOX_INVALID")
            edges.append(
                {
                    "id": identifier,
                    "source": source,
                    "target": target,
                    "relation": self._bounded_text(raw.get("relation", "UNKNOWN"), "DIAGRAM_IR_RELATION_INVALID", 128),
                    "direction": direction,
                    "bbox": list(bbox),
                    "confidence": self._validated_confidence(raw.get("confidence")),
                    "unresolved": direction == "AMBIGUOUS",
                    "source_anchor": {
                        "asset_id": asset.asset_id,
                        "source_sha256": asset.sha256,
                        "bbox": list(bbox),
                    },
                }
            )
        unresolved = [item["id"] for item in edges if item["unresolved"]]
        mermaid, plantuml = self._diagram_exports(nodes, edges)
        return {
            "schema_version": "1.0.0",
            "asset_id": asset.asset_id,
            "source_sha256": asset.sha256,
            "nodes": nodes,
            "edges": edges,
            "unresolved_edges": unresolved,
            "exports": {"mermaid": mermaid, "plantuml": plantuml},
            "render_comparison": "NOT_RUN",
        }

    @staticmethod
    def _diagram_exports(
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> tuple[str, str]:
        aliases = {node["id"]: f"n{index}" for index, node in enumerate(nodes)}

        def label(value: str) -> str:
            result = value.replace("\r", " ").replace("\n", " ")
            for marker in ('"', "\\", "|", "[", "]", "{", "}", "<", ">", "`"):
                result = result.replace(marker, " ")
            return " ".join(result.split())[:2048]

        mermaid = ["flowchart TD"]
        plantuml = ["@startuml"]
        for node in nodes:
            alias = aliases[node["id"]]
            rendered = label(node["label"])
            mermaid.append(f'  {alias}["{rendered}"]')
            plantuml.append(f'component "{rendered}" as {alias}')
        for edge in edges:
            source = aliases[edge["source"]]
            target = aliases[edge["target"]]
            relation = label(edge["relation"])
            connector = "-->" if edge["direction"] == "DIRECTED" else "---"
            mermaid.append(f"  {source} {connector}|{relation}| {target}")
            plant_connector = "-->" if edge["direction"] == "DIRECTED" else "--"
            plantuml.append(f'{source} {plant_connector} {target} : "{relation}"')
        plantuml.append("@enduml")
        return "\n".join(mermaid), "\n".join(plantuml)

    @staticmethod
    def _bounded_text(value: Any, code: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValidationError(code)
        return value.strip()

    @staticmethod
    def _optional_bounded_text(value: Any, maximum: int) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or len(value) > maximum:
            raise ValidationError("UNDERSTANDING_IR_TEXT_INVALID")
        return value.strip() or None

    @staticmethod
    def _validated_bbox(value: Any, code: str) -> tuple[float, float, float, float]:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            raise ValidationError(code)
        if any(
            not isinstance(item, (int, float))
            or isinstance(item, bool)
            or not math.isfinite(float(item))
            or float(item) < 0
            for item in value
        ):
            raise ValidationError(code)
        return tuple(float(item) for item in value)  # type: ignore[return-value]

    @staticmethod
    def _validated_confidence(value: Any) -> float:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or not 0 <= float(value) <= 1
        ):
            raise ValidationError("UNDERSTANDING_IR_CONFIDENCE_INVALID")
        return float(value)

    @staticmethod
    def _is_mutating_operation(skill_name: str, operation: str) -> bool:
        operations = {
            SKILL_MULTIMODAL_INPUT_ORCHESTRATOR: {
                "bootstrap_project",
                "create_session",
                "process_session",
                "resume_job",
                "cancel_job",
            },
            SKILL_SECURE_RESUMABLE_UPLOAD: {"start", "upload_part", "commit", "abort"},
            SKILL_MALWARE_SANDBOX: {"inspect", "process_asset"},
            SKILL_AUDIO_ASR: {"parse", "process_asset"},
            SKILL_IMAGE_OCR: {"parse", "process_asset"},
            SKILL_VISUAL_UI: {"parse", "process_asset", "understand"},
            SKILL_DIAGRAM: {"parse", "process_asset", "understand"},
            SKILL_PDF: {"parse", "process_asset"},
            SKILL_WORD: {"parse", "process_asset"},
            SKILL_TEXT: {"parse", "process_asset"},
            SKILL_DURABLE_PROCESSING: {"transition", "process_durable_transition", "mark_outbox_published"},
        }
        return operation in operations.get(skill_name, set())

    @staticmethod
    def _receipt_skill(skill_name: str, operation: str) -> str:
        value = f"core.{skill_name}.{operation}"
        if len(value) <= 128:
            return value
        return f"core.{canonical_digest(value)[:64]}"

    @staticmethod
    def _may_have_external_effect(skill_name: str, operation: str) -> bool:
        if skill_name == SKILL_MULTIMODAL_INPUT_ORCHESTRATOR:
            return operation in {"process_session", "resume_job"}
        return skill_name in {
            SKILL_MALWARE_SANDBOX,
            SKILL_AUDIO_ASR,
            SKILL_IMAGE_OCR,
            SKILL_VISUAL_UI,
            SKILL_DIAGRAM,
            SKILL_PDF,
            SKILL_WORD,
            SKILL_TEXT,
        } and operation in {"inspect", "parse", "process_asset", "understand"}

    @classmethod
    def _receipt_payload_identity(cls, payload: Mapping[str, Any]) -> dict[str, Any]:
        def identity(value: Any, key: str | None = None) -> Any:
            if isinstance(value, bytes):
                if key == "data" and len(value) > cls._MAX_UPLOAD_PART_ENVELOPE_BYTES:
                    raise ValidationError("UPLOAD_PART_BYTES_OUTSIDE_POLICY")
                return {"byte_size": len(value), "sha256": sha256_bytes(value)}
            if key == "data_base64" and isinstance(value, str):
                maximum_encoded = 4 * ((cls._MAX_UPLOAD_PART_ENVELOPE_BYTES + 2) // 3)
                if len(value) > maximum_encoded:
                    raise ValidationError("UPLOAD_PART_BYTES_OUTSIDE_POLICY")
                encoded = value.encode("utf-8")
                return {"encoded_bytes": len(encoded), "encoded_sha256": sha256_bytes(encoded)}
            if isinstance(value, Mapping):
                return {
                    str(item_key): identity(item, str(item_key))
                    for item_key, item in value.items()
                    if str(item_key) != "trace_id"
                }
            if isinstance(value, (tuple, list)):
                return [identity(item) for item in value]
            if isinstance(value, (set, frozenset)):
                return sorted((identity(item) for item in value), key=repr)
            if value is None or isinstance(value, (str, int, float, bool)):
                return value
            raise ValidationError(
                "SKILL_RECEIPT_PAYLOAD_INVALID",
                details={"type": type(value).__name__},
            )

        result = identity(payload)
        if not isinstance(result, dict):
            raise IntegrityError("SKILL_RECEIPT_PAYLOAD_INVALID")
        return result

    def _asset_bytes(
        self,
        context: TenantContext,
        payload: Mapping[str, Any],
    ) -> tuple[InputAsset, bytes]:
        asset = self.store.get_asset(context, self._required_string(payload, "asset_id"))
        if asset.status is AssetStatus.QUARANTINED:
            raise QuarantineError("ASSET_QUARANTINED")
        if asset.cas_digest is None or asset.sha256 is None:
            raise ValidationError("ASSET_UPLOAD_NOT_COMMITTED")
        if asset.sha256 != asset.cas_digest:
            raise IntegrityError("ASSET_CAS_DIGEST_BINDING_MISMATCH")
        data = self.cas.read_bytes(
            context.tenant_id,
            asset.cas_digest,
            maximum_bytes=maximum_bytes_for_media_type(asset.declared_media_type),
            expected_size=asset.byte_size,
        )
        return asset, data

    @staticmethod
    def _context(value: TenantContext | Mapping[str, Any]) -> TenantContext:
        if isinstance(value, TenantContext):
            return value
        if not isinstance(value, Mapping):
            raise ValidationError("TENANT_CONTEXT_INVALID")
        return TenantContext(
            tenant_id=str(value.get("tenant_id", "")),
            project_id=str(value.get("project_id", "")),
            actor_id=str(value.get("actor_id", "")),
        )

    @staticmethod
    def _payload(value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ValidationError("SKILL_PAYLOAD_INVALID")
        nested = value.get("input")
        if nested is not None and not isinstance(nested, Mapping):
            raise ValidationError("SKILL_INPUT_ENVELOPE_INVALID")
        result = dict(nested) if isinstance(nested, Mapping) else {}
        result.update({key: item for key, item in value.items() if key != "input"})
        return result

    @staticmethod
    def _operation(payload: Mapping[str, Any]) -> str:
        value = str(payload.get("operation", "")).strip().lower().replace("-", "_")
        if not value:
            raise ValidationError("SKILL_OPERATION_REQUIRED")
        return value

    @staticmethod
    def _required_string(
        payload: Mapping[str, Any],
        name: str,
        *,
        aliases: tuple[str, ...] = (),
    ) -> str:
        for key in (name, *aliases):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        raise ValidationError("SKILL_INPUT_REQUIRED", details={"field": name})

    @classmethod
    def _upload_id(cls, payload: Mapping[str, Any]) -> str:
        return cls._required_string(payload, "upload_session_id", aliases=("upload_id",))

    @staticmethod
    def _integer(value: Any, name: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError("SKILL_INTEGER_INPUT_INVALID", details={"field": name})
        return value

    @classmethod
    def _optional_integer(cls, value: Any, name: str) -> int | None:
        return None if value is None else cls._integer(value, name)

    @staticmethod
    def _string_sequence(value: Any, name: str) -> tuple[str, ...]:
        if not isinstance(value, (tuple, list)) or len(value) > 1000:
            raise ValidationError("SKILL_STRING_SEQUENCE_INVALID", details={"field": name})
        result: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValidationError("SKILL_STRING_SEQUENCE_INVALID", details={"field": name})
            result.append(item.strip())
        return tuple(result)

    def _bytes(self, payload: Mapping[str, Any]) -> bytes:
        maximum_bytes = self.uploads.policy.maximum_part_size
        value = payload.get("data")
        if isinstance(value, bytes):
            if len(value) > maximum_bytes:
                raise ValidationError("UPLOAD_PART_BYTES_OUTSIDE_POLICY")
            return value
        encoded = payload.get("data_base64")
        if not isinstance(encoded, str):
            raise ValidationError("UPLOAD_PART_BYTES_REQUIRED")
        maximum_encoded = 4 * ((maximum_bytes + 2) // 3)
        if len(encoded) > maximum_encoded:
            raise ValidationError("UPLOAD_PART_BYTES_OUTSIDE_POLICY")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValidationError("UPLOAD_PART_BASE64_INVALID") from error
        if len(decoded) > maximum_bytes:
            raise ValidationError("UPLOAD_PART_BYTES_OUTSIDE_POLICY")
        return decoded

    @classmethod
    def _json(cls, value: Any) -> Any:
        if is_dataclass(value):
            return {field.name: cls._json(getattr(value, field.name)) for field in fields(value)}
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Mapping):
            return {str(key): cls._json(item) for key, item in value.items()}
        if isinstance(value, (tuple, list, set, frozenset)):
            return [cls._json(item) for item in value]
        if isinstance(value, float) and not math.isfinite(value):
            raise ValidationError("RUNTIME_RESULT_NON_FINITE_NUMBER")
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise ValidationError("RUNTIME_RESULT_NOT_JSON_SERIALIZABLE", details={"type": type(value).__name__})


def create_runtime(
    db_path: str | Path,
    cas_root: str | Path,
    *,
    sandbox_executor: SandboxExecutor | None = None,
    provisioned_tools: Mapping[
        ToolCapability | str,
        ProvisionedTool | Mapping[str, str] | tuple[str, str] | str,
    ]
    | None = None,
    upload_policy: UploadPolicy | None = None,
    archive_password_provider: ArchivePasswordProvider | None = None,
    progress_webhook_transport: ProgressWebhookTransport | None = None,
    progress_webhook_signer: WebhookSigner | None = None,
) -> MultimodalIntakeRuntime:
    return MultimodalIntakeRuntime(
        db_path,
        cas_root,
        sandbox_executor=sandbox_executor,
        provisioned_tools=provisioned_tools,
        upload_policy=upload_policy,
        archive_password_provider=archive_password_provider,
        progress_webhook_transport=progress_webhook_transport,
        progress_webhook_signer=progress_webhook_signer,
    )


__all__ = [
    "IntakeError",
    "CommandReceipt",
    "ArchivePasswordLease",
    "ArchivePasswordProvider",
    "ContentBlock",
    "GovernanceDeletionCommandState",
    "GovernanceDeletionJobState",
    "MultimodalIntakeRuntime",
    "KnowledgeOutboxTransport",
    "KnowledgeWorker",
    "PersistentKnowledgeStore",
    "ProgressDeliveryStore",
    "ProgressWebhookTransport",
    "ProviderResult",
    "ProvisionedTool",
    "ResultStatus",
    "SandboxExecutor",
    "SourceAnchor",
    "TenantContext",
    "ToolCapability",
    "UploadPolicy",
    "WebhookSigner",
    "create_runtime",
]
