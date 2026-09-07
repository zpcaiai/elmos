#!/usr/bin/env python3
"""Materialize and verify self-contained FRT repository evidence.

The Batch 32 client-pack gate deliberately rejects references that escape the
pack root.  This tool copies the small, explicitly approved repository evidence
closure into the FRT client pack and binds every byte to its tracked source,
Git revision, role, artifact identity, producer, and aggregate digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


PACK_KEY = "frt-g01-g30-platform"
REPOSITORY = "zpcaiai/elmos"
MANIFEST_REF = "repository-evidence/manifest.json"
DEFAULT_PACK = Path("client-packs/frt-g01-g30-platform")
ARTIFACT_SPECS = (
    {
        "role": "installed-skill-manifest",
        "source_path": "docs/frt-g01-g30/installed-manifest.json",
        "path": "repository-evidence/files/docs/frt-g01-g30/installed-manifest.json",
    },
    {
        "role": "frontend-runtime-test-source",
        "source_path": "engines/frontend-client-engine/test/frt-runtime.test.ts",
        "path": (
            "repository-evidence/files/engines/frontend-client-engine/test/"
            "frt-runtime.test.ts"
        ),
    },
    {
        "role": "web-browser-journey-source",
        "source_path": "apps/web-console/e2e/frt-frontend-transformation.spec.ts",
        "path": (
            "repository-evidence/files/apps/web-console/e2e/"
            "frt-frontend-transformation.spec.ts"
        ),
    },
)
REFERENCE_DOCUMENTS = (
    "source-fingerprint/fingerprint.json",
    "route-matrix.json",
    "certification/evidence.json",
    "certification/certification.json",
)
REFERENCE_REPLACEMENTS = {
    "../../../docs/frt-g01-g30/installed-manifest.json": ARTIFACT_SPECS[0]["path"],
    "../../docs/frt-g01-g30/installed-manifest.json": ARTIFACT_SPECS[0]["path"],
    "../../../engines/frontend-client-engine/test/frt-runtime.test.ts": (
        ARTIFACT_SPECS[1]["path"]
    ),
    "../../engines/frontend-client-engine/test/frt-runtime.test.ts": (
        ARTIFACT_SPECS[1]["path"]
    ),
    "../../apps/web-console/e2e/frt-frontend-transformation.spec.ts": (
        ARTIFACT_SPECS[2]["path"]
    ),
}


class RepositoryEvidenceError(ValueError):
    """Raised when the repository evidence closure is unsafe or stale."""


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return digest_bytes(encoded)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepositoryEvidenceError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RepositoryEvidenceError(f"JSON root must be an object: {path}")
    return value


def safe_relative_path(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise RepositoryEvidenceError(f"{label} must be a safe relative path")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RepositoryEvidenceError(f"{label} must be a safe relative path: {value}")
    return path


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write(
        path,
        (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    )


def run_git(repo_root: Path, *arguments: str, binary: bool = False) -> bytes | str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RepositoryEvidenceError(
            f"git {' '.join(arguments)} failed: {detail or completed.returncode}"
        )
    return completed.stdout if binary else completed.stdout.decode("utf-8").strip()


def assert_clean_sources(repo_root: Path) -> None:
    sources = [str(spec["source_path"]) for spec in ARTIFACT_SPECS]
    status = run_git(repo_root, "status", "--porcelain=v1", "--", *sources)
    if status:
        raise RepositoryEvidenceError(
            "repository evidence sources must be tracked and unmodified: "
            + str(status).replace("\n", ", ")
        )


def replace_references(value: Any) -> tuple[Any, bool]:
    if isinstance(value, str):
        replacement = REFERENCE_REPLACEMENTS.get(value)
        return (replacement, True) if replacement is not None else (value, False)
    if isinstance(value, list):
        output: list[Any] = []
        changed = False
        for item in value:
            replacement, item_changed = replace_references(item)
            output.append(replacement)
            changed = changed or item_changed
        if changed and MANIFEST_REF not in output:
            output.append(MANIFEST_REF)
        return output, changed
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        changed = False
        for key, item in value.items():
            replacement, item_changed = replace_references(item)
            output[key] = replacement
            changed = changed or item_changed
        return output, changed
    return value, False


def iter_evidence_refs(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized in {"evidence_ref", "evidence_refs"}:
                if isinstance(item, str):
                    yield item
                elif isinstance(item, list):
                    yield from (entry for entry in item if isinstance(entry, str))
            yield from iter_evidence_refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_evidence_refs(item)


def materialize(repo_root: Path, pack: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve(strict=True)
    pack = pack.resolve(strict=True)
    assert_clean_sources(repo_root)
    revision = str(run_git(repo_root, "rev-parse", "HEAD"))
    if len(revision) != 40:
        raise RepositoryEvidenceError("repository revision is not a full Git SHA")

    artifacts: list[dict[str, Any]] = []
    for spec in ARTIFACT_SPECS:
        source_relative = safe_relative_path(spec["source_path"], "source_path")
        target_relative = safe_relative_path(spec["path"], "artifact path")
        source = repo_root / source_relative
        if not source.is_file() or source.is_symlink():
            raise RepositoryEvidenceError(f"source evidence is missing or unsafe: {source_relative}")
        data = source.read_bytes()
        digest = digest_bytes(data)
        target = pack / target_relative
        atomic_write(target, data)
        artifacts.append(
            {
                "artifact_id": f"artifact:{digest}",
                "role": spec["role"],
                "source_path": source_relative.as_posix(),
                "path": target_relative.as_posix(),
                "sha256": digest,
                "bytes": len(data),
            }
        )

    producer_relative = Path(__file__).resolve().relative_to(repo_root)
    producer_data = (repo_root / producer_relative).read_bytes()
    manifest = {
        "schema_version": 1,
        "pack_key": PACK_KEY,
        "repository": REPOSITORY,
        "repository_revision": revision,
        "status": "LOCAL_CONTENT_BOUND",
        "external_verification": "NOT_RUN",
        "production_operation_authorized": False,
        "production_certification": "NOT_CERTIFIED",
        "producer": {
            "path": producer_relative.as_posix(),
            "sha256": digest_bytes(producer_data),
            "bytes": len(producer_data),
        },
        "artifacts": artifacts,
        "aggregate_sha256": canonical_digest(artifacts),
    }
    write_json(pack / MANIFEST_REF, manifest)

    replaced_total = 0
    for relative in REFERENCE_DOCUMENTS:
        path = pack / relative
        document = load_json(path)
        replaced, changed = replace_references(document)
        if changed:
            write_json(path, replaced)
            replaced_total += 1
    if replaced_total != len(REFERENCE_DOCUMENTS):
        raise RepositoryEvidenceError(
            "repository evidence reference closure was not updated in every document"
        )
    validate(repo_root, pack)
    return manifest


def validate(repo_root: Path, pack: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve(strict=True)
    pack = pack.resolve(strict=True)
    manifest = load_json(pack / MANIFEST_REF)
    if (
        manifest.get("schema_version") != 1
        or manifest.get("pack_key") != PACK_KEY
        or manifest.get("repository") != REPOSITORY
        or manifest.get("status") != "LOCAL_CONTENT_BOUND"
        or manifest.get("external_verification") != "NOT_RUN"
        or manifest.get("production_operation_authorized") is not False
        or manifest.get("production_certification") != "NOT_CERTIFIED"
    ):
        raise RepositoryEvidenceError("repository evidence manifest boundary is invalid")

    revision = manifest.get("repository_revision")
    if not isinstance(revision, str) or len(revision) != 40:
        raise RepositoryEvidenceError("repository evidence revision is invalid")
    run_git(repo_root, "cat-file", "-e", f"{revision}^{{commit}}")

    producer = manifest.get("producer")
    if not isinstance(producer, dict):
        raise RepositoryEvidenceError("repository evidence producer is missing")
    producer_path = safe_relative_path(producer.get("path"), "producer path")
    producer_file = repo_root / producer_path
    producer_data = producer_file.read_bytes()
    if (
        producer.get("sha256") != digest_bytes(producer_data)
        or producer.get("bytes") != len(producer_data)
    ):
        raise RepositoryEvidenceError("repository evidence producer is stale")

    rows = manifest.get("artifacts")
    if not isinstance(rows, list) or len(rows) != len(ARTIFACT_SPECS):
        raise RepositoryEvidenceError("repository evidence artifact inventory is incomplete")
    expected_by_source = {str(spec["source_path"]): spec for spec in ARTIFACT_SPECS}
    seen_sources: set[str] = set()
    seen_paths: set[str] = set()
    seen_ids: set[str] = set()
    declared_files: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise RepositoryEvidenceError("repository evidence artifact row is invalid")
        source_path = safe_relative_path(row.get("source_path"), "artifact source_path")
        target_path = safe_relative_path(row.get("path"), "artifact path")
        source_name = source_path.as_posix()
        target_name = target_path.as_posix()
        expected = expected_by_source.get(source_name)
        if expected is None or target_name != expected["path"] or row.get("role") != expected["role"]:
            raise RepositoryEvidenceError(f"unexpected repository evidence mapping: {source_name}")
        if not target_name.startswith("repository-evidence/files/"):
            raise RepositoryEvidenceError(f"artifact escapes repository evidence root: {target_name}")
        artifact_id = row.get("artifact_id")
        digest = row.get("sha256")
        byte_count = row.get("bytes")
        if (
            not isinstance(artifact_id, str)
            or not isinstance(digest, str)
            or artifact_id != f"artifact:{digest}"
            or not digest.startswith("sha256:")
            or len(digest) != 71
            or not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or byte_count < 0
        ):
            raise RepositoryEvidenceError(f"artifact identity is invalid: {source_name}")
        if source_name in seen_sources or target_name in seen_paths or artifact_id in seen_ids:
            raise RepositoryEvidenceError("repository evidence identity is ambiguous")
        seen_sources.add(source_name)
        seen_paths.add(target_name)
        seen_ids.add(artifact_id)
        declared_files.add(target_name.removeprefix("repository-evidence/files/"))

        target = pack / target_path
        source = repo_root / source_path
        if (
            not target.is_file()
            or target.is_symlink()
            or not source.is_file()
            or source.is_symlink()
        ):
            raise RepositoryEvidenceError(f"artifact or source is missing or unsafe: {source_name}")
        target_data = target.read_bytes()
        source_data = source.read_bytes()
        revision_data = run_git(repo_root, "show", f"{revision}:{source_name}", binary=True)
        assert isinstance(revision_data, bytes)
        if (
            len(target_data) != byte_count
            or digest_bytes(target_data) != digest
            or target_data != source_data
            or target_data != revision_data
        ):
            raise RepositoryEvidenceError(f"repository evidence content drift: {source_name}")

    if seen_sources != set(expected_by_source):
        raise RepositoryEvidenceError("repository evidence source closure is not exact")
    files_root = pack / "repository-evidence" / "files"
    actual_files = {
        path.relative_to(files_root).as_posix()
        for path in files_root.rglob("*")
        if path.is_file()
    }
    if actual_files != declared_files:
        raise RepositoryEvidenceError("repository evidence file set is not exact")
    if manifest.get("aggregate_sha256") != canonical_digest(rows):
        raise RepositoryEvidenceError("repository evidence aggregate digest mismatch")

    all_refs: set[str] = set()
    for relative in REFERENCE_DOCUMENTS:
        document = load_json(pack / relative)
        refs = set(iter_evidence_refs(document))
        if any(Path(ref).is_absolute() or ".." in Path(ref).parts for ref in refs):
            raise RepositoryEvidenceError(f"unsafe evidence reference remains in {relative}")
        all_refs.update(refs)
    expected_refs = {str(spec["path"]) for spec in ARTIFACT_SPECS}
    if MANIFEST_REF not in all_refs or not expected_refs.issubset(all_refs):
        raise RepositoryEvidenceError("repository evidence references are incomplete")
    if any(reference in all_refs for reference in REFERENCE_REPLACEMENTS):
        raise RepositoryEvidenceError("legacy escaping evidence reference remains")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("materialize", "check"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    pack = args.pack if args.pack.is_absolute() else repo_root / args.pack
    try:
        result = (
            materialize(repo_root, pack)
            if args.mode == "materialize"
            else validate(repo_root, pack)
        )
    except (OSError, RepositoryEvidenceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        "OK: FRT repository evidence "
        f"artifacts={len(result['artifacts'])} "
        f"revision={result['repository_revision']} "
        f"external={result['external_verification']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
