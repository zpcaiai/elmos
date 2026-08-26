"""Explicit, local-only jobs for trusted parity and cache-SLO services.

This module does not contain a daemon, a command runner, or an external
provider adapter.  Composition installs one exact trusted parity harness, its
closed runner registry, and one cache-SLO runtime registry.  A request may then
select only a registered runner/controller and stable job/report identifiers.

Every completed job produces a canonical source event and a canonical receipt
in CAS.  The receipt is bound to the authenticated scope and principal and is
replayed from durable idempotency state after restart.  These receipts are
local engineering evidence only: they can never exceed
``READY_FOR_EXTERNAL_GATE`` and never claim external execution or
certification.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, cast

from .canonical import digest_of, require_digest
from .db.store import IdempotencyClaim, MetadataStore
from .enums import ArtifactStorageState, ValidationLevel
from .errors import ContractViolation, CorruptObject, NotFound
from .parity import ParityDecision
from .parity_harness_service import (
    ParityHarnessRunRequest,
    TrustedParityHarnessService,
    TrustedParityRunnerRegistration,
    TrustedParityRunnerRegistry,
)
from .slo_service import CacheSloControlService, CacheSloRuntimeRegistry

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}$")
_SCHEMA_VERSION = "1.2.0"
_HARNESS_OPERATION = "cache-parity-local-harness-job/v1.2"
_SLO_OPERATION = "cache-parity-local-slo-reconcile-job/v1.2"
_EVENT_KIND = "elmos.cache-parity-local-job-source-event/v1.2"
_RECEIPT_KIND = "elmos.cache-parity-local-job-receipt/v1.2"

PARITY_JOB_REF_SOURCE_KIND = "cache-parity-local-job"
PARITY_JOB_DEPENDENCY_SOURCE_KIND = "cache-parity-local-job-dependency"


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(
            f"{field_name} must be a bounded identifier",
            field=field_name,
        )
    return value


def parity_job_ref_kind(project_id: str) -> str:
    """Return the project-qualified reference used for local job artifacts."""

    return f"project:{_identifier(project_id, 'project_id')}"


@dataclass(frozen=True, slots=True)
class ParityHarnessJobRequest:
    """Closed request surface for one registered trusted harness run."""

    tenant_id: str
    project_id: str
    job_id: str
    runner_id: str
    report_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "tenant_id",
            "project_id",
            "job_id",
            "runner_id",
            "report_id",
        ):
            _identifier(getattr(self, field_name), field_name)

    def to_dict(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "job_id": self.job_id,
            "runner_id": self.runner_id,
            "report_id": self.report_id,
        }


@dataclass(frozen=True, slots=True)
class SloReconcileJobRequest:
    """Closed request surface for one registered SLO reconciliation tick."""

    tenant_id: str
    project_id: str
    job_id: str
    controller_id: str

    def __post_init__(self) -> None:
        for field_name in ("tenant_id", "project_id", "job_id", "controller_id"):
            _identifier(getattr(self, field_name), field_name)

    def to_dict(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "job_id": self.job_id,
            "controller_id": self.controller_id,
        }


@dataclass(frozen=True, slots=True)
class ParityJobResult:
    """Verified content-addressed job receipt plus replay disposition."""

    receipt_digest: str
    receipt: Mapping[str, Any]
    replayed: bool = False

    def __post_init__(self) -> None:
        require_digest(self.receipt_digest)
        copied = dict(self.receipt)
        if digest_of(copied) != self.receipt_digest:
            raise ContractViolation("local parity job receipt digest is invalid")
        object.__setattr__(self, "receipt", MappingProxyType(copied))

    def to_dict(self) -> dict[str, Any]:
        return {
            **dict(self.receipt),
            "receipt_digest": self.receipt_digest,
            "idempotent_replay": self.replayed,
        }


class ParityJobService:
    """Run one explicitly selected server-owned job; never schedule a daemon."""

    def __init__(
        self,
        *,
        harness_service: TrustedParityHarnessService,
        runner_registry: TrustedParityRunnerRegistry,
        slo_runtime_registry: CacheSloRuntimeRegistry,
    ) -> None:
        if type(harness_service) is not TrustedParityHarnessService:
            raise ContractViolation("local parity jobs require the trusted harness service")
        if type(runner_registry) is not TrustedParityRunnerRegistry:
            raise ContractViolation("local parity jobs require the trusted runner registry")
        if type(slo_runtime_registry) is not CacheSloRuntimeRegistry:
            raise ContractViolation("local parity jobs require the cache SLO runtime registry")
        if harness_service.registry is not runner_registry:
            raise ContractViolation("trusted harness and runner registry composition differs")
        self.harness_service = harness_service
        self.runner_registry = runner_registry
        self.slo_runtime_registry = slo_runtime_registry
        self.store: MetadataStore = harness_service.store
        self.cas = harness_service.cas

    def authorize_harness(
        self,
        request: ParityHarnessJobRequest,
        *,
        authenticated_principal_digest: str,
    ) -> TrustedParityRunnerRegistration:
        """Resolve scope and trusted runner without taking a durable claim."""

        if type(request) is not ParityHarnessJobRequest:
            raise ContractViolation("local parity harness job requires the closed request type")
        principal = require_digest(authenticated_principal_digest)
        owner = self.store.query_one(
            "SELECT tenant_id FROM projects WHERE project_id=?",
            (request.project_id,),
        )
        if owner is None or str(owner[0]) != request.tenant_id:
            raise NotFound("trusted parity runner is unavailable")
        harness_request = self._harness_request(request)
        registration = self.runner_registry.resolve(
            harness_request,
            authenticated_principal_id=principal,
        )
        if (
            registration.tenant_id != request.tenant_id
            or registration.project_id != request.project_id
            or registration.principal_id != principal
            or registration.runner_id != request.runner_id
        ):
            raise ContractViolation("trusted parity runner registration scope drifted")
        return registration

    def authorize_slo(
        self,
        request: SloReconcileJobRequest,
        *,
        authenticated_principal_digest: str,
    ) -> CacheSloControlService:
        """Resolve one registered SLO controller without mutating its journal."""

        if type(request) is not SloReconcileJobRequest:
            raise ContractViolation("SLO reconcile job requires the closed request type")
        principal = require_digest(authenticated_principal_digest)
        service = self.slo_runtime_registry.service(
            request.tenant_id,
            request.project_id,
            request.controller_id,
            principal,
        )
        if service.store is not self.store or service.cas is not self.cas:
            raise ContractViolation("SLO controller is not composed with the local job store")
        if (
            service.tenant_id != request.tenant_id
            or service.project_id != request.project_id
            or service.controller_id != request.controller_id
            or service.principal_digest != principal
        ):
            raise ContractViolation("SLO controller registration scope drifted")
        return service

    def run_harness_once(
        self,
        request: ParityHarnessJobRequest,
        *,
        authenticated_principal_digest: str,
    ) -> ParityJobResult:
        """Execute a registered deterministic harness at most once per job ID."""

        principal = require_digest(authenticated_principal_digest)
        registration = self.authorize_harness(
            request,
            authenticated_principal_digest=principal,
        )
        claim_request = {
            **request.to_dict(),
            "principal_digest": principal,
            "registration_digest": registration.registration_digest,
        }
        claim = self._claim(request.tenant_id, request.job_id, _HARNESS_OPERATION, claim_request)
        if claim.replayed:
            result = self._result_from_claim(
                claim,
                request=request,
                principal_digest=principal,
                expected_job_type="TRUSTED_PARITY_HARNESS",
            )
            # A replay is a read of the durable receipt, never a second harness
            # execution.  Re-running an arbitrary registered runner here would
            # violate at-most-once semantics and could consume external or
            # expensive resources.  The receipt and report envelope are
            # verified against their CAS registrations instead.
            self._verify_harness_report(result, request=request)
            return result
        owner_token = self._claim_owner(claim)

        harness_result = self.harness_service.execute(
            self._harness_request(request),
            authenticated_principal_id=principal,
        )
        report = dict(harness_result.report)
        local_decision_value = report.get("decision")
        if not isinstance(local_decision_value, str):
            raise ContractViolation("trusted parity report decision is missing")
        try:
            local_decision = ParityDecision(local_decision_value)
        except ValueError as exc:
            raise ContractViolation("trusted parity report decision is invalid") from exc
        report_digest = digest_of(report)
        harness_result_digest = digest_of(harness_result.receipt())
        event = {
            "schema_version": _SCHEMA_VERSION,
            "kind": _EVENT_KIND,
            "event_type": "TRUSTED_PARITY_HARNESS_COMPLETED",
            "tenant_id": request.tenant_id,
            "project_id": request.project_id,
            "job_id": request.job_id,
            "principal_digest": principal,
            "runner_id": request.runner_id,
            "report_id": request.report_id,
            "registration_digest": registration.registration_digest,
            "report_digest": report_digest,
            "report_artifact_digest": harness_result.report_artifact_digest,
            "harness_result_digest": harness_result_digest,
            "local_decision": str(local_decision),
        }
        source_event_digest = self._persist_job_document(
            request,
            event,
            artifact_kind="cache-parity-local-job-event",
            ref_kind="source-event",
        )
        receipt = {
            "schema_version": _SCHEMA_VERSION,
            "kind": _RECEIPT_KIND,
            "job_type": "TRUSTED_PARITY_HARNESS",
            "tenant_id": request.tenant_id,
            "project_id": request.project_id,
            "job_id": request.job_id,
            "principal_digest": principal,
            "runner_id": request.runner_id,
            "report_id": request.report_id,
            "registration_digest": registration.registration_digest,
            "source_event_digest": source_event_digest,
            "report_digest": report_digest,
            "report_artifact_digest": harness_result.report_artifact_digest,
            "harness_result_digest": harness_result_digest,
            "local_decision": str(local_decision),
            "maximum_local_decision": str(ParityDecision.READY_FOR_EXTERNAL_GATE),
            "external_evidence_state": "NOT_RUN",
            "certification_state": "NOT_CERTIFIED",
        }
        result = self._complete_job(
            request=request,
            operation=_HARNESS_OPERATION,
            claim_request=claim_request,
            owner_token=owner_token,
            fence=claim.fence,
            receipt=receipt,
            dependencies=(
                ("source-event", source_event_digest),
                ("parity-report", harness_result.report_artifact_digest),
            ),
        )
        self._verify_source_event(result, request=request, principal_digest=principal)
        return result

    def reconcile_slo_once(
        self,
        request: SloReconcileJobRequest,
        *,
        authenticated_principal_digest: str,
    ) -> ParityJobResult:
        """Reconcile one registered controller once, with a durable local receipt."""

        principal = require_digest(authenticated_principal_digest)
        service = self.authorize_slo(
            request,
            authenticated_principal_digest=principal,
        )
        claim_request = {**request.to_dict(), "principal_digest": principal}
        claim = self._claim(request.tenant_id, request.job_id, _SLO_OPERATION, claim_request)
        if claim.replayed:
            return self._result_from_claim(
                claim,
                request=request,
                principal_digest=principal,
                expected_job_type="CACHE_SLO_RECONCILE",
                slo_service=service,
            )
        owner_token = self._claim_owner(claim)

        before = service.status()
        after = service.reconcile()
        before_event = require_digest(str(before["event_digest"]))
        after_event = require_digest(str(after["event_digest"]))
        after_status_digest = digest_of(after)
        event = {
            "schema_version": _SCHEMA_VERSION,
            "kind": _EVENT_KIND,
            "event_type": "CACHE_SLO_RECONCILED",
            "tenant_id": request.tenant_id,
            "project_id": request.project_id,
            "job_id": request.job_id,
            "principal_digest": principal,
            "controller_id": request.controller_id,
            "source_slo_event_digest": before_event,
            "result_slo_event_digest": after_event,
            "result_sequence": int(after["sequence"]),
            "result_action": str(after["last_action"]),
            "result_status_digest": after_status_digest,
        }
        source_event_digest = self._persist_job_document(
            request,
            event,
            artifact_kind="cache-parity-local-job-event",
            ref_kind="source-event",
        )
        receipt = {
            "schema_version": _SCHEMA_VERSION,
            "kind": _RECEIPT_KIND,
            "job_type": "CACHE_SLO_RECONCILE",
            "tenant_id": request.tenant_id,
            "project_id": request.project_id,
            "job_id": request.job_id,
            "principal_digest": principal,
            "controller_id": request.controller_id,
            "source_event_digest": source_event_digest,
            "source_slo_event_digest": before_event,
            "result_slo_event_digest": after_event,
            "result_sequence": int(after["sequence"]),
            "result_action": str(after["last_action"]),
            "result_status_digest": after_status_digest,
            "maximum_local_decision": str(ParityDecision.READY_FOR_EXTERNAL_GATE),
            "external_evidence_state": "NOT_RUN",
            "certification_state": "NOT_CERTIFIED",
        }
        result = self._complete_job(
            request=request,
            operation=_SLO_OPERATION,
            claim_request=claim_request,
            owner_token=owner_token,
            fence=claim.fence,
            receipt=receipt,
            dependencies=(
                ("source-event", source_event_digest),
                ("slo-event-before", before_event),
                ("slo-event-after", after_event),
            ),
        )
        self._verify_source_event(result, request=request, principal_digest=principal)
        self._verify_slo_receipt(result, request=request, service=service)
        return result

    @staticmethod
    def _harness_request(request: ParityHarnessJobRequest) -> ParityHarnessRunRequest:
        return ParityHarnessRunRequest(
            request.tenant_id,
            request.project_id,
            request.runner_id,
            request.report_id,
        )

    def _claim(
        self,
        tenant_id: str,
        job_id: str,
        operation: str,
        claim_request: Mapping[str, Any],
    ) -> IdempotencyClaim:
        key = self._idempotency_key(tenant_id, job_id)
        with self.store.transaction():
            return self.store.claim_idempotent(
                tenant_id,
                key,
                operation,
                dict(claim_request),
            )

    @staticmethod
    def _idempotency_key(tenant_id: str, job_id: str) -> str:
        return "parity-job:" + digest_of(
            {"tenant_id": tenant_id, "job_id": job_id}
        )

    @staticmethod
    def _claim_owner(claim: IdempotencyClaim) -> str:
        if not claim.claimed or claim.owner_token is None:
            raise ContractViolation("local parity job idempotency claim is invalid")
        return claim.owner_token

    def _complete_job(
        self,
        *,
        request: ParityHarnessJobRequest | SloReconcileJobRequest,
        operation: str,
        claim_request: Mapping[str, Any],
        owner_token: str,
        fence: int,
        receipt: Mapping[str, Any],
        dependencies: Sequence[tuple[str, str]],
    ) -> ParityJobResult:
        receipt_document = dict(receipt)
        receipt_digest = self._persist_job_document(
            request,
            receipt_document,
            artifact_kind="cache-parity-local-job-receipt",
            ref_kind="receipt",
        )
        with self.store.transaction():
            for ref_kind, digest in dependencies:
                self.store.add_artifact_ref(
                    request.tenant_id,
                    PARITY_JOB_DEPENDENCY_SOURCE_KIND,
                    receipt_digest,
                    require_digest(digest),
                    ref_kind,
                )
            self.store.complete_idempotent(
                request.tenant_id,
                self._idempotency_key(request.tenant_id, request.job_id),
                operation,
                dict(claim_request),
                owner_token,
                fence,
                {"receipt_digest": receipt_digest},
            )
        return ParityJobResult(receipt_digest, receipt_document)

    def _persist_job_document(
        self,
        request: ParityHarnessJobRequest | SloReconcileJobRequest,
        document: Mapping[str, Any],
        *,
        artifact_kind: str,
        ref_kind: str,
    ) -> str:
        payload = dict(document)
        digest = self.cas.put_document(payload, artifact_kind=artifact_kind)
        if digest_of(payload) != digest:
            raise CorruptObject("local parity job CAS digest is invalid")
        info = self.cas.info(digest)
        metadata = {
            "project_id": request.project_id,
            "job_id": request.job_id,
            "job_type": str(payload.get("job_type", payload.get("event_type", ""))),
            "external_evidence_state": "NOT_RUN",
            "certification_state": "NOT_CERTIFIED",
        }
        with self.store.transaction():
            existing = self.store.get_artifact(request.tenant_id, digest)
            if existing is not None and (
                existing.size_bytes != info.size
                or existing.media_type != "application/json"
                or existing.artifact_kind != artifact_kind
                or existing.storage_state
                in {
                    ArtifactStorageState.QUARANTINED,
                    ArtifactStorageState.DELETING,
                    ArtifactStorageState.DELETED,
                }
                or existing.validation_level is ValidationLevel.QUARANTINED
            ):
                raise ContractViolation(
                    "existing artifact conflicts with local parity job evidence",
                    digest=digest,
                )
            self.store.register_artifact(
                request.tenant_id,
                digest,
                info.size,
                "application/json",
                artifact_kind,
                ArtifactStorageState.LOCAL,
                ValidationLevel.UNVERIFIED,
                metadata,
            )
            self.store.add_artifact_ref(
                request.tenant_id,
                PARITY_JOB_REF_SOURCE_KIND,
                request.job_id,
                digest,
                parity_job_ref_kind(request.project_id) + ":" + ref_kind,
            )
        return digest

    def _result_from_claim(
        self,
        claim: IdempotencyClaim,
        *,
        request: ParityHarnessJobRequest | SloReconcileJobRequest,
        principal_digest: str,
        expected_job_type: str,
        slo_service: CacheSloControlService | None = None,
    ) -> ParityJobResult:
        response = claim.response
        if not isinstance(response, Mapping) or set(response) != {"receipt_digest"}:
            raise CorruptObject("stored local parity job response is invalid")
        receipt_digest = response.get("receipt_digest")
        if not isinstance(receipt_digest, str):
            raise CorruptObject("stored local parity job receipt digest is invalid")
        try:
            document = self.cas.get_document(require_digest(receipt_digest))
        except (TypeError, ValueError) as exc:
            raise CorruptObject("stored local parity job receipt cannot be decoded") from exc
        if not isinstance(document, dict):
            raise CorruptObject("stored local parity job receipt must be an object")
        receipt = cast(dict[str, Any], document)
        if (
            digest_of(receipt) != receipt_digest
            or receipt.get("schema_version") != _SCHEMA_VERSION
            or receipt.get("kind") != _RECEIPT_KIND
            or receipt.get("job_type") != expected_job_type
            or receipt.get("tenant_id") != request.tenant_id
            or receipt.get("project_id") != request.project_id
            or receipt.get("job_id") != request.job_id
            or receipt.get("principal_digest") != principal_digest
            or receipt.get("maximum_local_decision")
            != str(ParityDecision.READY_FOR_EXTERNAL_GATE)
            or receipt.get("external_evidence_state") != "NOT_RUN"
            or receipt.get("certification_state") != "NOT_CERTIFIED"
        ):
            raise CorruptObject("stored local parity job receipt binding is invalid")
        self._verify_job_artifact(
            request,
            receipt_digest,
            receipt,
            artifact_kind="cache-parity-local-job-receipt",
            ref_kind="receipt",
        )
        result = ParityJobResult(receipt_digest, receipt, replayed=True)
        self._verify_source_event(
            result,
            request=request,
            principal_digest=principal_digest,
        )
        if expected_job_type == "CACHE_SLO_RECONCILE":
            if not isinstance(request, SloReconcileJobRequest) or slo_service is None:
                raise ContractViolation("SLO replay is missing its trusted controller")
            self._verify_slo_receipt(result, request=request, service=slo_service)
        return result

    def _verify_source_event(
        self,
        result: ParityJobResult,
        *,
        request: ParityHarnessJobRequest | SloReconcileJobRequest,
        principal_digest: str,
    ) -> None:
        source_event_digest = result.receipt.get("source_event_digest")
        if not isinstance(source_event_digest, str):
            raise CorruptObject("local parity job source event digest is missing")
        document = self.cas.get_document(require_digest(source_event_digest))
        if not isinstance(document, dict):
            raise CorruptObject("local parity job source event must be an object")
        event = cast(dict[str, Any], document)
        if (
            event.get("schema_version") != _SCHEMA_VERSION
            or event.get("kind") != _EVENT_KIND
            or event.get("tenant_id") != request.tenant_id
            or event.get("project_id") != request.project_id
            or event.get("job_id") != request.job_id
            or event.get("principal_digest") != principal_digest
        ):
            raise CorruptObject("local parity job source event binding is invalid")
        for field_name, value in result.receipt.items():
            if field_name in {
                "runner_id",
                "report_id",
                "registration_digest",
                "report_digest",
                "report_artifact_digest",
                "harness_result_digest",
                "controller_id",
                "source_slo_event_digest",
                "result_slo_event_digest",
                "result_sequence",
                "result_action",
                "result_status_digest",
            } and event.get(field_name) != value:
                raise CorruptObject(
                    "local parity job source event differs from its receipt",
                    field=field_name,
                )
        self._verify_job_artifact(
            request,
            source_event_digest,
            event,
            artifact_kind="cache-parity-local-job-event",
            ref_kind="source-event",
        )

    def _verify_slo_receipt(
        self,
        result: ParityJobResult,
        *,
        request: SloReconcileJobRequest,
        service: CacheSloControlService,
    ) -> None:
        """Re-check the durable SLO journal behind a replayed job receipt."""

        before_digest = result.receipt.get("source_slo_event_digest")
        after_digest = result.receipt.get("result_slo_event_digest")
        status_digest = result.receipt.get("result_status_digest")
        if not isinstance(before_digest, str) or not isinstance(after_digest, str):
            raise CorruptObject("SLO job receipt event digests are missing")
        require_digest(before_digest)
        require_digest(after_digest)
        if not isinstance(status_digest, str):
            raise CorruptObject("SLO job receipt status digest is missing")
        require_digest(status_digest)

        status = service.status()
        if (
            status["event_digest"] != after_digest
            or int(status["sequence"]) != int(result.receipt.get("result_sequence", -1))
            or status["last_action"] != result.receipt.get("result_action")
            or digest_of(status) != status_digest
        ):
            raise CorruptObject("SLO job receipt no longer matches the durable controller")

        for digest in (before_digest, after_digest):
            row = self.store.query_one(
                "SELECT event_digest, document FROM cache_slo_control_events_v12 "
                "WHERE tenant_id=? AND project_id=? AND controller_id=? AND event_digest=?",
                (request.tenant_id, request.project_id, request.controller_id, digest),
            )
            if row is None:
                raise CorruptObject("SLO job receipt references a missing journal event")
            try:
                document = json.loads(str(row[1]))
            except (TypeError, ValueError) as exc:
                raise CorruptObject("SLO journal event is not valid JSON") from exc
            if not isinstance(document, dict) or digest_of(document) != digest:
                raise CorruptObject("SLO journal event digest does not match its bytes")

    def _verify_harness_report(
        self,
        result: ParityJobResult,
        *,
        request: ParityHarnessJobRequest,
    ) -> None:
        """Verify the report envelope without invoking the trusted runner."""

        report_digest = result.receipt.get("report_digest")
        report_artifact_digest = result.receipt.get("report_artifact_digest")
        if not isinstance(report_digest, str) or not isinstance(
            report_artifact_digest, str
        ):
            raise CorruptObject("local parity job report digests are missing")
        envelope = self.cas.get_document(require_digest(report_artifact_digest))
        if not isinstance(envelope, Mapping):
            raise CorruptObject("local parity harness report envelope is invalid")
        report = envelope.get("report")
        if (
            envelope.get("kind") != "elmos.cache-parity-harness-report/v1.2"
            or not isinstance(report, Mapping)
            or digest_of(dict(report)) != report_digest
            or envelope.get("external_evidence_state") != "NOT_RUN"
            or envelope.get("maximum_local_decision")
            != str(ParityDecision.READY_FOR_EXTERNAL_GATE)
        ):
            raise CorruptObject("local parity harness report envelope binding is invalid")
        raw = self.cas.get_bytes(require_digest(report_artifact_digest), verify=True)
        registration = self.store.get_artifact(request.tenant_id, report_artifact_digest)
        expected_ref = (
            "parity-harness-report",
            request.report_id,
            parity_job_ref_kind(request.project_id),
        )
        if (
            registration is None
            or registration.size_bytes != len(raw)
            or registration.media_type != "application/json"
            or registration.artifact_kind != "cache-parity-harness-report"
            or expected_ref
            not in self.store.artifact_referrers(request.tenant_id, report_artifact_digest)
        ):
            raise CorruptObject("local parity harness report registration is incomplete")

    def _verify_job_artifact(
        self,
        request: ParityHarnessJobRequest | SloReconcileJobRequest,
        digest: str,
        document: Mapping[str, Any],
        *,
        artifact_kind: str,
        ref_kind: str,
    ) -> None:
        raw = self.cas.get_bytes(require_digest(digest), verify=True)
        registration = self.store.get_artifact(request.tenant_id, digest)
        expected_ref = (
            PARITY_JOB_REF_SOURCE_KIND,
            request.job_id,
            parity_job_ref_kind(request.project_id) + ":" + ref_kind,
        )
        if (
            digest_of(dict(document)) != digest
            or registration is None
            or registration.size_bytes != len(raw)
            or registration.media_type != "application/json"
            or registration.artifact_kind != artifact_kind
            or registration.storage_state
            in {
                ArtifactStorageState.QUARANTINED,
                ArtifactStorageState.DELETING,
                ArtifactStorageState.DELETED,
            }
            or registration.validation_level is ValidationLevel.QUARANTINED
            or expected_ref
            not in self.store.artifact_referrers(request.tenant_id, digest)
        ):
            raise CorruptObject("local parity job artifact registration is incomplete")


__all__ = [
    "PARITY_JOB_DEPENDENCY_SOURCE_KIND",
    "PARITY_JOB_REF_SOURCE_KIND",
    "ParityHarnessJobRequest",
    "ParityJobResult",
    "ParityJobService",
    "SloReconcileJobRequest",
    "parity_job_ref_kind",
]
