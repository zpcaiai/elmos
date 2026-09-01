"""Artifact and evidence protocol: content addressing, binding, sealing.

This module owns the rule that makes every downstream gate meaningful: a claim
is worth exactly the evidence bound to it, and evidence is worth exactly the
inputs it was produced from.  Two traps are closed here.  First, a producer
never states its own content address — the :class:`~.ports.ArtifactStore`
hashes the real bytes and that digest is the artifact's identity, so a lying or
buggy producer cannot register bytes under a convenient address.  Second,
evidence carries ``input_digests``: a test report produced against snapshot A
is *stale*, not merely old, when replayed against snapshot B, and
:func:`verify` says so with an explicit code instead of shrugging.

The third trap is quieter and has shipped more often: an unrun check reads like
a passed check.  :class:`Outcome` keeps ``NOT_RUN``, ``SKIPPED`` and ``PARTIAL``
structurally distinct from ``PASS``, and :func:`claim_support` refuses to render
a claim as supported unless every cited evidence verified *and* passed.  A claim
with no evidence at all is ``UNSUPPORTED`` and has no path to ``True``.
"""

from __future__ import annotations

import hmac
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from .contracts import (
    canonical_json,
    digest,
    digest_bytes,
    format_timestamp,
    parse_timestamp,
    reject_unknown_fields,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .ports import ArtifactStore, EventStore
from .registry import register

__all__ = [
    "Artifact",
    "BundleVerification",
    "Claim",
    "ClaimSupport",
    "DEFAULT_SECRET_PATTERNS",
    "Evidence",
    "EvidenceBundle",
    "EvidenceKind",
    "Outcome",
    "Redaction",
    "RedactionPattern",
    "RedactionRecord",
    "SealedBundle",
    "SecurityLabel",
    "VerificationOutcome",
    "VerificationReason",
    "build_matrix",
    "claim_support",
    "default_artifact_store",
    "handle",
    "record_provenance",
    "redact",
    "retention_decision",
    "seal_bundle",
    "set_default_artifact_store",
    "store_artifact",
    "verify",
    "verify_bundle",
]

register_codes(
    Category.INTEGRITY,
    "ARTIFACT_CORRUPT",
    "PROVENANCE_BROKEN",
    "BUNDLE_SEAL_INVALID",
)
register_codes(
    Category.VERIFICATION,
    "EVIDENCE_STALE",
    "CLAIM_UNSUPPORTED",
)
register_codes(
    Category.POLICY,
    "RETENTION_LABEL_UNKNOWN",
    "CROSS_TENANT_CACHE_DENIED",
)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SEAL_ALGORITHM = "hmac-sha256"
_MIN_SEAL_KEY_BYTES = 32
_REDACTED = b"[REDACTED]"


class EvidenceKind(StrEnum):
    """What sort of observation a piece of evidence is.

    The kind is not decoration: the release gate requires specific kinds for
    specific gates, so an execution trace can never be silently accepted where
    a test report was required.
    """

    TEST_REPORT = "test-report"
    POLICY_DECISION = "policy-decision"
    ARTIFACT_HASH = "artifact-hash"
    EXECUTION_TRACE = "execution-trace"
    REVIEW = "review"
    SCAN = "scan"


class Outcome(StrEnum):
    """The verdict a check reached, including the verdicts that are not verdicts.

    ``NOT_RUN`` is not ``PASS`` and is not ``FAIL``: it means nothing was
    observed.  ``SKIPPED`` means a decision was taken not to observe.
    ``PARTIAL`` and ``INTERRUPTED`` mean observation started and did not
    finish.  Only ``PASS`` is a positive result, and :attr:`is_pass` is the one
    place that is decided, so no caller can widen the set by writing
    ``status != FAIL``.
    """

    PASS = "PASS"  # noqa: S105 - a control/verdict name, not a credential
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"
    SKIPPED = "SKIPPED"
    PARTIAL = "PARTIAL"
    INTERRUPTED = "INTERRUPTED"
    BLOCKED = "BLOCKED"
    INFRA_FAILURE = "INFRA_FAILURE"

    @property
    def is_pass(self) -> bool:
        return self is Outcome.PASS

    @property
    def is_observed(self) -> bool:
        """True when the check actually produced a verdict (pass or fail)."""

        return self in (Outcome.PASS, Outcome.FAIL)


class ClaimSupport(StrEnum):
    """How well a claim is backed once its evidence has been verified."""

    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    REFUTED = "REFUTED"

    @property
    def is_supported(self) -> bool:
        return self is ClaimSupport.SUPPORTED


class SecurityLabel(StrEnum):
    """Sensitivity of artifact content; drives retention and cache scope."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class VerificationReason(StrEnum):
    """Why :func:`verify` reached its outcome.

    Every negative reason maps to a registered failure code so that a caller
    that wants to raise does not have to invent one.
    """

    VERIFIED = "VERIFIED"
    EVIDENCE_STALE = "EVIDENCE_STALE"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    DIGEST_MISMATCH = "DIGEST_MISMATCH"
    ARTIFACT_CORRUPT = "ARTIFACT_CORRUPT"
    NO_ARTIFACTS = "EVIDENCE_UNVERIFIABLE"


def _require_digest(value: Any, field_name: str) -> str:
    text = require_str(value, field_name, max_length=128)
    if not _DIGEST_RE.match(text):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name} is not a sha256 content address",
            recommended_action="pass a digest of the form sha256:<64 lowercase hex>",
        )
    return text


def _require_digests(value: Any, field_name: str) -> tuple[str, ...]:
    items = require_str_seq(value, field_name)
    return tuple(_require_digest(item, f"{field_name}[{index}]")
                 for index, item in enumerate(items))


@dataclass(frozen=True, slots=True)
class Artifact:
    """An immutable blob, identified by the digest of its stored bytes.

    ``digest`` is never taken from the producer.  Construct one through
    :func:`store_artifact`, which puts the bytes into the store and adopts the
    address the store computed.  ``redacted``/``redacted_from`` exist because a
    silent redaction breaks the digest chain: if the bytes under a claim change
    and nothing records why, the lineage becomes unexplainable.
    """

    digest: str
    media_type: str
    byte_count: int
    producer: str
    produced_at: datetime
    redacted: bool = False
    redacted_from: str = ""
    redaction_patterns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_digest(self.digest, "artifact.digest")
        require_str(self.media_type, "artifact.media_type", max_length=255)
        require_int(self.byte_count, "artifact.byte_count", minimum=0)
        require_identifier(self.producer, "artifact.producer")
        format_timestamp(self.produced_at)
        if self.redacted and not self.redacted_from:
            raise KernelError(
                code="PROVENANCE_BROKEN",
                message="a redacted artifact must record the digest it was derived from",
                recommended_action="set redacted_from to the pre-redaction digest",
            )
        if self.redacted_from:
            _require_digest(self.redacted_from, "artifact.redacted_from")

    def to_payload(self) -> dict[str, Any]:
        return {
            "digest": self.digest,
            "mediaType": self.media_type,
            "byteCount": self.byte_count,
            "producer": self.producer,
            "producedAt": format_timestamp(self.produced_at),
            "redacted": self.redacted,
            "redactedFrom": self.redacted_from,
            "redactionPatterns": list(self.redaction_patterns),
        }


@dataclass(frozen=True, slots=True)
class Evidence:
    """One observation, bound to the inputs it was produced from.

    ``input_digests`` is the field the rest of the system leans on.  Evidence
    is only about the world it saw: replaying it against a different set of
    inputs is a category error, and :func:`verify` reports ``EVIDENCE_STALE``
    rather than letting a stale pass justify a new snapshot.  ``outcome``
    defaults to ``NOT_RUN`` so that evidence which forgot to state a verdict
    cannot be mistaken for a passing one.
    """

    evidence_id: str
    claim: str
    kind: EvidenceKind
    artifact_digests: tuple[str, ...]
    input_digests: tuple[str, ...]
    producer_id: str
    produced_at: datetime
    environment_fingerprint: str
    outcome: Outcome = Outcome.NOT_RUN

    def __post_init__(self) -> None:
        require_identifier(self.evidence_id, "evidence.evidence_id")
        require_str(self.claim, "evidence.claim")
        if not isinstance(self.kind, EvidenceKind):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"evidence.kind {self.kind!r} is not a known evidence kind",
                recommended_action=f"use one of {sorted(k.value for k in EvidenceKind)}",
            )
        if not isinstance(self.outcome, Outcome):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"evidence.outcome {self.outcome!r} is not a known outcome",
                recommended_action=f"use one of {sorted(o.value for o in Outcome)}",
            )
        for index, item in enumerate(self.artifact_digests):
            _require_digest(item, f"evidence.artifact_digests[{index}]")
        for index, item in enumerate(self.input_digests):
            _require_digest(item, f"evidence.input_digests[{index}]")
        require_identifier(self.producer_id, "evidence.producer_id")
        format_timestamp(self.produced_at)
        require_str(self.environment_fingerprint, "evidence.environment_fingerprint")

    @property
    def binding_digest(self) -> str:
        """Content address of the exact input set this evidence is bound to."""

        return digest({"inputDigests": sorted(self.input_digests)})

    def to_payload(self) -> dict[str, Any]:
        return {
            "evidenceId": self.evidence_id,
            "claim": self.claim,
            "kind": str(self.kind),
            "artifactDigests": list(self.artifact_digests),
            "inputDigests": list(self.input_digests),
            "producerId": self.producer_id,
            "producedAt": format_timestamp(self.produced_at),
            "environmentFingerprint": self.environment_fingerprint,
            "outcome": str(self.outcome),
            "bindingDigest": self.binding_digest,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Evidence:
        """Strictly decode evidence from its wire form."""

        known = {
            "evidenceId", "claim", "kind", "artifactDigests", "inputDigests",
            "producerId", "producedAt", "environmentFingerprint", "outcome",
            "bindingDigest",
        }
        reject_unknown_fields(payload, known, field_name="evidence")
        kind_text = require_str(payload.get("kind"), "evidence.kind", max_length=64)
        if kind_text not in {k.value for k in EvidenceKind}:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown evidence kind {kind_text!r}",
                recommended_action=f"use one of {sorted(k.value for k in EvidenceKind)}",
            )
        outcome_text = require_str(payload.get("outcome", Outcome.NOT_RUN.value),
                                   "evidence.outcome", max_length=32)
        if outcome_text not in {o.value for o in Outcome}:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown evidence outcome {outcome_text!r}",
                recommended_action=f"use one of {sorted(o.value for o in Outcome)}",
            )
        return cls(
            evidence_id=require_identifier(payload.get("evidenceId"), "evidence.evidenceId"),
            claim=require_str(payload.get("claim"), "evidence.claim"),
            kind=EvidenceKind(kind_text),
            artifact_digests=_require_digests(payload.get("artifactDigests", ()),
                                              "evidence.artifactDigests"),
            input_digests=_require_digests(payload.get("inputDigests", ()),
                                           "evidence.inputDigests"),
            producer_id=require_identifier(payload.get("producerId"), "evidence.producerId"),
            produced_at=parse_timestamp(payload.get("producedAt"), "evidence.producedAt"),
            environment_fingerprint=require_str(payload.get("environmentFingerprint"),
                                                "evidence.environmentFingerprint"),
            outcome=Outcome(outcome_text),
        )


@dataclass(frozen=True, slots=True)
class Claim:
    """A statement that wants to be believed, plus the evidence it cites.

    A claim holds *references*, never a verdict.  Whether it is supported is
    computed by :func:`claim_support` against verified evidence, so a claim
    cannot carry its own "supported: true" across a boundary.
    """

    claim_id: str
    statement: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.claim_id, "claim.claim_id")
        require_str(self.statement, "claim.statement")
        for index, item in enumerate(self.evidence_ids):
            require_identifier(item, f"claim.evidence_ids[{index}]")

    @property
    def has_evidence(self) -> bool:
        return bool(self.evidence_ids)

    def to_payload(self) -> dict[str, Any]:
        return {
            "claimId": self.claim_id,
            "statement": self.statement,
            "evidenceIds": list(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    """The result of checking one piece of evidence, with an explicit reason."""

    evidence_id: str
    verified: bool
    reason: VerificationReason
    detail: str
    checked_digests: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "evidenceId": self.evidence_id,
            "verified": self.verified,
            "reason": str(self.reason),
            "detail": self.detail,
            "checkedDigests": list(self.checked_digests),
        }

    def as_error(self) -> KernelError:
        """Render a failed verification as the registered KernelError."""

        if self.verified:
            raise ValueError("a verified outcome has no error form")
        return KernelError(
            code=str(self.reason),
            message=f"evidence {self.evidence_id}: {self.detail}",
            retryable=False,
            evidence_ids=(self.evidence_id,),
            recommended_action="re-produce the evidence against the current inputs",
        )


def store_artifact(store: ArtifactStore, data: bytes, *, media_type: str,
                   producer: str, produced_at: datetime) -> Artifact:
    """Store bytes and mint the artifact at the address the store computed.

    The producer supplies content, never identity.  ``produced_at`` is passed
    in rather than read from a clock so that the same bytes produced at the
    same declared instant give a byte-identical artifact payload on replay.
    """

    if not isinstance(data, (bytes, bytearray)):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="artifact content must be bytes",
            recommended_action="encode the content before storing it",
        )
    payload = bytes(data)
    computed = store.put(payload, media_type=media_type)
    return Artifact(
        digest=computed,
        media_type=media_type,
        byte_count=len(payload),
        producer=producer,
        produced_at=produced_at,
    )


def verify(evidence: Evidence, expected_inputs: Sequence[str],
           store: ArtifactStore) -> VerificationOutcome:
    """Check that evidence still says what it said, about the inputs at hand.

    Order matters.  Binding is checked first: evidence about the wrong inputs
    is stale no matter how intact its blobs are, and reporting a blob problem
    there would send the caller to fix the wrong thing.  Then each artifact is
    fetched and re-hashed, because "the store has a row for that digest" is not
    the same statement as "those bytes still hash to that digest".
    """

    expected = tuple(_require_digest(item, f"expected_inputs[{index}]")
                     for index, item in enumerate(expected_inputs))
    if tuple(sorted(evidence.input_digests)) != tuple(sorted(expected)):
        return VerificationOutcome(
            evidence_id=evidence.evidence_id,
            verified=False,
            reason=VerificationReason.EVIDENCE_STALE,
            detail=(
                "evidence is bound to a different input set "
                f"({evidence.binding_digest}) than the one being justified "
                f"({digest({'inputDigests': sorted(expected)})})"
            ),
        )
    if not evidence.artifact_digests:
        return VerificationOutcome(
            evidence_id=evidence.evidence_id,
            verified=False,
            reason=VerificationReason.NO_ARTIFACTS,
            detail="evidence references no artifact and cannot be re-checked",
        )
    for artifact_digest in evidence.artifact_digests:
        try:
            data = store.get(artifact_digest)
        except KernelError as exc:
            reason = (
                VerificationReason.DIGEST_MISMATCH
                if exc.code == "DIGEST_MISMATCH"
                else VerificationReason.EVIDENCE_MISSING
            )
            return VerificationOutcome(
                evidence_id=evidence.evidence_id,
                verified=False,
                reason=reason,
                detail=f"artifact {artifact_digest}: {exc.message}",
                checked_digests=(artifact_digest,),
            )
        if digest_bytes(data) != artifact_digest:
            return VerificationOutcome(
                evidence_id=evidence.evidence_id,
                verified=False,
                reason=VerificationReason.DIGEST_MISMATCH,
                detail=(
                    f"artifact {artifact_digest} no longer hashes to its address "
                    f"(bytes hash to {digest_bytes(data)})"
                ),
                checked_digests=(artifact_digest,),
            )
    return VerificationOutcome(
        evidence_id=evidence.evidence_id,
        verified=True,
        reason=VerificationReason.VERIFIED,
        detail="input binding intact and every artifact re-hashed to its address",
        checked_digests=tuple(evidence.artifact_digests),
    )


def claim_support(claim: Claim, evidence_by_id: Mapping[str, Evidence],
                  verified_ids: Sequence[str]) -> ClaimSupport:
    """Decide how well a claim is backed — never optimistically.

    A claim with no evidence is ``UNSUPPORTED``; so is a claim whose evidence
    did not verify, and so is a claim whose evidence only ever reported
    ``NOT_RUN`` or ``SKIPPED``.  Only ``PASS`` outcomes, on verified evidence,
    produce ``SUPPORTED``.  A single ``FAIL`` makes the claim ``REFUTED``,
    which outranks the rest: one reproduced failure is not out-voted by other
    checks that happened to pass.
    """

    if not claim.has_evidence:
        return ClaimSupport.UNSUPPORTED
    verified = set(verified_ids)
    cited: list[Evidence] = []
    for evidence_id in claim.evidence_ids:
        found = evidence_by_id.get(evidence_id)
        if found is None or evidence_id not in verified:
            return ClaimSupport.UNSUPPORTED
        cited.append(found)
    if any(item.outcome is Outcome.FAIL for item in cited):
        return ClaimSupport.REFUTED
    if all(item.outcome.is_pass for item in cited):
        return ClaimSupport.SUPPORTED
    return ClaimSupport.UNSUPPORTED


def build_matrix(claims: Sequence[Claim],
                 evidence: Sequence[Evidence]) -> tuple[dict[str, Any], ...]:
    """Build the claim -> evidence -> artifact traceability matrix.

    A claim citing evidence the bundle does not contain is ``PROVENANCE_BROKEN``
    rather than an omitted row: a hole in the matrix must be loud, because the
    matrix is what an auditor reads instead of the code.
    """

    by_id = {item.evidence_id: item for item in evidence}
    rows: list[dict[str, Any]] = []
    for claim in sorted(claims, key=lambda item: item.claim_id):
        links: list[dict[str, Any]] = []
        for evidence_id in claim.evidence_ids:
            found = by_id.get(evidence_id)
            if found is None:
                raise KernelError(
                    code="PROVENANCE_BROKEN",
                    message=(
                        f"claim {claim.claim_id!r} cites evidence {evidence_id!r} "
                        "that is not in the bundle"
                    ),
                    evidence_ids=(evidence_id,),
                    recommended_action="add the evidence to the bundle or drop the citation",
                )
            links.append({
                "evidenceId": found.evidence_id,
                "kind": str(found.kind),
                "outcome": str(found.outcome),
                "artifactDigests": list(found.artifact_digests),
            })
        rows.append({
            "claimId": claim.claim_id,
            "statement": claim.statement,
            "evidence": links,
            "hasEvidence": claim.has_evidence,
        })
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    """Evidence plus claims plus the matrix that ties them together.

    The bundle is snapshot-scoped on purpose (``repo_snapshot_sha``): handing a
    bundle to a gate that is releasing a different snapshot must be detectable
    without re-verifying every artifact.
    """

    bundle_id: str
    repo_snapshot_sha: str
    evidence: tuple[Evidence, ...]
    claims: tuple[Claim, ...] = ()
    produced_at: datetime | None = None
    matrix: tuple[Mapping[str, Any], ...] = field(default=())

    def __post_init__(self) -> None:
        require_identifier(self.bundle_id, "bundle.bundle_id")
        require_str(self.repo_snapshot_sha, "bundle.repo_snapshot_sha", max_length=128)
        seen: set[str] = set()
        for item in self.evidence:
            if item.evidence_id in seen:
                raise KernelError(
                    code="PROVENANCE_BROKEN",
                    message=f"evidence {item.evidence_id!r} appears twice in the bundle",
                    recommended_action="deduplicate evidence before sealing",
                )
            seen.add(item.evidence_id)
        if not self.matrix:
            object.__setattr__(self, "matrix", build_matrix(self.claims, self.evidence))

    def to_payload(self) -> dict[str, Any]:
        return {
            "bundleId": self.bundle_id,
            "repoSnapshotSha": self.repo_snapshot_sha,
            "producedAt": (
                format_timestamp(self.produced_at) if self.produced_at is not None else None
            ),
            "evidence": [item.to_payload()
                         for item in sorted(self.evidence, key=lambda e: e.evidence_id)],
            "claims": [item.to_payload()
                       for item in sorted(self.claims, key=lambda c: c.claim_id)],
            "matrix": [dict(row) for row in self.matrix],
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class SealedBundle:
    """A bundle payload plus the HMAC that proves nobody edited it.

    The payload is kept as the plain mapping that was actually sealed rather
    than as the dataclass, because verification must hash *the bytes that were
    transmitted*, not a re-serialisation of a re-parsed object which could
    quietly normalise away the tamper.
    """

    payload: Mapping[str, Any]
    seal: str
    algorithm: str = _SEAL_ALGORITHM

    def __post_init__(self) -> None:
        require_mapping(self.payload, "sealed.payload")
        require_str(self.seal, "sealed.seal", max_length=256)
        if self.algorithm != _SEAL_ALGORITHM:
            raise KernelError(
                code="BUNDLE_SEAL_INVALID",
                message=f"unsupported seal algorithm {self.algorithm!r}",
                recommended_action=f"use {_SEAL_ALGORITHM}",
            )

    @property
    def bundle_digest(self) -> str:
        return digest(self.payload)

    def to_payload(self) -> dict[str, Any]:
        return {
            "payload": dict(self.payload),
            "seal": self.seal,
            "algorithm": self.algorithm,
        }


@dataclass(frozen=True, slots=True)
class BundleVerification:
    """Outcome of checking a bundle seal, plus the facts a gate may then use."""

    valid: bool
    reason: str
    bundle_id: str = ""
    repo_snapshot_sha: str = ""
    evidence_kinds: tuple[tuple[str, str], ...] = ()
    evidence_outcomes: tuple[tuple[str, str], ...] = ()
    artifact_digests: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "reason": self.reason,
            "bundleId": self.bundle_id,
            "repoSnapshotSha": self.repo_snapshot_sha,
            "evidenceKinds": [{"evidenceId": eid, "kind": kind}
                              for eid, kind in self.evidence_kinds],
            "evidenceOutcomes": [{"evidenceId": eid, "outcome": outcome}
                                 for eid, outcome in self.evidence_outcomes],
            "artifactDigests": list(self.artifact_digests),
        }


def _check_key(key: bytes) -> bytes:
    if not isinstance(key, (bytes, bytearray)) or len(key) < _MIN_SEAL_KEY_BYTES:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"seal key must be at least {_MIN_SEAL_KEY_BYTES} bytes",
            recommended_action="supply a 32-byte or longer key from the secret binding",
        )
    return bytes(key)


def seal_bundle(bundle: EvidenceBundle, *, key: bytes) -> SealedBundle:
    """Seal a bundle with HMAC-SHA256 over its canonical JSON.

    The key never enters the payload, an error message or a log line; only the
    MAC does.  Canonical JSON is what makes the MAC meaningful — two agents
    that serialise the same bundle differently would otherwise produce two
    valid-looking seals for one set of facts.
    """

    material = _check_key(key)
    payload = bundle.to_payload()
    mac = hmac.new(material, canonical_json(payload).encode("utf-8"), "sha256")
    return SealedBundle(payload=payload, seal=mac.hexdigest())


def verify_bundle(sealed: SealedBundle, *, key: bytes) -> BundleVerification:
    """Re-compute the seal and report what the bundle may be trusted to say.

    A single flipped byte anywhere in the nested payload changes the canonical
    JSON and therefore the MAC.  Comparison uses ``hmac.compare_digest`` so a
    forged seal cannot be found one character at a time.
    """

    material = _check_key(key)
    try:
        encoded = canonical_json(sealed.payload)
    except KernelError as exc:
        return BundleVerification(valid=False, reason=f"payload is not canonicalisable: {exc}")
    expected = hmac.new(material, encoded.encode("utf-8"), "sha256").hexdigest()
    if not hmac.compare_digest(expected, sealed.seal):
        return BundleVerification(valid=False, reason="BUNDLE_SEAL_INVALID")
    entries = sealed.payload.get("evidence", ())
    if not isinstance(entries, Sequence):
        return BundleVerification(valid=False, reason="PROVENANCE_BROKEN")
    kinds: list[tuple[str, str]] = []
    outcomes: list[tuple[str, str]] = []
    artifacts: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            return BundleVerification(valid=False, reason="PROVENANCE_BROKEN")
        evidence_id = str(entry.get("evidenceId", ""))
        kinds.append((evidence_id, str(entry.get("kind", ""))))
        outcomes.append((evidence_id, str(entry.get("outcome", Outcome.NOT_RUN.value))))
        for item in entry.get("artifactDigests", ()) or ():
            artifacts.add(str(item))
    return BundleVerification(
        valid=True,
        reason="VERIFIED",
        bundle_id=str(sealed.payload.get("bundleId", "")),
        repo_snapshot_sha=str(sealed.payload.get("repoSnapshotSha", "")),
        evidence_kinds=tuple(sorted(kinds)),
        evidence_outcomes=tuple(sorted(outcomes)),
        artifact_digests=tuple(sorted(artifacts)),
    )


# --- redaction ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RedactionPattern:
    """A named secret shape.  The name is loggable; the match never is."""

    name: str
    pattern: str

    def __post_init__(self) -> None:
        require_identifier(self.name, "redaction_pattern.name")
        require_str(self.pattern, "redaction_pattern.pattern")


#: Shapes that must never survive into an artifact a reviewer can read.
DEFAULT_SECRET_PATTERNS: tuple[RedactionPattern, ...] = (
    RedactionPattern("aws-access-key-id", r"AKIA[0-9A-Z]{16}"),
    RedactionPattern("bearer-token", r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    RedactionPattern("private-key-block",
                     r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    RedactionPattern("assigned-secret",
                     r"(?i)(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*\S+"),
)


@dataclass(frozen=True, slots=True)
class RedactionRecord:
    """How many times one named pattern fired.  Never the matched text."""

    pattern: str
    count: int

    def __post_init__(self) -> None:
        require_identifier(self.pattern, "redaction_record.pattern")
        require_int(self.count, "redaction_record.count", minimum=1)

    def to_payload(self) -> dict[str, Any]:
        return {"pattern": self.pattern, "count": self.count}


@dataclass(frozen=True, slots=True)
class Redaction:
    """The before/after of a redaction, with the link between the two digests."""

    original: Artifact
    artifact: Artifact
    changed: bool
    records: tuple[RedactionRecord, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "originalDigest": self.original.digest,
            "artifact": self.artifact.to_payload(),
            "changed": self.changed,
            "records": [record.to_payload() for record in self.records],
        }


def redact(artifact: Artifact, patterns: Sequence[RedactionPattern] | None = None, *,
           store: ArtifactStore) -> Redaction:
    """Remove secret-shaped content and record that it happened.

    Redaction changes the bytes, therefore it changes the content address.  If
    that new address appeared with no explanation, the lineage would show an
    artifact nobody produced.  So the redacted artifact carries ``redacted``,
    ``redacted_from`` and the names (never the values) of the patterns that
    fired, and the original digest keeps pointing at the original bytes.
    """

    active = tuple(patterns) if patterns is not None else DEFAULT_SECRET_PATTERNS
    data = store.get(artifact.digest)
    records: list[RedactionRecord] = []
    working = data
    for item in active:
        try:
            compiled = re.compile(item.pattern.encode("utf-8"))
        except re.error as exc:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"redaction pattern {item.name!r} is not a valid regular expression",
                recommended_action="fix the pattern",
            ) from exc
        working, count = compiled.subn(_REDACTED, working)
        if count:
            records.append(RedactionRecord(pattern=item.name, count=count))
    if not records:
        return Redaction(original=artifact, artifact=artifact, changed=False, records=())
    new_digest = store.put(working, media_type=artifact.media_type)
    redacted = Artifact(
        digest=new_digest,
        media_type=artifact.media_type,
        byte_count=len(working),
        producer=artifact.producer,
        produced_at=artifact.produced_at,
        redacted=True,
        redacted_from=artifact.digest,
        redaction_patterns=tuple(record.pattern for record in records),
    )
    return Redaction(original=artifact, artifact=redacted, changed=True,
                     records=tuple(records))


# --- retention & provenance --------------------------------------------------

#: Retention in whole days per label.  Integers, not floats: a retention window
#: is compared and persisted, and 89.99999 days is not a policy.
_RETENTION_DAYS: dict[SecurityLabel, int] = {
    SecurityLabel.PUBLIC: 3650,
    SecurityLabel.INTERNAL: 365,
    SecurityLabel.CONFIDENTIAL: 180,
    SecurityLabel.RESTRICTED: 30,
}


def retention_decision(label: SecurityLabel, *, tenant_id: str) -> dict[str, Any]:
    """Retention window and cache scope for a labelled artifact.

    Only ``public`` content may be cached across tenants.  The default is the
    closed one: an unrecognised label never reaches this function because
    decoding rejects it, and every other label is tenant-scoped.
    """

    if label not in _RETENTION_DAYS:
        raise KernelError(
            code="RETENTION_LABEL_UNKNOWN",
            message=f"no retention policy for label {label!r}",
            recommended_action="add a retention rule before storing this label",
        )
    require_identifier(tenant_id, "tenant_id")
    return {
        "securityLabel": str(label),
        "retentionDays": _RETENTION_DAYS[label],
        "tenantScope": tenant_id,
        "crossTenantCacheable": label is SecurityLabel.PUBLIC,
        "measured": True,
    }


def record_provenance(events: EventStore, stream_id: str, edge: Mapping[str, Any], *,
                      fencing_token: int) -> Mapping[str, Any]:
    """Append a provenance edge under a fencing token, idempotently.

    The idempotency key is the edge's own digest, so a duplicate delivery
    returns the original event instead of forking the lineage graph, and a
    worker whose lease was superseded is refused rather than allowed to write
    history behind the new owner's back.
    """

    require_int(fencing_token, "fencing_token", minimum=1)
    key = digest(edge)
    event = events.append(stream_id, edge, idempotency_key=key, fencing_token=fencing_token)
    return {
        "sequence": event.sequence,
        "eventId": event.event_id,
        "hashChain": event.hash_chain,
        "idempotencyKey": key,
    }


# --- registry entry point ----------------------------------------------------

_DEFAULT_STORE: ArtifactStore | None = None


def default_artifact_store() -> ArtifactStore:
    """The process-wide store the registry entry point writes through.

    ``handle`` receives plain data, so it cannot be handed a port.  The default
    is an in-memory store; a deployment binds a real one at startup with
    :func:`set_default_artifact_store`.  Content addressing means the digest in
    the response does not depend on which store is bound — only retrievability
    does.
    """

    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        from .adapters.memory import InMemoryArtifactStore

        _DEFAULT_STORE = InMemoryArtifactStore()
    return _DEFAULT_STORE


def set_default_artifact_store(store: ArtifactStore | None) -> None:
    """Bind (or, with ``None``, unbind) the store used by :func:`handle`."""

    global _DEFAULT_STORE
    _DEFAULT_STORE = store


def _decode_content(payload: Mapping[str, Any]) -> tuple[bytes, str]:
    reject_unknown_fields(payload, {"mediaType", "text", "base64"}, field_name="content")
    media_type = require_str(payload.get("mediaType", "application/octet-stream"),
                             "content.mediaType", max_length=255)
    has_text = "text" in payload
    has_base64 = "base64" in payload
    if has_text == has_base64:
        raise KernelError(
            code="MALFORMED_INPUT",
            message="content must carry exactly one of 'text' or 'base64'",
            recommended_action="send the payload once, in one encoding",
        )
    if has_text:
        return require_str(payload["text"], "content.text",
                           max_length=1 << 20).encode("utf-8"), media_type
    import base64 as _base64

    raw = require_str(payload["base64"], "content.base64", max_length=1 << 20)
    try:
        return _base64.b64decode(raw, validate=True), media_type
    except (ValueError, TypeError) as exc:
        raise KernelError(
            code="MALFORMED_INPUT",
            message="content.base64 is not valid base64",
            recommended_action="re-encode the content",
        ) from exc


@register("artifact-evidence-protocol")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point.

    Takes content plus the step that produced it, stores the bytes, mints the
    evidence bound to the declared input digests, and returns the artifact,
    evidence, provenance edge, retention decision and integrity record.  It
    never trusts a producer-supplied digest and never reads a wall clock: the
    producing step states ``producedAt``, so the same request replays to the
    same bytes.
    """

    reject_unknown_fields(
        request,
        {"producer_step", "content", "repo_snapshot", "task_spec_version", "security_label"},
        field_name="artifact-evidence-protocol request",
    )
    step = require_mapping(request.get("producer_step"), "producer_step")
    reject_unknown_fields(
        step,
        {"stepId", "producerId", "tenantId", "environmentFingerprint", "producedAt",
         "evidenceId", "claim", "kind", "outcome"},
        field_name="producer_step",
    )
    snapshot = require_mapping(request.get("repo_snapshot"), "repo_snapshot")
    reject_unknown_fields(snapshot, {"snapshotSha", "inputDigests"}, field_name="repo_snapshot")

    label_text = require_str(request.get("security_label"), "security_label", max_length=32)
    if label_text not in {item.value for item in SecurityLabel}:
        raise KernelError(
            code="RETENTION_LABEL_UNKNOWN",
            message=f"unknown security label {label_text!r}",
            recommended_action=f"use one of {sorted(item.value for item in SecurityLabel)}",
        )
    label = SecurityLabel(label_text)
    task_spec_version = require_str(request.get("task_spec_version"), "task_spec_version",
                                    max_length=64)
    data, media_type = _decode_content(require_mapping(request.get("content"), "content"))
    produced_at = parse_timestamp(step.get("producedAt"), "producer_step.producedAt")
    producer_id = require_identifier(step.get("producerId"), "producer_step.producerId")
    tenant_id = require_identifier(step.get("tenantId"), "producer_step.tenantId")
    step_id = require_identifier(step.get("stepId"), "producer_step.stepId")
    snapshot_sha = require_str(snapshot.get("snapshotSha"), "repo_snapshot.snapshotSha",
                               max_length=128)
    input_digests = _require_digests(snapshot.get("inputDigests", ()),
                                     "repo_snapshot.inputDigests")

    store = default_artifact_store()
    artifact = store_artifact(store, data, media_type=media_type, producer=producer_id,
                              produced_at=produced_at)
    redaction = redact(artifact, store=store)
    published = redaction.artifact

    kind_text = require_str(step.get("kind"), "producer_step.kind", max_length=64)
    if kind_text not in {item.value for item in EvidenceKind}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown evidence kind {kind_text!r}",
            recommended_action=f"use one of {sorted(item.value for item in EvidenceKind)}",
        )
    outcome_text = require_str(step.get("outcome", Outcome.NOT_RUN.value),
                               "producer_step.outcome", max_length=32)
    if outcome_text not in {item.value for item in Outcome}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown outcome {outcome_text!r}",
            recommended_action=f"use one of {sorted(item.value for item in Outcome)}",
        )
    evidence = Evidence(
        evidence_id=require_identifier(step.get("evidenceId"), "producer_step.evidenceId"),
        claim=require_str(step.get("claim"), "producer_step.claim"),
        kind=EvidenceKind(kind_text),
        artifact_digests=(published.digest,),
        input_digests=input_digests,
        producer_id=producer_id,
        produced_at=produced_at,
        environment_fingerprint=require_str(step.get("environmentFingerprint"),
                                            "producer_step.environmentFingerprint"),
        outcome=Outcome(outcome_text),
    )
    provenance_edge = {
        "fromDigests": list(input_digests),
        "toDigest": published.digest,
        "producerStepId": step_id,
        "producerId": producer_id,
        "repoSnapshotSha": snapshot_sha,
        "taskSpecVersion": task_spec_version,
        "evidenceId": evidence.evidence_id,
        "skill": "artifact-evidence-protocol",
    }
    integrity_record = {
        "algorithm": "sha256",
        "digest": published.digest,
        "byteCount": published.byte_count,
        "originalDigest": artifact.digest,
        "redacted": redaction.changed,
        "redactionRecords": [record.to_payload() for record in redaction.records],
        "verifiedAtProduction": True,
        "bindingDigest": evidence.binding_digest,
    }
    return {
        "artifact": published.to_payload(),
        "evidence": evidence.to_payload(),
        "provenance_edge": provenance_edge,
        "retention_decision": retention_decision(label, tenant_id=tenant_id),
        "integrity_record": integrity_record,
        "evidenceIds": [evidence.evidence_id],
    }
