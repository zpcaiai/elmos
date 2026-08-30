from __future__ import annotations

import base64
import fcntl
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .canonical import canonical_json, digest_bytes, validate_digest, validate_identifier


class ArtifactStoreError(ValueError):
    """Raised when a content-addressed artifact cannot be safely stored/read."""


class ArtifactStore(Protocol):
    """Tenant-bound immutable CAS boundary for local or provider adapters."""

    def put(
        self,
        tenant_id: str,
        data: bytes,
        *,
        media_type: str,
        retention_class: str,
    ) -> dict[str, Any]: ...

    def get(self, tenant_id: str, digest: str) -> bytes: ...

    def metadata(self, tenant_id: str, digest: str) -> dict[str, Any]: ...

    def verify_reference(
        self, tenant_id: str, reference: dict[str, Any]
    ) -> tuple[bytes, dict[str, Any]]: ...

    def delete(
        self,
        tenant_id: str,
        digest: str,
        *,
        retention_class: str | None = None,
        legal_hold: bool = False,
    ) -> None: ...


class ArtifactEnvelopeCipher(Protocol):
    """Operator-owned authenticated-encryption boundary for local artifacts."""

    @property
    def descriptor(self) -> dict[str, str]: ...

    def encrypt(self, plaintext: bytes, *, associated_data: bytes) -> bytes: ...

    def decrypt(self, envelope: bytes, *, associated_data: bytes) -> bytes: ...


class AesGcmEnvelopeCipher:
    """AES-256-GCM envelope encryption using one random data key per artifact.

    The supplied key is a local key-encryption key (KEK), not an application
    default. Production deployments should obtain it from a short-lived KMS or
    secret-manager lease and rotate the key identifier through a governed
    migration. Neither the KEK nor plaintext data is persisted by this class.
    """

    _ENVELOPE_FIELDS = frozenset(
        {
            "version",
            "algorithm",
            "keyWrapAlgorithm",
            "keyId",
            "contentNonce",
            "wrappedKeyNonce",
            "wrappedDataKey",
            "ciphertext",
        }
    )

    def __init__(self, key: bytes, *, key_id: str) -> None:
        if not isinstance(key, bytes) or len(key) != 32:
            raise ArtifactStoreError("artifact encryption KEK must be exactly 32 bytes")
        self._key = bytes(key)
        self._key_id = validate_identifier(key_id, "artifactEncryption.keyId")

    @property
    def descriptor(self) -> dict[str, str]:
        return {
            "algorithm": "AES-256-GCM",
            "keyWrapAlgorithm": "AES-256-GCM",
            "keyId": self._key_id,
        }

    def encrypt(self, plaintext: bytes, *, associated_data: bytes) -> bytes:
        if not isinstance(plaintext, bytes) or not isinstance(associated_data, bytes):
            raise ArtifactStoreError("artifact encryption inputs must be bytes")
        data_key = AESGCM.generate_key(bit_length=256)
        content_nonce = os.urandom(12)
        wrap_nonce = os.urandom(12)
        ciphertext = AESGCM(data_key).encrypt(
            content_nonce, plaintext, b"elmos-artifact-content/v1\x00" + associated_data
        )
        wrapped_key = AESGCM(self._key).encrypt(
            wrap_nonce, data_key, b"elmos-artifact-data-key/v1\x00" + associated_data
        )
        return canonical_json(
            {
                "version": 1,
                **self.descriptor,
                "contentNonce": _encode_binary(content_nonce),
                "wrappedKeyNonce": _encode_binary(wrap_nonce),
                "wrappedDataKey": _encode_binary(wrapped_key),
                "ciphertext": _encode_binary(ciphertext),
            }
        )

    def decrypt(self, envelope: bytes, *, associated_data: bytes) -> bytes:
        if not isinstance(envelope, bytes) or not isinstance(associated_data, bytes):
            raise ArtifactStoreError("artifact decryption inputs must be bytes")
        try:
            value = json.loads(envelope.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ArtifactStoreError("artifact encryption envelope is invalid") from exc
        if not isinstance(value, dict) or set(value) != self._ENVELOPE_FIELDS:
            raise ArtifactStoreError("artifact encryption envelope fields are invalid")
        if value.get("version") != 1 or any(
            value.get(key) != expected for key, expected in self.descriptor.items()
        ):
            raise ArtifactStoreError("artifact encryption envelope policy does not match")
        content_nonce = _decode_binary(value.get("contentNonce"), "contentNonce", 12)
        wrap_nonce = _decode_binary(value.get("wrappedKeyNonce"), "wrappedKeyNonce", 12)
        wrapped_key = _decode_binary(
            value.get("wrappedDataKey"), "wrappedDataKey", 48
        )
        ciphertext = _decode_binary(value.get("ciphertext"), "ciphertext", minimum=16)
        try:
            data_key = AESGCM(self._key).decrypt(
                wrap_nonce,
                wrapped_key,
                b"elmos-artifact-data-key/v1\x00" + associated_data,
            )
            if len(data_key) != 32:
                raise ArtifactStoreError("unwrapped artifact data key is invalid")
            return AESGCM(data_key).decrypt(
                content_nonce,
                ciphertext,
                b"elmos-artifact-content/v1\x00" + associated_data,
            )
        except InvalidTag as exc:
            raise ArtifactStoreError(
                "artifact encryption authentication failed"
            ) from exc


class ContentAddressedArtifactStore:
    """Tenant-isolated, immutable and envelope-encrypted filesystem CAS.

    Tenant identity, plaintext digest, media type, size and retention policy are
    authenticated as AES-GCM associated data. The filesystem path contains only
    a tenant digest. Writes are process-safe, atomic and immutable. There is no
    plaintext compatibility mode: callers must explicitly supply a cipher.
    """

    _RETENTION_CLASSES = frozenset({"EPHEMERAL", "STANDARD", "AUDIT", "LEGAL_HOLD"})

    def __init__(
        self,
        root: str | Path,
        *,
        envelope_cipher: ArtifactEnvelopeCipher | None = None,
    ) -> None:
        if envelope_cipher is None or any(
            not callable(getattr(envelope_cipher, method, None))
            for method in ("encrypt", "decrypt")
        ):
            raise ArtifactStoreError("artifact envelope cipher is required")
        descriptor = getattr(envelope_cipher, "descriptor", None)
        if not isinstance(descriptor, dict) or set(descriptor) != {
            "algorithm",
            "keyWrapAlgorithm",
            "keyId",
        }:
            raise ArtifactStoreError("artifact envelope cipher descriptor is invalid")
        for key, value in descriptor.items():
            if not isinstance(value, str) or not value:
                raise ArtifactStoreError(f"artifact envelope cipher {key} is invalid")
        raw_root = Path(root).expanduser()
        if raw_root.is_symlink():
            raise ArtifactStoreError("artifact root must not be a symlink")
        self.root = raw_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or not self.root.is_dir():
            raise ArtifactStoreError("artifact root must be a real directory")
        os.chmod(self.root, 0o700)
        self.envelope_cipher = envelope_cipher

    def put(
        self, tenant_id: str, data: bytes, *, media_type: str, retention_class: str
    ) -> dict[str, Any]:
        validate_identifier(tenant_id, "tenantId")
        if not isinstance(data, bytes):
            raise ArtifactStoreError("artifact data must be bytes")
        if len(data) > 4 * 1024 * 1024:
            raise ArtifactStoreError("artifact exceeds local size bound")
        if not isinstance(media_type, str) or not media_type or len(media_type) > 200:
            raise ArtifactStoreError("media type is invalid")
        if retention_class not in self._RETENTION_CLASSES:
            raise ArtifactStoreError("retention class is invalid")
        digest = digest_bytes(data)
        digest_hex = digest.removeprefix("sha256:")
        tenant_digest = self._tenant_digest(tenant_id)
        directory = self._tenant_directory(tenant_id) / digest_hex[:2]
        self._ensure_directory(directory)
        target = directory / digest_hex
        metadata_target = directory / f"{digest_hex}.metadata.json"
        core_metadata = {
            "tenantDigest": tenant_digest,
            "sha256": digest,
            "mediaType": media_type,
            "sizeBytes": len(data),
            "retentionClass": retention_class,
        }
        associated_data = canonical_json(core_metadata)
        with self._artifact_lock(directory / f".{digest_hex}.lock"):
            target_exists = target.exists() or target.is_symlink()
            metadata_exists = metadata_target.exists() or metadata_target.is_symlink()
            if target_exists != metadata_exists:
                raise ArtifactStoreError("artifact content and metadata are inconsistent")
            if target_exists:
                existing_metadata = self._read_metadata_path(
                    metadata_target, tenant_id, digest
                )
                if {
                    key: existing_metadata.get(key) for key in core_metadata
                } != core_metadata:
                    raise ArtifactStoreError("artifact metadata cannot be overwritten")
                existing = self._read_plaintext(
                    target, existing_metadata, associated_data=associated_data
                )
                if existing != data:
                    raise ArtifactStoreError(
                        "content-addressed path is occupied by different content"
                    )
            else:
                envelope = self.envelope_cipher.encrypt(
                    data, associated_data=associated_data
                )
                encryption = {
                    "state": "ENCRYPTED",
                    **self.envelope_cipher.descriptor,
                    "envelopeDigest": digest_bytes(envelope),
                }
                metadata = {**core_metadata, "encryption": encryption}
                self._install_immutable(target, envelope)
                try:
                    self._install_immutable(
                        metadata_target, canonical_json(metadata) + b"\n"
                    )
                except Exception:
                    target.unlink(missing_ok=True)
                    raise
        return {
            "uri": f"cas://{tenant_digest.removeprefix('sha256:')}/{digest}",
            "sha256": digest,
            "mediaType": media_type,
            "sizeBytes": len(data),
            "immutable": True,
            "retentionClass": retention_class,
            "encrypted": True,
            "encryptionKeyId": self.envelope_cipher.descriptor["keyId"],
        }

    def get(self, tenant_id: str, digest: str) -> bytes:
        validate_identifier(tenant_id, "tenantId")
        canonical = validate_digest(digest, "sha256")
        digest_hex = canonical.removeprefix("sha256:")
        directory = self._tenant_directory(tenant_id) / digest_hex[:2]
        metadata = self._read_metadata_path(
            directory / f"{digest_hex}.metadata.json", tenant_id, canonical
        )
        core_metadata = {
            key: metadata[key]
            for key in (
                "tenantDigest",
                "sha256",
                "mediaType",
                "sizeBytes",
                "retentionClass",
            )
        }
        data = self._read_plaintext(
            directory / digest_hex,
            metadata,
            associated_data=canonical_json(core_metadata),
        )
        if digest_bytes(data) != canonical or len(data) != metadata["sizeBytes"]:
            raise ArtifactStoreError("artifact plaintext digest or size mismatch")
        return data

    def metadata(self, tenant_id: str, digest: str) -> dict[str, Any]:
        validate_identifier(tenant_id, "tenantId")
        canonical = validate_digest(digest, "sha256")
        digest_hex = canonical.removeprefix("sha256:")
        return self._read_metadata_path(
            self._tenant_directory(tenant_id)
            / digest_hex[:2]
            / f"{digest_hex}.metadata.json",
            tenant_id,
            canonical,
        )

    def verify_reference(
        self, tenant_id: str, reference: dict[str, Any]
    ) -> tuple[bytes, dict[str, Any]]:
        """Resolve one exact tenant-bound reference and verify every declared fact."""
        if not isinstance(reference, dict):
            raise ArtifactStoreError("artifact reference must be an object")
        uri = reference.get("uri")
        if not isinstance(uri, str) or not uri:
            raise ArtifactStoreError("artifact reference URI is required")
        digest = validate_digest(reference.get("sha256"), "artifactReference.sha256")
        metadata = self.metadata(tenant_id, digest)
        tenant_digest = metadata["tenantDigest"].removeprefix("sha256:")
        expected_uri = f"cas://{tenant_digest}/{digest}"
        if uri != expected_uri:
            raise ArtifactStoreError("artifact reference URI binding mismatch")
        for reference_key, metadata_key in (
            ("mediaType", "mediaType"),
            ("sizeBytes", "sizeBytes"),
            ("retentionClass", "retentionClass"),
        ):
            if (
                reference_key in reference
                and reference[reference_key] != metadata[metadata_key]
            ):
                raise ArtifactStoreError(
                    f"artifact reference {reference_key} binding mismatch"
                )
        if "immutable" in reference and reference["immutable"] is not True:
            raise ArtifactStoreError("artifact reference must be immutable")
        if "encrypted" in reference and reference["encrypted"] is not True:
            raise ArtifactStoreError("artifact reference must remain encrypted at rest")
        return self.get(tenant_id, digest), metadata

    def delete(
        self,
        tenant_id: str,
        digest: str,
        *,
        retention_class: str | None = None,
        legal_hold: bool = False,
    ) -> None:
        """Apply the local retention policy; audit evidence is never deleted."""
        if legal_hold:
            raise ArtifactStoreError("legal-hold artifacts cannot be deleted")
        metadata = self.metadata(tenant_id, digest)
        actual_retention = metadata.get("retentionClass")
        if retention_class is not None and retention_class != actual_retention:
            raise ArtifactStoreError("retention class does not match artifact metadata")
        if actual_retention != "EPHEMERAL":
            raise ArtifactStoreError("only EPHEMERAL artifacts may be deleted locally")
        canonical = validate_digest(digest, "sha256")
        digest_hex = canonical.removeprefix("sha256:")
        directory = self._tenant_directory(tenant_id) / digest_hex[:2]
        content = directory / digest_hex
        metadata_path = directory / f"{digest_hex}.metadata.json"
        with self._artifact_lock(directory / f".{digest_hex}.lock"):
            if content.is_symlink() or metadata_path.is_symlink():
                raise ArtifactStoreError("artifact path is unsafe")
            try:
                content.unlink()
                metadata_path.unlink()
            except FileNotFoundError as exc:
                raise ArtifactStoreError("artifact is missing") from exc

    def _tenant_digest(self, tenant_id: str) -> str:
        return digest_bytes(tenant_id.encode("utf-8"))

    def _tenant_directory(self, tenant_id: str) -> Path:
        return self.root / self._tenant_digest(tenant_id).removeprefix("sha256:")

    def _ensure_directory(self, path: Path) -> None:
        relative = path.relative_to(self.root)
        current = self.root
        for part in relative.parts:
            current = current / part
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            try:
                metadata = current.lstat()
            except OSError as exc:
                raise ArtifactStoreError("artifact path component is unavailable") from exc
            if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise ArtifactStoreError(f"artifact path component is unsafe: {current}")
            os.chmod(current, 0o700)

    @contextmanager
    def _artifact_lock(self, path: Path) -> Iterator[None]:
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except OSError as exc:
            raise ArtifactStoreError("artifact lock path is unsafe") from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ArtifactStoreError("artifact lock is not a regular file")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _install_immutable(self, target: Path, data: bytes) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o440)
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError as exc:
                raise ArtifactStoreError("artifact path cannot be overwritten") from exc
        finally:
            if temporary.exists() or temporary.is_symlink():
                temporary.unlink()

    def _read_metadata_path(
        self, path: Path, tenant_id: str, digest: str
    ) -> dict[str, Any]:
        if path.is_symlink() or not path.is_file():
            raise ArtifactStoreError("artifact metadata is missing or unsafe")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise ArtifactStoreError("artifact metadata is invalid") from exc
        required = {
            "tenantDigest",
            "sha256",
            "mediaType",
            "sizeBytes",
            "retentionClass",
            "encryption",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise ArtifactStoreError("artifact metadata fields are invalid")
        if value.get("tenantDigest") != self._tenant_digest(tenant_id):
            raise ArtifactStoreError("artifact metadata tenant binding mismatch")
        if value.get("sha256") != digest:
            raise ArtifactStoreError("artifact metadata digest mismatch")
        if (
            not isinstance(value.get("sizeBytes"), int)
            or isinstance(value.get("sizeBytes"), bool)
            or value["sizeBytes"] < 0
            or not isinstance(value.get("mediaType"), str)
            or not value["mediaType"]
            or value.get("retentionClass") not in self._RETENTION_CLASSES
        ):
            raise ArtifactStoreError("artifact metadata values are invalid")
        encryption = value.get("encryption")
        expected_encryption = {
            "state": "ENCRYPTED",
            **self.envelope_cipher.descriptor,
        }
        if not isinstance(encryption, dict) or any(
            encryption.get(key) != expected
            for key, expected in expected_encryption.items()
        ):
            raise ArtifactStoreError("artifact encryption metadata does not match")
        if set(encryption) != {*expected_encryption, "envelopeDigest"}:
            raise ArtifactStoreError("artifact encryption metadata fields are invalid")
        validate_digest(encryption.get("envelopeDigest"), "encryption.envelopeDigest")
        return value

    def _read_plaintext(
        self, path: Path, metadata: dict[str, Any], *, associated_data: bytes
    ) -> bytes:
        if path.is_symlink() or not path.is_file():
            raise ArtifactStoreError("artifact is missing or unsafe")
        envelope = path.read_bytes()
        if digest_bytes(envelope) != metadata["encryption"]["envelopeDigest"]:
            raise ArtifactStoreError("artifact encryption envelope digest mismatch")
        return self.envelope_cipher.decrypt(envelope, associated_data=associated_data)


def _encode_binary(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode_binary(
    value: Any, field: str, exact: int | None = None, *, minimum: int | None = None
) -> bytes:
    if not isinstance(value, str):
        raise ArtifactStoreError(f"artifact encryption {field} is invalid")
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise ArtifactStoreError(f"artifact encryption {field} is invalid") from exc
    if exact is not None and len(decoded) != exact:
        raise ArtifactStoreError(f"artifact encryption {field} length is invalid")
    if minimum is not None and len(decoded) < minimum:
        raise ArtifactStoreError(f"artifact encryption {field} length is invalid")
    return decoded


__all__ = [
    "AesGcmEnvelopeCipher",
    "ArtifactEnvelopeCipher",
    "ArtifactStore",
    "ArtifactStoreError",
    "ContentAddressedArtifactStore",
]
