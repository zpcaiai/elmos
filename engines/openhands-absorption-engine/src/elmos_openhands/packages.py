"""Signed capability package registry and immutable run pinning."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .errors import ContractViolation, IdempotencyConflict, NotConfigured
from .models import canonical_json, digest_of, validate_id, utc_now


@dataclass(frozen=True, slots=True)
class CapabilityPackage:
    name: str
    version: str
    publisher: str
    manifest: Mapping[str, Any]
    digest: str
    signature: str | None
    trust_level: str


class PackageSigner(Protocol):
    def sign(self, digest: str, publisher: str) -> str: ...

    def verify(self, digest: str, publisher: str, signature: str) -> bool: ...


class HmacPackageSigner:
    """Reference signer; production can replace it with KMS-backed Ed25519."""

    def __init__(self, keys: Mapping[str, bytes]) -> None:
        self.keys = dict(keys)

    def sign(self, digest: str, publisher: str) -> str:
        key = self.keys.get(publisher)
        if key is None:
            raise NotConfigured("publisher signing key is not configured")
        return hmac.new(key, f"{publisher}:{digest}".encode(), hashlib.sha256).hexdigest()

    def verify(self, digest: str, publisher: str, signature: str) -> bool:
        try:
            return hmac.compare_digest(self.sign(digest, publisher), signature)
        except NotConfigured:
            return False


class PackageValidator:
    def validate(self, manifest: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
        required = ("name", "version", "publisher", "permissions", "dependencies", "files")
        missing = tuple(key for key in required if key not in manifest)
        if missing:
            raise ContractViolation("package manifest missing: " + ",".join(missing))
        name = str(manifest["name"])
        version = str(manifest["version"])
        publisher = str(manifest["publisher"])
        validate_id(name, "package.name")
        validate_id(version, "package.version")
        validate_id(publisher, "package.publisher")
        if not isinstance(manifest["permissions"], list) or not isinstance(manifest["dependencies"], list) or not isinstance(manifest["files"], list):
            raise ContractViolation("package permissions/dependencies/files must be arrays")
        if any(not isinstance(permission, str) or not permission or permission.startswith("*") for permission in manifest["permissions"]):
            raise ContractViolation("package permissions must be explicit and non-wildcard")
        for file in manifest["files"]:
            if not isinstance(file, Mapping) or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(file.get("path", ""))):
                raise ContractViolation("package files require digest-bound path entries")
        return name, tuple(str(item) for item in manifest["permissions"])


class CapabilityPackageRegistry:
    def __init__(self, database: str = ":memory:", *, signer: PackageSigner | None = None) -> None:
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS packages(name TEXT NOT NULL, version TEXT NOT NULL, publisher TEXT NOT NULL, digest TEXT NOT NULL, signature TEXT, trust_level TEXT NOT NULL, manifest TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(name,version));
            CREATE TABLE IF NOT EXISTS tenant_pins(tenant_id TEXT NOT NULL, name TEXT NOT NULL, version TEXT NOT NULL, PRIMARY KEY(tenant_id,name));
            """
        )
        self.signer = signer
        self.validator = PackageValidator()
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def publish(self, manifest: Mapping[str, Any], *, signature: str | None = None, trust_level: str = "untrusted") -> CapabilityPackage:
        if trust_level not in {"untrusted", "trusted", "verified"}:
            raise ContractViolation("package trust level is invalid")
        name, _ = self.validator.validate(manifest)
        digest = digest_of(dict(manifest))
        publisher = str(manifest["publisher"])
        if not signature and self.signer is not None:
            signature = self.signer.sign(digest, publisher)
        if not signature or self.signer is None or not self.signer.verify(digest, publisher, signature):
            raise ContractViolation("package signature is absent or unverifiable")
        package = CapabilityPackage(name, str(manifest["version"]), publisher, dict(manifest), digest, signature, trust_level)
        with self._lock:
            existing = self._connection.execute("SELECT digest FROM packages WHERE name=? AND version=?", (package.name, package.version)).fetchone()
            if existing is not None and existing["digest"] != package.digest:
                raise IdempotencyConflict("package version already exists with a different digest")
            self._connection.execute("INSERT OR IGNORE INTO packages VALUES(?,?,?,?,?,?,?,?,?)", (package.name, package.version, package.publisher, package.digest, package.signature, package.trust_level, canonical_json(dict(package.manifest)), "published", utc_now()))
        return package

    def install(self, package: CapabilityPackage) -> CapabilityPackage:
        stored = self._connection.execute("SELECT digest,publisher,signature,trust_level,state FROM packages WHERE name=? AND version=?", (package.name, package.version)).fetchone()
        if stored is None or stored["digest"] != package.digest or stored["publisher"] != package.publisher or stored["signature"] != package.signature:
            raise ContractViolation("package must be published with the same content digest before install")
        if self.signer is None or package.signature is None or not self.signer.verify(package.digest, package.publisher, package.signature):
            raise ContractViolation("installed package signature is not verifiable")
        self._connection.execute("UPDATE packages SET state=CASE WHEN state IN ('active','approved','deprecated') THEN state ELSE 'installed' END WHERE name=? AND version=?", (package.name, package.version))
        return package

    def approve(self, name: str, version: str, approver: str) -> CapabilityPackage:
        """Record the separate trust decision required before activation."""
        validate_id(approver, "package.approver")
        row = self._connection.execute("SELECT * FROM packages WHERE name=? AND version=?", (name, version)).fetchone()
        if row is None:
            raise KeyError(f"{name}@{version}")
        if row["state"] not in {"installed", "approved"} or row["state"] == "revoked":
            raise ContractViolation("only an installed package can be approved")
        self._connection.execute("UPDATE packages SET state='approved',trust_level='verified' WHERE name=? AND version=?", (name, version))
        return self._package(self._connection.execute("SELECT * FROM packages WHERE name=? AND version=?", (name, version)).fetchone())

    def activate(self, tenant_id: str, name: str, version: str) -> CapabilityPackage:
        validate_id(tenant_id, "tenant_id")
        row = self._connection.execute("SELECT * FROM packages WHERE name=? AND version=?", (name, version)).fetchone()
        if row is None:
            raise KeyError(f"{name}@{version}")
        if row["state"] == "revoked":
            raise ContractViolation("revoked package cannot be activated")
        if row["state"] not in {"installed", "approved", "active"}:
            raise ContractViolation("package must be installed before activation")
        if row["trust_level"] not in {"trusted", "verified"}:
            raise ContractViolation("untrusted package cannot gain runtime privileges")
        self._connection.execute("UPDATE packages SET state='active' WHERE name=? AND version=?", (name, version))
        self._connection.execute("INSERT INTO tenant_pins VALUES(?,?,?) ON CONFLICT(tenant_id,name) DO UPDATE SET version=excluded.version", (tenant_id, name, version))
        return self._package(row)

    def pin_for_run(self, tenant_id: str, name: str) -> CapabilityPackage:
        validate_id(tenant_id, "tenant_id")
        row = self._connection.execute("SELECT p.* FROM packages p JOIN tenant_pins t ON p.name=t.name AND p.version=t.version WHERE t.tenant_id=? AND t.name=?", (tenant_id, name)).fetchone()
        if row is None or row["state"] == "revoked":
            raise ContractViolation("no active package pin for tenant")
        return self._package(row)

    def revoke(self, name: str, version: str, reason: str) -> None:
        if not reason:
            raise ContractViolation("revocation reason is required")
        self._connection.execute("UPDATE packages SET state='revoked' WHERE name=? AND version=?", (name, version))

    def deprecate(self, name: str, version: str, reason: str) -> None:
        if not reason:
            raise ContractViolation("deprecation reason is required")
        updated = self._connection.execute("UPDATE packages SET state='deprecated' WHERE name=? AND version=? AND state NOT IN ('revoked','deprecated')", (name, version)).rowcount
        if updated != 1:
            raise ContractViolation("package cannot be deprecated in its current state")

    def rollback(self, tenant_id: str, name: str, version: str) -> CapabilityPackage:
        return self.activate(tenant_id, name, version)

    @staticmethod
    def _package(row: sqlite3.Row) -> CapabilityPackage:
        return CapabilityPackage(row["name"], row["version"], row["publisher"], json.loads(row["manifest"]), row["digest"], row["signature"], row["trust_level"])
