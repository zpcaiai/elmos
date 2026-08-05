#!/usr/bin/env python3
"""The conservative certification gate.

The gate answers one question: *given the evidence that actually exists right
now, what is the highest status this scope may hold?*  Two properties matter:

* A caller can never raise a status by editing a status field.  The status is
  **derived** from evidence and the request's declared status is only ever used
  as a ceiling to compare against.
* Every issued certificate binds the input digests it covers.  If an input
  changes, the certificate is stale by construction, not by convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable

from scripts.modernization_b01_44.canonical import digest, format_instant, is_digest, parse_instant
from scripts.modernization_b01_44.errors import (
    CertificationBlocked,
    EvidenceExpired,
    EvidenceMissing,
    UpstreamCertificateMissing,
)
from scripts.modernization_b01_44.evidence import EvidenceStore
from scripts.modernization_b01_44.policy import PolicyEngine

#: Status lattice, weakest first.  ``blocked`` and ``revoked`` are terminal.
STATUS_ORDER = ("blocked", "revoked", "stale", "experimental", "limited", "certified")

#: Evidence classes each status requires before policy is applied.  The
#: ``certified`` row is deliberately *incomplete*: holdout and representative
#: workload are added by ``certification.yaml``, so relaxing the policy file
#: measurably relaxes the gate instead of being decorative.
BASE_REQUIRED_EVIDENCE: dict[str, frozenset[str]] = {
    "experimental": frozenset({"schema-conformance"}),
    "limited": frozenset({"schema-conformance", "development-corpus", "negative-corpus"}),
    "certified": frozenset(
        {
            "schema-conformance",
            "development-corpus",
            "negative-corpus",
            "independent-review",
        }
    ),
}

#: Policy flag -> the evidence scope it makes mandatory for ``certified``.
POLICY_EVIDENCE_FLAGS = {
    "holdout_required_for_certified": "holdout-corpus",
    "representative_workload_required": "representative-workload",
}


def required_evidence(status: str, policy: dict[str, Any] | None = None) -> frozenset[str]:
    """Evidence required for ``status`` under ``policy``."""

    base = BASE_REQUIRED_EVIDENCE.get(status, frozenset())
    if status != "certified":
        return base
    extra = {
        scope
        for flag, scope in POLICY_EVIDENCE_FLAGS.items()
        if (policy or {}).get(flag, True)
    }
    return base | extra


#: Backwards-compatible view under the default (strictest) policy.
REQUIRED_EVIDENCE: dict[str, frozenset[str]] = {
    status: required_evidence(status) for status in BASE_REQUIRED_EVIDENCE
}

DEFAULT_TTL = timedelta(days=90)


def status_rank(status: str) -> int:
    try:
        return STATUS_ORDER.index(status)
    except ValueError:
        raise CertificationBlocked("unknown certification status", status=status) from None


@dataclass(frozen=True)
class Certificate:
    certificate_id: str
    batch: int
    status: str
    scope: str
    input_digests: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    issued_at: str
    expires_at: str
    limitations: tuple[str, ...]
    signature: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "certificate_id": self.certificate_id,
            "batch": self.batch,
            "status": self.status,
            "scope": self.scope,
            "input_digests": list(self.input_digests),
            "evidence_refs": list(self.evidence_refs),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "limitations": list(self.limitations),
        }
        if self.signature is not None:
            payload["signature"] = self.signature
        return payload

    def is_expired(self, now: datetime) -> bool:
        return parse_instant(self.expires_at, "expires_at") <= now

    def covers(self, input_digests: Iterable[str]) -> bool:
        return set(input_digests) <= set(self.input_digests)


@dataclass
class GateDecision:
    granted_status: str
    requested_status: str
    satisfied: tuple[str, ...]
    missing: tuple[str, ...]
    limitations: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def downgraded(self) -> bool:
        return status_rank(self.granted_status) < status_rank(self.requested_status)

    def as_dict(self) -> dict[str, Any]:
        return {
            "granted_status": self.granted_status,
            "requested_status": self.requested_status,
            "satisfied": list(self.satisfied),
            "missing": list(self.missing),
            "limitations": list(self.limitations),
            "reasons": list(self.reasons),
            "downgraded": self.downgraded,
        }


class CertificateRegistry:
    """Certificates are platform-wide: Batch N+1 must see Batch N's issuance."""

    def __init__(self) -> None:
        self.by_id: dict[str, Certificate] = {}
        self.by_scope: dict[tuple[int, str], str] = {}

    def put(self, certificate: Certificate) -> Certificate:
        self.by_id[certificate.certificate_id] = certificate
        self.by_scope[(certificate.batch, certificate.scope)] = certificate.certificate_id
        return certificate

    def __len__(self) -> int:
        return len(self.by_id)


class CertificationGate:
    """Derive a status from evidence and issue bound certificates."""

    def __init__(
        self,
        policy: PolicyEngine,
        store: EvidenceStore,
        certificates: CertificateRegistry | None = None,
    ) -> None:
        self.policy = policy
        self.store = store
        self.registry = certificates if certificates is not None else CertificateRegistry()

    @property
    def _certificates(self) -> dict[str, Certificate]:
        return self.registry.by_id

    @property
    def _by_scope(self) -> dict[tuple[int, str], str]:
        return self.registry.by_scope

    # -- evaluation -------------------------------------------------------

    def evaluate(
        self,
        *,
        requested_status: str,
        scope: str,
        evidence_refs: Iterable[str],
        now: datetime,
    ) -> GateDecision:
        """Derive the highest defensible status.  Never trusts the request."""

        status_rank(requested_status)
        cert_policy = self.policy.certification_policy
        require_execution = not self.policy.evidence_first.get("model_claim_is_evidence", False)

        satisfied: set[str] = set()
        reasons: list[str] = []
        limitations: list[str] = []

        for evidence_id in sorted(set(evidence_refs)):
            try:
                item = self.store.get(evidence_id)
            except EvidenceMissing:
                reasons.append(f"evidence-absent:{evidence_id}")
                continue
            if self.store.invalidation_reason(evidence_id) is not None:
                reasons.append(f"evidence-invalidated:{evidence_id}")
                continue
            if item.is_expired(now):
                reasons.append(f"evidence-expired:{evidence_id}")
                continue
            if require_execution and not item.is_execution_grade():
                reasons.append(f"evidence-not-execution-grade:{evidence_id}")
                limitations.append(f"{item.scope} rests on {item.trust_level} input")
                continue
            satisfied.add(item.scope)

        if cert_policy.get("evidence_digest_required", True):
            for evidence_id in sorted(set(evidence_refs)):
                try:
                    item = self.store.get(evidence_id)
                except EvidenceMissing:
                    continue
                if not is_digest(item.digest):
                    reasons.append(f"evidence-digest-malformed:{evidence_id}")

        granted = "blocked"
        for candidate in ("experimental", "limited", "certified"):
            if required_evidence(candidate, cert_policy) <= satisfied:
                granted = candidate
        for flag, scope in sorted(POLICY_EVIDENCE_FLAGS.items()):
            if cert_policy.get(flag, True) and granted == "certified" and scope not in satisfied:
                granted = "limited"
                reasons.append(f"{scope}-required-for-certified")

        # Conservative: never exceed what was asked for, never trust the ask.
        if status_rank(granted) > status_rank(requested_status):
            granted = requested_status
            reasons.append("capped-at-requested-status")

        missing = tuple(sorted(required_evidence(requested_status, cert_policy) - satisfied))
        if missing:
            reasons.append("missing-evidence")
        return GateDecision(
            granted_status=granted,
            requested_status=requested_status,
            satisfied=tuple(sorted(satisfied)),
            missing=missing,
            limitations=tuple(sorted(set(limitations))),
            reasons=tuple(sorted(set(reasons))),
        )

    # -- issuance ---------------------------------------------------------

    def issue(
        self,
        *,
        batch: int,
        scope: str,
        requested_status: str,
        evidence_refs: Iterable[str],
        input_digests: Iterable[str],
        now: datetime,
        ttl: timedelta = DEFAULT_TTL,
    ) -> tuple[Certificate, GateDecision]:
        refs = tuple(sorted(set(evidence_refs)))
        digests = tuple(sorted(set(input_digests)))
        for value in digests:
            if not is_digest(value):
                raise CertificationBlocked("input digest is malformed", digest=value)
        decision = self.evaluate(
            requested_status=requested_status, scope=scope, evidence_refs=refs, now=now
        )
        if decision.granted_status in ("blocked", "revoked"):
            raise CertificationBlocked(
                "gate refused to issue a certificate",
                scope=scope,
                batch=batch,
                reasons=list(decision.reasons),
                missing=list(decision.missing),
            )
        certificate_id = "cert-" + digest(
            {
                "batch": batch,
                "scope": scope,
                "status": decision.granted_status,
                "evidence": list(refs),
                "inputs": list(digests),
                "issued_at": format_instant(now),
            }
        )[:32]
        certificate = Certificate(
            certificate_id=certificate_id,
            batch=batch,
            status=decision.granted_status,
            scope=scope,
            input_digests=digests,
            evidence_refs=refs,
            issued_at=format_instant(now),
            expires_at=format_instant(now + ttl),
            limitations=decision.limitations,
        )
        self.registry.put(certificate)
        return certificate, decision

    # -- lookup and lifecycle --------------------------------------------

    def get(self, certificate_id: str) -> Certificate:
        try:
            return self._certificates[certificate_id]
        except KeyError:
            raise UpstreamCertificateMissing(
                "certificate is not present", certificate_id=certificate_id
            ) from None

    def for_scope(self, batch: int, scope: str) -> Certificate | None:
        certificate_id = self._by_scope.get((batch, scope))
        return self._certificates.get(certificate_id) if certificate_id else None

    def require_upstream(
        self,
        *,
        batch: int,
        certificate_refs: Iterable[str],
        now: datetime,
        minimum_status: str = "limited",
    ) -> list[Certificate]:
        """Refuse to run a batch whose upstream is absent, stale or too weak."""

        upstream_batch = batch - 1
        if upstream_batch < 1:
            return []
        refs = list(certificate_refs)
        if not refs:
            raise UpstreamCertificateMissing(
                "no upstream certificate was presented", batch=batch, upstream=upstream_batch
            )
        resolved: list[Certificate] = []
        for ref in refs:
            certificate = self.get(ref)
            if certificate.batch != upstream_batch:
                raise UpstreamCertificateMissing(
                    "certificate does not belong to the immediate upstream batch",
                    batch=batch,
                    expected_upstream=upstream_batch,
                    presented=certificate.batch,
                )
            if certificate.is_expired(now):
                raise CertificationBlocked(
                    "upstream certificate has expired",
                    certificate_id=ref,
                    expires_at=certificate.expires_at,
                )
            if status_rank(certificate.status) < status_rank(minimum_status):
                raise CertificationBlocked(
                    "upstream certificate status is below the required minimum",
                    certificate_id=ref,
                    status=certificate.status,
                    minimum=minimum_status,
                )
            resolved.append(certificate)
        return resolved

    def mark_stale(self, certificate_id: str, reason: str) -> Certificate:
        current = self.get(certificate_id)
        stale = Certificate(
            certificate_id=current.certificate_id,
            batch=current.batch,
            status="stale",
            scope=current.scope,
            input_digests=current.input_digests,
            evidence_refs=current.evidence_refs,
            issued_at=current.issued_at,
            expires_at=current.expires_at,
            limitations=tuple(sorted(set(current.limitations) | {f"stale:{reason}"})),
        )
        self._certificates[certificate_id] = stale
        return stale

    def revoke(self, certificate_id: str, reason: str) -> Certificate:
        current = self.get(certificate_id)
        revoked = Certificate(
            certificate_id=current.certificate_id,
            batch=current.batch,
            status="revoked",
            scope=current.scope,
            input_digests=current.input_digests,
            evidence_refs=current.evidence_refs,
            issued_at=current.issued_at,
            expires_at=current.expires_at,
            limitations=tuple(sorted(set(current.limitations) | {f"revoked:{reason}"})),
        )
        self._certificates[certificate_id] = revoked
        return revoked

    def sweep_expired_evidence(self, now: datetime) -> list[str]:
        """Recertification trigger: any certificate resting on expired evidence."""

        affected: list[str] = []
        for certificate_id, certificate in sorted(self._certificates.items()):
            if certificate.status in ("stale", "revoked", "blocked"):
                continue
            for evidence_id in certificate.evidence_refs:
                try:
                    item = self.store.get(evidence_id)
                except EvidenceMissing:
                    self.mark_stale(certificate_id, "evidence-absent")
                    affected.append(certificate_id)
                    break
                if item.is_expired(now) or self.store.invalidation_reason(evidence_id):
                    self.mark_stale(certificate_id, "evidence-expired")
                    affected.append(certificate_id)
                    break
            else:
                if certificate.is_expired(now):
                    self.mark_stale(certificate_id, "certificate-expired")
                    affected.append(certificate_id)
        return affected

    def invalidate_on_input_change(self, new_input_digests: Iterable[str]) -> list[str]:
        """Any certificate not covering the new inputs becomes stale."""

        digests = set(new_input_digests)
        affected: list[str] = []
        for certificate_id, certificate in sorted(self._certificates.items()):
            if certificate.status in ("stale", "revoked", "blocked"):
                continue
            if not certificate.covers(digests):
                self.mark_stale(certificate_id, "input-digest-changed")
                affected.append(certificate_id)
        return affected


def evidence_expiry_guard(store: EvidenceStore, evidence_refs: Iterable[str], now: datetime) -> None:
    """Raise :class:`EvidenceExpired` on the first expired reference."""

    for evidence_id in evidence_refs:
        item = store.get(evidence_id)
        if item.is_expired(now):
            raise EvidenceExpired(
                "evidence expired", evidence_id=evidence_id, expires_at=item.expires_at
            )
