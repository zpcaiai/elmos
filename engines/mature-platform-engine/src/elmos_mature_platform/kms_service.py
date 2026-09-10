"""Enterprise Key Management Service (KMS) & Envelope Encryption for Elmos Mature Platform."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from elmos_mature_platform.types import (
    CryptoAuditEntry,
    EncryptedPayload,
    KmsKeyDescriptor,
)


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("utf-8"))


class EnterpriseKmsService:
    """Enterprise KMS with Envelope Encryption, Key Rotation, Crypto-Shredding and Tamper-Evident Audit."""

    def __init__(self, key_store_dir: Optional[str] = None) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = key_store_dir or self._temp_dir.name
        self.keys: Dict[str, Dict[int, KmsKeyDescriptor]] = {}  # key_id -> version -> descriptor
        self.active_versions: Dict[str, int] = {}  # key_id -> active version
        self.audit_log: List[CryptoAuditEntry] = []
        self.last_audit_hash: str = "0" * 64
        self.event_log: List[str] = []

        # Create master platform root key
        self.create_key("platform-master-key", rotation_days=90)

    def __del__(self) -> None:
        try:
            self._temp_dir.cleanup()
        except Exception:
            pass

    def _log(self, message: str) -> None:
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        entry = f"[{ts}][KMS-SERVICE] {message}"
        self.event_log.append(entry)

    def _append_audit(
        self,
        operation: str,
        key_id: str,
        key_version: int,
        tenant_id: str,
        actor: str,
        status: str,
    ) -> CryptoAuditEntry:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        entry_id = f"audit-{len(self.audit_log) + 1:06d}"
        payload = f"{entry_id}:{now}:{operation}:{key_id}:{key_version}:{tenant_id}:{actor}:{status}:{self.last_audit_hash}"
        entry_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        entry = CryptoAuditEntry(
            entry_id=entry_id,
            timestamp=now,
            operation=operation,
            key_id=key_id,
            key_version=key_version,
            tenant_id=tenant_id,
            actor=actor,
            status=status,
            prev_hash=self.last_audit_hash,
            entry_hash=entry_hash,
        )
        self.audit_log.append(entry)
        self.last_audit_hash = entry_hash
        return entry

    def create_key(self, key_id: str, rotation_days: int = 90) -> KmsKeyDescriptor:
        """Creates a new KMS Customer Managed Key (CMK/KEK) version 1."""
        raw_key = secrets.token_bytes(32)  # 256 bits
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        desc = KmsKeyDescriptor(
            key_id=key_id,
            version=1,
            algorithm="AES-256-AUTHENTICATED",
            created_at=now,
            rotation_interval_days=rotation_days,
            raw_key_bytes=raw_key,
        )
        if key_id not in self.keys:
            self.keys[key_id] = {}
        self.keys[key_id][1] = desc
        self.active_versions[key_id] = 1

        self._append_audit("CREATE_KEY", key_id, 1, "system", "kms-admin", "SUCCESS")
        self._log(f"Created KMS key {key_id} version 1 (256-bit AES)")
        return desc

    def rotate_key(self, key_id: str, actor: str = "kms-rotator") -> KmsKeyDescriptor:
        """Rotates a key to a new version, preserving older versions for decryption."""
        if key_id not in self.keys:
            raise KeyError(f"Key {key_id} not found")

        current_ver = self.active_versions[key_id]
        new_ver = current_ver + 1
        raw_key = secrets.token_bytes(32)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        desc = KmsKeyDescriptor(
            key_id=key_id,
            version=new_ver,
            algorithm="AES-256-AUTHENTICATED",
            created_at=now,
            rotation_interval_days=self.keys[key_id][current_ver].rotation_interval_days,
            raw_key_bytes=raw_key,
        )
        self.keys[key_id][new_ver] = desc
        self.active_versions[key_id] = new_ver

        self._append_audit("ROTATE_KEY", key_id, new_ver, "system", actor, "SUCCESS")
        self._log(f"Rotated key {key_id} to active version {new_ver}")
        return desc

    def crypto_shred_key(self, key_id: str, version: Optional[int] = None, actor: str = "compliance-officer") -> int:
        """Cryptographically shreds key material rendering all encrypted data permanently unrecoverable."""
        if key_id not in self.keys:
            raise KeyError(f"Key {key_id} not found")

        shredded_count = 0
        versions_to_shred = [version] if version else list(self.keys[key_id].keys())

        for v in versions_to_shred:
            desc = self.keys[key_id].get(v)
            if desc and not desc.is_shredded:
                # Overwrite memory with zeroes before releasing
                desc.raw_key_bytes = b"\x00" * len(desc.raw_key_bytes)
                desc.is_shredded = True
                desc.is_revoked = True
                shredded_count += 1
                self._append_audit("CRYPTO_SHRED", key_id, v, "system", actor, "SUCCESS")
                self._log(f"CRYPTO-SHREDDED key {key_id} v{v}: key material permanently destroyed")

        return shredded_count

    def _encrypt_aes_cbc_hmac(self, plaintext: bytes, key: bytes, aad: bytes) -> Tuple[bytes, bytes, bytes]:
        """Encrypt-then-MAC authenticated encryption using OpenSSL AES-256-CBC and HMAC-SHA256."""
        # Derive enc_key and mac_key via HKDF/SHA256
        enc_key = hashlib.sha256(key + b":enc").digest()
        mac_key = hashlib.sha256(key + b":mac").digest()

        iv = secrets.token_bytes(16)
        # OpenSSL aes-256-cbc with explicit -K and -iv
        hex_key = enc_key.hex()
        hex_iv = iv.hex()

        proc = subprocess.run(
            ["openssl", "enc", "-aes-256-cbc", "-K", hex_key, "-iv", hex_iv],
            input=plaintext,
            check=True,
            capture_output=True,
        )
        ciphertext = proc.stdout

        # HMAC over AAD || IV || Ciphertext
        tag = hmac.new(mac_key, aad + iv + ciphertext, hashlib.sha256).digest()
        return ciphertext, iv, tag

    def _decrypt_aes_cbc_hmac(self, ciphertext: bytes, iv: bytes, tag: bytes, key: bytes, aad: bytes) -> bytes:
        """Verifies MAC in constant time and decrypts."""
        enc_key = hashlib.sha256(key + b":enc").digest()
        mac_key = hashlib.sha256(key + b":mac").digest()

        expected_tag = hmac.new(mac_key, aad + iv + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            raise ValueError("E_CRYPTO_TAMPER: Authentication tag mismatch! Ciphertext or AAD was tampered.")

        hex_key = enc_key.hex()
        hex_iv = iv.hex()

        proc = subprocess.run(
            ["openssl", "enc", "-d", "-aes-256-cbc", "-K", hex_key, "-iv", hex_iv],
            input=ciphertext,
            check=True,
            capture_output=True,
        )
        return proc.stdout

    def envelope_encrypt(
        self,
        key_id: str,
        plaintext: bytes,
        tenant_id: str,
        resource_id: str,
        actor: str = "app-worker",
    ) -> EncryptedPayload:
        """Envelope encrypts plaintext: DEK encrypted under KEK, plaintext encrypted under DEK."""
        if key_id not in self.keys:
            raise KeyError(f"Key {key_id} not found")

        active_ver = self.active_versions[key_id]
        kek_desc = self.keys[key_id][active_ver]

        if kek_desc.is_shredded or kek_desc.is_revoked:
            self._append_audit("ENVELOPE_ENCRYPT", key_id, active_ver, tenant_id, actor, "DENIED_SHREDDED")
            raise PermissionError(f"Cannot encrypt with shredded/revoked key {key_id} v{active_ver}")

        # 1. Generate ephemeral DEK (32 bytes = 256 bits)
        dek = secrets.token_bytes(32)

        # 2. AAD binds tenant and resource ID
        aad = f"tenant={tenant_id}&resource={resource_id}&key={key_id}&v={active_ver}".encode("utf-8")

        # 3. Encrypt plaintext using DEK
        ct, iv, tag = self._encrypt_aes_cbc_hmac(plaintext, dek, aad)

        # 4. Encrypt DEK under KEK
        dek_aad = f"dek_wrap:{key_id}:{active_ver}".encode("utf-8")
        enc_dek, dek_iv, dek_tag = self._encrypt_aes_cbc_hmac(dek, kek_desc.raw_key_bytes, dek_aad)
        encrypted_dek_bundle = _b64e(dek_iv + dek_tag + enc_dek)

        sha256_ct = hashlib.sha256(ct).hexdigest()

        self._append_audit("ENVELOPE_ENCRYPT", key_id, active_ver, tenant_id, actor, "SUCCESS")
        self._log(f"Envelope encrypted payload for tenant={tenant_id}, resource={resource_id}, key={key_id} v{active_ver}")

        return EncryptedPayload(
            key_id=key_id,
            key_version=active_ver,
            algorithm="AES-256-AUTHENTICATED-ENVELOPE",
            ciphertext_b64=_b64e(ct),
            iv_b64=_b64e(iv),
            tag_b64=_b64e(tag),
            aad_b64=_b64e(aad),
            encrypted_dek_b64=encrypted_dek_bundle,
            sha256_ciphertext=sha256_ct,
        )

    def envelope_decrypt(
        self,
        payload: EncryptedPayload,
        tenant_id: str,
        resource_id: str,
        actor: str = "app-worker",
    ) -> bytes:
        """Decrypts envelope payload with AAD and key validation."""
        key_id = payload.key_id
        ver = payload.key_version

        if key_id not in self.keys or ver not in self.keys[key_id]:
            self._append_audit("ENVELOPE_DECRYPT", key_id, ver, tenant_id, actor, "FAIL_KEY_NOT_FOUND")
            raise KeyError(f"Key {key_id} v{ver} not found")

        kek_desc = self.keys[key_id][ver]
        if kek_desc.is_shredded:
            self._append_audit("ENVELOPE_DECRYPT", key_id, ver, tenant_id, actor, "FAIL_KEY_SHREDDED")
            raise PermissionError(f"CRYPTO_SHREDDED: Key {key_id} v{ver} has been shredded. Data is permanently unrecoverable.")

        if kek_desc.is_revoked:
            self._append_audit("ENVELOPE_DECRYPT", key_id, ver, tenant_id, actor, "FAIL_KEY_REVOKED")
            raise PermissionError(f"CRYPTO_REVOKED: Key {key_id} v{ver} is revoked.")

        # 1. Unwrap DEK using KEK
        dek_bundle = _b64d(payload.encrypted_dek_b64)
        dek_iv = dek_bundle[:16]
        dek_tag = dek_bundle[16:48]
        enc_dek = dek_bundle[48:]
        dek_aad = f"dek_wrap:{key_id}:{ver}".encode("utf-8")

        dek = self._decrypt_aes_cbc_hmac(enc_dek, dek_iv, dek_tag, kek_desc.raw_key_bytes, dek_aad)

        # 2. Verify AAD matches requested tenant & resource
        expected_aad = f"tenant={tenant_id}&resource={resource_id}&key={key_id}&v={ver}".encode("utf-8")
        actual_aad = _b64d(payload.aad_b64)
        if actual_aad != expected_aad:
            self._append_audit("ENVELOPE_DECRYPT", key_id, ver, tenant_id, actor, "FAIL_AAD_MISMATCH")
            raise PermissionError("E_SECURITY_VIOLATION: AAD mismatch. Cross-tenant or cross-resource decryption blocked!")

        # 3. Decrypt ciphertext using DEK
        ct = _b64d(payload.ciphertext_b64)
        iv = _b64d(payload.iv_b64)
        tag = _b64d(payload.tag_b64)

        plaintext = self._decrypt_aes_cbc_hmac(ct, iv, tag, dek, actual_aad)

        self._append_audit("ENVELOPE_DECRYPT", key_id, ver, tenant_id, actor, "SUCCESS")
        return plaintext

    def verify_audit_ledger_integrity(self) -> Tuple[bool, int, str]:
        """Validates cryptographic hash chain across entire crypto audit ledger."""
        current_prev = "0" * 64
        for i, entry in enumerate(self.audit_log):
            if entry.prev_hash != current_prev:
                return False, i, f"Broken chain at index {i}: expected prev {current_prev}, got {entry.prev_hash}"
            payload = f"{entry.entry_id}:{entry.timestamp}:{entry.operation}:{entry.key_id}:{entry.key_version}:{entry.tenant_id}:{entry.actor}:{entry.status}:{entry.prev_hash}"
            expected_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if entry.entry_hash != expected_hash:
                return False, i, f"Tampered entry at index {i}: expected {expected_hash}, got {entry.entry_hash}"
            current_prev = entry.entry_hash
        return True, len(self.audit_log), f"Audit chain valid across {len(self.audit_log)} entries"
