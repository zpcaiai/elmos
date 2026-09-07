"""Repository model ELO: ratings that admit what they do not know.

Three honesty problems are solved here, and none of them is the arithmetic.

The first is precision.  Ratings are compared, ranked, persisted and hashed, so
they are held as integers of one hundredth of a rating point and the expectancy
curve is a *declared integer table* rather than a float formula.  A float
``1/(1+10**(-d/400))`` gives different last bits on different machines, and two
machines that disagree about a rating disagree about which model to route to.

The second is convergence.  A rating computed from two matches is not a smaller
version of a rating computed from two hundred; it is a different kind of claim.
Below the policy's minimum a rating is ``provisional`` and carries its
interval, and :func:`ranking` puts provisional entries in a separate section
that :func:`compare` refuses to compare against a converged one.  A leaderboard
that lists both in one column invites exactly the mistake the uncertainty was
computed to prevent.

The third is order.  Elo is path dependent: the same matches in a different
sequence give different ratings, and no amount of care changes that.  Rather
than pretend otherwise, the module declares :data:`ORDER_TOLERANCE_CENTI`,
reports it on every output, and provides :func:`order_sensitivity` so a caller
can measure the spread over the orderings it cares about instead of trusting a
number whose stability was never checked.

Two smaller rules earn their keep.  An ``UNDECIDED`` match — a quarantined
arena match, an interrupted run — never moves a rating and is never folded into
a draw, because a draw is information and an interruption is not.  And ratings
are kept per task class: a model strong at refactoring and weak at migration
has two ratings, and :func:`aggregate` refuses to merge them without an
explicit caller-supplied weighting, since whoever picks the weights picks the
winner.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import isqrt
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
from .errors import Category, KernelError, register_codes
from .ports import EventStore
from .registry import register

__all__ = [
    "CENTI",
    "EXPECTANCY_BASIS_POINTS",
    "Entrant",
    "MatchRecord",
    "MatchResultValue",
    "ORDER_TOLERANCE_CENTI",
    "Rating",
    "RatingBook",
    "RatingPolicy",
    "aggregate",
    "compare",
    "drift_alerts",
    "expected_score_bp",
    "handle",
    "order_sensitivity",
    "ranking",
    "rate",
    "record_rating_update",
    "routing_recommendation",
    "uncertainty_centi",
]

register_codes(
    Category.SEMANTIC,
    "ELO_DATA_SPARSE",
    "RATING_DRIFT",
    "SEGMENT_BIAS",
    "CROSS_CLASS_AGGREGATION_REFUSED",
)
register_codes(
    Category.POLICY,
    "ROUTING_RECOMMENDATION_UNSAFE",
)

#: Ratings are integers of one hundredth of a rating point.  1500.00 is
#: ``150000``.  Nothing in this module ever holds a rating as a float.
CENTI = 100

#: Expectancy for the *higher rated* side, in basis points, sampled every 25
#: rating points from 0 to 800.  The table is the model: it is data a reviewer
#: can read and a test can pin, where a float expression is a promise that two
#: machines round identically.
EXPECTANCY_BASIS_POINTS: tuple[int, ...] = (
    5000, 5359, 5715, 6063,
    6401, 6725, 7034, 7325,
    7597, 7850, 8083, 8296,
    8490, 8666, 8823, 8965,
    9091, 9203, 9302, 9390,
    9468, 9536, 9595, 9648,
    9693, 9733, 9768, 9799,
    9825, 9848, 9868, 9886,
    9901,
)

#: Spacing of the expectancy table, in centi-rating (25 rating points).
_STEP_CENTI = 25 * CENTI

#: How far two ratings computed from the same matches in different orders are
#: allowed to differ before the module calls the result order-dependent.  Fifty
#: rating points is not a tight bound and is not meant to be: with a K-factor
#: of 32 over a few dozen matches, permutation genuinely moves a rating that
#: far, and a tolerance chosen to look impressive would simply be false.
ORDER_TOLERANCE_CENTI = 50 * CENTI


def _div_round(numerator: int, denominator: int) -> int:
    """Integer division with round-half-to-even.

    Truncation biases every update towards zero, which over a season quietly
    drags the whole table towards the seed.  Half-to-even keeps the bias out
    without introducing a float.
    """

    if denominator == 0:
        raise KernelError(
            code="MALFORMED_INPUT",
            message="division by zero in rating arithmetic",
            recommended_action="treat as a kernel defect",
        )
    negative = (numerator < 0) != (denominator < 0)
    n, d = abs(numerator), abs(denominator)
    quotient, remainder = divmod(n, d)
    twice = remainder * 2
    if twice > d or (twice == d and quotient % 2 == 1):
        quotient += 1
    return -quotient if negative else quotient


def expected_score_bp(rating_a_centi: int, rating_b_centi: int) -> int:
    """Expected score for A against B, in basis points (0..10000).

    Linear interpolation over :data:`EXPECTANCY_BASIS_POINTS`, clamped beyond
    800 rating points where the curve is flat enough that the difference stops
    mattering and the extrapolation would only invent precision.
    """

    difference = rating_a_centi - rating_b_centi
    magnitude = abs(difference)
    last = len(EXPECTANCY_BASIS_POINTS) - 1
    index = magnitude // _STEP_CENTI
    if index >= last:
        higher_bp = EXPECTANCY_BASIS_POINTS[last]
    else:
        low = EXPECTANCY_BASIS_POINTS[index]
        high = EXPECTANCY_BASIS_POINTS[index + 1]
        offset = magnitude - index * _STEP_CENTI
        higher_bp = low + _div_round((high - low) * offset, _STEP_CENTI)
    return higher_bp if difference >= 0 else 10_000 - higher_bp


class MatchResultValue(StrEnum):
    """What a match established.

    ``UNDECIDED`` is a first-class value, not an absence.  A quarantined arena
    match, an interrupted contestant or a comparison the protocol refused to
    call all land here, and none of them moves a rating.  Recording them as
    draws would let infrastructure failures and detected cheating push ratings
    towards the mean and call it evidence.
    """

    WIN_A = "WIN_A"
    WIN_B = "WIN_B"
    DRAW = "DRAW"
    UNDECIDED = "UNDECIDED"


@dataclass(frozen=True, slots=True)
class Entrant:
    """A rated thing at a specific version.

    The version is part of the identity.  A model that shipped a new build is a
    new entrant with a fresh, provisional rating: carrying the old number
    forward would present two hundred matches of evidence about software that
    no longer exists.
    """

    contestant_id: str
    version: str

    def __post_init__(self) -> None:
        require_identifier(self.contestant_id, "entrant.contestant_id")
        require_identifier(self.version, "entrant.version")

    @property
    def key(self) -> str:
        return f"{self.contestant_id}:{self.version}"

    def to_payload(self) -> dict[str, Any]:
        return {"contestantId": self.contestant_id, "version": self.version, "key": self.key}


@dataclass(frozen=True, slots=True)
class MatchRecord:
    """One rated comparison, with its source and its snapshot."""

    match_id: str
    task_class: str
    a: Entrant
    b: Entrant
    result: MatchResultValue
    source: str = "arena"
    repo_snapshot_sha: str = ""
    reason: str = ""
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.match_id, "match.match_id")
        require_identifier(self.task_class, "match.task_class")
        if not isinstance(self.result, MatchResultValue):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown match result {self.result!r}",
                recommended_action=f"use one of {sorted(v.value for v in MatchResultValue)}",
            )
        if self.a.key == self.b.key:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"entrant {self.a.key!r} appears on both sides of {self.match_id!r}",
                recommended_action="an entrant cannot play itself",
            )
        if self.source not in {"arena", "production"}:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown match source {self.source!r}",
                recommended_action="use 'arena' or 'production'",
            )

    @property
    def is_rated(self) -> bool:
        return self.result is not MatchResultValue.UNDECIDED

    def to_payload(self) -> dict[str, Any]:
        return {
            "matchId": self.match_id,
            "taskClass": self.task_class,
            "a": self.a.to_payload(),
            "b": self.b.to_payload(),
            "result": str(self.result),
            "source": self.source,
            "repoSnapshotSha": self.repo_snapshot_sha,
            "reason": self.reason,
            "evidenceIds": list(self.evidence_ids),
            "rated": self.is_rated,
        }


@dataclass(frozen=True, slots=True)
class RatingPolicy:
    """Every knob that decides a rating, stated rather than assumed.

    All values are integers in centi-rating.  ``min_uncertainty_centi`` exists
    so that an interval never collapses to zero width: a rating with no
    uncertainty is a claim no finite number of matches supports.
    """

    k_factor_centi: int = 32 * CENTI
    seed_centi: int = 1500 * CENTI
    min_matches: int = 10
    base_uncertainty_centi: int = 350 * CENTI
    min_uncertainty_centi: int = 25 * CENTI
    drift_threshold_centi: int = 100 * CENTI
    high_risk_min_matches: int = 30

    def __post_init__(self) -> None:
        require_int(self.k_factor_centi, "policy.k_factor_centi", minimum=1)
        require_int(self.seed_centi, "policy.seed_centi", minimum=0)
        require_int(self.min_matches, "policy.min_matches", minimum=1)
        require_int(self.base_uncertainty_centi, "policy.base_uncertainty_centi", minimum=1)
        require_int(self.min_uncertainty_centi, "policy.min_uncertainty_centi", minimum=1)
        require_int(self.drift_threshold_centi, "policy.drift_threshold_centi", minimum=1)
        require_int(self.high_risk_min_matches, "policy.high_risk_min_matches", minimum=1)
        if self.min_uncertainty_centi > self.base_uncertainty_centi:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="min_uncertainty_centi cannot exceed base_uncertainty_centi",
                recommended_action="lower the floor or raise the base",
            )
        if self.high_risk_min_matches < self.min_matches:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=(
                    "high_risk_min_matches below min_matches would let a high-risk route "
                    "accept less evidence than an ordinary one"
                ),
                recommended_action="raise high_risk_min_matches to at least min_matches",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "kFactorCenti": self.k_factor_centi,
            "seedCenti": self.seed_centi,
            "minMatches": self.min_matches,
            "baseUncertaintyCenti": self.base_uncertainty_centi,
            "minUncertaintyCenti": self.min_uncertainty_centi,
            "driftThresholdCenti": self.drift_threshold_centi,
            "highRiskMinMatches": self.high_risk_min_matches,
            "ratingScale": CENTI,
            "orderToleranceCenti": ORDER_TOLERANCE_CENTI,
        }


def uncertainty_centi(match_count: int, policy: RatingPolicy) -> int:
    """Uncertainty that shrinks with evidence and never reaches zero.

    ``base / sqrt(n)`` on integers: four matches halve it, sixteen quarter it,
    and the policy floor stops it from claiming a certainty that no sample size
    justifies.
    """

    require_int(match_count, "match_count", minimum=0)
    if match_count <= 0:
        return policy.base_uncertainty_centi
    value = _div_round(policy.base_uncertainty_centi, isqrt(match_count))
    return max(value, policy.min_uncertainty_centi)


@dataclass(frozen=True, slots=True)
class Rating:
    """One entrant's standing in one task class.

    ``provisional`` is not a warning label that a caller may ignore: the
    ranking separates provisional entries, and :func:`compare` refuses to rank
    one against a converged rating at all.
    """

    entrant: Entrant
    task_class: str
    rating_centi: int
    match_count: int
    decided_count: int
    uncertainty_centi: int
    provisional: bool
    min_matches: int

    @property
    def interval_centi(self) -> tuple[int, int]:
        """Two standard uncertainties either side, as integers."""

        return (self.rating_centi - 2 * self.uncertainty_centi,
                self.rating_centi + 2 * self.uncertainty_centi)

    def to_payload(self) -> dict[str, Any]:
        low, high = self.interval_centi
        return {
            "entrant": self.entrant.to_payload(),
            "taskClass": self.task_class,
            "ratingCenti": self.rating_centi,
            "matchCount": self.match_count,
            "decidedCount": self.decided_count,
            "uncertaintyCenti": self.uncertainty_centi,
            "intervalCenti": [low, high],
            "provisional": self.provisional,
            "minMatches": self.min_matches,
            "measured": self.match_count > 0,
            "note": (
                f"provisional: {self.match_count} match(es) against a {self.min_matches} "
                "minimum; not comparable with a converged rating"
                if self.provisional else "converged"
            ),
        }


class RatingBook:
    """Per-task-class ratings, updated one match at a time.

    There is deliberately no global rating in here.  ``I1`` of the skill is
    that ELO is not a single leaderboard, and the way to enforce that is to
    make the global number impossible to obtain without stating a weighting —
    see :func:`aggregate`.
    """

    def __init__(self, policy: RatingPolicy | None = None) -> None:
        self._policy = policy or RatingPolicy()
        self._ratings: dict[tuple[str, str], int] = {}
        self._counts: dict[tuple[str, str], int] = {}
        self._decided: dict[tuple[str, str], int] = {}
        self._entrants: dict[str, Entrant] = {}
        self._skipped: list[MatchRecord] = []

    @property
    def policy(self) -> RatingPolicy:
        return self._policy

    @property
    def skipped(self) -> tuple[MatchRecord, ...]:
        """Matches that established nothing, kept visible rather than dropped."""

        return tuple(self._skipped)

    def task_classes(self) -> tuple[str, ...]:
        return tuple(sorted({task_class for task_class, _ in self._ratings}))

    def keys(self, task_class: str) -> tuple[str, ...]:
        return tuple(sorted(key for cls, key in self._ratings if cls == task_class))

    def _seed(self, task_class: str, entrant: Entrant) -> None:
        index = (task_class, entrant.key)
        if index not in self._ratings:
            self._ratings[index] = self._policy.seed_centi
            self._counts[index] = 0
            self._decided[index] = 0
        self._entrants[entrant.key] = entrant

    def apply(self, match: MatchRecord) -> None:
        """Fold one match in.  An undecided match seeds but never moves."""

        self._seed(match.task_class, match.a)
        self._seed(match.task_class, match.b)
        left = (match.task_class, match.a.key)
        right = (match.task_class, match.b.key)
        if not match.is_rated:
            self._skipped.append(match)
            return
        self._counts[left] += 1
        self._counts[right] += 1
        if match.result is not MatchResultValue.DRAW:
            self._decided[left] += 1
            self._decided[right] += 1
        expected_a = expected_score_bp(self._ratings[left], self._ratings[right])
        actual_a = {
            MatchResultValue.WIN_A: 10_000,
            MatchResultValue.WIN_B: 0,
            MatchResultValue.DRAW: 5_000,
        }[match.result]
        delta = _div_round(self._policy.k_factor_centi * (actual_a - expected_a), 10_000)
        self._ratings[left] += delta
        self._ratings[right] -= delta

    def rating(self, entrant_key: str, task_class: str) -> Rating:
        index = (task_class, entrant_key)
        if index not in self._ratings:
            raise KernelError(
                code="ELO_DATA_SPARSE",
                message=(
                    f"{entrant_key!r} has no match in task class {task_class!r}; there is no "
                    "rating to report and a seed value is not a measurement"
                ),
                retryable=True,
                recommended_action="run matches in this class before asking for a rating",
                details={"entrantKey": entrant_key, "taskClass": task_class},
            )
        count = self._counts[index]
        return Rating(
            entrant=self._entrants[entrant_key],
            task_class=task_class,
            rating_centi=self._ratings[index],
            match_count=count,
            decided_count=self._decided[index],
            uncertainty_centi=uncertainty_centi(count, self._policy),
            provisional=count < self._policy.min_matches,
            min_matches=self._policy.min_matches,
        )

    def ratings(self, task_class: str) -> tuple[Rating, ...]:
        return tuple(
            self.rating(key, task_class)
            for key in self.keys(task_class)
        )

    def all_ratings(self) -> tuple[Rating, ...]:
        return tuple(
            rating
            for task_class in self.task_classes()
            for rating in self.ratings(task_class)
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "policy": self._policy.to_payload(),
            "ratings": [item.to_payload() for item in self.all_ratings()],
            "skippedMatches": [item.to_payload() for item in self._skipped],
            "skippedMatchCount": len(self._skipped),
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def rate(matches: Sequence[MatchRecord], policy: RatingPolicy | None = None) -> RatingBook:
    """Process a match sequence in the order given.

    The order is the caller's, and it matters — see :func:`order_sensitivity`.
    This function does not sort the input into a canonical order, because a
    canonical order would hide the path dependence rather than remove it.
    """

    book = RatingBook(policy)
    for match in matches:
        book.apply(match)
    return book


def ranking(book: RatingBook, task_class: str) -> Mapping[str, Any]:
    """Two lists, never one.

    Converged and provisional ratings are returned in separate sections with
    an explicit note.  Merging them into a single ordered list is the failure
    this function exists to prevent: a two-match entrant sitting at the top is
    read as the best model by everyone who does not check the footnote.
    """

    ratings = book.ratings(task_class)
    converged = sorted((item for item in ratings if not item.provisional),
                       key=lambda item: (-item.rating_centi, item.entrant.key))
    provisional = sorted((item for item in ratings if item.provisional),
                         key=lambda item: (-item.rating_centi, item.entrant.key))
    return {
        "taskClass": task_class,
        "converged": [item.to_payload() for item in converged],
        "provisional": [item.to_payload() for item in provisional],
        "comparable": len(converged) > 1,
        "note": (
            "provisional ratings are listed separately and are not comparable with "
            "converged ones; they have not yet met the policy's minimum match count"
        ),
        "orderToleranceCenti": ORDER_TOLERANCE_CENTI,
        "measured": bool(ratings),
    }


def compare(left: Rating, right: Rating) -> Mapping[str, Any]:
    """Rank two ratings, or refuse and say why.

    Three refusals, in order: different task classes (the numbers are not on
    one scale), either side provisional (one of them is not a rating yet), and
    overlapping intervals (the difference is inside the noise).  Each returns
    ``comparable: False`` with a reason rather than an ordering a caller would
    act on.
    """

    if left.task_class != right.task_class:
        return {
            "comparable": False,
            "reason": (
                f"{left.task_class!r} and {right.task_class!r} are different task classes; "
                "ratings are only comparable within a class"
            ),
            "better": None,
        }
    if left.provisional or right.provisional:
        provisional = sorted(
            item.entrant.key for item in (left, right) if item.provisional
        )
        return {
            "comparable": False,
            "reason": (
                f"{provisional} still provisional; a provisional rating is not a weaker "
                "version of a converged one, it is a different claim"
            ),
            "better": None,
            "provisional": provisional,
        }
    low_left, high_left = left.interval_centi
    low_right, high_right = right.interval_centi
    if low_left <= high_right and low_right <= high_left:
        return {
            "comparable": False,
            "reason": (
                f"intervals {[low_left, high_left]} and {[low_right, high_right]} overlap; "
                "the gap is inside the uncertainty"
            ),
            "better": None,
        }
    better = left if left.rating_centi > right.rating_centi else right
    return {
        "comparable": True,
        "better": better.entrant.key,
        "reason": (
            f"{better.entrant.key} leads by "
            f"{abs(left.rating_centi - right.rating_centi)} centi-rating with "
            "non-overlapping intervals"
        ),
    }


def aggregate(book: RatingBook, entrant_key: str,
              weights: Mapping[str, int] | None) -> Mapping[str, Any]:
    """Combine per-class ratings under a weighting the caller must supply.

    There is no default weighting and there will not be one.  A single number
    across refactoring and migration is a statement about which of them matters,
    and the module has no standing to make it: an omitted weighting raises
    ``CROSS_CLASS_AGGREGATION_REFUSED``.  A weight naming a class the entrant
    never played raises ``SEGMENT_BIAS``, because the aggregate would otherwise
    be part measurement and part invention.
    """

    if not weights:
        raise KernelError(
            code="CROSS_CLASS_AGGREGATION_REFUSED",
            message=(
                f"no weighting supplied for {entrant_key!r}; a cross-class rating is a "
                "judgement about which classes matter and the kernel will not make it"
            ),
            retryable=False,
            recommended_action="supply an explicit integer weight per task class",
            details={"entrantKey": entrant_key,
                     "availableClasses": list(book.task_classes())},
        )
    played = {
        task_class for task_class in book.task_classes()
        if entrant_key in book.keys(task_class)
    }
    missing = sorted(set(weights) - played)
    if missing:
        raise KernelError(
            code="SEGMENT_BIAS",
            message=(
                f"{entrant_key!r} has no matches in {missing} but the weighting asks for "
                "them; the aggregate would be part measurement and part invention"
            ),
            retryable=False,
            recommended_action="run matches in the missing classes or drop them from the weights",
            details={"entrantKey": entrant_key, "missingClasses": missing},
        )
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise KernelError(
            code="MALFORMED_INPUT",
            message="aggregate weights must sum to a positive integer",
            recommended_action="supply positive integer weights",
        )
    contributions = []
    weighted = 0
    provisional_classes = []
    for task_class in sorted(weights):
        weight = require_int(weights[task_class], f"weights[{task_class}]", minimum=0)
        rating = book.rating(entrant_key, task_class)
        weighted += rating.rating_centi * weight
        if rating.provisional:
            provisional_classes.append(task_class)
        contributions.append({
            "taskClass": task_class,
            "weight": weight,
            "ratingCenti": rating.rating_centi,
            "provisional": rating.provisional,
        })
    return {
        "entrantKey": entrant_key,
        "aggregateCenti": _div_round(weighted, total_weight),
        "weights": {key: int(value) for key, value in sorted(weights.items())},
        "totalWeight": total_weight,
        "contributions": contributions,
        "provisionalClasses": provisional_classes,
        "measured": True,
        "note": (
            "this aggregate is only meaningful under the supplied weighting; it is not a "
            "global rating"
        ),
    }


def order_sensitivity(matches: Sequence[MatchRecord], policy: RatingPolicy,
                      orders: Sequence[Sequence[int]]) -> Mapping[str, Any]:
    """Measure how far the ratings move when the same matches arrive differently.

    The orderings are supplied by the caller rather than generated randomly, so
    the report is reproducible.  The result states the largest deviation seen,
    the declared tolerance, and whether the first is inside the second — which
    is the only honest form of the sentence "Elo is order independent".
    """

    if not orders:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="order_sensitivity needs at least one ordering to compare against",
            recommended_action="supply the permutations you care about",
        )
    baseline = rate(matches, policy)
    worst = 0
    worst_key = ""
    for order in orders:
        if sorted(order) != list(range(len(matches))):
            raise KernelError(
                code="MALFORMED_INPUT",
                message="each ordering must be a permutation of the match indices",
                recommended_action="supply complete permutations",
            )
        candidate = rate([matches[index] for index in order], policy)
        for rating in baseline.all_ratings():
            other = candidate.rating(rating.entrant.key, rating.task_class)
            deviation = abs(other.rating_centi - rating.rating_centi)
            if deviation > worst:
                worst = deviation
                worst_key = f"{rating.task_class}/{rating.entrant.key}"
    return {
        "orderingsCompared": len(orders),
        "maxDeviationCenti": worst,
        "worstEntrant": worst_key,
        "toleranceCenti": ORDER_TOLERANCE_CENTI,
        "withinTolerance": worst <= ORDER_TOLERANCE_CENTI,
        "measured": True,
        "note": (
            "Elo is path dependent; this is the measured spread over the supplied "
            "orderings, not a proof of order independence"
        ),
    }


def drift_alerts(book: RatingBook, previous: RatingBook | None,
                 policy: RatingPolicy) -> tuple[Mapping[str, Any], ...]:
    """Report ratings that moved too far, and versions that reset the evidence.

    Two alert kinds, both deliberately non-fatal here: the caller decides what
    a drift means.  ``version-change`` fires when a contestant appears under a
    new version, and says explicitly that the prior rating was *not* carried —
    a silent carry-over is how two hundred matches of evidence get attributed
    to a build that never ran them.
    """

    alerts: list[Mapping[str, Any]] = []
    if previous is None:
        return ()
    for rating in book.all_ratings():
        index_present = rating.entrant.key in previous.keys(rating.task_class)
        if index_present:
            before = previous.rating(rating.entrant.key, rating.task_class)
            movement = rating.rating_centi - before.rating_centi
            if abs(movement) > policy.drift_threshold_centi:
                alerts.append({
                    "alert": "rating-drift",
                    "code": "RATING_DRIFT",
                    "entrantKey": rating.entrant.key,
                    "taskClass": rating.task_class,
                    "fromCenti": before.rating_centi,
                    "toCenti": rating.rating_centi,
                    "movementCenti": movement,
                    "thresholdCenti": policy.drift_threshold_centi,
                    "explanation": (
                        f"{rating.entrant.key} moved {movement} centi-rating in "
                        f"{rating.task_class}, past the {policy.drift_threshold_centi} "
                        "threshold"
                    ),
                })
            continue
        prior_versions = sorted(
            key for key in previous.keys(rating.task_class)
            if key.split(":")[0] == rating.entrant.contestant_id
        )
        if prior_versions:
            alerts.append({
                "alert": "version-change",
                "code": "RATING_DRIFT",
                "entrantKey": rating.entrant.key,
                "taskClass": rating.task_class,
                "priorVersions": prior_versions,
                "ratingCarriedOver": False,
                "provisional": rating.provisional,
                "explanation": (
                    f"{rating.entrant.contestant_id} appears at version "
                    f"{rating.entrant.version}; the prior rating for {prior_versions} was "
                    "not carried over because a new build is a new entity"
                ),
            })
    return tuple(alerts)


def routing_recommendation(book: RatingBook, task_class: str, *, risk: str,
                           cost: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any]:
    """Name a model for a task class, or refuse with the reason.

    Quality and cost are returned as separate fields and are never combined:
    the router decides the trade-off, and a blended "value" score here would
    make that decision invisibly.  A high-risk class demands ``high_risk_min_matches``
    of evidence, and a provisional leader raises ``ROUTING_RECOMMENDATION_UNSAFE``
    rather than being returned with a caveat nobody reads.
    """

    if risk not in {"low", "standard", "high"}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown risk level {risk!r}",
            recommended_action="use 'low', 'standard' or 'high'",
        )
    ratings = book.ratings(task_class)
    if not ratings:
        raise KernelError(
            code="ELO_DATA_SPARSE",
            message=f"no rating exists for task class {task_class!r}",
            retryable=True,
            recommended_action="run matches in this class before routing on its ratings",
            details={"taskClass": task_class},
        )
    leader = sorted(ratings, key=lambda item: (-item.rating_centi, item.entrant.key))[0]
    required = (book.policy.high_risk_min_matches if risk == "high"
                else book.policy.min_matches)
    if leader.match_count < required:
        raise KernelError(
            code="ROUTING_RECOMMENDATION_UNSAFE",
            message=(
                f"the leader in {task_class!r} ({leader.entrant.key}) has "
                f"{leader.match_count} match(es); a {risk}-risk route requires {required}"
            ),
            retryable=True,
            recommended_action="collect more matches or route on a converged rating",
            details={
                "taskClass": task_class,
                "entrantKey": leader.entrant.key,
                "matchCount": leader.match_count,
                "requiredMatches": required,
                "risk": risk,
            },
        )
    entry = cost.get(leader.entrant.key)
    return {
        "taskClass": task_class,
        "risk": risk,
        "recommended": leader.entrant.key,
        "ratingCenti": leader.rating_centi,
        "uncertaintyCenti": leader.uncertainty_centi,
        "intervalCenti": list(leader.interval_centi),
        "matchCount": leader.match_count,
        "requiredMatches": required,
        "costMicros": None if entry is None else int(entry.get("costMicros")),
        "p50LatencyMs": None if entry is None else int(entry.get("p50LatencyMs")),
        "costMeasured": entry is not None,
        "note": (
            "quality and cost are reported separately; this function does not blend them "
            "into a single score"
        ),
    }


def record_rating_update(events: EventStore, stream_id: str, book: RatingBook, *,
                         fencing_token: int) -> Mapping[str, Any]:
    """Append the rating table to its stream, once, under a fencing token."""

    require_int(fencing_token, "fencing_token", minimum=1)
    event = events.append(stream_id, book.to_payload(), idempotency_key=book.digest,
                          fencing_token=fencing_token)
    return {
        "sequence": event.sequence,
        "eventId": event.event_id,
        "hashChain": event.hash_chain,
        "bookDigest": book.digest,
    }


# --- registry entry point ----------------------------------------------------

_REQUEST_FIELDS = frozenset({
    "arena_results", "production_evals", "task_taxonomy", "model_cost_latency",
    "rating_policy",
})


def _decode_entrant(payload: Any, field_name: str) -> Entrant:
    mapping = require_mapping(payload, field_name)
    reject_unknown_fields(mapping, {"contestantId", "version"}, field_name=field_name)
    return Entrant(
        contestant_id=require_identifier(mapping.get("contestantId"),
                                         f"{field_name}.contestantId"),
        version=require_identifier(mapping.get("version"), f"{field_name}.version"),
    )


def _decode_match(payload: Mapping[str, Any], *, source: str, snapshot: str,
                  classes: Sequence[str]) -> MatchRecord:
    reject_unknown_fields(
        payload,
        {"matchId", "taskClass", "a", "b", "result", "repoSnapshotSha", "reason",
         "evidenceIds"},
        field_name="match",
    )
    result = require_str(payload.get("result"), "match.result", max_length=32)
    if result not in {item.value for item in MatchResultValue}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown match result {result!r}",
            recommended_action=f"use one of {sorted(v.value for v in MatchResultValue)}",
        )
    task_class = require_identifier(payload.get("taskClass"), "match.taskClass")
    if task_class not in classes:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=(
                f"task class {task_class!r} is not in the declared taxonomy "
                f"{sorted(classes)}; an unknown class is denied, not invented"
            ),
            retryable=False,
            recommended_action="declare the class in task_taxonomy.classes",
            details={"taskClass": task_class},
        )
    match_snapshot = str(payload.get("repoSnapshotSha", "") or "")
    if match_snapshot and match_snapshot != snapshot:
        raise KernelError(
            code="STALE_SNAPSHOT",
            message=(
                f"match {payload.get('matchId')!r} was produced against snapshot "
                f"{match_snapshot} but the result set is pinned to {snapshot}"
            ),
            retryable=False,
            recommended_action="re-run the match against the pinned snapshot",
        )
    return MatchRecord(
        match_id=require_identifier(payload.get("matchId"), "match.matchId"),
        task_class=task_class,
        a=_decode_entrant(payload.get("a"), "match.a"),
        b=_decode_entrant(payload.get("b"), "match.b"),
        result=MatchResultValue(result),
        source=source,
        repo_snapshot_sha=match_snapshot or snapshot,
        reason=str(payload.get("reason", "")),
        evidence_ids=require_str_seq(payload.get("evidenceIds", ()), "match.evidenceIds"),
    )


@register("repository-model-elo")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point.

    Rates arena and production matches per task class, reports the interval and
    the provisional flag on every entry, and returns routing recommendations
    only where the evidence supports them.  A class whose leader is still
    provisional produces a recorded refusal in ``routing_recommendations``
    rather than a recommendation with a footnote.
    """

    reject_unknown_fields(request, _REQUEST_FIELDS, field_name="repository-model-elo request")
    for name in ("arena_results", "task_taxonomy"):
        if name not in request:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"{name} is required",
                recommended_action=f"supply {name}",
            )

    taxonomy = require_mapping(request.get("task_taxonomy"), "task_taxonomy")
    reject_unknown_fields(taxonomy, {"classes", "highRisk"}, field_name="task_taxonomy")
    classes = require_str_seq(taxonomy.get("classes", ()), "task_taxonomy.classes",
                              allow_empty=False)
    high_risk = require_str_seq(taxonomy.get("highRisk", ()), "task_taxonomy.highRisk")
    unknown_risk = sorted(set(high_risk) - set(classes))
    if unknown_risk:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"highRisk names undeclared classes {unknown_risk}",
            recommended_action="declare every high-risk class in classes",
        )

    policy_payload = request.get("rating_policy")
    if policy_payload is None:
        policy = RatingPolicy()
    else:
        policy_payload = require_mapping(policy_payload, "rating_policy")
        reject_unknown_fields(
            policy_payload,
            {"kFactorCenti", "seedCenti", "minMatches", "baseUncertaintyCenti",
             "minUncertaintyCenti", "driftThresholdCenti", "highRiskMinMatches"},
            field_name="rating_policy",
        )
        defaults = RatingPolicy()
        policy = RatingPolicy(
            k_factor_centi=require_int(policy_payload.get("kFactorCenti",
                                                          defaults.k_factor_centi),
                                       "rating_policy.kFactorCenti", minimum=1),
            seed_centi=require_int(policy_payload.get("seedCenti", defaults.seed_centi),
                                   "rating_policy.seedCenti", minimum=0),
            min_matches=require_int(policy_payload.get("minMatches", defaults.min_matches),
                                    "rating_policy.minMatches", minimum=1),
            base_uncertainty_centi=require_int(
                policy_payload.get("baseUncertaintyCenti", defaults.base_uncertainty_centi),
                "rating_policy.baseUncertaintyCenti", minimum=1),
            min_uncertainty_centi=require_int(
                policy_payload.get("minUncertaintyCenti", defaults.min_uncertainty_centi),
                "rating_policy.minUncertaintyCenti", minimum=1),
            drift_threshold_centi=require_int(
                policy_payload.get("driftThresholdCenti", defaults.drift_threshold_centi),
                "rating_policy.driftThresholdCenti", minimum=1),
            high_risk_min_matches=require_int(
                policy_payload.get("highRiskMinMatches", defaults.high_risk_min_matches),
                "rating_policy.highRiskMinMatches", minimum=1),
        )

    arena_results = require_mapping(request.get("arena_results"), "arena_results")
    reject_unknown_fields(arena_results, {"repoSnapshotSha", "matches", "priorMatches"},
                          field_name="arena_results")
    snapshot = require_str(arena_results.get("repoSnapshotSha"),
                           "arena_results.repoSnapshotSha", max_length=128)
    matches = [
        _decode_match(require_mapping(item, "matches[]"), source="arena", snapshot=snapshot,
                      classes=classes)
        for item in arena_results.get("matches", ())
    ]
    prior_matches = [
        _decode_match(require_mapping(item, "priorMatches[]"), source="arena",
                      snapshot=snapshot, classes=classes)
        for item in arena_results.get("priorMatches", ())
    ]

    production = request.get("production_evals")
    if production is not None:
        production = require_mapping(production, "production_evals")
        reject_unknown_fields(production, {"matches"}, field_name="production_evals")
        matches.extend(
            _decode_match(require_mapping(item, "production matches[]"), source="production",
                          snapshot=snapshot, classes=classes)
            for item in production.get("matches", ())
        )
    if not matches:
        raise KernelError(
            code="ELO_DATA_SPARSE",
            message="no match was supplied; there is nothing to rate",
            retryable=True,
            recommended_action="supply at least one match result",
        )

    cost_entries: dict[str, Mapping[str, Any]] = {}
    cost_payload = request.get("model_cost_latency")
    if cost_payload is not None:
        cost_payload = require_mapping(cost_payload, "model_cost_latency")
        reject_unknown_fields(cost_payload, {"entries"}, field_name="model_cost_latency")
        for item in cost_payload.get("entries", ()):
            entry = require_mapping(item, "model_cost_latency.entries[]")
            reject_unknown_fields(entry, {"key", "costMicros", "p50LatencyMs"},
                                  field_name="model_cost_latency.entry")
            key = require_str(entry.get("key"), "entry.key", max_length=256)
            cost_entries[key] = {
                "costMicros": require_int(entry.get("costMicros"), "entry.costMicros",
                                          minimum=0),
                "p50LatencyMs": require_int(entry.get("p50LatencyMs"), "entry.p50LatencyMs",
                                            minimum=0),
            }

    book = rate(matches, policy)
    previous = rate(prior_matches, policy) if prior_matches else None
    alerts = drift_alerts(book, previous, policy)

    rankings = [ranking(book, task_class) for task_class in book.task_classes()]
    recommendations: list[Mapping[str, Any]] = []
    for task_class in book.task_classes():
        risk = "high" if task_class in high_risk else "standard"
        try:
            recommendations.append(routing_recommendation(book, task_class, risk=risk,
                                                          cost=cost_entries))
        except KernelError as exc:
            if exc.code not in {"ROUTING_RECOMMENDATION_UNSAFE", "ELO_DATA_SPARSE"}:
                raise
            recommendations.append({
                "taskClass": task_class,
                "risk": risk,
                "recommended": None,
                "refused": True,
                "code": exc.code,
                "reason": exc.message,
                "measured": True,
            })

    segments = [
        {
            "taskClass": task_class,
            "entrantCount": len(book.keys(task_class)),
            "ratings": [item.to_payload() for item in book.ratings(task_class)],
            "converged": sum(1 for item in book.ratings(task_class) if not item.provisional),
            "provisional": sum(1 for item in book.ratings(task_class) if item.provisional),
        }
        for task_class in book.task_classes()
    ]
    uncovered = sorted(set(classes) - set(book.task_classes()))

    return {
        "elo_ratings": {
            **book.to_payload(),
            "bookDigest": book.digest,
            "ratedMatches": sum(1 for item in matches if item.is_rated),
            "undecidedMatches": sum(1 for item in matches if not item.is_rated),
            "sources": {
                "arena": sum(1 for item in matches if item.source == "arena"),
                "production": sum(1 for item in matches if item.source == "production"),
            },
        },
        "confidence_intervals": {
            "orderToleranceCenti": ORDER_TOLERANCE_CENTI,
            "entries": [
                {
                    "entrantKey": item.entrant.key,
                    "taskClass": item.task_class,
                    "ratingCenti": item.rating_centi,
                    "uncertaintyCenti": item.uncertainty_centi,
                    "intervalCenti": list(item.interval_centi),
                    "provisional": item.provisional,
                    "matchCount": item.match_count,
                }
                for item in book.all_ratings()
            ],
            "note": (
                "Elo is order dependent; ratings from the same match set in a different "
                f"order may differ by up to {ORDER_TOLERANCE_CENTI} centi-rating"
            ),
        },
        "segment_ratings": {
            "rankings": rankings,
            "segments": segments,
            "declaredClasses": list(classes),
            "uncoveredClasses": uncovered,
            "aggregationPolicy": (
                "no cross-class aggregate is produced without an explicit caller-supplied "
                "weighting; call aggregate() with integer weights"
            ),
        },
        "routing_recommendations": recommendations,
        "drift_alerts": [dict(item) for item in alerts],
        "evidenceIds": sorted({item for match in matches for item in match.evidence_ids}),
    }
