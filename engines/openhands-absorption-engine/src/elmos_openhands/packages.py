"""Signed capability package registry and immutable run pinning."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
import sqlite3
import threading
import base64
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Protocol

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
    """Local-test signer. It must not be used as production publisher proof."""

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


class Ed25519PackageSigner:
    """Asymmetric publisher signer with an explicit public-key trust map."""

    def __init__(self, private_keys: Mapping[str, Any] | None = None, public_keys: Mapping[str, Any] | None = None) -> None:
        self.private_keys = dict(private_keys or {})
        self.public_keys = dict(public_keys or {})

    @classmethod
    def from_raw_keys(cls, *, private_keys: Mapping[str, bytes] | None = None, public_keys: Mapping[str, bytes] | None = None) -> "Ed25519PackageSigner":
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
        except ImportError as error:  # pragma: no cover - optional production dependency
            raise NotConfigured("cryptography is required for Ed25519 packages") from error
        private = {publisher: Ed25519PrivateKey.from_private_bytes(value) for publisher, value in (private_keys or {}).items()}
        public = {publisher: Ed25519PublicKey.from_public_bytes(value) for publisher, value in (public_keys or {}).items()}
        for publisher, key in private.items():
            public.setdefault(publisher, key.public_key())
        return cls(private, public)

    def sign(self, digest: str, publisher: str) -> str:
        key = self.private_keys.get(publisher)
        if key is None:
            raise NotConfigured("publisher Ed25519 private key is not configured")
        value = key.sign(f"{publisher}:{digest}".encode("utf-8"))
        return "ed25519:" + base64.b64encode(value).decode("ascii")

    def verify(self, digest: str, publisher: str, signature: str) -> bool:
        key = self.public_keys.get(publisher)
        if key is None or not signature.startswith("ed25519:"):
            return False
        try:
            value = base64.b64decode(signature.split(":", 1)[1], validate=True)
            key.verify(value, f"{publisher}:{digest}".encode("utf-8"))
        except Exception:
            return False
        return True


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
            if not isinstance(file, Mapping):
                raise ContractViolation("package files require digest-bound path entries")
            path = str(file.get("path", ""))
            digest = str(file.get("digest", path if path.startswith("sha256:") else ""))
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                raise ContractViolation("package files require sha256 digests")
            if not path.startswith("sha256:"):
                normalized = PurePosixPath(path)
                if normalized.is_absolute() or ".." in normalized.parts or not path:
                    raise ContractViolation("package file path escapes package root")
        supply_chain = manifest.get("supply_chain")
        if supply_chain is not None:
            if not isinstance(supply_chain, Mapping) or not isinstance(supply_chain.get("sbom"), Mapping) or not isinstance(supply_chain.get("dependency_lock"), Mapping) or not isinstance(supply_chain.get("provenance"), Mapping):
                raise ContractViolation("package supply-chain metadata is incomplete")
            production_fields = ("minimum_elmos_version", "network_domains", "contract_versions", "migrations", "rollback")
            if any(field not in manifest for field in production_fields):
                raise ContractViolation("production package governance metadata is incomplete")
            if not isinstance(manifest["network_domains"], list) or any(not isinstance(value, str) or not value or value == "*" for value in manifest["network_domains"]):
                raise ContractViolation("package network domains must be an explicit allowlist")
            if not isinstance(manifest["contract_versions"], Mapping) or not manifest["contract_versions"]:
                raise ContractViolation("package contract versions must be declared")
            if not isinstance(manifest["migrations"], list) or not isinstance(manifest["rollback"], Mapping):
                raise ContractViolation("package migrations and rollback contract are invalid")
            if not str(manifest["minimum_elmos_version"]).strip() or not manifest["rollback"].get("strategy"):
                raise ContractViolation("package compatibility/rollback policy is incomplete")
        return name, tuple(str(item) for item in manifest["permissions"])


@dataclass(frozen=True, slots=True)
class PackageBuild:
    manifest: Mapping[str, Any]
    digest: str
    sbom_digest: str
    dependency_lock_digest: str
    provenance_digest: str
    manifest_digest: str
    bundle: bytes


class CapabilityPackageBuilder:
    """Builds deterministic package manifests, SBOM and dependency locks."""

    def build(
        self,
        metadata: Mapping[str, Any],
        files: Mapping[str, bytes],
        dependencies: Mapping[str, str],
        *,
        build_identity: str,
        source_revision: str,
    ) -> PackageBuild:
        if not files or not build_identity or not re.fullmatch(r"sha256:[0-9a-f]{64}", source_revision):
            raise ContractViolation("package build requires files, builder identity and source revision")
        file_rows: list[dict[str, Any]] = []
        for path, data in sorted(files.items()):
            normalized = PurePosixPath(path)
            if normalized.is_absolute() or ".." in normalized.parts or not path or not isinstance(data, bytes):
                raise ContractViolation("package build file is invalid")
            file_rows.append({"path": path, "digest": "sha256:" + hashlib.sha256(data).hexdigest(), "size_bytes": len(data)})
        dependency_rows = [{"name": name, "version": version} for name, version in sorted(dependencies.items())]
        if any(not row["name"] or not row["version"] or row["version"] in {"*", "latest"} for row in dependency_rows):
            raise ContractViolation("package dependencies must be exactly locked")
        sbom = {"bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1, "components": [{"type": "library", **row} for row in dependency_rows], "files": file_rows}
        lock = {"lock_version": 1, "dependencies": dependency_rows}
        provenance = {"predicateType": "https://slsa.dev/provenance/v1", "builder": {"id": build_identity}, "subject": [{"name": str(metadata.get("name", "package")), "digest": {"sha256": source_revision.removeprefix("sha256:")}}]}
        manifest = {
            **dict(metadata), "dependencies": dependency_rows, "files": file_rows,
            "supply_chain": {"sbom": sbom, "dependency_lock": lock, "provenance": provenance},
        }
        PackageValidator().validate(manifest)
        generated = {
            "manifest.json": canonical_json(manifest).encode("utf-8"),
            "sbom.cdx.json": canonical_json(sbom).encode("utf-8"),
            "dependency-lock.json": canonical_json(lock).encode("utf-8"),
            "provenance.json": canonical_json(provenance).encode("utf-8"),
        }
        collisions = set(files) & set(generated)
        if collisions:
            raise ContractViolation("package source files collide with generated metadata: " + ",".join(sorted(collisions)))
        bundle = _deterministic_zip({**dict(files), **generated})
        build = PackageBuild(
            manifest,
            "sha256:" + hashlib.sha256(bundle).hexdigest(),
            digest_of(sbom),
            digest_of(lock),
            digest_of(provenance),
            digest_of(manifest),
            bundle,
        )
        self.verify(build)
        return build

    def verify(self, build: PackageBuild) -> None:
        if "sha256:" + hashlib.sha256(build.bundle).hexdigest() != build.digest:
            raise ContractViolation("capability package bundle digest mismatch")
        if digest_of(build.manifest) != build.manifest_digest:
            raise ContractViolation("capability package manifest digest mismatch")
        try:
            with zipfile.ZipFile(io.BytesIO(build.bundle)) as archive:
                names = archive.namelist()
                if len(names) != len(set(names)) or len(names) > 10_000:
                    raise ContractViolation("capability package archive member set is invalid")
                total = 0
                members: dict[str, bytes] = {}
                for info in archive.infolist():
                    member_path = PurePosixPath(info.filename)
                    if member_path.is_absolute() or ".." in member_path.parts or info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ContractViolation("capability package archive contains an unsafe member")
                    total += info.file_size
                    if total > 1_073_741_824:
                        raise ContractViolation("capability package archive exceeds the verification limit")
                    members[info.filename] = archive.read(info)
        except (OSError, zipfile.BadZipFile) as error:
            raise ContractViolation("capability package archive is invalid") from error
        manifest_raw = members.get("manifest.json")
        if manifest_raw != canonical_json(build.manifest).encode("utf-8"):
            raise ContractViolation("capability package archive manifest does not match build metadata")
        for file in build.manifest["files"]:
            file_path = str(file["path"])
            value = members.get(file_path)
            if value is None or "sha256:" + hashlib.sha256(value).hexdigest() != str(file["digest"]):
                raise ContractViolation("capability package file digest mismatch: " + file_path)


@dataclass(frozen=True, slots=True)
class PackageConformanceResult:
    status: str
    evidence_digest: str
    checks: Mapping[str, str]
    executor_id: str
    independent_verifier_id: str | None = None


class PackageConformanceRunner:
    """Runs a package only through an explicitly supplied validation sandbox."""

    REQUIRED_CHECKS = ("manifest", "permissions", "dependency_lock", "sbom", "provenance", "unit", "integration", "negative")

    def run(
        self,
        build: PackageBuild,
        sandbox_runner: Callable[[Mapping[str, Any]], Mapping[str, Any]],
        *,
        executor_id: str,
        independent_verifier_id: str | None = None,
    ) -> PackageConformanceResult:
        if not executor_id:
            raise ContractViolation("package conformance executor identity is required")
        value = dict(sandbox_runner(build.manifest))
        checks = {name: str(value.get("checks", {}).get(name, "NOT_RUN")) for name in self.REQUIRED_CHECKS}
        passed = all(status == "PASS" for status in checks.values())
        if independent_verifier_id == executor_id:
            passed = False
            checks["independent_verification"] = "FAIL"
        elif independent_verifier_id is None:
            checks["independent_verification"] = "NOT_RUN"
            passed = False
        evidence = value.get("evidence")
        if not isinstance(evidence, (bytes, bytearray)):
            raise ContractViolation("package conformance must return raw evidence bytes")
        return PackageConformanceResult("PASS" if passed else "BLOCKED", "sha256:" + hashlib.sha256(bytes(evidence)).hexdigest(), checks, executor_id, independent_verifier_id)


class CapabilityPackageRegistry:
    def __init__(self, database: str = ":memory:", *, signer: PackageSigner | None = None) -> None:
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS packages(name TEXT NOT NULL, version TEXT NOT NULL, publisher TEXT NOT NULL, digest TEXT NOT NULL, signature TEXT, trust_level TEXT NOT NULL, manifest TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(name,version));
            CREATE TABLE IF NOT EXISTS tenant_pins(tenant_id TEXT NOT NULL, name TEXT NOT NULL, version TEXT NOT NULL, PRIMARY KEY(tenant_id,name));
            CREATE TABLE IF NOT EXISTS run_pins(tenant_id TEXT NOT NULL,run_id TEXT NOT NULL,name TEXT NOT NULL,version TEXT NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(tenant_id,run_id,name));
            CREATE TABLE IF NOT EXISTS package_visibility(name TEXT NOT NULL,version TEXT NOT NULL,tenant_id TEXT NOT NULL,PRIMARY KEY(name,version,tenant_id));
            CREATE TABLE IF NOT EXISTS vulnerability_actions(name TEXT NOT NULL,version TEXT NOT NULL,advisory_id TEXT NOT NULL,severity TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(name,version,advisory_id));
            CREATE TABLE IF NOT EXISTS package_bundles(name TEXT NOT NULL,version TEXT NOT NULL,bundle_digest TEXT NOT NULL,bundle BLOB NOT NULL,PRIMARY KEY(name,version));
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

    def publish_build(self, build: PackageBuild, *, signature: str | None = None, trust_level: str = "untrusted") -> CapabilityPackage:
        CapabilityPackageBuilder().verify(build)
        if trust_level not in {"untrusted", "trusted", "verified"}:
            raise ContractViolation("package trust level is invalid")
        name, _ = self.validator.validate(build.manifest)
        publisher = str(build.manifest["publisher"])
        signature = signature or (None if self.signer is None else self.signer.sign(build.digest, publisher))
        if not signature or self.signer is None or not self.signer.verify(build.digest, publisher, signature):
            raise ContractViolation("package bundle signature is absent or unverifiable")
        package = CapabilityPackage(name, str(build.manifest["version"]), publisher, dict(build.manifest), build.digest, signature, trust_level)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute("SELECT digest FROM packages WHERE name=? AND version=?", (package.name, package.version)).fetchone()
                if existing is not None and existing["digest"] != package.digest:
                    raise IdempotencyConflict("package version already exists with a different bundle")
                self._connection.execute("INSERT OR IGNORE INTO packages VALUES(?,?,?,?,?,?,?,?,?)", (package.name, package.version, package.publisher, package.digest, package.signature, package.trust_level, canonical_json(dict(package.manifest)), "published", utc_now()))
                self._connection.execute("INSERT OR IGNORE INTO package_bundles VALUES(?,?,?,?)", (package.name, package.version, build.digest, build.bundle))
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return package

    def bundle(self, name: str, version: str) -> bytes:
        row = self._connection.execute("SELECT p.digest,b.bundle_digest,b.bundle FROM packages p JOIN package_bundles b ON p.name=b.name AND p.version=b.version WHERE p.name=? AND p.version=?", (name, version)).fetchone()
        if row is None or row["digest"] != row["bundle_digest"]:
            raise ContractViolation("package bundle is unavailable or not digest-bound")
        value = bytes(row["bundle"])
        if "sha256:" + hashlib.sha256(value).hexdigest() != row["bundle_digest"]:
            raise ContractViolation("stored package bundle digest mismatch")
        return value

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
        visibility = self._connection.execute("SELECT tenant_id FROM package_visibility WHERE name=? AND version=?", (name, version)).fetchall()
        if visibility and tenant_id not in {item["tenant_id"] for item in visibility}:
            raise ContractViolation("private package is not visible to tenant")
        self._connection.execute("UPDATE packages SET state='active' WHERE name=? AND version=?", (name, version))
        self._connection.execute("INSERT INTO tenant_pins VALUES(?,?,?) ON CONFLICT(tenant_id,name) DO UPDATE SET version=excluded.version", (tenant_id, name, version))
        return self._package(row)

    def pin_for_run(self, tenant_id: str, name: str) -> CapabilityPackage:
        validate_id(tenant_id, "tenant_id")
        row = self._connection.execute("SELECT p.* FROM packages p JOIN tenant_pins t ON p.name=t.name AND p.version=t.version WHERE t.tenant_id=? AND t.name=?", (tenant_id, name)).fetchone()
        if row is None or row["state"] == "revoked":
            raise ContractViolation("no active package pin for tenant")
        return self._package(row)

    def bind_run(self, tenant_id: str, run_id: str, name: str) -> CapabilityPackage:
        """Pin exact package content for a run; upgrades cannot mutate it."""
        validate_id(run_id, "run_id")
        package = self.pin_for_run(tenant_id, name)
        existing = self._connection.execute("SELECT version,digest FROM run_pins WHERE tenant_id=? AND run_id=? AND name=?", (tenant_id, run_id, name)).fetchone()
        if existing is not None:
            if existing["version"] != package.version or existing["digest"] != package.digest:
                # Return the original immutable pin, not the tenant's newer active version.
                row = self._connection.execute("SELECT * FROM packages WHERE name=? AND version=? AND digest=?", (name, existing["version"], existing["digest"])).fetchone()
                if row is None or row["state"] == "revoked":
                    raise ContractViolation("run package pin is revoked or unavailable")
                return self._package(row)
            return package
        self._connection.execute("INSERT INTO run_pins VALUES(?,?,?,?,?)", (tenant_id, run_id, name, package.version, package.digest))
        return package

    def verify_resume_pins(self, tenant_id: str, run_id: str, expected: Mapping[str, str]) -> tuple[CapabilityPackage, ...]:
        rows = self._connection.execute("SELECT * FROM run_pins WHERE tenant_id=? AND run_id=? ORDER BY name", (tenant_id, run_id)).fetchall()
        actual = {row["name"]: row["digest"] for row in rows}
        if actual != dict(expected):
            raise ContractViolation("resume package pins do not match the original run")
        result: list[CapabilityPackage] = []
        for row in rows:
            package_row = self._connection.execute("SELECT * FROM packages WHERE name=? AND version=? AND digest=?", (row["name"], row["version"], row["digest"])).fetchone()
            if package_row is None or package_row["state"] == "revoked":
                raise ContractViolation("resume package is unavailable or revoked")
            result.append(self._package(package_row))
        return tuple(result)

    def restrict_to_tenants(self, name: str, version: str, tenants: Iterable[str]) -> None:
        values = tuple(dict.fromkeys(tenants))
        if not values:
            raise ContractViolation("private package visibility requires tenants")
        for tenant_id in values:
            validate_id(tenant_id, "tenant_id")
            self._connection.execute("INSERT OR IGNORE INTO package_visibility VALUES(?,?,?)", (name, version, tenant_id))

    def record_vulnerability(self, name: str, version: str, advisory_id: str, severity: str, reason: str) -> None:
        if severity not in {"low", "medium", "high", "critical"} or not advisory_id or not reason:
            raise ContractViolation("vulnerability action is invalid")
        self._connection.execute("INSERT OR IGNORE INTO vulnerability_actions VALUES(?,?,?,?,?,?)", (name, version, advisory_id, severity, reason, utc_now()))
        if severity == "critical":
            self.revoke(name, version, f"critical vulnerability {advisory_id}: {reason}")

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


def _deterministic_zip(files: Mapping[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, strict_timestamps=True) as archive:
        for path, value in sorted(files.items()):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, value)
    return output.getvalue()
