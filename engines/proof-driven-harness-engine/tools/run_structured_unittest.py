#!/usr/bin/env python3
"""Run unittest discovery and emit selector- and source-bound outcomes.

This is a bounded local engineering runner.  Its output is self-attested; it
does not provide independent verification or certification evidence.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import stat
import time
from typing import Any, Sequence
import unittest


MAX_SOURCE_BYTES = 16 * 1024 * 1024


class StructuredRunnerError(RuntimeError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_source(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SOURCE_BYTES:
            raise StructuredRunnerError(f"unsafe or oversized test source: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        payload = b"".join(chunks)
        if identity_before != identity_after or len(payload) != before.st_size:
            raise StructuredRunnerError(f"test source changed while reading: {path}")
        return payload
    finally:
        os.close(descriptor)


class StructuredResult(unittest.TextTestResult):
    def __init__(self, *args: Any, repository_root: Path, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.repository_root = repository_root
        self.outcomes: list[dict[str, Any]] = []
        self._started: dict[str, int] = {}
        self._recorded: set[str] = set()

    def startTest(self, test: unittest.case.TestCase) -> None:  # noqa: N802
        self._started[test.id()] = time.monotonic_ns()
        super().startTest(test)

    def _source_binding(self, test: unittest.case.TestCase) -> dict[str, str]:
        source = inspect.getsourcefile(test.__class__)
        if source is None:
            raise StructuredRunnerError(f"test source is unavailable: {test.id()}")
        source_path = Path(source).resolve(strict=True)
        try:
            relative = source_path.relative_to(self.repository_root)
        except ValueError as exc:
            raise StructuredRunnerError(
                f"test source escapes repository root: {test.id()}"
            ) from exc
        payload = _safe_source(source_path)
        source_digest = "sha256:" + _sha256(payload)
        selector = test.id()
        binding = {
            "selector": selector,
            "source_path": relative.as_posix(),
            "source_sha256": source_digest,
        }
        return {
            **binding,
            "selector_source_binding_sha256": "sha256:"
            + _sha256(canonical_bytes(binding)),
        }

    def _record(
        self,
        test: unittest.case.TestCase,
        status: str,
        detail: str = "",
    ) -> None:
        selector = test.id()
        if selector in self._recorded:
            return
        self._recorded.add(selector)
        started = self._started.get(selector, time.monotonic_ns())
        outcome = {
            **self._source_binding(test),
            "status": status,
            "duration_milliseconds": max(
                0, (time.monotonic_ns() - started) // 1_000_000
            ),
        }
        if detail:
            outcome["detail"] = detail[-16384:]
        self.outcomes.append(outcome)

    def addSuccess(self, test: unittest.case.TestCase) -> None:  # noqa: N802
        super().addSuccess(test)
        self._record(test, "PASSED")

    def addFailure(self, test: unittest.case.TestCase, err: Any) -> None:  # noqa: N802
        super().addFailure(test, err)
        self._record(test, "FAILED", self._exc_info_to_string(err, test))

    def addError(self, test: unittest.case.TestCase, err: Any) -> None:  # noqa: N802
        super().addError(test, err)
        self._record(test, "ERROR", self._exc_info_to_string(err, test))

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:  # noqa: N802
        super().addSkip(test, reason)
        self._record(test, "SKIPPED", reason)

    def addExpectedFailure(self, test: unittest.case.TestCase, err: Any) -> None:  # noqa: N802
        super().addExpectedFailure(test, err)
        self._record(test, "EXPECTED_FAILURE", self._exc_info_to_string(err, test))

    def addUnexpectedSuccess(self, test: unittest.case.TestCase) -> None:  # noqa: N802
        super().addUnexpectedSuccess(test)
        self._record(test, "UNEXPECTED_SUCCESS")


def run(repository_root: Path, start_directory: str, pattern: str) -> dict[str, Any]:
    repository_root = repository_root.resolve(strict=True)
    start = (repository_root / start_directory).resolve(strict=True)
    try:
        relative_start = start.relative_to(repository_root)
    except ValueError as exc:
        raise StructuredRunnerError("test discovery directory escapes repository root") from exc
    if start.is_symlink() or not start.is_dir():
        raise StructuredRunnerError("test discovery directory must be a real directory")
    if not pattern or "/" in pattern or "\\" in pattern:
        raise StructuredRunnerError("test discovery pattern is invalid")

    suite = unittest.defaultTestLoader.discover(
        start_dir=str(start),
        pattern=pattern,
    )
    selected = suite.countTestCases()
    if selected <= 0:
        raise StructuredRunnerError("test discovery selected no tests")
    runner_stream = io.StringIO()
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()

    class BoundResult(StructuredResult):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, repository_root=repository_root, **kwargs)

    runner = unittest.TextTestRunner(
        stream=runner_stream,
        verbosity=2,
        resultclass=BoundResult,
    )
    with redirect_stdout(captured_stdout), redirect_stderr(captured_stderr):
        result = runner.run(suite)
    assert isinstance(result, StructuredResult)
    outcomes = sorted(result.outcomes, key=lambda item: item["selector"])
    if len(outcomes) != selected:
        raise StructuredRunnerError(
            f"structured outcome count mismatch: selected={selected}, outcomes={len(outcomes)}"
        )
    counts = {
        status: sum(item["status"] == status for item in outcomes)
        for status in (
            "PASSED",
            "FAILED",
            "ERROR",
            "SKIPPED",
            "EXPECTED_FAILURE",
            "UNEXPECTED_SUCCESS",
        )
    }
    status = "PASS"
    if counts["FAILED"] or counts["ERROR"] or counts["UNEXPECTED_SUCCESS"]:
        status = "FAIL"
    elif counts["SKIPPED"] or counts["EXPECTED_FAILURE"]:
        status = "PASS_WITH_NONPASSING_OUTCOMES"
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.proof-harness.structured-unittest-results",
        "status": status,
        "discovery": {
            "start_directory": relative_start.as_posix(),
            "pattern": pattern,
        },
        "totals": {
            "selected": selected,
            "passed": counts["PASSED"],
            "failed": counts["FAILED"],
            "errors": counts["ERROR"],
            "skipped": counts["SKIPPED"],
            "expected_failures": counts["EXPECTED_FAILURE"],
            "unexpected_successes": counts["UNEXPECTED_SUCCESS"],
        },
        "outcomes": outcomes,
        "runner_output": runner_stream.getvalue(),
        "captured_stdout": captured_stdout.getvalue(),
        "captured_stderr": captured_stderr.getvalue(),
        "evidence_boundary": {
            "classification": "LOCAL_EXECUTED_SELF_ATTESTED",
            "external_evidence": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", type=Path)
    parser.add_argument("--start-directory", required=True)
    parser.add_argument("--pattern", default="test_*.py")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run(args.repo_root, args.start_directory, args.pattern)
    except (OSError, ValueError, StructuredRunnerError) as exc:
        print(
            json.dumps(
                {
                    "kind": "elmos.proof-harness.structured-unittest-results",
                    "status": "FAIL",
                    "error": str(exc),
                    "certification": "NOT_CERTIFIED",
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
