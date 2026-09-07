"""Explicit, digest-bound bridge to the optional repository native signer.

The bridge is an acceleration path for local HMAC and Merkle calculations. It
is never discovered implicitly and never upgrades a result to external or
independently verified evidence.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
import re
import stat
from typing import Any

from .canonical import validate_digest, validate_identifier
from .sbom_attestation_signer import AttestationSignature


class NativeAttestationError(ValueError):
    """Raised when native identity, input, or output validation fails."""


@dataclass(frozen=True)
class NativeLibraryIdentity:
    path: str
    sha256: str
    abi: str = "elmos-native-attestation/v1"


_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_LIBRARY_BYTES = 512 * 1024 * 1024
_MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
_MAX_MERKLE_LEAVES = 100_000
_MAX_NATIVE_RESPONSE_BYTES = 64 * 1024


class NativeAttestationBridge:
    """Load one exact native library and independently check every result."""

    def __init__(
        self,
        library_path: str | Path,
        library_sha256: str,
        *,
        _loader: Callable[[str], Any] | None = None,
    ) -> None:
        path = Path(library_path).expanduser()
        if not path.is_absolute():
            raise NativeAttestationError("native library path must be absolute")
        try:
            expected_digest = validate_digest(
                library_sha256, "nativeAttestation.librarySha256"
            )
        except ValueError as exc:
            raise NativeAttestationError(str(exc)) from exc
        actual_digest = _verified_file_digest(path)
        if not hmac.compare_digest(actual_digest, expected_digest):
            raise NativeAttestationError("native library digest mismatch")

        load = _loader or ctypes.CDLL
        try:
            library = load(str(path))
            _bind_native_abi(library)
        except (AttributeError, OSError, TypeError) as exc:
            raise NativeAttestationError(
                "native library does not provide the required attestation ABI"
            ) from exc
        if not hmac.compare_digest(_verified_file_digest(path), expected_digest):
            raise NativeAttestationError("native library changed while loading")

        self._library = library
        self.identity = NativeLibraryIdentity(
            path=str(path),
            sha256=expected_digest,
        )

    @classmethod
    def from_configuration(
        cls,
        library_path: str | Path | None,
        library_sha256: str | None,
        *,
        _loader: Callable[[str], Any] | None = None,
    ) -> NativeAttestationBridge | None:
        """Return ``None`` only for an explicitly unconfigured native path."""

        if library_path is None and library_sha256 is None:
            return None
        if library_path is None or library_sha256 is None:
            raise NativeAttestationError(
                "native library path and SHA-256 must be supplied together"
            )
        return cls(library_path, library_sha256, _loader=_loader)

    def sign_attestation(self, payload: bytes, secret_key: bytes) -> dict[str, Any]:
        if not isinstance(payload, bytes) or not payload:
            raise NativeAttestationError(
                "native attestation payload must be non-empty bytes"
            )
        if len(payload) > _MAX_PAYLOAD_BYTES:
            raise NativeAttestationError("native attestation payload exceeds the bound")
        if not isinstance(secret_key, bytes) or not 32 <= len(secret_key) <= 4096:
            raise NativeAttestationError(
                "native attestation key must contain between 32 and 4096 bytes"
            )

        transport_key = base64.urlsafe_b64encode(secret_key)
        payload_buffer = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
        pointer = self._library.elmos_attestation_sign(
            payload_buffer,
            len(payload),
            transport_key,
        )
        document = self._take_json(pointer)
        required_fields = {
            "status",
            "payload_digest",
            "signature",
            "signer_id",
            "algorithm",
        }
        if not required_fields.issubset(document) or set(document) - (
            required_fields | {"error"}
        ):
            raise NativeAttestationError("native attestation response fields are invalid")
        expected_digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        expected_signature = hmac.new(
            transport_key, payload, hashlib.sha256
        ).hexdigest()
        if (
            document.get("status") != "OK"
            or document.get("payload_digest") != expected_digest
            or document.get("algorithm") != "HMAC-SHA256"
            or document.get("signer_id") != "elmos-local-engineering-signer/v1"
            or document.get("error") is not None
            or not isinstance(document.get("signature"), str)
            or not hmac.compare_digest(document["signature"], expected_signature)
        ):
            raise NativeAttestationError(
                "native attestation response failed independent validation"
            )
        return document

    def merkle_root(self, digests: Sequence[str]) -> str:
        if isinstance(digests, (str, bytes)) or not isinstance(digests, Sequence):
            raise NativeAttestationError("Merkle digests must be an array")
        if len(digests) > _MAX_MERKLE_LEAVES:
            raise NativeAttestationError("Merkle digest count exceeds the bound")
        normalized: list[str] = []
        for index, value in enumerate(digests):
            if not isinstance(value, str):
                raise NativeAttestationError(
                    f"Merkle digest {index} must be lowercase SHA-256"
                )
            raw = value.removeprefix("sha256:")
            if not _HEX_DIGEST.fullmatch(raw):
                raise NativeAttestationError(
                    f"Merkle digest {index} must be lowercase SHA-256"
                )
            normalized.append(raw)

        pointer = self._library.elmos_merkle_root(
            ",".join(normalized).encode("ascii")
        )
        native_root = self._take_text(pointer)
        expected_root = _python_merkle_root(normalized)
        if not hmac.compare_digest(native_root, expected_root):
            raise NativeAttestationError(
                "native Merkle root failed independent validation"
            )
        return native_root

    def _take_json(self, pointer: int | None) -> dict[str, Any]:
        raw = self._take_text(pointer)
        try:
            document = json.loads(raw)
        except ValueError as exc:
            raise NativeAttestationError(
                "native attestation response is not valid JSON"
            ) from exc
        if not isinstance(document, dict):
            raise NativeAttestationError(
                "native attestation response must be an object"
            )
        return document

    def _take_text(self, pointer: int | None) -> str:
        if not pointer:
            raise NativeAttestationError("native attestation returned a null pointer")
        try:
            raw = ctypes.string_at(pointer)
        finally:
            self._library.elmos_free_string(pointer)
        if len(raw) > _MAX_NATIVE_RESPONSE_BYTES:
            raise NativeAttestationError("native attestation response exceeds the bound")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NativeAttestationError(
                "native attestation response is not UTF-8"
            ) from exc


class NativeHmacLocalAttestationSigner:
    """AttestationSigner adapter that remains local self-attested evidence."""

    def __init__(
        self,
        bridge: NativeAttestationBridge,
        key: bytes,
        *,
        key_id: str,
    ) -> None:
        if not isinstance(bridge, NativeAttestationBridge):
            raise NativeAttestationError("native attestation bridge is required")
        if not isinstance(key, bytes) or not 32 <= len(key) <= 4096:
            raise NativeAttestationError(
                "native attestation key must contain between 32 and 4096 bytes"
            )
        try:
            self._key_id = validate_identifier(key_id, "attestation.keyId")
        except ValueError as exc:
            raise NativeAttestationError(str(exc)) from exc
        self._bridge = bridge
        self._key = bytes(key)

    def sign(self, payload: bytes) -> AttestationSignature:
        result = self._bridge.sign_attestation(payload, self._key)
        return AttestationSignature(
            algorithm="HMAC-SHA256",
            key_id=self._key_id,
            value="hmac-sha256:" + result["signature"],
            classification="LOCAL_EXECUTED_SELF_ATTESTED",
        )

    def verify(self, payload: bytes, signature: AttestationSignature) -> bool:
        if (
            signature.algorithm != "HMAC-SHA256"
            or signature.key_id != self._key_id
            or signature.classification != "LOCAL_EXECUTED_SELF_ATTESTED"
        ):
            return False
        return hmac.compare_digest(self.sign(payload).value, signature.value)


def _bind_native_abi(library: Any) -> None:
    library.elmos_attestation_sign.argtypes = [
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_size_t,
        ctypes.c_char_p,
    ]
    library.elmos_attestation_sign.restype = ctypes.c_void_p
    library.elmos_merkle_root.argtypes = [ctypes.c_char_p]
    library.elmos_merkle_root.restype = ctypes.c_void_p
    library.elmos_free_string.argtypes = [ctypes.c_void_p]
    library.elmos_free_string.restype = None


def _verified_file_digest(path: Path) -> str:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise NativeAttestationError("native library path is missing or unsafe") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise NativeAttestationError("native library must be a regular file")
        if before.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise NativeAttestationError(
                "native library must not be writable by group or others"
            )
        if before.st_size < 1 or before.st_size > _MAX_LIBRARY_BYTES:
            raise NativeAttestationError("native library size is outside the bound")
        digest = hashlib.sha256()
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if remaining or any(
            getattr(before, field) != getattr(after, field) for field in stable_fields
        ):
            raise NativeAttestationError("native library changed while hashing")
        return "sha256:" + digest.hexdigest()
    finally:
        os.close(descriptor)


def _python_merkle_root(digests: Sequence[str]) -> str:
    if not digests:
        return hashlib.sha256(b"").hexdigest()
    level = [bytes.fromhex(value) for value in digests]
    while len(level) > 1:
        next_level: list[bytes] = []
        for index in range(0, len(level), 2):
            left = level[index]
            right = level[index + 1] if index + 1 < len(level) else left
            next_level.append(hashlib.sha256(left + right).digest())
        level = next_level
    return level[0].hex()


__all__ = [
    "NativeAttestationBridge",
    "NativeAttestationError",
    "NativeHmacLocalAttestationSigner",
    "NativeLibraryIdentity",
]
