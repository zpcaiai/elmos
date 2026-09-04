#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from elmos_project_synthesis.models import SUPPORTED_LANGUAGES, SUPPORTED_PROFILE_TARGETS

SCRIPT = Path(__file__).with_name("run_production_acceptance.py").resolve()
AUTH_MODES = ("jwt", "oidc")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run every selected PostgreSQL production profile through its native integration scenario."
    )
    parser.add_argument("--language", action="append", choices=SUPPORTED_LANGUAGES)
    parser.add_argument("--auth-mode", action="append", choices=AUTH_MODES)
    parser.add_argument(
        "--output",
        type=Path,
        help="Atomically write the local engineering evidence JSON to this path.",
    )
    return parser.parse_args()


def matrix_cases(
    languages: Sequence[str] | None = None,
    auth_modes: Sequence[str] | None = None,
) -> tuple[tuple[str, str], ...]:
    selected_languages = tuple(languages or SUPPORTED_LANGUAGES)
    selected_auth_modes = tuple(auth_modes or AUTH_MODES)
    if len(set(selected_languages)) != len(selected_languages):
        raise ValueError("DUPLICATE_LANGUAGE")
    if len(set(selected_auth_modes)) != len(selected_auth_modes):
        raise ValueError("DUPLICATE_AUTH_MODE")
    for language in selected_languages:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"UNSUPPORTED_LANGUAGE:{language}")
    for auth_mode in selected_auth_modes:
        if auth_mode not in AUTH_MODES:
            raise ValueError(f"UNSUPPORTED_AUTH_MODE:{auth_mode}")
        opened = SUPPORTED_PROFILE_TARGETS[("postgresql", auth_mode)]
        missing = set(selected_languages) - set(opened)
        if missing:
            raise ValueError(
                f"PRODUCTION_PROFILE_NOT_OPEN:{auth_mode}:{','.join(sorted(missing))}"
            )
    return tuple(
        (language, auth_mode)
        for language in selected_languages
        for auth_mode in selected_auth_modes
    )


def run_case(language: str, auth_mode: str) -> dict[str, Any]:
    command = [
        sys.executable,
        str(SCRIPT),
        "--language",
        language,
        "--auth-mode",
        auth_mode,
    ]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned script
            command,
            cwd=SCRIPT.parent.parent,
            check=False,
            text=True,
            capture_output=True,
            timeout=int(os.environ.get("PRODUCTION_ACCEPTANCE_TIMEOUT", "1800")),
        )
    except subprocess.TimeoutExpired as error:
        return {
            "status": "FAILED",
            "language": language,
            "auth_mode": auth_mode,
            "reason": "PRODUCTION_ACCEPTANCE_TIMEOUT",
            "output": str(error.stdout or "")[-4_000:],
        }
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "status": "FAILED",
            "language": language,
            "auth_mode": auth_mode,
            "reason": "PRODUCTION_ACCEPTANCE_RESULT_INVALID",
            "exit_code": completed.returncode,
            "output": (completed.stdout + completed.stderr)[-4_000:],
        }
    if not isinstance(result, dict):
        return {
            "status": "FAILED",
            "language": language,
            "auth_mode": auth_mode,
            "reason": "PRODUCTION_ACCEPTANCE_RESULT_INVALID",
            "exit_code": completed.returncode,
        }
    result["exit_code"] = completed.returncode
    if completed.returncode != 0:
        result["status"] = "FAILED"
    return result


def run_matrix(
    languages: Sequence[str] | None = None,
    auth_modes: Sequence[str] | None = None,
    *,
    executor: Callable[[str, str], dict[str, Any]] = run_case,
) -> dict[str, Any]:
    cases = matrix_cases(languages, auth_modes)
    results: list[dict[str, Any]] = []
    for index, (language, auth_mode) in enumerate(cases, start=1):
        print(
            f"[{index}/{len(cases)}] production acceptance: {language}/{auth_mode}",
            file=sys.stderr,
            flush=True,
        )
        results.append(executor(language, auth_mode))
    failures = [
        result
        for result in results
        if not isinstance(result.get("startup_probes"), list)
        or len(result["startup_probes"]) != 1
        or result.get("status") != "PASSED"
        or result.get("cleanup_status") != "PASSED"
        or any(
            probe.get("status") != "PASSED"
            or probe.get("integration_status") != "PASSED"
            for probe in result["startup_probes"]
            if isinstance(probe, dict)
        )
        or any(not isinstance(probe, dict) for probe in result["startup_probes"])
    ]
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.local-production-profile-matrix",
        "observed_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "status": "FAILED" if failures else "PASSED",
        "case_count": len(cases),
        "passed_count": len(cases) - len(failures),
        "languages": list(dict.fromkeys(language for language, _ in cases)),
        "auth_modes": list(dict.fromkeys(auth_mode for _, auth_mode in cases)),
        "cases": results,
        "failures": failures,
        "evidence_class": "LOCAL_ENGINEERING",
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
        "replay": (
            "uv --directory engines/project-synthesis-engine run --locked "
            "python scripts/run_production_matrix.py"
        ),
        "production_delivery_status": "NOT_RUN",
        "independent_verification_status": "NOT_RUN",
        "external_certification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }


def write_evidence(path: Path, result: dict[str, Any]) -> None:
    target = path.expanduser()
    if target.suffix != ".json":
        raise ValueError("PRODUCTION_MATRIX_OUTPUT_MUST_BE_JSON")
    if target.is_symlink():
        raise ValueError("PRODUCTION_MATRIX_OUTPUT_SYMLINK_REFUSED")
    parent = target.parent.resolve(strict=True)
    target = parent / target.name
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=parent,
            prefix=f".{target.name}.",
            delete=False,
        ) as temporary:
            json.dump(result, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, target)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def main() -> int:
    arguments = parse_args()
    try:
        result = run_matrix(arguments.language, arguments.auth_mode)
    except ValueError as error:
        result = {
            "schema_version": "1.0.0",
            "kind": "elmos.local-production-profile-matrix",
            "status": "FAILED",
            "reason": str(error),
            "evidence_class": "LOCAL_ENGINEERING",
            "production_delivery_status": "NOT_RUN",
            "independent_verification_status": "NOT_RUN",
            "external_certification_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }
    if arguments.output is not None:
        try:
            write_evidence(arguments.output, result)
        except (OSError, ValueError) as error:
            result["status"] = "FAILED"
            result["evidence_write_error"] = str(error)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
