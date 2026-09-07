"""Task spec and delta compilation: informal intent in, a versioned contract out.

This module owns the moment where a sentence becomes a commitment.  The trap it
closes is the cheapest and most expensive mistake in the whole kernel: resolving
an ambiguity by guessing.  A guess is indistinguishable from a decision once it
is written down, so every ambiguity this compiler finds becomes an
:class:`OpenQuestion` with a stable id and a ``blocking`` flag, and a spec that
still carries a blocking question can never be marked ready.  Detection is done
by *declared* detectors — each one has an id and appears in the output whether
or not it fired, so a reader can tell "nothing was found" apart from "nothing
was looked for", which is the same distinction the rest of this repository draws
between a measured zero and an unmeasured quantity.

Two smaller rules matter downstream.  A :class:`TaskSpec` is canonically ordered
(scope, constraints, criteria and questions are all sorted at construction), so
re-compiling the same inputs yields a byte-identical content address rather than
one that depends on the order a caller happened to build a list.  And
:func:`compile_delta` is *minimal*: a criterion that did not change never appears
in it, because the orchestrator reruns exactly the steps the delta names and a
spurious entry costs a full rerun of work that was already correct.

The informal intent is stored as a digest, never as text.  Requirements arrive
from READMEs, issues and comments, which are untrusted data; letting the raw
string ride into the spec would hand any of them a seat in a downstream prompt.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .contracts import (
    digest,
    reject_unknown_fields,
    require_bool,
    require_identifier,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .registry import register

__all__ = [
    "AcceptanceCriterion",
    "Assumption",
    "Change",
    "ChangeKind",
    "Constraint",
    "DETECTORS",
    "Detector",
    "DetectorReport",
    "OpenQuestion",
    "RepositorySnapshot",
    "RiskDirection",
    "SpecDelta",
    "SpecPolicy",
    "SpecStatus",
    "StepBinding",
    "StepInvalidation",
    "TaskSpec",
    "UNQUANTIFIED_ADJECTIVES",
    "VerifierType",
    "compile_delta",
    "compile_task_spec",
    "handle",
    "matching_paths",
]

register_codes(
    Category.SEMANTIC,
    "SPEC_INVALID",
    "AMBIGUITY_BLOCKED",
    "DELTA_IMPACT_UNCOMPUTABLE",
)
register_codes(Category.POLICY, "POLICY_CONFLICT")
register_codes(Category.INPUT, "STALE_BASE_SPEC")

_MAX_INTENT_CHARS = 1 << 16
_SENTENCE_SPLIT = re.compile(r"[.!?;\n]+")
_WORD = re.compile(r"[a-z][a-z0-9'-]*")
_MEASURABLE = re.compile(r"\d")


class VerifierType(StrEnum):
    """How an acceptance criterion is checked.

    ``UNVERIFIED`` exists so that a criterion which nobody knows how to check
    must say so.  Without it the honest state has no representation and the
    author reaches for the nearest plausible verifier, which produces a spec
    that looks complete and gates on nothing.
    """

    TEST = "test"
    CONTRACT_TEST = "contract-test"
    STATIC_ANALYSIS = "static-analysis"
    BENCHMARK = "benchmark"
    POLICY_CHECK = "policy-check"
    MANUAL_REVIEW = "manual-review"
    UNVERIFIED = "unverified"

    @property
    def is_verifiable(self) -> bool:
        """True when some named party can produce a verdict for this criterion."""

        return self is not VerifierType.UNVERIFIED

    @property
    def is_machine_verifiable(self) -> bool:
        """True only for verifiers a machine can run unattended."""

        return self.is_verifiable and self is not VerifierType.MANUAL_REVIEW


class SpecStatus(StrEnum):
    """Whether a spec may be handed to an executor.

    ``BLOCKED`` is not a soft warning.  It is the state of a spec that contains
    a question no one has answered, and :meth:`TaskSpec.require_ready` is the
    single place that decision is enforced so no caller can widen it.
    """

    READY = "READY"
    BLOCKED = "BLOCKED"


class ChangeKind(StrEnum):
    """The vocabulary a :class:`SpecDelta` is allowed to speak in."""

    OBJECTIVE_CHANGED = "objective-changed"
    CRITERION_ADDED = "criterion-added"
    CRITERION_REMOVED = "criterion-removed"
    CRITERION_CHANGED = "criterion-changed"
    CONSTRAINT_ADDED = "constraint-added"
    CONSTRAINT_REMOVED = "constraint-removed"
    CONSTRAINT_CHANGED = "constraint-changed"
    NON_GOAL_ADDED = "non-goal-added"
    NON_GOAL_REMOVED = "non-goal-removed"
    SCOPE_WIDENED = "scope-widened"
    SCOPE_NARROWED = "scope-narrowed"


class RiskDirection(StrEnum):
    """Whether a change enlarges, shrinks or leaves alone the blast radius."""

    INCREASES = "increases"
    DECREASES = "decreases"
    NEUTRAL = "neutral"


# --- glob resolution ---------------------------------------------------------


@functools.lru_cache(maxsize=1024)
def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Compile a repository-relative glob into an anchored regex.

    ``*`` and ``?`` never cross a path separator; ``**`` does.  Python 3.11 has
    no path-aware glob matcher (``PurePath.full_match`` arrived in 3.13) and
    ``fnmatch`` treats ``/`` as an ordinary character, which would make
    ``src/*`` match ``src/a/b/c.py``.  A scope that silently matches more than
    it says is exactly the failure this module exists to prevent.
    """

    out: list[str] = ["^"]
    index = 0
    length = len(pattern)
    while index < length:
        char = pattern[index]
        if char == "*":
            if pattern.startswith("**", index):
                index += 2
                if pattern.startswith("/", index):
                    out.append("(?:.*/)?")
                    index += 1
                else:
                    out.append(".*")
                continue
            out.append("[^/]*")
            index += 1
            continue
        if char == "?":
            out.append("[^/]")
            index += 1
            continue
        out.append(re.escape(char))
        index += 1
    out.append("$")
    return re.compile("".join(out))


def _glob_matches(pattern: str, path: str) -> bool:
    return _glob_regex(pattern).match(path) is not None


def matching_paths(globs: Sequence[str], paths: Sequence[str]) -> tuple[str, ...]:
    """Resolve globs against a snapshot's path list, sorted and deduplicated."""

    hits: set[str] = set()
    for pattern in globs:
        regex = _glob_regex(pattern)
        hits.update(path for path in paths if regex.match(path))
    return tuple(sorted(hits))


def _literal_prefix(pattern: str) -> str:
    """The wildcard-free head of a glob, used for path-independent checks."""

    cut = len(pattern)
    for index, char in enumerate(pattern):
        if char in "*?[":
            cut = index
            break
    head = pattern[:cut]
    return head.rsplit("/", 1)[0] if "/" in head else head


def _short(value: Any) -> str:
    """A 12-hex-character stable suffix derived from canonical content."""

    return digest(value)[7:19]


# --- value objects -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    """The immutable file listing a spec is compiled against.

    ``paths_measured`` is not decoration.  A snapshot whose listing could not be
    enumerated has *unknown* contents, and a detector that reports "no glob
    matched nothing" against an unknown listing has told a lie.  The flag lets
    the scope detector report that it did not run instead.
    """

    snapshot_sha: str
    paths: tuple[str, ...] = ()
    paths_measured: bool = True

    def __post_init__(self) -> None:
        require_str(self.snapshot_sha, "snapshot.snapshot_sha", max_length=128)
        for index, path in enumerate(self.paths):
            require_str(path, f"snapshot.paths[{index}]")
        if not self.paths_measured and self.paths:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="an unmeasured snapshot must not also carry paths",
                recommended_action="either enumerate the snapshot or declare it unmeasured",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "snapshotSha": self.snapshot_sha,
            "pathCount": len(self.paths) if self.paths_measured else None,
            "pathsMeasured": self.paths_measured,
        }


@dataclass(frozen=True, slots=True)
class AcceptanceCriterion:
    """One statement plus the reference to the check that decides it.

    ``check_ref`` is a reference, never a verdict: a test id, a policy rule id,
    a benchmark id.  A criterion whose verifier is ``UNVERIFIED`` or whose
    ``check_ref`` is empty is not a criterion, it is a wish, and the
    ``criterion-without-verifiable-check`` detector says so.
    """

    criterion_id: str
    statement: str
    verifier_type: VerifierType = VerifierType.UNVERIFIED
    check_ref: str = ""
    must: bool = True

    def __post_init__(self) -> None:
        require_identifier(self.criterion_id, "criterion.criterion_id")
        require_str(self.statement, "criterion.statement")
        if not isinstance(self.verifier_type, VerifierType):
            raise KernelError(
                code="SPEC_INVALID",
                message=f"criterion.verifier_type {self.verifier_type!r} is not a VerifierType",
                recommended_action=f"use one of {sorted(v.value for v in VerifierType)}",
            )
        if self.check_ref:
            require_str(self.check_ref, "criterion.check_ref", max_length=512)
        require_bool(self.must, "criterion.must")

    @property
    def is_verifiable(self) -> bool:
        """A criterion is verifiable only with both a real verifier and a target."""

        return self.verifier_type.is_verifiable and bool(self.check_ref)

    def to_payload(self) -> dict[str, Any]:
        return {
            "criterionId": self.criterion_id,
            "statement": self.statement,
            "verifierType": str(self.verifier_type),
            "checkRef": self.check_ref,
            "must": self.must,
            "verifiable": self.is_verifiable,
        }

    @property
    def content_digest(self) -> str:
        return digest(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, field_name: str) -> AcceptanceCriterion:
        reject_unknown_fields(
            payload,
            {"criterionId", "statement", "verifierType", "checkRef", "must", "verifiable"},
            field_name=field_name,
        )
        verifier = require_str(payload.get("verifierType", VerifierType.UNVERIFIED.value),
                               f"{field_name}.verifierType", max_length=64)
        if verifier not in {item.value for item in VerifierType}:
            raise KernelError(
                code="SPEC_INVALID",
                message=f"unknown verifier type {verifier!r}",
                recommended_action=f"use one of {sorted(v.value for v in VerifierType)}",
            )
        check_ref = payload.get("checkRef", "")
        return cls(
            criterion_id=require_identifier(payload.get("criterionId"),
                                            f"{field_name}.criterionId"),
            statement=require_str(payload.get("statement"), f"{field_name}.statement"),
            verifier_type=VerifierType(verifier),
            check_ref=require_str(check_ref, f"{field_name}.checkRef",
                                  max_length=512) if check_ref else "",
            must=require_bool(payload.get("must", True), f"{field_name}.must"),
        )


@dataclass(frozen=True, slots=True)
class Constraint:
    """A keyed restriction on how the objective may be met.

    The value is a string and never a float: constraints are compared for
    contradiction and hashed into the spec's content address, and two machines
    must agree on whether ``0.1`` equals ``0.1``.
    """

    key: str
    value: str
    source: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.key, "constraint.key")
        require_str(self.value, "constraint.value", max_length=1024)
        if self.source:
            require_str(self.source, "constraint.source", max_length=512)

    def to_payload(self) -> dict[str, Any]:
        return {"key": self.key, "value": self.value, "source": self.source}

    @property
    def content_digest(self) -> str:
        return digest(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, field_name: str) -> Constraint:
        reject_unknown_fields(payload, {"key", "value", "source"}, field_name=field_name)
        source = payload.get("source", "")
        return cls(
            key=require_identifier(payload.get("key"), f"{field_name}.key"),
            value=require_str(payload.get("value"), f"{field_name}.value", max_length=1024),
            source=require_str(source, f"{field_name}.source",
                               max_length=512) if source else "",
        )


@dataclass(frozen=True, slots=True)
class Assumption:
    """Something the compiler inferred and is willing to be wrong about in public.

    An assumption is the *safe* half of the ambiguity split: it is recorded,
    attributed to a basis, and never silently promoted into a constraint.
    """

    assumption_id: str
    statement: str
    basis: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.assumption_id, "assumption.assumption_id")
        require_str(self.statement, "assumption.statement")
        if self.basis:
            require_str(self.basis, "assumption.basis", max_length=512)

    def to_payload(self) -> dict[str, Any]:
        return {
            "assumptionId": self.assumption_id,
            "statement": self.statement,
            "basis": self.basis,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, field_name: str) -> Assumption:
        reject_unknown_fields(payload, {"assumptionId", "statement", "basis"},
                              field_name=field_name)
        basis = payload.get("basis", "")
        return cls(
            assumption_id=require_identifier(payload.get("assumptionId"),
                                             f"{field_name}.assumptionId"),
            statement=require_str(payload.get("statement"), f"{field_name}.statement"),
            basis=require_str(basis, f"{field_name}.basis", max_length=512) if basis else "",
        )


@dataclass(frozen=True, slots=True)
class OpenQuestion:
    """An ambiguity the compiler refused to resolve.

    The id is derived from the detector and the subject, not from a counter, so
    the same ambiguity keeps the same id across recompiles and a human answer
    stays attached to it.  ``blocking`` is the whole point: a blocking question
    makes the spec ``BLOCKED``, and nothing in this module can talk it down.
    """

    question_id: str
    detector_id: str
    subject: str
    question: str
    blocking: bool
    recommended_action: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.question_id, "open_question.question_id")
        require_identifier(self.detector_id, "open_question.detector_id")
        require_str(self.subject, "open_question.subject", max_length=512)
        require_str(self.question, "open_question.question", max_length=2048)
        require_bool(self.blocking, "open_question.blocking")

    def to_payload(self) -> dict[str, Any]:
        return {
            "questionId": self.question_id,
            "detectorId": self.detector_id,
            "subject": self.subject,
            "question": self.question,
            "blocking": self.blocking,
            "recommendedAction": self.recommended_action,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, field_name: str) -> OpenQuestion:
        reject_unknown_fields(
            payload,
            {"questionId", "detectorId", "subject", "question", "blocking", "recommendedAction"},
            field_name=field_name,
        )
        action = payload.get("recommendedAction", "")
        return cls(
            question_id=require_identifier(payload.get("questionId"), f"{field_name}.questionId"),
            detector_id=require_identifier(payload.get("detectorId"), f"{field_name}.detectorId"),
            subject=require_str(payload.get("subject"), f"{field_name}.subject", max_length=512),
            question=require_str(payload.get("question"), f"{field_name}.question",
                                 max_length=2048),
            blocking=require_bool(payload.get("blocking"), f"{field_name}.blocking"),
            recommended_action=require_str(action, f"{field_name}.recommendedAction",
                                           max_length=512) if action else "",
        )


@dataclass(frozen=True, slots=True)
class Detector:
    """A declared ambiguity check.

    Declaring detectors as data rather than hiding them inside a function is
    what makes the ambiguity register auditable: the output lists every detector
    with whether it ran, so "clean spec" and "detector crashed" cannot look the
    same to a reviewer.
    """

    detector_id: str
    description: str

    def __post_init__(self) -> None:
        require_identifier(self.detector_id, "detector.detector_id")
        require_str(self.description, "detector.description", max_length=512)


@dataclass(frozen=True, slots=True)
class DetectorReport:
    """What one detector did on one compilation."""

    detector_id: str
    description: str
    ran: bool
    question_ids: tuple[str, ...] = ()
    not_run_reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "detectorId": self.detector_id,
            "description": self.description,
            "ran": self.ran,
            "questionIds": list(self.question_ids),
            "findingCount": len(self.question_ids) if self.ran else None,
            "notRunReason": self.not_run_reason,
        }


#: Adjectives that promise a property without naming a threshold.  Sorted at
#: use, so the register never depends on set iteration order.
UNQUANTIFIED_ADJECTIVES: frozenset[str] = frozenset({
    "clean", "efficient", "fast", "flexible", "intuitive", "lightweight", "maintainable",
    "modern", "performant", "quick", "reliable", "responsive", "robust", "scalable",
    "seamless", "secure", "simple", "snappy", "stable", "user-friendly",
})

DETECTORS: tuple[Detector, ...] = (
    Detector("unquantified-adjective",
             "an adjective promising a property with no measurable threshold nearby"),
    Detector("scope-glob-matches-nothing",
             "a scope glob that matches no path in the repository snapshot"),
    Detector("criterion-without-verifiable-check",
             "an acceptance criterion with no verifier or no check reference"),
    Detector("contradictory-constraints",
             "two or more constraints asserting different values for one key"),
)


@dataclass(frozen=True, slots=True)
class _Draft:
    """Everything the detectors are allowed to look at."""

    intent_text: str
    scope: tuple[str, ...]
    constraints: tuple[Constraint, ...]
    acceptance_criteria: tuple[AcceptanceCriterion, ...]
    snapshot: RepositorySnapshot


def _question(detector_id: str, subject: str, question: str, *, blocking: bool,
              action: str) -> OpenQuestion:
    return OpenQuestion(
        question_id=f"oq-{detector_id}-{_short({'detector': detector_id, 'subject': subject})}",
        detector_id=detector_id,
        subject=subject,
        question=question,
        blocking=blocking,
        recommended_action=action,
    )


def _detect_unquantified_adjective(draft: _Draft) -> tuple[bool, tuple[OpenQuestion, ...]]:
    found: dict[str, str] = {}
    for sentence in _SENTENCE_SPLIT.split(draft.intent_text.lower()):
        if _MEASURABLE.search(sentence):
            # A digit in the same sentence is taken as the threshold.  This is
            # deliberately generous: the detector's job is to catch the naked
            # promise, not to grade the metric.
            continue
        for word in _WORD.findall(sentence):
            if word in UNQUANTIFIED_ADJECTIVES and word not in found:
                found[word] = sentence.strip()
    questions = tuple(
        _question(
            "unquantified-adjective",
            word,
            f"{word!r} is asserted without a measurable threshold; "
            "what number, unit and measurement method make it true?",
            blocking=True,
            action="add an acceptance criterion with a benchmark or test that fixes the number",
        )
        for word in sorted(found)
    )
    return True, questions


def _detect_scope_glob_matches_nothing(draft: _Draft) -> tuple[bool, tuple[OpenQuestion, ...]]:
    if not draft.snapshot.paths_measured:
        return False, (
            _question(
                "scope-glob-matches-nothing",
                "snapshot",
                "the repository snapshot was not enumerated, so no scope glob could be "
                "checked against it",
                blocking=True,
                action="supply an enumerated snapshot before compiling the spec",
            ),
        )
    questions = tuple(
        _question(
            "scope-glob-matches-nothing",
            pattern,
            f"scope glob {pattern!r} matches no path in snapshot "
            f"{draft.snapshot.snapshot_sha}; is the path wrong or the file not yet created?",
            blocking=True,
            action="correct the glob, or state the file as a deliverable to be created",
        )
        for pattern in sorted(set(draft.scope))
        if not any(_glob_matches(pattern, path) for path in draft.snapshot.paths)
    )
    return True, questions


def _detect_criterion_without_check(draft: _Draft) -> tuple[bool, tuple[OpenQuestion, ...]]:
    questions = tuple(
        _question(
            "criterion-without-verifiable-check",
            criterion.criterion_id,
            f"criterion {criterion.criterion_id!r} declares verifier "
            f"{str(criterion.verifier_type)!r} and check reference "
            f"{criterion.check_ref!r}; what check decides it?",
            blocking=criterion.must,
            action="name the test, benchmark, policy rule or reviewer that produces the verdict",
        )
        for criterion in sorted(draft.acceptance_criteria, key=lambda item: item.criterion_id)
        if not criterion.is_verifiable
    )
    return True, questions


def _detect_contradictory_constraints(draft: _Draft) -> tuple[bool, tuple[OpenQuestion, ...]]:
    by_key: dict[str, set[str]] = {}
    for constraint in draft.constraints:
        by_key.setdefault(constraint.key, set()).add(constraint.value)
    questions = tuple(
        _question(
            "contradictory-constraints",
            key,
            f"constraint key {key!r} is asserted with conflicting values "
            f"{sorted(values)}; which one holds?",
            blocking=True,
            action="drop or reconcile the conflicting constraint before execution",
        )
        for key, values in sorted(by_key.items())
        if len(values) > 1
    )
    return True, questions


_DETECTOR_FUNCS: dict[str, Callable[[_Draft], tuple[bool, tuple[OpenQuestion, ...]]]] = {
    "unquantified-adjective": _detect_unquantified_adjective,
    "scope-glob-matches-nothing": _detect_scope_glob_matches_nothing,
    "criterion-without-verifiable-check": _detect_criterion_without_check,
    "contradictory-constraints": _detect_contradictory_constraints,
}


def _run_detectors(draft: _Draft) -> tuple[tuple[OpenQuestion, ...], tuple[DetectorReport, ...]]:
    questions: list[OpenQuestion] = []
    reports: list[DetectorReport] = []
    for detector in DETECTORS:
        ran, found = _DETECTOR_FUNCS[detector.detector_id](draft)
        questions.extend(found)
        reports.append(DetectorReport(
            detector_id=detector.detector_id,
            description=detector.description,
            ran=ran,
            question_ids=tuple(item.question_id for item in found),
            not_run_reason="" if ran else "input required by this detector was not measured",
        ))
    return tuple(sorted(questions, key=lambda item: item.question_id)), tuple(reports)


# --- the spec ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SpecPolicy:
    """The authority envelope a spec must fit inside.

    Requirements text is untrusted.  ``forbidden_scope_globs`` is what stops an
    instruction embedded in a README from turning into a legitimate-looking
    scope entry, and the compiler raises rather than trimming the offending
    glob: a silently narrowed scope would let the caller believe it was granted.
    """

    policy_id: str
    policy_snapshot_hash: str
    forbidden_scope_globs: tuple[str, ...] = ()
    require_approval_on_widening: bool = True

    def __post_init__(self) -> None:
        require_identifier(self.policy_id, "policy.policy_id")
        require_str(self.policy_snapshot_hash, "policy.policy_snapshot_hash", max_length=128)
        for index, pattern in enumerate(self.forbidden_scope_globs):
            require_str(pattern, f"policy.forbidden_scope_globs[{index}]")
        require_bool(self.require_approval_on_widening, "policy.require_approval_on_widening")

    def to_payload(self) -> dict[str, Any]:
        return {
            "policyId": self.policy_id,
            "policySnapshotHash": self.policy_snapshot_hash,
            "forbiddenScopeGlobs": sorted(self.forbidden_scope_globs),
            "requireApprovalOnWidening": self.require_approval_on_widening,
        }


@dataclass(frozen=True, slots=True)
class StepBinding:
    """Which spec surface a workflow step depends on.

    This is the input that makes ``invalidates_steps`` a real answer instead of
    "rerun everything".  A step declares the globs it reads and the criteria it
    satisfies; the delta invalidates it only when one of those actually moved.
    """

    step_id: str
    scope_globs: tuple[str, ...] = ()
    criterion_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.step_id, "step.step_id")
        for index, pattern in enumerate(self.scope_globs):
            require_str(pattern, f"step.scope_globs[{index}]")
        for index, criterion_id in enumerate(self.criterion_ids):
            require_identifier(criterion_id, f"step.criterion_ids[{index}]")


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """A versioned, content-addressed contract for one unit of autonomous work.

    Every collection is normalised at construction — deduplicated and sorted —
    so the content address depends on what the spec *says*, not on the order a
    caller assembled it.  ``intent_digest`` stands in for the informal
    requirements text, which is untrusted and therefore never carried.
    """

    spec_id: str
    version: str
    objective: str
    scope: tuple[str, ...]
    constraints: tuple[Constraint, ...]
    acceptance_criteria: tuple[AcceptanceCriterion, ...]
    non_goals: tuple[str, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    open_questions: tuple[OpenQuestion, ...] = ()
    detectors: tuple[DetectorReport, ...] = ()
    snapshot_sha: str = ""
    intent_digest: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.spec_id, "task_spec.spec_id")
        require_str(self.version, "task_spec.version", max_length=64)
        require_str(self.objective, "task_spec.objective", max_length=4096)
        if not self.scope:
            raise KernelError(
                code="SPEC_INVALID",
                message="a task spec must declare at least one scope glob",
                recommended_action="state the paths the work may touch",
            )
        if not self.acceptance_criteria:
            raise KernelError(
                code="SPEC_INVALID",
                message="a task spec must declare at least one acceptance criterion",
                recommended_action="state at least one criterion with a verifiable check",
            )
        seen: set[str] = set()
        for criterion in self.acceptance_criteria:
            if criterion.criterion_id in seen:
                raise KernelError(
                    code="SPEC_INVALID",
                    message=f"duplicate acceptance criterion id {criterion.criterion_id!r}",
                    recommended_action="give every criterion a unique id",
                )
            seen.add(criterion.criterion_id)

    @property
    def blocking_questions(self) -> tuple[OpenQuestion, ...]:
        return tuple(item for item in self.open_questions if item.blocking)

    @property
    def status(self) -> SpecStatus:
        return SpecStatus.BLOCKED if self.blocking_questions else SpecStatus.READY

    @property
    def is_ready(self) -> bool:
        return self.status is SpecStatus.READY

    def require_ready(self) -> None:
        """Raise ``AMBIGUITY_BLOCKED`` unless every blocking question is answered.

        This is the enforcement point for the module's central rule.  It raises
        rather than returning a boolean so that a caller cannot forget to check.
        """

        blocking = self.blocking_questions
        if blocking:
            raise KernelError(
                code="AMBIGUITY_BLOCKED",
                message=(
                    f"task spec {self.spec_id}@{self.version} has "
                    f"{len(blocking)} blocking open question(s) and cannot be marked ready"
                ),
                retryable=False,
                recommended_action="answer the open questions; do not guess a resolution",
                details={"questionIds": [item.question_id for item in blocking]},
            )

    def criteria_by_id(self) -> dict[str, AcceptanceCriterion]:
        return {item.criterion_id: item for item in self.acceptance_criteria}

    def constraints_by_key(self) -> dict[str, Constraint]:
        return {item.key: item for item in self.constraints}

    def _core_payload(self) -> dict[str, Any]:
        return {
            "specId": self.spec_id,
            "version": self.version,
            "objective": self.objective,
            "snapshotSha": self.snapshot_sha,
            "intentDigest": self.intent_digest,
            "scope": list(self.scope),
            "constraints": [item.to_payload() for item in self.constraints],
            "acceptanceCriteria": [item.to_payload() for item in self.acceptance_criteria],
            "nonGoals": list(self.non_goals),
            "assumptions": [item.to_payload() for item in self.assumptions],
            "openQuestions": [item.to_payload() for item in self.open_questions],
            "detectors": [item.to_payload() for item in self.detectors],
        }

    @property
    def content_digest(self) -> str:
        """Content address over everything the spec asserts, excluding itself."""

        return digest(self._core_payload())

    def to_payload(self) -> dict[str, Any]:
        payload = self._core_payload()
        payload["contentHash"] = self.content_digest
        payload["status"] = str(self.status)
        payload["blockingQuestionCount"] = len(self.blocking_questions)
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *,
                     field_name: str = "previous_task_spec") -> TaskSpec:
        """Decode a spec strictly and prove its declared content hash.

        A prior spec arrives as data from another process.  Trusting its
        ``contentHash`` would make the delta a statement about a spec nobody
        can reproduce, so the hash is recomputed and a mismatch is
        ``STALE_BASE_SPEC`` rather than a silent acceptance.
        """

        reject_unknown_fields(
            payload,
            {"specId", "version", "objective", "snapshotSha", "intentDigest", "scope",
             "constraints", "acceptanceCriteria", "nonGoals", "assumptions", "openQuestions",
             "detectors", "contentHash", "status", "blockingQuestionCount"},
            field_name=field_name,
        )
        detectors = tuple(
            DetectorReport(
                detector_id=require_identifier(item.get("detectorId"),
                                               f"{field_name}.detectors[].detectorId"),
                description=require_str(item.get("description"),
                                        f"{field_name}.detectors[].description",
                                        max_length=512),
                ran=require_bool(item.get("ran"), f"{field_name}.detectors[].ran"),
                question_ids=require_str_seq(item.get("questionIds", ()),
                                             f"{field_name}.detectors[].questionIds"),
                not_run_reason=str(item.get("notRunReason", "")),
            )
            for item in payload.get("detectors", ()) or ()
        )
        spec = cls(
            spec_id=require_identifier(payload.get("specId"), f"{field_name}.specId"),
            version=require_str(payload.get("version"), f"{field_name}.version", max_length=64),
            objective=require_str(payload.get("objective"), f"{field_name}.objective",
                                  max_length=4096),
            scope=require_str_seq(payload.get("scope", ()), f"{field_name}.scope"),
            constraints=tuple(
                Constraint.from_payload(require_mapping(item, f"{field_name}.constraints[]"),
                                        field_name=f"{field_name}.constraints[]")
                for item in payload.get("constraints", ()) or ()
            ),
            acceptance_criteria=tuple(
                AcceptanceCriterion.from_payload(
                    require_mapping(item, f"{field_name}.acceptanceCriteria[]"),
                    field_name=f"{field_name}.acceptanceCriteria[]")
                for item in payload.get("acceptanceCriteria", ()) or ()
            ),
            non_goals=require_str_seq(payload.get("nonGoals", ()), f"{field_name}.nonGoals"),
            assumptions=tuple(
                Assumption.from_payload(require_mapping(item, f"{field_name}.assumptions[]"),
                                        field_name=f"{field_name}.assumptions[]")
                for item in payload.get("assumptions", ()) or ()
            ),
            open_questions=tuple(
                OpenQuestion.from_payload(require_mapping(item, f"{field_name}.openQuestions[]"),
                                          field_name=f"{field_name}.openQuestions[]")
                for item in payload.get("openQuestions", ()) or ()
            ),
            detectors=detectors,
            snapshot_sha=str(payload.get("snapshotSha", "")),
            intent_digest=str(payload.get("intentDigest", "")),
        )
        declared = payload.get("contentHash")
        if declared is not None and declared != spec.content_digest:
            raise KernelError(
                code="STALE_BASE_SPEC",
                message=(
                    f"{field_name} declares contentHash {declared!r} but its body hashes to "
                    f"{spec.content_digest!r}"
                ),
                retryable=False,
                recommended_action="re-fetch the base spec; do not diff against an unproven one",
            )
        return spec


def compile_task_spec(*, spec_id: str, version: str, objective: str, intent_text: str,
                      scope: Sequence[str], acceptance_criteria: Sequence[AcceptanceCriterion],
                      snapshot: RepositorySnapshot,
                      constraints: Sequence[Constraint] = (),
                      non_goals: Sequence[str] = (),
                      assumptions: Sequence[Assumption] = (),
                      policy: SpecPolicy | None = None,
                      base_snapshot_sha: str = "") -> TaskSpec:
    """Compile an informal intent plus a snapshot into a versioned TaskSpec.

    The function never invents scope, never answers a question and never drops
    an offending input: policy violations raise, ambiguities become open
    questions, and everything else is normalised into canonical order.
    ``base_snapshot_sha`` lets the caller state which snapshot the requirements
    were written against; a mismatch is ``STALE_SNAPSHOT``, because a spec
    compiled against yesterday's file listing scopes yesterday's repository.
    """

    require_identifier(spec_id, "spec_id")
    require_str(version, "version", max_length=64)
    require_str(objective, "objective", max_length=4096)
    require_str(intent_text, "intent_text", max_length=_MAX_INTENT_CHARS)
    if base_snapshot_sha and base_snapshot_sha != snapshot.snapshot_sha:
        raise KernelError(
            code="STALE_SNAPSHOT",
            message=(
                f"requirements were written against snapshot {base_snapshot_sha!r} "
                f"but compilation targets {snapshot.snapshot_sha!r}"
            ),
            retryable=False,
            recommended_action="re-derive the requirements against the current snapshot",
        )

    normalised_scope = tuple(sorted({require_str(item, "scope[]") for item in scope}))
    if policy is not None:
        _enforce_scope_policy(normalised_scope, policy, snapshot)

    draft = _Draft(
        intent_text=intent_text,
        scope=normalised_scope,
        constraints=tuple(constraints),
        acceptance_criteria=tuple(acceptance_criteria),
        snapshot=snapshot,
    )
    open_questions, detector_reports = _run_detectors(draft)

    return TaskSpec(
        spec_id=spec_id,
        version=version,
        objective=objective,
        scope=normalised_scope,
        constraints=tuple(sorted(constraints, key=lambda item: (item.key, item.value))),
        acceptance_criteria=tuple(sorted(acceptance_criteria,
                                         key=lambda item: item.criterion_id)),
        non_goals=tuple(sorted({require_str(item, "non_goals[]") for item in non_goals})),
        assumptions=tuple(sorted(assumptions, key=lambda item: item.assumption_id)),
        open_questions=open_questions,
        detectors=detector_reports,
        snapshot_sha=snapshot.snapshot_sha,
        intent_digest=digest({"intent": intent_text}),
    )


def _enforce_scope_policy(scope: Sequence[str], policy: SpecPolicy,
                          snapshot: RepositorySnapshot) -> None:
    """Reject a scope the policy profile does not allow.

    Two checks, because either alone is bypassable.  The path-independent one
    catches an escape (``/etc/**``, ``../secrets``) that resolves to nothing in
    this snapshot and would therefore look harmless; the resolved one catches a
    repository-relative glob that happens to cover a forbidden file.
    """

    for pattern in scope:
        if pattern.startswith("/") or pattern.startswith("~") or ".." in pattern.split("/"):
            raise KernelError(
                code="POLICY_CONFLICT",
                message=f"scope glob {pattern!r} escapes the repository root",
                retryable=False,
                recommended_action="declare repository-relative scope only",
                details={"policyId": policy.policy_id, "glob": pattern},
            )
        for forbidden in policy.forbidden_scope_globs:
            prefix = _literal_prefix(pattern)
            if _glob_matches(forbidden, pattern) or (prefix and _glob_matches(forbidden, prefix)):
                raise KernelError(
                    code="POLICY_CONFLICT",
                    message=(
                        f"scope glob {pattern!r} is forbidden by policy "
                        f"{policy.policy_id!r} rule {forbidden!r}"
                    ),
                    retryable=False,
                    recommended_action="remove the glob or obtain an explicit policy exception",
                    details={"policyId": policy.policy_id, "glob": pattern, "rule": forbidden},
                )
    if not snapshot.paths_measured:
        return
    forbidden_paths = set(matching_paths(policy.forbidden_scope_globs, snapshot.paths))
    if not forbidden_paths:
        return
    overlap = sorted(forbidden_paths.intersection(matching_paths(scope, snapshot.paths)))
    if overlap:
        raise KernelError(
            code="POLICY_CONFLICT",
            message=(
                f"scope resolves onto {len(overlap)} path(s) forbidden by policy "
                f"{policy.policy_id!r}"
            ),
            retryable=False,
            recommended_action="narrow the scope or obtain an explicit policy exception",
            details={"policyId": policy.policy_id, "paths": overlap[:32]},
        )


# --- the delta ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Change:
    """One difference between two specs, with its direction of risk."""

    kind: ChangeKind
    target: str
    risk: RiskDirection = RiskDirection.NEUTRAL
    before_digest: str = ""
    after_digest: str = ""
    detail: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": str(self.kind),
            "target": self.target,
            "risk": str(self.risk),
            "beforeDigest": self.before_digest,
            "afterDigest": self.after_digest,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class StepInvalidation:
    """Why one step must run again."""

    step_id: str
    reasons: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {"stepId": self.step_id, "reasons": list(self.reasons)}


@dataclass(frozen=True, slots=True)
class SpecDelta:
    """The minimal difference between two specs, plus its execution impact.

    Minimal means what it says: a criterion, constraint or non-goal that did not
    change has no entry here.  The orchestrator reruns exactly what
    ``invalidates_steps`` names, so a spurious entry is not a cosmetic defect —
    it is unnecessary work charged to a real budget.
    """

    from_version: str
    to_version: str
    changes: tuple[Change, ...]
    added_criteria: tuple[str, ...]
    removed_criteria: tuple[str, ...]
    changed_criteria: tuple[str, ...]
    scope_paths_entered: tuple[str, ...]
    scope_paths_left: tuple[str, ...]
    invalidates_steps: tuple[str, ...]
    step_invalidations: tuple[StepInvalidation, ...]
    risk_direction: RiskDirection
    requires_approval: bool
    from_digest: str = ""
    to_digest: str = ""

    @property
    def is_scope_widening(self) -> bool:
        return bool(self.scope_paths_entered)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "fromVersion": self.from_version,
            "toVersion": self.to_version,
            "fromDigest": self.from_digest,
            "toDigest": self.to_digest,
            "changes": [item.to_payload() for item in self.changes],
            "addedCriteria": list(self.added_criteria),
            "removedCriteria": list(self.removed_criteria),
            "changedCriteria": list(self.changed_criteria),
            "scopePathsEntered": list(self.scope_paths_entered),
            "scopePathsLeft": list(self.scope_paths_left),
            "invalidatesSteps": list(self.invalidates_steps),
            "stepInvalidations": [item.to_payload() for item in self.step_invalidations],
            "riskDirection": str(self.risk_direction),
            "scopeWidened": self.is_scope_widening,
            "requiresApproval": self.requires_approval,
        }
        payload["deltaDigest"] = digest(payload)
        return payload

    @property
    def delta_digest(self) -> str:
        return self.to_payload()["deltaDigest"]


def compile_delta(before: TaskSpec, after: TaskSpec, *,
                  snapshot: RepositorySnapshot,
                  steps: Sequence[StepBinding] = ()) -> SpecDelta:
    """Compile the minimal difference between two specs and what it invalidates.

    Scope movement is judged on *resolved paths*, not on glob strings.  Two
    different globs can cover the same files, and rewriting ``src/*.py`` as
    ``src/**/*.py`` in a flat directory changes nothing that any step could
    observe; treating that as a widening would invalidate the whole run for a
    cosmetic edit.  Conversely a glob that reads identically can cover new files
    after a snapshot changes, which is a real widening and is flagged as
    risk-increasing.
    """

    if before.spec_id != after.spec_id:
        raise KernelError(
            code="SPEC_INVALID",
            message=(
                f"cannot diff spec {before.spec_id!r} against {after.spec_id!r}; "
                "a delta is only defined within one spec identity"
            ),
            recommended_action="diff two versions of the same spec",
        )
    if before.version == after.version and before.content_digest != after.content_digest:
        raise KernelError(
            code="SPEC_INVALID",
            message=(
                f"spec {after.spec_id!r} changed content without bumping version "
                f"{after.version!r}"
            ),
            retryable=False,
            recommended_action="bump the spec version; a version must address one content",
        )
    if not snapshot.paths_measured:
        raise KernelError(
            code="DELTA_IMPACT_UNCOMPUTABLE",
            message=(
                "scope impact cannot be computed against an unenumerated snapshot; "
                "reporting an empty impact would understate the rerun set"
            ),
            retryable=True,
            recommended_action="enumerate the snapshot, then recompute the delta",
        )

    changes: list[Change] = []

    if before.objective != after.objective:
        changes.append(Change(
            kind=ChangeKind.OBJECTIVE_CHANGED,
            target=after.spec_id,
            risk=RiskDirection.INCREASES,
            before_digest=digest(before.objective),
            after_digest=digest(after.objective),
            detail="the objective statement changed",
        ))

    before_criteria = before.criteria_by_id()
    after_criteria = after.criteria_by_id()
    added = tuple(sorted(set(after_criteria) - set(before_criteria)))
    removed = tuple(sorted(set(before_criteria) - set(after_criteria)))
    changed = tuple(sorted(
        key for key in set(before_criteria) & set(after_criteria)
        if before_criteria[key].content_digest != after_criteria[key].content_digest
    ))
    for criterion_id in added:
        changes.append(Change(
            kind=ChangeKind.CRITERION_ADDED, target=criterion_id,
            risk=RiskDirection.INCREASES,
            after_digest=after_criteria[criterion_id].content_digest,
            detail="a new criterion must be satisfied",
        ))
    for criterion_id in removed:
        changes.append(Change(
            kind=ChangeKind.CRITERION_REMOVED, target=criterion_id,
            risk=RiskDirection.INCREASES,
            before_digest=before_criteria[criterion_id].content_digest,
            detail="a criterion that previously gated the work no longer does",
        ))
    for criterion_id in changed:
        changes.append(Change(
            kind=ChangeKind.CRITERION_CHANGED, target=criterion_id,
            risk=RiskDirection.INCREASES,
            before_digest=before_criteria[criterion_id].content_digest,
            after_digest=after_criteria[criterion_id].content_digest,
            detail="the criterion's statement, verifier or check reference moved",
        ))

    before_constraints = before.constraints_by_key()
    after_constraints = after.constraints_by_key()
    for key in sorted(set(after_constraints) - set(before_constraints)):
        changes.append(Change(
            kind=ChangeKind.CONSTRAINT_ADDED, target=key, risk=RiskDirection.DECREASES,
            after_digest=after_constraints[key].content_digest,
            detail="a new restriction narrows what is permitted",
        ))
    for key in sorted(set(before_constraints) - set(after_constraints)):
        changes.append(Change(
            kind=ChangeKind.CONSTRAINT_REMOVED, target=key, risk=RiskDirection.INCREASES,
            before_digest=before_constraints[key].content_digest,
            detail="a restriction was lifted",
        ))
    for key in sorted(set(before_constraints) & set(after_constraints)):
        if before_constraints[key].content_digest != after_constraints[key].content_digest:
            changes.append(Change(
                kind=ChangeKind.CONSTRAINT_CHANGED, target=key, risk=RiskDirection.INCREASES,
                before_digest=before_constraints[key].content_digest,
                after_digest=after_constraints[key].content_digest,
                detail="the constraint's value moved",
            ))

    for goal in sorted(set(after.non_goals) - set(before.non_goals)):
        changes.append(Change(kind=ChangeKind.NON_GOAL_ADDED, target=goal,
                              risk=RiskDirection.DECREASES,
                              detail="something was explicitly placed out of scope"))
    for goal in sorted(set(before.non_goals) - set(after.non_goals)):
        changes.append(Change(kind=ChangeKind.NON_GOAL_REMOVED, target=goal,
                              risk=RiskDirection.INCREASES,
                              detail="a previous non-goal is no longer excluded"))

    before_paths = set(matching_paths(before.scope, snapshot.paths))
    after_paths = set(matching_paths(after.scope, snapshot.paths))
    entered = tuple(sorted(after_paths - before_paths))
    left = tuple(sorted(before_paths - after_paths))
    if entered:
        changes.append(Change(
            kind=ChangeKind.SCOPE_WIDENED, target=after.spec_id,
            risk=RiskDirection.INCREASES,
            after_digest=digest(list(entered)),
            detail=f"{len(entered)} path(s) entered scope",
        ))
    if left:
        changes.append(Change(
            kind=ChangeKind.SCOPE_NARROWED, target=after.spec_id,
            risk=RiskDirection.DECREASES,
            before_digest=digest(list(left)),
            detail=f"{len(left)} path(s) left scope",
        ))

    moved_paths = set(entered) | set(left)
    moved_criteria = set(added) | set(removed) | set(changed)
    invalidations: list[StepInvalidation] = []
    for step in sorted(steps, key=lambda item: item.step_id):
        reasons: list[str] = []
        touched_criteria = sorted(set(step.criterion_ids) & moved_criteria)
        if touched_criteria:
            reasons.append(f"criteria moved: {','.join(touched_criteria)}")
        step_paths = set(matching_paths(step.scope_globs, snapshot.paths))
        touched_paths = sorted(step_paths & moved_paths)
        if touched_paths:
            reasons.append(f"scope paths moved: {len(touched_paths)}")
        if reasons:
            invalidations.append(StepInvalidation(step_id=step.step_id,
                                                  reasons=tuple(reasons)))

    ordered_changes = tuple(sorted(changes, key=lambda item: (str(item.kind), item.target)))
    risk = RiskDirection.NEUTRAL
    if any(item.risk is RiskDirection.INCREASES for item in ordered_changes):
        risk = RiskDirection.INCREASES
    elif any(item.risk is RiskDirection.DECREASES for item in ordered_changes):
        risk = RiskDirection.DECREASES

    return SpecDelta(
        from_version=before.version,
        to_version=after.version,
        changes=ordered_changes,
        added_criteria=added,
        removed_criteria=removed,
        changed_criteria=changed,
        scope_paths_entered=entered,
        scope_paths_left=left,
        invalidates_steps=tuple(item.step_id for item in invalidations),
        step_invalidations=tuple(invalidations),
        risk_direction=risk,
        requires_approval=risk is RiskDirection.INCREASES or bool(after.blocking_questions),
        from_digest=before.content_digest,
        to_digest=after.content_digest,
    )


# --- registry entry point ----------------------------------------------------

_REQUEST_FIELDS = {
    "requirements", "repository_snapshot", "previous_task_spec", "policy_profile",
    "require_ready",
}
_REQUIREMENTS_FIELDS = {
    "specId", "version", "objective", "intent", "scope", "constraints",
    "acceptanceCriteria", "nonGoals", "assumptions", "baseSnapshotSha",
}
_SNAPSHOT_FIELDS = {"snapshotSha", "paths", "pathsMeasured"}
_POLICY_FIELDS = {
    "policyId", "policySnapshotHash", "forbiddenScopeGlobs", "requireApprovalOnWidening", "steps",
}
_STEP_FIELDS = {"stepId", "scopeGlobs", "criterionIds"}


def _decode_snapshot(payload: Mapping[str, Any]) -> RepositorySnapshot:
    reject_unknown_fields(payload, _SNAPSHOT_FIELDS, field_name="repository_snapshot")
    measured = require_bool(payload.get("pathsMeasured", True),
                            "repository_snapshot.pathsMeasured")
    return RepositorySnapshot(
        snapshot_sha=require_str(payload.get("snapshotSha"), "repository_snapshot.snapshotSha",
                                 max_length=128),
        paths=require_str_seq(payload.get("paths", ()), "repository_snapshot.paths",
                              max_items=1 << 16) if measured else (),
        paths_measured=measured,
    )


def _decode_policy(payload: Mapping[str, Any]) -> tuple[SpecPolicy, tuple[StepBinding, ...]]:
    reject_unknown_fields(payload, _POLICY_FIELDS, field_name="policy_profile")
    decoded: list[StepBinding] = []
    for raw in payload.get("steps", ()) or ():
        item = require_mapping(raw, "policy_profile.steps[]")
        reject_unknown_fields(item, _STEP_FIELDS, field_name="policy_profile.steps[]")
        decoded.append(StepBinding(
            step_id=require_identifier(item.get("stepId"), "policy_profile.steps[].stepId"),
            scope_globs=require_str_seq(item.get("scopeGlobs", ()),
                                        "policy_profile.steps[].scopeGlobs"),
            criterion_ids=require_str_seq(item.get("criterionIds", ()),
                                          "policy_profile.steps[].criterionIds"),
        ))
    steps = tuple(decoded)
    policy = SpecPolicy(
        policy_id=require_identifier(payload.get("policyId"), "policy_profile.policyId"),
        policy_snapshot_hash=require_str(payload.get("policySnapshotHash"),
                                         "policy_profile.policySnapshotHash", max_length=128),
        forbidden_scope_globs=require_str_seq(payload.get("forbiddenScopeGlobs", ()),
                                              "policy_profile.forbiddenScopeGlobs"),
        require_approval_on_widening=require_bool(
            payload.get("requireApprovalOnWidening", True),
            "policy_profile.requireApprovalOnWidening"),
    )
    return policy, steps


@register("task-spec-delta-compiler")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point for ``task-spec-delta-compiler``.

    ``require_ready`` exists for the same reason the census has
    ``failOnPartial``: an authoring tool wants the blocked spec so it can show
    the questions, while a step that is about to execute wants a raise.  Neither
    may receive the other's answer by accident, so the choice is an input.  With
    it unset the compilation still succeeds and the ``no-open-critical-ambiguity``
    gate reports ``false`` — a blocked spec is a real, useful output, it is just
    not an executable one.
    """

    payload = require_mapping(request, "request")
    reject_unknown_fields(payload, _REQUEST_FIELDS, field_name="task-spec-delta-compiler request")

    requirements = payload.get("requirements")
    if requirements is None:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="task-spec-delta-compiler requires 'requirements'",
            recommended_action="supply the requirements object",
        )
    requirements = require_mapping(requirements, "requirements")
    reject_unknown_fields(requirements, _REQUIREMENTS_FIELDS, field_name="requirements")

    snapshot_payload = payload.get("repository_snapshot")
    if snapshot_payload is None:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="task-spec-delta-compiler requires 'repository_snapshot'",
            recommended_action="supply the snapshot the spec is compiled against",
        )
    snapshot = _decode_snapshot(require_mapping(snapshot_payload, "repository_snapshot"))

    policy: SpecPolicy | None = None
    steps: tuple[StepBinding, ...] = ()
    policy_payload = payload.get("policy_profile")
    if policy_payload is not None:
        policy, steps = _decode_policy(require_mapping(policy_payload, "policy_profile"))

    criteria = tuple(
        AcceptanceCriterion.from_payload(
            require_mapping(item, "requirements.acceptanceCriteria[]"),
            field_name="requirements.acceptanceCriteria[]")
        for item in requirements.get("acceptanceCriteria", ()) or ()
    )
    constraints = tuple(
        Constraint.from_payload(require_mapping(item, "requirements.constraints[]"),
                                field_name="requirements.constraints[]")
        for item in requirements.get("constraints", ()) or ()
    )
    assumptions = tuple(
        Assumption.from_payload(require_mapping(item, "requirements.assumptions[]"),
                                field_name="requirements.assumptions[]")
        for item in requirements.get("assumptions", ()) or ()
    )
    base_snapshot_sha = requirements.get("baseSnapshotSha", "")

    spec = compile_task_spec(
        spec_id=require_identifier(requirements.get("specId"), "requirements.specId"),
        version=require_str(requirements.get("version"), "requirements.version", max_length=64),
        objective=require_str(requirements.get("objective"), "requirements.objective",
                              max_length=4096),
        intent_text=require_str(requirements.get("intent"), "requirements.intent",
                                max_length=_MAX_INTENT_CHARS),
        scope=require_str_seq(requirements.get("scope", ()), "requirements.scope",
                              allow_empty=False),
        acceptance_criteria=criteria,
        snapshot=snapshot,
        constraints=constraints,
        non_goals=require_str_seq(requirements.get("nonGoals", ()), "requirements.nonGoals"),
        assumptions=assumptions,
        policy=policy,
        base_snapshot_sha=require_str(base_snapshot_sha, "requirements.baseSnapshotSha",
                                      max_length=128) if base_snapshot_sha else "",
    )

    if require_bool(payload.get("require_ready", False), "require_ready"):
        spec.require_ready()

    previous_payload = payload.get("previous_task_spec")
    if previous_payload is None:
        delta_payload: dict[str, Any] = {
            "computed": False,
            "reason": "no previous task spec was supplied; there is no baseline to diff",
        }
        affected = {
            "computed": True,
            "basis": "initial-spec",
            "steps": sorted(item.step_id for item in steps),
            "scopePathsEntered": list(matching_paths(spec.scope, snapshot.paths)),
            "scopePathsLeft": [],
            "criteria": [item.criterion_id for item in spec.acceptance_criteria],
        }
        delta_computed = False
    else:
        previous = TaskSpec.from_payload(require_mapping(previous_payload, "previous_task_spec"))
        delta = compile_delta(previous, spec, snapshot=snapshot, steps=steps)
        delta_payload = {"computed": True, **delta.to_payload()}
        affected = {
            "computed": True,
            "basis": "spec-delta",
            "steps": list(delta.invalidates_steps),
            "scopePathsEntered": list(delta.scope_paths_entered),
            "scopePathsLeft": list(delta.scope_paths_left),
            "criteria": sorted(set(delta.added_criteria) | set(delta.removed_criteria)
                               | set(delta.changed_criteria)),
        }
        delta_computed = True

    ambiguity_register = {
        "detectors": [item.to_payload() for item in spec.detectors],
        "openQuestions": [item.to_payload() for item in spec.open_questions],
        "openQuestionCount": len(spec.open_questions),
        "blockingQuestionCount": len(spec.blocking_questions),
        "status": str(spec.status),
    }
    acceptance_criteria = {
        "criteria": [item.to_payload() for item in spec.acceptance_criteria],
        "traceability": [
            {
                "criterionId": item.criterion_id,
                "verifierType": str(item.verifier_type),
                "checkRef": item.check_ref,
                "must": item.must,
                "traced": item.is_verifiable,
            }
            for item in spec.acceptance_criteria
        ],
        "untracedCriterionIds": [item.criterion_id for item in spec.acceptance_criteria
                                 if not item.is_verifiable],
    }
    gates = {
        "schema-valid": True,
        "no-open-critical-ambiguity": not spec.blocking_questions,
        "traceability-complete": not acceptance_criteria["untracedCriterionIds"],
        "delta-impact-computed": delta_computed or previous_payload is None,
    }
    return {
        "task_spec": spec.to_payload(),
        "spec_delta": delta_payload,
        "acceptance_criteria": acceptance_criteria,
        "ambiguity_register": ambiguity_register,
        "affected_node_set": affected,
        "specDigest": spec.content_digest,
        "policyProfile": policy.to_payload() if policy is not None else None,
        "snapshot": snapshot.to_payload(),
        "gates": gates,
    }
