"""Content-addressed evidence storage and deterministic bundle creation."""

from __future__ import annotations

import hashlib
import gzip
import json
import os
import re
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .canonical import canonical_json, digest_json, sha256_bytes


_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(\b(?:token|password|secret|api[_-]?key)\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(?i)(-----BEGIN [A-Z ]+ PRIVATE KEY-----)[\s\S]*?(-----END [A-Z ]+ PRIVATE KEY-----)"),
)


def redact_text(value: str) -> tuple[str, bool]:
    redacted = value
    changed = False
    for pattern in _SECRET_PATTERNS:
        redacted, count = pattern.subn(lambda match: f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED]", redacted)
        changed = changed or count > 0
    return redacted, changed


class EvidenceError(ValueError):
    """Raised when evidence cannot be safely persisted or verified."""


class EvidenceStore:
    """Write immutable blobs below a single tenant/run-scoped directory."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    def _path(self, digest: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise EvidenceError("invalid SHA-256 digest")
        return self.root / digest[:2] / digest

    def put_bytes(self, data: bytes, *, media_type: str, role: str, redacted: bool = False) -> dict[str, Any]:
        digest = sha256_bytes(data)
        destination = self._path(digest)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != data:
                raise EvidenceError(f"content address collision: {digest}")
        else:
            fd, temporary_name = tempfile.mkstemp(prefix=".evidence-", dir=destination.parent)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        return {
            "role": role,
            "uri": f"sha256:{digest}",
            "sha256": digest,
            "media_type": media_type,
            "size": len(data),
            "redacted": redacted,
        }

    def put_text(self, value: str, *, media_type: str, role: str, redact: bool = True) -> dict[str, Any]:
        content = value
        redacted = False
        raw_digest = sha256_bytes(value.encode("utf-8"))
        if redact:
            content, redacted = redact_text(value)
        artifact = self.put_bytes(content.encode("utf-8"), media_type=media_type, role=role, redacted=redacted)
        artifact["raw_sha256"] = raw_digest
        return artifact

    def put_json(self, value: Any, *, role: str) -> dict[str, Any]:
        return self.put_bytes(canonical_json(value), media_type="application/json", role=role)

    def verify(self, artifact: dict[str, Any]) -> bool:
        digest = artifact.get("sha256", "")
        path = self._path(digest)
        return path.is_file() and sha256_file(path) == digest and path.stat().st_size == artifact.get("size")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_evidence_manifest(*, run_id: str, case_id: str, result: dict[str, Any], artifacts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    artifact_list = sorted((dict(item) for item in artifacts), key=lambda item: (item.get("role", ""), item.get("sha256", "")))
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "case_id": case_id,
        "result_sha256": digest_json(result),
        "artifacts": artifact_list,
        "manifest_sha256": digest_json({"run_id": run_id, "case_id": case_id, "result_sha256": digest_json(result), "artifacts": artifact_list}),
    }


def verify_evidence_manifest(manifest: dict[str, Any], store: EvidenceStore) -> list[str]:
    errors: list[str] = []
    required = {"schema_version", "run_id", "case_id", "result_sha256", "artifacts", "manifest_sha256"}
    errors.extend(f"missing manifest field: {key}" for key in sorted(required - manifest.keys()))
    if errors:
        return errors
    if manifest["schema_version"] != "1.0":
        errors.append("unsupported evidence manifest version")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("evidence manifest requires at least one artifact")
    else:
        for artifact in artifacts:
            try:
                valid = isinstance(artifact, dict) and store.verify(artifact)
            except EvidenceError:
                valid = False
            if not valid:
                errors.append(f"missing or tampered artifact: {artifact.get('sha256') if isinstance(artifact, dict) else artifact}")
    unsigned = {key: manifest[key] for key in ("run_id", "case_id", "result_sha256", "artifacts")}
    if manifest["manifest_sha256"] != digest_json(unsigned):
        errors.append("manifest digest mismatch")
    return errors


def create_deterministic_bundle(source_root: Path, output: Path) -> dict[str, Any]:
    """Create a reproducible gzip tar of evidence files, excluding the output."""

    source_root = source_root.resolve(strict=True)
    output = output.resolve()
    files = sorted(path for path in source_root.rglob("*") if path.is_file() and not path.is_symlink() and path.resolve() != output)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as bundle:
                    for path in files:
                        relative = path.relative_to(source_root).as_posix()
                        info = tarfile.TarInfo(relative)
                        data = path.read_bytes()
                        info.size = len(data)
                        info.mode = 0o600
                        info.mtime = 0
                        info.uid = 0
                        info.gid = 0
                        info.uname = ""
                        info.gname = ""
                        bundle.addfile(info, __import__("io").BytesIO(data))
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": str(output), "sha256": sha256_file(output), "files": len(files), "bytes": output.stat().st_size}
