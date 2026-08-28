"""Bounded assembly subprocess cleanup."""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

import pytest

import elmos_polyglot_route.assembly as assembly
from elmos_polyglot_route.assembly import _kill_process_group, _run
from elmos_polyglot_route.models import RouteError


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group contract")
def test_assembly_timeout_kills_analyzer_process_group(tmp_path: Path) -> None:
    child_pid_file = tmp_path / "child.pid"
    launcher = (
        "import pathlib,subprocess,sys,time;"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid),encoding='ascii');"
        "time.sleep(60)"
    )

    with pytest.raises(
        RouteError,
        match="ASSEMBLY_BUILD_VERIFICATION_FAILED:python.*:process",
    ):
        _run(
            [sys.executable, "-c", launcher, str(child_pid_file)],
            tmp_path,
            timeout=1,
        )

    child_pid = int(child_pid_file.read_text(encoding="ascii"))
    deadline = time.monotonic() + 2
    while True:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        if time.monotonic() >= deadline:
            pytest.fail(f"assembly analyzer child survived timeout: pid={child_pid}")
        time.sleep(0.05)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group contract")
def test_process_group_cleanup_accepts_confirmed_darwin_teardown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def disappearing_group(process_group: int, signal_number: int) -> None:
        assert process_group == 12345
        calls.append(signal_number)
        if signal_number == signal.SIGKILL:
            raise PermissionError(1, "Operation not permitted")
        raise ProcessLookupError(3, "No such process")

    monkeypatch.setattr(assembly.os, "killpg", disappearing_group)

    _kill_process_group(12345, signal.SIGKILL)

    assert calls == [signal.SIGKILL, 0]


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group contract")
def test_process_group_cleanup_rejects_persistently_inaccessible_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def inaccessible_group(process_group: int, signal_number: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    times = iter((10.0, 10.2))
    monkeypatch.setattr(assembly.os, "killpg", inaccessible_group)
    monkeypatch.setattr(assembly.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(assembly.time, "sleep", lambda _: None)

    with pytest.raises(PermissionError):
        _kill_process_group(12345, signal.SIGKILL)
