from __future__ import annotations

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from elmos_polyglot_route.process_io import ProcessOutputLimitError, run_bounded


def test_exact_output_and_input_are_preserved() -> None:
    result = run_bounded(
        [sys.executable, "-c", "import sys; print(sys.stdin.read()); sys.stderr.write('err\\r\\n')"],
        input="semantic-π", env={}, timeout=10,
    )
    assert result.stdout == "semantic-π\n"
    assert result.stderr == "err\n"
    assert result.returncode == 0


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
        "import os; assert 'NODE_OPTIONS' not in os.environ; assert 'PYTHONPATH' not in os.environ; print(os.environ['HOME'])",
    ])
    assert not Path(result.stdout.strip()).exists()
