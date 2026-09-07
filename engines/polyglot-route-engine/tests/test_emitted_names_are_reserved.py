"""Every identifier the emitter can write into a target file must be reserved
by that language's identifier policy.

The two are separate tables maintained by hand, and nothing tied them together.
Kotlin drifted apart exactly the way that invites: the policy reserved
`elmosNonZeroDouble`, the emitter declared `elmosNonZero`. In a language whose
migrated functions and emitted helpers share one top-level namespace, that gap
is a redeclaration error waiting for a source function to be named the wrong
thing -- and the identifier planner, whose entire job is to make that
impossible, would have allowed it.

The check is deliberately about *names*, not about which helper is emitted
when: reserving a name the emitter no longer writes costs one avoidable rename,
while failing to reserve one it does write costs a build.
"""

from __future__ import annotations

import pytest

from elmos_polyglot_route import identifier_hygiene as hygiene
from elmos_polyglot_route.emitter import _CHECKED_INTEGER_CALL, _FLOAT_NON_ZERO_GUARD
from elmos_polyglot_route.models import Language


def _reserved(language: Language, call: str) -> bool:
    """A qualified call is covered if either half is reserved.

    `Migrated.elmosCheckedDiv` is unreachable once `Migrated` is taken, and
    `Math.addExact` once `Math` is; an unqualified `elmosCheckedDiv` needs the
    bare name itself.
    """
    forbidden = hygiene._FORBIDDEN[language]
    segments = call.split(".")
    return segments[0] in forbidden or segments[-1] in forbidden


def _languages() -> list[Language]:
    # `_FORBIDDEN` is the set of languages that have an identifier policy at
    # all; a language without one cannot be a target and has nothing to check.
    return sorted(hygiene._FORBIDDEN)


@pytest.mark.parametrize("language", _languages())
def test_checked_integer_call_names_are_reserved(language: Language) -> None:
    for operator, (call, _helper_keys) in _CHECKED_INTEGER_CALL.get(language, {}).items():
        assert _reserved(language, call), (
            f"{language} {operator} emits {call}, which the policy allows as a source name"
        )


@pytest.mark.parametrize("language", _languages())
def test_float_divisor_guard_names_are_reserved(language: Language) -> None:
    entry = _FLOAT_NON_ZERO_GUARD.get(language)
    if entry is None:
        return
    call, _helper_key = entry
    assert _reserved(language, call), f"{language} guards float division with {call}, which the policy allows"


def test_every_language_with_an_identifier_policy_has_a_dialect() -> None:
    # The two tables are indexed by the same key and read together on every
    # plan; a language in one and not the other raises KeyError at planning
    # time rather than failing closed.
    assert set(hygiene._FORBIDDEN) == set(hygiene._DIALECT)
    assert set(hygiene._RESERVED) == set(hygiene._DIALECT)
