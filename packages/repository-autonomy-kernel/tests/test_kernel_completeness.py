"""Whole-build assertions.

A partial build must be *detectable*.  Every other test file exercises one
capability in isolation, which means a capability that was never written passes
every test that exists — by not existing.  These assertions are the ones that
notice.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from elmos_autonomy_kernel import _bind_all_capabilities
from elmos_autonomy_kernel.contracts import Status, canonical_json
from elmos_autonomy_kernel.errors import CODES, Category
from elmos_autonomy_kernel.registry import DESCRIPTORS, bound_skills, dispatch, unbound_skills

SRC = str(Path(__file__).resolve().parents[1] / "src")


@pytest.fixture(scope="module", autouse=True)
def _bound():
    _bind_all_capabilities()


def test_every_declared_capability_has_a_handler():
    """31 declared, 31 bound.  A declared-but-unbound capability is a broken build."""

    assert unbound_skills() == ()
    assert len(bound_skills()) == 31
    assert len(DESCRIPTORS) == 31


def test_the_priority_split_matches_the_published_contract():
    counts = {"P0": 0, "P1": 0, "P2": 0}
    for descriptor in DESCRIPTORS.values():
        counts[descriptor.priority] += 1
    assert counts == {"P0": 16, "P1": 10, "P2": 5}


def test_every_failure_code_has_exactly_one_category():
    """A code that means two things cannot be routed on."""

    assert CODES
    for code, category in CODES.items():
        assert code == code.upper()
        assert isinstance(category, Category)


def test_an_unknown_capability_is_not_applicable_not_a_crash():
    result = dispatch("no-such-capability", {})
    assert result.status is Status.NOT_APPLICABLE
    assert result.error["code"] == "NOT_APPLICABLE"


def test_a_handler_that_raises_something_unexpected_becomes_a_terminal_failure():
    """The boundary that stops a kernel defect from looking like an empty success."""

    from elmos_autonomy_kernel import registry

    original = registry._HANDLERS["repository-census"]

    def exploding(_request):
        raise RuntimeError("kernel defect")

    registry._HANDLERS["repository-census"] = exploding
    try:
        result = dispatch("repository-census", {})
    finally:
        registry._HANDLERS["repository-census"] = original

    assert result.status is Status.FAILED
    assert result.error["code"] == "FAILED_TERMINAL"
    assert result.error["retryable"] is False
    assert result.succeeded is False


def test_every_descriptor_declares_inputs_outputs_invariants_and_gates():
    """A capability with no stated invariant is a capability nobody can review."""

    for descriptor in DESCRIPTORS.values():
        assert descriptor.inputs, descriptor.skill_id
        assert descriptor.outputs, descriptor.skill_id
        assert descriptor.invariants, descriptor.skill_id
        assert descriptor.gates, descriptor.skill_id
        assert descriptor.module, descriptor.skill_id


def test_a_partial_result_is_never_a_success():
    """The separation the whole package rests on, asserted once centrally."""

    from elmos_autonomy_kernel.contracts import SkillResult
    from elmos_autonomy_kernel.errors import KernelError

    for status in (Status.PARTIAL, Status.INTERRUPTED, Status.FAILED,
                   Status.NOT_APPLICABLE):
        error = KernelError(code="PARTIAL", message="half done", partial=True)
        result = SkillResult.failure("repository-census", error, status=status)
        assert result.succeeded is False
        assert result.status is status


# --- CLI ---------------------------------------------------------------------


def _cli(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "elmos_autonomy_kernel.cli", *args],
        input=stdin, capture_output=True, text=True,
        env={"PYTHONPATH": SRC, "PATH": "/usr/bin:/bin"},
    )


def test_cli_doctor_reports_a_complete_build():
    result = _cli("doctor")
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["complete"] is True
    assert report["unboundCapabilities"] == []
    assert report["bound"] == 31


def test_cli_catalogue_lists_all_31_bound():
    result = _cli("catalogue")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["counts"] == {"declared": 31, "bound": 31, "unbound": 0,
                                 "failureCodes": payload["counts"]["failureCodes"]}
    assert all(item["bound"] for item in payload["capabilities"])


def test_cli_exit_code_distinguishes_not_applicable_from_failure():
    """A caller must tell outcomes apart without parsing anything."""

    unknown = _cli("run", "no-such-capability", stdin="{}")
    assert unknown.returncode == 5
    assert json.loads(unknown.stdout)["error"]["code"] == "NOT_APPLICABLE"

    empty = _cli("run", "repository-census", stdin="")
    assert empty.returncode == 4
    assert json.loads(empty.stderr)["error"]["code"] == "MISSING_REQUIRED_INPUT"

    malformed = _cli("run", "repository-census", stdin="[1, 2]")
    assert malformed.returncode == 4
    assert json.loads(malformed.stderr)["error"]["code"] == "MALFORMED_INPUT"


def test_cli_output_is_canonical_json():
    """Stable bytes: the CLI's output is safe to hash, diff and cache."""

    first = _cli("catalogue").stdout
    second = _cli("catalogue").stdout
    assert first == second
    assert first.strip() == canonical_json(json.loads(first))
