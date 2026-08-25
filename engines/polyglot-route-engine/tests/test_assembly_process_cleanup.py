"""Bounded assembly subprocess cleanup."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from elmos_polyglot_route.assembly import _run
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
