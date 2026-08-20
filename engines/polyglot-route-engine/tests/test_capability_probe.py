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

import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(_TOOLS))

import capability_probe  # noqa: E402

_VOCABULARY = ("SUPPORTED", "REJECTED:", "NOT_PROBED:", "BY_DESIGN:", "ERROR:")


def _report() -> dict:
    if not hasattr(_report, "cached"):
        _report.cached = capability_probe.run()  # type: ignore[attr-defined]
    return _report.cached  # type: ignore[attr-defined]


def test_every_verdict_uses_the_closed_vocabulary() -> None:
    report = _report()
    for section in ("emission", "module_enumeration", "lifting", "subset_boundary"):
        for key, verdict in report[section].items():
            assert verdict.startswith(_VOCABULARY), f"{section}.{key} = {verdict}"


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


@pytest.mark.parametrize("language", ["react", "flutter"])
def test_a_language_with_no_identifier_policy_is_not_an_emission_target(language: str) -> None:
    assert _report()["emission"][language].startswith("REJECTED:IDENTIFIER_POLICY_UNSUPPORTED")


def test_kotlin_is_an_emission_target() -> None:
    assert _report()["emission"]["kotlin"] == "SUPPORTED"


@pytest.mark.parametrize(
    "construct",
    ["call", "assignment", "exception", "loop", "attribute_access", "subscript", "async"],
)
def test_the_ir_has_no_representation_for_these_constructs(construct: str) -> None:
    """Structural, not policy: the whitelist is name / literal / binary / return / if.

    Every widening item in the backlog rests on this row being accurate, so it
    is asserted from an executed probe rather than from reading `models.py`.
    """
    assert _report()["subset_boundary"][construct].startswith("REJECTED:")


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


def test_the_declaration_cross_check_reports_its_own_applicability() -> None:
    """A partial run must decline to compare rather than report a mismatch."""
    check = _report()["declaration_cross_check"]
    assert check["status"] in {"MATCH", "MISMATCH", "NOT_PROBED:INVENTORY_ABSENT", "NOT_PROBED:INCOMPLETE_RUN"}
    if check["status"] == "MATCH":
        assert check["declared_limited_route_count"] == check["executed_bidirectional_routes"]
