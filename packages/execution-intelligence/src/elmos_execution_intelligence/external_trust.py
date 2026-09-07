"""External trust-authority snapshots for evidence provenance verification.

The evidence verifier must not trust revocation flags that travel with release
evidence.  This module loads a separately governed, digest-pinned authority
root and verifies an Ed25519-signed trust snapshot obtained from either an
exact replay file or a bounded HTTPS request.  Only signed public trust data is
cached; bearer credentials are accepted in memory and are never written.
"""
from __future__ import annotations

import base64
import binascii
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO, Final

AUTHORITY_ROOT_ARTIFACT: Final = "evidence-trust-authority-root"
SNAPSHOT_ARTIFACT: Final = "external-evidence-trust-snapshot"
SNAPSHOT_SIGNATURE_DOMAIN: Final = "elmos.execution-intelligence.external-trust-snapshot.v1"
MAX_EXTERNAL_TRUST_BYTES: Final = 2 * 1024 * 1024
MAX_CLOCK_SKEW: Final = timedelta(minutes=5)
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
STRONG_ETAG_PATTERN: Final = re.compile(r'^"[A-Za-z0-9._:/+\-]{1,128}"$')


class ExternalTrustError(ValueError):
    """External trust state is unavailable, malformed, stale or untrusted."""


@dataclass(frozen=True)
class ExternalTrustOptions:
    """Operator-owned inputs for one external trust-authority lookup."""

    authority_root_path: str | Path
    authority_root_sha256: str
    snapshot_path: str | Path | None = None
    source_url: str | None = None
    cache_path: str | Path | None = None
    expected_snapshot_sha256: str | None = None
    expected_etag: str | None = None
    epoch_state_path: str | Path | None = None
    timeout_seconds: float = 5.0
    bearer_token: str | None = None


@dataclass(frozen=True)
class VerifiedExternalTrust:
    """Verified public trust material consumed by provenance verification."""

    trust_store: dict[str, Any]
    trust_store_sha256: str
    revocations: dict[str, dict[str, Any]]
    receipt: dict[str, Any]


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        """Never forward an in-memory bearer credential to another origin."""
        return None


def _reject_json_constant(value: str) -> None:
    raise ExternalTrustError(f"non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExternalTrustError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _strict_json(content: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except UnicodeDecodeError as exc:
        raise ExternalTrustError(f"invalid UTF-8 in {label}") from exc
    except json.JSONDecodeError as exc:
        raise ExternalTrustError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ExternalTrustError(f"expected a JSON object in {label}")
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ExternalTrustError(f"external trust value cannot be canonicalized: {exc}") from exc
    return encoded.encode("utf-8")


def external_trust_signature_payload(payload: Mapping[str, Any]) -> bytes:
    """Return the canonical bytes signed by the external trust authority."""
    return _canonical_json_bytes({"domain": SNAPSHOT_SIGNATURE_DOMAIN, "payload": payload})


def _require_exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ExternalTrustError(f"{label} fields mismatch; missing={missing}, extra={extra}")


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_PATTERN.fullmatch(value):
        raise ExternalTrustError(f"{label} is not a valid identifier")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ExternalTrustError(f"{label} must be an RFC3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ExternalTrustError(f"{label} is not a valid timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ExternalTrustError(f"{label} must use UTC")
    return parsed.astimezone(timezone.utc)


def _decode_base64(value: Any, expected_size: int, label: str) -> bytes:
    if not isinstance(value, str):
        raise ExternalTrustError(f"{label} must be base64 text")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ExternalTrustError(f"{label} is not valid base64") from exc
    if len(decoded) != expected_size:
        raise ExternalTrustError(f"{label} must decode to exactly {expected_size} bytes")
    return decoded


def _read_regular_file_once(path: str | Path) -> bytes:
    source = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise ExternalTrustError(f"cannot securely open external trust input {source}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ExternalTrustError(f"external trust input is not a regular file: {source}")
        if before.st_size < 0 or before.st_size > MAX_EXTERNAL_TRUST_BYTES:
            raise ExternalTrustError(
                f"external trust input exceeds the {MAX_EXTERNAL_TRUST_BYTES}-byte limit: {source}"
            )
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if before_identity != after_identity or len(content) != before.st_size:
            raise ExternalTrustError(f"external trust input changed while captured: {source}")
        return content
    except OSError as exc:
        raise ExternalTrustError(f"cannot read external trust input {source}: {exc}") from exc
    finally:
        os.close(descriptor)


def _read_bounded_stream(stream: BinaryIO) -> bytes:
    content = stream.read(MAX_EXTERNAL_TRUST_BYTES + 1)
    if len(content) > MAX_EXTERNAL_TRUST_BYTES:
        raise ExternalTrustError(
            f"external trust response exceeds the {MAX_EXTERNAL_TRUST_BYTES}-byte limit"
        )
    return content


def _resolve_external_path(path: str | Path, forbidden_root: Path | None, label: str) -> Path:
    resolved = Path(path).expanduser().resolve(strict=False)
    if forbidden_root is not None:
        try:
            resolved.relative_to(forbidden_root)
        except ValueError:
            pass
        else:
            raise ExternalTrustError(f"{label} must be outside the evidence directory")
    return resolved


def _atomic_write_public_state(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        current = None
    if current is not None and not stat.S_ISREG(current.st_mode):
        raise ExternalTrustError(f"external trust state target is not a regular file: {path}")
    temporary = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(temporary, flags, 0o600)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _authority_root(
    options: ExternalTrustOptions,
    checked_at: datetime,
    forbidden_root: Path | None,
) -> tuple[dict[str, Any], str]:
    if not SHA256_PATTERN.fullmatch(options.authority_root_sha256):
        raise ExternalTrustError("an exact lowercase SHA-256 authority-root pin is required")
    root_path = _resolve_external_path(options.authority_root_path, forbidden_root, "authority root")
    root_bytes = _read_regular_file_once(root_path)
    root_digest = hashlib.sha256(root_bytes).hexdigest()
    if root_digest != options.authority_root_sha256:
        raise ExternalTrustError("authority-root digest does not match the operator-provided pin")
    root = _strict_json(root_bytes, "evidence trust authority root")
    expected = {
        "schema_version",
        "artifact",
        "issuer_id",
        "key_id",
        "algorithm",
        "public_key_base64",
        "not_before",
        "expires_at",
        "authority_url",
        "minimum_epoch",
        "max_snapshot_lifetime_seconds",
        "max_revocation_age_seconds",
        "separate_from_evidence_authorities",
    }
    _require_exact_fields(root, expected, "authority root")
    if root.get("schema_version") != "1.0.0" or root.get("artifact") != AUTHORITY_ROOT_ARTIFACT:
        raise ExternalTrustError("unsupported evidence trust authority-root contract")
    _identifier(root.get("issuer_id"), "authority root issuer_id")
    _identifier(root.get("key_id"), "authority root key_id")
    if root.get("algorithm") != "Ed25519":
        raise ExternalTrustError("authority root must use Ed25519")
    _decode_base64(root.get("public_key_base64"), 32, "authority root public_key_base64")
    not_before = _timestamp(root.get("not_before"), "authority root not_before")
    expires_at = _timestamp(root.get("expires_at"), "authority root expires_at")
    if expires_at <= not_before or checked_at < not_before or checked_at >= expires_at:
        raise ExternalTrustError("authority root is outside its operator-pinned validity window")
    authority_url = root.get("authority_url")
    if authority_url is not None and not isinstance(authority_url, str):
        raise ExternalTrustError("authority root authority_url must be a string or null")
    for field in (
        "minimum_epoch",
        "max_snapshot_lifetime_seconds",
        "max_revocation_age_seconds",
    ):
        value = root.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ExternalTrustError(f"authority root {field} must be a positive integer")
    if int(root["max_snapshot_lifetime_seconds"]) > 3600:
        raise ExternalTrustError("authority root cannot permit snapshots valid for more than one hour")
    if int(root["max_revocation_age_seconds"]) > 3600:
        raise ExternalTrustError("authority root cannot permit revocation status older than one hour")
    if root.get("separate_from_evidence_authorities") is not True:
        raise ExternalTrustError("authority root must require separation from evidence authorities")
    return root, root_digest


def _validate_url(url: str, bearer_token: str | None) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ExternalTrustError("trust authority URL must not contain credentials, query or fragment")
    host = parsed.hostname
    local_http = parsed.scheme == "http" and host in {"127.0.0.1", "::1", "localhost"}
    if parsed.scheme != "https" and not local_http:
        raise ExternalTrustError("trust authority URL must use HTTPS")
    if not host or not parsed.path.startswith("/"):
        raise ExternalTrustError("trust authority URL must have an absolute origin and path")
    if bearer_token is not None and parsed.scheme != "https":
        raise ExternalTrustError("bearer credentials are forbidden over non-HTTPS transport")


def _unverified_cache_etag(cache_path: Path) -> str | None:
    try:
        cached = _strict_json(_read_regular_file_once(cache_path), "external trust cache")
        payload = cached.get("payload")
        if not isinstance(payload, dict):
            return None
        etag = payload.get("etag")
        return etag if isinstance(etag, str) and STRONG_ETAG_PATTERN.fullmatch(etag) else None
    except ExternalTrustError:
        return None


def _fetch_snapshot(
    options: ExternalTrustOptions,
    root: Mapping[str, Any],
    cache_path: Path | None,
) -> tuple[bytes, str | None, str]:
    if options.source_url is None:
        raise ExternalTrustError("trust authority URL is missing")
    if root.get("authority_url") != options.source_url:
        raise ExternalTrustError("trust authority URL does not match the digest-pinned authority root")
    _validate_url(options.source_url, options.bearer_token)
    if not isinstance(options.timeout_seconds, int | float) or isinstance(options.timeout_seconds, bool):
        raise ExternalTrustError("trust authority timeout must be numeric")
    timeout = float(options.timeout_seconds)
    if timeout <= 0 or timeout > 30:
        raise ExternalTrustError("trust authority timeout must be in the range (0, 30] seconds")
    headers = {"Accept": "application/json"}
    cached_etag = _unverified_cache_etag(cache_path) if cache_path is not None and cache_path.exists() else None
    if cached_etag is not None:
        headers["If-None-Match"] = cached_etag
    if options.bearer_token is not None:
        if not options.bearer_token or "\r" in options.bearer_token or "\n" in options.bearer_token:
            raise ExternalTrustError("trust authority bearer credential is malformed")
        headers["Authorization"] = f"Bearer {options.bearer_token}"
    # _validate_url has already constrained this to credential-free HTTPS, with
    # loopback HTTP permitted only for the replayable integration harness.
    request = urllib.request.Request(  # noqa: S310
        options.source_url, headers=headers, method="GET"
    )
    opener = urllib.request.build_opener(_RejectRedirects())
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.getcode() != 200:
                raise ExternalTrustError(f"unexpected trust authority HTTP status: {response.getcode()}")
            content_type = response.headers.get_content_type()
            if content_type not in {"application/json", "application/trust+json"}:
                raise ExternalTrustError("trust authority response has an unsupported content type")
            etag = response.headers.get("ETag")
            if etag is None or not STRONG_ETAG_PATTERN.fullmatch(etag):
                raise ExternalTrustError("trust authority response requires a strong ETag")
            return _read_bounded_stream(response), etag, "online"
    except urllib.error.HTTPError as exc:
        if exc.code == 304 and cache_path is not None and cached_etag is not None:
            response_etag = exc.headers.get("ETag") or cached_etag
            if response_etag != cached_etag:
                raise ExternalTrustError("trust authority 304 response changed the cached ETag") from exc
            return _read_regular_file_once(cache_path), cached_etag, "cache-revalidated"
        if exc.code not in {500, 502, 503, 504}:
            raise ExternalTrustError(f"trust authority rejected the request with HTTP {exc.code}") from exc
        network_error: Exception = exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        network_error = exc
    if cache_path is None:
        raise ExternalTrustError("trust authority unavailable and no signed cache is configured") from network_error
    try:
        return _read_regular_file_once(cache_path), None, "cache-fallback"
    except ExternalTrustError as exc:
        raise ExternalTrustError("trust authority unavailable and its signed cache is unusable") from exc


def _trust_store_key_metadata(trust_store: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    _require_exact_fields(
        trust_store,
        {"schema_version", "artifact", "trust_store_id", "keys"},
        "external snapshot trust store",
    )
    if trust_store.get("schema_version") != "1.0.0" or trust_store.get("artifact") != "evidence-trust-store":
        raise ExternalTrustError("external snapshot contains an unsupported trust-store contract")
    _identifier(trust_store.get("trust_store_id"), "external snapshot trust_store_id")
    raw_keys = trust_store.get("keys")
    if not isinstance(raw_keys, list) or not raw_keys:
        raise ExternalTrustError("external snapshot trust store must contain keys")
    result: dict[str, dict[str, Any]] = {}
    expected = {
        "key_id",
        "principal_id",
        "organization_id",
        "authority_id",
        "role",
        "algorithm",
        "public_key_base64",
        "not_before",
        "expires_at",
        "revoked",
    }
    for index, raw_key in enumerate(raw_keys):
        if not isinstance(raw_key, dict):
            raise ExternalTrustError(f"external snapshot trust key {index} must be an object")
        _require_exact_fields(raw_key, expected, f"external snapshot trust key {index}")
        key_id = _identifier(raw_key.get("key_id"), f"external snapshot trust key {index}.key_id")
        _identifier(raw_key.get("principal_id"), f"external snapshot trust key {index}.principal_id")
        _identifier(raw_key.get("organization_id"), f"external snapshot trust key {index}.organization_id")
        _identifier(raw_key.get("authority_id"), f"external snapshot trust key {index}.authority_id")
        if raw_key.get("role") not in {"executor", "independent_verifier"}:
            raise ExternalTrustError(f"external snapshot trust key {key_id} has an unsupported role")
        if raw_key.get("algorithm") != "Ed25519":
            raise ExternalTrustError(f"external snapshot trust key {key_id} is not Ed25519")
        _decode_base64(
            raw_key.get("public_key_base64"),
            32,
            f"external snapshot trust key {key_id}.public_key_base64",
        )
        _timestamp(raw_key.get("not_before"), f"external snapshot trust key {key_id}.not_before")
        _timestamp(raw_key.get("expires_at"), f"external snapshot trust key {key_id}.expires_at")
        if not isinstance(raw_key.get("revoked"), bool):
            raise ExternalTrustError(f"external snapshot trust key {key_id}.revoked must be boolean")
        if key_id in result:
            raise ExternalTrustError(f"duplicate external snapshot trust key: {key_id}")
        result[key_id] = raw_key
    return result


def _verify_snapshot_bytes(
    content: bytes,
    root: Mapping[str, Any],
    root_digest: str,
    options: ExternalTrustOptions,
    checked_at: datetime,
    observed_etag: str | None,
    source: str,
) -> VerifiedExternalTrust:
    snapshot_digest = hashlib.sha256(content).hexdigest()
    if options.expected_snapshot_sha256 is not None:
        if not SHA256_PATTERN.fullmatch(options.expected_snapshot_sha256):
            raise ExternalTrustError("expected snapshot SHA-256 must be exact lowercase hexadecimal")
        if snapshot_digest != options.expected_snapshot_sha256:
            raise ExternalTrustError("external trust snapshot digest does not match the operator pin")
    envelope = _strict_json(content, "external trust snapshot")
    _require_exact_fields(envelope, {"payload", "signature"}, "external trust snapshot")
    payload = envelope.get("payload")
    signature_record = envelope.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature_record, dict):
        raise ExternalTrustError("external trust snapshot payload and signature must be objects")
    expected_payload_fields = {
        "schema_version",
        "artifact",
        "issuer_id",
        "issuer_key_id",
        "snapshot_id",
        "epoch",
        "issued_at",
        "expires_at",
        "etag",
        "trust_store_sha256",
        "trust_store",
        "revocations",
    }
    _require_exact_fields(payload, expected_payload_fields, "external trust snapshot payload")
    _require_exact_fields(signature_record, {"algorithm", "signature_base64"}, "external trust signature")
    if payload.get("schema_version") != "1.0.0" or payload.get("artifact") != SNAPSHOT_ARTIFACT:
        raise ExternalTrustError("unsupported external trust snapshot contract")
    issuer_id = _identifier(payload.get("issuer_id"), "external trust snapshot issuer_id")
    issuer_key_id = _identifier(payload.get("issuer_key_id"), "external trust snapshot issuer_key_id")
    _identifier(payload.get("snapshot_id"), "external trust snapshot snapshot_id")
    if issuer_id != root.get("issuer_id") or issuer_key_id != root.get("key_id"):
        raise ExternalTrustError("external trust snapshot issuer or key does not match the pinned root")
    epoch = payload.get("epoch")
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < int(root["minimum_epoch"]):
        raise ExternalTrustError("external trust snapshot epoch is below the pinned minimum")
    issued_at = _timestamp(payload.get("issued_at"), "external trust snapshot issued_at")
    expires_at = _timestamp(payload.get("expires_at"), "external trust snapshot expires_at")
    if expires_at <= issued_at:
        raise ExternalTrustError("external trust snapshot has an empty validity window")
    if expires_at - issued_at > timedelta(seconds=int(root["max_snapshot_lifetime_seconds"])):
        raise ExternalTrustError("external trust snapshot exceeds the pinned maximum lifetime")
    if checked_at + MAX_CLOCK_SKEW < issued_at:
        raise ExternalTrustError("external trust snapshot is issued in the future")
    if checked_at >= expires_at:
        raise ExternalTrustError("external trust snapshot is expired")
    etag = payload.get("etag")
    if not isinstance(etag, str) or not STRONG_ETAG_PATTERN.fullmatch(etag):
        raise ExternalTrustError("external trust snapshot must bind a strong ETag")
    if observed_etag is not None and observed_etag != etag:
        raise ExternalTrustError("transport ETag does not match the signed snapshot ETag")
    if options.expected_etag is not None and options.expected_etag != etag:
        raise ExternalTrustError("signed snapshot ETag does not match the operator pin")
    raw_trust_store = payload.get("trust_store")
    if not isinstance(raw_trust_store, dict):
        raise ExternalTrustError("external trust snapshot trust_store must be an object")
    trust_store = dict(raw_trust_store)
    trust_keys = _trust_store_key_metadata(trust_store)
    trust_store_bytes = _canonical_json_bytes(trust_store)
    trust_store_digest = hashlib.sha256(trust_store_bytes).hexdigest()
    if payload.get("trust_store_sha256") != trust_store_digest:
        raise ExternalTrustError("external trust snapshot does not bind its canonical trust-store digest")
    if issuer_id in {str(key["authority_id"]) for key in trust_keys.values()}:
        raise ExternalTrustError("external trust issuer must be separate from every evidence authority")
    if issuer_key_id in trust_keys:
        raise ExternalTrustError("external trust signing key must not be an evidence signing key")
    raw_revocations = payload.get("revocations")
    if not isinstance(raw_revocations, list):
        raise ExternalTrustError("external trust snapshot revocations must be an array")
    revocations: dict[str, dict[str, Any]] = {}
    revocation_ids: list[str] = []
    expected_revocation_fields = {"key_id", "status", "checked_at", "next_update"}
    max_revocation_age = timedelta(seconds=int(root["max_revocation_age_seconds"]))
    for index, raw_status in enumerate(raw_revocations):
        if not isinstance(raw_status, dict):
            raise ExternalTrustError(f"external revocation status {index} must be an object")
        _require_exact_fields(raw_status, expected_revocation_fields, f"external revocation status {index}")
        key_id = _identifier(raw_status.get("key_id"), f"external revocation status {index}.key_id")
        status_value = raw_status.get("status")
        if status_value not in {"GOOD", "REVOKED", "UNKNOWN"}:
            raise ExternalTrustError(f"external revocation status for {key_id} is unsupported")
        if status_value == "UNKNOWN":
            raise ExternalTrustError(
                f"external revocation authority returned UNKNOWN for key: {key_id}"
            )
        status_checked_at = _timestamp(
            raw_status.get("checked_at"), f"external revocation status {key_id}.checked_at"
        )
        next_update = _timestamp(
            raw_status.get("next_update"), f"external revocation status {key_id}.next_update"
        )
        if status_checked_at > checked_at + MAX_CLOCK_SKEW:
            raise ExternalTrustError(f"external revocation status for {key_id} is from the future")
        if checked_at - status_checked_at > max_revocation_age:
            raise ExternalTrustError(f"external revocation status for {key_id} is stale")
        if next_update <= checked_at or next_update <= status_checked_at:
            raise ExternalTrustError(f"external revocation status for {key_id} has expired")
        if key_id in revocations:
            raise ExternalTrustError(f"duplicate external revocation status for key: {key_id}")
        revocation_ids.append(key_id)
        revocations[key_id] = dict(raw_status)
    if revocation_ids != sorted(revocation_ids):
        raise ExternalTrustError("external revocation statuses must be sorted by key_id")
    if set(revocations) != set(trust_keys):
        raise ExternalTrustError("external revocation statuses must exactly cover every trust-store key")
    if signature_record.get("algorithm") != "Ed25519":
        raise ExternalTrustError("external trust snapshot signature must use Ed25519")
    public_key = _decode_base64(root.get("public_key_base64"), 32, "authority root public_key_base64")
    signature = _decode_base64(
        signature_record.get("signature_base64"), 64, "external trust snapshot signature"
    )
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise ExternalTrustError("Ed25519 external trust verification is unavailable") from exc
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature,
            external_trust_signature_payload(payload),
        )
    except (InvalidSignature, ValueError) as exc:
        raise ExternalTrustError("external trust snapshot signature verification failed") from exc
    receipt = {
        "issuer_id": issuer_id,
        "issuer_key_id": issuer_key_id,
        "snapshot_id": payload["snapshot_id"],
        "epoch": epoch,
        "issued_at": payload["issued_at"],
        "expires_at": payload["expires_at"],
        "etag": etag,
        "snapshot_sha256": snapshot_digest,
        "authority_root_sha256": root_digest,
        "trust_store_sha256": trust_store_digest,
        "source": source,
        "revocation_status_count": len(revocations),
    }
    return VerifiedExternalTrust(
        trust_store=trust_store,
        trust_store_sha256=trust_store_digest,
        revocations=revocations,
        receipt=receipt,
    )


def _record_epoch(
    state_path: Path,
    verified: VerifiedExternalTrust,
) -> None:
    lock_path = state_path.with_name(state_path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    parent_stat = os.stat(lock_path.parent, follow_symlinks=False)
    if not stat.S_ISDIR(parent_stat.st_mode) or parent_stat.st_mode & 0o022:
        raise ExternalTrustError(
            "external trust epoch state directory must not be group/world writable"
        )
    lock_flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(lock_path, lock_flags, 0o600)
    try:
        lock_stat = os.fstat(descriptor)
        if not stat.S_ISREG(lock_stat.st_mode):
            raise ExternalTrustError("external trust epoch lock is not a regular file")
        if lock_stat.st_mode & 0o022:
            raise ExternalTrustError("external trust epoch lock must not be group/world writable")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        receipt = verified.receipt
        if state_path.exists():
            state_stat = os.lstat(state_path)
            if not stat.S_ISREG(state_stat.st_mode) or state_stat.st_mode & 0o022:
                raise ExternalTrustError(
                    "external trust epoch state must be a protected regular file"
                )
            state = _strict_json(_read_regular_file_once(state_path), "external trust epoch state")
            _require_exact_fields(
                state,
                {"schema_version", "issuer_id", "issuer_key_id", "epoch", "snapshot_sha256", "etag"},
                "external trust epoch state",
            )
            if state.get("schema_version") != "1.0.0":
                raise ExternalTrustError("unsupported external trust epoch-state contract")
            if state.get("issuer_id") != receipt["issuer_id"] or state.get("issuer_key_id") != receipt["issuer_key_id"]:
                raise ExternalTrustError("external trust epoch state belongs to a different authority")
            stored_epoch = state.get("epoch")
            if not isinstance(stored_epoch, int) or isinstance(stored_epoch, bool):
                raise ExternalTrustError("external trust epoch state has an invalid epoch")
            current_epoch = int(receipt["epoch"])
            if current_epoch < stored_epoch:
                raise ExternalTrustError("external trust snapshot epoch rollback was rejected")
            if current_epoch == stored_epoch and (
                state.get("snapshot_sha256") != receipt["snapshot_sha256"]
                or state.get("etag") != receipt["etag"]
            ):
                raise ExternalTrustError("external trust epoch was reused with different immutable bytes")
        state_value = {
            "schema_version": "1.0.0",
            "issuer_id": receipt["issuer_id"],
            "issuer_key_id": receipt["issuer_key_id"],
            "epoch": receipt["epoch"],
            "snapshot_sha256": receipt["snapshot_sha256"],
            "etag": receipt["etag"],
        }
        _atomic_write_public_state(state_path, _canonical_json_bytes(state_value) + b"\n")
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _load_external_trust(
    options: ExternalTrustOptions,
    *,
    now: datetime | None = None,
    forbidden_root: str | Path | None = None,
) -> VerifiedExternalTrust:
    """Load and verify one signed trust/revocation snapshot.

    Exactly one source is required. Replay files require a snapshot SHA-256 pin.
    Online responses require a strong ETag matching the signed payload; 304 and
    bounded outage fallback may use only a still-fresh signed cache.
    """
    supplied_now = now or datetime.now(timezone.utc)
    if supplied_now.tzinfo is None or supplied_now.utcoffset() is None:
        raise ExternalTrustError("external trust verification time must be timezone-aware")
    checked_at = supplied_now.astimezone(timezone.utc)
    forbidden = Path(forbidden_root).resolve() if forbidden_root is not None else None
    root, root_digest = _authority_root(options, checked_at, forbidden)
    root_path = _resolve_external_path(options.authority_root_path, forbidden, "authority root")
    source_count = int(options.snapshot_path is not None) + int(options.source_url is not None)
    if source_count != 1:
        raise ExternalTrustError("exactly one external trust snapshot file or authority URL is required")
    cache_path = (
        _resolve_external_path(options.cache_path, forbidden, "external trust cache")
        if options.cache_path is not None
        else None
    )
    state_path = (
        _resolve_external_path(options.epoch_state_path, forbidden, "external trust epoch state")
        if options.epoch_state_path is not None
        else None
    )
    if state_path is None:
        raise ExternalTrustError(
            "external trust requires a persistent epoch state to reject rollback"
        )
    snapshot_path = (
        _resolve_external_path(options.snapshot_path, forbidden, "external trust snapshot")
        if options.snapshot_path is not None
        else None
    )
    configured_paths = [
        ("authority root", root_path),
        ("epoch state", state_path),
    ]
    if snapshot_path is not None:
        configured_paths.append(("snapshot", snapshot_path))
    if cache_path is not None:
        configured_paths.append(("cache", cache_path))
    if len({path for _, path in configured_paths}) != len(configured_paths):
        raise ExternalTrustError("authority root, snapshot, cache and epoch state paths must be distinct")
    if options.snapshot_path is not None:
        if options.expected_snapshot_sha256 is None:
            raise ExternalTrustError("replay trust snapshots require an exact SHA-256 pin")
        if snapshot_path is None:  # pragma: no cover - narrowed by the branch above
            raise ExternalTrustError("external trust snapshot path is missing")
        content = _read_regular_file_once(snapshot_path)
        observed_etag = None
        source = "replay-file"
    else:
        content, observed_etag, source = _fetch_snapshot(options, root, cache_path)
    verified = _verify_snapshot_bytes(
        content,
        root,
        root_digest,
        options,
        checked_at,
        observed_etag,
        source,
    )
    if state_path is not None:
        _record_epoch(state_path, verified)
    if cache_path is not None and source == "online":
        _atomic_write_public_state(cache_path, content)
    return verified


def load_external_trust(
    options: ExternalTrustOptions,
    *,
    now: datetime | None = None,
    forbidden_root: str | Path | None = None,
) -> VerifiedExternalTrust:
    """Fail closed on both trust-contract and local state I/O failures."""
    try:
        return _load_external_trust(options, now=now, forbidden_root=forbidden_root)
    except ExternalTrustError:
        raise
    except OSError as exc:
        raise ExternalTrustError("external trust authority state I/O failed closed") from exc
