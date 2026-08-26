#!/usr/bin/env python3
"""Build or verify the bounded Project Intelligence local qualification receipt."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import stat
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engines/project-intelligence-engine"
ENGINE_SRC = ENGINE / "src"
TEST_FIXTURE = ENGINE / "tests/test_runtime.py"
RECEIPT = ENGINE / "qualification/local-qualification.json"
SELF_RELATIVE = Path("tooling/qualify_project_intelligence_runtime.py")
_QUALIFICATION_SECRET_SENTINEL = "must-not-leak"


class QualificationError(RuntimeError):
    pass


_IGNORED_ENGINE_GENERATED_PARTS = frozenset(
    {".venv", "__pycache__", ".ruff_cache", ".pytest_cache"}
)


def _is_ignored_engine_generated_path(path: Path) -> bool:
    """Ignore local tool environments and interpreter-generated metadata.

    The qualification inventory describes repository-owned engine sources.  A
    developer's ignored virtualenv, bytecode cache, or editable-install
    ``*.egg-info`` directory is not source and may contain symlinks by design.
    Keeping these paths out of both the ancestry check and receipt makes the
    receipt deterministic without deleting or mutating the environment.
    """

    relative = path.relative_to(ENGINE)
    return any(
        part in _IGNORED_ENGINE_GENERATED_PARTS or part.endswith(".egg-info")
        for part in relative.parts
    )


_EFFECT_GUARD_ACTIVE = False
_DENIED_AUDIT_EVENTS = frozenset(
    {
        "_thread.start_new_thread",
        "open",
        "os.chdir",
        "os.chflags",
        "os.chmod",
        "os.chown",
        "os.exec",
        "os.fork",
        "os.forkpty",
        "os.kill",
        "os.link",
        "os.listdir",
        "os.mkdir",
        "os.putenv",
        "os.posix_spawn",
        "os.remove",
        "os.rename",
        "os.rmdir",
        "os.scandir",
        "os.setxattr",
        "os.spawn",
        "os.symlink",
        "os.system",
        "os.truncate",
        "os.unsetenv",
        "os.utime",
        "os.removexattr",
        "shutil.copyfile",
        "shutil.copymode",
        "shutil.copystat",
        "shutil.move",
        "socket.__new__",
        "socket.bind",
        "socket.connect",
        "socket.getaddrinfo",
        "sqlite3.connect",
        "subprocess.Popen",
    }
)


def _deny_qualification_effects(event: str, _args: tuple[Any, ...]) -> None:
    if _EFFECT_GUARD_ACTIVE and (
        event in _DENIED_AUDIT_EVENTS
        or event.startswith("ctypes.dlopen")
        or event.startswith("os.exec")
        or event.startswith("os.spawn")
    ):
        raise QualificationError(
            f"qualification handler attempted a denied external effect: {event}"
        )


sys.addaudithook(_deny_qualification_effects)


def _validate_engine_ancestry() -> None:
    current = ROOT
    for part in ENGINE.relative_to(ROOT).parts:
        current = current / part
        if current.is_symlink():
            raise QualificationError(f"engine ancestry contains a symlink: {current}")
    if not ENGINE.is_dir():
        raise QualificationError("engine root must be a real directory")
    for candidate in sorted(ENGINE.rglob("*")):
        if _is_ignored_engine_generated_path(candidate):
            continue
        if candidate.is_symlink():
            raise QualificationError(
                f"engine tree contains a pre-import symlink: {candidate}"
            )
        if not candidate.is_dir() and not stat.S_ISREG(candidate.lstat().st_mode):
            raise QualificationError(
                f"engine tree contains a pre-import special file: {candidate}"
            )
    for relative in (
        Path("src"),
        Path("src/elmos_project_intelligence"),
        Path("src/elmos_project_intelligence/canonical.py"),
        Path("src/elmos_project_intelligence/runtime.py"),
    ):
        target = ENGINE
        for part in relative.parts:
            target = target / part
            if target.is_symlink():
                raise QualificationError(
                    f"engine import ancestry contains a symlink: {target}"
                )
        if relative.suffix == ".py":
            if not target.is_file() or not stat.S_ISREG(target.lstat().st_mode):
                raise QualificationError(
                    f"engine import source is not a regular file: {target}"
                )
        elif not target.is_dir():
            raise QualificationError(
                f"engine import directory is missing or unsafe: {target}"
            )


_validate_engine_ancestry()

if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_project_intelligence.canonical import canonical_digest  # noqa: E402
from elmos_project_intelligence.qualification_contract import (  # noqa: E402
    ExpectedRequestScope,
    QualificationContractError,
    validate_qualification_result,
)
from elmos_project_intelligence.runtime import (  # noqa: E402
    SKILL_REGISTRY,
    dispatch_skill,
    validate_skill_registry,
)


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return "sha256:" + value.hexdigest()


def engine_inventory() -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    _validate_engine_ancestry()
    for path in sorted(ENGINE.rglob("*")):
        if _is_ignored_engine_generated_path(path):
            continue
        if path.is_symlink():
            raise QualificationError(f"engine tree contains a symlink: {path}")
        if path.is_dir():
            continue
        if not stat.S_ISREG(path.lstat().st_mode):
            raise QualificationError(f"engine tree contains a special file: {path}")
        relative = path.relative_to(ENGINE).as_posix()
        if relative == "qualification/local-qualification.json":
            continue
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            raise QualificationError(
                f"engine tree contains generated Python cache: {path}"
            )
        values.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "mode": f"{stat.S_IMODE(path.lstat().st_mode):04o}",
                "sha256": sha256_file(path),
            }
        )
    return values


def runtime_environment() -> dict[str, Any]:
    executable = Path(sys.executable)
    try:
        resolved = executable.resolve(strict=True)
    except OSError as exc:
        raise QualificationError(
            "cannot resolve the qualification interpreter"
        ) from exc
    if not resolved.is_file() or not stat.S_ISREG(resolved.stat().st_mode):
        raise QualificationError("qualification interpreter is not a regular file")
    version = sys.version_info
    return {
        "implementation": sys.implementation.name,
        "version": f"{version.major}.{version.minor}.{version.micro}",
        "release_level": version.releaselevel,
        "serial": version.serial,
        "cache_tag": sys.implementation.cache_tag,
        "hexversion": sys.hexversion,
        "platform": sys.platform,
        "machine": platform.machine(),
        "byteorder": sys.byteorder,
        "executable": resolved.as_posix(),
        "resolved_executable": resolved.as_posix(),
        "executable_sha256": sha256_file(resolved),
    }


def load_fixture_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "project_intelligence_runtime_fixture", TEST_FIXTURE
    )
    if spec is None or spec.loader is None:
        raise QualificationError("cannot load runtime qualification fixture")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "request", None)):
        raise QualificationError("runtime fixture has no request() builder")
    return module


def build_receipt() -> dict[str, Any]:
    global _EFFECT_GUARD_ACTIVE
    validate_skill_registry()
    fixture = load_fixture_module()
    expected_scope = ExpectedRequestScope(
        request_id="request-1",
        tenant_id="tenant-a",
        project_id="project-a",
        revision="abc123",
    )
    results: list[dict[str, Any]] = []
    for binding in SKILL_REGISTRY.values():
        try:
            _EFFECT_GUARD_ACTIVE = True
            result = dispatch_skill(binding.skill, fixture.request())
        finally:
            _EFFECT_GUARD_ACTIVE = False
        expected_state = {
            "LOCAL": "LOCAL_EXECUTED",
            "PARTIAL": "PARTIAL_LOCAL_EXECUTED",
            "PLAN": "PLANNING_ONLY",
        }[binding.capability_state]
        try:
            validate_qualification_result(binding, result, expected_scope)
        except QualificationContractError:
            passed = False
        else:
            passed = True
        results.append(
            {
                "ordinal": binding.ordinal,
                "skill": binding.skill,
                "handler_id": binding.handler_id,
                "capability_state": binding.capability_state,
                "expected_state": expected_state,
                "observed_state": result.get("state"),
                "expected_code": binding.expected_success_code,
                "observed_code": result.get("code"),
                "result_digest": result.get("result_digest"),
                "result": result,
                "status": "PASSED" if passed else "FAILED",
            }
        )
    failed_skills = [item["skill"] for item in results if item["status"] != "PASSED"]
    if failed_skills:
        raise QualificationError(
            "qualification contract failed for "
            f"{len(failed_skills)} handler(s): {failed_skills[:5]}"
        )
    if _QUALIFICATION_SECRET_SENTINEL in json.dumps(
        results, ensure_ascii=False, sort_keys=True
    ):
        raise QualificationError("qualification results disclosed the secret sentinel")
    inventory = engine_inventory()
    receipt = {
        "schema_version": "elmos.project-intelligence.local-qualification.v2",
        "source_package": "elmos-project-intelligence-skills",
        "source_version": "1.1.0",
        "qualification_scope": "bounded-local-fixture-handlers",
        "qualification_status": "PASSED",
        "engine_tree_sha256": canonical_digest(inventory),
        "engine_files": inventory,
        "qualifier_path": SELF_RELATIVE.as_posix(),
        "qualifier_sha256": sha256_file(ROOT / SELF_RELATIVE),
        "fixture_path": TEST_FIXTURE.relative_to(ROOT).as_posix(),
        "fixture_sha256": sha256_file(TEST_FIXTURE),
        "replay_command": (
            "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/project-intelligence-engine/src "
            "python3 tooling/qualify_project_intelligence_runtime.py --check"
        ),
        "executor": "repository-local-self-attested",
        "effect_guard": "PYTHON_AUDIT_BEST_EFFORT_EFFECT_GUARD_DURING_DISPATCH",
        "effect_guard_limitations": (
            "Python audit events are fail-closed when observed but are not an OS "
            "sandbox and cannot account for effects through inherited descriptors, "
            "native extensions, or events the interpreter does not emit."
        ),
        "runtime_environment": runtime_environment(),
        "independent_verifier": None,
        "local_execution_evidence": "LOCAL_EXECUTED_SELF_ATTESTED",
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "counts": {"skills": 50, "local": 19, "partial": 26, "plan": 5},
        "results": results,
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    return receipt


def serialized(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_receipt(value: dict[str, Any]) -> None:
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".local-qualification.", dir=RECEIPT.parent
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), 0o644)
            handle.write(serialized(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, RECEIPT)
        _fsync_directory(RECEIPT.parent)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        expected = build_receipt()
        if args.write:
            write_receipt(expected)
        elif (
            not RECEIPT.is_file()
            or RECEIPT.is_symlink()
            or not stat.S_ISREG(RECEIPT.lstat().st_mode)
        ):
            raise QualificationError("local qualification receipt is missing or unsafe")
        elif stat.S_IMODE(RECEIPT.lstat().st_mode) != 0o644:
            raise QualificationError("local qualification receipt mode must be 0644")
        elif RECEIPT.read_bytes() != serialized(expected):
            raise QualificationError(
                "local qualification receipt drifted from engine bytes/results"
            )
    except (OSError, ValueError, QualificationError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "mode": "write" if args.write else "check",
                "skills": 50,
                "local": 19,
                "partial": 26,
                "plan": 5,
                "local_execution_evidence": "LOCAL_EXECUTED_SELF_ATTESTED",
                "external_evidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
                "receipt_digest": expected["receipt_digest"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
