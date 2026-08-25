"""Durable, evidence-gated cache SLO tuning and progressive rollout.

The controller is wired to one authenticated principal and exact tenant,
project and controller scope. Observations, approvals and rollout windows are
immutable CAS objects with Ed25519 attestations. Validation completes before
mutation, so denied, foreign, stale and malformed inputs cannot create rows or
CAS bytes. Local evidence may exercise rollback but never advances serving.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from .canonical import canonical_json_text, digest_of, require_digest
from .cas import ContentAddressableStore
from .clock import SYSTEM_CLOCK, Clock
from .db import MetadataStore
from .enums import ArtifactStorageState
from .errors import (
    ConflictError,
    ContractViolation,
    IdempotencyConflict,
    NotFound,
    PermissionDenied,
    ProvenanceInvalid,
)
from .parity import ParityReport
from .security import ProvenanceSigner, SignedStatement, require_asymmetric
from .slo_autotune import (
    ROLLOUT_ORDER,
    CacheTuningParameters,
    ProgressiveRolloutController,
    RollbackReason,
    RolloutEvidence,
    RolloutPhase,
    RolloutState,
    SloAutotuner,
    TuningObservation,
    TuningProposal,
)

SLO_SCHEMA_VERSION = "1.2.0"
SLO_APPROVAL_KIND = "elmos.cache-slo-policy-approval/v1.2"
SLO_OBSERVATION_ATTESTATION_KIND = "elmos.cache-slo-observation-attestation/v1.2"
SLO_ROLLOUT_EVIDENCE_ATTESTATION_KIND = (
    "elmos.cache-slo-rollout-evidence-attestation/v1.2"
)
SLO_APPROVAL_DECISION = "APPROVE_BOUNDED_ROLLOUT"
SLO_APPROVAL_MAX_TTL_SECONDS = 7 * 86_400
SLO_OBSERVATION_MAX_TTL_SECONDS = 86_400
SLO_EVIDENCE_MAX_TTL_SECONDS = 86_400
SLO_CLOCK_SKEW_SECONDS = 300

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}$")
_EVENT_KEYS = {
    "schema_version",
    "kind",
    "tenant_id",
    "project_id",
    "controller_id",
    "principal_digest",
    "sequence",
    "action",
    "state",
    "proposal_digest",
    "approval_digest",
    "evidence_digest",
    "evidence_state",
    "previous_event_digest",
    "recorded_at",
    "event_digest",
}
_PROPOSAL_KEYS = {
    "schema_version",
    "kind",
    "tenant_id",
    "project_id",
    "controller_id",
    "principal_digest",
    "proposal_digest",
    "baseline_digest",
    "candidate_digest",
    "candidate",
    "reason_codes",
    "shadow_only",
    "observation_artifact_digest",
    "observation_digest",
}


class SloEvidenceState(StrEnum):
    LOCAL_ENGINEERING = "LOCAL_ENGINEERING"
    EXTERNAL_VERIFIED = "EXTERNAL_VERIFIED"


@dataclass(frozen=True)
class TrustedTuningObservation:
    """One signed, content-addressed observation from a trusted collector."""

    observation: TuningObservation
    artifact_digest: str
    attestation: SignedStatement
    collector_identity: str
    verifier_identity: str

    def __post_init__(self) -> None:
        require_digest(self.artifact_digest)
        _identifier(self.collector_identity, "collector_identity")
        _identifier(self.verifier_identity, "verifier_identity")
        if self.collector_identity == self.verifier_identity:
            raise ContractViolation(
                "SLO observation collection and verification must be independent"
            )


@dataclass(frozen=True)
class TrustedRolloutWindow:
    """One signed, content-addressed rollout window from an evidence plane."""

    evidence: RolloutEvidence
    evidence_digest: str
    evidence_state: SloEvidenceState
    attestation: SignedStatement
    executor_identity: str
    verifier_identity: str

    def __post_init__(self) -> None:
        require_digest(self.evidence_digest)
        _identifier(self.executor_identity, "executor_identity")
        _identifier(self.verifier_identity, "verifier_identity")
        if self.executor_identity == self.verifier_identity:
            raise ContractViolation(
                "SLO rollout execution and verification must be independent"
            )


class TuningObservationSource(Protocol):
    def current(
        self,
        tenant_id: str,
        project_id: str,
        controller_id: str,
        principal_digest: str,
    ) -> TrustedTuningObservation: ...


class RolloutEvidenceSource(Protocol):
    def current(
        self,
        tenant_id: str,
        project_id: str,
        controller_id: str,
        principal_digest: str,
    ) -> TrustedRolloutWindow: ...


class SloApprovalResolver(Protocol):
    def resolve(
        self,
        tenant_id: str,
        project_id: str,
        controller_id: str,
        principal_digest: str,
        proposal_digest: str,
    ) -> SignedStatement | None: ...


class StaticSloApprovalResolver:
    """Exact-scope operator receipt registry for local composition."""

    def __init__(self) -> None:
        self._receipts: dict[tuple[str, str, str, str, str], SignedStatement] = {}

    def register(
        self,
        *,
        tenant_id: str,
        project_id: str,
        controller_id: str,
        principal_digest: str,
        proposal_digest: str,
        receipt: SignedStatement,
    ) -> None:
        key = (
            _identifier(tenant_id, "tenant_id"),
            _identifier(project_id, "project_id"),
            _identifier(controller_id, "controller_id"),
            require_digest(principal_digest),
            require_digest(proposal_digest),
        )
        existing = self._receipts.get(key)
        if existing is not None and existing.to_dict() != receipt.to_dict():
            raise IdempotencyConflict(
                "SLO proposal approval was replaced with different bytes",
                proposal_digest=proposal_digest,
            )
        self._receipts[key] = receipt

    def resolve(
        self,
        tenant_id: str,
        project_id: str,
        controller_id: str,
        principal_digest: str,
        proposal_digest: str,
    ) -> SignedStatement | None:
        return self._receipts.get(
            (
                _identifier(tenant_id, "tenant_id"),
                _identifier(project_id, "project_id"),
                _identifier(controller_id, "controller_id"),
                require_digest(principal_digest),
                require_digest(proposal_digest),
            )
        )


def slo_scope_digest(
    *, tenant_id: str, project_id: str, controller_id: str, principal_digest: str
) -> str:
    """Digest the exact authority scope consumed by the controller."""

    return digest_of(
        {
            "schema_version": SLO_SCHEMA_VERSION,
            "tenant_id": _identifier(tenant_id, "tenant_id"),
            "project_id": _identifier(project_id, "project_id"),
            "controller_id": _identifier(controller_id, "controller_id"),
            "principal_digest": require_digest(principal_digest),
        }
    )


def slo_observation_statement(
    *,
    tenant_id: str,
    project_id: str,
    controller_id: str,
    principal_digest: str,
    baseline_digest: str,
    observation: TuningObservation,
    collector_identity: str,
    verifier_identity: str,
    issued_at: float,
    expires_at: float,
) -> dict[str, Any]:
    """Return the exact statement an observation verifier signs."""

    collector = _identifier(collector_identity, "collector_identity")
    verifier = _identifier(verifier_identity, "verifier_identity")
    if collector == verifier:
        raise ContractViolation(
            "SLO observation collection and verification must be independent"
        )
    return {
        "schema_version": SLO_SCHEMA_VERSION,
        "tenant_id": _identifier(tenant_id, "tenant_id"),
        "project_id": _identifier(project_id, "project_id"),
        "controller_id": _identifier(controller_id, "controller_id"),
        "principal_digest": require_digest(principal_digest),
        "baseline_digest": require_digest(baseline_digest),
        "observation_digest": digest_of(asdict(observation)),
        "collector_identity": collector,
        "verifier_identity": verifier,
        "issued_at": _timestamp(issued_at, "issued_at"),
        "expires_at": _timestamp(expires_at, "expires_at"),
    }


def slo_observation_artifact(
    *,
    tenant_id: str,
    project_id: str,
    controller_id: str,
    principal_digest: str,
    baseline_digest: str,
    observation: TuningObservation,
    collector_identity: str,
    verifier_identity: str,
    attestation: SignedStatement,
) -> dict[str, Any]:
    """Build the closed signed observation envelope stored in CAS."""

    payload = {
        "schema_version": SLO_SCHEMA_VERSION,
        "kind": "elmos.cache-slo-observation/v1.2",
        "tenant_id": _identifier(tenant_id, "tenant_id"),
        "project_id": _identifier(project_id, "project_id"),
        "controller_id": _identifier(controller_id, "controller_id"),
        "principal_digest": require_digest(principal_digest),
        "baseline_digest": require_digest(baseline_digest),
        "observation_digest": digest_of(asdict(observation)),
        "observation": asdict(observation),
        "collector_identity": _identifier(collector_identity, "collector_identity"),
        "verifier_identity": _identifier(verifier_identity, "verifier_identity"),
    }
    return {
        "schema_version": SLO_SCHEMA_VERSION,
        "kind": "elmos.cache-slo-attested-observation/v1.2",
        "payload_digest": digest_of(payload),
        "payload": payload,
        "attestation": attestation.to_dict(),
    }


def slo_approval_statement(
    *,
    tenant_id: str,
    project_id: str,
    controller_id: str,
    principal_digest: str,
    proposal: TuningProposal,
    approver_identity: str,
    maximum_phase: RolloutPhase,
    issued_at: float,
    expires_at: float,
) -> dict[str, Any]:
    """Return the exact statement an independent policy approver signs."""

    if ROLLOUT_ORDER.index(maximum_phase) < ROLLOUT_ORDER.index(RolloutPhase.SHADOW):
        raise ContractViolation("an SLO approval must permit at least shadow evaluation")
    return {
        "schema_version": SLO_SCHEMA_VERSION,
        "tenant_id": _identifier(tenant_id, "tenant_id"),
        "project_id": _identifier(project_id, "project_id"),
        "controller_id": _identifier(controller_id, "controller_id"),
        "principal_digest": require_digest(principal_digest),
        "approver_identity": _identifier(approver_identity, "approver_identity"),
        "proposal_digest": proposal.proposal_digest,
        "baseline_digest": proposal.baseline_digest,
        "candidate_digest": proposal.candidate.digest,
        "approved_from_phase": RolloutPhase.SHADOW.value,
        "maximum_phase": maximum_phase.value,
        "decision": SLO_APPROVAL_DECISION,
        "issued_at": _timestamp(issued_at, "issued_at"),
        "expires_at": _timestamp(expires_at, "expires_at"),
    }


def slo_rollout_evidence_statement(
    *,
    tenant_id: str,
    project_id: str,
    controller_id: str,
    principal_digest: str,
    proposal: TuningProposal,
    approval_digest: str,
    current_state: RolloutState,
    head_event_digest: str,
    evidence: RolloutEvidence,
    evidence_state: SloEvidenceState,
    executor_identity: str,
    verifier_identity: str,
    issued_at: float,
    expires_at: float,
) -> dict[str, Any]:
    """Return the exact statement an independent rollout verifier signs."""

    executor = _identifier(executor_identity, "executor_identity")
    verifier = _identifier(verifier_identity, "verifier_identity")
    if executor == verifier:
        raise ContractViolation(
            "SLO rollout execution and verification must be independent"
        )
    return {
        "schema_version": SLO_SCHEMA_VERSION,
        "tenant_id": _identifier(tenant_id, "tenant_id"),
        "project_id": _identifier(project_id, "project_id"),
        "controller_id": _identifier(controller_id, "controller_id"),
        "principal_digest": require_digest(principal_digest),
        "proposal_digest": proposal.proposal_digest,
        "baseline_digest": proposal.baseline_digest,
        "candidate_digest": proposal.candidate.digest,
        "approval_digest": require_digest(approval_digest),
        "head_event_digest": require_digest(head_event_digest),
        "expected_phase": current_state.phase.value,
        "expected_epoch": current_state.epoch,
        "expected_consecutive_passes": current_state.consecutive_passes,
        "evidence_content_digest": digest_of(_rollout_evidence_payload(evidence)),
        "evidence_state": evidence_state.value,
        "executor_identity": executor,
        "verifier_identity": verifier,
        "issued_at": _timestamp(issued_at, "issued_at"),
        "expires_at": _timestamp(expires_at, "expires_at"),
    }


def slo_rollout_evidence_artifact(
    *,
    tenant_id: str,
    project_id: str,
    controller_id: str,
    principal_digest: str,
    proposal: TuningProposal,
    approval_digest: str,
    current_state: RolloutState,
    head_event_digest: str,
    evidence: RolloutEvidence,
    evidence_state: SloEvidenceState,
    executor_identity: str,
    verifier_identity: str,
    attestation: SignedStatement,
) -> dict[str, Any]:
    """Build the closed signed rollout-evidence envelope stored in CAS."""

    payload = {
        "schema_version": SLO_SCHEMA_VERSION,
        "kind": "elmos.cache-slo-rollout-window/v1.2",
        "tenant_id": _identifier(tenant_id, "tenant_id"),
        "project_id": _identifier(project_id, "project_id"),
        "controller_id": _identifier(controller_id, "controller_id"),
        "principal_digest": require_digest(principal_digest),
        "proposal_digest": proposal.proposal_digest,
        "baseline_digest": proposal.baseline_digest,
        "candidate_digest": proposal.candidate.digest,
        "approval_digest": require_digest(approval_digest),
        "head_event_digest": require_digest(head_event_digest),
        "expected_phase": current_state.phase.value,
        "expected_epoch": current_state.epoch,
        "expected_consecutive_passes": current_state.consecutive_passes,
        "evidence_content_digest": digest_of(_rollout_evidence_payload(evidence)),
        "evidence": _rollout_evidence_payload(evidence),
        "evidence_state": evidence_state.value,
        "executor_identity": _identifier(executor_identity, "executor_identity"),
        "verifier_identity": _identifier(verifier_identity, "verifier_identity"),
    }
    return {
        "schema_version": SLO_SCHEMA_VERSION,
        "kind": "elmos.cache-slo-attested-rollout-window/v1.2",
        "payload_digest": digest_of(payload),
        "payload": payload,
        "attestation": attestation.to_dict(),
    }


@dataclass(frozen=True)
class _VerifiedApproval:
    receipt: SignedStatement
    artifact_digest: str
    maximum_phase: RolloutPhase


@dataclass(frozen=True)
class _StoredProposal:
    proposal: TuningProposal
    document: dict[str, Any]
    artifact_digest: str
    configuration_artifact_digest: str


class CacheSloControlService:
    """Persist immutable SLO state and enforce approval/evidence transitions."""

    def __init__(
        self,
        *,
        tenant_id: str,
        project_id: str,
        controller_id: str,
        principal_digest: str,
        baseline: CacheTuningParameters,
        store: MetadataStore,
        cas: ContentAddressableStore,
        observation_source: TuningObservationSource,
        evidence_source: RolloutEvidenceSource,
        approval_resolver: SloApprovalResolver,
        observation_verifier: ProvenanceSigner,
        evidence_verifier: ProvenanceSigner,
        approval_verifier: ProvenanceSigner,
        clock: Clock = SYSTEM_CLOCK,
        minimum_samples: int = 1_000,
        required_windows: int = 3,
    ) -> None:
        self.tenant_id = _identifier(tenant_id, "tenant_id")
        self.project_id = _identifier(project_id, "project_id")
        self.controller_id = _identifier(controller_id, "controller_id")
        self.principal_digest = require_digest(principal_digest)
        self.baseline = baseline
        self.store = store
        self.cas = cas
        self.observation_source = observation_source
        self.evidence_source = evidence_source
        self.approval_resolver = approval_resolver
        self.observation_verifier = _require_ed25519(observation_verifier)
        self.evidence_verifier = _require_ed25519(evidence_verifier)
        self.approval_verifier = _require_ed25519(approval_verifier)
        self.clock = clock
        self.tuner = SloAutotuner(minimum_samples=minimum_samples)
        if required_windows < 1:
            raise ContractViolation("required rollout windows must be positive")
        self.required_windows = required_windows

        self._ensure_scope()
        events = self._events()
        if events:
            if events[0]["state"].get("baseline_digest") != self.baseline.digest:
                raise ContractViolation(
                    "configured SLO baseline differs from the durable baseline"
                )
            self._assert_configuration(self.baseline)
        else:
            baseline_artifact = self._persist_config(self.baseline)
            self._ensure_initialized(baseline_artifact)

    @property
    def scope_digest(self) -> str:
        return slo_scope_digest(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            controller_id=self.controller_id,
            principal_digest=self.principal_digest,
        )

    @property
    def _source_id(self) -> str:
        return f"{self.project_id}:{self.controller_id}"

    def _ensure_scope(self) -> None:
        row = self.store.query_one(
            "SELECT 1 FROM projects WHERE tenant_id=? AND project_id=?",
            (self.tenant_id, self.project_id),
        )
        if row is None:
            raise NotFound("SLO controller scope does not exist")

    def _configuration_document(
        self, parameters: CacheTuningParameters
    ) -> dict[str, Any]:
        return {
            "schema_version": SLO_SCHEMA_VERSION,
            "kind": "elmos.cache-slo-configuration/v1.2",
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "controller_id": self.controller_id,
            "principal_digest": self.principal_digest,
            "configuration_digest": parameters.digest,
            "parameters": asdict(parameters),
        }

    def _persist_config(self, parameters: CacheTuningParameters) -> str:
        return self._persist_document(
            self._configuration_document(parameters),
            artifact_kind="cache-slo-configuration",
            source_kind="cache-slo-configuration",
            source_id=f"{self._source_id}:{parameters.digest}",
            ref_kind="configuration",
        )

    def _assert_configuration(self, parameters: CacheTuningParameters) -> str:
        document = self._configuration_document(parameters)
        digest = digest_of(document)
        if self._owned_document(digest, "cache-slo-configuration") != document:
            raise ContractViolation("SLO configuration bytes do not match their digest")
        return digest

    def _persist_document(
        self,
        document: Mapping[str, Any],
        *,
        artifact_kind: str,
        source_kind: str,
        source_id: str,
        ref_kind: str,
        dependencies: Sequence[tuple[str, str]] = (),
    ) -> str:
        closed = dict(document)
        expected_digest = digest_of(closed)
        # Reject a semantic-id collision before CAS mutation. The same check
        # is repeated transactionally after the content write to close races.
        existing_targets = self.store.artifact_targets(
            self.tenant_id, source_kind, source_id
        )
        if existing_targets and set(existing_targets) != {expected_digest}:
            raise IdempotencyConflict(
                "SLO source identity already targets different bytes",
                source_kind=source_kind,
                source_id=source_id,
            )
        digest = self.cas.put_document(closed, artifact_kind=artifact_kind)
        if digest != expected_digest or not self.cas.verify(digest):
            raise ContractViolation("SLO artifact failed CAS verification")
        info = self.cas.info(digest)
        with self.store.transaction():
            self._ensure_scope()
            targets = self.store.artifact_targets(self.tenant_id, source_kind, source_id)
            if targets and set(targets) != {digest}:
                raise IdempotencyConflict(
                    "SLO source identity already targets different bytes",
                    source_kind=source_kind,
                    source_id=source_id,
                )
            record = self.store.register_artifact(
                self.tenant_id,
                digest,
                size_bytes=info.size,
                media_type="application/json",
                artifact_kind=artifact_kind,
            )
            if (
                record.size_bytes != info.size
                or record.media_type != "application/json"
                or record.artifact_kind != artifact_kind
                or record.storage_state is not ArtifactStorageState.LOCAL
            ):
                raise ConflictError("SLO CAS registration conflicts with existing metadata")
            self.store.add_artifact_ref(
                self.tenant_id, source_kind, source_id, digest, ref_kind
            )
            for dependency_kind, dependency_digest in dependencies:
                self._assert_owned_registration(dependency_digest)
                # Dependency edges are recorded under a derived source kind.
                # ``artifact_targets`` is not ref-kind aware, so writing them
                # under the identity key would make that key resolve to many
                # digests and destroy the exact one-target semantic identity
                # ``_proposal`` and the idempotency guard above depend on.
                self.store.add_artifact_ref(
                    self.tenant_id,
                    _dependency_source_kind(source_kind),
                    source_id,
                    dependency_digest,
                    _identifier(dependency_kind, "dependency_kind"),
                )
        return digest

    def _assert_owned_registration(self, digest: str) -> None:
        record = self.store.get_artifact(self.tenant_id, require_digest(digest))
        if record is None or record.storage_state is not ArtifactStorageState.LOCAL:
            raise NotFound("SLO evidence artifact does not exist")

    def _owned_document(self, digest: str, artifact_kind: str) -> dict[str, Any]:
        require_digest(digest)
        record = self.store.get_artifact(self.tenant_id, digest)
        if (
            record is None
            or record.storage_state is not ArtifactStorageState.LOCAL
            or record.media_type != "application/json"
            or record.artifact_kind != artifact_kind
        ):
            raise NotFound("SLO evidence artifact does not exist")
        if not self.cas.verify(digest):
            raise ContractViolation("SLO artifact failed CAS verification")
        info = self.cas.info(digest)
        if info.size != record.size_bytes:
            raise ContractViolation("SLO artifact size does not match metadata")
        document = self.cas.get_document(digest)
        if not isinstance(document, dict) or digest_of(document) != digest:
            raise ContractViolation("SLO artifact is not a canonical JSON document")
        return document

    def _ensure_initialized(self, baseline_artifact: str) -> None:
        with self.store.transaction():
            events = self._events()
            if events:
                if events[0]["state"].get("baseline_digest") != self.baseline.digest:
                    raise ContractViolation(
                        "configured SLO baseline differs from the durable baseline"
                    )
                return
            state = RolloutState(
                baseline_digest=self.baseline.digest,
                candidate_digest=None,
                serving_digest=self.baseline.digest,
            )
            self._insert_event(
                sequence=1,
                previous_event_digest=None,
                action="INITIALIZED",
                state=state,
                proposal_digest=None,
                approval_digest=None,
                evidence_digest=None,
                evidence_state=None,
                linked_artifacts=(("baseline_configuration", baseline_artifact),),
            )

    def _events(self) -> tuple[dict[str, Any], ...]:
        rows = self.store.query(
            "SELECT sequence,event_digest,principal_digest,previous_event_digest,action,"
            "proposal_digest,approval_digest,evidence_digest,evidence_state,document "
            "FROM cache_slo_control_events_v12 WHERE tenant_id=? AND project_id=? "
            "AND controller_id=? ORDER BY sequence",
            (self.tenant_id, self.project_id, self.controller_id),
        )
        if rows and any(str(row[2]) != self.principal_digest for row in rows):
            raise NotFound("SLO controller does not exist")
        events: list[dict[str, Any]] = []
        previous: str | None = None
        for expected_sequence, row in enumerate(rows, start=1):
            if int(row[0]) != expected_sequence:
                raise ContractViolation("SLO event sequence is not contiguous")
            document = _document(row[9])
            if set(document) != _EVENT_KEYS:
                raise ContractViolation("SLO event has an open or incomplete shape")
            if (
                document["schema_version"] != SLO_SCHEMA_VERSION
                or document["kind"] != "elmos.cache-slo-control-event/v1.2"
                or document["tenant_id"] != self.tenant_id
                or document["project_id"] != self.project_id
                or document["controller_id"] != self.controller_id
                or document["principal_digest"] != self.principal_digest
                or document["sequence"] != expected_sequence
                or document["previous_event_digest"] != previous
            ):
                raise ContractViolation("SLO event scope or chain is invalid")
            body = {key: value for key, value in document.items() if key != "event_digest"}
            calculated = digest_of(body)
            if document["event_digest"] != calculated or str(row[1]) != calculated:
                raise ContractViolation("SLO event digest does not match its bytes")
            state = _state(document["state"])
            self._assert_state(state)
            for field in ("proposal_digest", "approval_digest", "evidence_digest"):
                if document[field] is not None:
                    require_digest(str(document[field]))
            if document["evidence_state"] is not None:
                SloEvidenceState(str(document["evidence_state"]))
            column_values = (row[3], row[4], row[5], row[6], row[7], row[8])
            document_values = (
                document["previous_event_digest"],
                document["action"],
                document["proposal_digest"],
                document["approval_digest"],
                document["evidence_digest"],
                document["evidence_state"],
            )
            if tuple(None if value is None else str(value) for value in column_values) != tuple(
                None if value is None else str(value) for value in document_values
            ):
                raise ContractViolation("SLO event columns differ from document fields")
            previous = calculated
            events.append(document)
        return tuple(events)

    def _assert_state(self, state: RolloutState) -> None:
        if state.baseline_digest != self.baseline.digest:
            raise ContractViolation("SLO state is bound to a different baseline")
        if state.candidate_digest is None:
            if state.phase is not RolloutPhase.OBSERVE:
                raise ContractViolation("SLO state without a candidate must be OBSERVE")
            if state.serving_digest != state.baseline_digest:
                raise ContractViolation("SLO state without a candidate must serve baseline")
        elif state.phase is RolloutPhase.OBSERVE:
            raise ContractViolation("an installed SLO candidate cannot be OBSERVE")
        elif state.phase is RolloutPhase.SHADOW:
            if state.serving_digest != state.baseline_digest:
                raise ContractViolation("shadow SLO rollout must serve the baseline")
        elif state.serving_digest != state.candidate_digest:
            raise ContractViolation("active SLO rollout must serve the candidate")

    def _insert_event(
        self,
        *,
        sequence: int,
        previous_event_digest: str | None,
        action: str,
        state: RolloutState,
        proposal_digest: str | None,
        approval_digest: str | None,
        evidence_digest: str | None,
        evidence_state: SloEvidenceState | None,
        linked_artifacts: Sequence[tuple[str, str]] = (),
    ) -> dict[str, Any]:
        self._assert_state(state)
        body: dict[str, Any] = {
            "schema_version": SLO_SCHEMA_VERSION,
            "kind": "elmos.cache-slo-control-event/v1.2",
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "controller_id": self.controller_id,
            "principal_digest": self.principal_digest,
            "sequence": sequence,
            "action": _identifier(action, "action"),
            "state": state.to_dict(),
            "proposal_digest": proposal_digest,
            "approval_digest": approval_digest,
            "evidence_digest": evidence_digest,
            "evidence_state": evidence_state.value if evidence_state is not None else None,
            "previous_event_digest": previous_event_digest,
            "recorded_at": datetime.fromtimestamp(self.clock.now(), tz=UTC).isoformat(),
        }
        document = {**body, "event_digest": digest_of(body)}
        cursor = self.store.execute(
            "INSERT INTO cache_slo_control_events_v12 "
            "(tenant_id,project_id,controller_id,principal_digest,sequence,"
            "previous_event_digest,event_digest,action,proposal_digest,approval_digest,"
            "evidence_digest,evidence_state,document,recorded_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            (
                self.tenant_id,
                self.project_id,
                self.controller_id,
                self.principal_digest,
                sequence,
                previous_event_digest,
                document["event_digest"],
                document["action"],
                proposal_digest,
                approval_digest,
                evidence_digest,
                document["evidence_state"],
                canonical_json_text(document),
                document["recorded_at"],
            ),
        )
        if cursor.rowcount != 1:
            raise ConflictError("SLO controller received a concurrent transition")
        for ref_kind, digest in linked_artifacts:
            self._assert_owned_registration(digest)
            self.store.add_artifact_ref(
                self.tenant_id,
                "cache-slo-event",
                str(document["event_digest"]),
                digest,
                _identifier(ref_kind, "ref_kind"),
            )
        return document

    def _append(
        self,
        *,
        previous_event_digest: str,
        action: str,
        state: RolloutState,
        proposal_digest: str | None,
        approval_digest: str | None,
        evidence_digest: str | None,
        evidence_state: SloEvidenceState | None,
        linked_artifacts: Sequence[tuple[str, str]] = (),
    ) -> dict[str, Any]:
        with self.store.transaction():
            events = self._events()
            if not events or events[-1]["event_digest"] != previous_event_digest:
                raise ConflictError("SLO controller head changed concurrently")
            return self._insert_event(
                sequence=len(events) + 1,
                previous_event_digest=previous_event_digest,
                action=action,
                state=state,
                proposal_digest=proposal_digest,
                approval_digest=approval_digest,
                evidence_digest=evidence_digest,
                evidence_state=evidence_state,
                linked_artifacts=linked_artifacts,
            )

    def status(self) -> dict[str, Any]:
        events = self._events()
        if not events:
            raise NotFound("SLO controller is not initialized")
        head = events[-1]
        evidence_states = {
            str(event["evidence_state"])
            for event in events
            if event["evidence_state"] is not None
        }
        if SloEvidenceState.EXTERNAL_VERIFIED.value in evidence_states:
            evidence_status = SloEvidenceState.EXTERNAL_VERIFIED.value
        elif SloEvidenceState.LOCAL_ENGINEERING.value in evidence_states:
            evidence_status = "LOCAL_ENGINEERING_ONLY"
        else:
            evidence_status = "NOT_RUN"
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "controller_id": self.controller_id,
            "principal_digest": self.principal_digest,
            "sequence": head["sequence"],
            "event_digest": head["event_digest"],
            "state": head["state"],
            "last_action": head["action"],
            "proposal_digest": head["proposal_digest"],
            "approval_digest": head["approval_digest"],
            "evidence_digest": head["evidence_digest"],
            "external_evidence_state": evidence_status,
            "certified": False,
        }

    def _verify_observation(
        self, trusted: TrustedTuningObservation
    ) -> tuple[TuningObservation, str]:
        self._verify_statement(
            trusted.attestation,
            self.observation_verifier,
            SLO_OBSERVATION_ATTESTATION_KIND,
        )
        statement = trusted.attestation.statement
        expected = slo_observation_statement(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            controller_id=self.controller_id,
            principal_digest=self.principal_digest,
            baseline_digest=self.baseline.digest,
            observation=trusted.observation,
            collector_identity=trusted.collector_identity,
            verifier_identity=trusted.verifier_identity,
            issued_at=_statement_timestamp(statement, "issued_at"),
            expires_at=_statement_timestamp(statement, "expires_at"),
        )
        if statement != expected:
            raise ProvenanceInvalid("SLO observation binding is invalid")
        _validity_window(
            expected,
            now=self.clock.now(),
            maximum_ttl=SLO_OBSERVATION_MAX_TTL_SECONDS,
            subject="SLO observation",
        )
        expected_artifact = slo_observation_artifact(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            controller_id=self.controller_id,
            principal_digest=self.principal_digest,
            baseline_digest=self.baseline.digest,
            observation=trusted.observation,
            collector_identity=trusted.collector_identity,
            verifier_identity=trusted.verifier_identity,
            attestation=trusted.attestation,
        )
        stored = self._owned_document(trusted.artifact_digest, "cache-slo-observation")
        if stored != expected_artifact:
            raise ProvenanceInvalid("SLO observation CAS envelope is invalid")
        return trusted.observation, str(expected["observation_digest"])

    def propose(self) -> dict[str, Any]:
        trusted = self.observation_source.current(
            self.tenant_id,
            self.project_id,
            self.controller_id,
            self.principal_digest,
        )
        observation, observation_digest = self._verify_observation(trusted)
        proposal = self.tuner.propose(self.baseline, observation)
        if not proposal.shadow_only:
            raise ContractViolation("SLO tuner may only emit shadow proposals")
        document = {
            "schema_version": SLO_SCHEMA_VERSION,
            "kind": "elmos.cache-slo-proposal/v1.2",
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "controller_id": self.controller_id,
            "principal_digest": self.principal_digest,
            "proposal_digest": proposal.proposal_digest,
            "baseline_digest": proposal.baseline_digest,
            "candidate_digest": proposal.candidate.digest,
            "candidate": asdict(proposal.candidate),
            "reason_codes": list(proposal.reason_codes),
            "shadow_only": True,
            "observation_artifact_digest": trusted.artifact_digest,
            "observation_digest": observation_digest,
        }
        configuration_artifact = self._persist_config(proposal.candidate)
        artifact_digest = self._persist_document(
            document,
            artifact_kind="cache-slo-proposal",
            source_kind="cache-slo-proposal",
            source_id=f"{self._source_id}:{proposal.proposal_digest}",
            ref_kind="proposal",
            dependencies=(
                ("observation", trusted.artifact_digest),
                ("candidate_configuration", configuration_artifact),
            ),
        )
        return {**document, "artifact_digest": artifact_digest}

    def _proposal(self, proposal_digest: str) -> _StoredProposal:
        require_digest(proposal_digest)
        targets = self.store.artifact_targets(
            self.tenant_id,
            "cache-slo-proposal",
            f"{self._source_id}:{proposal_digest}",
        )
        if len(targets) != 1:
            raise NotFound("SLO proposal does not exist")
        artifact_digest = targets[0]
        document = self._owned_document(artifact_digest, "cache-slo-proposal")
        if set(document) != _PROPOSAL_KEYS:
            raise ContractViolation("SLO proposal has an open or incomplete shape")
        if (
            document["schema_version"] != SLO_SCHEMA_VERSION
            or document["kind"] != "elmos.cache-slo-proposal/v1.2"
            or document["tenant_id"] != self.tenant_id
            or document["project_id"] != self.project_id
            or document["controller_id"] != self.controller_id
            or document["principal_digest"] != self.principal_digest
            or document["proposal_digest"] != proposal_digest
            or document["baseline_digest"] != self.baseline.digest
            or document["shadow_only"] is not True
        ):
            raise ContractViolation("SLO proposal scope or baseline is invalid")
        candidate_value = document["candidate"]
        if not isinstance(candidate_value, Mapping):
            raise ContractViolation("SLO proposal candidate must be an object")
        candidate = CacheTuningParameters(**dict(candidate_value))
        reason_values = document["reason_codes"]
        if not isinstance(reason_values, list) or not all(
            isinstance(item, str) for item in reason_values
        ):
            raise ContractViolation("SLO proposal reasons must be strings")
        proposal = TuningProposal(
            baseline_digest=str(document["baseline_digest"]),
            candidate=candidate,
            reason_codes=tuple(reason_values),
            shadow_only=True,
        )
        if (
            proposal.proposal_digest != proposal_digest
            or document["candidate_digest"] != candidate.digest
        ):
            raise ContractViolation("SLO proposal digest is invalid")
        observation_artifact = str(document["observation_artifact_digest"])
        require_digest(observation_artifact)
        self._assert_owned_registration(observation_artifact)
        configuration_artifact = self._assert_configuration(candidate)
        return _StoredProposal(
            proposal, document, artifact_digest, configuration_artifact
        )

    def _approval(self, proposal: TuningProposal) -> _VerifiedApproval:
        receipt = self.approval_resolver.resolve(
            self.tenant_id,
            self.project_id,
            self.controller_id,
            self.principal_digest,
            proposal.proposal_digest,
        )
        if receipt is None:
            raise PermissionDenied("SLO proposal has no operator approval")
        self._verify_statement(receipt, self.approval_verifier, SLO_APPROVAL_KIND)
        statement = receipt.statement
        try:
            maximum_phase = RolloutPhase(str(statement["maximum_phase"]))
        except (KeyError, ValueError) as exc:
            raise ProvenanceInvalid("SLO approval phase is invalid") from exc
        expected = slo_approval_statement(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            controller_id=self.controller_id,
            principal_digest=self.principal_digest,
            proposal=proposal,
            approver_identity=str(statement.get("approver_identity", "")),
            maximum_phase=maximum_phase,
            issued_at=_statement_timestamp(statement, "issued_at"),
            expires_at=_statement_timestamp(statement, "expires_at"),
        )
        if statement != expected:
            raise ProvenanceInvalid("SLO approval binding is invalid")
        _validity_window(
            expected,
            now=self.clock.now(),
            maximum_ttl=SLO_APPROVAL_MAX_TTL_SECONDS,
            subject="SLO approval",
        )
        artifact_digest = digest_of(receipt.to_dict())
        if self._owned_document(artifact_digest, "cache-slo-approval") != receipt.to_dict():
            raise ProvenanceInvalid("SLO approval CAS receipt is invalid")
        return _VerifiedApproval(receipt, artifact_digest, maximum_phase)

    def _verify_window(
        self,
        window: TrustedRolloutWindow,
        stored_proposal: _StoredProposal,
        approval: _VerifiedApproval,
        current: RolloutState,
        head_event_digest: str,
    ) -> None:
        self._verify_statement(
            window.attestation,
            self.evidence_verifier,
            SLO_ROLLOUT_EVIDENCE_ATTESTATION_KIND,
        )
        statement = window.attestation.statement
        expected = slo_rollout_evidence_statement(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            controller_id=self.controller_id,
            principal_digest=self.principal_digest,
            proposal=stored_proposal.proposal,
            approval_digest=approval.artifact_digest,
            current_state=current,
            head_event_digest=head_event_digest,
            evidence=window.evidence,
            evidence_state=window.evidence_state,
            executor_identity=window.executor_identity,
            verifier_identity=window.verifier_identity,
            issued_at=_statement_timestamp(statement, "issued_at"),
            expires_at=_statement_timestamp(statement, "expires_at"),
        )
        if statement != expected:
            raise ProvenanceInvalid("SLO rollout evidence binding is invalid")
        _validity_window(
            expected,
            now=self.clock.now(),
            maximum_ttl=SLO_EVIDENCE_MAX_TTL_SECONDS,
            subject="SLO rollout evidence",
        )
        report = window.evidence.parity_report
        if report.report_digest != _parity_report_digest(report):
            raise ProvenanceInvalid("SLO parity report digest is invalid")
        if (
            report.binding.executor_identity != window.executor_identity
            or report.binding.verifier_identity != window.verifier_identity
        ):
            raise ProvenanceInvalid("SLO parity identities do not match the window")
        if window.evidence_state is SloEvidenceState.EXTERNAL_VERIFIED:
            if (
                not report.binding.authenticated
                or report.binding.tenant_scope_digest != self.scope_digest
                or report.binding.authorization_digest != approval.artifact_digest
                or report.binding.configuration_digest
                != stored_proposal.proposal.candidate.digest
            ):
                raise ProvenanceInvalid(
                    "external SLO evidence is not bound to scope and approval"
                )
        expected_artifact = slo_rollout_evidence_artifact(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            controller_id=self.controller_id,
            principal_digest=self.principal_digest,
            proposal=stored_proposal.proposal,
            approval_digest=approval.artifact_digest,
            current_state=current,
            head_event_digest=head_event_digest,
            evidence=window.evidence,
            evidence_state=window.evidence_state,
            executor_identity=window.executor_identity,
            verifier_identity=window.verifier_identity,
            attestation=window.attestation,
        )
        stored = self._owned_document(
            window.evidence_digest, "cache-slo-rollout-evidence"
        )
        if stored != expected_artifact:
            raise ProvenanceInvalid("SLO rollout evidence CAS envelope is invalid")

    @staticmethod
    def _verify_statement(
        signed: SignedStatement, verifier: ProvenanceSigner, expected_kind: str
    ) -> None:
        if signed.algorithm != "ed25519" or signed.kind != expected_kind:
            raise ProvenanceInvalid("SLO attestation kind or algorithm is invalid")
        verifier.verify_statement(signed)

    def install(self, proposal_digest: str) -> dict[str, Any]:
        stored_proposal = self._proposal(proposal_digest)
        approval = self._approval(stored_proposal.proposal)
        head = self._events()[-1]
        current = _state(head["state"])
        if current.candidate_digest == stored_proposal.proposal.candidate.digest:
            if (
                head["proposal_digest"] != stored_proposal.proposal.proposal_digest
                or head["approval_digest"] != approval.artifact_digest
            ):
                raise IdempotencyConflict(
                    "installed SLO candidate has a different durable authority"
                )
            return self.status()
        if current.candidate_digest is not None or current.serving_digest != current.baseline_digest:
            raise ConflictError(
                "an installed candidate must be rolled back before replacement"
            )
        next_state = ProgressiveRolloutController(
            current, required_windows=self.required_windows
        ).install_candidate(stored_proposal.proposal)
        self._append(
            previous_event_digest=str(head["event_digest"]),
            action="CANDIDATE_INSTALLED",
            state=next_state,
            proposal_digest=stored_proposal.proposal.proposal_digest,
            approval_digest=approval.artifact_digest,
            evidence_digest=None,
            evidence_state=None,
            linked_artifacts=(
                ("proposal", stored_proposal.artifact_digest),
                ("approval", approval.artifact_digest),
                ("candidate_configuration", stored_proposal.configuration_artifact_digest),
            ),
        )
        return self.status()

    def advance(self) -> dict[str, Any]:
        events = self._events()
        head = events[-1]
        current = _state(head["state"])
        proposal_digest = head.get("proposal_digest")
        if current.candidate_digest is None or not isinstance(proposal_digest, str):
            return self.status()
        stored_proposal = self._proposal(proposal_digest)
        try:
            approval = self._approval(stored_proposal.proposal)
        except (PermissionDenied, ProvenanceInvalid, ContractViolation, ValueError):
            return self._rollback_from_head(
                head,
                current,
                RollbackReason.APPROVAL_INVALID,
                action="APPROVAL_INVALID_ROLLBACK",
            )
        window = self.evidence_source.current(
            self.tenant_id,
            self.project_id,
            self.controller_id,
            self.principal_digest,
        )
        if any(event.get("evidence_digest") == window.evidence_digest for event in events):
            return self.status()
        self._verify_window(
            window,
            stored_proposal,
            approval,
            current,
            str(head["event_digest"]),
        )
        controller = ProgressiveRolloutController(
            current, required_windows=self.required_windows
        )
        trigger = controller._rollback_trigger(window.evidence)
        if trigger is not None:
            next_state = controller.rollback(trigger)
            action = "AUTOMATIC_ROLLBACK"
        elif window.evidence_state is SloEvidenceState.LOCAL_ENGINEERING:
            next_state = current
            action = "LOCAL_SHADOW_WINDOW"
        else:
            proposed_state = controller.observe(window.evidence)
            if ROLLOUT_ORDER.index(proposed_state.phase) > ROLLOUT_ORDER.index(
                approval.maximum_phase
            ):
                next_state = current
                action = "APPROVAL_PHASE_LIMIT_HOLD"
            else:
                next_state = proposed_state
                action = (
                    "ROLLOUT_ADVANCED"
                    if proposed_state.phase is not current.phase
                    else "EXTERNAL_WINDOW_ACCEPTED"
                )
        self._append(
            previous_event_digest=str(head["event_digest"]),
            action=action,
            state=next_state,
            proposal_digest=stored_proposal.proposal.proposal_digest,
            approval_digest=approval.artifact_digest,
            evidence_digest=window.evidence_digest,
            evidence_state=window.evidence_state,
            linked_artifacts=(
                ("proposal", stored_proposal.artifact_digest),
                ("approval", approval.artifact_digest),
                ("rollout_evidence", window.evidence_digest),
            ),
        )
        return self.status()

    def rollback(self, reason: RollbackReason) -> dict[str, Any]:
        head = self._events()[-1]
        return self._rollback_from_head(
            head, _state(head["state"]), reason, action="OPERATOR_ROLLBACK"
        )

    def _rollback_from_head(
        self,
        head: Mapping[str, Any],
        current: RolloutState,
        reason: RollbackReason,
        *,
        action: str,
    ) -> dict[str, Any]:
        if (
            current.candidate_digest is None
            and current.serving_digest == current.baseline_digest
            and current.rollback_reason is reason
        ):
            return self.status()
        next_state = ProgressiveRolloutController(
            current, required_windows=self.required_windows
        ).rollback(reason)
        self._append(
            previous_event_digest=str(head["event_digest"]),
            action=action,
            state=next_state,
            proposal_digest=(
                str(head["proposal_digest"])
                if head.get("proposal_digest") is not None
                else None
            ),
            approval_digest=(
                str(head["approval_digest"])
                if head.get("approval_digest") is not None
                else None
            ),
            evidence_digest=None,
            evidence_state=None,
        )
        return self.status()


@dataclass(frozen=True)
class _RuntimeRegistration:
    principal_digest: str
    service: CacheSloControlService


class CacheSloRuntimeRegistry:
    """Closed registry; request material cannot construct controllers."""

    def __init__(self) -> None:
        self._registrations: dict[tuple[str, str, str], _RuntimeRegistration] = {}

    def register(
        self, service: CacheSloControlService, *, principal_digest: str
    ) -> None:
        principal = require_digest(principal_digest)
        if principal != service.principal_digest:
            raise PermissionDenied("SLO runtime principal binding is invalid")
        key = (service.tenant_id, service.project_id, service.controller_id)
        registration = _RuntimeRegistration(principal, service)
        existing = self._registrations.get(key)
        if existing is not None and existing != registration:
            raise IdempotencyConflict("SLO runtime registration already exists")
        self._registrations[key] = registration

    def service(
        self,
        tenant_id: str,
        project_id: str,
        controller_id: str,
        principal_digest: str,
    ) -> CacheSloControlService:
        principal = require_digest(principal_digest)
        registration = self._registrations.get(
            (
                _identifier(tenant_id, "tenant_id"),
                _identifier(project_id, "project_id"),
                _identifier(controller_id, "controller_id"),
            )
        )
        if registration is None or registration.principal_digest != principal:
            raise NotFound("SLO controller does not exist")
        if registration.service.principal_digest != principal:
            raise NotFound("SLO controller does not exist")
        return registration.service


def _dependency_source_kind(source_kind: str) -> str:
    """Namespace for dependency edges of one semantic identity."""

    return f"{source_kind}-dependency"


def _rollout_evidence_payload(evidence: RolloutEvidence) -> dict[str, Any]:
    return {
        "parity_report": evidence.parity_report.to_dict(),
        "provider_accounting_matches": evidence.provider_accounting_matches,
        "worst_cohort_regressed": evidence.worst_cohort_regressed,
        "unknown_outcome_rate": evidence.unknown_outcome_rate,
        "unknown_outcome_budget": evidence.unknown_outcome_budget,
        "out_of_distribution": evidence.out_of_distribution,
        "cost_guardrail_passed": evidence.cost_guardrail_passed,
        "clean_fallback_exercised": evidence.clean_fallback_exercised,
        "rollback_exercised": evidence.rollback_exercised,
    }


def _parity_report_digest(report: ParityReport) -> str:
    """Recompute the evaluator-owned digest without trusting its receipt field."""

    return digest_of(
        {
            "schema_version": SLO_SCHEMA_VERSION,
            "report_id": report.report_id,
            "decision": str(report.decision),
            "binding": report.binding.to_dict(),
            "metrics": dict(sorted(report.metrics.items())),
            "cohorts": {
                cohort: dict(sorted(values.items()))
                for cohort, values in sorted(report.cohorts.items())
            },
            "checks": [check.to_dict() for check in report.checks],
            "scenarios": [scenario.to_dict() for scenario in report.scenarios],
            "failures": list(report.failures),
            "missing": list(report.missing),
            "thresholds": asdict(report.thresholds),
        }
    )


def _state(value: object) -> RolloutState:
    if not isinstance(value, Mapping):
        raise ContractViolation("SLO rollout state must be an object")
    expected = {
        "schema_version",
        "baseline_digest",
        "candidate_digest",
        "serving_digest",
        "phase",
        "consecutive_passes",
        "epoch",
        "rollback_reason",
    }
    if set(value) != expected or value.get("schema_version") != SLO_SCHEMA_VERSION:
        raise ContractViolation("SLO rollout state has an invalid shape")
    rollback = value.get("rollback_reason")
    return RolloutState(
        baseline_digest=str(value["baseline_digest"]),
        candidate_digest=(
            None if value.get("candidate_digest") is None else str(value["candidate_digest"])
        ),
        serving_digest=str(value["serving_digest"]),
        phase=RolloutPhase(str(value["phase"])),
        consecutive_passes=_integer(value["consecutive_passes"], "consecutive_passes"),
        epoch=_integer(value["epoch"], "epoch"),
        rollback_reason=None if rollback is None else RollbackReason(str(rollback)),
    )


def _document(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        parsed = json.loads(value)
    elif isinstance(value, Mapping):
        parsed = dict(value)
    else:
        raise ContractViolation("SLO event document has an unsupported database type")
    if not isinstance(parsed, dict):
        raise ContractViolation("SLO event document must be an object")
    return parsed


def _require_ed25519(verifier: ProvenanceSigner) -> ProvenanceSigner:
    checked = require_asymmetric(verifier)
    if checked.algorithm != "ed25519":
        raise ProvenanceInvalid(
            "SLO trust roots must use Ed25519", algorithm=checked.algorithm
        )
    return checked


def _validity_window(
    statement: Mapping[str, Any],
    *,
    now: float,
    maximum_ttl: int,
    subject: str,
) -> None:
    issued_at = _statement_timestamp(statement, "issued_at")
    expires_at = _statement_timestamp(statement, "expires_at")
    if (
        expires_at <= issued_at
        or expires_at - issued_at > maximum_ttl
        or now < issued_at - SLO_CLOCK_SKEW_SECONDS
        or now >= expires_at
    ):
        raise ProvenanceInvalid(f"{subject} is outside its validity window")


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(f"{field} must be a bounded identifier", field=field)
    return value


def _timestamp(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContractViolation(f"{field} must be a numeric timestamp", field=field)
    result = float(value)
    if result < 0 or result != result or result in {float("inf"), float("-inf")}:
        raise ContractViolation(
            f"{field} must be a finite non-negative timestamp", field=field
        )
    return result


def _statement_timestamp(statement: Mapping[str, Any], field: str) -> float:
    try:
        value = statement[field]
    except KeyError as exc:
        raise ProvenanceInvalid(f"SLO statement is missing {field}") from exc
    try:
        return _timestamp(value, field)
    except ContractViolation as exc:
        raise ProvenanceInvalid(f"SLO statement {field} is invalid") from exc


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"{field} must be an integer", field=field)
    return value


__all__ = [
    "CacheSloControlService",
    "CacheSloRuntimeRegistry",
    "SLO_APPROVAL_DECISION",
    "SLO_APPROVAL_KIND",
    "SLO_EVIDENCE_MAX_TTL_SECONDS",
    "SLO_OBSERVATION_ATTESTATION_KIND",
    "SLO_OBSERVATION_MAX_TTL_SECONDS",
    "SLO_ROLLOUT_EVIDENCE_ATTESTATION_KIND",
    "SloApprovalResolver",
    "SloEvidenceState",
    "StaticSloApprovalResolver",
    "TrustedRolloutWindow",
    "TrustedTuningObservation",
    "slo_approval_statement",
    "slo_observation_artifact",
    "slo_observation_statement",
    "slo_rollout_evidence_artifact",
    "slo_rollout_evidence_statement",
    "slo_scope_digest",
]
