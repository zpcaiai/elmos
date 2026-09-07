"""Bounded subprocess transport; callers retain toolchain and sandbox authority.

Output is exact or the invocation fails: truncated JSON can never become an
analyzer result. The bound applies while draining both pipes, not after exit.
POSIX process groups cover ordinary descendants, not processes escaping their
session; platform-specific Swift session cleanup remains authoritative.
"""

from __future__ import annotations

import errno
import locale
import math
import os
import select
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from contextlib import closing
from pathlib import Path
from typing import BinaryIO

MAX_PROCESS_STREAM_BYTES = 16 * 1024 * 1024
MAX_ALLOWED_PROCESS_STREAM_BYTES = 64 * 1024 * 1024
_CHUNK = 64 * 1024


class ProcessOutputLimitError(OSError):
    """The exact output protocol exceeded its host-owned budget."""


def _validate_budgets(timeout: float, max_stream_bytes: int) -> None:
    if type(timeout) not in (int, float) or timeout <= 0:
        raise ValueError("PROCESS_TIMEOUT_BUDGET_INVALID")
    try:
        finite_timeout = math.isfinite(timeout)
    except OverflowError:
        finite_timeout = False
    if not finite_timeout:
        raise ValueError("PROCESS_TIMEOUT_BUDGET_INVALID")
    if type(max_stream_bytes) is not int or not 0 < max_stream_bytes <= MAX_ALLOWED_PROCESS_STREAM_BYTES:
        raise ValueError("PROCESS_STREAM_BUDGET_INVALID")


def _validate_capture_policy(retain_stdout: bool, stdout_log: BinaryIO | None) -> None:
    if type(retain_stdout) is not bool or (not retain_stdout and stdout_log is None):
        raise ValueError("PROCESS_CAPTURE_POLICY_INVALID")


def bounded_communicate(
    process: subprocess.Popen[str],
    *,
    timeout: float,
    input: str | None = None,
    max_stream_bytes: int = MAX_PROCESS_STREAM_BYTES,
    reap: bool = False,
    stdout_log: BinaryIO | None = None,
    stderr_log: BinaryIO | None = None,
    retain_stdout: bool = True,
) -> tuple[str, str]:
    """Drain pipes concurrently, retaining at most the per-stream byte budget.

    Does not normally reap: the leader identity remains pinned while callers
    clean up its process group. The existing specialized Swift session adapter
    explicitly retains its own reap/cleanup protocol. No helper threads exist.
    """
    _validate_budgets(timeout, max_stream_bytes)
    _validate_capture_policy(retain_stdout, stdout_log)
    if os.name != "posix":
        raise OSError("BOUNDED_PROCESS_PLATFORM_NOT_IMPLEMENTED")
    deadline = time.monotonic() + timeout
    outputs = [bytearray(), bytearray()]
    stream_sizes = [0, 0]
    logs = (stdout_log, stderr_log)
    encoding = locale.getpreferredencoding(False)
    payload = memoryview(input.encode(encoding) if input is not None else b"")
    if len(payload) > max_stream_bytes:
        raise ProcessOutputLimitError("PROCESS_INPUT_LIMIT_EXCEEDED")
    with selectors.DefaultSelector() as selector:
        for index, stream in enumerate((process.stdout, process.stderr)):
            if stream is None:
                raise OSError("PROCESS_CAPTURE_PIPE_REQUIRED")
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, index)
        if process.stdin is not None:
            if payload:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, 2)
            else:
                process.stdin.close()
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(process.args, timeout)
            for key, _events in selector.select(remaining):
                index = key.data
                if index == 2:
                    try:
                        written = os.write(key.fd, payload[:_CHUNK])
                        payload = payload[written:]
                    except BrokenPipeError:
                        payload = memoryview(b"")
                    except BlockingIOError:
                        continue
                    if not payload:
                        selector.unregister(key.fileobj)
                        assert process.stdin is not None
                        process.stdin.close()
                    continue
                try:
                    chunk = os.read(key.fd, _CHUNK)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if stream_sizes[index] + len(chunk) > max_stream_bytes:
                    raise ProcessOutputLimitError(
                        f"PROCESS_OUTPUT_LIMIT_EXCEEDED:{'stdout' if index == 0 else 'stderr'}"
                    )
                stream_sizes[index] += len(chunk)
                if index != 0 or retain_stdout:
                    outputs[index].extend(chunk)
                log = logs[index]
                if log is not None:
                    if log.write(chunk) != len(chunk):
                        raise OSError("PROCESS_LOG_SHORT_WRITE")
                    log.flush()
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            stream.close()
    if reap:
        process.wait(timeout=max(0.0, deadline - time.monotonic()))
    else:
        _wait_unreaped(process, deadline, timeout)
    def decode(value: bytearray) -> str:
        return value.decode(encoding).replace("\r\n", "\n").replace("\r", "\n")
    return decode(outputs[0]), decode(outputs[1])


def _wait_unreaped(process: subprocess.Popen[str], deadline: float, timeout: float) -> None:
    """Observe owned-child exit without freeing its PID before group cleanup."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(process.args, timeout)
    if sys.platform == "darwin":
        # CPython on Darwin has no os.waitid. NOTE_EXIT observes without waitpid;
        # an already-exited unreaped child may refuse event registration (ESRCH).
        with closing(select.kqueue()) as queue:
            event = select.kevent(
                process.pid, filter=select.KQ_FILTER_PROC,
                flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT, fflags=select.KQ_NOTE_EXIT,
            )
            try:
                events = queue.control([event], 1, remaining)
            except ProcessLookupError:
                return
            if events:
                if events[0].flags & select.KQ_EV_ERROR and events[0].data != errno.ESRCH:
                    raise OSError(events[0].data, "PROCESS_EXIT_OBSERVER_FAILED")
                return
    elif hasattr(os, "waitid"):
        while time.monotonic() < deadline:
            if os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG) is not None:
                return
            time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
    else:
        raise OSError("UNREAPED_PROCESS_OBSERVER_NOT_IMPLEMENTED")
    raise subprocess.TimeoutExpired(process.args, timeout)


def _terminate(process: subprocess.Popen[str]) -> None:
    # Never signal a numeric PID/group after wait() has released its identity.
    permission_error: PermissionError | None = None
    if process.returncode is None and os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError as error:
            permission_error = error
    elif process.returncode is None:
        process.kill()
    try:
        process.wait(timeout=5)
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
    if permission_error is not None:
        # Darwin may report EPERM for a group containing only our unreaped
        # zombie. After reaping, only *non-signalling* probes may follow: a
        # surviving/reused/inaccessible group fails closed, never gets killed.
        deadline = time.monotonic() + 0.1
        while True:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return
            except PermissionError:
                pass
            if time.monotonic() >= deadline:
                raise permission_error
            time.sleep(0.001)


terminate_bounded_process = _terminate


def run_bounded(
    command: Sequence[str],
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 120,
    check: bool = False,
    capture_output: bool = True,
    text: bool = True,
    input: str | None = None,
    max_stream_bytes: int = MAX_PROCESS_STREAM_BYTES,
    stdin: int | None = None,
    stdout_log: BinaryIO | None = None,
    stderr_log: BinaryIO | None = None,
    retain_stdout: bool = True,
) -> subprocess.CompletedProcess[str]:
    """A narrow ``subprocess.run`` adapter for exact text protocols.

    ``env`` belongs to the trusted toolchain caller. This adapter grants no
    shell, environment additions, network permission, or sandbox authority.
    Optional binary log handles are host-owned, bounded by the same output
    limit, flushed as output arrives, and never opened from child-controlled
    paths. A caller may stream stdout only to that bounded host-owned sink so
    binary compiler artifacts are never decoded or duplicated in memory. Raw
    logs may contain source data; no ambient/global log sink exists.
    """
    _validate_budgets(timeout, max_stream_bytes)
    _validate_capture_policy(retain_stdout, stdout_log)
    if not capture_output or not text or stdin not in (None, subprocess.DEVNULL):
        raise ValueError("bounded text capture required")
    if input is not None and len(input.encode()) > max_stream_bytes:
        raise ProcessOutputLimitError("PROCESS_INPUT_LIMIT_EXCEEDED")
    if os.name != "posix" or signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
        raise OSError("BOUNDED_PROCESS_REAPER_AUTHORITY_UNAVAILABLE")
    with tempfile.TemporaryDirectory(prefix="elmos-bounded-process-") as temporary:
        if env is None:
            # Legacy helper-build call sites did not supply an environment.
            # Do not import ambient interpreter hooks or credentials there.
            root = Path(temporary)
            (root / "cache").mkdir(mode=0o700)
            env = {
                "PATH": os.defpath, "HOME": temporary, "TMPDIR": temporary,
                "XDG_CACHE_HOME": str(root / "cache"), "LANG": "C.UTF-8", "TZ": "UTC",
            }
        process = subprocess.Popen(
            command, cwd=cwd, env=env, text=True,
            stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=os.name == "posix",
        )
        try:
            stdout, stderr = bounded_communicate(
                process, timeout=timeout, input=input, max_stream_bytes=max_stream_bytes,
                stdout_log=stdout_log, stderr_log=stderr_log,
                retain_stdout=retain_stdout,
            )
            _terminate(process)
            completed = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            if check:
                completed.check_returncode()
            return completed
        finally:
            _terminate(process)
