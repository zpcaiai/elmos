"""The capability probe, and the distinction it exists to protect.

Reading code to answer "does this engine support X" produced three wrong
answers in one afternoon, all the same way: a rejection code in an intermediate
layer was read as the system's boundary. `discover_unit()` refuses a
multi-function file; `discover_repository()` then splits that same result into
one READY unit per function. Both are real; only the second is the boundary.

The probe never infers -- it calls the real entry point. These tests protect
the part that makes its output trustworthy: a machine without the pinned
toolchain must produce `NOT_PROBED`, never a capability claim.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(_TOOLS))

import capability_probe  # noqa: E402

_VOCABULARY = ("SUPPORTED", "REJECTED:", "NOT_PROBED:", "BY_DESIGN:", "ERROR:")

#: OPT-IN, AND THAT IS A CORRECTION OF MY OWN MISTAKE.
#:
#: These tests call `capability_probe.run()`, which is not a unit under test --
#: it executes the real analyzer, emitter and toolchain of every language in
#: the matrix. Putting that on the default suite path was wrong three ways: it
#: costs minutes, its result depends on which toolchains this machine happens
#: to have, and it can wedge the whole run indefinitely. It did: a full suite
#: sat at 0% CPU for over ten minutes inside this file, blocked in `poll()` on
#: a pipe whose write end an orphaned build daemon still held. A suite that can
#: hang forever cannot gate anything, and a diagnostic that runs every
#: toolchain does not belong in the same breath as a unit test.
#:
#: The probe itself is unchanged and still the answer to "what does this engine
#: actually accept" -- run it with `make capability-probe`, and run these
#: assertions over it with `make capability-probe-tests`.
_PROBE_TESTS_ENABLED = os.environ.get("ELMOS_CAPABILITY_PROBE_TESTS") == "1"

requires_real_probe = pytest.mark.skipif(
    not _PROBE_TESTS_ENABLED,
    reason="runs every language's real toolchain; set ELMOS_CAPABILITY_PROBE_TESTS=1 (make capability-probe-tests)",
)


def _report() -> dict:
    if not hasattr(_report, "cached"):
        _report.cached = capability_probe.run()  # type: ignore[attr-defined]
    return _report.cached  # type: ignore[attr-defined]


@requires_real_probe
def test_every_verdict_uses_the_closed_vocabulary() -> None:
    report = _report()
    for section in ("emission", "module_enumeration", "lifting", "subset_boundary"):
        for key, verdict in report[section].items():
            assert verdict.startswith(_VOCABULARY), f"{section}.{key} = {verdict}"


@requires_real_probe
def test_no_probe_reports_an_internal_error() -> None:
    """An `ERROR:` row is a probe defect, not a finding, and must never ship."""
    report = _report()
    errors = [
        f"{section}.{key}={verdict}"
        for section in ("emission", "module_enumeration", "lifting", "subset_boundary")
        for key, verdict in report[section].items()
        if verdict.startswith("ERROR:")
    ]
    assert errors == []


@requires_real_probe
def test_emission_is_conclusive_on_every_machine() -> None:
    """Emission is pure Python, so a `NOT_PROBED` there would be a probe bug.

    This is what makes the emission row usable as an answer rather than as an
    instruction to re-run somewhere else.
    """
    report = _report()
    for language, verdict in report["emission"].items():
        assert not verdict.startswith("NOT_PROBED"), f"{language} = {verdict}"


def test_a_missing_toolchain_is_never_reported_as_a_capability_gap() -> None:
    """The single distinction the probe exists to keep.

    Collapsing "cannot be probed here" into "not supported" is the same class
    of mistake as collapsing an intermediate rejection into a boundary.
    """
    assert capability_probe._verdict(
        lambda: (_ for _ in ()).throw(
            capability_probe.RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:swiftc")
        )
    ) == "NOT_PROBED:EXACT_TOOLCHAIN_UNAVAILABLE"

    assert capability_probe._verdict(
        lambda: (_ for _ in ()).throw(
            capability_probe.RouteError("PYTHON_UNSUPPORTED_STATEMENT:While")
        )
    ) == "REJECTED:PYTHON_UNSUPPORTED_STATEMENT"


@pytest.mark.parametrize("language", ["kotlin", "react", "flutter"])
@requires_real_probe
def test_new_active_languages_are_emission_targets(language: str) -> None:
    assert _report()["emission"][language] == "SUPPORTED"


@pytest.mark.parametrize(
    "construct",
    ["call", "assignment", "exception", "loop", "attribute_access", "subscript", "async"],
)
@requires_real_probe
def test_the_ir_has_no_representation_for_these_constructs(construct: str) -> None:
    """Structural, not policy: the whitelist is name / literal / binary / return / if.

    Every widening item in the backlog rests on this row being accurate, so it
    is asserted from an executed probe rather than from reading `models.py`.
    """
    assert _report()["subset_boundary"][construct].startswith("REJECTED:")


@requires_real_probe
def test_a_class_beside_the_function_does_not_block_lifting() -> None:
    """File closure is enumeration's question, not the lifter's.

    The first run of this probe labelled the same fixture `class` and reported
    SUPPORTED, which read as "objects work". They do not -- `attribute_access`
    above is the IR question, and it is rejected.
    """
    assert _report()["subset_boundary"]["class_declared_beside_function"] == "SUPPORTED"


def test_an_unregistered_toolchain_is_a_boundary_not_a_missing_machine() -> None:
    """`UNREGISTERED` is the one `EXACT_TOOLCHAIN_*` code that is machine-independent.

    Every other one means "this box lacks the compiler". `UNREGISTERED` means
    the engine has no pinned entry for the language at all, so it cannot be a
    source anywhere -- letting it sit in the "re-run elsewhere" bucket would
    hide a real gap behind an instruction nobody could ever satisfy.
    """
    assert capability_probe._verdict(
        lambda: (_ for _ in ()).throw(
            capability_probe.RouteError("EXACT_TOOLCHAIN_UNREGISTERED:flutter")
        )
    ) == "REJECTED:EXACT_TOOLCHAIN_UNREGISTERED"

    assert capability_probe._verdict(
        lambda: (_ for _ in ()).throw(
            capability_probe.RouteError("EXACT_TOOLCHAIN_PLATFORM_MISMATCH:go")
        )
    ) == "NOT_PROBED:EXACT_TOOLCHAIN_PLATFORM_MISMATCH"


@requires_real_probe
def test_no_cell_is_left_unprobed_for_want_of_a_fixture() -> None:
    """"Nobody wrote a fixture" and "there is no frontend" must not share a cell.

    The first run of this probe reported NO_FIXTURE for kotlin, react and
    flutter, which read as a capability gap and was really a gap in the probe.
    Every declared language now has a fixture, so a cell can only say what the
    engine actually answered.
    """
    report = _report()
    for section in ("module_enumeration", "lifting"):
        for language, verdict in report[section].items():
            assert "NO_FIXTURE" not in verdict, f"{section}.{language} = {verdict}"


@requires_real_probe
def test_the_declaration_cross_check_reports_its_own_applicability() -> None:
    """A partial run must decline to compare rather than report a mismatch."""
    check = _report()["declaration_cross_check"]
    assert check["status"] in {"MATCH", "MISMATCH", "NOT_PROBED:INVENTORY_ABSENT", "NOT_PROBED:INCOMPLETE_RUN"}
    if check["status"] == "MATCH":
        assert check["declared_route_count"] == check["executed_bidirectional_routes"]
        assert check["declared_route_count"] == 156
