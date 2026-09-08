from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from elmos_polyglot_route.process_io import (
    ProcessOutputLimitError,
    bounded_communicate,
    run_bounded,
)


@pytest.mark.parametrize("budget", [
    {"timeout": 0}, {"timeout": -1}, {"timeout": float("nan")},
    {"timeout": float("inf")}, {"timeout": float("-inf")},
    {"timeout": True}, {"timeout": "1"}, {"timeout": None}, {"timeout": 10 ** 400},
    {"max_stream_bytes": 0}, {"max_stream_bytes": -1},
    {"max_stream_bytes": float("nan")}, {"max_stream_bytes": float("inf")},
    {"max_stream_bytes": float("-inf")}, {"max_stream_bytes": True},
    {"max_stream_bytes": 1.0}, {"max_stream_bytes": "1"},
    {"max_stream_bytes": None}, {"max_stream_bytes": 64 * 1024 * 1024 + 1},
])
def test_invalid_budgets_fail_before_spawn_or_pipe_access(monkeypatch, budget) -> None:
    from elmos_polyglot_route.process_io import bounded_communicate
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: pytest.fail("invalid budget spawned process"))
    with pytest.raises(ValueError, match="BUDGET_INVALID"):
        run_bounded([sys.executable, "-c", "pass"], **budget)
    with pytest.raises(ValueError, match="BUDGET_INVALID"):
        bounded_communicate(None, **({"timeout": 1} | budget))


def test_ast_budget_upper_bound_remains_supported() -> None:
    result = run_bounded([sys.executable, "-c", "print('ok')"], max_stream_bytes=64 * 1024 * 1024)
    assert result.stdout == "ok\n"


def test_sink_only_policy_requires_a_host_owned_sink_before_spawn(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("invalid capture policy spawned process"),
    )
    with pytest.raises(ValueError, match="PROCESS_CAPTURE_POLICY_INVALID"):
        run_bounded(
            [sys.executable, "-c", "pass"],
            retain_stdout=False,
        )


def test_exact_output_and_input_are_preserved() -> None:
    result = run_bounded(
        [sys.executable, "-c", "import sys; print(sys.stdin.read()); sys.stderr.write('err\\r\\n')"],
        input="semantic-π", env={}, timeout=10,
    )
    assert result.stdout == "semantic-π\n"
    assert result.stderr == "err\n"
    assert result.returncode == 0


@pytest.mark.skipif(os.name != "posix", reason="POSIX inherited-pipe contract")
def test_completed_leader_allows_bounded_inherited_pipe_drain() -> None:
    child = "import time; time.sleep(0.15)"
    parent = (
        "import subprocess,sys; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
        "print('leader-complete')"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", parent],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    started = time.monotonic()
    stdout, stderr = bounded_communicate(
        process,
        timeout=5,
        reap=True,
        leader_exit_poll_interval=0.01,
    )

    assert stdout == "leader-complete\n"
    assert stderr == ""
    assert process.returncode == 0
    assert 0.1 <= time.monotonic() - started < 2.0


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_output_limit_fails_during_process_execution(stream: str) -> None:
    start = time.monotonic()
    with pytest.raises(ProcessOutputLimitError, match=f"LIMIT_EXCEEDED:{stream}"):
        run_bounded(
            [sys.executable, "-c", (
                f"import sys,time; sys.{stream}.write('x'*1048576); sys.{stream}.flush(); time.sleep(30)"
            )],
            env={}, timeout=10, max_stream_bytes=65536,
        )
    assert time.monotonic() - start < 10


def test_parallel_dual_stream_draining_is_bounded_and_exact() -> None:
    def execute(_: int) -> tuple[str, str]:
        result = run_bounded(
            [sys.executable, "-c", "import sys; sys.stdout.write('a'*524288); sys.stderr.write('b'*524288)"],
            env={}, timeout=15, max_stream_bytes=524288,
        )
        return result.stdout, result.stderr
    with ThreadPoolExecutor(max_workers=4) as pool:
        for stdout, stderr in pool.map(execute, range(8)):
            assert stdout == "a" * 524288
            assert stderr == "b" * 524288


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group contract")
def test_timeout_terminates_child_holding_output_pipes(tmp_path: Path) -> None:
    sentinel = tmp_path / "escaped-work"
    child_code = f"import time,pathlib; time.sleep(2); pathlib.Path({str(sentinel)!r}).write_text('leak')"
    parent_code = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child_code!r}]); time.sleep(30)"
    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded([sys.executable, "-c", parent_code], env={}, timeout=0.4)
    time.sleep(2)
    assert not sentinel.exists()


def test_exit_status_is_preserved_and_check_raises() -> None:
    command = [sys.executable, "-c", "import sys; print('failed'); sys.exit(7)"]
    assert run_bounded(command, env={}).returncode == 7
    with pytest.raises(subprocess.CalledProcessError) as captured:
        run_bounded(command, env={}, check=True)
    assert captured.value.stdout == "failed\n"


def test_legacy_helper_build_environment_does_not_inherit_hooks(monkeypatch) -> None:
    monkeypatch.setenv("NODE_OPTIONS", "--require=hostile")
    monkeypatch.setenv("PYTHONPATH", "/hostile")
    result = run_bounded([
        sys.executable, "-c",
        "import os; assert 'NODE_OPTIONS' not in os.environ; "
        "assert 'PYTHONPATH' not in os.environ; print(os.environ['HOME'])",
    ])
    assert not Path(result.stdout.strip()).exists()


def test_repeated_timeout_and_flood_leave_no_transport_threads() -> None:
    initial_threads = {thread.ident for thread in threading.enumerate()}
    for _ in range(5):
        with pytest.raises(ProcessOutputLimitError):
            run_bounded(
                [sys.executable, "-c", "import sys; sys.stdout.write('x'*1048576)"],
                env={}, timeout=10, max_stream_bytes=4096,
            )
        with pytest.raises(subprocess.TimeoutExpired):
            run_bounded([sys.executable, "-c", "import time; time.sleep(30)"], env={}, timeout=0.05)
    assert {thread.ident for thread in threading.enumerate()} == initial_threads


def test_host_owned_logs_are_flushed_before_process_exit(tmp_path: Path) -> None:
    log_path = tmp_path / "stdout.log"
    script = (
        "import pathlib,sys,time; print('ready',flush=True); "
        f"p=pathlib.Path({str(log_path)!r}); deadline=time.monotonic()+5\n"
        "while p.stat().st_size == 0 and time.monotonic()<deadline: time.sleep(.01)\n"
        "assert p.read_bytes()==b'ready\\n'; print('done'); print('diagnostic',file=sys.stderr)"
    )
    with log_path.open("wb") as stdout_log, (tmp_path / "stderr.log").open("wb") as stderr_log:
        result = run_bounded(
            [sys.executable, "-c", script], env={}, timeout=15, check=True,
            stdout_log=stdout_log, stderr_log=stderr_log,
        )
    assert result.stdout == "ready\ndone\n"
    assert log_path.read_bytes() == result.stdout.encode()
    assert (tmp_path / "stderr.log").read_bytes() == b"diagnostic\n"


def test_log_sink_never_receives_bytes_beyond_capture_limit(tmp_path: Path) -> None:
    log_path = tmp_path / "stdout.log"
    with log_path.open("wb") as stdout_log, pytest.raises(ProcessOutputLimitError):
        run_bounded(
            [sys.executable, "-c", "print('x'*8192)"], env={}, timeout=15,
            max_stream_bytes=4096, stdout_log=stdout_log,
        )
    assert log_path.stat().st_size <= 4096


def test_binary_stdout_can_stream_to_a_bounded_host_owned_sink(tmp_path: Path) -> None:
    output_path = tmp_path / "artifact.bin"
    payload = bytes(range(256)) * 16
    script = f"import sys; sys.stdout.buffer.write({payload!r})"
    with output_path.open("xb") as stdout_log:
        result = run_bounded(
            [sys.executable, "-c", script],
            env={},
            timeout=15,
            max_stream_bytes=len(payload),
            stdout_log=stdout_log,
            retain_stdout=False,
        )
    assert result.stdout == ""
    assert result.stderr == ""
    assert output_path.read_bytes() == payload


def test_sink_only_stdout_still_enforces_the_execution_limit(tmp_path: Path) -> None:
    output_path = tmp_path / "partial.bin"
    with output_path.open("xb") as stdout_log, pytest.raises(ProcessOutputLimitError):
        run_bounded(
            [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x'*8192)"],
            env={},
            timeout=15,
            max_stream_bytes=4096,
            stdout_log=stdout_log,
            retain_stdout=False,
        )
    assert output_path.stat().st_size <= 4096


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group contract")
def test_normal_completion_cleans_group_before_reaping(monkeypatch) -> None:
    import elmos_polyglot_route.process_io as process_io
    calls = []
    original = process_io._terminate
    def terminate(process):
        calls.append(process.returncode)
        return original(process)
    monkeypatch.setattr(process_io, "_terminate", terminate)
    assert run_bounded([sys.executable, "-c", "pass"], env={}).returncode == 0
    assert calls == [None, 0]


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group contract")
def test_child_closing_pipes_does_not_escape_normal_completion(tmp_path: Path) -> None:
    sentinel = tmp_path / "leaked"
    child = f"import time,pathlib; time.sleep(2); pathlib.Path({str(sentinel)!r}).write_text('leak')"
    parent = (
        "import subprocess,sys; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)"
    )
    assert run_bounded([sys.executable, "-c", parent], env={}).returncode == 0
    time.sleep(2)
    assert not sentinel.exists()
