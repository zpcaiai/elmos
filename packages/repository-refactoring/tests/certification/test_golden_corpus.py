"""Golden-corpus regression: the recorded behaviour of the whole runtime.

A failure here is a *behaviour change*.  It may be a fix — in which case the
right response is to read the reported difference, agree with it, and
re-record with ``ELMOS_UPDATE_GOLDEN=1`` — but it is never noise, and the
suite never re-records on its own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elmos_repository_refactoring.runtime import dispatch

from .cases import CASES
from .corpus import CorpusCase, describe_difference, load, observation, store, updating


@pytest.mark.parametrize("case", CASES, ids=[item.case_id for item in CASES])
def test_case_matches_its_recorded_behaviour(case: CorpusCase) -> None:
    envelope = dispatch(case.skill, case.payload, trusted_context=case.context)
    actual = observation(case, envelope)
    expected = load(case)

    if expected is None:
        if not updating():
            pytest.fail(
                f"no golden record for '{case.case_id}'. Re-record deliberately with "
                f"ELMOS_UPDATE_GOLDEN=1; a suite that records on demand cannot detect a regression."
            )
        store(case, actual)
        return

    if expected["inputDigest"] != actual["inputDigest"]:
        #: The fixture itself moved.  Comparing outputs now would compare two
        #: different questions and could pass while the behaviour regressed.
        pytest.fail(
            f"the fixture for '{case.case_id}' changed (input digest "
            f"{expected['inputDigest'][:19]} -> {actual['inputDigest'][:19]}); "
            "re-record with ELMOS_UPDATE_GOLDEN=1 after confirming the new fixture is intended."
        )

    if expected != actual:
        if updating():
            store(case, actual)
            return
        pytest.fail(
            f"'{case.case_id}' ({case.description}) behaves differently:\n"
            + describe_difference(expected, actual)
        )


@pytest.mark.parametrize("case", CASES, ids=[item.case_id for item in CASES])
def test_case_is_deterministic(case: CorpusCase) -> None:
    """The same input twice must produce the same envelope, byte for byte."""

    first = dispatch(case.skill, case.payload, trusted_context=case.context)
    second = dispatch(case.skill, case.payload, trusted_context=case.context)
    assert first == second, f"'{case.case_id}' is not deterministic"


def test_every_case_has_a_recorded_baseline() -> None:
    missing = [case.case_id for case in CASES if load(case) is None]
    assert missing == [], f"cases with no golden record: {missing}"


def test_the_corpus_covers_every_catalog_skill() -> None:
    """Every Skill in the catalog has at least one recorded case.

    Partial coverage is how a corpus quietly stops being a guard: the Skills
    nobody wrote a case for are exactly the ones that regress unnoticed.
    """

    from elmos_repository_refactoring.catalog import SKILL_NAMES

    covered = {case.skill for case in CASES}
    missing = sorted(set(SKILL_NAMES) - covered)
    assert missing == [], f"these Skills have no Golden-corpus case: {missing}"


def test_both_branches_of_the_verification_gate_are_recorded() -> None:
    """With and without an executor are different behaviours, not one.

    Recording only the no-executor branch would leave the entire
    evidence-adjudication path uncovered, which is the half that decides
    whether a change ships.
    """

    verification = [case for case in CASES if case.skill == "test-and-verification"]
    assert len(verification) >= 2
    assert any(case.executions is None for case in verification)
    assert any(case.executions is not None for case in verification)

    without = next(case for case in verification if case.executions is None)
    with_evidence = next(case for case in verification if case.executions is not None)
    left, right = load(without), load(with_evidence)
    assert left is not None and right is not None
    undecided_key = "output.validation_report.undecidedBlockingGates"
    assert left["projections"][undecided_key], "the no-executor case must have undecided gates"
    assert right["projections"][undecided_key] == [], (
        "with real recorded evidence nothing should remain undecided; anything still undecided "
        "means the evidence was not actually consumed"
    )


def test_every_case_is_deterministic_across_processes() -> None:
    """The in-process check is not enough, and this is not a theoretical gap.

    Two dispatches in one process share module state and one wall clock, so
    they agree even when the runtime is reading the clock — which it was, in
    four Skills, until the corpus caught it. Reproducibility means a *fresh*
    process with a different hash seed produces the same bytes, so that is
    what this measures.
    """

    import json
    import os
    import subprocess
    import sys
    import textwrap

    root = Path(__file__).resolve().parents[2]
    script = textwrap.dedent(
        """
        import hashlib, json, sys
        sys.path.insert(0, "src")
        sys.path.insert(0, ".")
        from tests.certification.cases import CASES
        from elmos_repository_refactoring.runtime import dispatch

        digests = {}
        for case in CASES:
            envelope = dispatch(case.skill, case.payload, trusted_context=case.context)
            digests[case.case_id] = hashlib.sha256(
                json.dumps(envelope, sort_keys=True).encode()
            ).hexdigest()
        sys.stdout.write(json.dumps(digests))
        """
    )

    def run(seed: str) -> dict[str, str]:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, no payload input
            [sys.executable, "-c", script],
            cwd=root,
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        parsed: dict[str, str] = json.loads(completed.stdout)
        return parsed

    first, second = run("0"), run("424242")
    unstable = sorted(name for name in first if first[name] != second.get(name))
    assert unstable == [], (
        f"these cases produce different bytes in a fresh process: {unstable}. "
        "Something in the run is reading the wall clock, a random source, or hash order "
        "instead of taking it from trusted context."
    )
