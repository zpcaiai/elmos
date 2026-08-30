"""Conservative E0-E5 evidence gate."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol, TypeVar, cast

from .canonical import canonical_json_bytes, require_digest, to_jsonable
from .contracts import (
    Evidence,
    EvidenceStatus,
    GateLevel,
    Obligation,
    ObligationStatus,
    Scope,
    utc_now,
)
from .errors import ContractError

_REQUIRED_CATEGORIES: Mapping[GateLevel, frozenset[str]] = {
    GateLevel.E0: frozenset({"INGESTION", "MANIFEST_INTEGRITY"}),
    GateLevel.E1: frozenset({"INGESTION", "MANIFEST_INTEGRITY", "SYNTAX", "BUILD"}),
    GateLevel.E2: frozenset({"INGESTION", "MANIFEST_INTEGRITY", "SYNTAX", "BUILD", "UNIT_TEST", "INTEGRATION_TEST"}),
    GateLevel.E3: frozenset(
        {
            "INGESTION",
            "MANIFEST_INTEGRITY",
            "SYNTAX",
            "BUILD",
            "UNIT_TEST",
            "INTEGRATION_TEST",
            "SECURITY",
            "ISOLATION",
            "AUTHORIZATION",
        }
    ),
    GateLevel.E4: frozenset(
        {
            "INGESTION",
            "MANIFEST_INTEGRITY",
            "SYNTAX",
            "BUILD",
            "UNIT_TEST",
            "INTEGRATION_TEST",
            "SECURITY",
            "ISOLATION",
            "AUTHORIZATION",
            "DIFFERENTIAL_RUNTIME",
            "REPRESENTATIVE_WORKLOAD",
        }
    ),
    GateLevel.E5: frozenset(
        {
            "INGESTION",
            "MANIFEST_INTEGRITY",
            "SYNTAX",
            "BUILD",
            "UNIT_TEST",
            "INTEGRATION_TEST",
            "SECURITY",
            "ISOLATION",
            "AUTHORIZATION",
            "DIFFERENTIAL_RUNTIME",
            "REPRESENTATIVE_WORKLOAD",
            "FORMAL_PROOF",
            "PROVENANCE",
            "INDEPENDENT_REVIEW",
        }
    ),
}
_DEFAULT_MAX_EVIDENCE_RECORDS = 512
_DEFAULT_MAX_OBLIGATIONS = 256
_DEFAULT_MAX_REVOKED_AUTHORIZATIONS = 4_096
_DEFAULT_MAX_GATE_INPUT_BYTES = 8 * 1_048_576

_RecordT = TypeVar("_RecordT")


@dataclass(frozen=True, slots=True)
class GateDecision:
    gate: GateLevel
    passed: bool
    status: str
    subject_digest: str
    scope_digest: str
    evidence_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    evaluated_at: datetime
    certification_status: str = "NOT_CERTIFIED"

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], to_jsonable(self))


class TrustedEvidenceVerifier(Protocol):
    """Independent host seam for signature, artifact and revocation checks."""

    def verify(
        self,
        evidence: Evidence,
        *,
        scope: Scope,
        subject_digest: str,
        authorization_id: str,
        revoked_authorization_ids: frozenset[str],
        now: datetime,
    ) -> None:
        ...


class DenyAllEvidenceVerifier:
    def verify(
        self,
        evidence: Evidence,
        *,
        scope: Scope,
        subject_digest: str,
        authorization_id: str,
        revoked_authorization_ids: frozenset[str],
        now: datetime,
    ) -> None:
        raise ContractError("no trusted evidence verifier is configured", code="EVIDENCE_TRUST_UNAVAILABLE")


class E0E5Gate:
    def __init__(
        self,
        *,
        evidence_verifier: TrustedEvidenceVerifier | None = None,
        clock: Callable[[], datetime] = utc_now,
        max_age: timedelta = timedelta(hours=24),
        max_evidence_records: int = _DEFAULT_MAX_EVIDENCE_RECORDS,
        max_obligations: int = _DEFAULT_MAX_OBLIGATIONS,
        max_revoked_authorizations: int = _DEFAULT_MAX_REVOKED_AUTHORIZATIONS,
        max_input_bytes: int = _DEFAULT_MAX_GATE_INPUT_BYTES,
    ) -> None:
        if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
            raise ContractError("gate max_age must be positive")
        if not callable(clock):
            raise ContractError("gate clock must be callable")
        for label, value in (
            ("max_evidence_records", max_evidence_records),
            ("max_obligations", max_obligations),
            ("max_revoked_authorizations", max_revoked_authorizations),
            ("max_input_bytes", max_input_bytes),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ContractError(f"gate {label} must be a positive integer")
        self.max_age = max_age
        self.max_evidence_records = max_evidence_records
        self.max_obligations = max_obligations
        self.max_revoked_authorizations = max_revoked_authorizations
        self.max_input_bytes = max_input_bytes
        self._evidence_verifier = evidence_verifier or DenyAllEvidenceVerifier()
        self._clock = clock

    @staticmethod
    def _bounded_records(
        values: Iterable[object],
        *,
        expected_type: type[_RecordT],
        label: str,
        max_items: int,
        remaining_bytes: int,
    ) -> tuple[tuple[_RecordT, ...], int]:
        try:
            iterator = iter(values)
        except TypeError as exc:
            raise ContractError(f"gate {label} must be iterable") from exc
        records: list[_RecordT] = []
        consumed_bytes = 0
        for index, record in enumerate(iterator):
            if index >= max_items:
                raise ContractError(f"gate {label} count limit exceeded", code="GATE_INPUT_LIMIT")
            if not isinstance(record, expected_type):
                raise ContractError(f"gate {label} contains an invalid record")
            consumed_bytes += len(canonical_json_bytes(record))
            if consumed_bytes > remaining_bytes:
                raise ContractError(f"gate {label} byte limit exceeded", code="GATE_INPUT_LIMIT")
            records.append(record)
        return tuple(records), consumed_bytes

    def evaluate(
        self,
        gate: GateLevel,
        *,
        scope: Scope,
        subject_digest: str,
        evidence: Iterable[Evidence],
        obligations: Iterable[Obligation] = (),
        authorization_id: str | None,
        revoked_authorization_ids: frozenset[str] = frozenset(),
    ) -> GateDecision:
        if not isinstance(gate, GateLevel):
            raise ContractError("gate must be GateLevel")
        require_digest(subject_digest, "gate.subject_digest")
        current = self._clock()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ContractError("gate clock must return a timezone-aware datetime")
        records, evidence_bytes = self._bounded_records(
            evidence,
            expected_type=Evidence,
            label="evidence",
            max_items=self.max_evidence_records,
            remaining_bytes=self.max_input_bytes,
        )
        obligation_records, obligation_bytes = self._bounded_records(
            obligations,
            expected_type=Obligation,
            label="obligations",
            max_items=self.max_obligations,
            remaining_bytes=self.max_input_bytes - evidence_bytes,
        )
        if not isinstance(revoked_authorization_ids, frozenset):
            raise ContractError("gate revoked_authorization_ids must be a frozenset")
        if len(revoked_authorization_ids) > self.max_revoked_authorizations:
            raise ContractError("gate revoked authorization count limit exceeded", code="GATE_INPUT_LIMIT")
        revoked_bytes = 0
        for revoked_id in revoked_authorization_ids:
            if not isinstance(revoked_id, str):
                raise ContractError("gate revoked authorization identifiers must be text")
            revoked_bytes += len(revoked_id.encode("utf-8"))
            if evidence_bytes + obligation_bytes + revoked_bytes > self.max_input_bytes:
                raise ContractError("gate input byte limit exceeded", code="GATE_INPUT_LIMIT")
        reasons: list[str] = []
        valid_categories: set[str] = set()
        valid_ids: set[str] = set()

        if not authorization_id:
            reasons.append("AUTHORIZATION_MISSING")
        elif authorization_id in revoked_authorization_ids:
            reasons.append("AUTHORIZATION_REVOKED")

        for record in records:
            prefix = record.evidence_id
            if record.scope != scope:
                reasons.append(f"{prefix}:SCOPE_MISMATCH")
                continue
            if record.subject_digest != subject_digest:
                reasons.append(f"{prefix}:SUBJECT_DIGEST_MISMATCH")
                continue
            if record.status is not EvidenceStatus.VERIFIED:
                reasons.append(f"{prefix}:STATUS_{record.status.value}")
                continue
            if record.verifier_id is None or record.verifier_id == record.producer_id:
                reasons.append(f"{prefix}:INDEPENDENCE_MISSING")
                continue
            if record.authorization_id is None or record.authorization_id != authorization_id:
                reasons.append(f"{prefix}:AUTHORIZATION_MISMATCH")
                continue
            if record.authorization_id in revoked_authorization_ids:
                reasons.append(f"{prefix}:AUTHORIZATION_REVOKED")
                continue
            if record.revoked_at is not None:
                reasons.append(f"{prefix}:EVIDENCE_REVOKED")
                continue
            if record.produced_at > current:
                reasons.append(f"{prefix}:FUTURE_TIMESTAMP")
                continue
            if current - record.produced_at > self.max_age:
                reasons.append(f"{prefix}:STALE")
                continue
            if record.expires_at is not None and current >= record.expires_at:
                reasons.append(f"{prefix}:EXPIRED")
                continue
            try:
                self._evidence_verifier.verify(
                    record,
                    scope=scope,
                    subject_digest=subject_digest,
                    authorization_id=authorization_id,
                    revoked_authorization_ids=revoked_authorization_ids,
                    now=current,
                )
            except Exception:
                reasons.append(f"{prefix}:TRUST_VERIFICATION_FAILED")
                continue
            valid_categories.add(record.category)
            valid_ids.add(record.evidence_id)

        for category in sorted(_REQUIRED_CATEGORIES[gate] - valid_categories):
            reasons.append(f"MISSING_CATEGORY:{category}")

        for obligation in obligation_records:
            if not obligation.mandatory:
                continue
            if obligation.status is not ObligationStatus.SATISFIED:
                reasons.append(f"OBLIGATION_{obligation.status.value}:{obligation.obligation_id}")
                continue
            missing = set(obligation.evidence_ids) - valid_ids
            if missing:
                reasons.append(f"OBLIGATION_EVIDENCE_INVALID:{obligation.obligation_id}")

        unique_reasons = tuple(dict.fromkeys(reasons))
        return GateDecision(
            gate=gate,
            passed=not unique_reasons,
            status="PASS" if not unique_reasons else "BLOCKED",
            subject_digest=subject_digest,
            scope_digest=scope.digest,
            evidence_ids=tuple(sorted(valid_ids)),
            reasons=unique_reasons,
            evaluated_at=current,
        )
