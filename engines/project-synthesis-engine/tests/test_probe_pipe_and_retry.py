"""The startup probe must not wedge the process it is probing.

`_probe` spawns the generated service with `stdout=PIPE`. An OS pipe holds
about 64 KiB. If nothing reads it while the startup deadline runs, a service
that logs more than that during startup blocks inside its own `write`, never
reaches the point where it answers `/health`, and the probe reports a startup
FAILURE for a service that was fine -- and that the probe itself wedged.

That failure mode is invisible in a small fixture: it only appears once the
child writes past the buffer. These tests write past it on purpose, and one of
them asserts the boundary directly rather than relying on a service to exhibit
it.

The retry tests pin the other half of the pass: exactly which failures a locked
dependency sync is allowed to retry, and which it must not.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from elmos_project_synthesis import verification

_PIPE_BUFFER_CEILING = 64 * 1024


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


_CHATTY_SERVER = textwrap.dedent(
    '''
    import json, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer

    # Well past a pipe buffer, written BEFORE the socket is bound. If the
    # probe is not draining, this write never returns.
    sys.stdout.write("startup-log:" + "x" * {volume})
    sys.stdout.flush()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({{"status": "UP", "service": sys.argv[2]}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
    '''
)


# ------------------------------------------------------- the pipe deadlock ----

@pytest.mark.parametrize("volume", [_PIPE_BUFFER_CEILING * 2, 200_000])
def test_a_service_that_logs_past_the_pipe_buffer_still_starts(tmp_path: Path, volume: int) -> None:
    """The regression itself. Before the drain, both of these timed out."""

    server = tmp_path / "chatty_server.py"
    server.write_text(_CHATTY_SERVER.format(volume=volume), encoding="utf-8")
    port = _free_port()

    probe = verification._probe(
        [sys.executable, str(server), str(port), "demo-service"],
        tmp_path,
        port,
        language="rust",
        expected_service="demo-service",
        startup_timeout_seconds=20,
    )

    assert probe["status"] == "PASSED"
    assert probe["integration_status"] == "NOT_RUN"


def test_the_reported_output_is_still_bounded(tmp_path: Path) -> None:
    """Draining must not turn a 200 KB startup log into a 200 KB result."""

    server = tmp_path / "chatty_server.py"
    server.write_text(_CHATTY_SERVER.format(volume=200_000), encoding="utf-8")
    port = _free_port()

    probe = verification._probe(
        [sys.executable, str(server), str(port), "demo-service"],
        tmp_path,
        port,
        language="rust",
        expected_service="demo-service",
        startup_timeout_seconds=20,
    )

    assert len(probe["output"]) <= verification._PROBE_OUTPUT_TAIL_CHARACTERS + 512


def test_the_drain_keeps_the_tail_not_the_head() -> None:
    """Asserted on the reader directly, so the boundary is pinned even if no
    fixture happens to cross it."""

    import io

    sink: list[str] = []
    verification._drain_tail(io.StringIO("HEAD" + "." * 50_000 + "TAIL"), sink, 100)

    assert len(sink) == 1
    assert sink[0].endswith("TAIL")
    assert "HEAD" not in sink[0]
    assert len(sink[0]) == 100


def test_the_drain_survives_a_stream_closed_under_it() -> None:
    """Shutting the child down closes the pipe while the reader is inside
    `read`. That must end the reader, not raise out of a daemon thread."""

    import io

    class ClosedMidRead(io.StringIO):
        def read(self, *args: object) -> str:
            raise ValueError("I/O operation on closed file")

    sink: list[str] = []
    verification._drain_tail(ClosedMidRead(), sink, 100)
    assert sink == [""]


# --------------------------------------------------- the configured timeout ----

def test_the_environment_supplies_the_default_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELMOS_PROJECT_SYNTHESIS_COMMAND_TIMEOUT_SECONDS", "450")
    assert verification._configured_command_timeout_seconds() == 450


def test_an_explicit_argument_still_beats_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The env var is the DEFAULT. A caller that decided per-command keeps it."""

    observed: list[float] = []

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed.append(float(kwargs["timeout"]))
        return subprocess.CompletedProcess(["x"], 0, stdout="ok", stderr="")

    monkeypatch.setenv("ELMOS_PROJECT_SYNTHESIS_COMMAND_TIMEOUT_SECONDS", "600")
    monkeypatch.setattr(verification.subprocess, "run", run)
    verification._run(["x"], tmp_path, language="test-runtime", timeout_seconds=45)

    assert observed == [45.0]


def test_an_unset_environment_keeps_the_documented_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: list[float] = []

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed.append(float(kwargs["timeout"]))
        return subprocess.CompletedProcess(["x"], 0, stdout="ok", stderr="")

    monkeypatch.delenv("ELMOS_PROJECT_SYNTHESIS_COMMAND_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr(verification.subprocess, "run", run)
    verification._run(["x"], tmp_path, language="test-runtime")

    assert observed == [float(verification._DEFAULT_COMMAND_TIMEOUT_SECONDS)]


@pytest.mark.parametrize("configured", ["29", "901", "0", "-1"])
def test_an_out_of_range_configured_timeout_fails_before_executing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    """Fails closed BEFORE the command runs -- the range gate is one place, so
    a configured value and a passed value are refused identically."""

    monkeypatch.setenv("ELMOS_PROJECT_SYNTHESIS_COMMAND_TIMEOUT_SECONDS", configured)

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("the command must not be executed")

    monkeypatch.setattr(verification.subprocess, "run", run)
    with pytest.raises(ValueError, match="COMMAND_TIMEOUT_OUT_OF_RANGE"):
        verification._run(["x"], tmp_path, language="test-runtime")


def test_a_non_numeric_configured_timeout_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ELMOS_PROJECT_SYNTHESIS_COMMAND_TIMEOUT_SECONDS", "soon")
    with pytest.raises(ValueError, match="COMMAND_TIMEOUT_NOT_AN_INTEGER"):
        verification._run(["x"], tmp_path, language="test-runtime")


# ------------------------------------------------------------- the retry ----

def _counting_run(results: list[subprocess.CompletedProcess[str]], attempts: list[int]):
    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        attempts.append(1)
        return results[min(len(attempts) - 1, len(results) - 1)]
    return run


def test_only_a_locked_sync_is_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unlocked resolution could install something different on the second
    try, so it is never retried even on the same fetch failure."""

    attempts: list[int] = []
    monkeypatch.setattr(
        verification.subprocess,
        "run",
        _counting_run(
            [subprocess.CompletedProcess(["uv"], 1, stdout="", stderr="Failed to fetch package")],
            attempts,
        ),
    )
    monkeypatch.setattr(verification.time, "sleep", lambda _: None)

    verification._run(["uv", "sync"], tmp_path, language="python")
    assert len(attempts) == 1


def test_another_language_is_not_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[int] = []
    monkeypatch.setattr(
        verification.subprocess,
        "run",
        _counting_run(
            [subprocess.CompletedProcess(["gradle"], 1, stdout="", stderr="Failed to fetch")],
            attempts,
        ),
    )
    monkeypatch.setattr(verification.time, "sleep", lambda _: None)

    verification._run(["gradle", "sync", "--locked"], tmp_path, language="kotlin")
    assert len(attempts) == 1


def test_the_retry_happens_at_most_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A network that is down stays down; retrying it forever turns a failure
    into a hang."""

    attempts: list[int] = []
    monkeypatch.setattr(
        verification.subprocess,
        "run",
        _counting_run(
            [subprocess.CompletedProcess(["uv"], 1, stdout="", stderr="Failed to fetch package")],
            attempts,
        ),
    )
    monkeypatch.setattr(verification.time, "sleep", lambda _: None)

    result = verification._run(["uv", "sync", "--locked"], tmp_path, language="python")
    assert len(attempts) == 2
    assert result["status"] == "FAILED"


def test_a_retried_pass_still_shows_the_first_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A green result that needed a retry must not look identical to one that
    succeeded first time."""

    attempts: list[int] = []
    monkeypatch.setattr(
        verification.subprocess,
        "run",
        _counting_run(
            [
                subprocess.CompletedProcess(["uv"], 1, stdout="", stderr="Failed to fetch package"),
                subprocess.CompletedProcess(["uv"], 0, stdout="resolved", stderr=""),
            ],
            attempts,
        ),
    )
    monkeypatch.setattr(verification.time, "sleep", lambda _: None)

    result = verification._run(["uv", "sync", "--locked"], tmp_path, language="python")
    assert result["status"] == "PASSED"
    assert "TRANSIENT_DEPENDENCY_FETCH_RETRY:1/1" in result["output"]
    assert "Failed to fetch package" in result["output"]
    assert "resolved" in result["output"]
