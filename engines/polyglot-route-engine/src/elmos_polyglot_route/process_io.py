"""Bounded subprocess transport; callers retain toolchain and sandbox authority.

Output is exact or the invocation fails: truncated JSON can never become an
analyzer result. The bound applies while draining both pipes, not after exit.
POSIX process groups cover ordinary descendants, not processes escaping their
session; platform-specific Swift session cleanup remains authoritative.
"""

from __future__ import annotations

import locale
import os
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

MAX_PROCESS_STREAM_BYTES = 16 * 1024 * 1024
_CHUNK = 64 * 1024


class ProcessOutputLimitError(OSError):
    """The exact output protocol exceeded its host-owned budget."""


def bounded_communicate(
    process: subprocess.Popen[str],
    *,
    timeout: float,
    input: str | None = None,
    max_stream_bytes: int = MAX_PROCESS_STREAM_BYTES,
) -> tuple[str, str]:
    """Drain pipes concurrently, retaining at most the per-stream byte budget.

    Does not own termination: callers must terminate/reap in their finally
    block. This permits the Swift adapter to retain its stronger session scan.
    """
    if timeout <= 0 or max_stream_bytes <= 0:
        raise ValueError("positive process budgets required")
    deadline = time.monotonic() + timeout
    outputs = [bytearray(), bytearray()]
    errors: list[BaseException] = []
    changed = threading.Event()
    finished = [False, False]
    encoding = locale.getpreferredencoding(False)

    def drain(index: int) -> None:
        stream = (process.stdout, process.stderr)[index]
        try:
            if stream is None:
                raise OSError("PROCESS_CAPTURE_PIPE_REQUIRED")
            while chunk := os.read(stream.fileno(), _CHUNK):
                if len(outputs[index]) + len(chunk) > max_stream_bytes:
                    raise ProcessOutputLimitError(
                        f"PROCESS_OUTPUT_LIMIT_EXCEEDED:{'stdout' if index == 0 else 'stderr'}"
                    )
                outputs[index].extend(chunk)
        except BaseException as error:
            errors.append(error)
        finally:
            if stream is not None:
                stream.close()
            finished[index] = True
            changed.set()

    readers = [threading.Thread(target=drain, args=(index,), daemon=True) for index in range(2)]
    for reader in readers:
        reader.start()

    def feed() -> None:
        try:
            if process.stdin is not None:
                if input is not None:
                    payload = memoryview(input.encode(encoding))
                    while payload:
                        written = os.write(process.stdin.fileno(), payload[:_CHUNK])
                        payload = payload[written:]
                process.stdin.close()
        except BrokenPipeError:
            pass
        except BaseException as error:
            errors.append(error)
            changed.set()

    writer = threading.Thread(target=feed, daemon=True)
    writer.start()
    while True:
        if errors:
            raise errors[0]
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, timeout)
        if all(finished) and not writer.is_alive():
            process.wait(timeout=remaining)
            def decode(value: bytearray) -> str:
                return value.decode(encoding).replace("\r\n", "\n").replace("\r", "\n")
            return decode(outputs[0]), decode(outputs[1])
        changed.wait(min(remaining, 0.05))
        changed.clear()


def _terminate(process: subprocess.Popen[str]) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        process.kill()
    process.wait(timeout=5)
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            stream.close()


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
) -> subprocess.CompletedProcess[str]:
    """A narrow ``subprocess.run`` adapter for exact text protocols.

    ``env`` belongs to the trusted toolchain caller. This adapter grants no
    shell, environment additions, network permission, or sandbox authority.
    """
    if not capture_output or not text or stdin not in (None, subprocess.DEVNULL):
        raise ValueError("bounded text capture required")
    if input is not None and len(input.encode()) > max_stream_bytes:
        raise ProcessOutputLimitError("PROCESS_INPUT_LIMIT_EXCEEDED")
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
            )
            completed = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            if check:
                completed.check_returncode()
            return completed
        finally:
            _terminate(process)
