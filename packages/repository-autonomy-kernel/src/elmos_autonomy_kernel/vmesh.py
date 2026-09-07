"""Independent verification mesh: who may check a claim, and what agreement means.

The invariant this module exists for is embarrassingly easy to violate in a
multi-agent system: the thing that produced a claim must not be the thing that
confirms it.  Identity is not enough — two agents from the same family, prompt
or toolchain fail in the same way, so independence is checked at the level of
an ``independence_class`` as well as the verifier id, and a violation raises
``INDEPENDENCE_VIOLATED`` instead of being quietly counted.

Agreement is then deliberately hard to manufacture.  A verdict that cites no
evidence is an *opinion*: it is recorded, it is preserved in dissent, and it
cannot carry a quorum — three confident, evidence-free ``CONFIRMED`` verdicts
adjudicate to ``INCONCLUSIVE``, because unanimous guessing is still guessing.
Ties and short quorums are ``INCONCLUSIVE`` too, never optimistic.

Two asymmetries are intentional.  A reproducible refutation from a factual
verifier (a compiler, a test, a scanner) is never out-voted by reviewers, and
dissent is carried into the result verbatim rather than averaged into a score,
because the minority verdict is usually the one an incident review wants.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .contracts import (
    digest,
    format_timestamp,
    parse_timestamp,
    reject_unknown_fields,
    require_decimal,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .ports import EventStore
from .registry import register

__all__ = [
    "Adjudication",
    "Consensus",
    "FACTUAL_KINDS",
    "QuorumPolicy",
    "Tally",
    "VerdictValue",
    "Verdict",
    "VerifiedClaim",
    "Verifier",
    "VerifierKind",
    "adjudicate",
    "check_independence",
    "handle",
    "record_verification_run",
    "release_recommendation",
]

register_codes(
    Category.VERIFICATION,
    "INDEPENDENCE_VIOLATED",
    "FINDING_UNVALIDATED",
    "VERIFIER_FAILED",
    "EVIDENCE_CONFLICT",
    "FALSE_POSITIVE_RATE_HIGH",
    "QUORUM_NOT_MET",
    "DUPLICATE_VERDICT",
    "EVIDENCE_STALE",
)


class VerifierKind(StrEnum):
    """What kind of thing is doing the verifying.

    The split that matters is factual versus judgemental: a compiler, a test
    run and a scanner produce reproducible observations, while a review — human
    or model — produces an assessment.  Both are welcome; only the first can
    refute a claim on its own.
    """

    COMPILER = "compiler"
    TEST = "test"
    STATIC_ANALYSIS = "static-analysis"
    SCANNER = "scanner"
    MODEL_REVIEW = "model-review"
    HUMAN_REVIEW = "human-review"


#: Verifier kinds whose verdicts are reproducible observations, not opinions.
FACTUAL_KINDS: frozenset[VerifierKind] = frozenset({
    VerifierKind.COMPILER,
    VerifierKind.TEST,
    VerifierKind.STATIC_ANALYSIS,
    VerifierKind.SCANNER,
})


class VerdictValue(StrEnum):
    """One verifier's answer about one claim."""

    CONFIRMED = "CONFIRMED"
    REFUTED = "REFUTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class Consensus(StrEnum):
    """The mesh's answer, which is not a majority vote.

    ``INCONCLUSIVE`` is the default and the fallback: insufficient quorum, too
    few independence classes, a tie, or nothing but opinions all land here.  It
    is never upgraded on the grounds that nobody objected.
    """

    CONFIRMED = "CONFIRMED"
    REFUTED = "REFUTED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class Verifier:
    """A verifying agent, tool or person.

    ``independence_class`` groups verifiers that share a failure mode — a model
    family, a shared static-analysis engine, one human team.  Two verifiers in
    the same class are one witness for quorum purposes, and neither may verify
    what that class produced.
    """

    verifier_id: str
    kind: VerifierKind
    independence_class: str

    def __post_init__(self) -> None:
        require_identifier(self.verifier_id, "verifier.verifier_id")
        if not isinstance(self.kind, VerifierKind):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown verifier kind {self.kind!r}",
                recommended_action=f"use one of {sorted(k.value for k in VerifierKind)}",
            )
        require_identifier(self.independence_class, "verifier.independence_class")

    @property
    def is_factual(self) -> bool:
        return self.kind in FACTUAL_KINDS

    def to_payload(self) -> dict[str, Any]:
        return {
            "verifierId": self.verifier_id,
            "kind": str(self.kind),
            "independenceClass": self.independence_class,
            "factual": self.is_factual,
        }


@dataclass(frozen=True, slots=True)
class VerifiedClaim:
    """The claim under verification, carrying who produced it.

    The producer's id *and* independence class travel with the claim because
    that is the only way a verifier can be checked for independence at the
    moment it is asked to verify, rather than after its verdict is already in
    the tally.
    """

    claim_id: str
    statement: str
    producer_id: str
    producer_independence_class: str
    repo_snapshot_sha: str

    def __post_init__(self) -> None:
        require_identifier(self.claim_id, "claim.claim_id")
        require_str(self.statement, "claim.statement")
        require_identifier(self.producer_id, "claim.producer_id")
        require_identifier(self.producer_independence_class,
                           "claim.producer_independence_class")
        require_str(self.repo_snapshot_sha, "claim.repo_snapshot_sha", max_length=128)

    def to_payload(self) -> dict[str, Any]:
        return {
            "claimId": self.claim_id,
            "statement": self.statement,
            "producerId": self.producer_id,
            "producerIndependenceClass": self.producer_independence_class,
            "repoSnapshotSha": self.repo_snapshot_sha,
        }


@dataclass(frozen=True, slots=True)
class Verdict:
    """One verifier's answer, with whatever evidence it can point at.

    ``evidence_ids`` decides the verdict's weight class.  Empty means opinion:
    still recorded, still surfaced as dissent, never able to carry a quorum.
    ``confidence`` is a ``Decimal`` because it is compared and hashed, and a
    float would make two machines disagree about the same verdict.
    """

    verifier: Verifier
    claim_id: str
    value: VerdictValue
    evidence_ids: tuple[str, ...] = ()
    confidence: Decimal | None = None
    repo_snapshot_sha: str = ""
    rationale: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.claim_id, "verdict.claim_id")
        if not isinstance(self.value, VerdictValue):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown verdict value {self.value!r}",
                recommended_action=f"use one of {sorted(v.value for v in VerdictValue)}",
            )
        for index, item in enumerate(self.evidence_ids):
            require_identifier(item, f"verdict.evidence_ids[{index}]")
        if self.confidence is not None and not isinstance(self.confidence, Decimal):
            raise KernelError(
                code="MALFORMED_INPUT",
                message="verdict.confidence must be a Decimal or None",
                recommended_action="send confidence as a decimal string, never a float",
            )

    @property
    def is_evidence_backed(self) -> bool:
        """Whether this verdict may be counted towards a quorum at all."""

        return bool(self.evidence_ids)

    def to_payload(self) -> dict[str, Any]:
        return {
            "verifier": self.verifier.to_payload(),
            "claimId": self.claim_id,
            "value": str(self.value),
            "evidenceIds": list(self.evidence_ids),
            "confidence": self.confidence,
            "confidenceMeasured": self.confidence is not None,
            "repoSnapshotSha": self.repo_snapshot_sha,
            "rationale": self.rationale,
            "evidenceBacked": self.is_evidence_backed,
            "weight": "evidence" if self.is_evidence_backed else "opinion",
        }


@dataclass(frozen=True, slots=True)
class QuorumPolicy:
    """How much independent agreement is required before anything is decided.

    All three numbers are counts, not fractions: a fraction of a small verifier
    set rounds in whichever direction the implementer happened to choose, and
    the number of *distinct independence classes* is the term that actually
    stops a mesh of clones from agreeing with itself.
    """

    required_verifiers: int
    required_agreement: int
    independence_classes_required: int

    def __post_init__(self) -> None:
        require_int(self.required_verifiers, "policy.required_verifiers", minimum=1)
        require_int(self.required_agreement, "policy.required_agreement", minimum=1)
        require_int(self.independence_classes_required,
                    "policy.independence_classes_required", minimum=1)
        if self.required_agreement > self.required_verifiers:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=(
                    "required_agreement cannot exceed required_verifiers; "
                    "the policy could never be satisfied"
                ),
                recommended_action="lower required_agreement or raise required_verifiers",
            )
        if self.independence_classes_required > self.required_verifiers:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=(
                    "independence_classes_required cannot exceed required_verifiers; "
                    "the policy could never be satisfied"
                ),
                recommended_action="lower the class requirement",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "requiredVerifiers": self.required_verifiers,
            "requiredAgreement": self.required_agreement,
            "independenceClassesRequired": self.independence_classes_required,
        }


@dataclass(frozen=True, slots=True)
class Tally:
    """Counted verdicts, with the uncounted ones kept visible.

    ``opinions`` is reported rather than discarded so that "nobody backed this
    with evidence" is a readable fact instead of an empty tally nobody can
    explain.
    """

    confirmed: int
    refuted: int
    inconclusive: int
    opinions: int
    independence_classes: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "confirmed": self.confirmed,
            "refuted": self.refuted,
            "inconclusive": self.inconclusive,
            "opinions": self.opinions,
            "independenceClasses": list(self.independence_classes),
        }


@dataclass(frozen=True, slots=True)
class Adjudication:
    """The mesh's outcome: a consensus, the counts, and the dissent verbatim."""

    claim_id: str
    consensus: Consensus
    tally: Tally
    dissent: tuple[Verdict, ...]
    reasons: tuple[str, ...]
    counted_verdicts: tuple[Verdict, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "claimId": self.claim_id,
            "consensus": str(self.consensus),
            "tally": self.tally.to_payload(),
            "dissent": [item.to_payload() for item in self.dissent],
            "reasons": list(self.reasons),
            "countedVerdicts": [item.to_payload() for item in self.counted_verdicts],
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def check_independence(verifier: Verifier, claim: VerifiedClaim) -> None:
    """Raise unless ``verifier`` is genuinely independent of ``claim``.

    Two rules, both necessary.  A verifier never verifies its own output — that
    one is obvious and still gets violated by config.  And a verifier never
    verifies the output of its own independence class, because a shared model,
    prompt or engine shares its blind spots: agreement between clones is one
    observation reported twice.
    """

    if verifier.verifier_id == claim.producer_id:
        raise KernelError(
            code="INDEPENDENCE_VIOLATED",
            message=(
                f"verifier {verifier.verifier_id!r} produced claim {claim.claim_id!r} "
                "and cannot verify it"
            ),
            retryable=False,
            recommended_action="assign a verifier from a different independence class",
            details={"claimId": claim.claim_id, "verifierId": verifier.verifier_id},
        )
    if verifier.independence_class == claim.producer_independence_class:
        raise KernelError(
            code="INDEPENDENCE_VIOLATED",
            message=(
                f"verifier {verifier.verifier_id!r} shares independence class "
                f"{verifier.independence_class!r} with the producer of claim "
                f"{claim.claim_id!r}"
            ),
            retryable=False,
            recommended_action="assign a verifier from a different independence class",
            details={
                "claimId": claim.claim_id,
                "verifierId": verifier.verifier_id,
                "independenceClass": verifier.independence_class,
            },
        )


def adjudicate(verdicts: Sequence[Verdict], policy: QuorumPolicy, *,
               claim: VerifiedClaim | None = None) -> Adjudication:
    """Turn a set of verdicts into a consensus, or admit there isn't one.

    The order of the checks is the design.  Independence and duplicate votes
    are rejected outright — those are configuration errors, not evidence.  A
    factual refutation then short-circuits, because a reproducible failure is
    not something reviewers get to out-vote.  Only after that do the quorum
    conditions apply, and each one that fails produces ``INCONCLUSIVE`` with a
    reason: too few evidence-backed verdicts, too few distinct independence
    classes, not enough agreement, or a tie.
    """

    if claim is not None:
        for verdict in verdicts:
            if verdict.claim_id != claim.claim_id:
                raise KernelError(
                    code="EVIDENCE_CONFLICT",
                    message=(
                        f"verdict from {verdict.verifier.verifier_id!r} is about claim "
                        f"{verdict.claim_id!r}, not {claim.claim_id!r}"
                    ),
                    recommended_action="adjudicate one claim at a time",
                )
            check_independence(verdict.verifier, claim)
            if verdict.repo_snapshot_sha and verdict.repo_snapshot_sha != claim.repo_snapshot_sha:
                raise KernelError(
                    code="EVIDENCE_STALE",
                    message=(
                        f"verdict from {verdict.verifier.verifier_id!r} was produced against "
                        f"snapshot {verdict.repo_snapshot_sha} but the claim is about "
                        f"{claim.repo_snapshot_sha}"
                    ),
                    retryable=False,
                    recommended_action="re-run the verifier against the current snapshot",
                )

    seen: set[str] = set()
    for verdict in verdicts:
        key = f"{verdict.verifier.verifier_id}:{verdict.claim_id}"
        if key in seen:
            raise KernelError(
                code="DUPLICATE_VERDICT",
                message=(
                    f"verifier {verdict.verifier.verifier_id!r} returned more than one verdict "
                    f"for claim {verdict.claim_id!r}"
                ),
                recommended_action="one verifier casts one verdict per claim",
            )
        seen.add(key)

    ordered = tuple(sorted(verdicts, key=lambda item: item.verifier.verifier_id))
    claim_id = claim.claim_id if claim is not None else (
        ordered[0].claim_id if ordered else ""
    )
    counted = tuple(item for item in ordered if item.is_evidence_backed)
    opinions = tuple(item for item in ordered if not item.is_evidence_backed)
    classes = tuple(sorted({item.verifier.independence_class for item in counted}))
    tally = Tally(
        confirmed=sum(1 for item in counted if item.value is VerdictValue.CONFIRMED),
        refuted=sum(1 for item in counted if item.value is VerdictValue.REFUTED),
        inconclusive=sum(1 for item in counted if item.value is VerdictValue.INCONCLUSIVE),
        opinions=len(opinions),
        independence_classes=classes,
    )
    reasons: list[str] = []
    if opinions:
        reasons.append(
            f"{len(opinions)} verdict(s) cited no evidence and were recorded as opinions"
        )

    factual_refutations = tuple(
        item for item in counted
        if item.value is VerdictValue.REFUTED and item.verifier.is_factual
    )
    if factual_refutations:
        reasons.append(
            "a factual verifier refuted the claim with evidence; "
            "reviewer opinions do not out-vote a reproduced failure"
        )
        consensus = Consensus.REFUTED
    elif len(counted) < policy.required_verifiers:
        reasons.append(
            f"quorum not met: {len(counted)} evidence-backed verdict(s), "
            f"{policy.required_verifiers} required"
        )
        consensus = Consensus.INCONCLUSIVE
    elif len(classes) < policy.independence_classes_required:
        reasons.append(
            f"independence not met: {len(classes)} distinct class(es), "
            f"{policy.independence_classes_required} required"
        )
        consensus = Consensus.INCONCLUSIVE
    elif tally.confirmed == tally.refuted:
        reasons.append(
            f"tie between {tally.confirmed} confirmation(s) and {tally.refuted} refutation(s)"
        )
        consensus = Consensus.INCONCLUSIVE
    elif tally.confirmed > tally.refuted and tally.confirmed >= policy.required_agreement:
        reasons.append(f"{tally.confirmed} independent, evidence-backed confirmation(s)")
        consensus = Consensus.CONFIRMED
    elif tally.refuted > tally.confirmed and tally.refuted >= policy.required_agreement:
        reasons.append(f"{tally.refuted} independent, evidence-backed refutation(s)")
        consensus = Consensus.REFUTED
    else:
        reasons.append(
            f"agreement not met: {policy.required_agreement} concurring verdict(s) required"
        )
        consensus = Consensus.INCONCLUSIVE

    dissent = tuple(item for item in ordered if str(item.value) != str(consensus))
    return Adjudication(
        claim_id=claim_id,
        consensus=consensus,
        tally=tally,
        dissent=dissent,
        reasons=tuple(reasons),
        counted_verdicts=counted,
    )


def release_recommendation(adjudication: Adjudication) -> Mapping[str, Any]:
    """Translate a consensus into a release posture, never optimistically.

    Only ``CONFIRMED`` recommends release.  ``INCONCLUSIVE`` recommends more
    verification, which is a different thing from a block: it says the mesh
    does not know, and the release gate treats "does not know" as a rejection
    on its own terms.
    """

    if adjudication.consensus is Consensus.CONFIRMED:
        recommendation = "RELEASE"
    elif adjudication.consensus is Consensus.REFUTED:
        recommendation = "BLOCK"
    else:
        recommendation = "INSUFFICIENT_EVIDENCE"
    return {
        "recommendation": recommendation,
        "consensus": str(adjudication.consensus),
        "claimId": adjudication.claim_id,
        "dissentCount": len(adjudication.dissent),
        "reasons": list(adjudication.reasons),
    }


def record_verification_run(events: EventStore, stream_id: str, adjudication: Adjudication, *,
                            fencing_token: int) -> Mapping[str, Any]:
    """Append the adjudication to the run stream, once, under a fencing token."""

    require_int(fencing_token, "fencing_token", minimum=1)
    payload = adjudication.to_payload()
    event = events.append(stream_id, payload, idempotency_key=adjudication.digest,
                          fencing_token=fencing_token)
    return {
        "sequence": event.sequence,
        "eventId": event.event_id,
        "hashChain": event.hash_chain,
        "adjudicationDigest": adjudication.digest,
    }


# --- registry entry point ----------------------------------------------------


def _decode_verifier(payload: Mapping[str, Any]) -> Verifier:
    reject_unknown_fields(payload, {"verifierId", "kind", "independenceClass"},
                          field_name="verifier")
    kind = require_str(payload.get("kind"), "verifier.kind", max_length=64)
    if kind not in {item.value for item in VerifierKind}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown verifier kind {kind!r}",
            recommended_action=f"use one of {sorted(k.value for k in VerifierKind)}",
        )
    return Verifier(
        verifier_id=require_identifier(payload.get("verifierId"), "verifier.verifierId"),
        kind=VerifierKind(kind),
        independence_class=require_identifier(payload.get("independenceClass"),
                                              "verifier.independenceClass"),
    )


def _decode_verdict(payload: Mapping[str, Any]) -> Verdict:
    reject_unknown_fields(
        payload,
        {"verifier", "claimId", "value", "evidenceIds", "confidence", "repoSnapshotSha",
         "rationale"},
        field_name="verdict",
    )
    value = require_str(payload.get("value"), "verdict.value", max_length=32)
    if value not in {item.value for item in VerdictValue}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown verdict value {value!r}",
            recommended_action=f"use one of {sorted(v.value for v in VerdictValue)}",
        )
    raw_confidence = payload.get("confidence")
    confidence = (
        None if raw_confidence is None
        else require_decimal(raw_confidence, "verdict.confidence", minimum=Decimal(0))
    )
    return Verdict(
        verifier=_decode_verifier(require_mapping(payload.get("verifier"), "verdict.verifier")),
        claim_id=require_identifier(payload.get("claimId"), "verdict.claimId"),
        value=VerdictValue(value),
        evidence_ids=require_str_seq(payload.get("evidenceIds", ()), "verdict.evidenceIds"),
        confidence=confidence,
        repo_snapshot_sha=str(payload.get("repoSnapshotSha", "")),
        rationale=str(payload.get("rationale", "")),
    )


def _coverage(verdicts: Sequence[Verdict], policy: QuorumPolicy,
              adjudication: Adjudication) -> Mapping[str, Any]:
    factual = sum(1 for item in verdicts if item.verifier.is_factual)
    return {
        "verdictsReceived": len(verdicts),
        "evidenceBackedVerdicts": len(adjudication.counted_verdicts),
        "opinionVerdicts": adjudication.tally.opinions,
        "factualVerifiers": factual,
        "independenceClasses": list(adjudication.tally.independence_classes),
        "policy": policy.to_payload(),
        "requiredVerifiersComplete": (
            len(adjudication.counted_verdicts) >= policy.required_verifiers
        ),
        "measured": True,
    }


@register("independent-verification-mesh")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point.

    Decodes the claim, its verifiers' verdicts and the quorum policy, enforces
    independence, and returns the verification run with its dissent intact.  An
    independence violation or a duplicate verdict raises rather than being
    absorbed into the tally, because a mesh that silently drops an invalid
    verdict reports a quorum it never had.
    """

    reject_unknown_fields(
        request,
        {"change_set", "validation_dag", "task_spec", "repository_snapshot", "policies"},
        field_name="independent-verification-mesh request",
    )
    change_set = require_mapping(request.get("change_set"), "change_set")
    reject_unknown_fields(change_set, {"claim", "producedAt"}, field_name="change_set")
    claim_payload = require_mapping(change_set.get("claim"), "change_set.claim")
    reject_unknown_fields(
        claim_payload,
        {"claimId", "statement", "producerId", "producerIndependenceClass"},
        field_name="claim",
    )
    snapshot = require_mapping(request.get("repository_snapshot"), "repository_snapshot")
    reject_unknown_fields(snapshot, {"snapshotSha"}, field_name="repository_snapshot")
    snapshot_sha = require_str(snapshot.get("snapshotSha"), "repository_snapshot.snapshotSha",
                               max_length=128)
    claim = VerifiedClaim(
        claim_id=require_identifier(claim_payload.get("claimId"), "claim.claimId"),
        statement=require_str(claim_payload.get("statement"), "claim.statement"),
        producer_id=require_identifier(claim_payload.get("producerId"), "claim.producerId"),
        producer_independence_class=require_identifier(
            claim_payload.get("producerIndependenceClass"), "claim.producerIndependenceClass"),
        repo_snapshot_sha=snapshot_sha,
    )
    produced_at: datetime = parse_timestamp(change_set.get("producedAt"),
                                            "change_set.producedAt")

    dag = require_mapping(request.get("validation_dag"), "validation_dag")
    reject_unknown_fields(dag, {"verdicts"}, field_name="validation_dag")
    verdicts = tuple(
        _decode_verdict(require_mapping(item, "verdicts[]"))
        for item in dag.get("verdicts", ())
    )

    policies = require_mapping(request.get("policies"), "policies")
    reject_unknown_fields(policies, {"quorum"}, field_name="policies")
    quorum_payload = require_mapping(policies.get("quorum"), "policies.quorum")
    reject_unknown_fields(
        quorum_payload,
        {"requiredVerifiers", "requiredAgreement", "independenceClassesRequired"},
        field_name="policies.quorum",
    )
    policy = QuorumPolicy(
        required_verifiers=require_int(quorum_payload.get("requiredVerifiers"),
                                       "quorum.requiredVerifiers", minimum=1),
        required_agreement=require_int(quorum_payload.get("requiredAgreement"),
                                       "quorum.requiredAgreement", minimum=1),
        independence_classes_required=require_int(
            quorum_payload.get("independenceClassesRequired"),
            "quorum.independenceClassesRequired", minimum=1),
    )
    task_spec_version = require_str(request.get("task_spec"), "task_spec", max_length=64)

    adjudication = adjudicate(verdicts, policy, claim=claim)
    findings = [
        {
            "findingId": f"finding-{item.verifier.verifier_id}",
            "category": "verification",
            "severity": "P1" if item.verifier.is_factual else "P2",
            "status": "VALIDATED" if item.is_evidence_backed else "OPEN",
            "description": item.rationale or "verifier refuted the claim",
            "evidenceIds": list(item.evidence_ids),
        }
        for item in adjudication.counted_verdicts
        if item.value is VerdictValue.REFUTED
    ]
    evidence_ids = sorted({
        evidence_id
        for item in adjudication.counted_verdicts
        for evidence_id in item.evidence_ids
    })
    return {
        "verification_run": {
            "claim": claim.to_payload(),
            "producedAt": format_timestamp(produced_at),
            "taskSpecVersion": task_spec_version,
            "adjudication": adjudication.to_payload(),
            "adjudicationDigest": adjudication.digest,
        },
        "findings": findings,
        "finding_validations": [
            {
                "verifierId": item.verifier.verifier_id,
                "independenceClass": item.verifier.independence_class,
                "value": str(item.value),
                "evidenceBacked": item.is_evidence_backed,
            }
            for item in sorted(verdicts, key=lambda entry: entry.verifier.verifier_id)
        ],
        "coverage_report": _coverage(verdicts, policy, adjudication),
        "release_recommendation": release_recommendation(adjudication),
        "evidenceIds": evidence_ids,
    }
