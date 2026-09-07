"""Direct, package-external launcher for verified database/Big Data source bytes."""

# ruff: noqa: E402 - isolation guards intentionally precede non-builtin imports

from __future__ import annotations

import sys

# The launcher itself is a repository trust root.  Refuse to import even Python
# standard-library modules unless the interpreter has already removed the
# script directory/current directory, ignored environment path injection, and
# disabled site customization and bytecode writes.  These flags must be set by
# the parent interpreter; setting them here would be too late.
if not (
    sys.flags.isolated
    and sys.flags.no_site
    and sys.flags.ignore_environment
    and sys.flags.safe_path
    and sys.flags.dont_write_bytecode
):
    sys.stderr.write(
        '{"code":"ISOLATED_LAUNCH_REQUIRED","external_effects_performed":false,'
        '"message":"invoke with python3 -I -S -B",'
        '"production_certification":"NOT_CERTIFIED",'
        '"runtime_evidence":"NOT_RUN",'
        '"schema_version":"elmos.database-bigdata.error.v1",'
        '"skill_implementation_state":"DECLARED","state":"BLOCKED"}\n'
    )
    raise SystemExit(2)

_trusted_interpreter_prefixes = tuple(
    prefix.rstrip("/\\") for prefix in {sys.base_prefix, sys.base_exec_prefix} if prefix
)
if not _trusted_interpreter_prefixes or any(
    not entry
    or "/../" in entry.replace("\\", "/")
    or not any(
        entry == prefix
        or entry.startswith(prefix + "/")
        or entry.startswith(prefix + "\\")
        for prefix in _trusted_interpreter_prefixes
    )
    for entry in sys.path
):
    sys.stderr.write(
        '{"code":"ISOLATED_SYS_PATH_REJECTED",'
        '"external_effects_performed":false,'
        '"message":"isolated interpreter path is outside its base prefix",'
        '"production_certification":"NOT_CERTIFIED",'
        '"runtime_evidence":"NOT_RUN",'
        '"schema_version":"elmos.database-bigdata.error.v1",'
        '"skill_implementation_state":"DECLARED","state":"BLOCKED"}\n'
    )
    raise SystemExit(2)

import hashlib
import importlib
import importlib.abc
import importlib.util
import json
from pathlib import Path, PurePosixPath
from typing import Any

sys.dont_write_bytecode = True

MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_SAFE_INTEGER = (1 << 53) - 1
ENGINE_RELATIVE = "engines/database-bigdata-engine"
MANIFEST_RELATIVE = "docs/database-bigdata-skills/installed-manifest.json"
PACKAGE_PREFIX = "elmos_database_bigdata"
LAUNCH_ASSURANCE = "ISOLATED_DIRECT_LAUNCHER_VERIFIED_SOURCE_LOADER"


class LauncherError(ValueError):
    """Raised before package import when the repository snapshot is not exact."""


def _reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LauncherError(f"installed manifest contains duplicate key: {key}")
        result[key] = value
    return result


def _reject_number(token: str) -> Any:
    raise LauncherError(f"installed manifest contains forbidden number: {token}")


def _parse_integer(token: str) -> int:
    digits = token.removeprefix("-")
    if len(digits) > 16:
        raise LauncherError("installed manifest contains an unsafe JSON integer")
    value = int(token)
    if abs(value) > MAX_SAFE_INTEGER:
        raise LauncherError("installed manifest contains an unsafe JSON integer")
    return value


def _parse_manifest(content: bytes) -> dict[str, Any]:
    if len(content) > MAX_MANIFEST_BYTES:
        raise LauncherError("installed manifest exceeds the byte limit")
    try:
        value = json.loads(
            content.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_pairs,
            parse_float=_reject_number,
            parse_int=_parse_integer,
            parse_constant=_reject_number,
        )
    except LauncherError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise LauncherError(f"installed manifest is not strict JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise LauncherError("installed manifest must be an object")
    return value


def _tree_digest(files: dict[str, bytes]) -> str:
    value = hashlib.sha256()
    value.update(b"elmos-tree-digest-v2\0")

    def update_framed(content: bytes) -> None:
        value.update(len(content).to_bytes(8, "big"))
        value.update(content)

    value.update((1).to_bytes(8, "big"))
    update_framed(b"database-bigdata-engine")
    value.update(len(files).to_bytes(8, "big"))
    for relative in sorted(files):
        update_framed(relative.encode("utf-8"))
        update_framed(files[relative])
    return "sha256:" + value.hexdigest()


def _confined_file(engine_root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative:
        raise LauncherError("runtime file path must be a non-empty string")
    pure = PurePosixPath(relative)
    if (
        pure.is_absolute()
        or str(pure) != relative
        or ".." in pure.parts
        or "\\" in relative
    ):
        raise LauncherError(f"runtime file path is not confined: {relative!r}")
    candidate = engine_root / relative
    current = engine_root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise LauncherError(f"runtime file path contains a symlink: {relative}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(engine_root)
    except (OSError, ValueError) as exc:
        raise LauncherError(
            f"runtime file path escapes or is missing: {relative}"
        ) from exc
    if not resolved.is_file():
        raise LauncherError(f"runtime file is not regular: {relative}")
    return resolved


def _verified_snapshot() -> dict[str, Any]:
    launcher_path = Path(__file__).resolve(strict=True)
    engine_root = launcher_path.parent
    repository_root = launcher_path.parents[2]
    if engine_root != repository_root / ENGINE_RELATIVE:
        raise LauncherError("launcher location differs from the repository trust root")
    manifest_path = repository_root / MANIFEST_RELATIVE
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise LauncherError(f"cannot read installed manifest: {exc}") from exc
    manifest = _parse_manifest(manifest_bytes)
    required_values = {
        "namespace": "elmos-database-bigdata-v1",
        "source_package": "elmos-database-bigdata-skills",
        "source_version": "1.0.0",
        "repository_bounded_handler_state": "BOUND_PLAN_SKELETON_ONLY",
        "skill_implementation_state": "DECLARED",
        "repository_handler_runtime_evidence": "NOT_RUN",
        "provider_runtime_evidence": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "repository_runtime_path": ENGINE_RELATIVE,
        "repository_runtime_digest_algorithm": "elmos-tree-digest-v2",
    }
    for field, expected in required_values.items():
        if manifest.get(field) != expected:
            raise LauncherError(f"installed manifest field drifted: {field}")

    paths = list(engine_root.rglob("*"))
    for path in paths:
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            raise LauncherError(f"runtime tree contains bytecode: {path}")
        if path.is_symlink():
            raise LauncherError(f"runtime tree contains a symlink: {path}")
    actual_paths = sorted(
        path.relative_to(engine_root).as_posix() for path in paths if path.is_file()
    )
    records = manifest.get("repository_runtime_files")
    if not isinstance(records, list) or not records:
        raise LauncherError("installed manifest runtime inventory is missing")
    declared_paths = [
        record.get("path") for record in records if isinstance(record, dict)
    ]
    if (
        len(declared_paths) != len(records)
        or not all(isinstance(path, str) for path in declared_paths)
        or declared_paths != sorted(declared_paths)
        or declared_paths != actual_paths
        or manifest.get("repository_runtime_file_count") != len(records)
    ):
        raise LauncherError("runtime file inventory differs from installed manifest")

    files: dict[str, bytes] = {}
    file_digests: dict[str, str] = {}
    for record in records:
        if set(record) != {"path", "bytes", "sha256"}:
            raise LauncherError("runtime file record fields are not exact")
        relative = record["path"]
        content = _confined_file(engine_root, relative).read_bytes()
        actual_digest = "sha256:" + hashlib.sha256(content).hexdigest()
        if record["bytes"] != len(content) or record["sha256"] != actual_digest:
            raise LauncherError(f"runtime file bytes drifted: {relative}")
        files[relative] = content
        file_digests[relative] = actual_digest
    tree_sha256 = _tree_digest(files)
    if manifest.get("repository_runtime_tree_sha256") != tree_sha256:
        raise LauncherError("runtime tree digest differs from installed manifest")
    return {
        "launch_assurance": LAUNCH_ASSURANCE,
        "manifest_bytes": manifest_bytes,
        "manifest_sha256": "sha256:" + hashlib.sha256(manifest_bytes).hexdigest(),
        "runtime_tree_sha256": tree_sha256,
        "files": tuple((path, files[path]) for path in sorted(files)),
        "file_digests": tuple(
            (path, file_digests[path]) for path in sorted(file_digests)
        ),
    }


class _VerifiedSourceLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Load only package modules whose exact source bytes are in the receipt."""

    def __init__(self, snapshot: dict[str, Any], engine_root: Path) -> None:
        self._snapshot = snapshot
        self._sources: dict[str, tuple[str, bytes, bool]] = {}
        prefix = "src/elmos_database_bigdata/"
        for relative, content in snapshot["files"]:
            if not relative.startswith(prefix) or not relative.endswith(".py"):
                continue
            suffix = relative.removeprefix("src/")
            parts = PurePosixPath(suffix).parts
            is_package = parts[-1] == "__init__.py"
            module_parts = parts[:-1] if is_package else (*parts[:-1], parts[-1][:-3])
            name = ".".join(module_parts)
            origin = str(engine_root / relative)
            self._sources[name] = (origin, content, is_package)

    def find_spec(
        self,
        fullname: str,
        path: Any = None,
        target: Any = None,
    ) -> Any:
        del path, target
        source = self._sources.get(fullname)
        if source is None:
            return None
        origin, _, is_package = source
        return importlib.util.spec_from_loader(
            fullname, self, origin=origin, is_package=is_package
        )

    def create_module(self, spec: Any) -> None:
        del spec

    def exec_module(self, module: Any) -> None:
        origin, content, _ = self._sources[module.__name__]
        module.__file__ = origin
        if module.__name__ == f"{PACKAGE_PREFIX}.bootstrap":
            module.__dict__["_PREVERIFIED_LAUNCHER_SNAPSHOT"] = self._snapshot
        code = compile(content, origin, "exec", dont_inherit=True, optimize=0)
        exec(code, module.__dict__)  # noqa: S102 - verified source-loader boundary


def _emit_error(exc: Exception) -> None:
    value = {
        "schema_version": "elmos.database-bigdata.error.v1",
        "state": "BLOCKED",
        "code": "VERIFIED_SOURCE_LAUNCH_REJECTED",
        "error_type": type(exc).__name__,
        "message": str(exc),
        "external_effects_performed": False,
        "skill_implementation_state": "DECLARED",
        "runtime_evidence": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
    }
    sys.stderr.write(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    loader: _VerifiedSourceLoader | None = None
    try:
        if any(
            name == PACKAGE_PREFIX or name.startswith(PACKAGE_PREFIX + ".")
            for name in sys.modules
        ):
            raise LauncherError(
                "database/Big Data package was loaded before verification"
            )
        snapshot = _verified_snapshot()
        engine_root = Path(__file__).resolve(strict=True).parent
        loader = _VerifiedSourceLoader(snapshot, engine_root)
        sys.meta_path.insert(0, loader)
        cli = importlib.import_module(f"{PACKAGE_PREFIX}.cli")
        return cli.main(argv)
    except (LauncherError, ImportError, OSError, TypeError, ValueError) as exc:
        _emit_error(exc)
        return 2
    finally:
        if loader is not None and loader in sys.meta_path:
            del sys.meta_path[sys.meta_path.index(loader)]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))


__all__ = ["LauncherError", "main"]
