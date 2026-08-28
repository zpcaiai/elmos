"""Fail-closed intake for an independent, signed security review."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

from .errors import ContractViolation
from .evidence import EvidenceTrustStore, SignatureEnvelope
from .models import canonical_json, digest_of


@dataclass(frozen=True, slots=True)
class SecurityReviewRequest:
    """A durable request that remains NOT_RUN until an external reviewer acts."""

    scope_digest: str
    artifact_digest: str
    executor_id: str
    authorization_ref: str
    requested_at: str
    status: str = "NOT_RUN"

    def __post_init__(self) -> None:
        for name, value in (("scope_digest", self.scope_digest), ("artifact_digest", self.artifact_digest)):
            if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
                raise ContractViolation(f"security review {name} must be digest-bound")
        if not self.executor_id or not self.authorization_ref or not self.requested_at:
            raise ContractViolation("security review request provenance is incomplete")
        if self.status != "NOT_RUN":
            raise ContractViolation("new security review requests must remain NOT_RUN")

    @property
    def request_digest(self) -> str:
        return digest_of(
            {
                "scope_digest": self.scope_digest,
                "artifact_digest": self.artifact_digest,
                "executor_id": self.executor_id,
                "authorization_ref": self.authorization_ref,
                "requested_at": self.requested_at,
                "status": self.status,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "scope_digest": self.scope_digest,
            "artifact_digest": self.artifact_digest,
            "executor_id": self.executor_id,
            "authorization_ref": self.authorization_ref,
            "requested_at": self.requested_at,
            "status": self.status,
            "request_digest": self.request_digest,
            "certification": "NOT_CERTIFIED",
        }


@dataclass(frozen=True, slots=True)
class SecurityReviewAcceptance:
    status: str
    reviewer_id: str
    report_digest: str
    findings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status not in {"READY_FOR_EXTERNAL_GATE", "REJECTED"} or not self.reviewer_id:
            raise ContractViolation("security review acceptance is invalid")

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reviewer_id": self.reviewer_id,
            "report_digest": self.report_digest,
            "findings": list(self.findings),
            "certification": "NOT_CERTIFIED",
        }


class IndependentSecurityReviewIntake:
    """Verify a report signed by a distinct security-reviewer trust key."""

    _REPORT_FIELDS: ClassVar[frozenset[str]] = frozenset({
        "schema_version",
        "review_id",
        "scope_digest",
        "artifact_digest",
        "reviewer_id",
        "executor_id",
        "authorization_ref",
        "decision",
        "critical_findings",
        "high_findings",
        "findings_digest",
        "completed_at",
        "expires_at",
        "signature",
    })

    def __init__(self, trust_store: EvidenceTrustStore) -> None:
        self.trust_store = trust_store

    def accept(
        self,
        report: Mapping[str, Any],
        *,
        expected_scope_digest: str,
        expected_artifact_digest: str,
        executor_id: str,
        now: datetime | None = None,
    ) -> SecurityReviewAcceptance:
        if set(report) != self._REPORT_FIELDS:
            raise ContractViolation("security review report shape is not exact")
        if report.get("schema_version") != "1.0":
            raise ContractViolation("security review report schema is unsupported")
        if (
            report.get("scope_digest") != expected_scope_digest
            or report.get("artifact_digest") != expected_artifact_digest
        ):
            raise ContractViolation("security review report is bound to a different scope or artifact")
        if report.get("executor_id") != executor_id:
            raise ContractViolation("security review executor binding is invalid")
        reviewer_id = str(report.get("reviewer_id", ""))
        if not reviewer_id or reviewer_id == executor_id:
            raise ContractViolation("security review must be performed by a distinct reviewer")
        if not str(report.get("authorization_ref", "")).strip():
            raise ContractViolation("security review authorization is required")
        if report.get("decision") not in {"PASS", "FAIL", "INCONCLUSIVE"}:
            raise ContractViolation("security review decision is invalid")
        critical = _nonnegative_int(report.get("critical_findings"))
        high = _nonnegative_int(report.get("high_findings"))
        if not isinstance(report.get("findings_digest"), str) or not report["findings_digest"].startswith(
            "sha256:"
        ):
            raise ContractViolation("security review findings must be digest-bound")
        _parse_expiry(report.get("completed_at"), field="completed_at")
        expires_at = _parse_expiry(report.get("expires_at"), field="expires_at")
        current = now or datetime.now(UTC)
        if expires_at <= current:
            raise ContractViolation("security review report is expired")
        signature = report.get("signature")
        if not isinstance(signature, Mapping) or set(signature) != {"algorithm", "key_id", "signature"}:
            raise ContractViolation("security review signature envelope is invalid")
        envelope = SignatureEnvelope(
            str(signature["algorithm"]), str(signature["key_id"]), str(signature["signature"])
        )
        unsigned = {key: value for key, value in report.items() if key != "signature"}
        verified_actor = self.trust_store.verify(
            canonical_json(unsigned).encode("utf-8"), envelope, required_role="security_reviewer"
        )
        if verified_actor != reviewer_id:
            raise ContractViolation("security review signer does not match reviewer identity")
        report_digest = digest_of(dict(report))
        findings: list[str] = []
        if critical:
            findings.append("CRITICAL_FINDINGS_PRESENT")
        if high:
            findings.append("HIGH_FINDINGS_PRESENT")
        decision = (
            "READY_FOR_EXTERNAL_GATE" if report.get("decision") == "PASS" and not findings else "REJECTED"
        )
        return SecurityReviewAcceptance(decision, reviewer_id, report_digest, tuple(findings))


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ContractViolation("security review finding count is invalid")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ContractViolation("security review finding count is invalid") from error
    if result < 0:
        raise ContractViolation("security review finding count is invalid")
    return result


def _parse_expiry(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ContractViolation(f"security review {field} is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ContractViolation(f"security review {field} is invalid") from error
    if parsed.tzinfo is None:
        raise ContractViolation(f"security review {field} must include a timezone")
    return parsed.astimezone(UTC)
