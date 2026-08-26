"""Does the certification suite actually detect a regression?

A suite is only worth its runtime if a broken package fails it.  These tests
apply a real defect to a copy of a module, import that copy, and assert the
behaviour the suite checks has genuinely changed — so the guard is proven
against a defect rather than assumed to work.

Mutation is done on an isolated copy of the package, never on the installed
one: a test that edits the code under test and restores it afterwards leaves
the tree broken whenever it fails partway.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "elmos_repository_refactoring"


@contextmanager
def mutated_package(tmp_path: Path, module: str, apply: Callable[[str], str]) -> Iterator[Any]:
    """Import a copy of the package with one module rewritten."""

    root = tmp_path / "mutant"
    package = root / "elmos_repository_refactoring"
    shutil.copytree(SOURCE_ROOT, package)
    target = package / module
    original = target.read_text(encoding="utf-8")
    changed = apply(original)
    assert changed != original, f"the mutation did not alter {module}; the test would prove nothing"
    target.write_text(changed, encoding="utf-8")

    saved = {name: value for name, value in sys.modules.items() if name.startswith("elmos_")}
    for name in list(saved):
        del sys.modules[name]
    sys.path.insert(0, str(root))
    try:
        spec = importlib.util.find_spec("elmos_repository_refactoring.runtime")
        assert spec is not None
        import elmos_repository_refactoring.runtime as mutant_runtime

        yield mutant_runtime
    finally:
        sys.path.remove(str(root))
        for name in [item for item in sys.modules if item.startswith("elmos_")]:
            del sys.modules[name]
        sys.modules.update(saved)


WORKSPACE = {
    "source": "inline",
    "repository_id": "r",
    "revision": "a" * 40,
    "files": [
        {"path": "a.py", "content": "def f():\n    pass\n"},
        {
            "path": "c.py",
            "content_digest": "sha256:" + "1" * 64,
            "size_bytes": 64,
            "binary": False,
            "unreadable_reason": "undecodable-utf8",
        },
    ],
}


def test_dropping_the_unscanned_report_changes_observable_coverage(tmp_path: Path) -> None:
    """Mutation: an undecodable file stops lowering coverage."""

    def apply(text: str) -> str:
        return text.replace(
            "        if record.unreadable_reason is not None:\n"
            '            unscanned.append({"path": record.path, "reason": record.unreadable_reason})',
            "        if False:\n"
            '            unscanned.append({"path": record.path, "reason": ""})',
            1,
        )

    with mutated_package(tmp_path, "discovery.py", apply) as mutant:
        envelope = mutant.dispatch("repository-discovery", {"workspace": WORKSPACE})
    inventory = envelope["output"]["repository_inventory"]
    assert inventory["unscanned"] == []
    assert float(inventory["coverage"]) == 1.0, (
        "the mutant should report full coverage over an unreadable file — if it does not, "
        "this test is not exercising the property the suite guards"
    )

    from elmos_repository_refactoring.runtime import dispatch

    healthy = dispatch("repository-discovery", {"workspace": WORKSPACE})
    assert float(healthy["output"]["repository_inventory"]["coverage"]) < 1.0


def test_an_undecided_gate_reading_as_a_pass_is_observable(tmp_path: Path) -> None:
    """Mutation: a blocking gate with no evidence stops counting as a failure."""

    from .cases import CASES

    case = next(item for item in CASES if item.skill == "test-and-verification")

    def apply(text: str) -> str:
        return text.replace(
            "            item.gate for item in self.gates "
            "if item.blocking and item.outcome is GateOutcome.FAIL\n        )",
            "            item.gate\n"
            "            for item in self.gates\n"
            "            if item.blocking\n"
            "            and item.outcome is GateOutcome.FAIL\n"
            '            and "not produced" not in item.detail\n'
            "        )",
            1,
        )

    with mutated_package(tmp_path, "verification.py", apply) as mutant:
        envelope = mutant.dispatch(case.skill, case.payload)
    mutant_failures = envelope["output"]["validation_report"]["blockingFailures"]

    from elmos_repository_refactoring.runtime import dispatch

    healthy = dispatch(case.skill, case.payload)["output"]["validation_report"]
    assert healthy["blockingFailures"] != mutant_failures, (
        "the mutant hides undecided gates from the blocking-failure list; if the two agree, "
        "the suite's honesty check is not measuring what it claims to"
    )
    assert healthy["passed"] is False


def test_a_third_party_import_is_visible_to_the_purity_check(tmp_path: Path) -> None:
    """Mutation: a convenience dependency creeps into a pure module."""

    from .test_package_invariants import ALLOWED_TOP_LEVEL, _imports

    root = tmp_path / "mutant"
    shutil.copytree(SOURCE_ROOT, root)
    target = root / "impact.py"
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            "from __future__ import annotations\n",
            "from __future__ import annotations\n\nimport requests\n",
            1,
        ),
        encoding="utf-8",
    )
    assert sorted(_imports(target) - ALLOWED_TOP_LEVEL) == ["requests"]
    assert sorted(_imports(SOURCE_ROOT / "impact.py") - ALLOWED_TOP_LEVEL) == []


@pytest.mark.parametrize(
    "module",
    ["discovery.py", "verification.py", "impact.py"],
)
def test_the_real_package_is_untouched_after_mutation(module: str) -> None:
    """The mutation helper must never write to the package under test."""

    text = (SOURCE_ROOT / module).read_text(encoding="utf-8")
    assert "MUTANT" not in text
    assert "if False:" not in text
