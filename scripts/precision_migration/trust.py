#!/usr/bin/env python3
"""Content-addressed evidence and Ed25519 trust verification.

The Precision Migration runtime treats every URI, digest, approval, and proof as
untrusted input.  This module resolves local content below explicitly approved
roots and verifies signed envelopes with an immutable trust store.  It never
interprets a caller supplied boolean as authorization or proof.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
DIGEST_PATTERN = re.compile(r"^sha256:([0-9a-f]{64})$")
TRUSTED_OPENSSL_PATHS = (
    Path("/usr/bin/openssl"),
    Path("/opt/homebrew/opt/openssl@3/bin/openssl"),
    Path("/usr/local/opt/openssl@3/bin/openssl"),
)


def _trusted_system_executable(
    path: Path, *, label: str, allow_current_owner: bool = False
) -> Path:
    """Resolve one fixed system executable without consulting caller PATH state."""

    if not path.is_absolute() or path == Path("/"):
        raise OSError(f"{label} path must be an absolute non-root path")
    try:
        resolved = path.resolve(strict=True)
        details = resolved.stat()
    except OSError as exc:
        raise OSError(f"{label} is unavailable at {path}") from exc
    allowed_owners = {0}
    if allow_current_owner and os.geteuid() != 0:
        allowed_owners.add(os.geteuid())
    if not stat.S_ISREG(details.st_mode) or details.st_uid not in allowed_owners:
        raise OSError(f"{label} must resolve to an approved-owner regular file")
    if stat.S_IMODE(details.st_mode) & 0o022:
        raise OSError(f"{label} must not be group/other-writable")
    for parent in resolved.parents:
        parent_details = parent.stat()
        if (
            not stat.S_ISDIR(parent_details.st_mode)
            or parent_details.st_uid not in allowed_owners
            or (
                stat.S_IMODE(parent_details.st_mode) & 0o022
                and not (
                    allow_current_owner
                    and os.geteuid() != 0
                    and parent_details.st_uid == os.geteuid()
                )
            )
        ):
            raise OSError(f"{label} must not traverse an unapproved path")
    return resolved


@lru_cache(maxsize=1)
def trusted_openssl_path() -> Path:
    """Select an allowlisted OpenSSL that actually supports Ed25519.

    Linux production hosts are expected to use the root-owned ``/usr/bin``
    binary.  Apple ships an older LibreSSL there, so bounded developer checks
    may use the current account's allowlisted Homebrew OpenSSL installation.
    Production launch validation separately rejects a non-root-owned crypto
    toolchain.
    """

    probe = (
        b"-----BEGIN PUBLIC KEY-----\n"
        b"MCowBQYDK2VwAyEA11qYAYKxCrfVS/JC/eEXyzE32cDGOtaIWzPDcqdEKQA=\n"
        b"-----END PUBLIC KEY-----\n"
    )
    failures: list[str] = []
    for candidate in TRUSTED_OPENSSL_PATHS:
        try:
            executable = _trusted_system_executable(
                candidate,
                label="OpenSSL verifier",
                allow_current_owner=True,
            )
            completed = subprocess.run(
                [str(executable), "pkey", "-pubin", "-outform", "DER"],
                input=probe,
                check=False,
                capture_output=True,
                timeout=10,
                env={
                    "HOME": "/nonexistent",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PATH": "/usr/bin:/bin",
                },
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"{candidate}: {exc}")
            continue
        if completed.returncode == 0 and completed.stdout.startswith(b"0*"):
            return executable
        failures.append(f"{candidate}: Ed25519 unsupported")
    raise OSError("no allowlisted Ed25519-capable OpenSSL verifier is available")


def production_openssl_is_root_owned() -> bool:
    """Return whether the selected crypto verifier is immutable to this account."""

    executable = trusted_openssl_path()
    if executable.stat().st_uid != 0:
        return False
    return all(parent.stat().st_uid == 0 for parent in executable.parents)


def run_trusted_openssl(
    arguments: Iterable[str],
    *,
    input_bytes: bytes | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run the fixed OS OpenSSL binary with no inherited path or Python hooks."""

    executable = trusted_openssl_path()
    effective_timeout = (
        int(os.environ.get("ELMOS_OPENSSL_TIMEOUT_SECONDS", "30"))
        if timeout is None
        else timeout
    )
    return subprocess.run(
        [str(executable), *arguments],
        input=input_bytes,
        check=False,
        capture_output=True,
        timeout=effective_timeout,
        env={
            "HOME": "/nonexistent",
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": "/usr/bin:/bin",
        },
    )


def canonical_bytes(value: Any) -> bytes:
    """Canonical JSON shared with the TypeScript control plane.

    Both implementations must agree byte for byte or a signature produced on one side
    cannot verify on the other. The contract is: object keys sorted by code point, no
    insignificant whitespace, and raw UTF-8 rather than ``\\uXXXX`` escapes.

    ``ensure_ascii=False`` is required for that last part. Left at its default this
    emits ``\\uXXXX`` while ``JSON.stringify`` emits the character itself, so every
    payload carrying a non-ASCII byte silently canonicalizes differently on the two
    sides. All-ASCII payloads are unaffected by this setting.

    Known and accepted limit: ``sort_keys`` compares code points, while the TypeScript
    side compares UTF-16 code units. The two disagree only for keys containing
    supplementary-plane characters (U+10000 and above). Every key in every signed
    payload is a schema-constrained ASCII identifier, so this cannot be reached today;
    widening a key pattern beyond ASCII means fixing both sides in one change.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def decode_signature(signature_text: str) -> bytes:
    """Decode a base64url signature, matching Node's ``Buffer.from(x, "base64url")``.

    Standard base64 is accepted as well so records signed before the two sides were
    unified still verify; base64url is what new signatures use.
    """
    if not isinstance(signature_text, str) or not signature_text:
        raise ValueError("signature must be a non-empty string")
    normalized = signature_text.replace("-", "+").replace("_", "/")
    padded = normalized + "=" * (-len(normalized) % 4)
    return base64.b64decode(padded, validate=True)


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return "sha256:" + value.hexdigest()


@dataclass(frozen=True)
class RegularFileSnapshot:
    content: bytes
    stat_result: os.stat_result


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def read_regular_file_snapshot(
    path: Path, *, max_bytes: int, label: str
) -> RegularFileSnapshot:
    """Read bytes and descriptor identity without following the final symlink."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode):
            raise ValueError(f"{label} must be a regular file")
        if observed.st_size > max_bytes:
            raise ValueError(f"{label} exceeds the byte budget")
        chunks: list[bytes] = []
        remaining = observed.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError(f"{label} changed while being read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError(f"{label} changed while being read")
        completed = os.fstat(descriptor)
        if _file_identity(completed) != _file_identity(observed):
            raise ValueError(f"{label} changed while being read")
        return RegularFileSnapshot(b"".join(chunks), completed)
    finally:
        os.close(descriptor)


def read_regular_file_once(path: Path, *, max_bytes: int, label: str) -> bytes:
    """Read one bounded regular file descriptor without following its final symlink."""

    return read_regular_file_snapshot(
        path, max_bytes=max_bytes, label=label
    ).content


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def configured_roots(values: Iterable[Path] | None = None) -> tuple[Path, ...]:
    candidates = list(values or [])
    if not candidates:
        configured = os.environ.get("ELMOS_PRECISION_EVIDENCE_ROOTS", "")
        candidates.extend(Path(item) for item in configured.split(os.pathsep) if item)
    if not candidates:
        candidates.append(ROOT)
    roots: list[Path] = []
    for candidate in candidates:
        resolved = candidate.expanduser().resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError(f"evidence root is not a directory: {resolved}")
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _within(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def resolve_uri(uri: Any, roots: tuple[Path, ...]) -> Path:
    if not isinstance(uri, str) or not uri:
        raise ValueError("artifact URI is required")
    parsed = urlparse(uri)
    if parsed.scheme == "workspace":
        if parsed.netloc not in {"", "repo"}:
            raise ValueError("workspace URI authority is not supported")
        relative = unquote(parsed.path).lstrip("/")
        candidate = (ROOT / relative).resolve(strict=True)
    elif parsed.scheme == "file":
        if parsed.netloc not in {"", "localhost"}:
            raise ValueError("remote file URI is not supported")
        candidate = Path(unquote(parsed.path)).resolve(strict=True)
    elif parsed.scheme == "cas":
        match = re.fullmatch(
            r"sha256/([0-9a-f]{64})", f"{parsed.netloc}{parsed.path}".lstrip("/")
        )
        if match is None:
            raise ValueError("CAS URI must be cas://sha256/<64 lowercase hex>")
        digest = match.group(1)
        candidates = [root / "sha256" / digest[:2] / digest for root in roots]
        existing = [item.resolve(strict=True) for item in candidates if item.is_file()]
        if len(existing) != 1:
            raise ValueError("CAS object must resolve exactly once in approved roots")
        candidate = existing[0]
    else:
        raise ValueError(
            f"unsupported artifact URI scheme: {parsed.scheme or 'relative'}"
        )
    if not _within(candidate, roots):
        raise ValueError("artifact URI escapes approved evidence roots")
    if not candidate.is_file():
        raise ValueError("artifact URI does not resolve to a regular file")
    return candidate


def verify_content_reference(reference: Any, roots: tuple[Path, ...]) -> dict[str, Any]:
    if not isinstance(reference, dict):
        raise ValueError("content reference must be an object")
    expected_digest = reference.get("digest")
    digest_match = DIGEST_PATTERN.fullmatch(str(expected_digest))
    if digest_match is None:
        raise ValueError("content reference digest must be sha256:<64 lowercase hex>")
    expected_size = reference.get("size_bytes")
    if (
        not isinstance(expected_size, int)
        or isinstance(expected_size, bool)
        or expected_size < 0
    ):
        raise ValueError("content reference size_bytes must be a non-negative integer")
    path = resolve_uri(reference.get("uri") or reference.get("artifact_uri"), roots)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        observed_stat = os.fstat(descriptor)
        if not stat.S_ISREG(observed_stat.st_mode):
            raise ValueError(
                "artifact URI does not resolve to a regular file descriptor"
            )
        actual_size = observed_stat.st_size
        value = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            value.update(chunk)
        actual_digest = "sha256:" + value.hexdigest()
    finally:
        os.close(descriptor)
    if actual_size != expected_size:
        raise ValueError(
            f"content byte count mismatch: expected {expected_size}, observed {actual_size}"
        )
    if actual_digest != expected_digest:
        raise ValueError(
            f"content digest mismatch: expected {expected_digest}, observed {actual_digest}"
        )
    return {
        "uri": reference.get("uri") or reference.get("artifact_uri"),
        "digest": actual_digest,
        "size_bytes": actual_size,
        "media_type": reference.get("media_type", "application/octet-stream"),
        "resolved_path": str(path),
    }


@dataclass(frozen=True)
class TrustedKey:
    key_id: str
    roles: frozenset[str]
    public_key_path: Path
    public_key_bytes: bytes
    public_key_digest: str
    not_before: datetime
    not_after: datetime


@dataclass(frozen=True)
class TrustStore:
    path: Path
    keys: dict[str, TrustedKey]
    revoked_record_ids: frozenset[str]
    digest: str

    @classmethod
    def load(cls, path: Path) -> "TrustStore":
        store, _document = cls.load_with_document(path)
        return store

    @classmethod
    def load_with_document(cls, path: Path) -> tuple["TrustStore", dict[str, Any]]:
        """Load trust decisions and identity metadata from one byte snapshot.

        Callers that need actor/organization metadata must not read the trust
        store separately and then call :meth:`load`, because a path swap could
        combine metadata from one document with keys from another.  This method
        parses the exact bytes used to construct the TrustStore and snapshots
        every public key before returning either view.
        """
        supplied_store = path.expanduser()
        resolved_store = supplied_store.resolve(strict=True)
        path_stat = os.stat(supplied_store, follow_symlinks=False)
        if stat.S_ISLNK(path_stat.st_mode):
            raise OSError("trust store must not be a symlink")
        if not stat.S_ISREG(path_stat.st_mode):
            raise ValueError("trust store must be a regular file")
        # Keep the compatibility seam around the bounded one-shot reader.  It
        # performs the descriptor-level identity check; the path stat captured
        # before and after the call below closes the rename/swap window between
        # descriptor close and parsing.
        store_bytes = read_regular_file_once(
            supplied_store, max_bytes=1024 * 1024, label="trust store"
        )
        store_stat = os.stat(supplied_store, follow_symlinks=False)
        return cls._from_bytes_with_document(
            resolved_store,
            store_bytes,
            supplied_store=supplied_store,
            store_path_stat=path_stat,
            store_stat=store_stat,
        )

    @classmethod
    def from_bytes(cls, path: Path, store_bytes: bytes) -> "TrustStore":
        """Load a trust store from one immutable snapshot of its JSON bytes.

        ``path`` remains the origin used to resolve public-key paths.  Callers that
        already performed a bounded, no-follow read can pass those exact bytes here
        so metadata inspection and trust construction cannot observe different JSON
        revisions.  ``load`` remains the path-based, backward-compatible entrypoint.
        """
        store, _document = cls._from_bytes_with_document(path, store_bytes)
        return store

    @classmethod
    def _from_bytes_with_document(
        cls,
        path: Path,
        store_bytes: bytes,
        *,
        supplied_store: Path | None = None,
        store_path_stat: os.stat_result | None = None,
        store_stat: os.stat_result | None = None,
    ) -> tuple["TrustStore", dict[str, Any]]:
        """Build both trust views from one byte snapshot.

        ``load_with_document`` supplies the original path identity so a path
        replacement during its read is rejected.  ``from_bytes`` intentionally
        omits that identity: its contract is to trust the caller's immutable
        byte snapshot even when the origin file has since changed.
        """
        if not isinstance(store_bytes, bytes):
            raise TypeError("trust store content must be bytes")
        store_identity_parts = (
            supplied_store is not None,
            store_path_stat is not None,
            store_stat is not None,
        )
        if any(store_identity_parts) and not all(store_identity_parts):
            raise ValueError("trust store path identity is incomplete")
        if (
            store_path_stat is not None
            and store_stat is not None
            and _file_identity(store_path_stat) != _file_identity(store_stat)
        ):
            raise ValueError("trust store changed while its snapshot was loaded")
        resolved_store = path.expanduser().resolve(strict=True)

        def reject_constant(value: str) -> None:
            raise ValueError(f"trust store contains a non-finite JSON number: {value}")

        payload = json.loads(
            store_bytes.decode("utf-8"), parse_constant=reject_constant
        )
        if not isinstance(payload, dict):
            raise ValueError("trust store must be a JSON object")
        if payload.get("schema_version") != 1:
            raise ValueError("trust store schema_version must be 1")
        records = payload.get("keys")
        if not isinstance(records, list):
            raise ValueError("trust store keys must be an array")
        keys: dict[str, TrustedKey] = {}
        seen_key_ids: set[str] = set()
        key_material_digests: dict[str, str] = {}
        key_path_stats: list[
            tuple[Path, Path, os.stat_result, os.stat_result]
        ] = []
        base = resolved_store.parent
        for index, item in enumerate(records):
            if not isinstance(item, dict):
                raise ValueError(f"trust store key {index} must be an object")
            key_id = item.get("key_id")
            roles = item.get("roles")
            relative_key = item.get("public_key_path")
            if not isinstance(key_id, str) or not key_id or key_id in seen_key_ids:
                raise ValueError(f"trust store key {index} has an invalid identity")
            seen_key_ids.add(key_id)
            if (
                not isinstance(roles, list)
                or not roles
                or any(not isinstance(role, str) or not role for role in roles)
            ):
                raise ValueError(f"trust store key {key_id} has invalid roles")
            if not isinstance(relative_key, str) or not relative_key:
                raise ValueError(f"trust store key {key_id} lacks public_key_path")
            supplied_key_path = base / relative_key
            key_path = supplied_key_path.resolve(strict=True)
            if not _within(key_path, (base,)) or not key_path.is_file():
                raise ValueError(
                    f"trust store key {key_id} escapes the trust-store directory"
                )
            key_stat = os.stat(supplied_key_path, follow_symlinks=False)
            if stat.S_ISLNK(key_stat.st_mode):
                raise OSError(f"trust store key {key_id} must not be a symlink")
            if not stat.S_ISREG(key_stat.st_mode):
                raise ValueError(f"trust store key {key_id} must be a regular file")
            # Use the bounded one-shot reader so callers can observe and
            # reject a path replacement during loading.  The pre/post path
            # identity check complements its descriptor-level check.
            key_bytes = read_regular_file_once(
                supplied_key_path,
                max_bytes=64 * 1024,
                label=f"trust store key {key_id}",
            )
            key_after_read = os.stat(supplied_key_path, follow_symlinks=False)
            if _file_identity(key_stat) != _file_identity(key_after_read):
                raise ValueError(
                    "trust store public key changed while its snapshot was loaded"
                )
            key_path_stats.append(
                (
                    supplied_key_path,
                    key_path,
                    key_stat,
                    key_after_read,
                )
            )
            key_digest = "sha256:" + hashlib.sha256(key_bytes).hexdigest()
            key_material_digests[key_id] = key_digest
            if item.get("revoked") is True:
                continue
            keys[key_id] = TrustedKey(
                key_id=key_id,
                roles=frozenset(roles),
                public_key_path=key_path,
                public_key_bytes=key_bytes,
                public_key_digest=key_digest,
                not_before=parse_instant(
                    item.get("not_before"), f"keys[{index}].not_before"
                ),
                not_after=parse_instant(
                    item.get("not_after"), f"keys[{index}].not_after"
                ),
            )
        revoked = payload.get("revoked_record_ids", [])
        if not isinstance(revoked, list) or any(
            not isinstance(item, str) or not item for item in revoked
        ):
            raise ValueError("trust store revoked_record_ids must be a string array")
        if (
            supplied_store is not None
            and store_path_stat is not None
            and store_stat is not None
        ):
            current_store_stat = os.stat(supplied_store, follow_symlinks=False)
            if (
                supplied_store.resolve(strict=True) != resolved_store
                or _file_identity(store_path_stat) != _file_identity(store_stat)
                or _file_identity(current_store_stat) != _file_identity(store_stat)
            ):
                raise ValueError("trust store changed while its snapshot was loaded")
        for (
            supplied_key_path,
            resolved_key_path,
            path_stat,
            descriptor_stat,
        ) in key_path_stats:
            current_key_stat = os.stat(supplied_key_path, follow_symlinks=False)
            if (
                supplied_key_path.resolve(strict=True) != resolved_key_path
                or _file_identity(path_stat) != _file_identity(descriptor_stat)
                or _file_identity(current_key_stat) != _file_identity(descriptor_stat)
            ):
                raise ValueError(
                    "trust store public key changed while its snapshot was loaded"
                )
        store = cls(
            path=resolved_store,
            keys=keys,
            revoked_record_ids=frozenset(revoked),
            digest=canonical_digest(
                {
                    "trust_store": "sha256:" + hashlib.sha256(store_bytes).hexdigest(),
                    "public_keys": dict(sorted(key_material_digests.items())),
                }
            ),
        )
        return store, payload

    def verify_envelope(
        self,
        envelope: Any,
        *,
        required_role: str,
        bindings: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not isinstance(envelope, dict):
            raise ValueError("signed envelope must be an object")
        if envelope.get("algorithm") != "ed25519":
            raise ValueError("signed envelope algorithm must be ed25519")
        key_id = envelope.get("key_id")
        signature_text = envelope.get("signature")
        payload = envelope.get("payload")
        if not isinstance(key_id, str) or key_id not in self.keys:
            raise ValueError("signed envelope key is unknown or revoked")
        if not isinstance(signature_text, str) or not signature_text:
            raise ValueError("signed envelope signature is required")
        if not isinstance(payload, dict):
            raise ValueError("signed envelope payload must be an object")
        key = self.keys[key_id]
        if required_role not in key.roles:
            raise ValueError(f"signing key lacks required role: {required_role}")
        observed_now = (now or utc_now()).astimezone(timezone.utc)
        if observed_now < key.not_before or observed_now >= key.not_after:
            raise ValueError("signing key is outside its validity window")
        issued_at = parse_instant(payload.get("issued_at"), "payload.issued_at")
        expires_at = parse_instant(payload.get("expires_at"), "payload.expires_at")
        if issued_at < key.not_before or issued_at >= key.not_after:
            raise ValueError(
                "signed envelope issued_at is outside the key validity window"
            )
        if expires_at > key.not_after:
            raise ValueError(
                "signed envelope expires_at exceeds the key validity window"
            )
        if (
            expires_at <= issued_at
            or observed_now < issued_at
            or observed_now >= expires_at
        ):
            raise ValueError("signed envelope is outside its validity window")
        record_id = payload.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("signed envelope payload.record_id is required")
        if record_id in self.revoked_record_ids:
            raise ValueError("signed envelope record is revoked")
        for field, expected in bindings.items():
            if payload.get(field) != expected:
                raise ValueError(f"signed envelope binding mismatch: {field}")
        try:
            signature = decode_signature(signature_text)
        except (ValueError, TypeError) as exc:
            raise ValueError("signed envelope signature is not valid base64") from exc
        with tempfile.TemporaryDirectory(prefix="precision-signature-") as temporary:
            base = Path(temporary)
            payload_path = base / "payload.json"
            signature_path = base / "signature.bin"
            public_key_path = base / "public-key.pem"
            payload_path.write_bytes(canonical_bytes(payload))
            signature_path.write_bytes(signature)
            public_key_path.write_bytes(key.public_key_bytes)
            completed = run_trusted_openssl(
                [
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-inkey",
                    str(public_key_path),
                    "-rawin",
                    "-in",
                    str(payload_path),
                    "-sigfile",
                    str(signature_path),
                ],
                timeout=10,
            )
        if completed.returncode != 0:
            raise ValueError("signed envelope signature verification failed")
        return {
            "record_id": record_id,
            "key_id": key_id,
            "role": required_role,
            "payload_digest": canonical_digest(payload),
            "trust_store_digest": self.digest,
        }


def request_binding_digest(request: dict[str, Any]) -> str:
    return canonical_digest(
        {
            "request_id": request.get("request_id"),
            "skill": request.get("skill"),
            "mode": request.get("mode"),
            "inputs": request.get("inputs"),
            "policy": request.get("policy"),
            "claimed_status": request.get("claimed_status"),
        }
    )
