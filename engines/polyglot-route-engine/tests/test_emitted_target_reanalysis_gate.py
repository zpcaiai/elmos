"""`native.analyze`'s two language gates: who may be lifted at all, and whose
emitted output may be re-lifted.

Neither had a test. That is how deprecating javascript could move a whole
language from "relifts fine" to "raises on every call" without one assertion
naming the cause -- 15 `test_javascript_node` failures all pointed at their own
subject instead of at the one line responsible.

The first draft of this file got the boundary wrong in the other direction: it
assumed the relift gate was what refused kotlin/react/flutter. It was not. They
reached `exact_toolchain` and died there, so the error a caller saw was
`EXACT_TOOLCHAIN_KOTLIN_NOT_PINNED` -- naming a fix that would not have helped.
That is now refused up front and by its established name.
"""

from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest

from elmos_polyglot_route.models import (
    DEPRECATED_LANGUAGES,
    PENDING_ANALYZER_LANGUAGES,
    ROUTED_LANGUAGES,
    Language,
    RouteError,
)
from elmos_polyglot_route.native import NATIVE_RELIFTABLE_LANGUAGES, analyze

_RELIFT_GATE = "EMITTED_TARGET_REANALYSIS_UNSUPPORTED"


def _subject(tmp_path: Path) -> Path:
    # Content is irrelevant: both gates are reached before any parse.
    path = tmp_path / "subject.txt"
    path.write_text("// emitted\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("emitted_target", [False, True])
@pytest.mark.parametrize("language", PENDING_ANALYZER_LANGUAGES)
def test_a_language_without_an_analyzer_is_refused_before_its_toolchain(
    language: Language, emitted_target: bool, tmp_path: Path
) -> None:
    """The refusal must name the analyzer, not the pin.

    `EXACT_TOOLCHAIN_KOTLIN_NOT_PINNED` told the caller to run the pinning
    script; doing so would have produced a pinned toolchain and the same
    inability to lift. `SOURCE_ANALYZER_NOT_IMPLEMENTED` is what
    `SemanticIR.from_mapping` already calls this state.
    """
    with pytest.raises(RouteError) as raised:
        analyze(_subject(tmp_path), language, "subject", emitted_target=emitted_target)
    assert str(raised.value) == f"SOURCE_ANALYZER_NOT_IMPLEMENTED:{language}"


@pytest.mark.parametrize("language", DEPRECATED_LANGUAGES)
def test_a_deprecated_language_keeps_its_relift_capability(language: Language, tmp_path: Path) -> None:
    # It may still fail -- a text file is not valid javascript, and the helper
    # verification ahead of the parse has its own opinions. What it must not do
    # is fail *at the relift gate*, because that would mean archived evidence
    # for the language can no longer be re-derived.
    try:
        analyze(_subject(tmp_path), language, "subject", emitted_target=True)
    except RouteError as error:
        assert not str(error).startswith(_RELIFT_GATE), str(error)


def test_the_relift_gate_is_unreachable_by_construction() -> None:
    """It is a backstop, and this is the assertion that says so out loud.

    Every declared language is either routed or deprecated, so the gate cannot
    fire today. It exists for the one arrangement that would otherwise fall
    through to a dispatch chain with no branch for the language: a new member
    added to the `Language` literal and placed in neither set. When this
    assertion fails, the gate has become live -- that is the signal to give the
    new language a home, not to delete the check.
    """
    declared = set(get_args(Language))
    assert declared == set(ROUTED_LANGUAGES) | set(DEPRECATED_LANGUAGES)


def test_the_native_relift_set_is_disjoint_from_the_pending_set() -> None:
    # Claiming both would mean a language relifts emitted output through an
    # analyzer that does not exist yet.
    assert not NATIVE_RELIFTABLE_LANGUAGES & set(PENDING_ANALYZER_LANGUAGES)
