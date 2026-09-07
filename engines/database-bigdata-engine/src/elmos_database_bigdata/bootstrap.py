"""Small console trust surface that verifies engine bytes before runtime import."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

MAX_MANIFEST_BYTES = 4 * 1024 * 1024
ENGINE_RELATIVE = "engines/database-bigdata-engine"
MANIFEST_RELATIVE = "docs/database-bigdata-skills/installed-manifest.json"
MAX_SAFE_INTEGER = (1 << 53) - 1
DIRECT_IMPORT_ASSURANCE = "DIRECT_IMPORT_TRUSTED_CODE_ONLY"
ISOLATED_LAUNCH_ASSURANCE = "ISOLATED_DIRECT_LAUNCHER_VERIFIED_SOURCE_LOADER"
LAUNCH_ASSURANCES = frozenset({DIRECT_IMPORT_ASSURANCE, ISOLATED_LAUNCH_ASSURANCE})


class BootstrapError(ValueError):
    """Raised before runtime import when repository byte identity is not exact."""


@dataclass(frozen=True, slots=True)
class VerificationReceipt:
    """Immutable bytes used to bind this process to one repository snapshot."""

    launch_assurance: str
    manifest_bytes: bytes
    manifest_sha256: str
    runtime_tree_sha256: str
    files: tuple[tuple[str, bytes], ...]
    file_digests: tuple[tuple[str, str], ...]


_INITIAL_RECEIPT: VerificationReceipt | None = None


def _reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BootstrapError(f"installed manifest contains duplicate key: {key}")
        result[key] = value
    return result


def _reject_number(token: str) -> Any:
    raise BootstrapError(f"installed manifest contains forbidden number: {token}")


def _parse_integer(token: str) -> int:
    digits = token.removeprefix("-")
    if len(digits) > 16:
        raise BootstrapError("installed manifest contains an unsafe JSON integer")
    value = int(token)
    if abs(value) > MAX_SAFE_INTEGER:
        raise BootstrapError("installed manifest contains an unsafe JSON integer")
    return value


def _parse_manifest(content: bytes) -> dict[str, Any]:
    if len(content) > MAX_MANIFEST_BYTES:
        raise BootstrapError("installed manifest exceeds the byte limit")
    try:
        text = content.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_pairs,
            parse_float=_reject_number,
            parse_int=_parse_integer,
            parse_constant=_reject_number,
        )
    except BootstrapError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise BootstrapError(f"installed manifest is not strict JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise BootstrapError("installed manifest must be an object")
    return value


def _load_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise BootstrapError(f"cannot read installed manifest: {exc}") from exc
    return _parse_manifest(content), content


def _confined_file(engine_root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative:
        raise BootstrapError("runtime file path must be a non-empty string")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or str(pure) != relative or ".." in pure.parts:
        raise BootstrapError(f"runtime file path is not confined: {relative!r}")
    candidate = engine_root / relative
    current = engine_root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise BootstrapError(f"runtime file path contains a symlink: {relative}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(engine_root)
    except (OSError, ValueError) as exc:
        raise BootstrapError(
            f"runtime file path escapes or is missing: {relative}"
        ) from exc
    if not resolved.is_file():
        raise BootstrapError(f"runtime file is not regular: {relative}")
    return resolved


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


def _verify_repository_runtime(
    launch_assurance: str = DIRECT_IMPORT_ASSURANCE,
) -> VerificationReceipt:
    """Read and verify one complete manifest/engine snapshot."""

    if launch_assurance not in LAUNCH_ASSURANCES:
        raise BootstrapError("repository runtime launch assurance is invalid")

    bootstrap_path = Path(__file__).resolve(strict=True)
    engine_root = bootstrap_path.parents[2]
    repository_root = bootstrap_path.parents[4]
    if engine_root != repository_root / ENGINE_RELATIVE:
        raise BootstrapError("bootstrap engine location differs from the trust root")
    manifest, manifest_bytes = _load_manifest(repository_root / MANIFEST_RELATIVE)
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
    }
    for field, expected in required_values.items():
        if manifest.get(field) != expected:
            raise BootstrapError(f"installed manifest status drifted: {field}")
    if manifest.get("repository_runtime_path") != ENGINE_RELATIVE:
        raise BootstrapError("installed manifest runtime path differs")
    records = manifest.get("repository_runtime_files")
    if not isinstance(records, list) or not records:
        raise BootstrapError("installed manifest runtime file inventory is missing")
    expected_count = manifest.get("repository_runtime_file_count")
    if expected_count != len(records):
        raise BootstrapError("installed manifest runtime file count differs")

    for path in engine_root.rglob("*"):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            raise BootstrapError(f"runtime tree contains bytecode: {path}")
        if path.is_symlink():
            raise BootstrapError(f"runtime tree contains a symlink: {path}")
    actual = sorted(
        path.relative_to(engine_root).as_posix()
        for path in engine_root.rglob("*")
        if path.is_file()
    )
    declared = [record.get("path") for record in records if isinstance(record, dict)]
    if (
        len(declared) != len(records)
        or not all(isinstance(relative, str) for relative in declared)
        or declared != sorted(declared)
        or actual != declared
    ):
        raise BootstrapError("runtime file inventory differs from installed manifest")

    files: dict[str, bytes] = {}
    for record in records:
        if set(record) != {"path", "bytes", "sha256"}:
            raise BootstrapError("runtime file record fields are not exact")
        path = _confined_file(engine_root, record["path"])
        content = path.read_bytes()
        actual_digest = "sha256:" + hashlib.sha256(content).hexdigest()
        if record["bytes"] != len(content) or record["sha256"] != actual_digest:
            raise BootstrapError(f"runtime file bytes drifted: {record['path']}")
        files[record["path"]] = content
    if manifest.get("repository_runtime_digest_algorithm") != "elmos-tree-digest-v2":
        raise BootstrapError("installed manifest runtime digest algorithm differs")
    runtime_tree_sha256 = _tree_digest(files)
    if manifest.get("repository_runtime_tree_sha256") != runtime_tree_sha256:
        raise BootstrapError("installed manifest runtime tree digest differs")
    return VerificationReceipt(
        launch_assurance=launch_assurance,
        manifest_bytes=manifest_bytes,
        manifest_sha256="sha256:" + hashlib.sha256(manifest_bytes).hexdigest(),
        runtime_tree_sha256=runtime_tree_sha256,
        files=tuple((path, files[path]) for path in sorted(files)),
        file_digests=tuple(
            (path, "sha256:" + hashlib.sha256(files[path]).hexdigest())
            for path in sorted(files)
        ),
    )


def _receipt_from_launcher_snapshot(value: Any) -> VerificationReceipt:
    if not isinstance(value, dict) or set(value) != {
        "launch_assurance",
        "manifest_bytes",
        "manifest_sha256",
        "runtime_tree_sha256",
        "files",
        "file_digests",
    }:
        raise BootstrapError("verified launcher handoff fields are not exact")
    try:
        receipt = VerificationReceipt(
            launch_assurance=value["launch_assurance"],
            manifest_bytes=value["manifest_bytes"],
            manifest_sha256=value["manifest_sha256"],
            runtime_tree_sha256=value["runtime_tree_sha256"],
            files=value["files"],
            file_digests=value["file_digests"],
        )
    except (KeyError, TypeError) as exc:
        raise BootstrapError("verified launcher handoff is invalid") from exc
    if receipt.launch_assurance != ISOLATED_LAUNCH_ASSURANCE:
        raise BootstrapError("verified launcher assurance is invalid")
    if not isinstance(receipt.manifest_bytes, bytes) or receipt.manifest_sha256 != (
        "sha256:" + hashlib.sha256(receipt.manifest_bytes).hexdigest()
    ):
        raise BootstrapError("verified launcher manifest digest is invalid")
    if not isinstance(receipt.files, tuple) or not isinstance(
        receipt.file_digests, tuple
    ):
        raise BootstrapError("verified launcher file inventory is invalid")
    files = dict(receipt.files)
    digests = dict(receipt.file_digests)
    if (
        len(files) != len(receipt.files)
        or len(digests) != len(receipt.file_digests)
        or sorted(files) != sorted(digests)
        or _tree_digest(files) != receipt.runtime_tree_sha256
        or any(
            digests[path] != "sha256:" + hashlib.sha256(files[path]).hexdigest()
            for path in files
        )
    ):
        raise BootstrapError("verified launcher runtime receipt is inconsistent")
    return receipt


def initialize_repository_runtime() -> VerificationReceipt:
    """Set or confirm the immutable process snapshot before runtime imports."""

    global _INITIAL_RECEIPT
    if _INITIAL_RECEIPT is None:
        launcher_snapshot = globals().pop("_PREVERIFIED_LAUNCHER_SNAPSHOT", None)
        if launcher_snapshot is not None:
            _INITIAL_RECEIPT = _receipt_from_launcher_snapshot(launcher_snapshot)
    launch_assurance = (
        _INITIAL_RECEIPT.launch_assurance
        if _INITIAL_RECEIPT is not None
        else DIRECT_IMPORT_ASSURANCE
    )
    current = _verify_repository_runtime(launch_assurance)
    if _INITIAL_RECEIPT is None:
        _INITIAL_RECEIPT = current
    elif current != _INITIAL_RECEIPT:
        raise BootstrapError(
            "repository runtime changed after this process initialized; restart required"
        )
    return _INITIAL_RECEIPT


def assert_repository_runtime_unchanged() -> VerificationReceipt:
    """Refuse long-lived-process drift instead of misbinding loaded code."""

    if _INITIAL_RECEIPT is None:
        return initialize_repository_runtime()
    current = _verify_repository_runtime(_INITIAL_RECEIPT.launch_assurance)
    if current != _INITIAL_RECEIPT:
        raise BootstrapError(
            "repository runtime changed after this process initialized; restart required"
        )
    return current


def manifest_document(receipt: VerificationReceipt) -> dict[str, Any]:
    """Return a fresh strict parse of the exact manifest bytes in a receipt."""

    return _parse_manifest(receipt.manifest_bytes)


def verify_repository_runtime() -> VerificationReceipt:
    """Compatibility surface for an initialization-or-drift check."""

    return initialize_repository_runtime()


def _emit_error(exc: Exception) -> None:
    value = {
        "schema_version": "elmos.database-bigdata.error.v1",
        "state": "BLOCKED",
        "code": "PREIMPORT_RUNTIME_DIGEST_REJECTED",
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
    try:
        assert_repository_runtime_unchanged()
    except BootstrapError as exc:
        _emit_error(exc)
        return 2
    from .cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "BootstrapError",
    "VerificationReceipt",
    "assert_repository_runtime_unchanged",
    "initialize_repository_runtime",
    "main",
    "manifest_document",
    "verify_repository_runtime",
]
