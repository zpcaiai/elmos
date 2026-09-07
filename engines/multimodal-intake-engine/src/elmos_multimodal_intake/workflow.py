"""Durable, checkpointed per-asset processing with explicit partial success."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from typing import Any

from .canonical import canonical_digest, new_id, normalize_sha256
from .errors import ConflictError, IntakeError, IntegrityError
from .models import (
    AssetKind,
    AssetStatus,
    InputAsset,
    JobStatus,
    ParseReport,
    ProcessingJob,
    ResultStatus,
    SecurityDecision,
    SessionStatus,
    TenantContext,
    WorkflowResult,
)
from .parsers import ParserRegistry
from .providers import ExternalToolProvider, ProviderResult, ToolCapability
from .security import (
    FileSecurityInspector,
    apply_malware_scan,
    requires_malware_clearance,
    validate_malware_clearance,
)
from .store import IntakeStore, LocalCasStore
from .uploads import maximum_bytes_for_media_type


class _WorkflowCancellation(Exception):
    """Internal control flow after durable cancellation has won the fence."""


class MultimodalIntakeWorkflow:
    # One asset may invoke both the malware scanner and a format provider.  The
    # provider contract permits 300 seconds per invocation, so the lease must
    # cover the full bounded chain rather than only one external call.
    JOB_LEASE_SECONDS = 15 * 60
    EXTERNAL_EFFECT_RECONCILIATION_CODE = "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED"
    AMBIGUOUS_PROVIDER_FAILURES = frozenset(
        {"SANDBOX_EXECUTION_FAILED", "SANDBOX_RECEIPT_INVALID"}
    )
    MALWARE_EFFECT_SKILL = "workflow.malware-scan-effect.v1"
    MALWARE_EFFECT_SCHEMA = "elmos-malware-scan-effect-v1"
    PARSER_EFFECT_SKILL = "workflow.parser-provider-effect.v1"
    PARSER_EFFECT_SCHEMA = "elmos-parser-provider-effect-v1"
    TERMINAL_JOBS = {
        JobStatus.COMPLETED,
        JobStatus.PARTIAL,
        JobStatus.NEEDS_REVIEW,
        JobStatus.BLOCKED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }

    def __init__(
        self,
        store: IntakeStore,
        cas: LocalCasStore,
        inspector: FileSecurityInspector,
        parsers: ParserRegistry,
        providers: ExternalToolProvider,
        *,
        human_review_source_capability: object,
    ) -> None:
        self.store = store
        self.cas = cas
        self.inspector = inspector
        self.parsers = parsers
        self.providers = providers
        self._human_review_source_capability = human_review_source_capability

    def process_session(
        self,
        context: TenantContext,
        *,
        session_id: str,
        idempotency_key: str,
        max_attempts: int = 3,
        expected_asset_generation_digest: str | None = None,
    ) -> WorkflowResult:
        assets = self.store.list_assets(context, session_id)
        committed_assets = [
            asset
            for asset in assets
            if asset.sha256
            and asset.cas_digest
            and asset.status not in {AssetStatus.CREATED, AssetStatus.UPLOADING}
        ]
        generation_digest = hashlib.sha256(
            "\n".join(sorted(asset.asset_id for asset in committed_assets)).encode("utf-8")
        ).hexdigest()
        if expected_asset_generation_digest is not None:
            expected_generation = normalize_sha256(expected_asset_generation_digest)
            if not hmac.compare_digest(generation_digest, expected_generation):
                raise ConflictError(
                    "ASSET_GENERATION_DIGEST_MISMATCH",
                    details={
                        "expected_asset_generation_digest": expected_generation,
                        "actual_asset_generation_digest": generation_digest,
                    },
                )
        request_digest = canonical_digest(
            {
                "session_id": session_id,
                "max_attempts": max_attempts,
                "asset_generation_digest": generation_digest,
                "asset_generation": [
                    {
                        "asset_id": asset.asset_id,
                        "source_sha256": asset.sha256,
                        "byte_size": asset.byte_size,
                    }
                    for asset in committed_assets
                ],
                "workflow_contract": "multimodal-intake-v2",
            }
        )
        job = self.store.create_job(
            context,
            session_id,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            max_attempts=max_attempts,
        )
        if job.status in self.TERMINAL_JOBS:
            return self._result(context, job)
        return self._run(context, job)

    def resume_job(self, context: TenantContext, job_id: str) -> WorkflowResult:
        job = self.store.get_job(context, job_id, write=True)
        if job.status in self.TERMINAL_JOBS:
            return self._result(context, job)
        return self._run(context, job)

    def cancel_job(
        self,
        context: TenantContext,
        job_id: str,
        *,
        reason: str = "CANCELLED_BY_CALLER",
    ) -> WorkflowResult:
        job, _session = self.store.request_job_cancellation(
            context,
            job_id,
            reason=reason,
        )
        return self._result(context, job)

    def _run(self, context: TenantContext, job: ProcessingJob) -> WorkflowResult:
        lease_owner = new_id("worker")
        if self.store.job_cancellation_requested(context, job.job_id):
            # A RUNNING job may still own an exact provider-effect lease.  A
            # different resumer cannot discard it merely because cancellation
            # was requested; the lease owner performs the atomic terminal
            # transition after publishing any already-won receipt.
            return self._result(
                context,
                self.store.get_job(context, job.job_id, write=True),
            )
        try:
            job = self.store.claim_job(
                context,
                job.job_id,
                owner_token=lease_owner,
                stage="asset-processing",
                lease_seconds=self.JOB_LEASE_SECONDS,
            )
        except ConflictError as error:
            if error.code != "PROCESSING_JOB_ATTEMPT_LIMIT":
                raise
            job, _session = self.store.finalize_job_and_session(
                context,
                job.job_id,
                session_status=SessionStatus.FAILED,
                status=JobStatus.FAILED,
                stage="attempt-limit",
                result_status=ResultStatus.FAILED,
                failure_code=error.code,
            )
            return self._result(context, job)
        if job.status in self.TERMINAL_JOBS:
            return self._result(context, job)
        session = self.store.get_session(context, job.session_id, write=True)
        if session.status is SessionStatus.CANCELLED:
            job, _session = self.store.finalize_job_and_session(
                context,
                job.job_id,
                session_status=SessionStatus.CANCELLED,
                status=JobStatus.CANCELLED,
                stage="cancelled",
                result_status=ResultStatus.BLOCKED,
                failure_code="INPUT_SESSION_CANCELLED",
                lease_owner=lease_owner,
            )
            return self._result(context, job)
        self.store.update_session_status(context, job.session_id, SessionStatus.PROCESSING)
        assets = self.store.list_assets(context, job.session_id)
        reports: dict[str, ParseReport] = {}
        try:
            for asset in assets:
                self._raise_if_cancellation_requested(context, job.job_id, lease_owner)
                job = self.store.renew_job_lease(
                    context,
                    job.job_id,
                    owner_token=lease_owner,
                    lease_seconds=self.JOB_LEASE_SECONDS,
                )
                reports[asset.asset_id] = self._process_asset(context, job, asset, lease_owner)
                if reports[asset.asset_id].error_code == self.EXTERNAL_EFFECT_RECONCILIATION_CODE:
                    # The asset helper durably terminalized the job.  Do not run
                    # another paid/provider effect or overwrite the reconciliation
                    # state with aggregate status.
                    return self._result(context, self.store.get_job(context, job.job_id, write=True))
            self._raise_if_cancellation_requested(context, job.job_id, lease_owner)
        except _WorkflowCancellation:
            return self._result(
                context,
                self.store.get_job(context, job.job_id, write=True),
            )
        except ConflictError as error:
            if error.code != "PROCESSING_JOB_CANCELLATION_REQUESTED":
                raise
            return self._complete_job_cancellation(context, job.job_id, lease_owner)
        refreshed = self.store.list_assets(context, job.session_id)
        session_status, job_status, result_status, failure_code = self._aggregate(refreshed)
        job, session = self.store.finalize_job_and_session(
            context,
            job.job_id,
            session_status=session_status,
            status=job_status,
            stage="completed",
            result_status=result_status,
            failure_code=failure_code,
            lease_owner=lease_owner,
        )
        return WorkflowResult(job=job, session=session, assets=tuple(refreshed), reports=reports)

    def _process_asset(
        self,
        context: TenantContext,
        job: ProcessingJob,
        asset: InputAsset,
        lease_owner: str,
    ) -> ParseReport:
        if asset.status is AssetStatus.UPLOADING:
            return ParseReport(
                parser="upload-gate",
                status=ResultStatus.NOT_RUN,
                blocks=(),
                warnings=("ASSET_UPLOAD_INCOMPLETE",),
                error_code="ASSET_UPLOAD_INCOMPLETE",
            )
        if asset.status in {AssetStatus.READY, AssetStatus.NEEDS_REVIEW, AssetStatus.QUARANTINED, AssetStatus.FAILED}:
            return self._report_from_asset(context, asset)
        if asset.status not in {AssetStatus.UPLOADED, AssetStatus.PROCESSING} or not asset.sha256 or not asset.cas_digest:
            self.store.set_asset_result(
                context,
                asset.asset_id,
                status=AssetStatus.FAILED,
                failure_code="ASSET_NOT_PROCESSABLE",
            )
            return ParseReport(
                parser="workflow-gate",
                status=ResultStatus.FAILED,
                blocks=(),
                error_code="ASSET_NOT_PROCESSABLE",
            )
        checkpoint_key = f"asset:{asset.asset_id}:{asset.sha256}:processed-v1"
        if self.store.checkpoint_exists(context, job.job_id, checkpoint_key):
            return self._report_from_asset(context, self.store.get_asset(context, asset.asset_id))
        working_asset = asset
        external_effect_started = False
        external_effect_stage: str | None = None
        observed_kind = asset.kind
        observed_media_type = asset.detected_media_type or asset.declared_media_type
        observed_decision = asset.security_decision or SecurityDecision.NEEDS_REVIEW
        try:
            if asset.sha256 != asset.cas_digest:
                raise IntegrityError("ASSET_CAS_DIGEST_BINDING_MISMATCH")
            data = self.cas.read_bytes(
                context.tenant_id,
                asset.cas_digest,
                maximum_bytes=maximum_bytes_for_media_type(asset.declared_media_type),
                expected_size=asset.byte_size,
            )
            passive = self.inspector.inspect(asset, data)
            observed_kind = passive.kind
            observed_media_type = passive.media_type
            observed_decision = passive.decision
            if passive.decision is SecurityDecision.QUARANTINE:
                detection = passive
                malware_clearance_granted = False
                malware_clearance_reason = "PASSIVE_OR_SCANNER_QUARANTINE"
                malware_metadata = {
                    "status": ResultStatus.NOT_RUN.value,
                    "verdict": "PASSIVE_QUARANTINE",
                    "error_code": "PASSIVE_SECURITY_GATE_BLOCKED",
                    "receipt": {},
                    "clearance_granted": malware_clearance_granted,
                    "clearance_reason": malware_clearance_reason,
                }
            else:
                if self._provider_configured(ToolCapability.MALWARE_SCAN):
                    self._raise_if_cancellation_requested(context, job.job_id, lease_owner)
                    external_effect_stage = "malware-scan"
                    self._mark_external_effect_stage(context, job, lease_owner, asset, "malware-scan")
                    external_effect_started = True
                if external_effect_started:
                    scan = self._run_durable_malware_scan(
                        context,
                        job,
                        asset,
                        lease_owner,
                        data=data,
                        media_type=passive.media_type,
                    )
                else:
                    scan = self.providers.run(
                        ToolCapability.MALWARE_SCAN,
                        data,
                        passive.media_type,
                        job_id=job.job_id,
                        stage=f"asset:{asset.asset_id}:malware-scan",
                    )
                self._raise_if_cancellation_requested(context, job.job_id, lease_owner)
                if external_effect_started and self._provider_effect_is_ambiguous(
                    scan.error_code,
                    scan.receipt,
                ):
                    return self._block_for_external_effect_reconciliation(
                        context,
                        job,
                        lease_owner,
                        working_asset,
                        checkpoint_key,
                        stage=external_effect_stage or "malware-scan",
                        kind=observed_kind,
                        detected_media_type=observed_media_type,
                        security_decision=observed_decision,
                    )
                if external_effect_started:
                    # Only the completed, fenced effect receipt above closes
                    # scanner intent.  A crash after this point can replay that
                    # durable outcome and therefore never calls the scanner a
                    # second time.  Any later parser/provider effect gets its
                    # own reconciliation boundary.
                    self._clear_external_effect_stage(context, job, lease_owner)
                    external_effect_started = False
                    external_effect_stage = None
                detection, verdict, scan_findings = apply_malware_scan(passive, scan)
                malware_clearance_granted, malware_clearance_reason = validate_malware_clearance(
                    detection,
                    scan,
                    verdict,
                    data,
                )
                observed_kind = detection.kind
                observed_media_type = detection.media_type
                observed_decision = detection.decision
                malware_metadata = {
                    "status": scan.status.value,
                    "verdict": verdict,
                    "error_code": scan.error_code,
                    "findings": list(scan_findings),
                    "receipt": dict(scan.receipt),
                    "sandbox_required": True,
                    "network_allowed": False,
                    "clearance_granted": malware_clearance_granted,
                    "clearance_reason": malware_clearance_reason,
                }
            if detection.decision is SecurityDecision.QUARANTINE:
                report = ParseReport(
                    parser="security-gate",
                    status=ResultStatus.BLOCKED,
                    blocks=(),
                    warnings=detection.findings,
                    error_code="ASSET_QUARANTINED",
                    metadata={"malware_scan": malware_metadata},
                )
                self.store.renew_job_lease(
                    context,
                    job.job_id,
                    owner_token=lease_owner,
                    lease_seconds=self.JOB_LEASE_SECONDS,
                )
                updated, report_digest = self.store.finalize_asset_processing(
                    context,
                    human_review_source_capability=self._human_review_source_capability,
                    job_id=job.job_id,
                    lease_owner=lease_owner,
                    asset=asset,
                    report=report,
                    status=AssetStatus.QUARANTINED,
                    kind=detection.kind,
                    detected_media_type=detection.media_type,
                    security_decision=detection.decision,
                    failure_code=detection.findings[0] if detection.findings else "SECURITY_QUARANTINE",
                    finding_codes=detection.findings,
                )
                self.cas.quarantine_object(
                    context.tenant_id,
                    asset.cas_digest,
                    detection.findings[0] if detection.findings else "SECURITY_QUARANTINE",
                )
                self._checkpoint(context, job, checkpoint_key, updated, report, report_digest)
                if external_effect_started:
                    self._clear_external_effect_stage(context, job, lease_owner)
                return report
            if requires_malware_clearance(detection.kind) and not malware_clearance_granted:
                report = ParseReport(
                    parser="malware-clearance-gate",
                    status=ResultStatus.NEEDS_REVIEW,
                    blocks=(),
                    warnings=tuple(
                        sorted(set(detection.findings + (malware_clearance_reason,)))
                    ),
                    error_code="MALWARE_CLEARANCE_REQUIRED",
                    metadata={"malware_scan": malware_metadata},
                )
                self.store.renew_job_lease(
                    context,
                    job.job_id,
                    owner_token=lease_owner,
                    lease_seconds=self.JOB_LEASE_SECONDS,
                )
                updated, report_digest = self.store.finalize_asset_processing(
                    context,
                    human_review_source_capability=self._human_review_source_capability,
                    job_id=job.job_id,
                    lease_owner=lease_owner,
                    asset=asset,
                    report=report,
                    status=AssetStatus.NEEDS_REVIEW,
                    kind=detection.kind,
                    detected_media_type=detection.media_type,
                    security_decision=SecurityDecision.NEEDS_REVIEW,
                    failure_code=report.error_code,
                    finding_codes=tuple(detection.findings)
                    + ("MALWARE_CLEARANCE_REQUIRED", malware_clearance_reason),
                )
                self._checkpoint(context, job, checkpoint_key, updated, report, report_digest)
                if external_effect_started:
                    self._clear_external_effect_stage(context, job, lease_owner)
                return report
            processing = self.store.set_asset_result(
                context,
                asset.asset_id,
                status=AssetStatus.PROCESSING,
                kind=detection.kind,
                detected_media_type=detection.media_type,
                security_decision=detection.decision,
                expected_version=asset.version,
                job_id=job.job_id,
                lease_owner=lease_owner,
            )
            working_asset = processing
            parser_capability = self._external_parser_capability(processing)
            provider_result: ProviderResult | None = None
            if parser_capability is not None and self._provider_configured(parser_capability):
                self._raise_if_cancellation_requested(context, job.job_id, lease_owner)
                external_effect_stage = parser_capability.value.lower()
                self._mark_external_effect_stage(
                    context,
                    job,
                    lease_owner,
                    asset,
                    parser_capability.value.lower(),
                )
                external_effect_started = True
                provider_result = self._run_durable_parser_effect(
                    context,
                    job,
                    processing,
                    lease_owner,
                    capability=parser_capability,
                    data=data,
                    media_type=detection.media_type,
                )
                self._raise_if_cancellation_requested(context, job.job_id, lease_owner)
            report = self.parsers.parse(
                processing,
                data,
                detection,
                job_id=job.job_id,
                stage=f"asset:{asset.asset_id}:parse",
                provider_result=provider_result,
            )
            self._raise_if_cancellation_requested(context, job.job_id, lease_owner)
            if (
                parser_capability is not None
                and self._provider_configured(parser_capability)
                and self._provider_effect_is_ambiguous(report.error_code, report.provider_receipt)
            ):
                return self._block_for_external_effect_reconciliation(
                    context,
                    job,
                    lease_owner,
                    processing,
                    checkpoint_key,
                    stage=external_effect_stage or parser_capability.value.lower(),
                    kind=observed_kind,
                    detected_media_type=observed_media_type,
                    security_decision=observed_decision,
                )
            metadata = dict(report.metadata)
            metadata["malware_scan"] = malware_metadata
            if detection.decision is SecurityDecision.NEEDS_REVIEW and report.status is ResultStatus.PASSED:
                report = ParseReport(
                    parser=report.parser,
                    status=ResultStatus.NEEDS_REVIEW,
                    blocks=report.blocks,
                    warnings=tuple(sorted(set(report.warnings + detection.findings))),
                    error_code="SECURITY_REVIEW_REQUIRED",
                    provider_receipt=report.provider_receipt,
                    metadata=metadata,
                )
            elif metadata != dict(report.metadata):
                report = ParseReport(
                    parser=report.parser,
                    status=report.status,
                    blocks=report.blocks,
                    warnings=report.warnings,
                    error_code=report.error_code,
                    provider_receipt=report.provider_receipt,
                    metadata=metadata,
                )
            decision: SecurityDecision
            if report.status is ResultStatus.PASSED:
                status = AssetStatus.READY
                decision = detection.decision
            elif report.status in {ResultStatus.PARTIAL, ResultStatus.NEEDS_REVIEW, ResultStatus.NOT_RUN}:
                status = AssetStatus.NEEDS_REVIEW
                decision = SecurityDecision.NEEDS_REVIEW
            elif report.status is ResultStatus.BLOCKED:
                status = AssetStatus.QUARANTINED
                decision = SecurityDecision.QUARANTINE
            else:
                status = AssetStatus.FAILED
                decision = detection.decision
            self.store.renew_job_lease(
                context,
                job.job_id,
                owner_token=lease_owner,
                lease_seconds=self.JOB_LEASE_SECONDS,
            )
            updated, report_digest = self.store.finalize_asset_processing(
                context,
                human_review_source_capability=self._human_review_source_capability,
                job_id=job.job_id,
                lease_owner=lease_owner,
                asset=processing,
                report=report,
                status=status,
                kind=detection.kind,
                detected_media_type=detection.media_type,
                security_decision=decision,
                failure_code=report.error_code,
                finding_codes=tuple(detection.findings)
                + (
                    (report.error_code or "PARSER_SECURITY_BLOCK",)
                    if status is AssetStatus.QUARANTINED
                    else ()
                ),
            )
            if status is AssetStatus.QUARANTINED:
                self.cas.quarantine_object(
                    context.tenant_id,
                    asset.cas_digest,
                    report.error_code or "PARSER_SECURITY_BLOCK",
                )
            self._checkpoint(context, job, checkpoint_key, updated, report, report_digest)
            if external_effect_started:
                self._clear_external_effect_stage(context, job, lease_owner)
            return report
        except _WorkflowCancellation:
            raise
        except ConflictError:
            raise
        except IntegrityError as error:
            if external_effect_started:
                return self._block_for_external_effect_reconciliation(
                    context,
                    job,
                    lease_owner,
                    working_asset,
                    checkpoint_key,
                    stage=external_effect_stage or "unknown",
                    kind=observed_kind,
                    detected_media_type=observed_media_type,
                    security_decision=observed_decision,
                )
            report = ParseReport(
                parser="cas-integrity-gate",
                status=ResultStatus.BLOCKED,
                blocks=(),
                error_code=error.code,
            )
            self.store.renew_job_lease(
                context,
                job.job_id,
                owner_token=lease_owner,
                lease_seconds=self.JOB_LEASE_SECONDS,
            )
            updated, report_digest = self.store.finalize_asset_processing(
                context,
                human_review_source_capability=self._human_review_source_capability,
                job_id=job.job_id,
                lease_owner=lease_owner,
                asset=working_asset,
                report=report,
                status=AssetStatus.QUARANTINED,
                kind=working_asset.kind,
                detected_media_type=working_asset.detected_media_type or working_asset.declared_media_type,
                security_decision=SecurityDecision.QUARANTINE,
                failure_code=error.code,
                finding_codes=(error.code,),
            )
            self._checkpoint(context, job, checkpoint_key, updated, report, report_digest)
            if external_effect_started:
                self._clear_external_effect_stage(context, job, lease_owner)
            return report
        except IntakeError as error:
            if external_effect_started:
                return self._block_for_external_effect_reconciliation(
                    context,
                    job,
                    lease_owner,
                    working_asset,
                    checkpoint_key,
                    stage=external_effect_stage or "unknown",
                    kind=observed_kind,
                    detected_media_type=observed_media_type,
                    security_decision=observed_decision,
                )
            report = ParseReport(
                parser="workflow-error",
                status=ResultStatus.FAILED,
                blocks=(),
                error_code=error.code,
            )
            self.store.renew_job_lease(
                context,
                job.job_id,
                owner_token=lease_owner,
                lease_seconds=self.JOB_LEASE_SECONDS,
            )
            updated, report_digest = self.store.finalize_asset_processing(
                context,
                human_review_source_capability=self._human_review_source_capability,
                job_id=job.job_id,
                lease_owner=lease_owner,
                asset=working_asset,
                report=report,
                status=AssetStatus.FAILED,
                kind=working_asset.kind,
                detected_media_type=working_asset.detected_media_type or working_asset.declared_media_type,
                security_decision=working_asset.security_decision or SecurityDecision.NEEDS_REVIEW,
                failure_code=error.code,
            )
            self._checkpoint(context, job, checkpoint_key, updated, report, report_digest)
            if external_effect_started:
                self._clear_external_effect_stage(context, job, lease_owner)
            return report
        except Exception:
            if external_effect_started:
                return self._block_for_external_effect_reconciliation(
                    context,
                    job,
                    lease_owner,
                    working_asset,
                    checkpoint_key,
                    stage=external_effect_stage or "unknown",
                    kind=observed_kind,
                    detected_media_type=observed_media_type,
                    security_decision=observed_decision,
                )
            report = ParseReport(
                parser="workflow-error",
                status=ResultStatus.FAILED,
                blocks=(),
                error_code="UNEXPECTED_ASSET_PROCESSING_FAILURE",
            )
            self.store.renew_job_lease(
                context,
                job.job_id,
                owner_token=lease_owner,
                lease_seconds=self.JOB_LEASE_SECONDS,
            )
            updated, report_digest = self.store.finalize_asset_processing(
                context,
                human_review_source_capability=self._human_review_source_capability,
                job_id=job.job_id,
                lease_owner=lease_owner,
                asset=working_asset,
                report=report,
                status=AssetStatus.FAILED,
                kind=working_asset.kind,
                detected_media_type=working_asset.detected_media_type or working_asset.declared_media_type,
                security_decision=working_asset.security_decision or SecurityDecision.NEEDS_REVIEW,
                failure_code="UNEXPECTED_ASSET_PROCESSING_FAILURE",
            )
            self._checkpoint(context, job, checkpoint_key, updated, report, report_digest)
            if external_effect_started:
                self._clear_external_effect_stage(context, job, lease_owner)
            return report

    def _complete_job_cancellation(
        self,
        context: TenantContext,
        job_id: str,
        lease_owner: str | None,
    ) -> WorkflowResult:
        job = self.store.get_job(context, job_id, write=True)
        if job.status is JobStatus.CANCELLED:
            return self._result(context, job)
        if job.status in self.TERMINAL_JOBS:
            return self._result(context, job)
        job, _session = self.store.finalize_job_and_session(
            context,
            job.job_id,
            session_status=SessionStatus.CANCELLED,
            status=JobStatus.CANCELLED,
            stage="cancelled",
            result_status=ResultStatus.BLOCKED,
            failure_code="CANCELLED_BY_CALLER",
            lease_owner=lease_owner,
        )
        return self._result(context, job)

    def _raise_if_cancellation_requested(
        self,
        context: TenantContext,
        job_id: str,
        lease_owner: str,
    ) -> None:
        if not self.store.job_cancellation_requested(context, job_id):
            return
        self._complete_job_cancellation(context, job_id, lease_owner)
        raise _WorkflowCancellation

    def _mark_external_effect_stage(
        self,
        context: TenantContext,
        job: ProcessingJob,
        lease_owner: str,
        asset: InputAsset,
        stage: str,
    ) -> None:
        # Refresh before publishing the intent marker.  A crash after the marker
        # but before a trustworthy completion receipt is deliberately recovered
        # as reconciliation-required by IntakeStore.claim_job.
        self.store.renew_job_lease(
            context,
            job.job_id,
            owner_token=lease_owner,
            lease_seconds=self.JOB_LEASE_SECONDS,
        )
        self.store.update_job(
            context,
            job.job_id,
            status=JobStatus.RUNNING,
            stage=f"external-effect:{asset.asset_id}:{stage}",
            result_status=ResultStatus.NOT_RUN,
            lease_owner=lease_owner,
        )

    def _run_durable_malware_scan(
        self,
        context: TenantContext,
        job: ProcessingJob,
        asset: InputAsset,
        lease_owner: str,
        *,
        data: bytes,
        media_type: str,
    ) -> ProviderResult:
        """Execute a scanner effect once behind the existing durable fence.

        The processing-job stage remains ``external-effect:*`` until the exact
        ProviderResult has been completed in ``skill_execution_receipts``.  A
        later asset-processing retry replays that result, while an execution
        with no durable outcome remains reconciliation-required.
        """

        stage = f"asset:{asset.asset_id}:malware-scan"
        effect_stage_key = self.store.job_effect_stage_key(
            job.job_id,
            f"external-effect:{asset.asset_id}:malware-scan",
        )
        policy_digest = self.providers.invocation_policy_digest(ToolCapability.MALWARE_SCAN)
        binding = {
            "schema_version": self.MALWARE_EFFECT_SCHEMA,
            "job_id": job.job_id,
            "asset_id": asset.asset_id,
            "source_sha256": asset.sha256,
            "input_sha256": hashlib.sha256(data).hexdigest(),
            "input_bytes": len(data),
            "media_type": media_type,
            "stage": stage,
            "provider_policy_digest": policy_digest,
        }
        request_digest = canonical_digest(binding)
        # Keep the fence identity stable across input/provider drift so reuse
        # conflicts instead of silently creating a second paid effect.
        effect_identity_digest = canonical_digest(
            {
                "schema_version": self.MALWARE_EFFECT_SCHEMA,
                "job_id": job.job_id,
                "asset_id": asset.asset_id,
                "stage": stage,
            }
        )
        idempotency_key = f"malware-scan:{effect_identity_digest}"
        job_effect_receipt = self.store.load_job_effect_receipt(
            context,
            job.job_id,
            effect_stage_key,
            lease_owner=lease_owner,
        )
        if job_effect_receipt is not None:
            return self._malware_result_from_effect_receipt(
                200,
                job_effect_receipt,
                request_digest=request_digest,
                policy_digest=policy_digest,
            )
        claim_state, replay = self.store.claim_skill_execution(
            context,
            skill=self.MALWARE_EFFECT_SKILL,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            owner_token=lease_owner,
            lease_seconds=self.JOB_LEASE_SECONDS,
        )
        if claim_state == "REPLAY":
            if replay is None:
                raise IntegrityError("MALWARE_SCAN_EFFECT_RECEIPT_CORRUPT")
            status, response = replay
            restored = self._malware_result_from_effect_receipt(
                status,
                response,
                request_digest=request_digest,
                policy_digest=policy_digest,
            )
            self.store.save_job_effect_receipt(
                context,
                job.job_id,
                effect_stage_key,
                response,
                lease_owner=lease_owner,
            )
            return restored
        if claim_state == "RECONCILIATION_REQUIRED":
            # A v9-upgraded or previously dispatched effect has an unknown
            # outcome.  Keep the job's external-effect stage intact so neither
            # this actor nor a different authorized writer can call it again.
            raise ConflictError(
                self.EXTERNAL_EFFECT_RECONCILIATION_CODE,
                retryable=False,
            )
        if claim_state != "CLAIMED":
            raise ConflictError(
                "MALWARE_SCAN_EFFECT_IN_PROGRESS",
                retryable=True,
            )

        # Fence the uncertain provider boundary before the first external byte
        # is dispatched.  A crash or lost provider response after this commit
        # is reconciliation-only and can never become lease-expiry authority
        # for a second scanner invocation.
        self.store.mark_skill_execution_dispatched(
            context,
            skill=self.MALWARE_EFFECT_SKILL,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            owner_token=lease_owner,
            job_id=job.job_id,
        )
        scan = self.providers.run(
            ToolCapability.MALWARE_SCAN,
            data,
            media_type,
            job_id=job.job_id,
            stage=stage,
        )
        if self._provider_effect_is_ambiguous(scan.error_code, scan.receipt):
            # Do not manufacture a completed effect receipt when the sandbox
            # cannot prove whether execution occurred.  The live job intent
            # deliberately remains in external-effect reconciliation state.
            return scan
        if (
            scan.capability is not ToolCapability.MALWARE_SCAN
            or (
                scan.status is ResultStatus.PASSED
                and not self.providers.verify_issued_result(scan)
            )
        ):
            scan = ProviderResult(
                status=ResultStatus.FAILED,
                capability=ToolCapability.MALWARE_SCAN,
                error_code="SANDBOX_RECEIPT_INVALID",
            )
        result_body = {
            "status": scan.status.value,
            "capability": scan.capability.value,
            "payload": dict(scan.payload),
            "error_code": scan.error_code,
            "warnings": list(scan.warnings),
            "receipt": dict(scan.receipt),
        }
        response = {
            "schema_version": self.MALWARE_EFFECT_SCHEMA,
            "request_digest": request_digest,
            "provider_policy_digest": policy_digest,
            "result": result_body,
            "result_digest": canonical_digest(result_body),
        }
        # The job-owned checkpoint is the cross-actor recovery authority.  It
        # must commit before the actor-scoped inner receipt, otherwise a crash
        # after inner completion can strand the job as permanently ambiguous.
        restored = self._malware_result_from_effect_receipt(
            200,
            response,
            request_digest=request_digest,
            policy_digest=policy_digest,
        )
        self.store.save_job_effect_receipt(
            context,
            job.job_id,
            effect_stage_key,
            response,
            lease_owner=lease_owner,
        )
        try:
            persisted_status, persisted = self.store.complete_skill_execution(
                context,
                skill=self.MALWARE_EFFECT_SKILL,
                idempotency_key=idempotency_key,
                request_digest=request_digest,
                owner_token=lease_owner,
                http_status=200,
                response=response,
            )
        except Exception:
            # The exact job checkpoint already closed the external-effect
            # ambiguity.  A recoverable inner-receipt storage error must not
            # convert that proven result into a permanent BLOCKED job.  A real
            # process crash (BaseException) still propagates and exercises the
            # same checkpoint-led cross-actor recovery path.
            return restored
        persisted_result = self._malware_result_from_effect_receipt(
            persisted_status,
            persisted,
            request_digest=request_digest,
            policy_digest=policy_digest,
        )
        # If completion replayed anything other than the checkpointed response,
        # the immutable checkpoint detects it before returning provider data.
        self.store.save_job_effect_receipt(
            context,
            job.job_id,
            effect_stage_key,
            persisted,
            lease_owner=lease_owner,
        )
        return persisted_result

    def _malware_result_from_effect_receipt(
        self,
        http_status: int,
        response: Mapping[str, Any],
        *,
        request_digest: str,
        policy_digest: str,
    ) -> ProviderResult:
        """Validate and restore one exact scanner outcome from durable storage."""

        if http_status != 200 or set(response) != {
            "schema_version",
            "request_digest",
            "provider_policy_digest",
            "result",
            "result_digest",
        }:
            raise IntegrityError("MALWARE_SCAN_EFFECT_RECEIPT_CORRUPT")
        raw_request_digest = response.get("request_digest")
        raw_policy_digest = response.get("provider_policy_digest")
        raw_result_digest = response.get("result_digest")
        if (
            not isinstance(raw_request_digest, str)
            or not isinstance(raw_policy_digest, str)
            or not isinstance(raw_result_digest, str)
        ):
            raise IntegrityError("MALWARE_SCAN_EFFECT_RECEIPT_CORRUPT")
        try:
            stored_request_digest = normalize_sha256(raw_request_digest)
            stored_policy_digest = normalize_sha256(raw_policy_digest)
            stored_result_digest = normalize_sha256(raw_result_digest)
        except Exception as error:
            raise IntegrityError("MALWARE_SCAN_EFFECT_RECEIPT_CORRUPT") from error
        if (
            not hmac.compare_digest(stored_request_digest, request_digest)
            or not hmac.compare_digest(stored_policy_digest, policy_digest)
            or response.get("schema_version") != self.MALWARE_EFFECT_SCHEMA
        ):
            raise IntegrityError("MALWARE_SCAN_EFFECT_RECEIPT_CORRUPT")
        raw_result = response.get("result")
        if not isinstance(raw_result, Mapping) or set(raw_result) != {
            "status",
            "capability",
            "payload",
            "error_code",
            "warnings",
            "receipt",
        }:
            raise IntegrityError("MALWARE_SCAN_EFFECT_RECEIPT_CORRUPT")
        try:
            if not hmac.compare_digest(canonical_digest(dict(raw_result)), stored_result_digest):
                raise IntegrityError("MALWARE_SCAN_EFFECT_RECEIPT_CORRUPT")
            raw_status = raw_result.get("status")
            if not isinstance(raw_status, str):
                raise IntegrityError("MALWARE_SCAN_EFFECT_RECEIPT_CORRUPT")
            status = ResultStatus(raw_status)
        except Exception as error:
            raise IntegrityError("MALWARE_SCAN_EFFECT_RECEIPT_CORRUPT") from error
        payload = raw_result.get("payload")
        receipt = raw_result.get("receipt")
        warnings = raw_result.get("warnings")
        error_code = raw_result.get("error_code")
        if (
            raw_result.get("capability") != ToolCapability.MALWARE_SCAN.value
            or not isinstance(payload, Mapping)
            or not isinstance(receipt, Mapping)
            or not isinstance(warnings, list)
            or len(warnings) > 1024
            or any(not isinstance(warning, str) for warning in warnings)
            or (error_code is not None and not isinstance(error_code, str))
        ):
            raise IntegrityError("MALWARE_SCAN_EFFECT_RECEIPT_CORRUPT")
        return ProviderResult(
            status=status,
            capability=ToolCapability.MALWARE_SCAN,
            payload=dict(payload),
            error_code=error_code,
            warnings=tuple(warnings),
            receipt=dict(receipt),
        )

    def _run_durable_parser_effect(
        self,
        context: TenantContext,
        job: ProcessingJob,
        asset: InputAsset,
        lease_owner: str,
        *,
        capability: ToolCapability,
        data: bytes,
        media_type: str,
    ) -> ProviderResult:
        """Execute one parser provider effect behind an immutable durable fence."""

        suffixes = {
            ToolCapability.PDF_TEXT: "pdf-text",
            ToolCapability.OCR: "ocr",
            ToolCapability.ASR: "asr",
            ToolCapability.WORD_DOC_CONVERT: "word-convert",
        }
        suffix = suffixes.get(capability)
        if suffix is None:
            raise IntegrityError("PARSER_PROVIDER_CAPABILITY_INVALID")
        stage = f"asset:{asset.asset_id}:parse:{suffix}"
        effect_name = capability.value.lower()
        effect_stage_key = self.store.job_effect_stage_key(
            job.job_id,
            f"external-effect:{asset.asset_id}:{effect_name}",
        )
        policy_digest = self.providers.invocation_policy_digest(capability)
        binding = {
            "schema_version": self.PARSER_EFFECT_SCHEMA,
            "job_id": job.job_id,
            "asset_id": asset.asset_id,
            "source_sha256": asset.sha256,
            "input_sha256": hashlib.sha256(data).hexdigest(),
            "input_bytes": len(data),
            "media_type": media_type,
            "stage": stage,
            "capability": capability.value,
            "provider_policy_digest": policy_digest,
        }
        request_digest = canonical_digest(binding)
        effect_identity_digest = canonical_digest(
            {
                "schema_version": self.PARSER_EFFECT_SCHEMA,
                "job_id": job.job_id,
                "asset_id": asset.asset_id,
                "stage": stage,
                "capability": capability.value,
            }
        )
        idempotency_key = f"parser-effect:{effect_identity_digest}"
        job_effect_receipt = self.store.load_job_effect_receipt(
            context,
            job.job_id,
            effect_stage_key,
            lease_owner=lease_owner,
        )
        if job_effect_receipt is not None:
            return self._parser_result_from_effect_receipt(
                200,
                job_effect_receipt,
                request_digest=request_digest,
                policy_digest=policy_digest,
                capability=capability,
            )
        claim_state, replay = self.store.claim_skill_execution(
            context,
            skill=self.PARSER_EFFECT_SKILL,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            owner_token=lease_owner,
            lease_seconds=self.JOB_LEASE_SECONDS,
        )
        if claim_state == "REPLAY":
            if replay is None:
                raise IntegrityError("PARSER_PROVIDER_EFFECT_RECEIPT_CORRUPT")
            status, response = replay
            restored = self._parser_result_from_effect_receipt(
                status,
                response,
                request_digest=request_digest,
                policy_digest=policy_digest,
                capability=capability,
            )
            self.store.save_job_effect_receipt(
                context,
                job.job_id,
                effect_stage_key,
                response,
                lease_owner=lease_owner,
            )
            return restored
        if claim_state == "RECONCILIATION_REQUIRED":
            raise ConflictError(
                self.EXTERNAL_EFFECT_RECONCILIATION_CODE,
                retryable=False,
            )
        if claim_state != "CLAIMED":
            raise ConflictError("PARSER_PROVIDER_EFFECT_IN_PROGRESS", retryable=True)

        self.store.mark_skill_execution_dispatched(
            context,
            skill=self.PARSER_EFFECT_SKILL,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            owner_token=lease_owner,
            job_id=job.job_id,
        )
        result = self.providers.run(
            capability,
            data,
            media_type,
            job_id=job.job_id,
            stage=stage,
        )
        if self._provider_effect_is_ambiguous(result.error_code, result.receipt):
            return result
        if (
            result.capability is not capability
            or (
                result.status is ResultStatus.PASSED
                and not self.providers.verify_issued_result(result)
            )
        ):
            result = ProviderResult(
                status=ResultStatus.FAILED,
                capability=capability,
                error_code="SANDBOX_RECEIPT_INVALID",
            )
        result_body = {
            "status": result.status.value,
            "capability": result.capability.value,
            "payload": dict(result.payload),
            "error_code": result.error_code,
            "warnings": list(result.warnings),
            "receipt": dict(result.receipt),
        }
        response = {
            "schema_version": self.PARSER_EFFECT_SCHEMA,
            "request_digest": request_digest,
            "provider_policy_digest": policy_digest,
            "result": result_body,
            "result_digest": canonical_digest(result_body),
        }
        restored = self._parser_result_from_effect_receipt(
            200,
            response,
            request_digest=request_digest,
            policy_digest=policy_digest,
            capability=capability,
        )
        self.store.save_job_effect_receipt(
            context,
            job.job_id,
            effect_stage_key,
            response,
            lease_owner=lease_owner,
        )
        try:
            persisted_status, persisted = self.store.complete_skill_execution(
                context,
                skill=self.PARSER_EFFECT_SKILL,
                idempotency_key=idempotency_key,
                request_digest=request_digest,
                owner_token=lease_owner,
                http_status=200,
                response=response,
            )
        except Exception:
            return restored
        persisted_result = self._parser_result_from_effect_receipt(
            persisted_status,
            persisted,
            request_digest=request_digest,
            policy_digest=policy_digest,
            capability=capability,
        )
        self.store.save_job_effect_receipt(
            context,
            job.job_id,
            effect_stage_key,
            persisted,
            lease_owner=lease_owner,
        )
        return persisted_result

    def _parser_result_from_effect_receipt(
        self,
        http_status: int,
        response: Mapping[str, Any],
        *,
        request_digest: str,
        policy_digest: str,
        capability: ToolCapability,
    ) -> ProviderResult:
        """Validate and restore one exact parser provider outcome."""

        corrupt = "PARSER_PROVIDER_EFFECT_RECEIPT_CORRUPT"
        if http_status != 200 or set(response) != {
            "schema_version",
            "request_digest",
            "provider_policy_digest",
            "result",
            "result_digest",
        }:
            raise IntegrityError(corrupt)
        raw_request_digest = response.get("request_digest")
        raw_policy_digest = response.get("provider_policy_digest")
        raw_result_digest = response.get("result_digest")
        if (
            not isinstance(raw_request_digest, str)
            or not isinstance(raw_policy_digest, str)
            or not isinstance(raw_result_digest, str)
        ):
            raise IntegrityError(corrupt)
        try:
            stored_request_digest = normalize_sha256(raw_request_digest)
            stored_policy_digest = normalize_sha256(raw_policy_digest)
            stored_result_digest = normalize_sha256(raw_result_digest)
        except Exception as error:
            raise IntegrityError(corrupt) from error
        if (
            response.get("schema_version") != self.PARSER_EFFECT_SCHEMA
            or not hmac.compare_digest(stored_request_digest, request_digest)
            or not hmac.compare_digest(stored_policy_digest, policy_digest)
        ):
            raise IntegrityError(corrupt)
        raw_result = response.get("result")
        if not isinstance(raw_result, Mapping) or set(raw_result) != {
            "status",
            "capability",
            "payload",
            "error_code",
            "warnings",
            "receipt",
        }:
            raise IntegrityError(corrupt)
        try:
            if not hmac.compare_digest(
                canonical_digest(dict(raw_result)),
                stored_result_digest,
            ):
                raise IntegrityError(corrupt)
            raw_status = raw_result.get("status")
            if not isinstance(raw_status, str):
                raise IntegrityError(corrupt)
            status = ResultStatus(raw_status)
        except Exception as error:
            raise IntegrityError(corrupt) from error
        payload = raw_result.get("payload")
        receipt = raw_result.get("receipt")
        warnings = raw_result.get("warnings")
        error_code = raw_result.get("error_code")
        if (
            raw_result.get("capability") != capability.value
            or not isinstance(payload, Mapping)
            or not isinstance(receipt, Mapping)
            or not isinstance(warnings, list)
            or len(warnings) > 1024
            or any(not isinstance(warning, str) for warning in warnings)
            or (error_code is not None and not isinstance(error_code, str))
        ):
            raise IntegrityError(corrupt)
        return ProviderResult(
            status=status,
            capability=capability,
            payload=dict(payload),
            error_code=error_code,
            warnings=tuple(warnings),
            receipt=dict(receipt),
        )

    @classmethod
    def _provider_effect_is_ambiguous(
        cls,
        error_code: str | None,
        receipt: object,
    ) -> bool:
        return error_code in cls.AMBIGUOUS_PROVIDER_FAILURES and not bool(receipt)

    def _block_for_external_effect_reconciliation(
        self,
        context: TenantContext,
        job: ProcessingJob,
        lease_owner: str,
        asset: InputAsset,
        checkpoint_key: str,
        *,
        stage: str,
        kind: AssetKind,
        detected_media_type: str,
        security_decision: SecurityDecision,
    ) -> ParseReport:
        """Persist ambiguity as terminal BLOCKED; never silently retry a paid effect."""

        code = self.EXTERNAL_EFFECT_RECONCILIATION_CODE
        report = ParseReport(
            parser="external-effect-reconciliation-v1",
            status=ResultStatus.BLOCKED,
            blocks=(),
            warnings=(code,),
            error_code=code,
            metadata={
                "reconciliation_state": "REQUIRED",
                "external_effect_stage": stage,
                "automatic_retry_allowed": False,
            },
        )
        self.store.renew_job_lease(
            context,
            job.job_id,
            owner_token=lease_owner,
            lease_seconds=self.JOB_LEASE_SECONDS,
        )
        updated, report_digest = self.store.finalize_asset_processing(
            context,
            human_review_source_capability=self._human_review_source_capability,
            job_id=job.job_id,
            lease_owner=lease_owner,
            asset=asset,
            report=report,
            status=AssetStatus.NEEDS_REVIEW,
            kind=kind,
            detected_media_type=detected_media_type,
            security_decision=security_decision,
            failure_code=code,
            finding_codes=(code,),
        )
        self._checkpoint(context, job, checkpoint_key, updated, report, report_digest)
        self.store.finalize_job_and_session(
            context,
            job.job_id,
            session_status=SessionStatus.NEEDS_REVIEW,
            status=JobStatus.BLOCKED,
            stage="external-effect-reconciliation-required",
            result_status=ResultStatus.BLOCKED,
            failure_code=code,
            lease_owner=lease_owner,
        )
        return report

    def _clear_external_effect_stage(
        self,
        context: TenantContext,
        job: ProcessingJob,
        lease_owner: str,
    ) -> None:
        self.store.update_job(
            context,
            job.job_id,
            status=JobStatus.RUNNING,
            stage="asset-processing",
            result_status=ResultStatus.NOT_RUN,
            lease_owner=lease_owner,
        )

    def _provider_configured(self, capability: ToolCapability) -> bool:
        return self.providers.executor is not None and capability in self.providers.provisioned_tools

    @staticmethod
    def _external_parser_capability(asset: InputAsset) -> ToolCapability | None:
        if asset.kind.value == "PDF":
            return ToolCapability.PDF_TEXT
        if asset.kind.value == "IMAGE":
            return ToolCapability.OCR
        if asset.kind.value == "AUDIO":
            return ToolCapability.ASR
        if asset.declared_media_type == "application/msword":
            return ToolCapability.WORD_DOC_CONVERT
        return None

    def _checkpoint(
        self,
        context: TenantContext,
        job: ProcessingJob,
        checkpoint_key: str,
        asset: InputAsset,
        report: ParseReport,
        report_digest: str,
    ) -> None:
        self.store.save_checkpoint(
            context,
            job.job_id,
            checkpoint_key,
            {
                "asset_id": asset.asset_id,
                "source_sha256": asset.sha256,
                "asset_status": asset.status.value,
                "parser": report.parser,
                "result_status": report.status.value,
                "block_ids": [block.block_id for block in report.blocks],
                "error_code": report.error_code,
                "asset_version": asset.version,
                "report_sha256": report_digest,
            },
        )

    def _result(self, context: TenantContext, job: ProcessingJob) -> WorkflowResult:
        session = self.store.get_session(context, job.session_id)
        assets = self.store.list_assets(context, job.session_id)
        reports = {asset.asset_id: self._report_from_asset(context, asset) for asset in assets}
        return WorkflowResult(job=job, session=session, assets=tuple(assets), reports=reports)

    def _report_from_asset(self, context: TenantContext, asset: InputAsset) -> ParseReport:
        persisted = self.store.load_asset_report(context, asset)
        if persisted is not None:
            return persisted
        blocks = tuple(self.store.content_blocks(context, asset.asset_id))
        if asset.status is AssetStatus.READY:
            status = ResultStatus.PASSED
        elif asset.status is AssetStatus.NEEDS_REVIEW:
            status = ResultStatus.NEEDS_REVIEW
        elif asset.status is AssetStatus.QUARANTINED:
            status = ResultStatus.BLOCKED
        elif asset.status is AssetStatus.FAILED:
            status = ResultStatus.FAILED
        else:
            status = ResultStatus.NOT_RUN
        return ParseReport(
            parser="persisted-v1",
            status=status,
            blocks=blocks,
            error_code=asset.failure_code,
        )

    @staticmethod
    def _aggregate(
        assets: list[InputAsset],
    ) -> tuple[SessionStatus, JobStatus, ResultStatus, str | None]:
        if not assets:
            return (
                SessionStatus.NEEDS_REVIEW,
                JobStatus.NEEDS_REVIEW,
                ResultStatus.NEEDS_REVIEW,
                "INPUT_SESSION_HAS_NO_ASSETS",
            )
        statuses = [asset.status for asset in assets]
        ready = statuses.count(AssetStatus.READY)
        if ready == len(statuses):
            return SessionStatus.READY, JobStatus.COMPLETED, ResultStatus.PASSED, None
        if ready:
            return SessionStatus.PARTIAL_READY, JobStatus.PARTIAL, ResultStatus.PARTIAL, "PARTIAL_ASSET_SUCCESS"
        if any(status in {AssetStatus.NEEDS_REVIEW, AssetStatus.UPLOADING} for status in statuses):
            return (
                SessionStatus.NEEDS_REVIEW,
                JobStatus.NEEDS_REVIEW,
                ResultStatus.NEEDS_REVIEW,
                "ASSET_REVIEW_REQUIRED",
            )
        if all(status is AssetStatus.QUARANTINED for status in statuses):
            return SessionStatus.QUARANTINED, JobStatus.BLOCKED, ResultStatus.BLOCKED, "ALL_ASSETS_QUARANTINED"
        return SessionStatus.FAILED, JobStatus.FAILED, ResultStatus.FAILED, "NO_ASSET_PROCESSED_SUCCESSFULLY"
