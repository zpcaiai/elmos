"""Agent arena: head-to-head evaluation that a contestant cannot game from the inside.

Two things make an arena worthless, and both are structural rather than
statistical.  The first is leakage: if the thing being measured can see the
grader's reference solution or the hidden checks, every score afterwards is a
measurement of retrieval, not of capability.  That is why the task is split
into a :class:`TaskView` — literally the only object a contestant is ever
handed — and a :class:`TaskSecret`.  The view has no field that could carry a
reference or a hidden check, so "the contestant saw the answer" is not a bug
that can be introduced by a careless caller; it is a shape that does not exist.
:class:`ArenaTask` additionally scans the view for verbatim fragments of the
secret at construction, because a leak can also be pasted into a task
*statement* by hand.

The second is silent exclusion.  Anti-cheat detectors here are deliberately
crude and deliberately explainable — an output too close to the reference for
the task's difficulty, a solution that hard-codes the visible test inputs, a
read outside the declared scope, a wall clock too short for the work claimed —
and every one of them reports the observation it fired on rather than a score.
A flagged match is *quarantined*, never deleted: the leaderboard carries the
exclusions with their detector ids and reasons, because a benchmark that
quietly drops the matches it distrusts publishes a number nobody can audit and
hides the cheating it just detected.

Scoring is a pure function of recorded artefacts: the same submissions replay
to the same digest, and a submission whose checks were never recorded scores
*unmeasured*, never zero — an interrupted contestant did not earn nothing, it
was never asked.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields
from enum import StrEnum
from typing import Any

from .contracts import (
    canonical_json,
    digest,
    reject_unknown_fields,
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
    "AntiCheatReport",
    "ArenaTask",
    "CheckOutcome",
    "Contestant",
    "Detection",
    "DETECTORS",
    "Difficulty",
    "EvaluationProtocol",
    "HiddenCheck",
    "Leaderboard",
    "LeaderboardEntry",
    "MatchResult",
    "QuarantineReason",
    "SIMILARITY_CEILING_PERCENT",
    "Score",
    "Submission",
    "SubmissionOutcome",
    "TaskSecret",
    "TaskView",
    "build_leaderboard",
    "detect_cheating",
    "handle",
    "judge_match",
    "pairwise_confidence",
    "quality_cost_frontier",
    "record_arena_match",
    "score_submission",
    "similarity_percent",
]

register_codes(
    Category.VERIFICATION,
    "ARENA_ENV_DRIFT",
    "UNFAIR_COMPARISON",
    "INSUFFICIENT_RUNS",
    "ARENA_MATCH_QUARANTINED",
)
register_codes(
    Category.INTEGRITY,
    "BENCHMARK_LEAKAGE",
)

#: Shingle width used by :func:`similarity_percent`.  Three tokens is wide
#: enough that shared keywords ("def", "return", "self") do not manufacture a
#: match, and narrow enough that a reordered copy still registers.
_SHINGLE = 3

#: The shortest secret fragment worth searching for inside a task view.  Below
#: this length a "match" is a common English word, and a leak detector that
#: fires on the word "return" gets switched off within a week.
_MIN_LEAK_FRAGMENT = 12

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class Difficulty(StrEnum):
    """How much room the task leaves for two correct answers to differ.

    This is the term that makes the reference-similarity detector meaningful.
    On a trivial task every correct solution looks like every other one, so a
    high similarity is evidence of nothing; on a hard task it is evidence of a
    leak.  One global similarity threshold would either accuse everyone who
    solved the easy task or catch nobody on the hard one.
    """

    TRIVIAL = "trivial"
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


#: Per-difficulty similarity ceiling, in whole percent.  ``TRIVIAL`` is 100:
#: the detector is explicitly disabled rather than set to an unreachable
#: number, so that reading the table tells you it never fires there.
SIMILARITY_CEILING_PERCENT: Mapping[Difficulty, int] = {
    Difficulty.TRIVIAL: 100,
    Difficulty.EASY: 95,
    Difficulty.MEDIUM: 85,
    Difficulty.HARD: 70,
}


class SubmissionOutcome(StrEnum):
    """How a contestant's attempt ended.

    The four values are kept apart for the same reason the kernel keeps
    ``Status`` apart: a ``PARTIAL`` attempt produced real work and real
    failure, and an ``INTERRUPTED`` one produced no verdict at all.  Folding
    either into ``FAILED`` would let an arena report a contestant as beaten
    when it was actually cut off.
    """

    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    INTERRUPTED = "INTERRUPTED"
    FAILED = "FAILED"


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(match.group(0).lower() for match in _TOKEN_RE.finditer(text))


def _shingles(text: str, width: int = _SHINGLE) -> frozenset[str]:
    tokens = _tokens(text)
    if len(tokens) < width:
        return frozenset({" ".join(tokens)}) if tokens else frozenset()
    return frozenset(
        " ".join(tokens[index:index + width])
        for index in range(len(tokens) - width + 1)
    )


def similarity_percent(left: str, right: str) -> int:
    """Jaccard overlap of token shingles, in whole percent.

    Integer arithmetic on purpose: a similarity that is compared against a
    threshold, recorded in an anti-cheat report and hashed into a match digest
    must not be a float, or two machines can disagree about whether a
    contestant cheated.
    """

    a = _shingles(left)
    b = _shingles(right)
    if not a and not b:
        return 100
    union = a | b
    if not union:
        return 0
    return 100 * len(a & b) // len(union)


@dataclass(frozen=True, slots=True)
class HiddenCheck:
    """One graded assertion the contestant never sees.

    ``points`` is an integer because the total is compared, ranked and hashed;
    a fractional weight would be a float in the digest.
    """

    check_id: str
    expression: str
    points: int

    def __post_init__(self) -> None:
        require_identifier(self.check_id, "hidden_check.check_id")
        require_str(self.expression, "hidden_check.expression")
        require_int(self.points, "hidden_check.points", minimum=1)


@dataclass(frozen=True, slots=True)
class TaskView:
    """Everything a contestant is allowed to see — and nothing else.

    The isolation guarantee in this module is the *field set* of this class.
    There is no ``reference_solution`` field, no ``hidden_checks`` field and no
    free-form ``extra`` mapping that one could be smuggled through, so a caller
    cannot hand a contestant the answer by filling in the wrong argument.  Tests
    assert the field set directly, which is the only assertion that keeps being
    true after someone adds a field in two years.
    """

    task_id: str
    task_class: str
    difficulty: Difficulty
    statement: str
    visible_test_inputs: tuple[str, ...]
    declared_scope: tuple[str, ...]
    repo_snapshot_sha: str
    budget_micros: int
    max_wall_clock_ms: int

    def __post_init__(self) -> None:
        require_identifier(self.task_id, "task.task_id")
        require_identifier(self.task_class, "task.task_class")
        if not isinstance(self.difficulty, Difficulty):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown difficulty {self.difficulty!r}",
                recommended_action=f"use one of {sorted(d.value for d in Difficulty)}",
            )
        require_str(self.statement, "task.statement")
        require_str(self.repo_snapshot_sha, "task.repo_snapshot_sha", max_length=128)
        require_int(self.budget_micros, "task.budget_micros", minimum=1)
        require_int(self.max_wall_clock_ms, "task.max_wall_clock_ms", minimum=1)
        if not self.declared_scope:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"task {self.task_id!r} declares no scope",
                recommended_action="declare the paths the contestant may read; empty is a deny",
            )

    @property
    def similarity_ceiling_percent(self) -> int:
        return SIMILARITY_CEILING_PERCENT[self.difficulty]

    def to_payload(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "taskClass": self.task_class,
            "difficulty": str(self.difficulty),
            "statement": self.statement,
            "visibleTestInputs": list(self.visible_test_inputs),
            "declaredScope": list(self.declared_scope),
            "repoSnapshotSha": self.repo_snapshot_sha,
            "budgetMicros": self.budget_micros,
            "maxWallClockMs": self.max_wall_clock_ms,
        }


@dataclass(frozen=True, slots=True)
class TaskSecret:
    """The grader's half: the reference solution and the hidden checks.

    Nothing in this class is ever rendered into an output payload, an error
    message or an anti-cheat explanation.  The reference-similarity detector
    reports a *percentage* and the ceiling it exceeded, never the text it
    matched, because an explanation that quotes the reference leaks it to
    whoever reads the report.
    """

    task_id: str
    reference_solution: str
    hidden_checks: tuple[HiddenCheck, ...]
    min_plausible_wall_clock_ms: int

    def __post_init__(self) -> None:
        require_identifier(self.task_id, "secret.task_id")
        require_str(self.reference_solution, "secret.reference_solution")
        require_int(self.min_plausible_wall_clock_ms, "secret.min_plausible_wall_clock_ms",
                    minimum=1)
        if not self.hidden_checks:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"task {self.task_id!r} has no hidden check; nothing would be graded",
                recommended_action="declare at least one hidden check",
            )
        seen: set[str] = set()
        for check in self.hidden_checks:
            if check.check_id in seen:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"duplicate hidden check {check.check_id!r}",
                    recommended_action="give each hidden check a unique id",
                )
            seen.add(check.check_id)

    @property
    def check_ids(self) -> tuple[str, ...]:
        return tuple(check.check_id for check in self.hidden_checks)

    @property
    def max_points(self) -> int:
        return sum(check.points for check in self.hidden_checks)

    def points_for(self, check_id: str) -> int:
        for check in self.hidden_checks:
            if check.check_id == check_id:
                return check.points
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"check {check_id!r} is not part of task {self.task_id!r}",
            recommended_action="grade against the task's own check set",
        )

    def public_summary(self) -> dict[str, Any]:
        """The only shape of this object that may leave the module."""

        return {
            "taskId": self.task_id,
            "hiddenCheckCount": len(self.hidden_checks),
            "maxPoints": self.max_points,
            "minPlausibleWallClockMs": self.min_plausible_wall_clock_ms,
        }


def _leak_fragments(secret: TaskSecret) -> tuple[str, ...]:
    fragments = [
        line.strip() for line in secret.reference_solution.splitlines()
        if len(line.strip()) >= _MIN_LEAK_FRAGMENT
    ]
    fragments.extend(
        check.expression.strip() for check in secret.hidden_checks
        if len(check.expression.strip()) >= _MIN_LEAK_FRAGMENT
    )
    return tuple(sorted(set(fragments)))


@dataclass(frozen=True, slots=True)
class ArenaTask:
    """A view/secret pair, checked at construction for a pasted-in leak.

    The field-level split already makes it impossible to *pass* the reference
    to a contestant.  This class closes the other door: a task author who
    pastes the reference into the statement, or a hidden check expression into
    the visible test inputs, gets ``BENCHMARK_LEAKAGE`` at construction rather
    than a leaderboard nobody can trust.
    """

    view: TaskView
    secret: TaskSecret

    def __post_init__(self) -> None:
        if self.view.task_id != self.secret.task_id:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=(
                    f"task view {self.view.task_id!r} is paired with secret "
                    f"{self.secret.task_id!r}"
                ),
                recommended_action="pair a view with the secret of the same task",
            )
        rendered = canonical_json(self.view.to_payload())
        for fragment in _leak_fragments(self.secret):
            if fragment in rendered:
                raise KernelError(
                    code="BENCHMARK_LEAKAGE",
                    message=(
                        f"task {self.view.task_id!r} exposes a {len(fragment)}-character "
                        "fragment of the grader's secret in the contestant-visible view"
                    ),
                    retryable=False,
                    recommended_action=(
                        "remove the reference solution and hidden check text from the "
                        "statement and the visible test inputs"
                    ),
                    details={"taskId": self.view.task_id, "fragmentLength": len(fragment)},
                )

    def to_contestant_payload(self) -> dict[str, Any]:
        """What is handed to a contestant.  Deliberately just the view."""

        return self.view.to_payload()


@dataclass(frozen=True, slots=True)
class Contestant:
    """An entrant, with the resources it was actually given.

    ``family`` groups entrants that share a model, prompt or toolchain.  It is
    not used to exclude anyone here — it travels into the ELO book so that a
    leaderboard cannot present five variants of one system as five independent
    data points.
    """

    contestant_id: str
    family: str
    permission_profile_id: str
    allowed_tools: tuple[str, ...]
    budget_micros: int
    max_wall_clock_ms: int

    def __post_init__(self) -> None:
        require_identifier(self.contestant_id, "contestant.contestant_id")
        require_identifier(self.family, "contestant.family")
        require_identifier(self.permission_profile_id, "contestant.permission_profile_id")
        require_int(self.budget_micros, "contestant.budget_micros", minimum=1)
        require_int(self.max_wall_clock_ms, "contestant.max_wall_clock_ms", minimum=1)
        if not self.allowed_tools:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"contestant {self.contestant_id!r} has an empty tool grant",
                recommended_action="an empty grant is a deny; declare the tools explicitly",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "contestantId": self.contestant_id,
            "family": self.family,
            "permissionProfileId": self.permission_profile_id,
            "allowedTools": list(self.allowed_tools),
            "budgetMicros": self.budget_micros,
            "maxWallClockMs": self.max_wall_clock_ms,
        }


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """One recorded hidden-check result.  Recorded, not inferred."""

    check_id: str
    passed: bool

    def __post_init__(self) -> None:
        require_identifier(self.check_id, "check_outcome.check_id")
        if not isinstance(self.passed, bool):
            raise KernelError(
                code="MALFORMED_INPUT",
                message="check_outcome.passed must be a boolean",
                recommended_action="record the check result as true or false",
            )

    def to_payload(self) -> dict[str, Any]:
        return {"checkId": self.check_id, "passed": self.passed}


@dataclass(frozen=True, slots=True)
class Submission:
    """One contestant's recorded attempt at one task.

    ``check_results is None`` means the checks were never run — an interrupted
    or crashed attempt.  It is not the same as every check failing, so the
    score it produces is *unmeasured* rather than zero.  Conflating the two is
    how an arena reports a contestant that was killed by an infrastructure
    fault as one that could not do the work.
    """

    contestant_id: str
    task_id: str
    run_id: str
    outcome: SubmissionOutcome
    solution_text: str
    read_paths: tuple[str, ...]
    tools_used: tuple[str, ...]
    wall_clock_ms: int
    cost_micros: int
    repo_snapshot_sha: str
    environment_fingerprint: str
    check_results: tuple[CheckOutcome, ...] | None = None
    manual_interventions: int = 0
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.contestant_id, "submission.contestant_id")
        require_identifier(self.task_id, "submission.task_id")
        require_identifier(self.run_id, "submission.run_id")
        if not isinstance(self.outcome, SubmissionOutcome):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown submission outcome {self.outcome!r}",
                recommended_action=f"use one of {sorted(o.value for o in SubmissionOutcome)}",
            )
        require_str(self.solution_text, "submission.solution_text", max_length=1 << 18)
        require_int(self.wall_clock_ms, "submission.wall_clock_ms", minimum=0)
        require_int(self.cost_micros, "submission.cost_micros", minimum=0)
        require_int(self.manual_interventions, "submission.manual_interventions", minimum=0)
        require_str(self.repo_snapshot_sha, "submission.repo_snapshot_sha", max_length=128)
        require_str(self.environment_fingerprint, "submission.environment_fingerprint",
                    max_length=128)
        if self.outcome is SubmissionOutcome.SUCCEEDED and self.check_results is None:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=(
                    f"submission {self.run_id!r} claims SUCCEEDED but recorded no check "
                    "results; a success with nothing graded is not a success"
                ),
                recommended_action="record the hidden check outcomes or lower the outcome",
            )

    @property
    def score_is_measurable(self) -> bool:
        return self.check_results is not None

    def to_payload(self) -> dict[str, Any]:
        return {
            "contestantId": self.contestant_id,
            "taskId": self.task_id,
            "runId": self.run_id,
            "outcome": str(self.outcome),
            "readPaths": list(self.read_paths),
            "toolsUsed": list(self.tools_used),
            "wallClockMs": self.wall_clock_ms,
            "costMicros": self.cost_micros,
            "repoSnapshotSha": self.repo_snapshot_sha,
            "environmentFingerprint": self.environment_fingerprint,
            "checkResults": (
                None if self.check_results is None
                else [item.to_payload() for item in self.check_results]
            ),
            "manualInterventions": self.manual_interventions,
            "solutionDigest": digest(self.solution_text),
            "evidenceIds": list(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class Score:
    """A graded submission, or an honest statement that it was never graded."""

    contestant_id: str
    task_id: str
    measured: bool
    points: int | None
    max_points: int
    checks_passed: int | None
    checks_total: int
    reason: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "contestantId": self.contestant_id,
            "taskId": self.task_id,
            "measured": self.measured,
            "points": self.points,
            "maxPoints": self.max_points,
            "checksPassed": self.checks_passed,
            "checksTotal": self.checks_total,
            "reason": self.reason,
        }


def score_submission(submission: Submission, task: ArenaTask) -> Score:
    """Grade a recorded submission against the task's hidden checks.

    Pure and replayable: the same recorded artefacts produce the same score on
    any machine, because nothing here consults a clock, a model or the network.
    A submission graded against a check set that is not the task's own is
    rejected rather than partially counted — a partially-graded score compared
    against a fully-graded one is not a comparison.
    """

    if submission.task_id != task.view.task_id:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=(
                f"submission {submission.run_id!r} is for task {submission.task_id!r}, "
                f"graded against {task.view.task_id!r}"
            ),
            recommended_action="grade each submission against its own task",
        )
    if submission.check_results is None:
        return Score(
            contestant_id=submission.contestant_id,
            task_id=task.view.task_id,
            measured=False,
            points=None,
            max_points=task.secret.max_points,
            checks_passed=None,
            checks_total=len(task.secret.hidden_checks),
            reason=(
                f"no hidden check was recorded for this {submission.outcome} attempt; "
                "unmeasured is not zero"
            ),
        )
    recorded = {item.check_id for item in submission.check_results}
    expected = set(task.secret.check_ids)
    if recorded != expected:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=(
                f"submission {submission.run_id!r} recorded checks {sorted(recorded)} "
                f"but task {task.view.task_id!r} declares {sorted(expected)}"
            ),
            recommended_action="grade every submission against the identical check set",
            details={"runId": submission.run_id},
        )
    passed = tuple(item for item in submission.check_results if item.passed)
    points = sum(task.secret.points_for(item.check_id) for item in passed)
    return Score(
        contestant_id=submission.contestant_id,
        task_id=task.view.task_id,
        measured=True,
        points=points,
        max_points=task.secret.max_points,
        checks_passed=len(passed),
        checks_total=len(task.secret.hidden_checks),
        reason=f"{len(passed)}/{len(task.secret.hidden_checks)} hidden checks passed",
    )


@dataclass(frozen=True, slots=True)
class Detection:
    """One anti-cheat detector firing, with the observation that made it fire.

    ``observed`` never contains reference text or hidden-check text.  A report
    that explains itself by quoting the secret hands the secret to everyone who
    reads the report, which is the failure the detector exists to prevent.
    """

    detector_id: str
    explanation: str
    observed: Mapping[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "detectorId": self.detector_id,
            "explanation": self.explanation,
            "observed": dict(self.observed),
        }


def _detect_reference_match(submission: Submission, task: ArenaTask) -> Detection | None:
    """Output that resembles the reference more closely than the task allows."""

    ceiling = task.view.similarity_ceiling_percent
    observed = similarity_percent(submission.solution_text, task.secret.reference_solution)
    if observed <= ceiling:
        return None
    return Detection(
        detector_id="reference-verbatim-match",
        explanation=(
            f"the submission overlaps the grader's reference by {observed}% of token "
            f"shingles, above the {ceiling}% ceiling for a {task.view.difficulty} task; "
            "on a task this open-ended, independent work does not converge that closely"
        ),
        observed={
            "similarityPercent": observed,
            "ceilingPercent": ceiling,
            "difficulty": str(task.view.difficulty),
        },
    )


def _detect_visible_test_special_casing(submission: Submission,
                                        task: ArenaTask) -> Detection | None:
    """A solution that hard-codes the inputs it was shown."""

    hits = sorted(
        value for value in task.view.visible_test_inputs
        if value and value in submission.solution_text
    )
    if not hits:
        return None
    return Detection(
        detector_id="visible-test-special-casing",
        explanation=(
            f"the submission contains {len(hits)} literal visible-test value(s); "
            "special-casing the examples passes the demonstration and fails the task"
        ),
        observed={"literals": hits, "literalCount": len(hits)},
    )


def _detect_out_of_scope_read(submission: Submission, task: ArenaTask) -> Detection | None:
    """A contestant reading outside the scope the task declared."""

    outside = sorted(
        path for path in submission.read_paths
        if not any(path == scope or path.startswith(scope) for scope in task.view.declared_scope)
    )
    if not outside:
        return None
    return Detection(
        detector_id="out-of-scope-read",
        explanation=(
            f"the submission read {len(outside)} path(s) outside the task's declared scope "
            f"{list(task.view.declared_scope)}; the scope is the boundary the score assumes"
        ),
        observed={"paths": outside, "declaredScope": list(task.view.declared_scope)},
    )


def _detect_implausible_wall_clock(submission: Submission, task: ArenaTask) -> Detection | None:
    """Work claimed in less time than the work physically takes."""

    floor = task.secret.min_plausible_wall_clock_ms
    if submission.wall_clock_ms >= floor:
        return None
    return Detection(
        detector_id="implausible-wall-clock",
        explanation=(
            f"the attempt claims completion in {submission.wall_clock_ms} ms against a "
            f"{floor} ms floor for this task; the result predates the work"
        ),
        observed={
            "wallClockMs": submission.wall_clock_ms,
            "floorMs": floor,
        },
    )


#: The detector set, in the order it is always applied.  A tuple rather than a
#: set so the report is byte-identical across runs.
DETECTORS: tuple[Callable[[Submission, ArenaTask], Detection | None], ...] = (
    _detect_reference_match,
    _detect_visible_test_special_casing,
    _detect_out_of_scope_read,
    _detect_implausible_wall_clock,
)


def detect_cheating(submission: Submission, task: ArenaTask) -> tuple[Detection, ...]:
    """Run every detector, in declared order, and return what fired."""

    return tuple(
        detection for detection in (detector(submission, task) for detector in DETECTORS)
        if detection is not None
    )


@dataclass(frozen=True, slots=True)
class QuarantineReason:
    """Why one match was excluded, kept so the leaderboard can show it."""

    contestant_id: str
    detector_id: str
    explanation: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "contestantId": self.contestant_id,
            "detectorId": self.detector_id,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class EvaluationProtocol:
    """The rules of the comparison, fixed before any match is judged.

    ``required_margin`` is a count of decided matches, not a p-value: over the
    handful of runs an arena of this kind actually performs, a significance
    test computed from three samples is decoration.  A stated minimum margin is
    a claim a reader can check.
    """

    min_runs_per_pair: int = 1
    required_margin: int = 1
    tie_break: str = "none"
    min_difficulty_classes: int = 1

    def __post_init__(self) -> None:
        require_int(self.min_runs_per_pair, "protocol.min_runs_per_pair", minimum=1)
        require_int(self.required_margin, "protocol.required_margin", minimum=1)
        require_int(self.min_difficulty_classes, "protocol.min_difficulty_classes", minimum=1)
        if self.tie_break not in {"none", "cost"}:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown tie_break {self.tie_break!r}",
                recommended_action="use 'none' or 'cost'",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "minRunsPerPair": self.min_runs_per_pair,
            "requiredMargin": self.required_margin,
            "tieBreak": self.tie_break,
            "minDifficultyClasses": self.min_difficulty_classes,
        }


@dataclass(frozen=True, slots=True)
class MatchResult:
    """One head-to-head, including the reason it decided nothing when it didn't."""

    match_id: str
    task_id: str
    task_class: str
    difficulty: Difficulty
    scores: tuple[Score, ...]
    winner: str | None
    reason: str
    detections: tuple[QuarantineReason, ...]
    quarantined: bool
    outcomes: tuple[tuple[str, str], ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "matchId": self.match_id,
            "taskId": self.task_id,
            "taskClass": self.task_class,
            "difficulty": str(self.difficulty),
            "scores": [item.to_payload() for item in self.scores],
            "winner": self.winner,
            "decided": self.winner is not None,
            "reason": self.reason,
            "detections": [item.to_payload() for item in self.detections],
            "quarantined": self.quarantined,
            "outcomes": [
                {"contestantId": contestant, "outcome": outcome}
                for contestant, outcome in self.outcomes
            ],
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def _check_fairness(contestants: Sequence[Contestant]) -> None:
    budgets = sorted({item.budget_micros for item in contestants})
    if len(budgets) > 1:
        raise KernelError(
            code="UNFAIR_COMPARISON",
            message=f"contestants were given different budgets: {budgets} micros",
            retryable=False,
            recommended_action="give every contestant the identical budget or do not compare",
            details={"budgetsMicros": budgets},
        )
    clocks = sorted({item.max_wall_clock_ms for item in contestants})
    if len(clocks) > 1:
        raise KernelError(
            code="UNFAIR_COMPARISON",
            message=f"contestants were given different wall-clock ceilings: {clocks} ms",
            retryable=False,
            recommended_action="equalise maxWallClockMs across contestants",
            details={"maxWallClockMs": clocks},
        )
    profiles = sorted({item.permission_profile_id for item in contestants})
    if len(profiles) > 1:
        raise KernelError(
            code="UNFAIR_COMPARISON",
            message=f"contestants ran under different permission profiles: {profiles}",
            retryable=False,
            recommended_action="run every contestant under one permission profile",
            details={"permissionProfileIds": profiles},
        )


def _check_environment(submission: Submission, task: ArenaTask,
                       environment_fingerprint: str) -> None:
    if submission.repo_snapshot_sha != task.view.repo_snapshot_sha:
        raise KernelError(
            code="STALE_SNAPSHOT",
            message=(
                f"submission {submission.run_id!r} ran against snapshot "
                f"{submission.repo_snapshot_sha} but task {task.view.task_id!r} is pinned to "
                f"{task.view.repo_snapshot_sha}"
            ),
            retryable=False,
            recommended_action="re-run the contestant against the frozen snapshot",
            details={"runId": submission.run_id},
        )
    if submission.environment_fingerprint != environment_fingerprint:
        raise KernelError(
            code="ARENA_ENV_DRIFT",
            message=(
                f"submission {submission.run_id!r} ran in environment "
                f"{submission.environment_fingerprint} but the arena froze "
                f"{environment_fingerprint}"
            ),
            retryable=False,
            recommended_action="re-run in the frozen image; a drifted environment is not a match",
            details={"runId": submission.run_id},
        )


def _check_tools(submission: Submission, contestant: Contestant) -> None:
    denied = sorted(set(submission.tools_used) - set(contestant.allowed_tools))
    if denied:
        raise KernelError(
            code="TOOL_DENIED",
            message=(
                f"contestant {contestant.contestant_id!r} used tool(s) {denied} that its "
                "permission profile does not grant"
            ),
            retryable=False,
            recommended_action="deny the run; a wider tool set is a different contestant",
            details={"contestantId": contestant.contestant_id, "deniedTools": denied},
        )


def judge_match(task: ArenaTask, submissions: Sequence[Submission],
                contestants: Mapping[str, Contestant], protocol: EvaluationProtocol, *,
                environment_fingerprint: str) -> MatchResult:
    """Decide one head-to-head from recorded artefacts alone.

    The order of the checks matters.  Fairness, snapshot and environment
    mismatches *raise*: they mean the two runs are not comparable, and a
    leaderboard built on them is wrong rather than merely dirty.  Cheating, in
    contrast, is *quarantined*: the match is recorded with its detectors and
    kept out of the standings, because the fact that a contestant cheated is
    the most valuable output the arena produces and deleting it destroys it.

    A winner requires two measured scores and two ``SUCCEEDED`` outcomes.  An
    interrupted or partial attempt never loses by default and never wins by
    default; the match reports ``winner=None`` and says why.
    """

    if len(submissions) != 2:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=(
                f"task {task.view.task_id!r} has {len(submissions)} submission(s); "
                "a head-to-head is exactly two"
            ),
            recommended_action="submit exactly one attempt per contestant per match",
        )
    ordered = tuple(sorted(submissions, key=lambda item: item.contestant_id))
    if ordered[0].contestant_id == ordered[1].contestant_id:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"contestant {ordered[0].contestant_id!r} appears on both sides",
            recommended_action="a contestant cannot play itself",
        )
    entrants = []
    for submission in ordered:
        contestant = contestants.get(submission.contestant_id)
        if contestant is None:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"submission from unregistered contestant {submission.contestant_id!r}",
                recommended_action="register every contestant before judging",
            )
        entrants.append(contestant)
    _check_fairness(entrants)
    for submission, contestant in zip(ordered, entrants, strict=True):
        _check_environment(submission, task, environment_fingerprint)
        _check_tools(submission, contestant)

    scores = tuple(score_submission(item, task) for item in ordered)
    reasons: list[QuarantineReason] = []
    for submission in ordered:
        for detection in detect_cheating(submission, task):
            reasons.append(QuarantineReason(
                contestant_id=submission.contestant_id,
                detector_id=detection.detector_id,
                explanation=detection.explanation,
            ))
    quarantined = bool(reasons)

    match_id = f"match-{task.view.task_id}-{ordered[0].contestant_id}-{ordered[1].contestant_id}"
    outcomes = tuple((item.contestant_id, str(item.outcome)) for item in ordered)

    if quarantined:
        winner: str | None = None
        reason = (
            f"quarantined: {len(reasons)} anti-cheat detection(s) "
            f"{sorted({item.detector_id for item in reasons})}; excluded from the standings "
            "and reported"
        )
    elif any(item.outcome is not SubmissionOutcome.SUCCEEDED for item in ordered):
        winner = None
        unfinished = sorted(
            f"{item.contestant_id}={item.outcome}" for item in ordered
            if item.outcome is not SubmissionOutcome.SUCCEEDED
        )
        reason = (
            f"undecided: {unfinished} did not reach SUCCEEDED; a non-success is not a loss"
        )
    elif any(not item.measured for item in scores):
        winner = None
        reason = "undecided: at least one submission was never graded; unmeasured is not zero"
    else:
        left, right = scores
        if left.points > right.points:
            winner, reason = left.contestant_id, (
                f"{left.points} > {right.points} hidden-check points"
            )
        elif right.points > left.points:
            winner, reason = right.contestant_id, (
                f"{right.points} > {left.points} hidden-check points"
            )
        elif protocol.tie_break == "cost":
            costs = {item.contestant_id: item.cost_micros for item in ordered}
            cheaper = sorted(costs.items(), key=lambda item: (item[1], item[0]))
            if cheaper[0][1] == cheaper[1][1]:
                winner, reason = None, (
                    f"draw at {left.points} points and {cheaper[0][1]} micros"
                )
            else:
                winner, reason = cheaper[0][0], (
                    f"draw at {left.points} points, broken on cost "
                    f"({cheaper[0][1]} < {cheaper[1][1]} micros)"
                )
        else:
            winner, reason = None, f"draw at {left.points} points; tie_break is 'none'"

    return MatchResult(
        match_id=match_id,
        task_id=task.view.task_id,
        task_class=task.view.task_class,
        difficulty=task.view.difficulty,
        scores=scores,
        winner=winner,
        reason=reason,
        detections=tuple(reasons),
        quarantined=quarantined,
        outcomes=outcomes,
    )


@dataclass(frozen=True, slots=True)
class LeaderboardEntry:
    """One contestant's standings, with everything that did not count visible."""

    contestant_id: str
    wins: int
    losses: int
    draws: int
    counted_matches: int
    points: int
    max_points: int
    undecided_matches: int
    unmeasured_matches: int
    excluded_matches: int
    cost_micros: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "contestantId": self.contestant_id,
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
            "countedMatches": self.counted_matches,
            "points": self.points,
            "maxPoints": self.max_points,
            "undecidedMatches": self.undecided_matches,
            "unmeasuredMatches": self.unmeasured_matches,
            "excludedMatches": self.excluded_matches,
            "costMicros": self.cost_micros,
            "pointsMeasured": self.counted_matches > 0,
        }


@dataclass(frozen=True, slots=True)
class AntiCheatReport:
    """The quarantine ledger, which is part of the result rather than a footnote."""

    quarantined_match_ids: tuple[str, ...]
    reasons: tuple[Mapping[str, Any], ...]
    detectors: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "quarantinedMatchIds": list(self.quarantined_match_ids),
            "quarantinedMatchCount": len(self.quarantined_match_ids),
            "reasons": [dict(item) for item in self.reasons],
            "detectorsApplied": list(self.detectors),
        }


@dataclass(frozen=True, slots=True)
class Leaderboard:
    """Standings that cannot be read without also reading the exclusions."""

    entries: tuple[LeaderboardEntry, ...]
    anti_cheat: AntiCheatReport
    counted_matches: int
    excluded_matches: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "entries": [item.to_payload() for item in self.entries],
            "countedMatches": self.counted_matches,
            "excludedMatches": self.excluded_matches,
            "antiCheat": self.anti_cheat.to_payload(),
            "note": (
                "excludedMatches are quarantined, not deleted; every exclusion is listed "
                "in antiCheat.reasons with the detector that fired"
            ),
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def build_leaderboard(results: Sequence[MatchResult],
                      contestant_ids: Sequence[str],
                      submissions: Sequence[Submission]) -> Leaderboard:
    """Aggregate matches into standings that show their own exclusions.

    A quarantined match contributes to ``excludedMatches`` and to the anti-cheat
    report, and to nothing else.  It is not silently dropped: the entry for
    each implicated contestant carries the count, so a reader cannot see a
    ranking without also seeing that some of it was thrown out and why.
    """

    cost_by_contestant: dict[str, int] = {}
    for submission in submissions:
        cost_by_contestant[submission.contestant_id] = (
            cost_by_contestant.get(submission.contestant_id, 0) + submission.cost_micros
        )
    entries: list[LeaderboardEntry] = []
    for contestant_id in sorted(set(contestant_ids)):
        wins = losses = draws = counted = points = max_points = 0
        undecided = unmeasured = excluded = 0
        for result in results:
            involved = [item.contestant_id for item in result.scores]
            if contestant_id not in involved:
                continue
            if result.quarantined:
                excluded += 1
                continue
            own = next(item for item in result.scores if item.contestant_id == contestant_id)
            if not own.measured:
                unmeasured += 1
                continue
            counted += 1
            points += int(own.points or 0)
            max_points += own.max_points
            if result.winner is None:
                if all(item.measured for item in result.scores) and all(
                    outcome == str(SubmissionOutcome.SUCCEEDED)
                    for _, outcome in result.outcomes
                ):
                    draws += 1
                else:
                    undecided += 1
            elif result.winner == contestant_id:
                wins += 1
            else:
                losses += 1
        entries.append(LeaderboardEntry(
            contestant_id=contestant_id,
            wins=wins,
            losses=losses,
            draws=draws,
            counted_matches=counted,
            points=points,
            max_points=max_points,
            undecided_matches=undecided,
            unmeasured_matches=unmeasured,
            excluded_matches=excluded,
            cost_micros=cost_by_contestant.get(contestant_id, 0),
        ))
    entries.sort(key=lambda item: (-item.wins, item.losses, -item.points, item.contestant_id))
    quarantined = tuple(sorted(item.match_id for item in results if item.quarantined))
    reasons = tuple(
        {"matchId": result.match_id, **reason.to_payload()}
        for result in sorted(results, key=lambda item: item.match_id)
        for reason in result.detections
    )
    return Leaderboard(
        entries=tuple(entries),
        anti_cheat=AntiCheatReport(
            quarantined_match_ids=quarantined,
            reasons=reasons,
            detectors=tuple(
                detector.__name__.removeprefix("_detect_").replace("_", "-")
                for detector in DETECTORS
            ),
        ),
        counted_matches=sum(1 for item in results if not item.quarantined),
        excluded_matches=len(quarantined),
    )


def pairwise_confidence(results: Sequence[MatchResult], protocol: EvaluationProtocol,
                        left: str, right: str) -> Mapping[str, Any]:
    """State whether the head-to-head record actually decides anything.

    Two integers decide it: how many matches counted, and the win margin.  A
    margin below the protocol's declared requirement is reported as undecided
    with the numbers attached, rather than as a narrow victory — and a pair
    with fewer counted matches than the protocol demands raises
    ``INSUFFICIENT_RUNS``, because "we ran it once" is not a comparison.
    """

    counted = [
        item for item in results
        if not item.quarantined
        and {score.contestant_id for score in item.scores} == {left, right}
    ]
    decided = [item for item in counted if item.winner is not None]
    if len(counted) < protocol.min_runs_per_pair:
        raise KernelError(
            code="INSUFFICIENT_RUNS",
            message=(
                f"{left!r} vs {right!r} has {len(counted)} counted match(es); the protocol "
                f"requires {protocol.min_runs_per_pair}"
            ),
            retryable=True,
            recommended_action="run more matches before reading the comparison",
            details={"left": left, "right": right, "countedMatches": len(counted)},
        )
    left_wins = sum(1 for item in decided if item.winner == left)
    right_wins = sum(1 for item in decided if item.winner == right)
    margin = abs(left_wins - right_wins)
    leader = None if left_wins == right_wins else (left if left_wins > right_wins else right)
    return {
        "left": left,
        "right": right,
        "countedMatches": len(counted),
        "decidedMatches": len(decided),
        "excludedMatches": sum(
            1 for item in results
            if item.quarantined and {s.contestant_id for s in item.scores} == {left, right}
        ),
        "leftWins": left_wins,
        "rightWins": right_wins,
        "margin": margin,
        "requiredMargin": protocol.required_margin,
        "confident": margin >= protocol.required_margin and leader is not None,
        "leader": leader if margin >= protocol.required_margin else None,
        "reason": (
            f"margin {margin} meets the required {protocol.required_margin}"
            if margin >= protocol.required_margin and leader is not None
            else f"margin {margin} is below the required {protocol.required_margin}"
        ),
        "measured": True,
    }


def quality_cost_frontier(entries: Sequence[LeaderboardEntry]) -> tuple[Mapping[str, Any], ...]:
    """Points against cost, with dominated entrants marked rather than hidden.

    Quality and cost are reported as two integers and never combined into one
    "value" number: a single blended score lets whoever picks the weights pick
    the winner.  An entrant with no counted match is on neither side of the
    frontier and says so.
    """

    frontier: list[Mapping[str, Any]] = []
    for entry in sorted(entries, key=lambda item: item.contestant_id):
        if entry.counted_matches == 0:
            frontier.append({
                "contestantId": entry.contestant_id,
                "measured": False,
                "points": None,
                "costMicros": entry.cost_micros,
                "dominatedBy": [],
                "reason": "no counted match; quality is unmeasured, not zero",
            })
            continue
        dominators = sorted(
            other.contestant_id for other in entries
            if other.contestant_id != entry.contestant_id
            and other.counted_matches > 0
            and other.points >= entry.points
            and other.cost_micros <= entry.cost_micros
            and (other.points > entry.points or other.cost_micros < entry.cost_micros)
        )
        frontier.append({
            "contestantId": entry.contestant_id,
            "measured": True,
            "points": entry.points,
            "costMicros": entry.cost_micros,
            "dominatedBy": dominators,
            "onFrontier": not dominators,
            "reason": (
                "no entrant is at least as good and at least as cheap"
                if not dominators else f"dominated by {dominators}"
            ),
        })
    return tuple(frontier)


def record_arena_match(events: EventStore, stream_id: str, result: MatchResult, *,
                       fencing_token: int) -> Mapping[str, Any]:
    """Append one judged match to the arena stream, once, under a fencing token."""

    require_int(fencing_token, "fencing_token", minimum=1)
    event = events.append(stream_id, result.to_payload(), idempotency_key=result.digest,
                          fencing_token=fencing_token)
    return {
        "sequence": event.sequence,
        "eventId": event.event_id,
        "hashChain": event.hash_chain,
        "matchDigest": result.digest,
    }


# --- registry entry point ----------------------------------------------------

_REQUEST_FIELDS = frozenset({
    "arena_task_set", "agent_candidates", "fixed_environments", "budgets",
    "evaluation_protocol",
})


def _decode_task(payload: Mapping[str, Any], *, snapshot: str, budget_micros: int,
                 max_wall_clock_ms: int) -> ArenaTask:
    reject_unknown_fields(payload, {"view", "secret"}, field_name="task")
    view_payload = require_mapping(payload.get("view"), "task.view")
    reject_unknown_fields(
        view_payload,
        {"taskId", "taskClass", "difficulty", "statement", "visibleTestInputs", "declaredScope"},
        field_name="task.view",
    )
    difficulty = require_str(view_payload.get("difficulty"), "task.view.difficulty",
                             max_length=32)
    if difficulty not in {item.value for item in Difficulty}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown difficulty {difficulty!r}",
            recommended_action=f"use one of {sorted(d.value for d in Difficulty)}",
        )
    view = TaskView(
        task_id=require_identifier(view_payload.get("taskId"), "task.view.taskId"),
        task_class=require_identifier(view_payload.get("taskClass"), "task.view.taskClass"),
        difficulty=Difficulty(difficulty),
        statement=require_str(view_payload.get("statement"), "task.view.statement"),
        visible_test_inputs=require_str_seq(view_payload.get("visibleTestInputs", ()),
                                            "task.view.visibleTestInputs"),
        declared_scope=require_str_seq(view_payload.get("declaredScope", ()),
                                       "task.view.declaredScope", allow_empty=False),
        repo_snapshot_sha=snapshot,
        budget_micros=budget_micros,
        max_wall_clock_ms=max_wall_clock_ms,
    )
    secret_payload = require_mapping(payload.get("secret"), "task.secret")
    reject_unknown_fields(
        secret_payload,
        {"referenceSolution", "hiddenChecks", "minPlausibleWallClockMs"},
        field_name="task.secret",
    )
    checks = tuple(
        HiddenCheck(
            check_id=require_identifier(
                require_mapping(item, "hiddenChecks[]").get("checkId"), "hiddenCheck.checkId"),
            expression=require_str(require_mapping(item, "hiddenChecks[]").get("expression"),
                                   "hiddenCheck.expression"),
            points=require_int(require_mapping(item, "hiddenChecks[]").get("points", 1),
                               "hiddenCheck.points", minimum=1),
        )
        for item in secret_payload.get("hiddenChecks", ())
    )
    secret = TaskSecret(
        task_id=view.task_id,
        reference_solution=require_str(secret_payload.get("referenceSolution"),
                                       "task.secret.referenceSolution", max_length=1 << 18),
        hidden_checks=checks,
        min_plausible_wall_clock_ms=require_int(
            secret_payload.get("minPlausibleWallClockMs"),
            "task.secret.minPlausibleWallClockMs", minimum=1),
    )
    return ArenaTask(view=view, secret=secret)


def _decode_submission(payload: Mapping[str, Any]) -> Submission:
    reject_unknown_fields(
        payload,
        {"contestantId", "taskId", "runId", "outcome", "solutionText", "readPaths",
         "toolsUsed", "wallClockMs", "costMicros", "repoSnapshotSha",
         "environmentFingerprint", "checkResults", "manualInterventions", "evidenceIds"},
        field_name="submission",
    )
    outcome = require_str(payload.get("outcome"), "submission.outcome", max_length=32)
    if outcome not in {item.value for item in SubmissionOutcome}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown submission outcome {outcome!r}",
            recommended_action=f"use one of {sorted(o.value for o in SubmissionOutcome)}",
        )
    raw_checks = payload.get("checkResults")
    if raw_checks is None:
        checks: tuple[CheckOutcome, ...] | None = None
    else:
        checks = tuple(
            CheckOutcome(
                check_id=require_identifier(require_mapping(item, "checkResults[]").get("checkId"),
                                            "checkResult.checkId"),
                passed=bool(require_mapping(item, "checkResults[]").get("passed")),
            )
            for item in raw_checks
        )
    return Submission(
        contestant_id=require_identifier(payload.get("contestantId"), "submission.contestantId"),
        task_id=require_identifier(payload.get("taskId"), "submission.taskId"),
        run_id=require_identifier(payload.get("runId"), "submission.runId"),
        outcome=SubmissionOutcome(outcome),
        solution_text=require_str(payload.get("solutionText"), "submission.solutionText",
                                  max_length=1 << 18),
        read_paths=require_str_seq(payload.get("readPaths", ()), "submission.readPaths"),
        tools_used=require_str_seq(payload.get("toolsUsed", ()), "submission.toolsUsed"),
        wall_clock_ms=require_int(payload.get("wallClockMs"), "submission.wallClockMs",
                                  minimum=0),
        cost_micros=require_int(payload.get("costMicros"), "submission.costMicros", minimum=0),
        repo_snapshot_sha=require_str(payload.get("repoSnapshotSha"),
                                      "submission.repoSnapshotSha", max_length=128),
        environment_fingerprint=require_str(payload.get("environmentFingerprint"),
                                            "submission.environmentFingerprint", max_length=128),
        check_results=checks,
        manual_interventions=require_int(payload.get("manualInterventions", 0),
                                         "submission.manualInterventions", minimum=0),
        evidence_ids=require_str_seq(payload.get("evidenceIds", ()), "submission.evidenceIds"),
    )


def _failure_analysis(submissions: Sequence[Submission], results: Sequence[MatchResult],
                      tasks: Sequence[ArenaTask]) -> Mapping[str, Any]:
    outcome_counts = {
        str(value): sum(1 for item in submissions if item.outcome is value)
        for value in SubmissionOutcome
    }
    difficulty_counts = {
        str(value): sum(1 for item in tasks if item.view.difficulty is value)
        for value in Difficulty
    }
    return {
        "outcomeCounts": outcome_counts,
        "manualInterventions": sum(item.manual_interventions for item in submissions),
        "unmeasuredSubmissions": sum(1 for item in submissions if not item.score_is_measurable),
        "quarantinedMatches": sum(1 for item in results if item.quarantined),
        "undecidedMatches": sum(
            1 for item in results if item.winner is None and not item.quarantined
        ),
        "taskMix": difficulty_counts,
        "difficultyClassesCovered": sum(1 for count in difficulty_counts.values() if count),
        "measured": True,
    }


@register("agent-arena")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point.

    Builds the frozen task set, judges every head-to-head from recorded
    artefacts, and returns the standings together with the quarantine ledger.
    It never promotes anyone: ``promotion_candidate`` names at most a candidate
    and always states the evidence behind it, or states that there is none.
    """

    reject_unknown_fields(request, _REQUEST_FIELDS, field_name="agent-arena request")
    for name in ("arena_task_set", "agent_candidates", "fixed_environments", "budgets",
                 "evaluation_protocol"):
        if name not in request:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"{name} is required",
                recommended_action=f"supply {name}",
            )

    budgets = require_mapping(request.get("budgets"), "budgets")
    reject_unknown_fields(budgets, {"budgetMicros", "maxWallClockMs"}, field_name="budgets")
    budget_micros = require_int(budgets.get("budgetMicros"), "budgets.budgetMicros", minimum=1)
    max_wall_clock_ms = require_int(budgets.get("maxWallClockMs"), "budgets.maxWallClockMs",
                                    minimum=1)

    environments = require_mapping(request.get("fixed_environments"), "fixed_environments")
    reject_unknown_fields(environments, {"environmentId", "fingerprint"},
                          field_name="fixed_environments")
    environment_id = require_identifier(environments.get("environmentId"),
                                        "fixed_environments.environmentId")
    fingerprint = require_str(environments.get("fingerprint"), "fixed_environments.fingerprint",
                              max_length=128)

    task_set = require_mapping(request.get("arena_task_set"), "arena_task_set")
    reject_unknown_fields(task_set, {"repoSnapshotSha", "tasks"}, field_name="arena_task_set")
    snapshot = require_str(task_set.get("repoSnapshotSha"), "arena_task_set.repoSnapshotSha",
                           max_length=128)
    raw_tasks = task_set.get("tasks", ())
    if not raw_tasks:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="arena_task_set.tasks is empty",
            recommended_action="supply at least one task",
        )
    tasks = tuple(
        _decode_task(require_mapping(item, "tasks[]"), snapshot=snapshot,
                     budget_micros=budget_micros, max_wall_clock_ms=max_wall_clock_ms)
        for item in raw_tasks
    )
    by_task = {item.view.task_id: item for item in tasks}

    candidates = require_mapping(request.get("agent_candidates"), "agent_candidates")
    reject_unknown_fields(candidates, {"contestants", "submissions"},
                          field_name="agent_candidates")
    contestants: dict[str, Contestant] = {}
    for item in candidates.get("contestants", ()):
        payload = require_mapping(item, "contestants[]")
        reject_unknown_fields(
            payload,
            {"contestantId", "family", "permissionProfileId", "allowedTools", "budgetMicros",
             "maxWallClockMs"},
            field_name="contestant",
        )
        contestant = Contestant(
            contestant_id=require_identifier(payload.get("contestantId"),
                                             "contestant.contestantId"),
            family=require_identifier(payload.get("family"), "contestant.family"),
            permission_profile_id=require_identifier(payload.get("permissionProfileId"),
                                                     "contestant.permissionProfileId"),
            allowed_tools=require_str_seq(payload.get("allowedTools", ()),
                                          "contestant.allowedTools", allow_empty=False),
            budget_micros=require_int(payload.get("budgetMicros", budget_micros),
                                      "contestant.budgetMicros", minimum=1),
            max_wall_clock_ms=require_int(payload.get("maxWallClockMs", max_wall_clock_ms),
                                          "contestant.maxWallClockMs", minimum=1),
        )
        contestants[contestant.contestant_id] = contestant
    if len(contestants) < 2:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message=f"an arena needs at least two contestants, got {len(contestants)}",
            recommended_action="register a second contestant",
        )
    _check_fairness(tuple(contestants.values()))

    protocol_payload = require_mapping(request.get("evaluation_protocol"), "evaluation_protocol")
    reject_unknown_fields(
        protocol_payload,
        {"minRunsPerPair", "requiredMargin", "tieBreak", "minDifficultyClasses"},
        field_name="evaluation_protocol",
    )
    protocol = EvaluationProtocol(
        min_runs_per_pair=require_int(protocol_payload.get("minRunsPerPair", 1),
                                      "evaluation_protocol.minRunsPerPair", minimum=1),
        required_margin=require_int(protocol_payload.get("requiredMargin", 1),
                                    "evaluation_protocol.requiredMargin", minimum=1),
        tie_break=require_str(protocol_payload.get("tieBreak", "none"),
                              "evaluation_protocol.tieBreak", max_length=16),
        min_difficulty_classes=require_int(protocol_payload.get("minDifficultyClasses", 1),
                                           "evaluation_protocol.minDifficultyClasses",
                                           minimum=1),
    )
    covered = {item.view.difficulty for item in tasks}
    if len(covered) < protocol.min_difficulty_classes:
        raise KernelError(
            code="UNFAIR_COMPARISON",
            message=(
                f"the task set covers {len(covered)} difficulty class(es), the protocol "
                f"requires {protocol.min_difficulty_classes}; a set of easy tasks measures "
                "the easy tasks"
            ),
            retryable=False,
            recommended_action="add tasks from the missing difficulty classes",
            details={"covered": sorted(str(item) for item in covered)},
        )

    submissions = tuple(
        _decode_submission(require_mapping(item, "submissions[]"))
        for item in candidates.get("submissions", ())
    )
    for submission in submissions:
        if submission.task_id not in by_task:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"submission {submission.run_id!r} names unknown task "
                        f"{submission.task_id!r}",
                recommended_action="submit only against tasks in the frozen set",
            )
        if submission.contestant_id not in contestants:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"submission {submission.run_id!r} names unknown contestant "
                        f"{submission.contestant_id!r}",
                recommended_action="register the contestant first",
            )
    for task in tasks:
        answered = {
            item.contestant_id for item in submissions if item.task_id == task.view.task_id
        }
        missing = sorted(set(contestants) - answered)
        if missing:
            raise KernelError(
                code="UNFAIR_COMPARISON",
                message=(
                    f"task {task.view.task_id!r} was not attempted by {missing}; every "
                    "contestant must be asked the same questions"
                ),
                retryable=False,
                recommended_action="run the missing attempts or drop the task from the set",
                details={"taskId": task.view.task_id, "missing": missing},
            )

    results = tuple(
        judge_match(
            by_task[task_id],
            tuple(item for item in submissions if item.task_id == task_id),
            contestants,
            protocol,
            environment_fingerprint=fingerprint,
        )
        for task_id in sorted(by_task)
    )
    leaderboard = build_leaderboard(results, tuple(contestants), submissions)
    ids = sorted(contestants)
    confidences = tuple(
        pairwise_confidence(results, protocol, left, right)
        for index, left in enumerate(ids) for right in ids[index + 1:]
    )
    frontier = quality_cost_frontier(leaderboard.entries)

    top = leaderboard.entries[0] if leaderboard.entries else None
    decisive = [item for item in confidences if item["confident"]]
    if top is None or top.counted_matches == 0:
        candidate: Mapping[str, Any] = {
            "selected": None,
            "reason": "no match counted towards the standings",
            "measured": False,
        }
    elif top.excluded_matches:
        candidate = {
            "selected": None,
            "reason": (
                f"the leader has {top.excluded_matches} quarantined match(es); a contestant "
                "under an open anti-cheat detection is not promotable until it is resolved"
            ),
            "excludedMatches": top.excluded_matches,
            "measured": True,
        }
    elif not decisive:
        candidate = {
            "selected": None,
            "reason": (
                "no pairwise comparison reached the protocol's required margin; a leader "
                "on an undecided record is not a promotion candidate"
            ),
            "measured": True,
        }
    else:
        candidate = {
            "selected": top.contestant_id,
            "reason": (
                f"{top.wins} win(s) with {len(decisive)} decisive pairwise comparison(s) "
                f"and {top.excluded_matches} quarantined match(es)"
            ),
            "wins": top.wins,
            "excludedMatches": top.excluded_matches,
            "measured": True,
        }

    evidence_ids = sorted({item for entry in submissions for item in entry.evidence_ids})
    return {
        "arena_runs": {
            "environmentId": environment_id,
            "environmentFingerprint": fingerprint,
            "repoSnapshotSha": snapshot,
            "protocol": protocol.to_payload(),
            "tasks": [item.to_contestant_payload() for item in tasks],
            "taskSecrets": [item.secret.public_summary() for item in tasks],
            "submissions": [item.to_payload() for item in submissions],
            "runsDigest": digest([item.to_payload() for item in submissions]),
        },
        "pairwise_results": {
            "matches": [item.to_payload() for item in results],
            "confidence": [dict(item) for item in confidences],
            "leaderboard": leaderboard.to_payload(),
            "leaderboardDigest": leaderboard.digest,
        },
        "quality_cost_frontier": [dict(item) for item in frontier],
        "failure_analysis": _failure_analysis(submissions, results, tasks),
        "promotion_candidate": dict(candidate),
        "evidenceIds": evidence_ids,
    }


def view_field_names() -> tuple[str, ...]:
    """The contestant-visible field set, exposed so tests can assert on it."""

    return tuple(field.name for field in fields(TaskView))
