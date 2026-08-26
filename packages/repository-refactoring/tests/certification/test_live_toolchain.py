"""The live path: a real executor running a real toolchain over a real tree.

Everything else in this suite exercises the deterministic core, where "no
executor" is the honest default.  That leaves the *other* half of the
two-layer design untested: materialize a snapshot, run an actual compiler and
an actual test runner over it through :class:`SubprocessExecutor`, and feed
what really happened back into adjudication.

These tests skip — loudly, by name — when a toolchain is not installed.  They
never pass by doing nothing: a suite that reports green because it found no
interpreter is the exact failure mode this package is built to refuse.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from elmos_repository_refactoring.contracts import ContractError, NetworkPolicy
from elmos_repository_refactoring.sandbox import (
    ExecutionKind,
    ExecutionRequest,
    ExecutionStatus,
    SubprocessExecutor,
)
from elmos_repository_refactoring.workspace import WorkspaceSnapshot, materialize

from .cases import CASES

#: A runnable version of the corpus fixture: the same package, plus the
#: configuration a real pytest run needs to import it.
RUNNABLE = {
    "pyproject.toml": (
        "[project]\n"
        'name = "acme-billing"\n'
        'version = "1.0.0"\n'
        'requires-python = ">=3.11"\n'
        "\n"
        "[tool.pytest.ini_options]\n"
        'pythonpath = ["src"]\n'
        'testpaths = ["tests"]\n'
    ),
    "src/acme/__init__.py": "",
    "src/acme/ledger.py": (
        "def post_entry(customer_id: str, amount: int, currency: str) -> str:\n"
        "    return f'{customer_id}:{amount}:{currency}'\n"
    ),
    "src/acme/api.py": (
        "from acme.ledger import post_entry\n"
        "\n"
        "\n"
        "def handle(customer_id: str, amount: int, currency: str) -> str:\n"
        "    return post_entry(customer_id, amount, currency)\n"
    ),
    "tests/test_billing.py": (
        "from acme.api import handle\n"
        "from acme.ledger import post_entry\n"
        "\n"
        "\n"
        "def test_post_entry() -> None:\n"
        "    assert post_entry('c1', 1, 'USD') == 'c1:1:USD'\n"
        "\n"
        "\n"
        "def test_handle_delegates() -> None:\n"
        "    assert handle('c2', 2, 'EUR') == 'c2:2:EUR'\n"
    ),
}


def _snapshot(files: dict[str, str]) -> WorkspaceSnapshot:
    return WorkspaceSnapshot.from_payload(
        {
            "source": "inline",
            "repository_id": "live",
            "revision": "a" * 40,
            "files": [{"path": key, "content": value} for key, value in sorted(files.items())],
        }
    )


def _requires(binary: str) -> str | None:
    return None if shutil.which(binary) else f"'{binary}' is not installed"


PYTEST_MISSING = _requires("pytest")
RUFF_MISSING = _requires("ruff")


def _executor(root: Path, *, allowlist: tuple[str, ...]) -> SubprocessExecutor:
    return SubprocessExecutor(
        root,
        allowlist=allowlist,
        network=NetworkPolicy.DENY,
        environment={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"},
    )


class TestMaterialization:
    def test_a_snapshot_round_trips_through_the_filesystem(self, tmp_path: Path) -> None:
        source = _snapshot(RUNNABLE)
        report = materialize(source, tmp_path)
        assert report.complete
        assert set(report.written) == set(RUNNABLE)

        #: Reading it back must reproduce the same tree digest. If it does not,
        #: every gate decided from a materialized run was decided over a tree
        #: that is not the one the core reasoned about.
        reloaded = WorkspaceSnapshot.from_directory(
            tmp_path, repository_id="live", revision="a" * 40
        )
        assert reloaded.tree_digest == source.tree_digest

    def test_an_unreproducible_file_is_reported_not_invented(self, tmp_path: Path) -> None:
        """An empty stand-in would make a test runner report on a tree that
        exists nowhere."""

        snapshot = WorkspaceSnapshot.from_payload(
            {
                "source": "inline",
                "repository_id": "live",
                "revision": "a" * 40,
                "files": [
                    {"path": "a.py", "content": "x = 1\n"},
                    {
                        "path": "logo.png",
                        "content_digest": "sha256:" + "2" * 64,
                        "size_bytes": 2048,
                        "binary": True,
                    },
                ],
            }
        )
        report = materialize(snapshot, tmp_path)
        assert not report.complete
        assert [item["path"] for item in report.skipped] == ["logo.png"]
        assert not (tmp_path / "logo.png").exists()

    def test_a_non_empty_root_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "someone-elses-file").write_text("hello", encoding="utf-8")
        with pytest.raises(ContractError) as error:
            materialize(_snapshot(RUNNABLE), tmp_path)
        assert error.value.code == "materialize_root_not_empty"


class TestLiveExecution:
    @pytest.mark.skipif(bool(PYTEST_MISSING), reason=str(PYTEST_MISSING))
    def test_a_real_test_run_passes_on_the_unmodified_tree(self, tmp_path: Path) -> None:
        materialize(_snapshot(RUNNABLE), tmp_path)
        result = _executor(tmp_path, allowlist=("pytest",)).execute(
            ExecutionRequest(
                request_id="live-tests",
                kind=ExecutionKind.TEST,
                argv=("pytest", "-q"),
                timeout_seconds=120,
            )
        )
        assert result.status is ExecutionStatus.COMPLETED, result.stderr[-2000:]
        assert result.exit_code == 0
        assert "2 passed" in result.stdout

    @pytest.mark.skipif(bool(PYTEST_MISSING), reason=str(PYTEST_MISSING))
    def test_a_broken_rename_really_fails_the_real_tests(self, tmp_path: Path) -> None:
        """The negative control.

        A rename that changes the definition and not the importers must fail a
        real test run. Without this, a green live run proves only that the
        toolchain starts.
        """

        broken = dict(RUNNABLE)
        broken["src/acme/ledger.py"] = RUNNABLE["src/acme/ledger.py"].replace(
            "def post_entry", "def record_entry"
        )
        materialize(_snapshot(broken), tmp_path)
        result = _executor(tmp_path, allowlist=("pytest",)).execute(
            ExecutionRequest(
                request_id="live-tests-broken",
                kind=ExecutionKind.TEST,
                argv=("pytest", "-q"),
                timeout_seconds=120,
            )
        )
        assert result.status is ExecutionStatus.FAILED
        assert result.exit_code != 0

    @pytest.mark.skipif(bool(PYTEST_MISSING), reason=str(PYTEST_MISSING))
    def test_the_transform_output_survives_a_real_test_run(self, tmp_path: Path) -> None:
        """The whole point of the two-layer design, end to end.

        The pure core computes a cross-file rename with no shell and no
        filesystem. The result is then written to disk and handed to a real
        pytest. If the core's scope analysis were wrong — an importer missed,
        a call site left behind — this is where it stops being a theory.
        """

        from elmos_repository_refactoring.adapters import AdapterCapabilitySnapshot
        from elmos_repository_refactoring.buildgraph import build_graph
        from elmos_repository_refactoring.discovery import discover
        from elmos_repository_refactoring.executor import execute_transform
        from elmos_repository_refactoring.index import build_index
        from elmos_repository_refactoring.intent import compile_intent
        from elmos_repository_refactoring.request import RefactorRequest
        from elmos_repository_refactoring.synthesis import predicate_context, synthesize

        case = next(item for item in CASES if item.case_id.startswith("04-"))
        request = RefactorRequest.from_payload(case.payload["request"])
        source = _snapshot(RUNNABLE)
        inventory = discover(source)
        index = build_index(source, inventory, build_graph(source, inventory))
        intent = compile_intent(request, index)
        adapters = AdapterCapabilitySnapshot()
        synthesis = synthesize(intent, source, index, adapters, dry_run=False)
        transform = execute_transform(
            [(item.recipe, item.parameters) for item in synthesis.selected],
            source,
            index,
            lock=synthesis.lock,
            scope=intent.scope,
            adapters=adapters,
            context=predicate_context(intent, index, source, synthesis.selected),
        )
        assert transform.patch.changes, "the core produced no change; the live check would be vacuous"

        report = materialize(transform.snapshot, tmp_path)
        assert report.complete
        result = _executor(tmp_path, allowlist=("pytest",)).execute(
            ExecutionRequest(
                request_id="live-tests-after-transform",
                kind=ExecutionKind.TEST,
                argv=("pytest", "-q"),
                timeout_seconds=120,
            )
        )
        changed = sorted(change.path for change in transform.patch.changes)
        assert result.status is ExecutionStatus.COMPLETED, (
            f"the core rewrote {changed} and a real pytest rejected the result:\n"
            f"{result.stdout[-3000:]}\n{result.stderr[-2000:]}"
        )
        assert "2 passed" in result.stdout

    @pytest.mark.skipif(bool(RUFF_MISSING), reason=str(RUFF_MISSING))
    def test_a_real_linter_accepts_the_rewritten_source(self, tmp_path: Path) -> None:
        """A rename that leaves an unused import behind still lints clean by
        accident unless the rewrite is actually correct."""

        materialize(_snapshot(RUNNABLE), tmp_path)
        result = _executor(tmp_path, allowlist=("ruff",)).execute(
            ExecutionRequest(
                request_id="live-lint",
                kind=ExecutionKind.FORMAT,
                argv=("ruff", "check", "--select", "F", "."),
                timeout_seconds=120,
            )
        )
        assert result.status is ExecutionStatus.COMPLETED, result.stdout[-2000:]


class TestSandboxRefusals:
    """The guarantees the executor advertises, checked against the real one."""

    def test_a_binary_outside_the_allowlist_is_refused(self, tmp_path: Path) -> None:
        result = _executor(tmp_path, allowlist=("pytest",)).execute(
            ExecutionRequest(
                request_id="not-allowed",
                kind=ExecutionKind.CUSTOM,
                argv=("curl", "https://example.com"),
            )
        )
        assert result.status is ExecutionStatus.REFUSED
        assert not result.status.produced_evidence

    @pytest.mark.parametrize(
        ("working_directory", "reason"),
        [
            ("../../etc", "path_escape"),
            ("/etc", "invalid_path"),
            ("does-not-exist", "missing_working_directory"),
        ],
    )
    def test_a_working_directory_outside_the_root_is_refused(
        self, tmp_path: Path, working_directory: str, reason: str
    ) -> None:
        result = _executor(tmp_path, allowlist=("pytest",)).execute(
            ExecutionRequest(
                request_id="escape",
                kind=ExecutionKind.TEST,
                argv=("pytest", "-q"),
                working_directory=working_directory,
            )
        )
        #: A refusal, with the reason named — not an exception the caller has
        #: to catch, and never a silent fallback to the root.
        assert result.status is ExecutionStatus.REFUSED
        assert result.reason == reason
        assert not result.succeeded

    @pytest.mark.skipif(bool(PYTEST_MISSING), reason=str(PYTEST_MISSING))
    def test_the_host_environment_does_not_reach_the_subprocess(self, tmp_path: Path) -> None:
        import os

        materialize(_snapshot({"probe.py": "import os\nprint(os.environ.get('LEAK', 'absent'))\n"}), tmp_path)
        os.environ["LEAK"] = "a-token-that-must-not-travel"
        try:
            result = _executor(tmp_path, allowlist=(Path(sys.executable).name, "python3")).execute(
                ExecutionRequest(
                    request_id="env-probe",
                    kind=ExecutionKind.PROBE,
                    argv=("python3", "probe.py"),
                    timeout_seconds=60,
                )
            )
        finally:
            del os.environ["LEAK"]
        assert result.status is ExecutionStatus.COMPLETED, result.stderr[-1000:]
        assert "absent" in result.stdout
        assert "a-token-that-must-not-travel" not in result.stdout

    @pytest.mark.skipif(bool(PYTEST_MISSING), reason=str(PYTEST_MISSING))
    def test_a_timeout_is_a_timeout_and_not_a_pass(self, tmp_path: Path) -> None:
        materialize(_snapshot({"slow.py": "import time\ntime.sleep(30)\n"}), tmp_path)
        result = _executor(tmp_path, allowlist=("python3",)).execute(
            ExecutionRequest(
                request_id="slow",
                kind=ExecutionKind.PROBE,
                argv=("python3", "slow.py"),
                timeout_seconds=2,
            )
        )
        assert result.status is ExecutionStatus.TIMEOUT
        #: A timeout *is* decisive — as a failure. What it must never be is a
        #: pass: `succeeded` requires COMPLETED with exit code 0, so a command
        #: that never finished cannot satisfy a gate.
        assert result.decisive
        assert not result.succeeded

    def test_a_timed_out_gate_blocks_the_run(self) -> None:
        """End to end, because the property that matters is the adjudication."""

        from elmos_repository_refactoring.runtime import dispatch

        case = next(item for item in CASES if item.case_id.startswith("25-"))
        context = {key: value for key, value in case.context.items() if key != "recorded_executions"}
        timed_out = [
            {**entry, "status": "timeout", "exitCode": None}
            for entry in case.context["recorded_executions"]
        ]
        envelope = dispatch(
            case.skill, case.payload, trusted_context={**context, "recorded_executions": timed_out}
        )
        report = envelope["output"]["validation_report"]
        assert envelope["status"] == "blocked"
        assert report["passed"] is False
        assert {"build", "typecheck", "changed-target-tests"} <= set(report["blockingFailures"])


def test_the_live_suite_actually_ran_something() -> None:
    """Fail loudly if nothing above could execute.

    Without this, removing pytest from the image would turn this file into a
    row of skips and the suite would still report success — which is the
    precise shape of dishonesty the rest of the package refuses.
    """

    assert PYTEST_MISSING is None or RUFF_MISSING is None, (
        "no toolchain was available, so the live-execution layer was not exercised at all. "
        "That is a gap in the certification, not a pass."
    )
