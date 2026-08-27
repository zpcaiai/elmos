"""Content-addressed evidence storage and deterministic bundle creation."""

from __future__ import annotations

import hashlib
import gzip
import hmac
import json
import os
import re
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .canonical import canonical_json, digest_json, sha256_bytes


_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
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

    def __init__(self, root: Path, *, hmac_key: bytes | None = None) -> None:
        self.root = root.resolve()
        self.hmac_key = hmac_key
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.manifest_path = self.root / "manifest.json"
        if not self.manifest_path.exists():
            self.manifest_path.write_text(json.dumps({"schema_version": "1.1", "events": [], "sealed": False}, sort_keys=True) + "\n", encoding="utf-8")

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

    def _append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvidenceError("evidence manifest is unreadable") from exc
        if manifest.get("sealed"):
            raise EvidenceError("evidence ledger is already sealed")
        previous = manifest["events"][-1]["event_digest"] if manifest.get("events") else None
        event = {"sequence": len(manifest.get("events", [])), "event_type": event_type, "payload": payload, "previous_event_digest": previous}
        event["event_digest"] = digest_json(event)
        manifest.setdefault("events", []).append(event)
        temporary = self.manifest_path.with_name(f".{self.manifest_path.name}.tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self.manifest_path)

    def add_bytes(self, *, logical_name: str, data: bytes, media_type: str, producer_environment: str, redact: bool = False) -> dict[str, Any]:
        if not logical_name or logical_name.startswith("/") or ".." in Path(logical_name).parts:
            raise EvidenceError("unsafe logical_name")
        raw_digest = sha256_bytes(data)
        redacted = False
        stored = data
        if redact and media_type.startswith("text/"):
            text, redacted = redact_text(data.decode("utf-8", errors="replace"))
            stored = text.encode("utf-8")
        artifact = self.put_bytes(stored, media_type=media_type, role=logical_name, redacted=redacted)
        artifact.update({"artifact_id": "sha256:" + artifact["sha256"], "logical_name": logical_name, "producer_environment": producer_environment, "raw_sha256": raw_digest, "blob_path": str(self._path(artifact["sha256"]).relative_to(self.root))})
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        existing = next((item for item in manifest.setdefault("artifacts", []) if item.get("logical_name") == logical_name), None)
        if existing is not None:
            if existing.get("sha256") != artifact["sha256"]:
                raise EvidenceError(f"logical artifact already bound to another digest: {logical_name}")
            return existing
        manifest["artifacts"].append(artifact)
        self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self._append_event("artifact.added", artifact)
        return artifact

    def add_file(self, path: Path, *, logical_name: str, producer_environment: str, redact: bool = False) -> dict[str, Any]:
        if path.is_symlink() or not path.is_file():
            raise EvidenceError(f"evidence input must be a regular file: {path}")
        media_type = "text/plain" if path.suffix.lower() in {".txt", ".log", ".json", ".yaml", ".yml"} else "application/octet-stream"
        return self.add_bytes(logical_name=logical_name, data=path.read_bytes(), media_type=media_type, producer_environment=producer_environment, redact=redact)

    def add_json(self, *, logical_name: str, value: Any, producer_environment: str, **_: Any) -> dict[str, Any]:
        return self.add_bytes(logical_name=logical_name, data=canonical_json(value), media_type="application/json", producer_environment=producer_environment)

    def seal(self, run_metadata: dict[str, Any]) -> dict[str, Any]:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if manifest.get("sealed"):
            return manifest
        self._append_event("ledger.sealed", {"run_metadata": run_metadata})
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["sealed"] = True
        manifest["seal_digest"] = digest_json({key: value for key, value in manifest.items() if key not in {"seal_digest", "signature"}})
        if self.hmac_key:
            manifest["signature"] = hmac.new(self.hmac_key, manifest["seal_digest"].encode("utf-8"), hashlib.sha256).hexdigest()
        self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return manifest

    def verify(self, artifact: dict[str, Any] | None = None) -> Any:
        if artifact is not None:
            digest = artifact.get("sha256", "")
            path = self._path(digest)
            return path.is_file() and sha256_file(path) == digest and path.stat().st_size == artifact.get("size")
        errors: list[str] = []
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"valid": False, "errors": [str(exc)], "signature_status": "missing"}
        previous = None
        for event in manifest.get("events", []):
            unsigned = {key: event[key] for key in ("sequence", "event_type", "payload", "previous_event_digest")}
            if event.get("previous_event_digest") != previous or event.get("event_digest") != digest_json(unsigned):
                errors.append("event digest mismatch")
            previous = event.get("event_digest")
            payload = event.get("payload", {})
            if event.get("event_type") == "artifact.added" and not self.verify(payload):
                errors.append(f"artifact digest mismatch: {payload.get('sha256')}")
        signature_status = "unsigned"
        if manifest.get("sealed"):
            expected = digest_json({key: value for key, value in manifest.items() if key not in {"seal_digest", "signature"}})
            if manifest.get("seal_digest") != expected: errors.append("seal digest mismatch")
            if self.hmac_key:
                expected_signature = hmac.new(self.hmac_key, manifest["seal_digest"].encode("utf-8"), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(str(manifest.get("signature", "")), expected_signature): errors.append("evidence signature mismatch")
                else: signature_status = "valid"
            else: signature_status = "unverified"
        return {"valid": not errors, "errors": errors, "signature_status": signature_status, "event_count": len(manifest.get("events", [])), "sealed": bool(manifest.get("sealed"))}
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


def create_bundle_from_paths(output_dir: Path, paths: Iterable[Path], *, producer_environment: str, run_metadata: dict[str, Any], hmac_key: bytes | None = None, redact_text_artifacts: bool = True) -> dict[str, Any]:
    """Collect regular files into a sealed evidence ledger without executing them."""

    store = EvidenceStore(output_dir, hmac_key=hmac_key)
    for source in paths:
        source = Path(source)
        if source.is_symlink():
            raise EvidenceError(f"evidence input must be a regular file or directory: {source}")
        if source.is_dir():
            for child in sorted(path for path in source.rglob("*") if path.is_file() and not path.is_symlink()):
                logical_name = child.relative_to(source.parent).as_posix()
                store.add_file(child, logical_name=logical_name, producer_environment=producer_environment, redact=redact_text_artifacts and child.suffix.lower() in {".txt", ".log", ".json", ".yaml", ".yml"})
        elif source.is_file():
            store.add_file(source, logical_name=source.name, producer_environment=producer_environment, redact=redact_text_artifacts and source.suffix.lower() in {".txt", ".log", ".json", ".yaml", ".yml"})
        else:
            raise EvidenceError(f"evidence input does not exist: {source}")
    store.seal(run_metadata)
    return store.verify()
