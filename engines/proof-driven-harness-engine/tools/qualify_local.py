#!/usr/bin/env python3
"""Run bounded local qualification and emit a digest-bound receipt.

This script executes only repository-owned, fixed commands. It never executes
the source ZIP or any repository-under-analysis. The receipt is self-attested
local engineering evidence and cannot authorize an external effect or
certification decision.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any


PACKAGE_NAME = "elmos-proof-driven-agentic-harness-repository-semantic-compiler"
PACKAGE_VERSION = "3.0.0"
ARCHIVE_SHA256 = "552268611c3edc55f58c6d4d488adaaeda8a549212cc5dc52c06e4333e0c3e07"
ENGINE_RELATIVE = Path("engines/proof-driven-harness-engine")
QUALIFIER_RELATIVE = ENGINE_RELATIVE / "tools/qualify_local.py"
STRUCTURED_RUNNER_RELATIVE = ENGINE_RELATIVE / "tools/run_structured_unittest.py"
POSTGRES_TEST_RELATIVE = ENGINE_RELATIVE / "tests/postgres17_integration.py"
RECEIPT_RELATIVE = ENGINE_RELATIVE / "qualification/local-qualification.json"
RAW_RELATIVE = ENGINE_RELATIVE / "qualification/raw"
POSTGRES_VERSION = "17.5"
PSYCOPG_VERSION = "3.2.13"
SKILL_NAMES = tuple(
    sorted(
        (
            "elmos-goal-specification-kernel",
            "elmos-repository-intelligence-kernel",
            "elmos-repository-semantic-compiler-kernel",
            "elmos-agentic-reasoning-kernel",
            "elmos-transformation-kernel",
            "elmos-proof-verification-kernel",
            "elmos-harness-runtime-kernel",
            "elmos-certification-kernel",
            "elmos-domain-spring-legacy-modernization",
            "elmos-domain-cross-language-conversion",
            "elmos-domain-multi-language-project-generation",
            "elmos-domain-sql-dialect-routine-conversion",
            "elmos-domain-repository-refactoring",
            "elmos-evaluation-trust-gate",
            "elmos-self-improvement-governance",
            "elmos-commercial-operations-finops",
        )
    )
)
COMPONENT_IDS = tuple(f"K{kernel}-C{component:02d}" for kernel in range(1, 9) for component in range(1, 13))
EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "build",
        "dist",
    }
)


class QualificationError(RuntimeError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_regular_bytes(path: Path) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise QualificationError(f"cannot open regular file safely: {path}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise QualificationError(f"qualification input is not a regular file: {path}")
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
        if identity_before != identity_after:
            raise QualificationError(f"qualification input changed while reading: {path}")
        payload = b"".join(chunks)
        if len(payload) != before.st_size:
            raise QualificationError(f"short read while hashing qualification input: {path}")
        return payload, before
    finally:
        os.close(descriptor)


def _safe_regular_bytes_at(directory_fd: int, name: str, display: str) -> tuple[bytes, os.stat_result]:
    """Read one directory-bound regular file without following links."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise QualificationError(f"cannot open regular file safely: {display}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise QualificationError(f"qualification input is not a regular file: {display}")
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
        if identity_before != identity_after:
            raise QualificationError(f"qualification input changed while reading: {display}")
        payload = b"".join(chunks)
        if len(payload) != before.st_size:
            raise QualificationError(f"short read while hashing qualification input: {display}")
        return payload, before
    finally:
        os.close(descriptor)


def _excluded(relative: PurePosixPath) -> bool:
    if not relative.parts:
        return True
    if relative.parts[0] == "qualification":
        return True
    if any(
        part in EXCLUDED_DIRECTORY_NAMES or part.endswith(".egg-info")
        for part in relative.parts
    ):
        return True
    return (
        relative.name.endswith(".pyc")
        or relative.name == ".coverage"
        or relative.name.startswith(".coverage.")
        or relative.name == "coverage.xml"
    )


def engine_inventory(engine_root: Path) -> list[dict[str, Any]]:
    if engine_root.is_symlink() or not engine_root.is_dir():
        raise QualificationError(f"engine root must be a real directory: {engine_root}")
    records: list[dict[str, Any]] = []
    directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)

    def walk(directory_fd: int, prefix: PurePosixPath) -> None:
        try:
            names = sorted(os.listdir(directory_fd))
        except OSError as exc:
            raise QualificationError(f"cannot enumerate engine tree at {prefix}: {exc}") from exc
        for name in names:
            relative = prefix / name
            if _excluded(relative):
                continue
            try:
                metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError as exc:
                raise QualificationError(f"cannot inspect engine member {relative}: {exc}") from exc
            if stat.S_ISLNK(metadata.st_mode):
                raise QualificationError(f"linked engine member is forbidden: {relative}")
            if stat.S_ISDIR(metadata.st_mode):
                try:
                    child_fd = os.open(name, directory_flags, dir_fd=directory_fd)
                except OSError as exc:
                    raise QualificationError(f"cannot open engine directory {relative}: {exc}") from exc
                try:
                    opened = os.fstat(child_fd)
                    if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                        raise QualificationError(f"engine directory changed while opening: {relative}")
                    walk(child_fd, relative)
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise QualificationError(f"special engine member is forbidden: {relative}")
            payload, opened = _safe_regular_bytes_at(directory_fd, name, relative.as_posix())
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise QualificationError(f"engine member changed while opening: {relative}")
            records.append(
                {
                    "path": relative.as_posix(),
                    "sha256": sha256_bytes(payload),
                    "bytes": len(payload),
                    "mode": format(stat.S_IMODE(opened.st_mode), "04o"),
                }
            )

    root_fd = os.open(engine_root, directory_flags)
    try:
        walk(root_fd, PurePosixPath())
    finally:
        os.close(root_fd)
    records.sort(key=lambda item: item["path"])
    if not records:
        raise QualificationError("engine tree is empty")
    return records


def _ensure_private_output_tree(engine_root: Path) -> tuple[Path, Path]:
    qualification = engine_root / "qualification"
    raw = qualification / "raw"
    directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.open(engine_root, directory_flags)
    try:
        for name, display in (("qualification", qualification), ("raw", raw)):
            try:
                os.mkdir(name, 0o700, dir_fd=parent_fd)
            except FileExistsError:
                pass
            try:
                child_fd = os.open(name, directory_flags, dir_fd=parent_fd)
            except OSError as exc:
                raise QualificationError(f"unsafe qualification output directory: {display}: {exc}") from exc
            metadata = os.fstat(child_fd)
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(child_fd)
                raise QualificationError(f"qualification output is not a directory: {display}")
            if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
                os.close(child_fd)
                raise QualificationError(f"qualification output is not owned by the qualifier user: {display}")
            if stat.S_IMODE(metadata.st_mode) & 0o077:
                try:
                    os.fchmod(child_fd, 0o700)
                except OSError as exc:
                    os.close(child_fd)
                    raise QualificationError(
                        f"cannot make qualification output private: {display}: {exc}"
                    ) from exc
                metadata = os.fstat(child_fd)
                if stat.S_IMODE(metadata.st_mode) & 0o077:
                    os.close(child_fd)
                    raise QualificationError(f"qualification output permissions are too broad: {display}")
            if name == "raw":
                os.close(child_fd)
            else:
                os.close(parent_fd)
                parent_fd = child_fd
    finally:
        os.close(parent_fd)
    return qualification, raw


def _atomic_write(path: Path, payload: bytes) -> None:
    parent = path.parent
    directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_fd = os.open(parent, directory_flags)
    except OSError as exc:
        raise QualificationError(f"unsafe qualification output parent: {parent}: {exc}") from exc
    temporary_name = f".{path.name}.{secrets.token_hex(16)}.tmp"
    descriptor = -1
    try:
        try:
            existing = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            raise QualificationError(f"unsafe qualification output target: {path}")
        create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        create_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary_name, create_flags, 0o600, dir_fd=directory_fd)
        os.fchmod(descriptor, 0o644)
        offset = 0
        while offset < len(payload):
            count = os.write(descriptor, payload[offset:])
            if count <= 0:
                raise QualificationError(f"short write: {path}")
            offset += count
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary_name, path.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)


def _command_environment(
    repository_root: Path,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    allowed = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SYSTEMROOT")
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    engine_source = repository_root / ENGINE_RELATIVE / "src"
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            # The engine source must win import resolution, while the
            # repository root is required for the repository-owned importer
            # integration suite (``tooling`` is intentionally not installed
            # as a third-party package).
            "PYTHONPATH": os.pathsep.join((str(engine_source), str(repository_root))),
            # Proxy-denial reduces accidental HTTP access. It is not a kernel
            # network sandbox and the receipt never claims that it is one.
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "socks5://127.0.0.1:9",
            "http_proxy": "http://127.0.0.1:9",
            "https_proxy": "http://127.0.0.1:9",
            "all_proxy": "socks5://127.0.0.1:9",
            "NO_PROXY": "",
            "no_proxy": "",
            # Qualification must be reproducible and must never turn a
            # missing local validator dependency into an implicit network
            # install.  Cached wheels may still be used by uv.
            "UV_OFFLINE": "1",
        }
    )
    if extra:
        environment.update(extra)
    return environment


def _execution_environment(
    repository_root: Path,
    tool_relative: Path,
    *,
    postgres: dict[str, Any] | None = None,
) -> dict[str, Any]:
    executable = Path(sys.executable).resolve(strict=True)
    executable_payload, _ = _safe_regular_bytes(executable)
    tool_path = repository_root / tool_relative
    tool_payload, _ = _safe_regular_bytes(tool_path)
    packages: dict[str, str] = {}
    for distribution in ("psycopg", "psycopg-binary"):
        try:
            packages[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            packages[distribution] = "NOT_INSTALLED"
    return {
        "schema_version": "1.0.0",
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "cache_tag": sys.implementation.cache_tag,
            "executable": str(executable),
            "executable_sha256": "sha256:" + sha256_bytes(executable_payload),
        },
        "tool": {
            "path": tool_relative.as_posix(),
            "version": PACKAGE_VERSION,
            "sha256": "sha256:" + sha256_bytes(tool_payload),
        },
        "packages": packages,
        "postgresql": postgres or {
            "status": "NOT_APPLICABLE_TO_COMMAND",
            "required_version": POSTGRES_VERSION,
        },
        "evidence_boundary": {
            "classification": "LOCAL_EXECUTED_SELF_ATTESTED",
            "external_evidence": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
    }


def _postgres17_preflight(repository_root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    configured = os.environ.get("ELMOS_TEST_POSTGRES17_BIN")
    if configured:
        bin_root = Path(configured).resolve(strict=True)
    else:
        discovered = shutil.which("initdb")
        bin_root = (
            Path(discovered).resolve(strict=True).parent
            if discovered
            else Path("/opt/homebrew/opt/postgresql@17/bin").resolve(strict=True)
        )
    tools: list[dict[str, Any]] = []
    for name in ("initdb", "pg_ctl", "psql", "postgres"):
        path = (bin_root / name).resolve(strict=True)
        payload, _ = _safe_regular_bytes(path)
        tools.append(
            {
                "name": name,
                "path": str(path),
                "sha256": "sha256:" + sha256_bytes(payload),
            }
        )
    completed = subprocess.run(
        [str(bin_root / "initdb"), "--version"],
        cwd=repository_root,
        env=_command_environment(repository_root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
    )
    version_output = (completed.stdout + completed.stderr).decode(
        "utf-8", errors="replace"
    ).strip()
    match = re.fullmatch(r"initdb \(PostgreSQL\) ([0-9]+\.[0-9]+)(?:\.[0-9]+)?", version_output)
    if completed.returncode != 0 or match is None or match.group(1) != POSTGRES_VERSION:
        raise QualificationError(
            f"qualification requires exact PostgreSQL {POSTGRES_VERSION}; observed {version_output!r}"
        )
    try:
        psycopg_version = importlib.metadata.version("psycopg")
        binary_version = importlib.metadata.version("psycopg-binary")
    except importlib.metadata.PackageNotFoundError as exc:
        raise QualificationError("PostgreSQL qualification requires psycopg and psycopg-binary") from exc
    if psycopg_version != PSYCOPG_VERSION or binary_version != PSYCOPG_VERSION:
        raise QualificationError(
            "PostgreSQL qualification requires exact psycopg/psycopg-binary "
            f"{PSYCOPG_VERSION}; observed {psycopg_version}/{binary_version}"
        )
    return (
        {
            "status": "AVAILABLE_EXACT",
            "required_version": POSTGRES_VERSION,
            "observed_version": match.group(1),
            "version_output": version_output,
            "psycopg_version": psycopg_version,
            "psycopg_binary_version": binary_version,
            "tools": tools,
        },
        {"ELMOS_TEST_POSTGRES17_BIN": str(bin_root)},
    )


def _empty_test_totals() -> dict[str, int]:
    return {
        "selected": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "expected_failures": 0,
        "unexpected_successes": 0,
    }


def _structured_totals(stdout: str, name: str) -> dict[str, int]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise QualificationError(f"{name} did not emit structured JSON results") from exc
    if not isinstance(value, dict) or value.get("kind") != "elmos.proof-harness.structured-unittest-results":
        raise QualificationError(f"{name} emitted an unexpected structured result")
    totals = value.get("totals")
    outcomes = value.get("outcomes")
    expected_keys = set(_empty_test_totals())
    if (
        value.get("status") != "PASS"
        or not isinstance(totals, dict)
        or set(totals) != expected_keys
        or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in totals.values())
        or not isinstance(outcomes, list)
        or len(outcomes) != totals["selected"]
        or totals["selected"] <= 0
        or totals["passed"] != totals["selected"]
        or any(totals[key] != 0 for key in expected_keys - {"selected", "passed"})
    ):
        raise QualificationError(f"{name} contains failed, skipped, or malformed test outcomes")
    selectors = [item.get("selector") for item in outcomes if isinstance(item, dict)]
    if len(selectors) != len(outcomes) or len(set(selectors)) != len(selectors):
        raise QualificationError(f"{name} contains duplicate or malformed test selectors")
    return {key: int(totals[key]) for key in sorted(expected_keys)}


def _run_fixed_command(
    *,
    repository_root: Path,
    name: str,
    argv: list[str],
    timeout_seconds: int,
    raw_directory: Path,
    tool_relative: Path,
    structured_tests: bool = False,
    extra_environment: dict[str, str] | None = None,
    postgres_environment: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, int], bool]:
    execution_environment = _execution_environment(
        repository_root,
        tool_relative,
        postgres=postgres_environment,
    )
    started = __import__("time").monotonic_ns()
    timed_out = False
    try:
        completed = subprocess.run(
            argv,
            cwd=repository_root,
            env=_command_environment(repository_root, extra_environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
        returncode = completed.returncode
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = 124
        stdout = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    elapsed_ms = (__import__("time").monotonic_ns() - started) // 1_000_000
    record = {
        "schema_version": "1.0.0",
        "name": name,
        "argv": argv,
        "cwd": ".",
        "returncode": returncode,
        "timed_out": timed_out,
        "wall_clock_milliseconds": elapsed_ms,
        "stdout": stdout,
        "stderr": stderr,
        "execution_environment": execution_environment,
    }
    raw_path = raw_directory / f"{name}.json"
    raw_payload = canonical_bytes(record) + b"\n"
    _atomic_write(raw_path, raw_payload)
    totals = _empty_test_totals()
    structured_valid = True
    if structured_tests:
        try:
            totals = _structured_totals(stdout, name)
        except QualificationError:
            structured_valid = False
    raw_ref = {
        "path": f"qualification/raw/{raw_path.name}",
        "sha256": sha256_bytes(raw_payload),
        "bytes": len(raw_payload),
    }
    return raw_ref, totals, returncode == 0 and not timed_out and structured_valid


def _validate_runtime_registry(repository_root: Path) -> None:
    source_root = repository_root / ENGINE_RELATIVE / "src"
    sys.path.insert(0, str(source_root))
    try:
        module = importlib.import_module("elmos_proof_harness.skills")
        skill_registry = getattr(module, "SKILL_REGISTRY", None)
        if not isinstance(skill_registry, dict) or tuple(sorted(skill_registry)) != SKILL_NAMES:
            raise QualificationError("runtime SKILL_REGISTRY does not expose the exact 16 names")
        component_registry = getattr(module, "COMPONENT_REGISTRY", None)
        if component_registry is None:
            component_registry = getattr(module, "INTERNAL_COMPONENT_REGISTRY", None)
        if not isinstance(component_registry, dict) or tuple(sorted(component_registry)) != COMPONENT_IDS:
            raise QualificationError("runtime component registry does not expose K1-C01 through K8-C12")
        runtime = getattr(module, "SkillRuntime", None)
        if runtime is None or not callable(getattr(runtime, "execute", None)):
            raise QualificationError("runtime SkillRuntime.execute is missing")
    finally:
        try:
            sys.path.remove(str(source_root))
        except ValueError:
            pass


def qualify(repository_root: Path, *, postgres17_mode: str = "not-run") -> dict[str, Any]:
    repository_root = repository_root.resolve(strict=True)
    engine_root = repository_root / ENGINE_RELATIVE
    archive = repository_root / "skills/subskills/elmos-proof-driven-agentic-harness-repository-semantic-compiler-v3.0.0.zip"
    archive_payload, _ = _safe_regular_bytes(archive)
    if sha256_bytes(archive_payload) != ARCHIVE_SHA256:
        raise QualificationError("source archive digest changed")
    inventory_before = engine_inventory(engine_root)
    _, raw_directory = _ensure_private_output_tree(engine_root)

    commands = (
        (
            "engine-tests",
            [
                sys.executable,
                STRUCTURED_RUNNER_RELATIVE.as_posix(),
                "--repo-root",
                ".",
                "--start-directory",
                (ENGINE_RELATIVE / "tests").as_posix(),
                "--pattern",
                "test_*.py",
            ],
            300,
            STRUCTURED_RUNNER_RELATIVE,
            True,
        ),
        (
            "package-integration-tests",
            [
                sys.executable,
                STRUCTURED_RUNNER_RELATIVE.as_posix(),
                "--repo-root",
                ".",
                "--start-directory",
                "tests/proof-driven-harness-v3",
                "--pattern",
                "test_*.py",
            ],
            300,
            STRUCTURED_RUNNER_RELATIVE,
            True,
        ),
        (
            "archive-installation-check",
            [
                sys.executable,
                "tooling/integrate_proof_driven_harness_v3.py",
                "--check",
                "--qualification-phase",
            ],
            300,
            Path("tooling/integrate_proof_driven_harness_v3.py"),
            False,
        ),
    )
    raw_logs: list[dict[str, Any]] = []
    totals = _empty_test_totals()
    failures: list[str] = []
    for name, argv, timeout, tool_relative, structured_tests in commands:
        extra_environment = (
            {"ELMOS_PROOF_HARNESS_QUALIFICATION_PHASE": "1"}
            if name == "package-integration-tests"
            else None
        )
        raw, command_totals, command_succeeded = _run_fixed_command(
            repository_root=repository_root,
            name=name,
            argv=argv,
            timeout_seconds=timeout,
            raw_directory=raw_directory,
            tool_relative=tool_relative,
            structured_tests=structured_tests,
            extra_environment=extra_environment,
        )
        raw_logs.append(raw)
        if not command_succeeded:
            failures.append(name)
        for key in totals:
            totals[key] += command_totals[key]

    postgres_receipt: dict[str, Any] = {
        "status": "NOT_RUN",
        "required_postgresql_version": POSTGRES_VERSION,
        "required_psycopg_version": PSYCOPG_VERSION,
        "raw_log": None,
        "reason": "Disposable PostgreSQL qualification was not explicitly requested.",
    }
    if postgres17_mode == "require":
        postgres_environment, extra_environment = _postgres17_preflight(repository_root)
        raw, command_totals, command_succeeded = _run_fixed_command(
            repository_root=repository_root,
            name="postgres17-integration",
            argv=[
                sys.executable,
                STRUCTURED_RUNNER_RELATIVE.as_posix(),
                "--repo-root",
                ".",
                "--start-directory",
                (ENGINE_RELATIVE / "tests").as_posix(),
                "--pattern",
                POSTGRES_TEST_RELATIVE.name,
            ],
            timeout_seconds=600,
            raw_directory=raw_directory,
            tool_relative=STRUCTURED_RUNNER_RELATIVE,
            structured_tests=True,
            extra_environment=extra_environment,
            postgres_environment=postgres_environment,
        )
        raw_logs.append(raw)
        if not command_succeeded:
            failures.append("postgres17-integration")
        for key in totals:
            totals[key] += command_totals[key]
        postgres_receipt = {
            "status": "LOCAL_EXECUTED_SELF_ATTESTED" if command_succeeded else "FAILED",
            "required_postgresql_version": POSTGRES_VERSION,
            "required_psycopg_version": PSYCOPG_VERSION,
            "environment": postgres_environment,
            "tests": command_totals,
            "raw_log": raw,
            "external_evidence": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
    if failures:
        raise QualificationError(f"local qualification commands failed: {failures}")

    _validate_runtime_registry(repository_root)
    records = engine_inventory(engine_root)
    if canonical_bytes(records) != canonical_bytes(inventory_before):
        raise QualificationError("engine tree changed during local qualification")
    archive_after, _ = _safe_regular_bytes(archive)
    if archive_after != archive_payload:
        raise QualificationError("source archive changed during local qualification")
    qualifier_path = repository_root / QUALIFIER_RELATIVE
    qualifier_payload, _ = _safe_regular_bytes(qualifier_path)
    qualifier_record = next(
        (record for record in records if record["path"] == "tools/qualify_local.py"),
        None,
    )
    if qualifier_record is None or qualifier_record["sha256"] != sha256_bytes(qualifier_payload):
        raise QualificationError("qualifier is not bound to the qualified engine tree")
    receipt = {
        "schema_version": "1.1.0",
        "kind": "elmos.proof-driven-harness-v3.local-qualification",
        "status": "PASS",
        "package": {
            "name": PACKAGE_NAME,
            "version": PACKAGE_VERSION,
            "archive_sha256": ARCHIVE_SHA256,
        },
        "engine": {
            "root": ENGINE_RELATIVE.as_posix(),
            "tree_sha256": sha256_bytes(canonical_bytes(records)),
            "files": records,
            "skill_count": len(SKILL_NAMES),
            "skill_names_sha256": sha256_bytes(canonical_bytes(list(SKILL_NAMES))),
            "component_count": len(COMPONENT_IDS),
            "component_ids_sha256": sha256_bytes(canonical_bytes(list(COMPONENT_IDS))),
        },
        "tests": {
            "status": "PASS",
            **totals,
            "raw_logs": raw_logs,
        },
        "postgresql17": postgres_receipt,
        "qualifier": {
            "path": QUALIFIER_RELATIVE.as_posix(),
            "sha256": sha256_bytes(qualifier_payload),
        },
    }
    _atomic_write(repository_root / RECEIPT_RELATIVE, canonical_bytes(receipt) + b"\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--postgres17-mode",
        choices=("not-run", "require"),
        default="not-run",
        help=(
            "default records PostgreSQL as NOT_RUN; require executes only the "
            "repository-owned disposable PostgreSQL 17.5 runner"
        ),
    )
    args = parser.parse_args()
    try:
        receipt = qualify(Path(args.repo_root), postgres17_mode=args.postgres17_mode)
    except (OSError, QualificationError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "engine_tree_sha256": receipt["engine"]["tree_sha256"],
                "tests_passed": receipt["tests"]["passed"],
                "evidence": RECEIPT_RELATIVE.as_posix(),
                "external_evidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
