from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import mimetypes
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable


SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("bearer-token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("password-assignment", re.compile(r"(?i)(password\s*[=:]\s*)[^\s,;]+")),
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def redact_text(text: str) -> tuple[str, list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    redacted = text
    for name, pattern in SECRET_PATTERNS:
        matches = list(pattern.finditer(redacted))
        if not matches:
            continue
        findings.append({"type": name, "count": len(matches)})
        if name == "password-assignment":
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted, findings


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class EvidenceStore:
    """Content-addressed evidence store with provenance and optional HMAC seal."""

    def __init__(self, root: Path, *, hmac_key: bytes | None = None):
        self.root = Path(root)
        self.blob_root = self.root / "blobs" / "sha256"
        self.manifest_path = self.root / "manifest.json"
        self.signature_path = self.root / "manifest.hmac-sha256"
        self.hmac_key = hmac_key
        self.root.mkdir(parents=True, exist_ok=True)
        self.blob_root.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self._write_manifest(
                {
                    "schema_version": "1.1",
                    "created_at": utc_now(),
                    "sealed_at": None,
                    "run": {},
                    "artifacts": [],
                    "events": [],
                    "root_digest": None,
                }
            )

    def _read_manifest(self) -> dict[str, Any]:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        _atomic_write(self.manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")

    @staticmethod
    def _event_digest(event: dict[str, Any]) -> str:
        return sha256_bytes(canonical_json_bytes(event))

    def _append_event(self, manifest: dict[str, Any], event_type: str, payload: dict[str, Any]) -> None:
        previous = manifest["events"][-1]["digest"] if manifest["events"] else None
        event = {
            "sequence": len(manifest["events"]) + 1,
            "at": utc_now(),
            "type": event_type,
            "previous_digest": previous,
            "payload": payload,
        }
        event["digest"] = self._event_digest(event)
        manifest["events"].append(event)

    def add_bytes(
        self,
        *,
        logical_name: str,
        data: bytes,
        media_type: str = "application/octet-stream",
        producer_environment: str,
        access_policy: str = "tenant-private",
        retention_class: str = "release-evidence",
        redact: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not logical_name or logical_name.startswith("/") or ".." in Path(logical_name).parts:
            raise ValueError("unsafe logical_name")
        findings: list[dict[str, Any]] = []
        content = data
        if redact:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                raise ValueError("redaction requested for non-UTF-8 artifact")
            redacted, findings = redact_text(text)
            content = redacted.encode("utf-8")
        digest = sha256_bytes(content)
        blob_path = self.blob_root / digest[:2] / digest
        if blob_path.exists() and sha256_bytes(blob_path.read_bytes()) != digest:
            raise RuntimeError("content-addressed blob corruption")
        if not blob_path.exists():
            _atomic_write(blob_path, content)
        manifest = self._read_manifest()
        existing = next((x for x in manifest["artifacts"] if x["logical_name"] == logical_name), None)
        if existing is not None and existing["sha256"] != digest:
            raise ValueError(f"logical artifact already bound to another digest: {logical_name}")
        if existing is not None:
            return existing
        artifact = {
            "artifact_id": f"sha256:{digest}",
            "logical_name": logical_name,
            "sha256": digest,
            "size": len(content),
            "media_type": media_type,
            "producer_environment": producer_environment,
            "access_policy": access_policy,
            "retention_class": retention_class,
            "redaction_status": "redacted" if findings else ("checked-clean" if redact else "not-checked"),
            "redaction_findings": findings,
            "created_at": utc_now(),
            "blob_path": str(blob_path.relative_to(self.root)),
            "metadata": metadata or {},
        }
        manifest["artifacts"].append(artifact)
        self._append_event(manifest, "artifact-added", {"logical_name": logical_name, "sha256": digest})
        self._write_manifest(manifest)
        return artifact

    def add_file(
        self,
        path: Path,
        *,
        logical_name: str | None = None,
        media_type: str | None = None,
        producer_environment: str,
        access_policy: str = "tenant-private",
        retention_class: str = "release-evidence",
        redact: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(path)
        return self.add_bytes(
            logical_name=logical_name or path.name,
            data=path.read_bytes(),
            media_type=media_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            producer_environment=producer_environment,
            access_policy=access_policy,
            retention_class=retention_class,
            redact=redact,
            metadata=metadata,
        )

    def add_json(self, *, logical_name: str, value: Any, producer_environment: str, **kwargs: Any) -> dict[str, Any]:
        return self.add_bytes(
            logical_name=logical_name,
            data=json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n",
            media_type="application/json",
            producer_environment=producer_environment,
            **kwargs,
        )

    def seal(self, run_metadata: dict[str, Any]) -> dict[str, Any]:
        manifest = self._read_manifest()
        if manifest.get("sealed_at"):
            raise RuntimeError("evidence bundle already sealed")
        manifest["run"] = run_metadata
        manifest["sealed_at"] = utc_now()
        self._append_event(manifest, "bundle-sealed", {"run_id": run_metadata.get("run_id")})
        material = dict(manifest)
        material["root_digest"] = None
        root_digest = sha256_bytes(canonical_json_bytes(material))
        manifest["root_digest"] = root_digest
        self._write_manifest(manifest)
        if self.hmac_key is not None:
            signature = hmac.new(self.hmac_key, self.manifest_path.read_bytes(), hashlib.sha256).hexdigest()
            _atomic_write(self.signature_path, (signature + "\n").encode("ascii"))
        return manifest

    def verify(self) -> dict[str, Any]:
        errors: list[str] = []
        manifest = self._read_manifest()
        for artifact in manifest.get("artifacts", []):
            blob = self.root / artifact["blob_path"]
            if not blob.exists():
                errors.append(f"missing blob: {artifact['logical_name']}")
                continue
            actual = sha256_bytes(blob.read_bytes())
            if actual != artifact["sha256"]:
                errors.append(f"digest mismatch: {artifact['logical_name']}")
            if blob.stat().st_size != artifact["size"]:
                errors.append(f"size mismatch: {artifact['logical_name']}")

        previous: str | None = None
        for event in manifest.get("events", []):
            event_copy = dict(event)
            recorded = event_copy.pop("digest", None)
            if event_copy.get("previous_digest") != previous:
                errors.append(f"event chain gap at sequence {event.get('sequence')}")
            calculated = self._event_digest(event_copy)
            if recorded != calculated:
                errors.append(f"event digest mismatch at sequence {event.get('sequence')}")
            previous = recorded

        if manifest.get("sealed_at"):
            material = dict(manifest)
            recorded_root = material.get("root_digest")
            material["root_digest"] = None
            actual_root = sha256_bytes(canonical_json_bytes(material))
            if recorded_root != actual_root:
                errors.append("manifest root digest mismatch")

        signature_status = "not-present"
        if self.signature_path.exists():
            if self.hmac_key is None:
                signature_status = "present-not-verified"
            else:
                expected = hmac.new(self.hmac_key, self.manifest_path.read_bytes(), hashlib.sha256).hexdigest()
                actual = self.signature_path.read_text(encoding="ascii").strip()
                if not hmac.compare_digest(expected, actual):
                    errors.append("manifest signature mismatch")
                    signature_status = "invalid"
                else:
                    signature_status = "valid"
        return {
            "valid": not errors,
            "artifact_count": len(manifest.get("artifacts", [])),
            "sealed": bool(manifest.get("sealed_at")),
            "signature_status": signature_status,
            "root_digest": manifest.get("root_digest"),
            "errors": errors,
        }


def create_bundle_from_paths(
    output_dir: Path,
    paths: Iterable[Path],
    *,
    producer_environment: str,
    run_metadata: dict[str, Any],
    hmac_key: bytes | None = None,
    redact_text_artifacts: bool = True,
) -> dict[str, Any]:
    store = EvidenceStore(output_dir, hmac_key=hmac_key)
    for path in paths:
        path = Path(path)
        if path.is_dir():
            for child in sorted(x for x in path.rglob("*") if x.is_file()):
                logical = str(child.relative_to(path.parent))
                store.add_file(
                    child,
                    logical_name=logical,
                    producer_environment=producer_environment,
                    redact=redact_text_artifacts and (mimetypes.guess_type(child.name)[0] or "").startswith("text/"),
                )
        else:
            store.add_file(
                path,
                logical_name=path.name,
                producer_environment=producer_environment,
                redact=redact_text_artifacts and (mimetypes.guess_type(path.name)[0] or "").startswith("text/"),
            )
    store.seal(run_metadata)
    return store.verify()
