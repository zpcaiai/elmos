#!/usr/bin/env python3
"""Run one ELMOS engine through its repository-owned test contract.

The registry is explicit on purpose.  The engines use several build systems and
dependency layouts; guessing from the presence of a pyproject.toml or pom.xml
has repeatedly produced false failures.  This runner provides one stable
entrypoint while preserving each engine's real command.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final, TextIO

ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY: Final = ROOT / "scripts/operations/engine-test-registry.json"
REGISTRY_SCHEMA: Final = "elmos.engine-test-registry.v1"
RESULT_SCHEMA: Final = "elmos.engine-test-result.v1"
ALLOWED_KINDS: Final = frozenset({"pytest", "maven", "dotnet", "command"})
ALLOWED_ENGINE_FIELDS: Final = frozenset({"description", "steps"})
ALLOWED_STEP_FIELDS: Final = frozenset(
    {
        "name",
        "kind",
        "timeout_seconds",
        "project",
        "tests",
        "uv_args",
        "pythonpath",
        "module",
        "goals",
        "solution",
        "configuration",
        "argv",
        "environment",
    }
)
PYTEST_SUMMARY = re.compile(
    r"(?m)^(?:=+\s*)?"
    r"(?=[^\n]*\b(?:passed|failed|errors?|skipped|xfailed|xpassed)\b)"
    r"(?P<summary>"
    r"\d+\s+(?:passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?)"
    r"(?:,\s*\d+\s+(?:passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?))*"
    r"\s+in\s+[0-9.]+s"
    r")"
)
PYTEST_FAILURE_LINE = re.compile(r"(?m)^(?:FAILED|ERROR)(?:\s|$)")
ENVIRONMENT_MARKERS: Final = (
    "no solution found when resolving dependencies",
    "failed to download",
    "failed to fetch",
    "could not resolve host",
    "connection refused",
    "network is unreachable",
    "command not found",
    "no such file or directory",
    "requires python",
    "toolchain platform mismatch",
    "exact toolchain mismatch",
)


class RegistryError(ValueError):
    """The engine test registry is incomplete or unsafe."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise RegistryError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _relative_path(raw: Any, field: str, *, directory: bool | None = None) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise RegistryError(f"{field} must be a non-empty relative POSIX path")
    path = PurePosixPath(raw)
    if path.is_absolute() or str(path) != raw or any(part in {"", ".", ".."} for part in path.parts):
        raise RegistryError(f"{field} must be normalized and repository-confined")
    candidate = ROOT / raw
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(ROOT)
    except (OSError, ValueError) as exc:
        raise RegistryError(f"{field} does not resolve inside the repository: {raw}") from exc
    if directory is True and not resolved.is_dir():
        raise RegistryError(f"{field} must be a directory: {raw}")
    if directory is False and not resolved.is_file():
        raise RegistryError(f"{field} must be a file: {raw}")
    return raw


def _string_list(raw: Any, field: str, *, nonempty: bool = True) -> list[str]:
    if not isinstance(raw, list) or (nonempty and not raw):
        raise RegistryError(f"{field} must be a{' non-empty' if nonempty else ''} string array")
    if any(not isinstance(item, str) or not item or "\x00" in item for item in raw):
        raise RegistryError(f"{field} must contain non-empty strings")
    return list(raw)


def _validate_step(engine: str, index: int, raw: Any) -> dict[str, Any]:
    field = f"engines.{engine}.steps[{index}]"
    if not isinstance(raw, dict):
        raise RegistryError(f"{field} must be an object")
    extra = sorted(set(raw) - ALLOWED_STEP_FIELDS)
    if extra:
        raise RegistryError(f"{field} has unknown fields: {extra}")
    name = raw.get("name")
    kind = raw.get("kind")
    timeout = raw.get("timeout_seconds")
    if not isinstance(name, str) or not name or len(name) > 120:
        raise RegistryError(f"{field}.name is invalid")
    if kind not in ALLOWED_KINDS:
        raise RegistryError(f"{field}.kind is invalid: {kind}")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 43_200:
        raise RegistryError(f"{field}.timeout_seconds must be between 1 and 43200")

    step = dict(raw)
    environment = step.get("environment", {})
    if not isinstance(environment, dict) or any(
        not isinstance(key, str)
        or not key
        or not isinstance(value, str)
        or "\x00" in key
        or "\x00" in value
        for key, value in environment.items()
    ):
        raise RegistryError(f"{field}.environment must be a string map")
    step["environment"] = dict(environment)

    pythonpath = step.get("pythonpath", [])
    _string_list(pythonpath, f"{field}.pythonpath", nonempty=False)
    step["pythonpath"] = [
        _relative_path(path, f"{field}.pythonpath", directory=True) for path in pythonpath
    ]

    if kind == "pytest":
        project = step.get("project")
        if project is not None:
            step["project"] = _relative_path(project, f"{field}.project", directory=True)
        step["tests"] = [
            _relative_path(path, f"{field}.tests", directory=None)
            for path in _string_list(step.get("tests"), f"{field}.tests")
        ]
        step["uv_args"] = _string_list(
            step.get("uv_args", []), f"{field}.uv_args", nonempty=False
        )
    elif kind == "maven":
        step["module"] = _relative_path(step.get("module"), f"{field}.module", directory=True)
        step["goals"] = _string_list(step.get("goals", ["verify"]), f"{field}.goals")
    elif kind == "dotnet":
        step["solution"] = _relative_path(
            step.get("solution"), f"{field}.solution", directory=False
        )
        configuration = step.get("configuration", "Release")
        if not isinstance(configuration, str) or not configuration:
            raise RegistryError(f"{field}.configuration is invalid")
        step["configuration"] = configuration
    else:
        step["argv"] = _string_list(step.get("argv"), f"{field}.argv")
    return step


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, dict[str, Any]]:
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                RegistryError(f"forbidden JSON constant: {token}")
            ),
        )
    except RegistryError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RegistryError(f"cannot read engine test registry: {exc}") from exc
    if not isinstance(document, dict) or set(document) != {"schema_version", "engines"}:
        raise RegistryError("registry fields must be exactly schema_version and engines")
    if document["schema_version"] != REGISTRY_SCHEMA:
        raise RegistryError(f"registry schema must be {REGISTRY_SCHEMA}")
    raw_engines = document["engines"]
    if not isinstance(raw_engines, dict) or not raw_engines:
        raise RegistryError("engines must be a non-empty object")

    actual_engines = {
        path.name
        for path in (ROOT / "engines").iterdir()
        if path.is_dir() and not path.is_symlink() and not path.name.startswith(".")
    }
    declared_engines = set(raw_engines)
    if declared_engines != actual_engines:
        raise RegistryError(
            "registry must cover every engine exactly once: "
            f"missing={sorted(actual_engines - declared_engines)} "
            f"extra={sorted(declared_engines - actual_engines)}"
        )

    engines: dict[str, dict[str, Any]] = {}
    for engine in sorted(raw_engines):
        raw = raw_engines[engine]
        if not isinstance(raw, dict) or set(raw) != ALLOWED_ENGINE_FIELDS:
            raise RegistryError(
                f"engines.{engine} fields must be exactly {sorted(ALLOWED_ENGINE_FIELDS)}"
            )
        description = raw["description"]
        if not isinstance(description, str) or not description or len(description) > 240:
            raise RegistryError(f"engines.{engine}.description is invalid")
        steps_raw = raw["steps"]
        if not isinstance(steps_raw, list) or not steps_raw:
            raise RegistryError(f"engines.{engine}.steps must not be empty")
        steps = [_validate_step(engine, index, item) for index, item in enumerate(steps_raw)]
        step_names = [item["name"] for item in steps]
        if len(step_names) != len(set(step_names)):
            raise RegistryError(f"engines.{engine} has duplicate step names")
        engines[engine] = {"description": description, "steps": steps}
    return engines


@dataclass(frozen=True)
class StepResult:
    name: str
    kind: str
    verdict: str
    exit_code: int | None
    elapsed_seconds: float
    summary: str | None
    log_path: str

    @property
    def passed(self) -> bool:
        return self.verdict in {"PASSED", "PASSED_WITH_SKIPS"}


def classify_pytest(exit_code: int | None, output: str, *, timed_out: bool = False) -> tuple[str, str | None]:
    summaries = [match.group("summary") for match in PYTEST_SUMMARY.finditer(output)]
    summary = summaries[-1] if summaries else None
    lowered = output.lower()
    if timed_out:
        return "TIMEOUT", summary
    if exit_code is None:
        return "ENVIRONMENT", summary
    if exit_code == 2:
        return "COLLECTION_ERROR", summary
    if exit_code in {3, 4}:
        return "PYTEST_INTERNAL_ERROR", summary
    if exit_code == 5:
        return "NO_TESTS_COLLECTED", summary
    if PYTEST_FAILURE_LINE.search(output):
        return "FAILED", summary
    if summary is None and any(marker in lowered for marker in ENVIRONMENT_MARKERS):
        return "ENVIRONMENT", None
    if exit_code != 0:
        return "FAILED", summary
    if summary is None:
        return "NO_SUMMARY", None
    statuses = re.findall(
        r"\d+\s+(passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?)",
        summary,
    )
    if any(status in {"failed", "error", "errors"} for status in statuses):
        return "FAILED", summary
    if "passed" not in statuses:
        return "PASSED_WITH_SKIPS", summary
    return "PASSED", summary


def classify_command(exit_code: int | None, output: str, *, timed_out: bool = False) -> str:
    if timed_out:
        return "TIMEOUT"
    if exit_code is None:
        return "ENVIRONMENT"
    if exit_code == 0:
        return "PASSED"
    if any(marker in output.lower() for marker in ENVIRONMENT_MARKERS):
        return "ENVIRONMENT"
    return "FAILED"


def _expand(value: str, engine: str, run_root: Path) -> str:
    return value.format(
        repo=str(ROOT),
        engine=engine,
        engine_dir=str(ROOT / "engines" / engine),
        run_root=str(run_root),
    )


def build_command(
    engine: str,
    step: dict[str, Any],
    run_root: Path,
    *,
    uv: str,
    maven: str,
    dotnet: str,
) -> list[str]:
    kind = step["kind"]
    if kind == "pytest":
        command = [uv, "run"]
        if step.get("project") is not None:
            command.extend(["--project", str(ROOT / step["project"])])
        else:
            command.append("--no-project")
        command.extend(_expand(item, engine, run_root) for item in step["uv_args"])
        command.extend(
            [
                "python",
                "-m",
                "pytest",
                *(str(ROOT / path) for path in step["tests"]),
                "-rfE",
                "-o",
                "addopts=",
                "--basetemp",
                str(run_root / "pytest"),
                "-p",
                "no:cacheprovider",
            ]
        )
        return command
    if kind == "maven":
        return [
            maven,
            "-B",
            "-ntp",
            "-pl",
            step["module"],
            "-am",
            *step["goals"],
        ]
    if kind == "dotnet":
        return [
            dotnet,
            "test",
            step["solution"],
            "--configuration",
            step["configuration"],
        ]
    return [_expand(item, engine, run_root) for item in step["argv"]]


def _stream_process(
    command: list[str],
    *,
    environment: dict[str, str],
    timeout_seconds: int,
    log: TextIO,
) -> tuple[int | None, str, bool]:
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
        )
    except OSError as exc:
        message = f"cannot start command: {type(exc).__name__}: {exc}\n"
        sys.stdout.write(message)
        log.write(message)
        return None, message, False

    output: list[str] = []
    timed_out = False
    assert process.stdout is not None

    def copy_output() -> None:
        for line in process.stdout:
            output.append(line)
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()

    reader = threading.Thread(
        target=copy_output,
        name=f"engine-test-output-{process.pid}",
        daemon=True,
    )
    reader.start()
    try:
        exit_code = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(process.pid, signal.SIGTERM)
            exit_code = process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            exit_code = process.wait()
    reader.join(timeout=5)
    if reader.is_alive():
        warning = "\nengine test output reader did not terminate cleanly\n"
        output.append(warning)
        log.write(warning)
    return exit_code, "".join(output), timed_out


def run_step(
    engine: str,
    step: dict[str, Any],
    run_root: Path,
    *,
    uv: str,
    maven: str,
    dotnet: str,
    java_home: str | None,
) -> StepResult:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", step["name"]).strip("-") or "step"
    log_path = run_root / f"{slug}.log"
    command = build_command(engine, step, run_root, uv=uv, maven=maven, dotnet=dotnet)
    venv_root = run_root.parents[2] / "venvs" / engine
    environment = dict(os.environ)
    for inherited in (
        "CONDA_PREFIX",
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
        "PYTHONHOME",
        "PYTHONPATH",
        "UV_PROJECT",
        "UV_PROJECT_ENVIRONMENT",
        "UV_PYTHON",
        "UV_WORKING_DIRECTORY",
        "VIRTUAL_ENV",
    ):
        environment.pop(inherited, None)
    environment["PATH"] = os.pathsep.join(
        part for part in environment.get("PATH", "").split(os.pathsep) if part
    )
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": str(run_root / "tmp"),
            "UV_PROJECT_ENVIRONMENT": str(venv_root),
        }
    )
    python_paths = [str(ROOT / item) for item in step["pythonpath"]]
    if python_paths:
        environment["PYTHONPATH"] = os.pathsep.join(python_paths)
    environment.update(
        {key: _expand(value, engine, run_root) for key, value in step["environment"].items()}
    )
    if step["kind"] == "maven" and java_home:
        environment["JAVA_HOME"] = java_home
    (run_root / "tmp").mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write(f"cwd={ROOT}\n")
        log.write("command=" + json.dumps(command, ensure_ascii=False) + "\n")
        log.flush()
        print(f"\n[{engine}] {step['name']}")
        print("  " + " ".join(command))
        exit_code, output, timed_out = _stream_process(
            command,
            environment=environment,
            timeout_seconds=step["timeout_seconds"],
            log=log,
        )
    elapsed = time.monotonic() - started
    if step["kind"] == "pytest":
        verdict, summary = classify_pytest(exit_code, output, timed_out=timed_out)
    else:
        verdict = classify_command(exit_code, output, timed_out=timed_out)
        summary = None
    return StepResult(
        name=step["name"],
        kind=step["kind"],
        verdict=verdict,
        exit_code=exit_code,
        elapsed_seconds=round(elapsed, 3),
        summary=summary,
        log_path=str(log_path),
    )


def _write_result(path: Path, engine: str, results: list[StepResult]) -> None:
    document = {
        "schema_version": RESULT_SCHEMA,
        "engine": engine,
        "repository_root": str(ROOT),
        "passed": all(result.passed for result in results),
        "steps": [
            {
                "name": result.name,
                "kind": result.kind,
                "verdict": result.verdict,
                "exit_code": result.exit_code,
                "elapsed_seconds": result.elapsed_seconds,
                "summary": result.summary,
                "log_path": result.log_path,
            }
            for result in results
        ],
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", nargs="?", help="engine directory name")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--check", action="store_true", help="validate registry coverage only")
    parser.add_argument("--list", action="store_true", help="list registered engines")
    parser.add_argument("--all", action="store_true", help="run all registered engines sequentially")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path.home() / ".cache/elmos-engine-tests",
        help="logs, temp files and environments (must be outside the repository)",
    )
    parser.add_argument("--uv", default=os.environ.get("UV", "uv"))
    parser.add_argument("--maven", default=os.environ.get("MAVEN", "mvn"))
    parser.add_argument("--dotnet", default=os.environ.get("DOTNET", "dotnet"))
    parser.add_argument(
        "--java-home",
        default=os.environ.get("JAVA_21_HOME") or os.environ.get("JAVA_HOME"),
    )
    parser.add_argument("--clean", action="store_true", help="remove each run environment after recording results")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        engines = load_registry(arguments.registry)
        output_root = arguments.output_root.expanduser().resolve()
        try:
            output_root.relative_to(ROOT)
        except ValueError:
            pass
        else:
            raise RegistryError("output root must be outside the repository")
    except RegistryError as exc:
        print(f"ENGINE_TEST_REGISTRY_INVALID: {exc}", file=sys.stderr)
        return 2

    if arguments.check:
        print(f"ENGINE_TEST_REGISTRY_OK engines={len(engines)} steps={sum(len(v['steps']) for v in engines.values())}")
        return 0
    if arguments.list:
        for name, contract in engines.items():
            print(f"{name}\t{len(contract['steps'])}\t{contract['description']}")
        return 0
    if arguments.all and arguments.engine:
        print("choose either one engine or --all", file=sys.stderr)
        return 2
    selected = list(engines) if arguments.all else [arguments.engine or os.environ.get("ENGINE", "")]
    if not selected or not selected[0]:
        print("ENGINE is required; pass a name or use --all", file=sys.stderr)
        return 2
    unknown = sorted(set(selected) - set(engines))
    if unknown:
        print(f"unknown engine(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    output_root.mkdir(parents=True, exist_ok=True)
    overall = True
    for engine in selected:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        run_root = output_root / "runs" / engine / f"{stamp}-{os.getpid()}"
        run_root.mkdir(parents=True, mode=0o700)
        results: list[StepResult] = []
        for step in engines[engine]["steps"]:
            result = run_step(
                engine,
                step,
                run_root,
                uv=arguments.uv,
                maven=arguments.maven,
                dotnet=arguments.dotnet,
                java_home=arguments.java_home,
            )
            results.append(result)
            print(
                f"[{engine}] {result.name}: {result.verdict}"
                + (f" ({result.summary})" if result.summary else "")
            )
            if not result.passed:
                break
        result_path = run_root / "result.json"
        _write_result(result_path, engine, results)
        passed = len(results) == len(engines[engine]["steps"]) and all(
            item.passed for item in results
        )
        overall = overall and passed
        print(f"[{engine}] {'PASSED' if passed else 'FAILED'} result={result_path}")
        if arguments.clean:
            shutil.rmtree(output_root / "venvs" / engine, ignore_errors=True)
            shutil.rmtree(run_root / "tmp", ignore_errors=True)
            shutil.rmtree(run_root / "pytest", ignore_errors=True)
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
