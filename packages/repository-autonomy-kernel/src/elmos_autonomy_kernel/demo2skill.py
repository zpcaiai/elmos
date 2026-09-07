"""Demonstration to skill: turning traces into a rule that knows its own boundary.

Generalisation is the dangerous step in this whole package, so it is made
explicit rather than left to a model's judgement.  Three things are separated
and reported separately: the *invariant* steps (the longest step sequence every
validated demonstration performs, in order), the *varying slots* (arguments
whose observed values differ, which become parameters carrying the value set
that was actually seen), and the *confirmed preconditions* (those observed in
every demonstration — a precondition seen in some runs is reported as
unconfirmed, never quietly promoted to a requirement).

The rule this module exists to enforce is that a skill learned only from
positive examples has no boundary.  A draft therefore cannot leave ``draft``
without at least one counterexample — a trace on which the skill must *not*
fire — and each counterexample is executed against the draft's own trigger
predicate.  If the draft would fire on it, the generalisation is too wide and
``SKILL_TRIGGER_OVERBROAD`` is raised instead of a confidence number being
nudged down.

Nothing here auto-promotes.  ``handle`` only ever produces a draft plus the
list of blockers; promotion is a separate, explicit call through
:class:`SkillDraftRegistry`, one tier at a time, and it raises when the
evidence is absent.  An improvement that was never measured is reported as
unmeasured, never as zero, because "we did not measure it" and "it did not
help" are different facts and only one of them is a reason to stop.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import StrEnum
from typing import Any

from .contracts import (
    digest,
    reject_unknown_fields,
    require_bool,
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
    "ABSOLUTE_MIN_DEMONSTRATIONS",
    "Counterexample",
    "CounterexampleResult",
    "Demonstration",
    "DemonstrationOutcome",
    "DemonstrationStep",
    "Generalisation",
    "GeneralisationPolicy",
    "GymImprovement",
    "PrivacyClearance",
    "PrivacyPolicy",
    "Promotion",
    "PromotionEvidence",
    "SkillDraft",
    "SkillDraftRegistry",
    "Slot",
    "StepSignature",
    "TIERS",
    "clear_privacy",
    "evaluate_counterexamples",
    "generalise",
    "handle",
    "reusable_scripts",
]

register_codes(
    Category.SEMANTIC,
    "DEMONSTRATION_UNSTABLE",
    "GENERALISATION_UNSUPPORTED",
    "SKILL_TRIGGER_OVERBROAD",
)
register_codes(
    Category.POLICY,
    "PRIVACY_BLOCKED",
)
register_codes(
    Category.VERIFICATION,
    "COUNTEREXAMPLE_REQUIRED",
    "NO_MEASURED_IMPROVEMENT",
)
register_codes(
    Category.RELEASE,
    "DRAFT_NOT_PROMOTABLE",
    "PROMOTION_EVIDENCE_MISSING",
)

#: The promotion ladder.  A draft climbs one rung at a time; there is no jump
#: from ``draft`` to ``production`` because each rung is where a different kind
#: of evidence is demanded.
TIERS: tuple[str, ...] = ("draft", "candidate", "production")

#: Two demonstrations is the floor, whatever a caller's policy says.  One
#: demonstration cannot distinguish "this is the procedure" from "this is what
#: happened that day", so a policy asking for one is rejected at construction.
ABSOLUTE_MIN_DEMONSTRATIONS = 2

#: One counterexample is likewise the floor: a rule with no negative example
#: has never been shown a case it must decline.
ABSOLUTE_MIN_COUNTEREXAMPLES = 1

_QUANTUM = Decimal("0.0001")


def _ratio(numerator: int, denominator: int) -> Decimal:
    """Deterministic bounded ratio.

    The context precision and the rounding mode are pinned locally: a Decimal
    division that inherits the ambient context would give two processes two
    different confidences for the same evidence, which is exactly the class of
    bug ``canonical_json`` refuses floats to prevent.
    """

    if denominator <= 0:
        raise KernelError(
            code="MALFORMED_INPUT",
            message="ratio denominator must be positive",
            recommended_action="do not compute a ratio over an empty population",
        )
    with localcontext() as ctx:
        ctx.prec = 28
        value = Decimal(numerator) / Decimal(denominator)
        return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


class DemonstrationOutcome(StrEnum):
    """How a demonstration ended.

    Only ``SUCCEEDED`` is evidence of a procedure.  ``PARTIAL`` and
    ``INTERRUPTED`` are kept as separate values rather than folded into
    ``FAILED`` because a half-finished run tells you where the procedure
    breaks, and an interrupted one tells you nothing at all — the two must not
    be counted as the same observation.
    """

    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    INTERRUPTED = "INTERRUPTED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class StepSignature:
    """The shape of a step, with its argument *values* deliberately absent.

    Two steps share a signature when they call the same action on the same tool
    with the same argument keys.  Values are excluded on purpose: that is the
    line between "this step always happens" and "this step always happens with
    this literal", and conflating them is how a skill ends up hard-coded to one
    repository.
    """

    tool: str
    action: str
    argument_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        require_identifier(self.tool, "step.tool")
        require_identifier(self.action, "step.action")
        for index, key in enumerate(self.argument_keys):
            require_identifier(key, f"step.argument_keys[{index}]")
        if list(self.argument_keys) != sorted(self.argument_keys):
            raise KernelError(
                code="MALFORMED_INPUT",
                message="step signature argument keys must be sorted",
                recommended_action="sort the argument keys before constructing the signature",
            )

    @property
    def token(self) -> str:
        """Stable text form used as a dictionary key and in evidence."""

        return f"{self.tool}:{self.action}({','.join(self.argument_keys)})"

    def to_payload(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "action": self.action,
            "argumentKeys": list(self.argument_keys),
            "token": self.token,
        }


@dataclass(frozen=True, slots=True)
class DemonstrationStep:
    """One recorded tool call with the values it was actually made with."""

    tool: str
    action: str
    arguments: tuple[tuple[str, str], ...] = ()
    outcome: str = "ok"

    def __post_init__(self) -> None:
        require_identifier(self.tool, "step.tool")
        require_identifier(self.action, "step.action")
        seen: set[str] = set()
        for key, value in self.arguments:
            require_identifier(key, "step.argument key")
            require_str(value, f"step.arguments[{key}]")
            if key in seen:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"step {self.tool}:{self.action} repeats argument {key!r}",
                    recommended_action="send each argument once",
                )
            seen.add(key)
        if list(self.arguments) != sorted(self.arguments):
            raise KernelError(
                code="MALFORMED_INPUT",
                message="step arguments must be sorted by key",
                recommended_action="sort the (key, value) pairs before constructing the step",
            )

    @property
    def signature(self) -> StepSignature:
        return StepSignature(
            tool=self.tool,
            action=self.action,
            argument_keys=tuple(key for key, _ in self.arguments),
        )

    def value_of(self, key: str) -> str | None:
        for name, value in self.arguments:
            if name == key:
                return value
        return None

    def to_payload(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "action": self.action,
            "arguments": {key: value for key, value in self.arguments},
            "outcome": self.outcome,
            "signature": self.signature.token,
        }


@dataclass(frozen=True, slots=True)
class Demonstration:
    """One validated recording: what was done, on what, and whether it replayed.

    ``reproduced`` is a separate field from ``outcome`` because a run that
    succeeded once and has never been replayed is an anecdote.  Only a
    demonstration that both succeeded and reproduced feeds generalisation; the
    rest are reported as excluded, with the reason.
    """

    demonstration_id: str
    task_class: str
    steps: tuple[DemonstrationStep, ...]
    preconditions: tuple[str, ...] = ()
    outcome: DemonstrationOutcome = DemonstrationOutcome.SUCCEEDED
    reproduced: bool = False
    repo_snapshot_sha: str = ""
    tenant_id: str = ""
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.demonstration_id, "demonstration.demonstration_id")
        require_identifier(self.task_class, "demonstration.task_class")
        if not self.steps:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"demonstration {self.demonstration_id!r} records no steps",
                recommended_action="supply the ordered trace of tool calls",
            )
        if not isinstance(self.outcome, DemonstrationOutcome):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown demonstration outcome {self.outcome!r}",
                recommended_action=(
                    f"use one of {sorted(item.value for item in DemonstrationOutcome)}"
                ),
            )

    @property
    def signatures(self) -> tuple[StepSignature, ...]:
        return tuple(step.signature for step in self.steps)

    @property
    def is_eligible(self) -> bool:
        """Whether this demonstration may contribute to a generalisation."""

        return self.outcome is DemonstrationOutcome.SUCCEEDED and self.reproduced

    def exclusion_reason(self) -> str | None:
        if self.outcome is not DemonstrationOutcome.SUCCEEDED:
            return f"outcome {self.outcome} is not SUCCEEDED"
        if not self.reproduced:
            return "never reproduced; a single lucky run is not a procedure"
        return None

    def to_payload(self) -> dict[str, Any]:
        return {
            "demonstrationId": self.demonstration_id,
            "taskClass": self.task_class,
            "steps": [step.to_payload() for step in self.steps],
            "preconditions": list(self.preconditions),
            "outcome": str(self.outcome),
            "reproduced": self.reproduced,
            "repoSnapshotSha": self.repo_snapshot_sha,
            "evidenceIds": list(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class Slot:
    """A parameterised argument, carrying the values that were observed.

    ``observed_values`` travels with the slot so that a reviewer can see what
    the parameter was generalised *from*.  A slot with two observed values is a
    much weaker claim than one with nine, and hiding the set behind the word
    "parameter" makes the two look alike.
    """

    step_token: str
    name: str
    observed_values: tuple[str, ...]

    def __post_init__(self) -> None:
        require_identifier(self.name, "slot.name")
        if len(self.observed_values) < 2:
            raise KernelError(
                code="GENERALISATION_UNSUPPORTED",
                message=(
                    f"slot {self.name!r} on {self.step_token} was created from "
                    f"{len(self.observed_values)} observed value(s); a constant is not a slot"
                ),
                recommended_action="keep single-valued arguments as literals",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "stepToken": self.step_token,
            "name": self.name,
            "observedValues": list(self.observed_values),
            "observedValueCount": len(self.observed_values),
        }


@dataclass(frozen=True, slots=True)
class Generalisation:
    """The extracted procedure: what is invariant, what varies, what is unproven."""

    invariant_steps: tuple[StepSignature, ...]
    slots: tuple[Slot, ...]
    constants: tuple[tuple[str, str, str], ...]
    confirmed_preconditions: tuple[str, ...]
    unconfirmed_preconditions: tuple[str, ...]
    optional_steps: tuple[StepSignature, ...]
    supporting_demonstrations: tuple[str, ...]
    excluded_demonstrations: tuple[tuple[str, str], ...]
    confidence: Decimal

    def to_payload(self) -> dict[str, Any]:
        return {
            "invariantSteps": [item.to_payload() for item in self.invariant_steps],
            "slots": [item.to_payload() for item in self.slots],
            "constants": [
                {"stepToken": token, "name": name, "value": value}
                for token, name, value in self.constants
            ],
            "confirmedPreconditions": list(self.confirmed_preconditions),
            "unconfirmedPreconditions": list(self.unconfirmed_preconditions),
            "optionalSteps": [item.to_payload() for item in self.optional_steps],
            "supportingDemonstrations": list(self.supporting_demonstrations),
            "excludedDemonstrations": [
                {"demonstrationId": item, "reason": reason}
                for item, reason in self.excluded_demonstrations
            ],
            "generalisationConfidence": self.confidence,
            "confidenceMeasured": True,
        }


@dataclass(frozen=True, slots=True)
class Counterexample:
    """A trace on which the skill must *not* fire.

    This is the only input that gives a learned rule a boundary.  It carries
    the same shape as a demonstration trace — signatures plus preconditions —
    so that the draft's own trigger predicate can be run against it rather than
    a human asserting that it "looks different".
    """

    counterexample_id: str
    description: str
    step_tokens: tuple[str, ...]
    preconditions: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.counterexample_id, "counterexample.counterexample_id")
        require_str(self.description, "counterexample.description")

    def to_payload(self) -> dict[str, Any]:
        return {
            "counterexampleId": self.counterexample_id,
            "description": self.description,
            "stepTokens": list(self.step_tokens),
            "preconditions": list(self.preconditions),
            "evidenceIds": list(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class CounterexampleResult:
    """Whether the draft declined a case it was supposed to decline."""

    counterexample_id: str
    would_fire: bool
    reason: str

    @property
    def passed(self) -> bool:
        return not self.would_fire

    def to_payload(self) -> dict[str, Any]:
        return {
            "counterexampleId": self.counterexample_id,
            "wouldFire": self.would_fire,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PrivacyPolicy:
    """What may cross the boundary from a tenant's demonstration into a skill.

    ``scope`` decides how strict this is.  A tenant-scoped draft may keep the
    tenant's literals; a ``global`` draft may not, because a global skill is
    shipped to everyone and a literal path, host or identifier lifted from one
    customer's repository is a data leak with a version number on it.
    """

    tenant_id: str
    scope: str
    forbidden_value_prefixes: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.tenant_id, "privacy_policy.tenant_id")
        if self.scope not in {"tenant", "global"}:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown privacy scope {self.scope!r}",
                recommended_action="use 'tenant' or 'global'",
            )
        if not self.allowed_tools:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="privacy_policy.allowed_tools is empty; an empty allow-list denies all",
                recommended_action="declare the tools the demonstration may legitimately use",
            )

    @property
    def is_global(self) -> bool:
        return self.scope == "global"

    def to_payload(self) -> dict[str, Any]:
        return {
            "tenantId": self.tenant_id,
            "scope": self.scope,
            "forbiddenValuePrefixes": list(self.forbidden_value_prefixes),
            "allowedTools": list(self.allowed_tools),
        }


@dataclass(frozen=True, slots=True)
class PrivacyClearance:
    """The outcome of the privacy check, with what was redacted spelled out."""

    cleared: bool
    scope: str
    violations: tuple[str, ...]
    redacted_slots: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "cleared": self.cleared,
            "scope": self.scope,
            "violations": list(self.violations),
            "redactedSlots": list(self.redacted_slots),
        }


@dataclass(frozen=True, slots=True)
class GymImprovement:
    """A before/after measurement, or an honest admission that there is none.

    ``measured=False`` forces both scores to ``None``.  Reporting an unmeasured
    improvement as ``0`` would make "we never ran the gym" indistinguishable
    from "it made no difference", and only the second of those is a finding.
    """

    measured: bool
    baseline_score: int | None = None
    candidate_score: int | None = None
    sample_size: int = 0

    def __post_init__(self) -> None:
        if self.measured:
            if self.baseline_score is None or self.candidate_score is None:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message="a measured improvement must carry both scores",
                    recommended_action="supply baselineScore and candidateScore",
                )
            require_int(self.sample_size, "gym_improvement.sample_size", minimum=1)
        elif self.baseline_score is not None or self.candidate_score is not None:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="an unmeasured improvement must not carry scores",
                recommended_action="set measured=true or drop the scores",
            )

    @property
    def delta(self) -> int | None:
        if not self.measured:
            return None
        return int(self.candidate_score) - int(self.baseline_score)

    def to_payload(self) -> dict[str, Any]:
        return {
            "measured": self.measured,
            "baselineScore": self.baseline_score,
            "candidateScore": self.candidate_score,
            "delta": self.delta,
            "sampleSize": self.sample_size if self.measured else None,
        }


@dataclass(frozen=True, slots=True)
class GeneralisationPolicy:
    """How much agreement a draft needs before it is even allowed to be promoted."""

    min_demonstrations: int = ABSOLUTE_MIN_DEMONSTRATIONS
    min_counterexamples: int = ABSOLUTE_MIN_COUNTEREXAMPLES
    min_confidence: Decimal = Decimal("0.5")

    def __post_init__(self) -> None:
        require_int(self.min_demonstrations, "policy.min_demonstrations",
                    minimum=ABSOLUTE_MIN_DEMONSTRATIONS)
        require_int(self.min_counterexamples, "policy.min_counterexamples",
                    minimum=ABSOLUTE_MIN_COUNTEREXAMPLES)
        if not isinstance(self.min_confidence, Decimal):
            raise KernelError(
                code="MALFORMED_INPUT",
                message="policy.min_confidence must be a Decimal",
                recommended_action="send the threshold as a decimal string, never a float",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "minDemonstrations": self.min_demonstrations,
            "minCounterexamples": self.min_counterexamples,
            "minConfidence": self.min_confidence,
            "absoluteMinDemonstrations": ABSOLUTE_MIN_DEMONSTRATIONS,
            "absoluteMinCounterexamples": ABSOLUTE_MIN_COUNTEREXAMPLES,
        }


@dataclass(frozen=True, slots=True)
class SkillDraft:
    """A candidate skill that knows what it does not yet have.

    ``tier`` is always ``draft`` on construction.  There is no constructor
    argument that produces a promoted draft, so no code path can mint one; the
    only way up the ladder is :meth:`SkillDraftRegistry.promote`, which demands
    the evidence.
    """

    draft_id: str
    task_class: str
    generalisation: Generalisation
    counterexamples: tuple[Counterexample, ...]
    privacy: PrivacyClearance
    policy: GeneralisationPolicy
    references: tuple[str, ...] = ()
    tier: str = "draft"

    def __post_init__(self) -> None:
        require_identifier(self.draft_id, "draft.draft_id")
        require_identifier(self.task_class, "draft.task_class")
        if self.tier != "draft":
            raise KernelError(
                code="DRAFT_NOT_PROMOTABLE",
                message="a SkillDraft is always constructed at tier 'draft'",
                recommended_action="promote through SkillDraftRegistry.promote",
            )

    def would_fire(self, step_tokens: Sequence[str],
                   preconditions: Iterable[str]) -> tuple[bool, str]:
        """The draft's trigger predicate, used for both positive and negative tests.

        The predicate is the whole rule: every confirmed precondition must hold
        and the invariant step sequence must appear as an ordered subsequence.
        Running counterexamples through the same function that decides real
        activations is the point — a boundary checked by a different code path
        is a boundary that drifts.  When it does not fire, *every* failing check
        is reported, not the first.
        """

        reasons: list[str] = []
        missing = [item for item in self.generalisation.confirmed_preconditions
                   if item not in set(preconditions)]
        if missing:
            reasons.append(f"precondition(s) not met: {sorted(missing)}")
        wanted = [item.token for item in self.generalisation.invariant_steps]
        cursor = 0
        for token in step_tokens:
            if cursor < len(wanted) and token == wanted[cursor]:
                cursor += 1
        if cursor < len(wanted):
            reasons.append(f"invariant step {wanted[cursor]!r} absent from the trace")
        if reasons:
            # Every reason, not the first one.  Short-circuiting turned fixing a
            # counterexample into whack-a-mole: the author satisfies the
            # precondition, re-runs, and only then learns an invariant step was
            # also missing.  The caller gets the whole boundary in one pass.
            return False, "; ".join(reasons)
        return True, "all preconditions hold and every invariant step is present in order"

    def blockers(self, evidence: PromotionEvidence | None = None) -> tuple[str, ...]:
        """Everything standing between this draft and the next tier.

        Returned as text rather than raised so that ``handle`` can report a
        draft *and* its gaps in one pass; promotion raises on the same list.
        """

        reasons: list[str] = []
        support = len(self.generalisation.supporting_demonstrations)
        if support < self.policy.min_demonstrations:
            reasons.append(
                f"{support} supporting demonstration(s), "
                f"{self.policy.min_demonstrations} required"
            )
        if len(self.counterexamples) < self.policy.min_counterexamples:
            reasons.append(
                f"{len(self.counterexamples)} counterexample(s), "
                f"{self.policy.min_counterexamples} required; a rule learned only from "
                "positives has no boundary"
            )
        if self.generalisation.confidence < self.policy.min_confidence:
            reasons.append(
                f"generalisation confidence {self.generalisation.confidence} is below the "
                f"required {self.policy.min_confidence}"
            )
        if not self.privacy.cleared:
            reasons.append(
                f"privacy not cleared: {list(self.privacy.violations)}"
            )
        if evidence is None:
            reasons.append("no promotion evidence supplied")
            return tuple(reasons)
        reasons.extend(evidence.blockers())
        return tuple(reasons)

    def to_payload(self) -> dict[str, Any]:
        return {
            "draftId": self.draft_id,
            "taskClass": self.task_class,
            "tier": self.tier,
            "generalisation": self.generalisation.to_payload(),
            "counterexamples": [item.to_payload() for item in self.counterexamples],
            "privacy": self.privacy.to_payload(),
            "policy": self.policy.to_payload(),
            "references": list(self.references),
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class PromotionEvidence:
    """What a promotion has to show, gathered in one place so none of it is optional."""

    counterexample_results: tuple[CounterexampleResult, ...]
    improvement: GymImprovement
    approver: str
    rationale: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.approver, "promotion.approver")
        if not self.rationale.strip():
            raise KernelError(
                code="PROMOTION_EVIDENCE_MISSING",
                message="a promotion needs a recorded rationale",
                recommended_action="state why this draft should climb a tier",
            )

    def blockers(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if not self.counterexample_results:
            reasons.append("no counterexample was executed against the draft")
        failed = [item.counterexample_id for item in self.counterexample_results
                  if not item.passed]
        if failed:
            reasons.append(f"the draft fires on counterexample(s) {sorted(failed)}")
        if not self.improvement.measured:
            reasons.append(
                "gym improvement is unmeasured; unmeasured is not zero and is not positive"
            )
        elif (self.improvement.delta or 0) <= 0:
            reasons.append(
                f"gym improvement delta {self.improvement.delta} is not positive"
            )
        return tuple(reasons)

    def to_payload(self) -> dict[str, Any]:
        return {
            "counterexampleResults": [item.to_payload() for item in self.counterexample_results],
            "improvement": self.improvement.to_payload(),
            "approver": self.approver,
            "rationale": self.rationale,
            "evidenceIds": list(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class Promotion:
    """One rung climbed, with who authorised it and on what evidence."""

    draft_id: str
    draft_digest: str
    from_tier: str
    to_tier: str
    evidence: PromotionEvidence

    def to_payload(self) -> dict[str, Any]:
        return {
            "draftId": self.draft_id,
            "draftDigest": self.draft_digest,
            "fromTier": self.from_tier,
            "toTier": self.to_tier,
            "evidence": self.evidence.to_payload(),
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


# --- generalisation ----------------------------------------------------------


def _lcs(left: Sequence[str], right: Sequence[str]) -> tuple[str, ...]:
    """Longest common subsequence with a deterministic tie-break.

    The invariant step sequence is the LCS folded across every eligible
    demonstration.  An intersection of *sets* would happily claim a step order
    nobody ever performed; the subsequence keeps the ordering that every
    demonstration actually agreed on.  Ties prefer the shorter prefix so the
    result does not depend on iteration accidents.
    """

    rows, cols = len(left), len(right)
    table = [[0] * (cols + 1) for _ in range(rows + 1)]
    for i in range(rows - 1, -1, -1):
        for j in range(cols - 1, -1, -1):
            if left[i] == right[j]:
                table[i][j] = table[i + 1][j + 1] + 1
            else:
                table[i][j] = max(table[i + 1][j], table[i][j + 1])
    out: list[str] = []
    i = j = 0
    while i < rows and j < cols:
        if left[i] == right[j]:
            out.append(left[i])
            i += 1
            j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            i += 1
        else:
            j += 1
    return tuple(out)


def _observed_values(demonstrations: Sequence[Demonstration], token: str,
                     key: str) -> tuple[str, ...]:
    values: list[str] = []
    for demo in demonstrations:
        for step in demo.steps:
            if step.signature.token == token:
                value = step.value_of(key)
                if value is not None and value not in values:
                    values.append(value)
    return tuple(sorted(values))


def generalise(demonstrations: Sequence[Demonstration]) -> Generalisation:
    """Extract the invariant procedure, its slots and its confirmed preconditions.

    Ineligible demonstrations are excluded *with a reason* rather than dropped,
    and the confidence is computed from how many of the submitted
    demonstrations survived that filter as well as how many agreed — a
    generalisation drawn from three of thirty runs is a different claim from
    one drawn from three of three, and one number that hides which is worse
    than two numbers that do not.
    """

    if not demonstrations:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="no demonstrations were supplied",
            recommended_action="supply at least one validated demonstration",
        )
    eligible = tuple(item for item in demonstrations if item.is_eligible)
    excluded = tuple(
        (item.demonstration_id, item.exclusion_reason() or "")
        for item in demonstrations if not item.is_eligible
    )
    if not eligible:
        raise KernelError(
            code="DEMONSTRATION_UNSTABLE",
            message=(
                "no demonstration both succeeded and reproduced; "
                f"{len(demonstrations)} submitted, all excluded"
            ),
            retryable=False,
            recommended_action="replay the demonstrations and record the reproduction",
            details={"excluded": [{"demonstrationId": i, "reason": r} for i, r in excluded]},
        )
    task_classes = sorted({item.task_class for item in eligible})
    if len(task_classes) > 1:
        raise KernelError(
            code="GENERALISATION_UNSUPPORTED",
            message=(
                f"demonstrations span several task classes {task_classes}; "
                "generalising across them would invent a procedure nobody performed"
            ),
            recommended_action="group the demonstrations by task class first",
        )

    common = tuple(item.token for item in eligible[0].signatures)
    for demo in eligible[1:]:
        common = _lcs(common, tuple(item.token for item in demo.signatures))
    if not common:
        raise KernelError(
            code="GENERALISATION_UNSUPPORTED",
            message=(
                "the demonstrations share no ordered step in common; "
                "there is no procedure here to extract"
            ),
            recommended_action="group demonstrations that actually perform the same task",
        )

    by_token: dict[str, StepSignature] = {}
    for demo in eligible:
        for signature in demo.signatures:
            by_token.setdefault(signature.token, signature)
    invariant = tuple(by_token[token] for token in common)
    optional = tuple(
        by_token[token] for token in sorted(set(by_token) - set(common))
    )

    slots: list[Slot] = []
    constants: list[tuple[str, str, str]] = []
    for signature in invariant:
        for key in signature.argument_keys:
            values = _observed_values(eligible, signature.token, key)
            if len(values) > 1:
                slots.append(Slot(step_token=signature.token, name=key,
                                  observed_values=values))
            elif len(values) == 1:
                constants.append((signature.token, key, values[0]))

    precondition_sets = [set(item.preconditions) for item in eligible]
    confirmed = tuple(sorted(set.intersection(*precondition_sets))) if precondition_sets else ()
    union = tuple(sorted(set.union(*precondition_sets))) if precondition_sets else ()
    unconfirmed = tuple(item for item in union if item not in set(confirmed))

    agreeing = len(eligible)
    confidence = _ratio(agreeing, agreeing + 1) * _ratio(agreeing, len(demonstrations))
    confidence = confidence.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)
    # A weak generalisation is still worth drafting; the policy thresholds are
    # applied as promotion blockers, not as a reason to refuse the draft.
    return Generalisation(
        invariant_steps=invariant,
        slots=tuple(slots),
        constants=tuple(constants),
        confirmed_preconditions=confirmed,
        unconfirmed_preconditions=unconfirmed,
        optional_steps=optional,
        supporting_demonstrations=tuple(sorted(item.demonstration_id for item in eligible)),
        excluded_demonstrations=excluded,
        confidence=confidence,
    )


def clear_privacy(generalisation: Generalisation, policy: PrivacyPolicy) -> PrivacyClearance:
    """Decide whether this generalisation may be shipped at the requested scope.

    A global draft carrying a tenant literal is refused rather than
    auto-redacted: silently rewriting a constant into a slot would change what
    the skill does while telling nobody, and the caller who asked for a global
    skill should be told their evidence is tenant-shaped.
    """

    violations: list[str] = []
    redacted: list[str] = []
    for signature in generalisation.invariant_steps:
        if signature.tool not in set(policy.allowed_tools):
            violations.append(
                f"step {signature.token} uses tool {signature.tool!r}, "
                "which is outside the permission profile"
            )
    for token, name, value in generalisation.constants:
        for prefix in policy.forbidden_value_prefixes:
            if value.startswith(prefix):
                if policy.is_global:
                    violations.append(
                        f"constant {name!r} on {token} carries tenant-private value "
                        f"prefixed {prefix!r}; it cannot enter a global skill"
                    )
                else:
                    redacted.append(f"{token}.{name}")
                break
    return PrivacyClearance(
        cleared=not violations,
        scope=policy.scope,
        violations=tuple(violations),
        redacted_slots=tuple(sorted(set(redacted))),
    )


def evaluate_counterexamples(draft: SkillDraft) -> tuple[CounterexampleResult, ...]:
    """Run every counterexample through the draft's own trigger predicate.

    A counterexample the draft fires on is not a low score, it is a defect in
    the generalisation, and it raises ``SKILL_TRIGGER_OVERBROAD`` at promotion
    time.  Here the results are returned so the caller can see all of them at
    once instead of one raise per fix cycle.
    """

    results: list[CounterexampleResult] = []
    for item in sorted(draft.counterexamples, key=lambda entry: entry.counterexample_id):
        fires, reason = draft.would_fire(item.step_tokens, item.preconditions)
        results.append(CounterexampleResult(
            counterexample_id=item.counterexample_id,
            would_fire=fires,
            reason=reason,
        ))
    return tuple(results)


def reusable_scripts(generalisation: Generalisation) -> tuple[Mapping[str, Any], ...]:
    """Propose scripts only for runs of steps with nothing left to decide.

    A script is appropriate where the logic is deterministic and repeated: a
    maximal run of consecutive invariant steps that carries no slot.  A run
    containing a slot stays prose, because a script that hard-codes one
    observed value is the failure mode this whole module is trying to avoid.
    """

    slotted = {item.step_token for item in generalisation.slots}
    scripts: list[Mapping[str, Any]] = []
    run: list[StepSignature] = []

    def flush() -> None:
        if len(run) >= 2:
            scripts.append({
                "scriptId": f"script-{len(scripts) + 1:03d}",
                "steps": [item.token for item in run],
                "deterministic": True,
                "rationale": (
                    "consecutive invariant steps with no varying slot; "
                    "deterministic repeated logic belongs in a script"
                ),
            })
        run.clear()

    for signature in generalisation.invariant_steps:
        if signature.token in slotted:
            flush()
            continue
        run.append(signature)
    flush()
    return tuple(scripts)


# --- promotion ladder --------------------------------------------------------


class SkillDraftRegistry:
    """The only way a draft moves, and it never moves on its own.

    The ladder is ``draft -> candidate -> production``.  Admission is
    idempotent on the draft digest, so a redelivered draft does not create a
    second entry, while a *different* draft under an existing id is an
    ``IDEMPOTENCY_CONFLICT`` rather than a silent overwrite — a promoted id
    whose contents changed underneath is indistinguishable from an approved
    skill that was never approved.
    """

    def __init__(self, events: EventStore | None = None, *, stream_id: str = "skill-drafts"):
        self._events = events
        self._stream_id = stream_id
        self._drafts: dict[str, SkillDraft] = {}
        self._tiers: dict[str, str] = {}
        self._promotions: dict[str, list[Promotion]] = {}

    def admit(self, draft: SkillDraft) -> str:
        """Record a draft at tier ``draft``.  Never promotes, by construction."""

        existing = self._drafts.get(draft.draft_id)
        if existing is not None:
            if existing.digest != draft.digest:
                raise KernelError(
                    code="IDEMPOTENCY_CONFLICT",
                    message=(
                        f"draft {draft.draft_id!r} is already registered with a different "
                        "digest; a registered draft is immutable"
                    ),
                    recommended_action="register the changed draft under a new id",
                    details={"draftId": draft.draft_id},
                )
            return self._tiers[draft.draft_id]
        self._drafts[draft.draft_id] = draft
        self._tiers[draft.draft_id] = "draft"
        self._promotions[draft.draft_id] = []
        return "draft"

    def tier(self, draft_id: str) -> str:
        if draft_id not in self._tiers:
            raise KernelError(
                code="DRAFT_NOT_PROMOTABLE",
                message=f"draft {draft_id!r} is not registered",
                recommended_action="admit the draft before asking about its tier",
            )
        return self._tiers[draft_id]

    def promotions(self, draft_id: str) -> tuple[Promotion, ...]:
        return tuple(self._promotions.get(draft_id, ()))

    def promote(self, draft_id: str, *, to_tier: str, evidence: PromotionEvidence,
                fencing_token: int) -> Promotion:
        """Climb exactly one rung, or raise with the reason.

        Every failure mode here is a raise rather than a returned ``False``:
        a caller that ignores a returned boolean ships the skill anyway, and
        this is the one call in the module that has a production side effect.
        """

        require_int(fencing_token, "fencing_token", minimum=1)
        draft = self._drafts.get(draft_id)
        if draft is None:
            raise KernelError(
                code="DRAFT_NOT_PROMOTABLE",
                message=f"draft {draft_id!r} is not registered",
                recommended_action="admit the draft first",
            )
        current = self._tiers[draft_id]
        if to_tier not in TIERS:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown tier {to_tier!r}",
                recommended_action=f"use one of {list(TIERS)}",
            )
        if TIERS.index(to_tier) != TIERS.index(current) + 1:
            raise KernelError(
                code="DRAFT_NOT_PROMOTABLE",
                message=(
                    f"draft {draft_id!r} is at tier {current!r}; {to_tier!r} is not the "
                    "next rung and the ladder cannot be skipped"
                ),
                recommended_action=f"promote to {TIERS[TIERS.index(current) + 1]!r} first"
                if TIERS.index(current) + 1 < len(TIERS) else "the draft is already at the top",
            )

        results = evaluate_counterexamples(draft)
        if not draft.counterexamples:
            raise KernelError(
                code="COUNTEREXAMPLE_REQUIRED",
                message=(
                    f"draft {draft_id!r} has no counterexample; a rule learned only from "
                    "positive examples has no boundary and cannot be promoted"
                ),
                retryable=False,
                recommended_action="record at least one trace on which the skill must not fire",
                details={"draftId": draft_id},
            )
        fired = [item.counterexample_id for item in results if item.would_fire]
        if fired:
            raise KernelError(
                code="SKILL_TRIGGER_OVERBROAD",
                message=(
                    f"draft {draft_id!r} fires on counterexample(s) {sorted(fired)}; "
                    "the generalisation is wider than the evidence"
                ),
                retryable=False,
                recommended_action="add a precondition or an invariant step that excludes them",
                details={"draftId": draft_id, "counterexamples": sorted(fired)},
            )
        if not draft.privacy.cleared:
            raise KernelError(
                code="PRIVACY_BLOCKED",
                message=(
                    f"draft {draft_id!r} did not clear privacy: "
                    f"{list(draft.privacy.violations)}"
                ),
                retryable=False,
                recommended_action="scope the draft to the tenant or remove the private values",
                details={"draftId": draft_id, "violations": list(draft.privacy.violations)},
            )
        if not evidence.improvement.measured:
            raise KernelError(
                code="NO_MEASURED_IMPROVEMENT",
                message=(
                    f"draft {draft_id!r} carries no gym measurement; unmeasured is not "
                    "zero and is not positive"
                ),
                retryable=True,
                recommended_action="run the draft through the repository gym and re-submit",
                details={"draftId": draft_id},
            )
        blockers = draft.blockers(evidence)
        if blockers:
            raise KernelError(
                code="DRAFT_NOT_PROMOTABLE",
                message=f"draft {draft_id!r} is not promotable: {list(blockers)}",
                retryable=False,
                recommended_action="close every blocker before promoting",
                details={"draftId": draft_id, "blockers": list(blockers)},
            )

        promotion = Promotion(
            draft_id=draft_id,
            draft_digest=draft.digest,
            from_tier=current,
            to_tier=to_tier,
            evidence=PromotionEvidence(
                counterexample_results=results,
                improvement=evidence.improvement,
                approver=evidence.approver,
                rationale=evidence.rationale,
                evidence_ids=evidence.evidence_ids,
            ),
        )
        if self._events is not None:
            self._events.append(self._stream_id, promotion.to_payload(),
                                idempotency_key=promotion.digest,
                                fencing_token=fencing_token)
        self._tiers[draft_id] = to_tier
        self._promotions[draft_id].append(promotion)
        return promotion


# --- registry entry point ----------------------------------------------------

_REQUEST_FIELDS = frozenset({
    "validated_demonstration", "run_artifacts", "expert_annotations", "privacy_policy",
})


def _decode_step(payload: Mapping[str, Any]) -> DemonstrationStep:
    reject_unknown_fields(payload, {"tool", "action", "arguments", "outcome"},
                          field_name="step")
    raw_arguments = payload.get("arguments", {})
    arguments = require_mapping(raw_arguments, "step.arguments") if raw_arguments else {}
    pairs = tuple(sorted(
        (require_identifier(key, "step.arguments key"),
         require_str(value, f"step.arguments[{key}]"))
        for key, value in arguments.items()
    ))
    return DemonstrationStep(
        tool=require_identifier(payload.get("tool"), "step.tool"),
        action=require_identifier(payload.get("action"), "step.action"),
        arguments=pairs,
        outcome=str(payload.get("outcome", "ok")),
    )


def _decode_demonstration(payload: Mapping[str, Any], *, snapshot: str) -> Demonstration:
    reject_unknown_fields(
        payload,
        {"demonstrationId", "taskClass", "steps", "preconditions", "outcome", "reproduced",
         "repoSnapshotSha", "evidenceIds"},
        field_name="demonstration",
    )
    outcome = require_str(payload.get("outcome", "SUCCEEDED"), "demonstration.outcome",
                          max_length=32)
    if outcome not in {item.value for item in DemonstrationOutcome}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown demonstration outcome {outcome!r}",
            recommended_action=(
                f"use one of {sorted(item.value for item in DemonstrationOutcome)}"
            ),
        )
    demonstration_snapshot = require_str(
        payload.get("repoSnapshotSha", snapshot), "demonstration.repoSnapshotSha",
        max_length=128,
    )
    demonstration_id = require_identifier(payload.get("demonstrationId"),
                                          "demonstration.demonstrationId")
    if demonstration_snapshot != snapshot:
        raise KernelError(
            code="STALE_SNAPSHOT",
            message=(
                f"demonstration {demonstration_id!r} was recorded against snapshot "
                f"{demonstration_snapshot} but the draft is being built for {snapshot}"
            ),
            retryable=False,
            recommended_action="replay the demonstration against the current snapshot",
            details={"demonstrationId": demonstration_id},
        )
    steps = tuple(
        _decode_step(require_mapping(item, "demonstration.steps[]"))
        for item in payload.get("steps", ())
    )
    return Demonstration(
        demonstration_id=demonstration_id,
        task_class=require_identifier(payload.get("taskClass"), "demonstration.taskClass"),
        steps=steps,
        preconditions=require_str_seq(payload.get("preconditions", ()),
                                      "demonstration.preconditions"),
        outcome=DemonstrationOutcome(outcome),
        reproduced=require_bool(payload.get("reproduced", False), "demonstration.reproduced"),
        repo_snapshot_sha=demonstration_snapshot,
        evidence_ids=require_str_seq(payload.get("evidenceIds", ()),
                                     "demonstration.evidenceIds"),
    )


def _decode_counterexample(payload: Mapping[str, Any]) -> Counterexample:
    reject_unknown_fields(
        payload,
        {"counterexampleId", "description", "stepTokens", "preconditions", "evidenceIds"},
        field_name="counterexample",
    )
    return Counterexample(
        counterexample_id=require_identifier(payload.get("counterexampleId"),
                                             "counterexample.counterexampleId"),
        description=require_str(payload.get("description"), "counterexample.description"),
        step_tokens=require_str_seq(payload.get("stepTokens", ()),
                                    "counterexample.stepTokens"),
        preconditions=require_str_seq(payload.get("preconditions", ()),
                                      "counterexample.preconditions"),
        evidence_ids=require_str_seq(payload.get("evidenceIds", ()),
                                     "counterexample.evidenceIds"),
    )


def _decode_improvement(payload: Mapping[str, Any] | None) -> GymImprovement:
    if payload is None:
        return GymImprovement(measured=False)
    reject_unknown_fields(payload, {"measured", "baselineScore", "candidateScore", "sampleSize"},
                          field_name="gymImprovement")
    measured = require_bool(payload.get("measured", False), "gymImprovement.measured")
    if not measured:
        return GymImprovement(measured=False)
    return GymImprovement(
        measured=True,
        baseline_score=require_int(payload.get("baselineScore"),
                                   "gymImprovement.baselineScore", minimum=0),
        candidate_score=require_int(payload.get("candidateScore"),
                                    "gymImprovement.candidateScore", minimum=0),
        sample_size=require_int(payload.get("sampleSize", 1), "gymImprovement.sampleSize",
                                minimum=1),
    )


@register("demonstration-to-skill")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point.

    Produces a draft and the exact list of what stands between it and
    promotion.  It deliberately does not promote anything, and there is no
    input field that would let it: an ``expert_annotations`` payload asking for
    immediate promotion is data, not authority, and reaches the output only as
    a recorded rationale on a draft that is still a draft.
    """

    reject_unknown_fields(request, _REQUEST_FIELDS,
                          field_name="demonstration-to-skill request")
    demonstration_payload = require_mapping(request.get("validated_demonstration"),
                                            "validated_demonstration")
    reject_unknown_fields(demonstration_payload,
                          {"draftId", "demonstrations", "repoSnapshotSha", "policy"},
                          field_name="validated_demonstration")
    snapshot = require_str(demonstration_payload.get("repoSnapshotSha"),
                           "validated_demonstration.repoSnapshotSha", max_length=128)
    draft_id = require_identifier(demonstration_payload.get("draftId"),
                                  "validated_demonstration.draftId")
    raw_demonstrations = demonstration_payload.get("demonstrations", ())
    if not isinstance(raw_demonstrations, Sequence) or isinstance(raw_demonstrations, str):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="validated_demonstration.demonstrations must be an array",
            recommended_action="supply the demonstrations as a JSON array",
        )
    if not raw_demonstrations:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="validated_demonstration.demonstrations is empty",
            recommended_action="supply at least one validated demonstration",
        )
    demonstrations = tuple(
        _decode_demonstration(require_mapping(item, "demonstrations[]"), snapshot=snapshot)
        for item in raw_demonstrations
    )

    policy_payload = demonstration_payload.get("policy")
    if policy_payload is None:
        policy = GeneralisationPolicy()
    else:
        policy_payload = require_mapping(policy_payload, "validated_demonstration.policy")
        reject_unknown_fields(policy_payload,
                              {"minDemonstrations", "minCounterexamples", "minConfidence"},
                              field_name="validated_demonstration.policy")
        policy = GeneralisationPolicy(
            min_demonstrations=require_int(
                policy_payload.get("minDemonstrations", ABSOLUTE_MIN_DEMONSTRATIONS),
                "policy.minDemonstrations", minimum=ABSOLUTE_MIN_DEMONSTRATIONS),
            min_counterexamples=require_int(
                policy_payload.get("minCounterexamples", ABSOLUTE_MIN_COUNTEREXAMPLES),
                "policy.minCounterexamples", minimum=ABSOLUTE_MIN_COUNTEREXAMPLES),
            min_confidence=require_decimal(policy_payload.get("minConfidence", "0.5"),
                                           "policy.minConfidence", minimum=Decimal(0)),
        )

    privacy_payload = require_mapping(request.get("privacy_policy"), "privacy_policy")
    reject_unknown_fields(privacy_payload,
                          {"tenantId", "scope", "forbiddenValuePrefixes", "allowedTools"},
                          field_name="privacy_policy")
    privacy_policy = PrivacyPolicy(
        tenant_id=require_identifier(privacy_payload.get("tenantId"), "privacy_policy.tenantId"),
        scope=require_str(privacy_payload.get("scope"), "privacy_policy.scope", max_length=32),
        forbidden_value_prefixes=require_str_seq(
            privacy_payload.get("forbiddenValuePrefixes", ()),
            "privacy_policy.forbiddenValuePrefixes"),
        allowed_tools=require_str_seq(privacy_payload.get("allowedTools", ()),
                                      "privacy_policy.allowedTools", allow_empty=False),
    )

    annotations = require_mapping(request.get("expert_annotations", {}), "expert_annotations")
    reject_unknown_fields(annotations,
                          {"counterexamples", "approver", "rationale", "gymImprovement"},
                          field_name="expert_annotations")
    counterexamples = tuple(
        _decode_counterexample(require_mapping(item, "counterexamples[]"))
        for item in annotations.get("counterexamples", ())
    )
    improvement = _decode_improvement(
        require_mapping(annotations["gymImprovement"], "expert_annotations.gymImprovement")
        if annotations.get("gymImprovement") is not None else None
    )

    artifacts = require_mapping(request.get("run_artifacts", {}), "run_artifacts")
    reject_unknown_fields(artifacts, {"references", "evidenceIds"}, field_name="run_artifacts")
    references = require_str_seq(artifacts.get("references", ()), "run_artifacts.references")
    artifact_evidence = require_str_seq(artifacts.get("evidenceIds", ()),
                                        "run_artifacts.evidenceIds")

    generalisation = generalise(demonstrations)
    clearance = clear_privacy(generalisation, privacy_policy)
    if not clearance.cleared and any("outside the permission profile" in item
                                     for item in clearance.violations):
        raise KernelError(
            code="TOOL_DENIED",
            message=(
                "the demonstration uses a tool outside the permission profile: "
                f"{list(clearance.violations)}"
            ),
            retryable=False,
            recommended_action="grant the tool explicitly or drop the demonstration",
            details={"violations": list(clearance.violations)},
        )

    draft = SkillDraft(
        draft_id=draft_id,
        task_class=demonstrations[0].task_class,
        generalisation=generalisation,
        counterexamples=counterexamples,
        privacy=clearance,
        policy=policy,
        references=references,
    )
    results = evaluate_counterexamples(draft)
    evidence = None
    if counterexamples and annotations.get("approver") and annotations.get("rationale"):
        evidence = PromotionEvidence(
            counterexample_results=results,
            improvement=improvement,
            approver=require_identifier(annotations.get("approver"),
                                        "expert_annotations.approver"),
            rationale=require_str(annotations.get("rationale"),
                                  "expert_annotations.rationale"),
        )
    blockers = draft.blockers(evidence)

    evidence_ids = sorted({
        item for demo in demonstrations for item in demo.evidence_ids
    } | {item for entry in counterexamples for item in entry.evidence_ids}
        | set(artifact_evidence))
    trigger_examples = {
        "positive": [
            {
                "demonstrationId": demo.demonstration_id,
                "stepTokens": [item.signature.token for item in demo.steps],
                "preconditions": list(demo.preconditions),
                "fires": draft.would_fire(
                    [item.signature.token for item in demo.steps], demo.preconditions)[0],
            }
            for demo in demonstrations if demo.is_eligible
        ],
        "negative": [item.to_payload() for item in results],
        "negativeCount": len(results),
    }
    return {
        "skill_draft": {
            **draft.to_payload(),
            "draftDigest": draft.digest,
            "promotable": not blockers,
            "promotionBlockers": list(blockers),
            "autoPromoted": False,
            "improvement": improvement.to_payload(),
        },
        "trigger_examples": trigger_examples,
        "reusable_scripts": [dict(item) for item in reusable_scripts(generalisation)],
        "references": list(references),
        "regression_fixtures": [
            {
                "fixtureId": f"fixture-{demo.demonstration_id}",
                "kind": "positive",
                "demonstrationId": demo.demonstration_id,
                "expectFire": True,
            }
            for demo in demonstrations if demo.is_eligible
        ] + [
            {
                "fixtureId": f"fixture-{item.counterexample_id}",
                "kind": "negative",
                "counterexampleId": item.counterexample_id,
                "expectFire": False,
            }
            for item in sorted(counterexamples, key=lambda entry: entry.counterexample_id)
        ],
        "evidenceIds": evidence_ids,
    }
