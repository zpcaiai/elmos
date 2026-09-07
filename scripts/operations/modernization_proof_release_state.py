"""Fail-closed state contract for Batch 105-108 external release boundaries."""

from __future__ import annotations

from collections.abc import Mapping


EXTERNAL_BOUNDARIES = (
    "REAL_CLOUD_PROVIDER",
    "SCM_DRAFT_PULL_REQUEST",
    "CUSTOMER_ACCEPTANCE",
    "INDEPENDENT_REVIEW",
    "PRODUCTION_DEPLOYMENT",
    "EXTERNAL_CERTIFICATION",
)
NOT_RUN = "NOT_RUN"
BLOCKED = "BLOCKED"
FAILED = "FAILED"
EXECUTED_AWAITING_VERIFICATION = "EXECUTED_AWAITING_INDEPENDENT_VERIFICATION"
INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"
ALLOWED_STATES = frozenset(
    {
        NOT_RUN,
        BLOCKED,
        FAILED,
        EXECUTED_AWAITING_VERIFICATION,
        INDEPENDENTLY_VERIFIED,
    }
)


class ReleaseStateFailure(ValueError):
    """The supplied external release state violates the exact contract."""


def initial_external_boundaries() -> dict[str, str]:
    """Return a new, exact, fail-closed boundary map."""
    return {boundary: NOT_RUN for boundary in EXTERNAL_BOUNDARIES}


def validate_external_boundaries(states: Mapping[str, object]) -> dict[str, str]:
    """Reject missing, extra, unknown, or non-string boundary states."""
    actual = set(states)
    expected = set(EXTERNAL_BOUNDARIES)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ReleaseStateFailure(
            f"external boundary keys are not exact; missing={missing}, extra={extra}"
        )
    normalized: dict[str, str] = {}
    for boundary in EXTERNAL_BOUNDARIES:
        state = states[boundary]
        if not isinstance(state, str) or state not in ALLOWED_STATES:
            raise ReleaseStateFailure(f"unsupported state for {boundary}")
        normalized[boundary] = state
    return normalized


def record_observed_execution(
    states: Mapping[str, object], *, boundary: str
) -> dict[str, str]:
    """Record a real execution without pretending that it was independently verified."""
    normalized = validate_external_boundaries(states)
    if boundary not in EXTERNAL_BOUNDARIES:
        raise ReleaseStateFailure("unknown external boundary")
    current = normalized[boundary]
    if current == INDEPENDENTLY_VERIFIED:
        raise ReleaseStateFailure(
            "an observation cannot downgrade independent verification"
        )
    normalized[boundary] = EXECUTED_AWAITING_VERIFICATION
    return normalized


def validate_observation_transition(
    before: Mapping[str, object], after: Mapping[str, object], *, boundary: str
) -> dict[str, str]:
    """Allow exactly one execution observation and no unrelated state edits."""
    expected = record_observed_execution(before, boundary=boundary)
    normalized_after = validate_external_boundaries(after)
    if normalized_after != expected:
        raise ReleaseStateFailure(
            "external observation changed an unauthorized boundary"
        )
    return normalized_after
