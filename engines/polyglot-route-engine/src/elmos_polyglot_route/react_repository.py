"""Exact whole-repository boundary for React's typed-pure TS/TSX slice.

React repository support is intentionally narrower than a general React
application.  The route IR cannot represent JSX, components, hooks, effects or
imports, so the only admitted project is an exact Node/TypeScript/React module
profile containing independent, explicitly typed pure functions.  Project
metadata and source bytes are content-addressed before the exact TypeScript
compiler sees a private snapshot; no repository lifecycle script is executed.
"""

from __future__ import annotations

import hashlib
import json
import stat
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

from .models import RouteError
from .toolchains import exact_toolchain, sanitized_subprocess_env

MAX_DESCRIPTOR_BYTES = 256 * 1024
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_COMPILER_OUTPUT_BYTES = 1_000_000

_PACKAGE_VERSIONS = {
    "@types/react": "19.1.10",
    "@types/react-dom": "19.1.7",
    "react": "19.2.7",
    "react-dom": "19.2.7",
    "typescript": "5.9.2",
}
_DEPENDENCIES = {
    "react": "19.2.7",
    "react-dom": "19.2.7",
}
_DEV_DEPENDENCIES = {
    "@types/react": "19.1.10",
    "@types/react-dom": "19.1.7",
    "typescript": "5.9.2",
}
_PACKAGE_KEYS = {"private", "type", "dependencies", "devDependencies"}
_COMPILER_OPTIONS = {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": True,
    "jsx": "react-jsx",
    "noEmit": True,
    "types": [],
}
_INCLUDE = ["**/*.ts", "**/*.tsx"]


def _stable_regular_bytes(
    path: Path,
    failure: str,
    *,
    maximum_bytes: int = MAX_DESCRIPTOR_BYTES,
) -> bytes:
    try:
        before = path.lstat()
        if (
            stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > maximum_bytes
        ):
            raise RouteError(failure)
        content = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_uid,
        before.st_gid,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    if len(content) != before.st_size or identity != (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_uid,
        after.st_gid,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise RouteError(failure)
    return content


def _strict_json(content: bytes, failure: str) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value

    try:
        value = json.loads(content.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise RouteError(failure) from error
    if type(value) is not dict:
        raise RouteError(failure)
    return value


def _binding(path: Path, content: bytes) -> dict[str, str | int]:
    return {
        "path": path.name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def _toolchain_receipt(toolchain: object) -> dict[str, Any]:
    return {
        "language": getattr(toolchain, "language"),
        "version": getattr(toolchain, "version"),
        "executable": getattr(toolchain, "executable"),
        "executable_sha256": getattr(toolchain, "executable_sha256"),
        "auxiliary": getattr(toolchain, "auxiliary"),
        "auxiliary_sha256": getattr(toolchain, "auxiliary_sha256"),
        "profile": list(getattr(toolchain, "profile")),
    }


def react_project_descriptor(repository_root: Path) -> dict[str, Any]:
    """Validate and bind the exact repository-level React project profile."""

    if repository_root.is_symlink() or not repository_root.is_dir():
        raise RouteError("REACT_REPOSITORY_DIRECTORY_INVALID")
    root = repository_root.resolve(strict=True)
    package_path = root / "package.json"
    config_path = root / "tsconfig.json"
    package_content = _stable_regular_bytes(package_path, "REACT_PACKAGE_DESCRIPTOR_INVALID")
    config_content = _stable_regular_bytes(config_path, "REACT_TSCONFIG_DESCRIPTOR_INVALID")
    package = _strict_json(package_content, "REACT_PACKAGE_DESCRIPTOR_INVALID")
    config = _strict_json(config_content, "REACT_TSCONFIG_DESCRIPTOR_INVALID")

    if set(package) != _PACKAGE_KEYS or package.get("private") is not True:
        raise RouteError("REACT_PACKAGE_PROFILE_INVALID")
    if package.get("type") != "module":
        raise RouteError("REACT_PACKAGE_TYPE_MODULE_REQUIRED")
    dependencies = package.get("dependencies")
    dev_dependencies = package.get("devDependencies")
    if dependencies != _DEPENDENCIES or dev_dependencies != _DEV_DEPENDENCIES:
        observed = {
            str(name): version
            for section in (dependencies, dev_dependencies)
            if type(section) is dict
            for name, version in section.items()
        }
        mismatches = [
            name for name, version in _PACKAGE_VERSIONS.items() if observed.get(name) != version
        ]
        if mismatches:
            raise RouteError(f"REACT_PACKAGE_VERSION_MISMATCH:{mismatches[0]}")
        raise RouteError("REACT_PACKAGE_DEPENDENCY_PROFILE_INVALID")

    if set(config) != {"compilerOptions", "include"}:
        raise RouteError("REACT_TSCONFIG_PROFILE_INVALID")
    if config.get("compilerOptions") != _COMPILER_OPTIONS or config.get("include") != _INCLUDE:
        raise RouteError("REACT_TSCONFIG_PROFILE_INVALID")
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.react-typed-pure-project-descriptor",
        "profile": "react-19.2.7-typescript-5.9.2-node-26.0.0-typed-pure-v1",
        "package": _binding(package_path, package_content),
        "tsconfig": _binding(config_path, config_content),
        "dependencies": dict(_PACKAGE_VERSIONS),
        "compiler_options": dict(_COMPILER_OPTIONS),
        "include": list(_INCLUDE),
        "unsupported_semantics": [
            "components",
            "effects",
            "hooks",
            "imports",
            "jsx",
            "module-side-effects",
        ],
    }


def _source_path(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if (
        not relative
        or pure.is_absolute()
        or ".." in pure.parts
        or pure.as_posix() != relative
        or pure.suffix not in {".ts", ".tsx"}
    ):
        raise RouteError(f"REACT_REPOSITORY_SOURCE_PATH_INVALID:{relative}")
    candidate = root.joinpath(*pure.parts)
    cursor = root
    for part in pure.parts:
        cursor /= part
        if cursor.is_symlink():
            raise RouteError(f"REACT_REPOSITORY_SOURCE_PATH_INVALID:{relative}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise RouteError(f"REACT_REPOSITORY_SOURCE_PATH_INVALID:{relative}") from error
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise RouteError(f"REACT_REPOSITORY_SOURCE_PATH_INVALID:{relative}")
    return candidate


def verify_react_repository_project(
    repository_root: Path,
    source_paths: Sequence[str],
    descriptor: dict[str, Any],
) -> dict[str, Any]:
    """Compile the exact multi-file source snapshot with Node 26 / TS 5.9.2."""

    root = repository_root.resolve(strict=True)
    if react_project_descriptor(root) != descriptor:
        raise RouteError("REACT_PROJECT_DESCRIPTOR_CHANGED")
    ordered = sorted(dict.fromkeys(source_paths))
    if not ordered or len(ordered) != len(source_paths):
        raise RouteError("REACT_REPOSITORY_SOURCE_SET_INVALID")
    bindings: list[tuple[str, Path, bytes]] = []
    for relative in ordered:
        path = _source_path(root, relative)
        content = _stable_regular_bytes(
            path,
            f"REACT_REPOSITORY_SOURCE_CHANGED:{relative}",
            maximum_bytes=MAX_SOURCE_BYTES,
        )
        bindings.append((relative, path, content))

    package_content = _stable_regular_bytes(root / "package.json", "REACT_PACKAGE_DESCRIPTOR_CHANGED")
    config_content = _stable_regular_bytes(root / "tsconfig.json", "REACT_TSCONFIG_DESCRIPTOR_CHANGED")
    toolchain = exact_toolchain("react")
    if toolchain.auxiliary is None:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:react-typescript")
    with tempfile.TemporaryDirectory(prefix="elmos-react-repository-") as temporary:
        snapshot = Path(temporary)
        snapshot.chmod(0o700)
        home = snapshot / ".home"
        scratch = snapshot / ".tmp"
        home.mkdir(mode=0o700)
        scratch.mkdir(mode=0o700)
        (snapshot / "package.json").write_bytes(package_content)
        (snapshot / "tsconfig.json").write_bytes(config_content)
        for relative, _path, content in bindings:
            target = snapshot.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            target.write_bytes(content)
        command = [toolchain.auxiliary, "-p", "tsconfig.json", "--pretty", "false"]
        try:
            completed = subprocess.run(
                command,
                cwd=snapshot,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
                env=sanitized_subprocess_env(
                    home=home,
                    temp_dir=scratch,
                    executable_dirs=tuple(
                        dict.fromkeys(
                            Path(path).resolve().parent
                            for path in (toolchain.executable, toolchain.auxiliary)
                            if path is not None
                        )
                    ),
                ),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RouteError("REACT_REPOSITORY_TYPESCRIPT_EXECUTION_NOT_PASSED") from error
    output_bytes = len(completed.stdout.encode()) + len(completed.stderr.encode())
    if output_bytes > MAX_COMPILER_OUTPUT_BYTES:
        raise RouteError("REACT_REPOSITORY_TYPESCRIPT_OUTPUT_TOO_LARGE")
    if completed.returncode != 0:
        diagnostic = (completed.stderr or completed.stdout).strip().splitlines()
        detail = diagnostic[-1][:300] if diagnostic else "no-diagnostic"
        raise RouteError(f"REACT_REPOSITORY_TYPESCRIPT_COMPILE_FAILED:{detail}")

    for relative, path, content in bindings:
        if _stable_regular_bytes(
            path,
            f"REACT_REPOSITORY_SOURCE_CHANGED:{relative}",
            maximum_bytes=MAX_SOURCE_BYTES,
        ) != content:
            raise RouteError(f"REACT_REPOSITORY_SOURCE_CHANGED:{relative}")
    if react_project_descriptor(root) != descriptor:
        raise RouteError("REACT_PROJECT_DESCRIPTOR_CHANGED")
    receipt = {
        "status": "PASSED",
        "profile": descriptor["profile"],
        "source_file_count": len(bindings),
        "source_sha256": {
            relative: hashlib.sha256(content).hexdigest()
            for relative, _path, content in bindings
        },
        "toolchain": _toolchain_receipt(toolchain),
        "command": [toolchain.auxiliary, "-p", "tsconfig.json", "--pretty", "false"],
        "stdout": completed.stdout[-2_000:],
        "stderr": completed.stderr[-2_000:],
        "external_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    return {**receipt, "receipt_sha256": _canonical_sha256(receipt)}


def validate_react_repository_verification(
    repository_root: Path,
    source_paths: Sequence[str],
    descriptor: dict[str, Any],
    receipt: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed unless a discovery receipt binds the complete exact profile."""

    expected_keys = {
        "status",
        "profile",
        "source_file_count",
        "source_sha256",
        "toolchain",
        "command",
        "stdout",
        "stderr",
        "external_verification_status",
        "certification_status",
        "receipt_sha256",
    }
    if set(receipt) != expected_keys:
        raise RouteError("REACT_REPOSITORY_VERIFICATION_SCHEMA_INVALID")
    bound = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if receipt.get("receipt_sha256") != _canonical_sha256(bound):
        raise RouteError("REACT_REPOSITORY_VERIFICATION_DIGEST_INVALID")

    root = repository_root.resolve(strict=True)
    if react_project_descriptor(root) != descriptor:
        raise RouteError("REACT_PROJECT_DESCRIPTOR_CHANGED")
    ordered = sorted(dict.fromkeys(source_paths))
    if not ordered or len(ordered) != len(source_paths):
        raise RouteError("REACT_REPOSITORY_SOURCE_SET_INVALID")
    expected_sources: dict[str, str] = {}
    for relative in ordered:
        source = _source_path(root, relative)
        content = _stable_regular_bytes(
            source,
            f"REACT_REPOSITORY_SOURCE_CHANGED:{relative}",
            maximum_bytes=MAX_SOURCE_BYTES,
        )
        expected_sources[relative] = hashlib.sha256(content).hexdigest()

    toolchain = exact_toolchain("react")
    if toolchain.auxiliary is None:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:react-typescript")
    stdout = receipt.get("stdout")
    stderr = receipt.get("stderr")
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        raise RouteError("REACT_REPOSITORY_VERIFICATION_OUTPUT_INVALID")
    if len(stdout) > 2_000 or len(stderr) > 2_000:
        raise RouteError("REACT_REPOSITORY_VERIFICATION_OUTPUT_INVALID")
    if (
        receipt.get("status") != "PASSED"
        or receipt.get("profile") != descriptor.get("profile")
        or receipt.get("source_file_count") != len(expected_sources)
        or receipt.get("source_sha256") != expected_sources
        or receipt.get("toolchain") != _toolchain_receipt(toolchain)
        or receipt.get("command")
        != [toolchain.auxiliary, "-p", "tsconfig.json", "--pretty", "false"]
        or receipt.get("external_verification_status") != "NOT_RUN"
        or receipt.get("certification_status") != "NOT_CERTIFIED"
    ):
        raise RouteError("REACT_REPOSITORY_VERIFICATION_INVALID")
    return dict(receipt)


__all__ = [
    "react_project_descriptor",
    "validate_react_repository_verification",
    "verify_react_repository_project",
]
