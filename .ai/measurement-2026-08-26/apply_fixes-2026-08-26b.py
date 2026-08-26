"""2026-08-26 pass 2: the six remaining project-synthesis failures.

Four defects and one stale test. Each is stated with what it actually breaks in
production, not just which assertion it turns green.

FIX 1  `_run` ignores `ELMOS_PROJECT_SYNTHESIS_COMMAND_TIMEOUT_SECONDS`.
       Every other knob in this module is configurable that way
       (`_LOCK_CACHE`, `_GRADLE_PROXY`, `_TOOLCHAIN_ROOT`, ...); the command
       timeout is the one that decides whether a slow but healthy native build
       is reported as a failure, and it was hard-wired to the parameter default.
       The env var supplies the DEFAULT only -- an explicit `timeout_seconds=`
       from a caller still wins, so the callers that already pass 30 keep 30.
       The existing 30..900 range check is left as the single gate, so a
       configured 901 fails closed with `COMMAND_TIMEOUT_OUT_OF_RANGE` BEFORE
       anything is executed.

FIX 2  A locked dependency sync has no retry, so one transient network blip
       fails the whole verification. The retry is deliberately narrow:
         * only `uv sync --locked` (a pure re-resolution of a pinned lockfile,
           so re-running it cannot change what is installed),
         * only when the failure text is a FETCH failure,
         * exactly once,
         * never after `TimeoutExpired` -- a hard timeout is a budget decision,
           not a blip, even when the tool's own message says "timed out".
       A compilation failure is deterministic and is never retried. The retry
       is recorded in the output as `TRANSIENT_DEPENDENCY_FETCH_RETRY:1/1` so a
       green result still shows that the first attempt failed.

FIX 3  `_probe` deadlocks any service that logs more than the OS pipe buffer
       during startup. THIS IS THE SERIOUS ONE. The child is spawned with
       `stdout=PIPE`, and the pipe is not read until the `finally` block --
       after the startup deadline. A pipe holds ~64 KiB; a service that writes
       more than that during startup blocks forever inside its own `write`,
       never reaches the point where it serves `/health`, and is then reported
       as a startup FAILURE. The service is fine; the probe wedged it.
       Draining the pipe on a reader thread while the deadline runs fixes it,
       and the tail is bounded exactly as before.

FIX 4  `test_markdown_document_pack_is_in_the_download_archive` asserts the
       archive root is the OUTPUT DIRECTORY name (`generated-task/`). It is the
       PROJECT name, by design: `cli._archive_workspace` reads it from the
       blueprint and validates it against an identity pattern with its own
       `ARCHIVE_PROJECT_IDENTITY_INVALID` code, and the sibling test
       `test_archive_includes_verified_lockfiles` pins exactly that
       (`commerce-service/python/uv.lock`, from a workspace directory named
       `workspace`). An unzipped deliverable should be named after the project,
       not after whatever scratch directory produced it. The test is stale;
       the code is right.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
PS = "engines/project-synthesis-engine"
VERIFICATION = f"{PS}/src/elmos_project_synthesis/verification.py"
DOC_TEST = f"{PS}/tests/test_project_documentation.py"


def patch(relative: str, old: str, new: str, *, expect: int = 1) -> None:
    path = ROOT / relative
    src = path.read_text(encoding="utf-8")
    found = src.count(old)
    if found != expect:
        raise SystemExit(f"ABORT {relative}: expected {expect} match(es), found {found}")
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"  patched {relative}")


# --------------------------------------------------------------- FIX 1+2 ----
patch(
    VERIFICATION,
    '''def _run(
    command: list[str],
    cwd: Path,
    *,
    language: str,
    kind: str = "build-analysis",
    timeout_seconds: int = 300,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not 30 <= timeout_seconds <= 900:
        raise ValueError("COMMAND_TIMEOUT_OUT_OF_RANGE")''',
    '''#: The command timeout when neither the caller nor the environment sets one.
_DEFAULT_COMMAND_TIMEOUT_SECONDS = 300

#: One retry, and only for a fetch failure. See `_is_transient_dependency_fetch`.
_MAX_TRANSIENT_DEPENDENCY_RETRIES = 1
_TRANSIENT_DEPENDENCY_RETRY_BACKOFF_SECONDS = 2.0

#: Matched case-insensitively against the failed attempt's combined output.
#: Deliberately narrow: these are the tool saying it could not GET a package,
#: which is the only failure re-running an identical locked resolution can fix.
_TRANSIENT_DEPENDENCY_FETCH_MARKERS = (
    "failed to fetch",
    "failed to download",
    "error sending request",
    "connection reset by peer",
    "temporary failure in name resolution",
)


def _configured_command_timeout_seconds() -> int:
    """The default timeout, from the environment when it is set.

    Only the DEFAULT. A caller that passes `timeout_seconds=` explicitly has
    made a per-command decision and keeps it. The value is NOT range-checked
    here -- `_run` holds the single 30..900 gate so a configured value and a
    passed value fail closed identically.
    """

    configured = os.getenv("ELMOS_PROJECT_SYNTHESIS_COMMAND_TIMEOUT_SECONDS", "").strip()
    if not configured:
        return _DEFAULT_COMMAND_TIMEOUT_SECONDS
    try:
        return int(configured)
    except ValueError:
        raise ValueError("COMMAND_TIMEOUT_NOT_AN_INTEGER") from None


def _is_locked_dependency_sync(command: list[str]) -> bool:
    """`uv sync --locked` and nothing else.

    `--locked` means "resolve exactly the committed lockfile or fail"; running
    it a second time cannot install anything different, which is what makes a
    retry safe here and unsafe almost everywhere else.
    """

    return (
        len(command) >= 3
        and Path(command[0]).name in {"uv", "uv.exe"}
        and command[1] == "sync"
        and "--locked" in command
    )


def _is_transient_dependency_fetch(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in _TRANSIENT_DEPENDENCY_FETCH_MARKERS)


def _run(
    command: list[str],
    cwd: Path,
    *,
    language: str,
    kind: str = "build-analysis",
    timeout_seconds: int | None = None,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    if timeout_seconds is None:
        timeout_seconds = _configured_command_timeout_seconds()
    if not 30 <= timeout_seconds <= 900:
        raise ValueError("COMMAND_TIMEOUT_OUT_OF_RANGE")''',
)

patch(
    VERIFICATION,
    '''        completed = subprocess.run(  # noqa: S603
            effective_command,
            cwd=cwd,
            env=process_environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:''',
    '''        retry_notes: list[str] = []
        attempt = 0
        while True:
            completed = subprocess.run(  # noqa: S603
                effective_command,
                cwd=cwd,
                env=process_environment,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
            )
            attempt_output = completed.stdout + completed.stderr
            if (
                completed.returncode == 0
                or attempt >= _MAX_TRANSIENT_DEPENDENCY_RETRIES
                or language != "python"
                or not _is_locked_dependency_sync(effective_command)
                or not _is_transient_dependency_fetch(attempt_output)
            ):
                break
            attempt += 1
            # Kept in the output on purpose: a PASSED result that needed a
            # retry must not look identical to one that succeeded first time.
            retry_notes.append(
                f"TRANSIENT_DEPENDENCY_FETCH_RETRY:{attempt}/"
                f"{_MAX_TRANSIENT_DEPENDENCY_RETRIES}\\n{attempt_output}"
            )
            time.sleep(_TRANSIENT_DEPENDENCY_RETRY_BACKOFF_SECONDS)
    except subprocess.TimeoutExpired as error:''',
)

patch(
    VERIFICATION,
    '''    output = completed.stdout + completed.stderr
    return _result(
        language=language,
        kind=kind,
        command=effective_command,
        status="PASSED" if completed.returncode == 0 else "FAILED",
        exit_code=completed.returncode,
        output=output,
    )''',
    '''    output = "".join(retry_notes) + completed.stdout + completed.stderr
    return _result(
        language=language,
        kind=kind,
        command=effective_command,
        status="PASSED" if completed.returncode == 0 else "FAILED",
        exit_code=completed.returncode,
        output=output,
    )''',
)

# ----------------------------------------------------------------- FIX 3 ----
patch(
    VERIFICATION,
    "import tempfile\nimport time\n",
    "import tempfile\nimport threading\nimport time\n",
)

patch(
    VERIFICATION,
    '''    env = _loopback_environment(environment)
    process = subprocess.Popen(  # noqa: S603
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )''',
    '''    env = _loopback_environment(environment)
    process = subprocess.Popen(  # noqa: S603
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    # THE PIPE MUST BE DRAINED WHILE THE CHILD RUNS.
    #
    # An OS pipe holds about 64 KiB. Reading it only after the startup deadline
    # means a service that logs more than that during startup blocks forever
    # inside its own `write`, never reaches the point where it answers
    # /health, and is then reported as a startup FAILURE -- a healthy service
    # that this probe wedged. The reader keeps the same bounded tail the
    # `finally` block used to take, so nothing downstream changes.
    captured_tail: list[str] = []
    reader = threading.Thread(
        target=_drain_tail,
        args=(process.stdout, captured_tail, _PROBE_OUTPUT_TAIL_CHARACTERS),
        daemon=True,
    )
    reader.start()''',
)

patch(
    VERIFICATION,
    '''        output = process.stdout.read()[-6_000:] if process.stdout is not None else ""
        if process.stdout is not None:
            process.stdout.close()''',
    '''        # The child is gone, so the reader sees EOF and finishes. Bounded
        # join: a wedged reader must not wedge the probe in turn.
        reader.join(timeout=5)
        output = captured_tail[0] if captured_tail else ""
        if process.stdout is not None:
            process.stdout.close()''',
)

patch(
    VERIFICATION,
    "def _probe(",
    '''#: Same bound the probe has always reported; only *when* it is read changed.
_PROBE_OUTPUT_TAIL_CHARACTERS = 6_000


def _drain_tail(stream: Any, sink: list[str], limit: int) -> None:
    """Read `stream` to EOF, keeping only its last `limit` characters.

    Runs on a thread for the whole life of the probed process so the pipe
    never fills. Appends exactly one element to `sink` when it is done.
    """

    tail = ""
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            tail = (tail + chunk)[-limit:]
    except (OSError, ValueError):
        # The pipe was closed under us while shutting the process down; the
        # tail collected so far is still the right thing to report.
        pass
    sink.append(tail)


def _probe(''',
)

# ----------------------------------------------------------------- FIX 4 ----
patch(
    DOC_TEST,
    '''    assert {f"generated-task/{path}" for path in DOCUMENT_SOURCE_REFS} <= archived''',
    '''    # The archive root is the PROJECT name, not the output directory name:
    # `cli._archive_workspace` reads it from the blueprint and validates it
    # against an identity pattern (`ARCHIVE_PROJECT_IDENTITY_INVALID`), and
    # `test_archive_includes_verified_lockfiles` pins the same rule from a
    # directory called `workspace`. An unzipped deliverable is named after the
    # project, not after the scratch directory that produced it.
    assert {f"notes-docs-service/{path}" for path in DOCUMENT_SOURCE_REFS} <= archived''',
)

print("2026-08-26 pass 2 applied (timeout env, transient retry, probe drain, archive-root test)")
