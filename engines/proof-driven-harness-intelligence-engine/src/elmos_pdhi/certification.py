"""Conservative E0-E5 evidence evaluation for PDHI.

This module can prepare a digest-bound bundle and a readiness decision.  It
cannot mint production certification: an external, independently authorized
verifier must provide the final evidence and signature through the base
harness certification authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, Protocol, Sequence

from .canonical import digest_object, require_sha256_digest, utc_now
from .contracts import (
    CertificationBundle,
    CertificationLevel,
    CertificationVerdict,
    GateStatus,
)
from .errors import ValidationError


class FindingSeverity(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class ClaimStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    REFUTED = "REFUTED"
    UNKNOWN = "UNKNOWN"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_RUN = "NOT_RUN"
    INVALID = "INVALID"
    STALE = "STALE"
    REVOKED = "REVOKED"
    NOT_REQUIRED = "NOT_REQUIRED"


class ReadinessState(StrEnum):
    BLOCKED = "BLOCKED"
    READY_FOR_EXTERNAL_GATE = "READY_FOR_EXTERNAL_GATE"
    READY_FOR_HUMAN_DECISION = "READY_FOR_HUMAN_DECISION"
    EXTERNALLY_VERIFIED = "EXTERNALLY_VERIFIED"


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    evidence_id: str
    artifact_digest: str
    gate: CertificationLevel
    obligation_id: str
    producer_id: str
    verifier_id: str | None
    status: ClaimStatus
    produced_at: datetime
    input_digests: tuple[str, ...]
    tool_digest: str
    environment_digest: str
    independent: bool = False
    external: bool = False
    authorization_id: str | None = None
    verification_receipt_digest: str | None = None
    expires_at: datetime | None = None
    subject_revision: str | None = None

    def __post_init__(self) -> None:
        for name in ("evidence_id", "obligation_id", "producer_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f"{name} is required", code="INVALID_EVIDENCE_CLAIM")
        if not isinstance(self.gate, CertificationLevel):
            raise ValidationError("gate must be CertificationLevel")
        if not isinstance(self.status, ClaimStatus):
            raise ValidationError("status must be ClaimStatus")
        for name in ("artifact_digest", "tool_digest", "environment_digest"):
            require_sha256_digest(getattr(self, name), field=name)
        if not isinstance(self.input_digests, tuple) or not self.input_digests:
            raise ValidationError("evidence claim requires input digests", code="MISSING_INPUT_DIGESTS")
        for item in self.input_digests:
            require_sha256_digest(item, field="input_digest")
        if len(set(self.input_digests)) != len(self.input_digests):
            raise ValidationError("input digests contain duplicates")
        if self.produced_at.tzinfo is None or self.produced_at.utcoffset() is None:
            raise ValidationError("produced_at must be timezone-aware")
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
                raise ValidationError("expires_at must be timezone-aware")
            if self.expires_at <= self.produced_at:
                raise ValidationError("expires_at must follow produced_at")
        if self.independent:
            if not self.verifier_id or self.verifier_id == self.producer_id:
                raise ValidationError("independent evidence requires a distinct verifier")
        if self.external and not self.authorization_id:
            raise ValidationError("external evidence requires authorization binding")
        if self.verification_receipt_digest is not None:
            require_sha256_digest(
                self.verification_receipt_digest,
                field="verification_receipt_digest",
            )
        if self.subject_revision is not None:
            require_sha256_digest(self.subject_revision, field="subject_revision")

    def is_fresh(
        self,
        *,
        now: datetime,
        maximum_age: timedelta,
        maximum_clock_skew: timedelta,
    ) -> bool:
        """Reject expired, future-dated, or indefinitely old evidence."""

        current = now.astimezone(UTC)
        produced = self.produced_at.astimezone(UTC)
        if produced > current + maximum_clock_skew:
            return False
        if current - produced > maximum_age:
            return False
        return self.expires_at is None or self.expires_at.astimezone(UTC) > current


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str
    severity: FindingSeverity
    summary: str
    evidence_ids: tuple[str, ...]
    resolved: bool = False
    exception_id: str | None = None
    exception_expires_at: datetime | None = None
    compensating_controls: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.finding_id or not self.summary:
            raise ValidationError("finding id and summary are required")
        if not isinstance(self.severity, FindingSeverity):
            raise ValidationError("severity must be FindingSeverity")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValidationError("finding evidence ids contain duplicates")
        if self.exception_id is not None:
            if self.severity is FindingSeverity.P0:
                raise ValidationError("P0 findings cannot be excepted")
            if self.exception_expires_at is None or not self.compensating_controls:
                raise ValidationError("exception requires expiry and compensating controls")
            if self.exception_expires_at.tzinfo is None or self.exception_expires_at.utcoffset() is None:
                raise ValidationError("exception expiry must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ApplicabilityDecision:
    gate: CertificationLevel
    required: bool
    policy_id: str
    policy_digest: str
    approver_id: str
    evidence_id: str
    independent: bool

    def __post_init__(self) -> None:
        if not all(isinstance(item, str) and item.strip() for item in (self.policy_id, self.approver_id, self.evidence_id)):
            raise ValidationError("applicability decision bindings are required")
        require_sha256_digest(self.policy_digest, field="policy_digest")
        if not self.required and not self.independent:
            raise ValidationError("NOT_REQUIRED applicability must be independently approved")


@dataclass(frozen=True, slots=True)
class GateEvaluation:
    gate: CertificationLevel
    status: GateStatus
    evidence_ids: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CertificationDecision:
    bundle: CertificationBundle
    bundle_digest: str
    readiness: ReadinessState
    certification_status: str
    gate_results: Mapping[str, GateEvaluation]
    reasons: tuple[str, ...]
    external_evidence_complete: bool


class EvidenceClaimVerifier(Protocol):
    """Trusted adapter that verifies identity, independence and receipt bytes."""

    def verify(self, claim: EvidenceClaim) -> bool: ...


DEFAULT_OBLIGATIONS: Mapping[CertificationLevel, tuple[str, ...]] = MappingProxyType(
    {
        CertificationLevel.E0: ("repository-readiness", "environment-reproducibility", "toolchain-identity"),
        CertificationLevel.E1: ("static-semantic-integrity", "reference-integrity", "schema-compatibility"),
        CertificationLevel.E2: ("functional-regression", "negative-tests", "corpus-independence"),
        CertificationLevel.E3: ("runtime-equivalence", "side-effect-equivalence", "deterministic-replay"),
        CertificationLevel.E4: ("security", "resilience", "concurrency", "performance"),
        CertificationLevel.E5: ("representative-workload", "rollback", "observability", "operator-approval"),
    }
)


class CertificationEvaluator:
    """Evaluate exact evidence without trusting executor-supplied verdicts."""

    def __init__(
        self,
        obligations: Mapping[CertificationLevel, Sequence[str]] | None = None,
        *,
        verifier: EvidenceClaimVerifier | None = None,
        maximum_evidence_age: timedelta = timedelta(days=30),
        maximum_clock_skew: timedelta = timedelta(minutes=5),
    ) -> None:
        source = DEFAULT_OBLIGATIONS if obligations is None else obligations
        if set(source) != set(CertificationLevel):
            raise ValidationError("obligation map must cover E0-E5")
        normalized: dict[CertificationLevel, tuple[str, ...]] = {}
        for level in CertificationLevel:
            values = tuple(source[level])
            if not values or len(set(values)) != len(values):
                raise ValidationError(f"{level.value} obligations must be nonempty and unique")
            normalized[level] = values
        if maximum_evidence_age <= timedelta(0) or maximum_evidence_age > timedelta(days=365):
            raise ValidationError("maximum_evidence_age must be in (0, 365 days]")
        if maximum_clock_skew < timedelta(0) or maximum_clock_skew > timedelta(hours=1):
            raise ValidationError("maximum_clock_skew must be in [0, 1 hour]")
        self._obligations = MappingProxyType(normalized)
        self._verifier = verifier
        self._maximum_evidence_age = maximum_evidence_age
        self._maximum_clock_skew = maximum_clock_skew

    def evaluate(
        self,
        *,
        project_id: str,
        job_id: str,
        source_revision: str,
        target_revision: str,
        target_level: CertificationLevel,
        claims: Sequence[EvidenceClaim],
        findings: Sequence[Finding] = (),
        applicability: Sequence[ApplicabilityDecision] = (),
        now: datetime | None = None,
    ) -> CertificationDecision:
        current = utc_now() if now is None else now
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValidationError("evaluation time must be timezone-aware")
        for digest_name, digest_value in (("source_revision", source_revision), ("target_revision", target_revision)):
            require_sha256_digest(digest_value, field=digest_name)

        claim_ids: set[str] = set()
        claims_by_gate: dict[CertificationLevel, list[EvidenceClaim]] = {level: [] for level in CertificationLevel}
        for claim in claims:
            if claim.evidence_id in claim_ids:
                raise ValidationError("duplicate evidence id", details={"evidence_id": claim.evidence_id})
            claim_ids.add(claim.evidence_id)
            if claim.subject_revision is not None and claim.subject_revision not in {source_revision, target_revision}:
                raise ValidationError("evidence subject revision is outside certification bundle")
            claims_by_gate[claim.gate].append(claim)

        applicability_by_gate: dict[CertificationLevel, ApplicabilityDecision] = {}
        for decision in applicability:
            if decision.gate in applicability_by_gate:
                raise ValidationError("duplicate applicability decision")
            applicability_by_gate[decision.gate] = decision

        gate_results: dict[str, GateEvaluation] = {}
        evidence_index: dict[str, str] = {}
        all_external = True
        for level in CertificationLevel:
            applicability_decision = applicability_by_gate.get(level)
            if applicability_decision is not None and not applicability_decision.required:
                result = GateEvaluation(
                    level,
                    GateStatus.NOT_REQUIRED,
                    (applicability_decision.evidence_id,),
                    (f"not required by {applicability_decision.policy_id}",),
                )
                gate_results[level.value] = result
                all_external = False
                continue
            gate_claims = claims_by_gate[level]
            required = self._obligations[level]
            by_obligation: dict[str, list[EvidenceClaim]] = {item: [] for item in required}
            extra_obligations: list[str] = []
            for claim in gate_claims:
                if claim.obligation_id in by_obligation:
                    by_obligation[claim.obligation_id].append(claim)
                else:
                    extra_obligations.append(claim.obligation_id)

            reasons: list[str] = []
            selected_ids: list[str] = []
            status = GateStatus.PASS
            for obligation_id in required:
                obligation_claims = by_obligation[obligation_id]
                if not obligation_claims:
                    reasons.append(f"missing evidence for {obligation_id}")
                    status = GateStatus.INSUFFICIENT_EVIDENCE
                    continue
                hard_failures = [item for item in obligation_claims if item.status in {ClaimStatus.FAIL, ClaimStatus.REFUTED}]
                if hard_failures:
                    status = GateStatus.FAIL
                    reasons.append(f"{obligation_id} has refuting evidence")
                    for item in hard_failures:
                        selected_ids.append(item.evidence_id)
                        evidence_index[item.evidence_id] = item.artifact_digest
                    continue
                passing = [
                    item
                    for item in obligation_claims
                    if item.status is ClaimStatus.PASS
                    and item.is_fresh(
                        now=current,
                        maximum_age=self._maximum_evidence_age,
                        maximum_clock_skew=self._maximum_clock_skew,
                    )
                    and item.independent
                    and item.verifier_id != item.producer_id
                    and item.verification_receipt_digest is not None
                    and self._verifier is not None
                    and self._verifier.verify(item)
                ]
                if not passing:
                    if status is not GateStatus.FAIL:
                        status = GateStatus.INSUFFICIENT_EVIDENCE
                    reasons.append(f"{obligation_id} lacks fresh independent PASS evidence")
                    continue
                chosen = sorted(passing, key=lambda item: (not item.external, item.produced_at, item.evidence_id))[0]
                selected_ids.append(chosen.evidence_id)
                evidence_index[chosen.evidence_id] = chosen.artifact_digest
                all_external = all_external and chosen.external
            if extra_obligations:
                reasons.append("unrecognized evidence obligations were ignored: " + ",".join(sorted(set(extra_obligations))))
            gate_results[level.value] = GateEvaluation(level, status, tuple(sorted(set(selected_ids))), tuple(reasons))

        unresolved_p0 = [item for item in findings if item.severity is FindingSeverity.P0 and not item.resolved]
        unresolved_p1 = [
            item
            for item in findings
            if item.severity is FindingSeverity.P1
            and not item.resolved
            and not (
                item.exception_id
                and item.exception_expires_at is not None
                and item.exception_expires_at.astimezone(UTC) > current.astimezone(UTC)
                and item.compensating_controls
            )
        ]
        decision_reasons: list[str] = []
        if unresolved_p0:
            decision_reasons.append("unresolved P0 findings: " + ",".join(item.finding_id for item in unresolved_p0))
        if unresolved_p1:
            decision_reasons.append("unresolved P1 findings: " + ",".join(item.finding_id for item in unresolved_p1))

        statuses = {name: result.status for name, result in gate_results.items()}
        target_index = list(CertificationLevel).index(target_level)
        required_gate_names = {level.value for level in list(CertificationLevel)[: target_index + 1]}
        required_statuses = [statuses[name] for name in required_gate_names]
        if unresolved_p0 or unresolved_p1 or GateStatus.FAIL in required_statuses:
            verdict = CertificationVerdict.FAIL
            readiness = ReadinessState.BLOCKED
        elif GateStatus.INSUFFICIENT_EVIDENCE in required_statuses:
            verdict = CertificationVerdict.INSUFFICIENT_EVIDENCE
            readiness = ReadinessState.BLOCKED
        else:
            # Even verified claims only prepare the immutable PDHI bundle.  The
            # separately authorized base-v3 gate owns external verification and
            # certification; caller-supplied booleans cannot cross that boundary.
            verdict = CertificationVerdict.INSUFFICIENT_EVIDENCE
            readiness = ReadinessState.READY_FOR_EXTERNAL_GATE
            target_result = gate_results[target_level.value]
            if target_result.status is GateStatus.PASS:
                gate_results[target_level.value] = GateEvaluation(
                    target_result.gate,
                    GateStatus.INSUFFICIENT_EVIDENCE,
                    target_result.evidence_ids,
                    target_result.reasons + ("external independently authorized evidence is not complete",),
                )
                statuses[target_level.value] = GateStatus.INSUFFICIENT_EVIDENCE

        if verdict is CertificationVerdict.INSUFFICIENT_EVIDENCE and GateStatus.INSUFFICIENT_EVIDENCE not in statuses.values():
            target_result = gate_results[target_level.value]
            gate_results[target_level.value] = GateEvaluation(
                target_result.gate,
                GateStatus.INSUFFICIENT_EVIDENCE,
                target_result.evidence_ids,
                target_result.reasons + ("external evidence boundary remains open",),
            )
            statuses[target_level.value] = GateStatus.INSUFFICIENT_EVIDENCE

        finding_labels = tuple(
            f"{item.finding_id}:{item.severity.value}:{'resolved' if item.resolved else 'open'}"
            for item in findings
        )
        residual_risks = tuple(
            f"{item.finding_id}:{item.summary}"
            for item in findings
            if not item.resolved and item.severity in {FindingSeverity.P2, FindingSeverity.P3}
        )
        bundle = CertificationBundle(
            project_id=project_id,
            job_id=job_id,
            source_revision=source_revision,
            target_revision=target_revision,
            target_level=target_level,
            gates=statuses,
            findings=finding_labels,
            residual_risks=residual_risks,
            verdict=verdict,
            evidence_index=evidence_index,
        )
        return CertificationDecision(
            bundle=bundle,
            bundle_digest=digest_object(bundle, domain="pdhi-certification-bundle"),
            readiness=readiness,
            certification_status="NOT_CERTIFIED" if readiness is not ReadinessState.EXTERNALLY_VERIFIED else "EXTERNALLY_VERIFIED_NOT_CERTIFIED",
            gate_results=MappingProxyType(dict(gate_results)),
            reasons=tuple(decision_reasons),
            external_evidence_complete=False,
        )


K10_CAPABILITY_BINDINGS: Mapping[str, str] = MappingProxyType(
    {
        "elmos-e0-e5-harness-certification": "CertificationEvaluator.evaluate",
    }
)


__all__ = [
    "ApplicabilityDecision",
    "CertificationDecision",
    "CertificationEvaluator",
    "ClaimStatus",
    "DEFAULT_OBLIGATIONS",
    "EvidenceClaim",
    "EvidenceClaimVerifier",
    "Finding",
    "FindingSeverity",
    "GateEvaluation",
    "K10_CAPABILITY_BINDINGS",
    "ReadinessState",
]
