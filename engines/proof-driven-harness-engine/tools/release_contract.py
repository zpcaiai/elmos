#!/usr/bin/env python3
"""Generate and verify the proof-harness release contract.

The contract is repository-owned release metadata.  It never executes the
untrusted source archive.  A successful check proves byte identity for the
listed local files only; it is not a signature, provenance attestation,
distribution approval, or certification decision.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import sysconfig
from typing import Any, Mapping, Sequence
import zipfile


ARTIFACT = "elmos-proof-driven-harness-engine@3.0.0"
MANIFEST_RELATIVE = Path("supply-chain/release-contract-manifest.json")
ASSET_INSTALL_RELATIVE = Path("share/elmos-proof-harness")
MAX_FILE_BYTES = 128 * 1024 * 1024
SCHEMA_NAMES = (
    "admission.schema.json",
    "adapter-contract.schema.json",
    "architecture-graph.schema.json",
    "completion-certificate.schema.json",
    "completion-review.schema.json",
    "domain-pack.schema.json",
    "environment-authority.schema.json",
    "evidence.schema.json",
    "goal-contract.schema.json",
    "invocation.schema.json",
    "proof-obligation-graph.schema.json",
    "proof-result.schema.json",
    "repository-evidence-graph.schema.json",
    "result.schema.json",
    "revision-set.schema.json",
    "semantic-ir.schema.json",
    "semantic-profile.schema.json",
    "workflow-ir.schema.json",
)
CLAIM_BOUNDARY = {
    "certification": "NOT_CERTIFIED",
    "commercialDistribution": "BLOCKED",
    "externalEvidence": "NOT_RUN",
    "localEngineeringMaximum": "READY_FOR_EXTERNAL_GATE",
}
EXCLUDED_NAMES = frozenset({"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"})


class ReleaseContractError(RuntimeError):
    """Raised when release-contract bytes fail closed."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def digest(payload: bytes) -> str:
    return "sha256:" + sha256_hex(payload)


def _safe_bytes(path: Path, *, limit: int = MAX_FILE_BYTES) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ReleaseContractError(f"cannot safely open release input {path}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ReleaseContractError(f"release input is not a regular file: {path}")
        if before.st_size > limit:
            raise ReleaseContractError(f"release input exceeds byte limit: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ReleaseContractError(f"release input exceeds byte limit: {path}")
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
            raise ReleaseContractError(f"release input changed while reading: {path}")
        return payload
    finally:
        os.close(descriptor)


def _relative(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ReleaseContractError(f"release path escapes engine root: {path}") from exc
    if path.is_symlink() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ReleaseContractError(f"unsafe release path: {relative}")
    return relative.as_posix()


def _glob_regular(root: Path, pattern: str) -> list[Path]:
    paths: list[Path] = []
    for path in sorted(root.glob(pattern)):
        relative = path.relative_to(root)
        if any(part in EXCLUDED_NAMES for part in relative.parts):
            continue
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ReleaseContractError(f"linked or special release member is forbidden: {relative}")
        paths.append(path)
    return paths


def inventory_paths(root: Path) -> list[tuple[str, Path]]:
    """Return the exact manifest-owned release inventory."""

    root = root.resolve(strict=True)
    paths: list[tuple[str, Path]] = []

    runtime_sources = _glob_regular(root, "src/elmos_proof_harness/**/*.py")
    if not runtime_sources:
        raise ReleaseContractError("runtime source inventory is empty")
    paths.extend(("runtime-source", path) for path in runtime_sources)

    schema_paths = [root / "schemas" / name for name in SCHEMA_NAMES]
    actual_schema_names = tuple(
        path.name for path in _glob_regular(root, "schemas/*.schema.json")
    )
    if tuple(sorted(actual_schema_names)) != tuple(sorted(SCHEMA_NAMES)):
        raise ReleaseContractError(
            "schema inventory must contain the exact 18 release schemas"
        )
    paths.extend(("json-schema", path) for path in schema_paths)

    exact = (
        ("openapi", root / "openapi/proof-harness-v3.openapi.yaml"),
        ("database-migration", root / "migrations/V001__proof_harness_core.sql"),
        ("observability-catalog", root / "observability/metrics.yaml"),
        ("observability-rule-source", root / "observability/alerts.yaml"),
        ("supply-chain-policy", root / "supply-chain/release-policy.json"),
        ("source-dependency-sbom", root / "supply-chain/sbom.cdx.json"),
        ("production-dependency-lock", root / "deploy/requirements-production.txt"),
        ("container-build-contract", root / "deploy/Dockerfile"),
        ("deployment-boundary", root / "deploy/README.md"),
        ("packaging-contract", root / "pyproject.toml"),
        ("implementation-boundary", root / "README.md"),
        ("postgres-migration-applicator", root / "tools/apply_postgres_migration.py"),
        ("release-contract-verifier", root / "tools/release_contract.py"),
        ("structured-test-runner", root / "tools/run_structured_unittest.py"),
        ("local-qualification-producer", root / "tools/qualify_local.py"),
        ("verification-pack-publisher", root / "tools/publish_verification_pack.py"),
    )
    paths.extend(exact)
    paths.extend(
        ("helm-release-asset", path)
        for path in _glob_regular(root, "deploy/helm/proof-harness/**/*")
    )

    seen: set[str] = set()
    normalized: list[tuple[str, Path]] = []
    for role, path in paths:
        relative = _relative(path, root)
        if relative == MANIFEST_RELATIVE.as_posix():
            raise ReleaseContractError("manifest cannot include itself in its content root")
        if relative in seen:
            raise ReleaseContractError(f"duplicate release inventory path: {relative}")
        seen.add(relative)
        normalized.append((role, path))
    return sorted(normalized, key=lambda item: _relative(item[1], root))


def build_manifest(root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    files: list[dict[str, Any]] = []
    role_counts: dict[str, int] = {}
    for role, path in inventory_paths(root):
        payload = _safe_bytes(path)
        files.append(
            {
                "bytes": len(payload),
                "path": _relative(path, root),
                "role": role,
                "sha256": digest(payload),
            }
        )
        role_counts[role] = role_counts.get(role, 0) + 1
    body: dict[str, Any] = {
        "artifact": ARTIFACT,
        "claimBoundary": CLAIM_BOUNDARY,
        "counts": {
            "files": len(files),
            "roles": dict(sorted(role_counts.items())),
            "schemas": len(SCHEMA_NAMES),
        },
        "files": files,
        "hashAlgorithm": "sha256",
        "kind": "elmos.proof-harness.release-contract",
        "schemaVersion": "1.0.0",
    }
    return {**body, "contractRoot": digest(canonical_bytes(body))}


def _load_manifest(payload: bytes, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseContractError(f"invalid release manifest JSON ({label}): {exc}") from exc
    if not isinstance(value, dict):
        raise ReleaseContractError(f"release manifest must be an object ({label})")
    if payload != json_bytes(value):
        raise ReleaseContractError(f"release manifest is not canonical JSON ({label})")
    expected_keys = {
        "artifact",
        "claimBoundary",
        "contractRoot",
        "counts",
        "files",
        "hashAlgorithm",
        "kind",
        "schemaVersion",
    }
    if set(value) != expected_keys:
        raise ReleaseContractError(f"release manifest fields are not exact ({label})")
    body = {key: value[key] for key in value if key != "contractRoot"}
    if value["contractRoot"] != digest(canonical_bytes(body)):
        raise ReleaseContractError(f"release manifest contract root mismatch ({label})")
    if (
        value["artifact"] != ARTIFACT
        or value["claimBoundary"] != CLAIM_BOUNDARY
        or value["hashAlgorithm"] != "sha256"
        or value["kind"] != "elmos.proof-harness.release-contract"
        or value["schemaVersion"] != "1.0.0"
    ):
        raise ReleaseContractError(f"release manifest identity/boundary mismatch ({label})")
    return value


def _expected_manifest_digest(value: str | None, payload: bytes) -> None:
    if value is None:
        return
    expected = value.removeprefix("sha256:")
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise ReleaseContractError("expected manifest SHA-256 is malformed")
    if sha256_hex(payload) != expected:
        raise ReleaseContractError("release manifest byte digest does not match the supplied pin")


def check_repository(root: Path, expected_manifest_sha256: str | None = None) -> Mapping[str, Any]:
    root = root.resolve(strict=True)
    manifest_path = root / MANIFEST_RELATIVE
    payload = _safe_bytes(manifest_path)
    manifest = _load_manifest(payload, manifest_path.as_posix())
    _expected_manifest_digest(expected_manifest_sha256, payload)
    expected = build_manifest(root)
    if manifest != expected:
        expected_by_path = {item["path"]: item for item in expected["files"]}
        actual_by_path = {
            item.get("path"): item
            for item in manifest.get("files", [])
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        missing = sorted(set(expected_by_path).difference(actual_by_path))
        unexpected = sorted(set(actual_by_path).difference(expected_by_path))
        changed = sorted(
            path
            for path in set(expected_by_path).intersection(actual_by_path)
            if expected_by_path[path] != actual_by_path[path]
        )
        raise ReleaseContractError(
            "release contract drift: "
            f"missing={missing}, unexpected={unexpected}, changed={changed}"
        )
    return manifest


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    directory_fd = os.open(
        path.parent,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    temporary = f".{path.name}.{os.getpid()}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o644,
            dir_fd=directory_fd,
        )
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise ReleaseContractError(f"short write: {path}")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)


def generate(root: Path) -> Mapping[str, Any]:
    root = root.resolve(strict=True)
    manifest = build_manifest(root)
    _atomic_write(root / MANIFEST_RELATIVE, json_bytes(manifest))
    return check_repository(root)


def _safe_zip_members(archive: zipfile.ZipFile) -> Mapping[str, zipfile.ZipInfo]:
    members: dict[str, zipfile.ZipInfo] = {}
    normalized_names: set[str] = set()
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        normalized = path.as_posix()
        if (
            info.is_dir()
            or path.is_absolute()
            or not path.parts
            or any(part in {"", ".", ".."} for part in path.parts)
            or "\\" in info.filename
            or normalized in normalized_names
            or info.flag_bits & 0x1
        ):
            raise ReleaseContractError(f"unsafe or duplicate wheel member: {info.filename!r}")
        normalized_names.add(normalized)
        if info.file_size > MAX_FILE_BYTES:
            raise ReleaseContractError(f"wheel member exceeds byte limit: {normalized}")
        mode = (info.external_attr >> 16) & 0xFFFF
        if mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG}:
            raise ReleaseContractError(f"linked or special wheel member: {normalized}")
        members[normalized] = info
    return members


def _wheel_path(path: Path) -> Path:
    path = path.resolve(strict=True)
    if path.is_dir():
        wheels = sorted(path.glob("elmos_proof_driven_harness_engine-3.0.0-*.whl"))
        if len(wheels) != 1:
            raise ReleaseContractError(
                f"expected exactly one proof-harness wheel in {path}, found {len(wheels)}"
            )
        path = wheels[0]
    if path.is_symlink() or not path.is_file() or path.suffix != ".whl":
        raise ReleaseContractError(f"wheel path must be a real .whl file: {path}")
    return path


def _wheel_member_for_entry(path: str, data_prefix: str) -> str:
    runtime_prefix = "src/elmos_proof_harness/"
    if path.startswith(runtime_prefix):
        return "elmos_proof_harness/" + path.removeprefix(runtime_prefix)
    return data_prefix + ASSET_INSTALL_RELATIVE.as_posix() + "/" + path


def check_wheel(
    wheel: Path,
    *,
    repository_root: Path | None = None,
    expected_manifest_sha256: str | None = None,
) -> Mapping[str, Any]:
    wheel = _wheel_path(wheel)
    with zipfile.ZipFile(wheel) as archive:
        members = _safe_zip_members(archive)
        suffix = ".data/data/" + ASSET_INSTALL_RELATIVE.as_posix() + "/"
        candidates = [name for name in members if suffix in name]
        prefixes = {name.split(suffix, 1)[0] + ".data/data/" for name in candidates}
        if len(prefixes) != 1:
            raise ReleaseContractError("wheel has no unique release-asset data prefix")
        data_prefix = next(iter(prefixes))
        manifest_member = data_prefix + ASSET_INSTALL_RELATIVE.as_posix() + "/" + MANIFEST_RELATIVE.as_posix()
        if manifest_member not in members:
            raise ReleaseContractError("wheel does not contain the release manifest")
        manifest_payload = archive.read(members[manifest_member])
        manifest = _load_manifest(manifest_payload, manifest_member)
        _expected_manifest_digest(expected_manifest_sha256, manifest_payload)
        if repository_root is not None:
            repository_manifest = _safe_bytes(
                repository_root.resolve(strict=True) / MANIFEST_RELATIVE
            )
            if repository_manifest != manifest_payload:
                raise ReleaseContractError("wheel manifest bytes differ from repository manifest")
        expected_members = {manifest_member}
        for entry in manifest["files"]:
            if not isinstance(entry, dict) or set(entry) != {"bytes", "path", "role", "sha256"}:
                raise ReleaseContractError("release manifest file entry is not exact")
            member_name = _wheel_member_for_entry(entry["path"], data_prefix)
            expected_members.add(member_name)
            info = members.get(member_name)
            if info is None:
                raise ReleaseContractError(f"wheel is missing release member: {member_name}")
            payload = archive.read(info)
            if len(payload) != entry["bytes"] or digest(payload) != entry["sha256"]:
                raise ReleaseContractError(f"wheel release member digest mismatch: {member_name}")
        release_prefix = data_prefix + ASSET_INSTALL_RELATIVE.as_posix() + "/"
        actual_assets = {name for name in members if name.startswith(release_prefix)}
        actual_runtime = {name for name in members if name.startswith("elmos_proof_harness/")}
        expected_runtime = {name for name in expected_members if name.startswith("elmos_proof_harness/")}
        expected_assets = expected_members.difference(expected_runtime)
        if actual_assets != expected_assets or actual_runtime != expected_runtime:
            raise ReleaseContractError("wheel release/runtime member set does not match manifest")
        return manifest


def check_installed(
    assets_root: Path | None,
    module_root: Path | None = None,
    expected_manifest_sha256: str | None = None,
) -> Mapping[str, Any]:
    assets_root = (
        assets_root.resolve(strict=True)
        if assets_root is not None
        else (Path(sysconfig.get_path("data")) / ASSET_INSTALL_RELATIVE).resolve(strict=True)
    )
    if module_root is None:
        spec = importlib.util.find_spec("elmos_proof_harness")
        if spec is None or not spec.submodule_search_locations:
            raise ReleaseContractError("installed elmos_proof_harness package is unavailable")
        locations = list(spec.submodule_search_locations)
        if len(locations) != 1:
            raise ReleaseContractError("installed elmos_proof_harness package location is ambiguous")
        module_root = Path(locations[0]).resolve(strict=True)
    else:
        module_root = module_root.resolve(strict=True)
    manifest_payload = _safe_bytes(assets_root / MANIFEST_RELATIVE)
    manifest = _load_manifest(manifest_payload, "installed release manifest")
    _expected_manifest_digest(expected_manifest_sha256, manifest_payload)
    runtime_prefix = "src/elmos_proof_harness/"
    expected_runtime: set[Path] = set()
    expected_assets: set[Path] = {MANIFEST_RELATIVE}
    for entry in manifest["files"]:
        relative = entry["path"]
        if relative.startswith(runtime_prefix):
            target_relative = Path(relative.removeprefix(runtime_prefix))
            target = module_root / target_relative
            expected_runtime.add(target_relative)
        else:
            target_relative = Path(*PurePosixPath(relative).parts)
            target = assets_root / target_relative
            expected_assets.add(target_relative)
        payload = _safe_bytes(target)
        if len(payload) != entry["bytes"] or digest(payload) != entry["sha256"]:
            raise ReleaseContractError(f"installed release member digest mismatch: {relative}")
    actual_runtime = {
        path.relative_to(module_root)
        for path in module_root.rglob("*.py")
        if path.is_file() and not path.is_symlink()
    }
    actual_assets = {
        path.relative_to(assets_root)
        for path in assets_root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if actual_runtime != expected_runtime or actual_assets != expected_assets:
        raise ReleaseContractError("installed release/runtime member set does not match manifest")
    return manifest


def _result(mode: str, manifest: Mapping[str, Any], manifest_payload: bytes) -> dict[str, Any]:
    return {
        "artifact": ARTIFACT,
        "certification": "NOT_CERTIFIED",
        "commercial_distribution": "BLOCKED",
        "contract_root": manifest["contractRoot"],
        "external_evidence": "NOT_RUN",
        "files": manifest["counts"]["files"],
        "manifest_sha256": digest(manifest_payload),
        "mode": mode,
        "status": "PASS",
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="proof-harness engine root",
    )
    parser.add_argument("--expected-manifest-sha256")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--generate", action="store_true")
    action.add_argument("--check", action="store_true")
    action.add_argument("--check-wheel", type=Path)
    action.add_argument("--check-installed", action="store_true")
    parser.add_argument("--assets-root", type=Path)
    parser.add_argument("--module-root", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.generate:
            manifest = generate(args.root)
            mode = "generate"
            payload = _safe_bytes(args.root.resolve(strict=True) / MANIFEST_RELATIVE)
            _expected_manifest_digest(args.expected_manifest_sha256, payload)
        elif args.check:
            manifest = check_repository(args.root, args.expected_manifest_sha256)
            mode = "repository-check"
            payload = _safe_bytes(args.root.resolve(strict=True) / MANIFEST_RELATIVE)
        elif args.check_wheel is not None:
            manifest = check_wheel(
                args.check_wheel,
                repository_root=args.root,
                expected_manifest_sha256=args.expected_manifest_sha256,
            )
            mode = "wheel-check"
            payload = _safe_bytes(args.root.resolve(strict=True) / MANIFEST_RELATIVE)
        else:
            manifest = check_installed(
                args.assets_root,
                args.module_root,
                args.expected_manifest_sha256,
            )
            mode = "installed-check"
            asset_root = args.assets_root or Path(sysconfig.get_path("data")) / ASSET_INSTALL_RELATIVE
            payload = _safe_bytes(asset_root.resolve(strict=True) / MANIFEST_RELATIVE)
    except (OSError, ValueError, zipfile.BadZipFile, ReleaseContractError) as exc:
        print(
            json.dumps(
                {
                    "certification": "NOT_CERTIFIED",
                    "commercial_distribution": "BLOCKED",
                    "error": str(exc),
                    "status": "FAIL",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(_result(mode, manifest, payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
