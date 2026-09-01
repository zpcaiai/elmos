"""Auto-improvement inbox and skill curator: one root cause, one proposal, one decision.

The characteristic failure of a self-improvement loop is not that it proposes
bad changes; it is that it proposes the *same* change five times.  Five
incidents with one root cause become five skill drafts, each with a fifth of
the evidence, and the fifth one duplicates something that shipped last quarter.
So the inbox does two things before anyone is asked to decide.

It **merges**.  Similarity is a declared integer function over four fields —
failure code, touched capability, a digest of the failing step's signature, and
normalised message shingles — with published weights and a published threshold,
so a reviewer can be told *why* two incidents are one problem instead of being
handed a score.  Clustering is computed as connected components over that
relation on every read, never by greedily attaching each arrival to whatever it
happened to meet first; that is what makes ingesting A then B identical to
ingesting B then A, which is asserted directly in the tests.  Two signals from
different tenants never merge, whatever they look like.

It **checks what already exists**.  Every cluster is scored against the shipped
skill catalogue, and an ``ADOPT`` on a cluster that overlaps a shipped skill
raises ``DUPLICATE_SKILL_PROPOSAL`` unless the author explicitly acknowledges
the overlap in the decision.  Proposing a duplicate of something that already
exists is the most common way these systems waste a quarter.

Nothing here promotes anything.  ``ADOPT`` records an intention with a named
author and a rationale — a decision without either raises — and the only path
into the promotion ladder is :meth:`Curator.adopt_into`, which calls
:class:`~.demo2skill.SkillDraftRegistry.admit` and leaves the draft at tier
``draft``.  Promotion still requires the evidence demanded by :mod:`.demo2skill`,
which this module builds but never approves on its own behalf.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .contracts import (
    digest,
    reject_unknown_fields,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .demo2skill import (
    GymImprovement,
    PromotionEvidence,
    SkillDraft,
    SkillDraftRegistry,
)
from .errors import CODES, Category, KernelError, register_codes
from .ports import EventStore
from .registry import DESCRIPTORS, register

__all__ = [
    "Cluster",
    "Curator",
    "Decision",
    "DecisionKind",
    "Inbox",
    "InboxItem",
    "MERGE_THRESHOLD",
    "OVERLAP_THRESHOLD",
    "OverlapReport",
    "Reproducer",
    "ShippedSkill",
    "Signal",
    "SignalKind",
    "SimilarityBreakdown",
    "WEIGHTS",
    "check_no_regression",
    "curation_to_promotion_evidence",
    "handle",
    "overlap_with_shipped",
    "require_stable_reproducer",
    "similarity",
]

register_codes(
    Category.SEMANTIC,
    "INCIDENT_UNCLASSIFIED",
    "DUPLICATE_SKILL_PROPOSAL",
)
register_codes(
    Category.VERIFICATION,
    "REPRODUCER_FLAKY",
    "IMPROVEMENT_REGRESSION",
)
register_codes(
    Category.RELEASE,
    "CURATION_REJECTED",
    "CURATION_DECISION_INCOMPLETE",
)

#: The similarity weights, published because a threshold is meaningless without
#: them.  They sum to 100 so the total reads as a percentage of the evidence a
#: perfect match would carry.
WEIGHTS: Mapping[str, int] = {
    "failureCode": 40,
    "capability": 20,
    "stepSignature": 25,
    "messageShingles": 15,
}

#: At or above this total, two items are one root cause and merge.  Same
#: failure code, same capability and same failing step reaches 85 without any
#: help from the message text; two items agreeing only on the code and the
#: capability reach 60 and stay apart.
MERGE_THRESHOLD = 70

#: At or above this, a cluster overlaps a shipped skill enough that adopting it
#: as something new needs an explicit acknowledgement.
OVERLAP_THRESHOLD = 60

#: Minimum reproducer executions before stability can be claimed at all.  One
#: green run does not distinguish a fixed bug from a flaky one.
MIN_REPRODUCER_RUNS = 3

_TOKEN_RE = re.compile(r"[A-Za-z]+|[0-9]+")
_SHINGLE = 3


class SignalKind(StrEnum):
    """Where an improvement signal came from.

    Kept as a field rather than collapsed into "incident" because the source
    changes what the evidence is worth: a user correction is a statement about
    intent, a rollback is a statement about production, and a low rating is
    neither.
    """

    INCIDENT = "incident"
    ROLLBACK = "rollback"
    USER_CORRECTION = "user-correction"
    LOW_RATING = "low-rating"
    PERFORMANCE_ANOMALY = "performance-anomaly"
    FINDING = "finding"


def _normalise_message(message: str) -> str:
    """Fold the parts of a message that vary between instances of one bug.

    Digits become ``#`` and hex-looking runs become ``@``: "timed out after
    30s" and "timed out after 45s" are the same incident, and a similarity
    function that says otherwise forks one root cause into two skills.
    """

    lowered = message.lower()
    lowered = re.sub(r"\b(?:0x)?[0-9a-f]{8,}\b", "@", lowered)
    return re.sub(r"\d+", "#", lowered)


def _shingles(message: str) -> tuple[str, ...]:
    tokens = _TOKEN_RE.findall(_normalise_message(message))
    if len(tokens) < _SHINGLE:
        return tuple(sorted({" ".join(tokens)})) if tokens else ()
    return tuple(sorted({
        " ".join(tokens[index:index + _SHINGLE])
        for index in range(len(tokens) - _SHINGLE + 1)
    }))


def _jaccard_percent(left: Sequence[str], right: Sequence[str]) -> int:
    a, b = set(left), set(right)
    if not a and not b:
        return 100
    union = a | b
    if not union:
        return 0
    return 100 * len(a & b) // len(union)


@dataclass(frozen=True, slots=True)
class Signal:
    """One raw input to the inbox, already classified.

    ``failure_code`` must be a registered kernel code and ``capability`` a
    declared capability.  An incident that matches neither is
    ``INCIDENT_UNCLASSIFIED``: bucketing it as "other" is how a taxonomy dies,
    and inventing a code for it is how two names for one failure appear.

    The accepted taxonomy is whatever the running build has registered, so a
    code owned by a capability module this build never imported is refused
    rather than assumed valid.  That is the fail-closed direction: the fix is
    to load the owning module, not to widen the check.
    """

    signal_id: str
    kind: SignalKind
    failure_code: str
    capability: str
    step_signature: str
    message: str
    tenant_id: str
    repo_snapshot_sha: str = ""
    occurrence_count: int = 1
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.signal_id, "signal.signal_id")
        require_identifier(self.tenant_id, "signal.tenant_id")
        require_str(self.message, "signal.message")
        require_str(self.step_signature, "signal.step_signature", max_length=512)
        require_int(self.occurrence_count, "signal.occurrence_count", minimum=1)
        if not isinstance(self.kind, SignalKind):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown signal kind {self.kind!r}",
                recommended_action=f"use one of {sorted(k.value for k in SignalKind)}",
            )
        if self.failure_code not in CODES:
            raise KernelError(
                code="INCIDENT_UNCLASSIFIED",
                message=(
                    f"signal {self.signal_id!r} carries failure code {self.failure_code!r}, "
                    "which is not in the kernel taxonomy"
                ),
                retryable=False,
                recommended_action=(
                    "classify the incident against a registered failure code, or register "
                    "the code in the owning module first"
                ),
                details={"signalId": self.signal_id, "failureCode": self.failure_code},
            )
        if self.capability not in DESCRIPTORS:
            raise KernelError(
                code="INCIDENT_UNCLASSIFIED",
                message=(
                    f"signal {self.signal_id!r} names capability {self.capability!r}, which "
                    "is not declared; an unknown capability is denied, not invented"
                ),
                retryable=False,
                recommended_action="attribute the incident to a declared capability",
                details={"signalId": self.signal_id, "capability": self.capability},
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "signalId": self.signal_id,
            "kind": str(self.kind),
            "failureCode": self.failure_code,
            "capability": self.capability,
            "stepSignature": self.step_signature,
            "tenantId": self.tenant_id,
            "occurrenceCount": self.occurrence_count,
            "evidenceIds": list(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class InboxItem:
    """A normalised improvement proposal, ready to be compared with its siblings."""

    item_id: str
    tenant_id: str
    failure_code: str
    capability: str
    step_signature_digest: str
    shingles: tuple[str, ...]
    title: str
    occurrence_count: int = 1
    sources: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.item_id, "item.item_id")
        require_identifier(self.tenant_id, "item.tenant_id")
        require_str(self.title, "item.title")
        require_int(self.occurrence_count, "item.occurrence_count", minimum=1)

    @classmethod
    def from_signal(cls, signal: Signal) -> InboxItem:
        return cls(
            item_id=f"item-{signal.signal_id}",
            tenant_id=signal.tenant_id,
            failure_code=signal.failure_code,
            capability=signal.capability,
            step_signature_digest=digest(signal.step_signature),
            shingles=_shingles(signal.message),
            title=signal.message[:120],
            occurrence_count=signal.occurrence_count,
            sources=(signal.signal_id,),
            evidence_ids=tuple(sorted(set(signal.evidence_ids))),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "itemId": self.item_id,
            "tenantId": self.tenant_id,
            "failureCode": self.failure_code,
            "capability": self.capability,
            "stepSignatureDigest": self.step_signature_digest,
            "shingleCount": len(self.shingles),
            "title": self.title,
            "occurrenceCount": self.occurrence_count,
            "sources": list(self.sources),
            "evidenceIds": list(self.evidence_ids),
        }

    @property
    def digest(self) -> str:
        return digest({**self.to_payload(), "shingles": list(self.shingles)})


@dataclass(frozen=True, slots=True)
class SimilarityBreakdown:
    """A score you can argue with.

    Every component states what it awarded, out of what, and why.  A single
    opaque number cannot be reviewed, cannot be tuned safely, and cannot be
    explained to the person whose two incidents were merged.
    """

    total: int
    threshold: int
    components: tuple[Mapping[str, Any], ...]
    explanation: str

    @property
    def merges(self) -> bool:
        return self.total >= self.threshold

    def to_payload(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "threshold": self.threshold,
            "merges": self.merges,
            "components": [dict(item) for item in self.components],
            "explanation": self.explanation,
            "weights": dict(sorted(WEIGHTS.items())),
        }


def similarity(left: InboxItem, right: InboxItem) -> SimilarityBreakdown:
    """Score two items on the four declared fields.

    Cross-tenant pairs score zero unconditionally.  That is not a tuning
    decision: one tenant's incident text must never influence another tenant's
    inbox, and a similarity function that could merge them is a data-isolation
    bug wearing a statistics costume.
    """

    if left.tenant_id != right.tenant_id:
        return SimilarityBreakdown(
            total=0,
            threshold=MERGE_THRESHOLD,
            components=(
                {"component": "tenant", "awarded": 0, "max": 100,
                 "reason": f"{left.tenant_id!r} and {right.tenant_id!r} are different tenants"},
            ),
            explanation=(
                "items from different tenants never merge, whatever their content; "
                "tenant isolation outranks similarity"
            ),
        )
    components: list[Mapping[str, Any]] = []
    total = 0

    same_code = left.failure_code == right.failure_code
    awarded = WEIGHTS["failureCode"] if same_code else 0
    total += awarded
    components.append({
        "component": "failureCode", "awarded": awarded, "max": WEIGHTS["failureCode"],
        "reason": (f"both {left.failure_code}" if same_code
                   else f"{left.failure_code} vs {right.failure_code}"),
    })

    same_capability = left.capability == right.capability
    awarded = WEIGHTS["capability"] if same_capability else 0
    total += awarded
    components.append({
        "component": "capability", "awarded": awarded, "max": WEIGHTS["capability"],
        "reason": (f"both {left.capability}" if same_capability
                   else f"{left.capability} vs {right.capability}"),
    })

    same_step = left.step_signature_digest == right.step_signature_digest
    awarded = WEIGHTS["stepSignature"] if same_step else 0
    total += awarded
    components.append({
        "component": "stepSignature", "awarded": awarded, "max": WEIGHTS["stepSignature"],
        "reason": ("identical failing-step signature" if same_step
                   else "different failing-step signature"),
    })

    overlap = _jaccard_percent(left.shingles, right.shingles)
    awarded = WEIGHTS["messageShingles"] * overlap // 100
    total += awarded
    components.append({
        "component": "messageShingles", "awarded": awarded,
        "max": WEIGHTS["messageShingles"],
        "overlapPercent": overlap,
        "reason": f"{overlap}% of normalised message shingles in common",
    })

    return SimilarityBreakdown(
        total=total,
        threshold=MERGE_THRESHOLD,
        components=tuple(components),
        explanation=(
            f"{total}/100 against a threshold of {MERGE_THRESHOLD}: "
            + "; ".join(f"{item['component']} {item['awarded']}/{item['max']}"
                        for item in components)
        ),
    )


@dataclass(frozen=True, slots=True)
class Cluster:
    """One root cause, and every proposal that turned out to be about it."""

    cluster_id: str
    tenant_id: str
    members: tuple[str, ...]
    failure_codes: tuple[str, ...]
    capabilities: tuple[str, ...]
    occurrence_count: int
    evidence_ids: tuple[str, ...]
    titles: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "clusterId": self.cluster_id,
            "tenantId": self.tenant_id,
            "members": list(self.members),
            "memberCount": len(self.members),
            "failureCodes": list(self.failure_codes),
            "capabilities": list(self.capabilities),
            "occurrenceCount": self.occurrence_count,
            "evidenceIds": list(self.evidence_ids),
            "titles": list(self.titles),
        }


class Inbox:
    """The improvement inbox: append-only items, recomputed clusters.

    Clusters are derived, never stored.  Storing them would require deciding,
    at ingest time, which existing cluster an arrival joins — and that decision
    depends on arrival order, which is precisely the property this class must
    not have.  Recomputing connected components over the similarity relation
    costs nothing at these volumes and is order-independent by construction.
    """

    def __init__(self) -> None:
        self._items: dict[str, InboxItem] = {}

    def __len__(self) -> int:
        return len(self._items)

    def items(self) -> tuple[InboxItem, ...]:
        return tuple(self._items[key] for key in sorted(self._items))

    def get(self, item_id: str) -> InboxItem:
        item = self._items.get(item_id)
        if item is None:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"inbox item {item_id!r} does not exist",
                recommended_action="ingest the item before referring to it",
            )
        return item

    def ingest(self, item: InboxItem) -> InboxItem:
        """Add an item.  Re-ingesting the identical item changes nothing.

        A *different* item under an existing id is an ``IDEMPOTENCY_CONFLICT``
        rather than an overwrite: a duplicate delivery must not be able to
        rewrite the evidence a decision was taken on.
        """

        existing = self._items.get(item.item_id)
        if existing is not None:
            if existing.digest != item.digest:
                raise KernelError(
                    code="IDEMPOTENCY_CONFLICT",
                    message=(
                        f"inbox item {item.item_id!r} already exists with different content"
                    ),
                    recommended_action="ingest the changed proposal under a new id",
                    details={"itemId": item.item_id},
                )
            return existing
        self._items[item.item_id] = item
        return item

    def clusters(self) -> tuple[Cluster, ...]:
        """Connected components over the merge relation, in a stable order."""

        ordered = self.items()
        parent = {item.item_id: item.item_id for item in ordered}

        def find(node: str) -> str:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        for index, left in enumerate(ordered):
            for right in ordered[index + 1:]:
                if similarity(left, right).merges:
                    root_left, root_right = find(left.item_id), find(right.item_id)
                    if root_left != root_right:
                        # Attach the larger id under the smaller so the root is
                        # a function of the member set, never of arrival order.
                        low, high = sorted((root_left, root_right))
                        parent[high] = low

        groups: dict[str, list[InboxItem]] = {}
        for item in ordered:
            groups.setdefault(find(item.item_id), []).append(item)

        clusters = []
        for root in sorted(groups):
            members = sorted(groups[root], key=lambda entry: entry.item_id)
            clusters.append(Cluster(
                cluster_id=f"cluster-{root}",
                tenant_id=members[0].tenant_id,
                members=tuple(item.item_id for item in members),
                failure_codes=tuple(sorted({item.failure_code for item in members})),
                capabilities=tuple(sorted({item.capability for item in members})),
                occurrence_count=sum(item.occurrence_count for item in members),
                evidence_ids=tuple(sorted({
                    evidence for item in members for evidence in item.evidence_ids
                })),
                titles=tuple(item.title for item in members),
            ))
        return tuple(clusters)

    def to_payload(self) -> dict[str, Any]:
        return {
            "items": [item.to_payload() for item in self.items()],
            "clusters": [item.to_payload() for item in self.clusters()],
            "mergeThreshold": MERGE_THRESHOLD,
            "weights": dict(sorted(WEIGHTS.items())),
        }

    @property
    def state_digest(self) -> str:
        """Content address of the inbox.  Independent of ingest order."""

        return digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class ShippedSkill:
    """Something that already exists, and that a new proposal might duplicate."""

    skill_id: str
    capability: str
    failure_codes: tuple[str, ...]
    keywords: tuple[str, ...]
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        require_identifier(self.skill_id, "shipped_skill.skill_id")
        require_identifier(self.capability, "shipped_skill.capability")

    def to_payload(self) -> dict[str, Any]:
        return {
            "skillId": self.skill_id,
            "capability": self.capability,
            "failureCodes": list(self.failure_codes),
            "keywords": list(self.keywords),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class OverlapReport:
    """How much a cluster duplicates something already shipped."""

    cluster_id: str
    skill_id: str
    score: int
    threshold: int
    components: tuple[Mapping[str, Any], ...]
    explanation: str

    @property
    def duplicates(self) -> bool:
        return self.score >= self.threshold

    def to_payload(self) -> dict[str, Any]:
        return {
            "clusterId": self.cluster_id,
            "skillId": self.skill_id,
            "score": self.score,
            "threshold": self.threshold,
            "duplicates": self.duplicates,
            "components": [dict(item) for item in self.components],
            "explanation": self.explanation,
        }


def overlap_with_shipped(cluster: Cluster, skills: Sequence[ShippedSkill],
                         *, keywords: Mapping[str, Sequence[str]] | None = None
                         ) -> tuple[OverlapReport, ...]:
    """Score a cluster against every shipped skill, highest first.

    The components are the same kind of declared, explainable terms as
    :func:`similarity`: the capability it touches, the failure codes it covers,
    and the keywords in its titles.  A proposal that duplicates a shipped skill
    is the single most common output of an improvement loop nobody checks, and
    it is cheap to catch here and expensive to catch after review.
    """

    cluster_keywords = set(
        (keywords or {}).get(cluster.cluster_id, ())
    ) or {
        token for title in cluster.titles
        for token in _TOKEN_RE.findall(title.lower()) if len(token) > 3
    }
    reports = []
    for skill in skills:
        components: list[Mapping[str, Any]] = []
        score = 0
        capability_hit = skill.capability in cluster.capabilities
        awarded = 40 if capability_hit else 0
        score += awarded
        components.append({
            "component": "capability", "awarded": awarded, "max": 40,
            "reason": (f"both touch {skill.capability}" if capability_hit
                       else f"{skill.capability} not among {list(cluster.capabilities)}"),
        })
        shared_codes = sorted(set(skill.failure_codes) & set(cluster.failure_codes))
        awarded = 40 if shared_codes else 0
        score += awarded
        components.append({
            "component": "failureCodes", "awarded": awarded, "max": 40,
            "sharedCodes": shared_codes,
            "reason": (f"shares {shared_codes}" if shared_codes
                       else "no failure code in common"),
        })
        shared_keywords = sorted(set(skill.keywords) & cluster_keywords)
        awarded = 20 if shared_keywords else 0
        score += awarded
        components.append({
            "component": "keywords", "awarded": awarded, "max": 20,
            "sharedKeywords": shared_keywords,
            "reason": (f"shares {shared_keywords}" if shared_keywords
                       else "no keyword in common"),
        })
        reports.append(OverlapReport(
            cluster_id=cluster.cluster_id,
            skill_id=skill.skill_id,
            score=score,
            threshold=OVERLAP_THRESHOLD,
            components=tuple(components),
            explanation=(
                f"{score}/100 overlap with shipped skill {skill.skill_id} "
                f"(threshold {OVERLAP_THRESHOLD}): "
                + "; ".join(f"{item['component']} {item['awarded']}/{item['max']}"
                            for item in components)
            ),
        ))
    return tuple(sorted(reports, key=lambda item: (-item.score, item.skill_id)))


class DecisionKind(StrEnum):
    """What a curator decided.  All four are decisions; none of them is a promotion."""

    ADOPT = "ADOPT"
    MERGE = "MERGE"
    DEFER = "DEFER"
    REJECT = "REJECT"


@dataclass(frozen=True, slots=True)
class Decision:
    """A recorded human judgement, with the two things that make it auditable.

    An author and a rationale are required at construction.  A decision without
    them is not a weaker decision, it is an unattributable one, and six months
    later nobody can tell whether a rejected proposal was rejected for a reason
    or lost in a queue.
    """

    decision_id: str
    cluster_id: str
    kind: DecisionKind
    author: str
    rationale: str
    merged_into: str | None = None
    acknowledges_duplicate: bool = False
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.decision_id, "decision.decision_id")
        require_identifier(self.cluster_id, "decision.cluster_id")
        if not isinstance(self.kind, DecisionKind):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown decision kind {self.kind!r}",
                recommended_action=f"use one of {sorted(k.value for k in DecisionKind)}",
            )
        if not str(self.author).strip():
            raise KernelError(
                code="CURATION_DECISION_INCOMPLETE",
                message=f"decision {self.decision_id!r} names no author",
                retryable=False,
                recommended_action="record who took the decision",
                details={"decisionId": self.decision_id},
            )
        require_identifier(self.author, "decision.author")
        if not str(self.rationale).strip():
            raise KernelError(
                code="CURATION_DECISION_INCOMPLETE",
                message=(
                    f"decision {self.decision_id!r} carries no rationale; a decision "
                    "nobody explained cannot be reviewed or reversed"
                ),
                retryable=False,
                recommended_action="state why this cluster is adopted, merged, deferred "
                                   "or rejected",
                details={"decisionId": self.decision_id},
            )
        if self.kind is DecisionKind.MERGE and not self.merged_into:
            raise KernelError(
                code="CURATION_DECISION_INCOMPLETE",
                message=f"decision {self.decision_id!r} is a MERGE with no target",
                retryable=False,
                recommended_action="name the cluster or shipped skill this merges into",
                details={"decisionId": self.decision_id},
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "decisionId": self.decision_id,
            "clusterId": self.cluster_id,
            "kind": str(self.kind),
            "author": self.author,
            "rationale": self.rationale,
            "mergedInto": self.merged_into,
            "acknowledgesDuplicate": self.acknowledges_duplicate,
            "evidenceIds": list(self.evidence_ids),
            "autoPromoted": False,
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class Reproducer:
    """A minimal reproduction and the runs that were actually executed.

    ``runs`` is the recorded result of each execution.  A reproducer is stable
    only when every run agreed; a mixed record is flaky, and a flaky reproducer
    proves nothing about a fix that follows it.
    """

    reproducer_id: str
    cluster_id: str
    command_digest: str
    runs: tuple[bool, ...]

    def __post_init__(self) -> None:
        require_identifier(self.reproducer_id, "reproducer.reproducer_id")
        require_identifier(self.cluster_id, "reproducer.cluster_id")
        for index, value in enumerate(self.runs):
            if not isinstance(value, bool):
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"reproducer.runs[{index}] must be a boolean",
                    recommended_action="record each run as reproduced true/false",
                )

    @property
    def stable(self) -> bool:
        return len(self.runs) >= MIN_REPRODUCER_RUNS and (all(self.runs) or not any(self.runs))

    def to_payload(self) -> dict[str, Any]:
        return {
            "reproducerId": self.reproducer_id,
            "clusterId": self.cluster_id,
            "commandDigest": self.command_digest,
            "runs": list(self.runs),
            "runCount": len(self.runs),
            "reproducedCount": sum(1 for item in self.runs if item),
            "minRuns": MIN_REPRODUCER_RUNS,
            "stable": self.stable,
            "reproduces": self.stable and all(self.runs) and bool(self.runs),
        }


def require_stable_reproducer(reproducer: Reproducer) -> Reproducer:
    """Raise unless the reproducer earned the right to be evidence."""

    if len(reproducer.runs) < MIN_REPRODUCER_RUNS:
        raise KernelError(
            code="REPRODUCER_FLAKY",
            message=(
                f"reproducer {reproducer.reproducer_id!r} was run "
                f"{len(reproducer.runs)} time(s); {MIN_REPRODUCER_RUNS} are required before "
                "stability can be claimed"
            ),
            retryable=True,
            recommended_action=f"execute the reproducer at least {MIN_REPRODUCER_RUNS} times",
            details={"reproducerId": reproducer.reproducer_id},
        )
    if not reproducer.stable:
        raise KernelError(
            code="REPRODUCER_FLAKY",
            message=(
                f"reproducer {reproducer.reproducer_id!r} reproduced in "
                f"{sum(1 for item in reproducer.runs if item)}/{len(reproducer.runs)} runs; "
                "a flaky reproducer cannot demonstrate that a fix worked"
            ),
            retryable=True,
            recommended_action="stabilise the reproduction before proposing a fix",
            details={"reproducerId": reproducer.reproducer_id,
                     "runs": list(reproducer.runs)},
        )
    return reproducer


def check_no_regression(improvement: GymImprovement, *, candidate_id: str) -> Mapping[str, Any]:
    """Reject a candidate that made things worse, and one that measured nothing.

    The unmeasured case raises too, with a different code.  "We did not run the
    benchmark" and "the benchmark got worse" are both reasons not to ship, but
    they are different reasons and a caller that cannot tell them apart cannot
    fix either.  The regression path carries the rollback action, because
    detecting a regression without naming the reversal is half a control.
    """

    if not improvement.measured:
        raise KernelError(
            code="NO_MEASURED_IMPROVEMENT",
            message=(
                f"candidate {candidate_id!r} has no before/after measurement; unmeasured "
                "is not zero and is not an improvement"
            ),
            retryable=True,
            recommended_action="run the candidate through the repository gym and re-submit",
            details={"candidateId": candidate_id},
        )
    delta = improvement.delta or 0
    if delta < 0:
        raise KernelError(
            code="IMPROVEMENT_REGRESSION",
            message=(
                f"candidate {candidate_id!r} scored {improvement.candidate_score} against a "
                f"{improvement.baseline_score} baseline, a regression of {-delta}"
            ),
            retryable=False,
            recommended_action="roll the candidate back to the baseline and re-open the item",
            details={
                "candidateId": candidate_id,
                "deltaPoints": delta,
                "rollbackAction": "revert-to-baseline",
                "baselineScore": improvement.baseline_score,
                "candidateScore": improvement.candidate_score,
            },
        )
    return {
        "candidateId": candidate_id,
        "deltaPoints": delta,
        "measured": True,
        "regression": False,
        "sampleSize": improvement.sample_size,
    }


def curation_to_promotion_evidence(decision: Decision, improvement: GymImprovement,
                                   counterexample_results: Sequence[Any] = (),
                                   ) -> PromotionEvidence:
    """Hand a curator's decision to the promotion ladder in :mod:`.demo2skill`.

    The curator supplies the author and the rationale; ``demo2skill`` still
    demands the counterexamples and the measured improvement and still refuses
    the promotion if either is missing.  Nothing about being "curator approved"
    shortens that ladder — this function only carries the paperwork across the
    boundary.
    """

    if decision.kind is not DecisionKind.ADOPT:
        raise KernelError(
            code="CURATION_REJECTED",
            message=(
                f"decision {decision.decision_id!r} is {decision.kind}; only an ADOPT "
                "decision can supply promotion evidence"
            ),
            retryable=False,
            recommended_action="adopt the cluster first, with a rationale",
            details={"decisionId": decision.decision_id, "kind": str(decision.kind)},
        )
    return PromotionEvidence(
        counterexample_results=tuple(counterexample_results),
        improvement=improvement,
        approver=decision.author,
        rationale=decision.rationale,
        evidence_ids=decision.evidence_ids,
    )


class Curator:
    """The review desk.  It records judgements; it does not make them.

    Every decision passes through :meth:`decide`, which refuses an
    unattributable decision, refuses an ``ADOPT`` on a cluster that duplicates
    something shipped unless the author says so explicitly, and records the
    result once under its own digest so a redelivery cannot double-count an
    approval.
    """

    def __init__(self, inbox: Inbox, shipped: Sequence[ShippedSkill] = (), *,
                 events: EventStore | None = None, stream_id: str = "curation") -> None:
        self._inbox = inbox
        self._shipped = tuple(shipped)
        self._events = events
        self._stream_id = stream_id
        self._decisions: dict[str, Decision] = {}

    @property
    def inbox(self) -> Inbox:
        return self._inbox

    @property
    def shipped(self) -> tuple[ShippedSkill, ...]:
        return self._shipped

    def duplicate_reports(self) -> tuple[OverlapReport, ...]:
        """The best shipped-skill match for every cluster that has one."""

        reports = []
        for cluster in self._inbox.clusters():
            for report in overlap_with_shipped(cluster, self._shipped):
                if report.duplicates:
                    reports.append(report)
        return tuple(reports)

    def decisions(self) -> tuple[Decision, ...]:
        return tuple(self._decisions[key] for key in sorted(self._decisions))

    def decision_for(self, cluster_id: str) -> Decision | None:
        for decision in self.decisions():
            if decision.cluster_id == cluster_id:
                return decision
        return None

    def decide(self, decision: Decision, *, fencing_token: int = 1) -> Decision:
        """Record one decision, refusing the ones that must not be recorded."""

        require_int(fencing_token, "fencing_token", minimum=1)
        clusters = {item.cluster_id: item for item in self._inbox.clusters()}
        cluster = clusters.get(decision.cluster_id)
        if cluster is None:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"decision names unknown cluster {decision.cluster_id!r}",
                recommended_action="decide on a cluster the inbox actually holds",
                details={"clusterId": decision.cluster_id,
                         "known": sorted(clusters)},
            )
        existing = self._decisions.get(decision.decision_id)
        if existing is not None:
            if existing.digest != decision.digest:
                raise KernelError(
                    code="IDEMPOTENCY_CONFLICT",
                    message=(
                        f"decision {decision.decision_id!r} already exists with different "
                        "content; a recorded decision is immutable"
                    ),
                    recommended_action="record the revised judgement under a new id",
                    details={"decisionId": decision.decision_id},
                )
            return existing
        if decision.kind is DecisionKind.ADOPT and not decision.acknowledges_duplicate:
            duplicates = [
                report for report in overlap_with_shipped(cluster, self._shipped)
                if report.duplicates
            ]
            if duplicates:
                raise KernelError(
                    code="DUPLICATE_SKILL_PROPOSAL",
                    message=(
                        f"cluster {cluster.cluster_id!r} overlaps shipped skill(s) "
                        f"{[item.skill_id for item in duplicates]}; adopting it as new "
                        "would fork a capability that already exists"
                    ),
                    retryable=False,
                    recommended_action=(
                        "MERGE into the existing skill, or set acknowledgesDuplicate with a "
                        "rationale explaining why a second skill is warranted"
                    ),
                    details={
                        "clusterId": cluster.cluster_id,
                        "skills": [item.skill_id for item in duplicates],
                        "scores": [item.score for item in duplicates],
                    },
                )
        if self._events is not None:
            self._events.append(self._stream_id, decision.to_payload(),
                                idempotency_key=decision.digest,
                                fencing_token=fencing_token)
        self._decisions[decision.decision_id] = decision
        return decision

    def adopt_into(self, registry: SkillDraftRegistry, draft: SkillDraft,
                   decision: Decision) -> str:
        """Admit an adopted draft at tier ``draft`` — and no further.

        This is the whole of "curator approved": the draft enters the ladder.
        Promotion remains :meth:`SkillDraftRegistry.promote`, which demands
        counterexamples, privacy clearance and a measured gym improvement that
        no curation decision can substitute for.
        """

        if decision.kind is not DecisionKind.ADOPT:
            raise KernelError(
                code="CURATION_REJECTED",
                message=(
                    f"cluster {decision.cluster_id!r} was {decision.kind}, not ADOPT; "
                    "nothing enters the draft registry without an adoption"
                ),
                retryable=False,
                recommended_action="adopt the cluster before admitting a draft",
                details={"decisionId": decision.decision_id, "kind": str(decision.kind)},
            )
        if self._decisions.get(decision.decision_id) is None:
            raise KernelError(
                code="CURATION_DECISION_INCOMPLETE",
                message=f"decision {decision.decision_id!r} was never recorded",
                retryable=False,
                recommended_action="record the decision through decide() first",
            )
        tier = registry.admit(draft)
        if tier != "draft":
            raise KernelError(
                code="DRAFT_NOT_PROMOTABLE",
                message=(
                    f"draft {draft.draft_id!r} entered the registry at tier {tier!r}; "
                    "curation admits at 'draft' and never above it"
                ),
                recommended_action="treat as a kernel defect",
            )
        return tier


# --- registry entry point ----------------------------------------------------

_REQUEST_FIELDS = frozenset({
    "run_incidents", "user_corrections", "findings", "telemetry", "benchmark_results",
    "existing_skills", "curation",
})

_SIGNAL_FIELDS = frozenset({
    "signalId", "kind", "failureCode", "capability", "stepSignature", "message",
    "tenantId", "repoSnapshotSha", "occurrenceCount", "evidenceIds",
})


def _decode_signal(payload: Mapping[str, Any], *, default_kind: SignalKind,
                   tenant_id: str, snapshot: str) -> Signal:
    reject_unknown_fields(payload, _SIGNAL_FIELDS, field_name="signal")
    kind = str(payload.get("kind", default_kind.value))
    if kind not in {item.value for item in SignalKind}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown signal kind {kind!r}",
            recommended_action=f"use one of {sorted(k.value for k in SignalKind)}",
        )
    signal_tenant = require_identifier(payload.get("tenantId", tenant_id), "signal.tenantId")
    if signal_tenant != tenant_id:
        raise KernelError(
            code="PRIVACY_BLOCKED",
            message=(
                f"signal {payload.get('signalId')!r} belongs to tenant {signal_tenant!r} "
                f"but this inbox is scoped to {tenant_id!r}"
            ),
            retryable=False,
            recommended_action="curate each tenant's incidents in its own run",
            details={"tenantId": signal_tenant},
        )
    signal_snapshot = str(payload.get("repoSnapshotSha", "") or "")
    if signal_snapshot and snapshot and signal_snapshot != snapshot:
        raise KernelError(
            code="STALE_SNAPSHOT",
            message=(
                f"signal {payload.get('signalId')!r} was recorded against snapshot "
                f"{signal_snapshot} but the curation run is pinned to {snapshot}"
            ),
            retryable=False,
            recommended_action="re-classify the incident against the pinned snapshot",
        )
    return Signal(
        signal_id=require_identifier(payload.get("signalId"), "signal.signalId"),
        kind=SignalKind(kind),
        failure_code=require_str(payload.get("failureCode"), "signal.failureCode",
                                 max_length=64),
        capability=require_str(payload.get("capability"), "signal.capability", max_length=128),
        step_signature=require_str(payload.get("stepSignature"), "signal.stepSignature",
                                   max_length=512),
        message=require_str(payload.get("message"), "signal.message", max_length=4096),
        tenant_id=signal_tenant,
        repo_snapshot_sha=signal_snapshot or snapshot,
        occurrence_count=require_int(payload.get("occurrenceCount", 1),
                                     "signal.occurrenceCount", minimum=1),
        evidence_ids=require_str_seq(payload.get("evidenceIds", ()), "signal.evidenceIds"),
    )


def _collect(request: Mapping[str, Any], field_name: str, container: str,
             kind: SignalKind, *, tenant_id: str, snapshot: str) -> list[Signal]:
    payload = request.get(field_name)
    if payload is None:
        return []
    mapping = require_mapping(payload, field_name)
    reject_unknown_fields(mapping, {container}, field_name=field_name)
    return [
        _decode_signal(require_mapping(item, f"{field_name}.{container}[]"),
                       default_kind=kind, tenant_id=tenant_id, snapshot=snapshot)
        for item in mapping.get(container, ())
    ]


def _improvement_from(payload: Mapping[str, Any] | None) -> GymImprovement:
    if payload is None:
        return GymImprovement(measured=False)
    reject_unknown_fields(payload, {"measured", "baselineScore", "candidateScore",
                                    "sampleSize"}, field_name="improvement")
    measured = bool(payload.get("measured", False))
    if not measured:
        return GymImprovement(measured=False)
    return GymImprovement(
        measured=True,
        baseline_score=require_int(payload.get("baselineScore"), "improvement.baselineScore"),
        candidate_score=require_int(payload.get("candidateScore"),
                                    "improvement.candidateScore"),
        sample_size=require_int(payload.get("sampleSize", 1), "improvement.sampleSize",
                                minimum=1),
    )


def _decode_decision(payload: Mapping[str, Any]) -> Decision:
    reject_unknown_fields(
        payload,
        {"decisionId", "clusterId", "kind", "author", "rationale", "mergedInto",
         "acknowledgesDuplicate", "evidenceIds"},
        field_name="decision",
    )
    kind = str(payload.get("kind", ""))
    if kind not in {item.value for item in DecisionKind}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown decision kind {kind!r}",
            recommended_action=f"use one of {sorted(k.value for k in DecisionKind)}",
        )
    merged_into = payload.get("mergedInto")
    return Decision(
        decision_id=require_identifier(payload.get("decisionId"), "decision.decisionId"),
        cluster_id=require_identifier(payload.get("clusterId"), "decision.clusterId"),
        kind=DecisionKind(kind),
        author=str(payload.get("author", "")),
        rationale=str(payload.get("rationale", "")),
        merged_into=None if merged_into is None else str(merged_into),
        acknowledges_duplicate=bool(payload.get("acknowledgesDuplicate", False)),
        evidence_ids=require_str_seq(payload.get("evidenceIds", ()), "decision.evidenceIds"),
    )


@register("auto-improvement-inbox-and-skill-curator")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point.

    Ingests every signal into one inbox, clusters by root cause, reports the
    overlap with what already shipped, and returns one improvement candidate
    per cluster — never one per incident.  Decisions supplied by the caller are
    validated and recorded; clusters without one are returned as ``PENDING``,
    and no cluster is ever promoted here.
    """

    reject_unknown_fields(request, _REQUEST_FIELDS,
                          field_name="auto-improvement-inbox-and-skill-curator request")
    incidents_payload = request.get("run_incidents")
    if incidents_payload is None:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="run_incidents is required",
            recommended_action="supply run_incidents with a tenantId and incidents",
        )
    incidents_payload = require_mapping(incidents_payload, "run_incidents")
    reject_unknown_fields(incidents_payload, {"tenantId", "repoSnapshotSha", "incidents"},
                          field_name="run_incidents")
    tenant_id = require_identifier(incidents_payload.get("tenantId"),
                                   "run_incidents.tenantId")
    snapshot = str(incidents_payload.get("repoSnapshotSha", "") or "")

    signals = [
        _decode_signal(require_mapping(item, "run_incidents.incidents[]"),
                       default_kind=SignalKind.INCIDENT, tenant_id=tenant_id,
                       snapshot=snapshot)
        for item in incidents_payload.get("incidents", ())
    ]
    signals.extend(_collect(request, "user_corrections", "corrections",
                            SignalKind.USER_CORRECTION, tenant_id=tenant_id,
                            snapshot=snapshot))
    signals.extend(_collect(request, "findings", "findings", SignalKind.FINDING,
                            tenant_id=tenant_id, snapshot=snapshot))
    signals.extend(_collect(request, "telemetry", "anomalies",
                            SignalKind.PERFORMANCE_ANOMALY, tenant_id=tenant_id,
                            snapshot=snapshot))
    if not signals:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="no signal was supplied; there is nothing to curate",
            recommended_action="supply at least one incident, correction, finding or anomaly",
        )

    inbox = Inbox()
    for signal in signals:
        inbox.ingest(InboxItem.from_signal(signal))

    shipped_payload = request.get("existing_skills")
    shipped: list[ShippedSkill] = []
    if shipped_payload is not None:
        shipped_payload = require_mapping(shipped_payload, "existing_skills")
        reject_unknown_fields(shipped_payload, {"skills"}, field_name="existing_skills")
        for item in shipped_payload.get("skills", ()):
            entry = require_mapping(item, "existing_skills.skills[]")
            reject_unknown_fields(entry, {"skillId", "capability", "failureCodes", "keywords",
                                          "version"}, field_name="existing_skill")
            shipped.append(ShippedSkill(
                skill_id=require_identifier(entry.get("skillId"), "existing_skill.skillId"),
                capability=require_str(entry.get("capability"), "existing_skill.capability",
                                       max_length=128),
                failure_codes=require_str_seq(entry.get("failureCodes", ()),
                                              "existing_skill.failureCodes"),
                keywords=require_str_seq(entry.get("keywords", ()),
                                         "existing_skill.keywords"),
                version=str(entry.get("version", "1.0.0")),
            ))

    curator = Curator(inbox, shipped)
    clusters = inbox.clusters()

    benchmark_payload = request.get("benchmark_results")
    reproducers: list[Reproducer] = []
    improvements: dict[str, GymImprovement] = {}
    if benchmark_payload is not None:
        benchmark_payload = require_mapping(benchmark_payload, "benchmark_results")
        reject_unknown_fields(benchmark_payload, {"reproducers", "improvements"},
                              field_name="benchmark_results")
        for item in benchmark_payload.get("reproducers", ()):
            entry = require_mapping(item, "benchmark_results.reproducers[]")
            reject_unknown_fields(entry, {"reproducerId", "clusterId", "commandDigest", "runs"},
                                  field_name="reproducer")
            reproducers.append(Reproducer(
                reproducer_id=require_identifier(entry.get("reproducerId"),
                                                 "reproducer.reproducerId"),
                cluster_id=require_identifier(entry.get("clusterId"), "reproducer.clusterId"),
                command_digest=require_str(entry.get("commandDigest"),
                                           "reproducer.commandDigest", max_length=128),
                runs=tuple(bool(value) for value in entry.get("runs", ())),
            ))
        for item in benchmark_payload.get("improvements", ()):
            entry = require_mapping(item, "benchmark_results.improvements[]")
            reject_unknown_fields(entry, {"clusterId", "measured", "baselineScore",
                                          "candidateScore", "sampleSize"},
                                  field_name="improvement")
            cluster_id = require_identifier(entry.get("clusterId"), "improvement.clusterId")
            improvements[cluster_id] = _improvement_from(
                {key: value for key, value in entry.items() if key != "clusterId"}
            )

    curation_payload = request.get("curation")
    recorded: list[Decision] = []
    if curation_payload is not None:
        curation_payload = require_mapping(curation_payload, "curation")
        reject_unknown_fields(curation_payload, {"decisions"}, field_name="curation")
        for item in curation_payload.get("decisions", ()):
            recorded.append(curator.decide(
                _decode_decision(require_mapping(item, "curation.decisions[]"))
            ))

    candidates = []
    for cluster in clusters:
        decision = curator.decision_for(cluster.cluster_id)
        improvement = improvements.get(cluster.cluster_id, GymImprovement(measured=False))
        cluster_reproducers = [
            item for item in reproducers if item.cluster_id == cluster.cluster_id
        ]
        blockers: list[str] = []
        if decision is None:
            blockers.append("no curation decision recorded")
        elif decision.kind is not DecisionKind.ADOPT:
            blockers.append(f"decision is {decision.kind}, not ADOPT")
        if not cluster_reproducers:
            blockers.append("no reproducer recorded")
        elif not all(item.stable for item in cluster_reproducers):
            blockers.append("reproducer is flaky")
        if not improvement.measured:
            blockers.append("gym improvement is unmeasured; unmeasured is not zero")
        elif (improvement.delta or 0) <= 0:
            blockers.append(f"gym improvement delta {improvement.delta} is not positive")
        overlaps = [
            item.to_payload() for item in overlap_with_shipped(cluster, tuple(shipped))
            if item.duplicates
        ]
        if overlaps:
            blockers.append(
                f"overlaps shipped skill(s) {[item['skillId'] for item in overlaps]}"
            )
        candidates.append({
            "candidateId": f"candidate-{cluster.cluster_id}",
            "clusterId": cluster.cluster_id,
            "occurrenceCount": cluster.occurrence_count,
            "failureCodes": list(cluster.failure_codes),
            "capabilities": list(cluster.capabilities),
            "evidenceIds": list(cluster.evidence_ids),
            "improvement": improvement.to_payload(),
            "duplicateOf": overlaps,
            "blockers": blockers,
            "readyForDraftAdmission": not blockers,
            "autoPromoted": False,
            "status": (
                "PENDING" if decision is None else str(decision.kind)
            ),
        })

    return {
        "improvement_candidate": candidates,
        "failure_cluster": {
            **inbox.to_payload(),
            "signalCount": len(signals),
            "clusterCount": len(clusters),
            "stateDigest": inbox.state_digest,
            "note": (
                "clusters are connected components over the declared similarity relation; "
                "ingest order does not change them"
            ),
        },
        "reproducer": [item.to_payload() for item in reproducers],
        "regression_test": [
            {
                "regressionTestId": f"regression-{cluster.cluster_id}",
                "clusterId": cluster.cluster_id,
                "failureCodes": list(cluster.failure_codes),
                "expectation": "the reproducer no longer reproduces after the change",
                "reproducerIds": sorted(
                    item.reproducer_id for item in reproducers
                    if item.cluster_id == cluster.cluster_id
                ),
                "rollbackAction": "revert-to-baseline",
            }
            for cluster in clusters
        ],
        "curation_decision": {
            "decisions": [item.to_payload() for item in recorded],
            "pendingClusters": [
                cluster.cluster_id for cluster in clusters
                if curator.decision_for(cluster.cluster_id) is None
            ],
            "duplicateReports": [item.to_payload() for item in curator.duplicate_reports()],
            "autoPromotions": [],
            "note": (
                "nothing is promoted here; an ADOPT admits a draft at tier 'draft' and the "
                "demonstration-to-skill ladder still demands counterexamples, privacy "
                "clearance and a measured improvement"
            ),
        },
        "evidenceIds": sorted({
            evidence for signal in signals for evidence in signal.evidence_ids
        }),
    }


def cluster_titles(items: Iterable[InboxItem]) -> tuple[str, ...]:
    """Titles in a stable order, for rendering a cluster to a reviewer."""

    return tuple(item.title for item in sorted(items, key=lambda entry: entry.item_id))
