#!/usr/bin/env python3
"""Ed25519 actor authentication for migration evidence and decisions."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def read_regular(path: Path, maximum: int, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode) or observed.st_size > maximum:
            raise ValueError(f"{label} must be a bounded regular file")
        data = b""
        while len(data) < observed.st_size:
            chunk = os.read(descriptor, min(65536, observed.st_size - len(data)))
            if not chunk:
                raise ValueError(f"{label} changed while being read")
            data += chunk
        if os.read(descriptor, 1):
            raise ValueError(f"{label} changed while being read")
        return data
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class TrustedActor:
    actor_id: str
    key_id: str
    roles: frozenset[str]
    public_key: bytes
    not_before: datetime
    not_after: datetime


@dataclass(frozen=True)
class ActorTrustStore:
    path: Path
    actors: dict[str, TrustedActor]
    revoked_records: frozenset[str]
    digest: str

    @classmethod
    def load(cls, path: Path) -> "ActorTrustStore":
        resolved = path.expanduser().resolve(strict=True)
        raw = read_regular(resolved, 1024 * 1024, "actor trust store")
        payload = json.loads(raw.decode("utf-8"))
        if payload.get("schema_version") != "1.0":
            raise ValueError("actor trust store schema_version must be 1.0")
        entries = payload.get("actors")
        if not isinstance(entries, list):
            raise ValueError("actor trust store actors must be an array")
        actors: dict[str, TrustedActor] = {}
        actor_ids: set[str] = set()
        key_ids: set[str] = set()
        key_digests: dict[str, str] = {}
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ValueError(f"actors[{index}] must be an object")
            actor_id = entry.get("actor_id")
            key_id = entry.get("key_id")
            roles = entry.get("roles")
            relative = entry.get("public_key_path")
            if not isinstance(actor_id, str) or not actor_id or actor_id in actor_ids:
                raise ValueError(f"actors[{index}].actor_id is invalid")
            if not isinstance(key_id, str) or not key_id or key_id in key_ids:
                raise ValueError(f"actors[{index}].key_id is invalid")
            if not isinstance(roles, list) or not roles or any(not isinstance(role, str) or not role for role in roles):
                raise ValueError(f"actors[{index}].roles is invalid")
            if not isinstance(relative, str) or not relative:
                raise ValueError(f"actors[{index}].public_key_path is invalid")
            key_path = (resolved.parent / relative).resolve(strict=True)
            if resolved.parent not in key_path.parents or not key_path.is_file():
                raise ValueError(f"actors[{index}] public key escapes the trust-store directory")
            public_key = read_regular(key_path, 65536, f"public key {key_id}")
            key_digests[key_id] = "sha256:" + hashlib.sha256(public_key).hexdigest()
            actor_ids.add(actor_id)
            key_ids.add(key_id)
            if entry.get("revoked") is True:
                continue
            actors[actor_id] = TrustedActor(
                actor_id=actor_id,
                key_id=key_id,
                roles=frozenset(roles),
                public_key=public_key,
                not_before=parse_time(entry.get("not_before"), f"actors[{index}].not_before"),
                not_after=parse_time(entry.get("not_after"), f"actors[{index}].not_after"),
            )
        revoked = payload.get("revoked_record_ids", [])
        if not isinstance(revoked, list) or any(not isinstance(item, str) or not item for item in revoked):
            raise ValueError("revoked_record_ids must be a string array")
        return cls(
            path=resolved,
            actors=actors,
            revoked_records=frozenset(revoked),
            digest=canonical_digest({"store": hashlib.sha256(raw).hexdigest(), "keys": key_digests}),
        )

    def verify(self, envelope: Any, required_role: str, bindings: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
        if not isinstance(envelope, dict) or set(envelope) != {"algorithm", "key_id", "payload", "signature"}:
            raise ValueError("signed actor envelope fields are invalid")
        if envelope.get("algorithm") != "ed25519" or not isinstance(envelope.get("payload"), dict):
            raise ValueError("signed actor envelope must use Ed25519 and an object payload")
        payload = envelope["payload"]
        actor_id = payload.get("actor_id")
        actor = self.actors.get(actor_id) if isinstance(actor_id, str) else None
        if actor is None or actor.key_id != envelope.get("key_id"):
            raise ValueError("signed actor is unknown, revoked, or bound to another key")
        if required_role not in actor.roles:
            raise ValueError(f"actor lacks required role: {required_role}")
        observed = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        issued = parse_time(payload.get("issued_at"), "payload.issued_at")
        expires = parse_time(payload.get("expires_at"), "payload.expires_at")
        if not (actor.not_before <= observed < actor.not_after) or not (issued <= observed < expires) or expires <= issued:
            raise ValueError("actor key or signed envelope is outside its validity window")
        record_id = payload.get("record_id")
        if not isinstance(record_id, str) or not record_id or record_id in self.revoked_records:
            raise ValueError("signed record is missing or revoked")
        for field, expected in bindings.items():
            if payload.get(field) != expected:
                raise ValueError(f"signed actor binding mismatch: {field}")
        signature_text = envelope.get("signature")
        if not isinstance(signature_text, str) or not signature_text:
            raise ValueError("signed actor envelope signature is required")
        try:
            normalized = signature_text.replace("-", "+").replace("_", "/")
            signature = base64.b64decode(normalized + "=" * (-len(normalized) % 4), validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("signed actor signature is not valid base64") from exc
        with tempfile.TemporaryDirectory(prefix="rmp-signature-") as temporary:
            base = Path(temporary)
            payload_path = base / "payload.json"
            signature_path = base / "signature.bin"
            public_path = base / "public.pem"
            payload_path.write_bytes(canonical_bytes(payload))
            signature_path.write_bytes(signature)
            public_path.write_bytes(actor.public_key)
            completed = subprocess.run(
                ["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(public_path), "-rawin", "-in", str(payload_path), "-sigfile", str(signature_path)],
                check=False,
                capture_output=True,
                timeout=10,
            )
        if completed.returncode != 0:
            raise ValueError("signed actor signature verification failed")
        return {
            "actor_id": actor.actor_id,
            "key_id": actor.key_id,
            "role": required_role,
            "record_id": record_id,
            "payload_sha256": canonical_digest(payload),
            "trust_store_sha256": self.digest,
        }
