"""Tenant isolation, secret scanning, signed provenance and revocation.

The threats this module is written against are specific:

* **cache poisoning** -- an untrusted producer trying to place a result where a
  production consumer will find it. Blocked by trust namespaces plus a
  signature that binds digest, producer, ActionKey, validation level, scope and
  time bounds together, so no field can be swapped independently.
* **cross-tenant existence leaks** -- an unauthorised digest probe returns the
  same answer whether or not the object exists.
* **secret exfiltration** -- generated output is scanned before it can reach a
  shared cache or a published tree, not after.
* **archive bombs and path escapes** -- expansion ratio, entry count and
  member paths are all bounded before extraction.
* **stale trust** -- revoking one artifact propagates to every cache entry,
  tree, checkpoint and certificate that depends on it.

Provenance signing is **Ed25519 by default**: verifiers need only the public
keyset, so a compromised cache reader cannot mint provenance. Artifact
encryption is **AES-256-GCM** with the tenant identity bound in as additional
authenticated data, so a ciphertext cannot be replayed into another tenant.
The HMAC signer is retained for offline development and is refused by policy
when ``SecurityConfig.require_asymmetric_provenance`` is set.
"""

from __future__ import annotations

import hmac
import os
import re
import secrets
import stat
import tarfile
import zipfile
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .canonical import canonical_json_bytes, digest_of, normalize_logical_path, require_digest
from .clock import SYSTEM_CLOCK, Clock
from .config import SecurityConfig
from .db import MetadataStore
from .enums import ArtifactStorageState, CacheEntryStatus, TrustNamespace, ValidationLevel
from .errors import (
    ConflictError,
    ContractViolation,
    PermissionDenied,
    ProvenanceInvalid,
    SecretDetected,
    UnsafePath,
)

SCHEMA_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# secret scanning
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class SecretFinding:
    rule: str
    path: str
    line: int
    excerpt_digest: str

    def to_dict(self) -> dict[str, Any]:
        # The matched text is never included: a finding must be reportable
        # without becoming a second copy of the secret.
        return {
            "rule": self.rule,
            "path": self.path,
            "line": self.line,
            "excerpt_digest": self.excerpt_digest,
        }


SECRET_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("aws-secret-key", re.compile(r"(?i)aws.{0,20}secret.{0,20}['\"][A-Za-z0-9/+=]{40}['\"]")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("private-key-block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("basic-auth-url", re.compile(r"\b[a-z][a-z0-9+.\-]*://[^/\s:@]{1,64}:[^/\s:@]{1,64}@")),
    ("generic-password-assignment", re.compile(
        r"(?i)\b(?:password|passwd|secret|api[_-]?key|token|credential)\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"
    )),
    ("connection-string", re.compile(r"(?i)\b(?:Password|Pwd)\s*=\s*[^;\s]{6,};")),
    ("pem-certificate-key", re.compile(r"-----BEGIN ENCRYPTED PRIVATE KEY-----")),
)

#: Patterns that look like secrets but are placeholders in generated code.
SECRET_ALLOWLIST: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(?:example|placeholder|changeme|redacted|dummy|your[_-]?\w+here|xxx+)\b"),
    re.compile(r"\$\{[^}]+\}"),
    re.compile(r"\{\{[^}]+\}\}"),
    re.compile(r"<[A-Z_]{3,}>"),
)

MAX_SCAN_BYTES = 8 * 1024 * 1024


class SecretScanner:
    def __init__(
        self,
        rules: Sequence[tuple[str, re.Pattern[str]]] = SECRET_RULES,
        allowlist: Sequence[re.Pattern[str]] = SECRET_ALLOWLIST,
        max_bytes: int = MAX_SCAN_BYTES,
    ) -> None:
        self.rules = list(rules)
        self.allowlist = list(allowlist)
        self.max_bytes = max_bytes

    def scan_text(self, text: str, path: str = "") -> list[SecretFinding]:
        findings: list[SecretFinding] = []
        for number, line in enumerate(text.splitlines(), 1):
            if any(pattern.search(line) for pattern in self.allowlist):
                continue
            for rule, pattern in self.rules:
                match = pattern.search(line)
                if match:
                    findings.append(
                        SecretFinding(
                            rule=rule,
                            path=path,
                            line=number,
                            excerpt_digest=digest_of(match.group(0)),
                        )
                    )
        return findings

    def scan_bytes(self, data: bytes, path: str = "") -> list[SecretFinding]:
        if b"\x00" in data[:8192]:
            return []
        try:
            text = data[: self.max_bytes].decode("utf-8")
        except UnicodeDecodeError:
            text = data[: self.max_bytes].decode("utf-8", errors="ignore")
        return self.scan_text(text, path)

    def scan_file(self, path: Path, logical_path: str = "") -> list[SecretFinding]:
        target = Path(path)
        if not target.is_file() or target.is_symlink():
            return []
        if target.stat().st_size > self.max_bytes:
            with target.open("rb") as handle:
                return self.scan_bytes(handle.read(self.max_bytes), logical_path or target.name)
        return self.scan_bytes(target.read_bytes(), logical_path or target.name)

    def scan_tree(self, root: Path) -> list[SecretFinding]:
        findings: list[SecretFinding] = []
        base = Path(root)
        for path in sorted(base.rglob("*")):
            if path.is_file() and not path.is_symlink():
                findings.extend(self.scan_file(path, path.relative_to(base).as_posix()))
        return findings


# --------------------------------------------------------------------------
# filesystem hardening
# --------------------------------------------------------------------------
def open_no_follow(path: Path, flags: int, mode: int = 0o600) -> int:
    """Open refusing to traverse a symlink at the final component."""
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return os.open(path, flags, mode)


def assert_no_symlinks(root: Path) -> list[str]:
    """Return offending relative paths; used before sealing or publishing."""
    offenders: list[str] = []
    base = Path(root).resolve()
    for path in sorted(base.rglob("*")):
        if path.is_symlink():
            target = Path(os.readlink(path))
            resolved = (path.parent / target).resolve()
            if base != resolved and base not in resolved.parents:
                offenders.append(path.relative_to(base).as_posix())
    return offenders


def assert_executable_policy(root: Path, allow_executable: bool) -> list[str]:
    if allow_executable:
        return []
    offenders: list[str] = []
    base = Path(root)
    for path in sorted(base.rglob("*")):
        if path.is_file() and not path.is_symlink() and path.stat().st_mode & stat.S_IXUSR:
            offenders.append(path.relative_to(base).as_posix())
    return offenders


@dataclass(frozen=True)
class ArchiveReport:
    entries: int
    declared_bytes: int
    compressed_bytes: int
    expansion_ratio: float
    rejected: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": self.entries,
            "declared_bytes": self.declared_bytes,
            "compressed_bytes": self.compressed_bytes,
            "expansion_ratio": round(self.expansion_ratio, 3),
            "rejected": list(self.rejected),
        }


def inspect_archive(path: Path, config: SecurityConfig) -> ArchiveReport:
    """Bound an archive *before* extraction: entries, ratio and member paths."""
    target = Path(path)
    compressed = target.stat().st_size or 1
    entries = 0
    declared = 0
    rejected: list[str] = []

    def check_member(name: str, size: int, is_link: bool) -> None:
        nonlocal entries, declared
        entries += 1
        declared += max(0, size)
        try:
            normalize_logical_path(name)
        except UnsafePath:
            rejected.append(name)
            return
        if is_link:
            rejected.append(name)

    if zipfile.is_zipfile(target):
        with zipfile.ZipFile(target) as zip_archive:
            for info in zip_archive.infolist():
                check_member(info.filename, info.file_size, False)
    elif tarfile.is_tarfile(target):
        with tarfile.open(target) as tar_archive:
            for member in tar_archive.getmembers():
                check_member(member.name, member.size, member.issym() or member.islnk())
    else:
        raise ContractViolation("unsupported archive format", path=str(target))

    ratio = declared / compressed
    if entries > config.max_archive_entries:
        rejected.append(f"<entry count {entries} exceeds {config.max_archive_entries}>")
    if ratio > config.max_archive_expansion_ratio:
        rejected.append(f"<expansion ratio {ratio:.1f} exceeds {config.max_archive_expansion_ratio}>")
    return ArchiveReport(entries, declared, compressed, ratio, tuple(rejected))


def safe_extract(path: Path, destination: Path, config: SecurityConfig) -> int:
    """Extract only after the archive passes :func:`inspect_archive`."""
    report = inspect_archive(path, config)
    if report.rejected:
        raise ContractViolation("archive failed safety inspection", report=report.to_dict())
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    extracted = 0
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zip_archive:
            for info in zip_archive.infolist():
                if info.is_dir():
                    continue
                relative = normalize_logical_path(info.filename)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with zip_archive.open(info) as source, target.open("wb") as sink:
                    sink.write(source.read())
                extracted += 1
    else:
        with tarfile.open(path) as tar_archive:
            for member in tar_archive.getmembers():
                if not member.isfile():
                    continue
                relative = normalize_logical_path(member.name)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                handle = tar_archive.extractfile(member)
                if handle is None:
                    continue
                with handle, target.open("wb") as sink:
                    sink.write(handle.read())
                extracted += 1
    return extracted


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Provenance:
    """A signed statement binding *all* the fields a consumer relies on."""

    subject_digest: str
    action_key: str
    producer_identity: str
    validation_level: ValidationLevel
    trust_namespace: TrustNamespace
    scope: str
    issued_at: float
    expires_at: float
    verifier_identities: tuple[str, ...] = ()
    materials: tuple[str, ...] = ()

    def statement(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "elmos.provenance/v1",
            "subject_digest": require_digest(self.subject_digest),
            "action_key": require_digest(self.action_key),
            "producer_identity": self.producer_identity,
            "validation_level": str(self.validation_level),
            "trust_namespace": str(self.trust_namespace),
            "scope": self.scope,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "verifier_identities": sorted(self.verifier_identities),
            "materials": sorted(self.materials),
        }

    def digest(self) -> str:
        return digest_of(self.statement())


@dataclass(frozen=True)
class SignedProvenance:
    provenance: Provenance
    signature: str
    key_id: str
    algorithm: str = "ed25519"

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.provenance.statement(),
            "signature": self.signature,
            "key_id": self.key_id,
            "algorithm": self.algorithm,
        }


#: Domain separator. Prevents a signature over some other ELMOS document from
#: ever being replayed as provenance.
SIGNING_CONTEXT = "elmos.provenance/v1"

#: Signers that must not be used where policy demands asymmetric provenance.
SYMMETRIC_ALGORITHMS: frozenset[str] = frozenset({"hmac-sha256"})


def signing_payload(statement: Mapping[str, Any], algorithm: str, key_id: str) -> bytes:
    """Bytes that are actually signed.

    The algorithm and key identifier are inside the signed payload, so an
    attacker cannot downgrade a statement to a weaker algorithm or re-point it
    at a key they control while keeping the signature bytes.
    """
    return canonical_json_bytes(
        {
            "context": SIGNING_CONTEXT,
            "algorithm": algorithm,
            "key_id": key_id,
            "statement": dict(statement),
        }
    )


@dataclass(frozen=True)
class SignedStatement:
    """Any canonical statement, signed by the same key material as provenance.

    Provenance signs artifacts. A cache-policy certificate and a learned model
    need the same guarantee -- this is who produced it, and it has not been
    edited since -- over a different payload, so the signer exposes a generic
    form rather than growing a second key hierarchy.
    """

    kind: str
    statement: dict[str, Any]
    signature: str
    key_id: str
    algorithm: str

    def payload(self) -> dict[str, Any]:
        return {"kind": self.kind, "statement": self.statement}

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "statement": self.statement,
            "signature": self.signature,
            "key_id": self.key_id,
            "algorithm": self.algorithm,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SignedStatement:
        return cls(
            kind=str(value["kind"]),
            statement=dict(value["statement"]),
            signature=str(value["signature"]),
            key_id=str(value["key_id"]),
            algorithm=str(value["algorithm"]),
        )


class ProvenanceSigner(ABC):
    """Signing contract. Implementations differ only in the primitive."""

    algorithm: str = "abstract"

    @property
    @abstractmethod
    def active_key_id(self) -> str: ...

    @abstractmethod
    def sign(self, provenance: Provenance) -> SignedProvenance: ...

    @abstractmethod
    def verify(self, signed: SignedProvenance, now: float) -> None: ...

    @abstractmethod
    def _sign_payload(self, payload: bytes) -> str: ...

    @abstractmethod
    def _verify_payload(self, payload: bytes, signature: str, key_id: str) -> None: ...

    def sign_statement(self, kind: str, statement: Mapping[str, Any]) -> SignedStatement:
        """Sign an arbitrary canonical statement under the active key."""
        key_id = self.active_key_id
        body = {"kind": kind, "statement": dict(statement)}
        payload = signing_payload(body, self.algorithm, key_id)
        return SignedStatement(kind, dict(statement), self._sign_payload(payload), key_id, self.algorithm)

    def verify_statement(self, signed: SignedStatement) -> None:
        """Reject a statement whose algorithm, key or bytes do not check out."""
        if signed.algorithm != self.algorithm:
            raise ProvenanceInvalid(
                "algorithm mismatch; refusing to verify",
                expected=self.algorithm,
                found=signed.algorithm,
            )
        payload = signing_payload(signed.payload(), signed.algorithm, signed.key_id)
        self._verify_payload(payload, signed.signature, signed.key_id)

    @property
    def asymmetric(self) -> bool:
        return self.algorithm not in SYMMETRIC_ALGORITHMS

    def _check_time_bounds(self, signed: SignedProvenance, now: float) -> None:
        if now >= signed.provenance.expires_at:
            raise ProvenanceInvalid(
                "provenance has expired", expires_at=signed.provenance.expires_at, now=now
            )
        if now < signed.provenance.issued_at - 300:
            raise ProvenanceInvalid("provenance is not yet valid; check for clock skew")


class Ed25519ProvenanceSigner(ProvenanceSigner):
    """Asymmetric provenance signing.

    A verifier is constructed from public keys alone (:meth:`verifier`), so the
    party that checks a cache entry never holds the material needed to forge
    one. Rotation adds a new active private key while old public keys stay in
    the set, which is what lets already-issued provenance keep verifying.
    """

    algorithm = "ed25519"

    def __init__(
        self,
        private_keys: Mapping[str, Ed25519PrivateKey | bytes] | None = None,
        active_key_id: str | None = None,
        public_keys: Mapping[str, Ed25519PublicKey | bytes] | None = None,
    ) -> None:
        self._private: dict[str, Ed25519PrivateKey] = {
            key_id: _as_private(value) for key_id, value in (private_keys or {}).items()
        }
        self._public: dict[str, Ed25519PublicKey] = {
            key_id: _as_public(value) for key_id, value in (public_keys or {}).items()
        }
        for key_id, private in self._private.items():
            self._public.setdefault(key_id, private.public_key())
        if active_key_id is not None and active_key_id not in self._private:
            raise ContractViolation("active signing key is not in the key set", key_id=active_key_id)
        self._active = active_key_id

    # -- construction -----------------------------------------------------
    @classmethod
    def generate(cls, key_id: str = "elmos-provenance-1") -> Ed25519ProvenanceSigner:
        return cls({key_id: Ed25519PrivateKey.generate()}, key_id)

    @classmethod
    def verifier(cls, public_keys: Mapping[str, Ed25519PublicKey | bytes]) -> Ed25519ProvenanceSigner:
        """A verify-only signer. ``sign`` raises."""
        return cls(private_keys=None, active_key_id=None, public_keys=public_keys)

    def rotate(self, key_id: str, private_key: Ed25519PrivateKey | bytes | None = None) -> str:
        """Add and activate a new key; previous public keys keep verifying."""
        material = _as_private(private_key) if private_key is not None else Ed25519PrivateKey.generate()
        self._private[key_id] = material
        self._public[key_id] = material.public_key()
        self._active = key_id
        return key_id

    def public_keyset(self) -> dict[str, bytes]:
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        return {
            key_id: key.public_bytes(Encoding.Raw, PublicFormat.Raw)
            for key_id, key in sorted(self._public.items())
        }

    # -- contract ---------------------------------------------------------
    @property
    def active_key_id(self) -> str:
        if self._active is None:
            raise ContractViolation("this signer is verify-only and has no active key")
        return self._active

    def sign(self, provenance: Provenance) -> SignedProvenance:
        key_id = self.active_key_id
        payload = signing_payload(provenance.statement(), self.algorithm, key_id)
        signature = self._private[key_id].sign(payload)
        return SignedProvenance(provenance, signature.hex(), key_id, self.algorithm)

    def verify(self, signed: SignedProvenance, now: float) -> None:
        if signed.algorithm != self.algorithm:
            raise ProvenanceInvalid(
                "algorithm mismatch; refusing to verify",
                expected=self.algorithm,
                found=signed.algorithm,
            )
        payload = signing_payload(signed.provenance.statement(), signed.algorithm, signed.key_id)
        self._verify_payload(payload, signed.signature, signed.key_id)
        self._check_time_bounds(signed, now)

    def _sign_payload(self, payload: bytes) -> str:
        return self._private[self.active_key_id].sign(payload).hex()

    def _verify_payload(self, payload: bytes, signature: str, key_id: str) -> None:
        public = self._public.get(key_id)
        if public is None:
            raise ProvenanceInvalid("unknown signing key", key_id=key_id)
        try:
            public.verify(bytes.fromhex(signature), payload)
        except (InvalidSignature, ValueError) as exc:
            raise ProvenanceInvalid("signature does not verify") from exc


class HmacProvenanceSigner(ProvenanceSigner):
    """Shared-secret signer for offline development.

    Every verifier necessarily holds forging material, so this is refused when
    ``SecurityConfig.require_asymmetric_provenance`` is set. It exists so an
    air-gapped or bootstrap environment can still exercise the full contract.
    """

    algorithm = "hmac-sha256"

    def __init__(self, keys: Mapping[str, bytes], active_key_id: str) -> None:
        if active_key_id not in keys:
            raise ContractViolation("active signing key is not in the key set", key_id=active_key_id)
        self._keys = dict(keys)
        self._active = active_key_id

    @property
    def active_key_id(self) -> str:
        return self._active

    def sign(self, provenance: Provenance) -> SignedProvenance:
        payload = signing_payload(provenance.statement(), self.algorithm, self._active)
        signature = hmac.new(self._keys[self._active], payload, sha256).hexdigest()
        return SignedProvenance(provenance, signature, self._active, self.algorithm)

    def verify(self, signed: SignedProvenance, now: float) -> None:
        if signed.algorithm != self.algorithm:
            raise ProvenanceInvalid(
                "algorithm mismatch; refusing to verify",
                expected=self.algorithm,
                found=signed.algorithm,
            )
        payload = signing_payload(signed.provenance.statement(), signed.algorithm, signed.key_id)
        self._verify_payload(payload, signed.signature, signed.key_id)
        self._check_time_bounds(signed, now)

    def _sign_payload(self, payload: bytes) -> str:
        return hmac.new(self._keys[self._active], payload, sha256).hexdigest()

    def _verify_payload(self, payload: bytes, signature: str, key_id: str) -> None:
        key = self._keys.get(key_id)
        if key is None:
            raise ProvenanceInvalid("unknown signing key", key_id=key_id)
        expected = hmac.new(key, payload, sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ProvenanceInvalid("signature does not verify")


def require_asymmetric(signer: ProvenanceSigner, config: SecurityConfig | None = None) -> ProvenanceSigner:
    """Enforce the deployment's provenance policy at wiring time."""
    policy = config or SecurityConfig()
    if policy.require_asymmetric_provenance and not signer.asymmetric:
        raise ProvenanceInvalid(
            "policy requires asymmetric provenance signing",
            algorithm=signer.algorithm,
        )
    return signer


def _as_private(value: Ed25519PrivateKey | bytes) -> Ed25519PrivateKey:
    if isinstance(value, Ed25519PrivateKey):
        return value
    return Ed25519PrivateKey.from_private_bytes(bytes(value))


def _as_public(value: Ed25519PublicKey | bytes) -> Ed25519PublicKey:
    if isinstance(value, Ed25519PublicKey):
        return value
    return Ed25519PublicKey.from_public_bytes(bytes(value))


# --------------------------------------------------------------------------
# authorization
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Principal:
    identity: str
    tenant_id: str
    trust_namespace: TrustNamespace = TrustNamespace.BRANCH
    can_write: bool = True
    can_publish: bool = False
    can_gc: bool = False


class AccessController:
    """Authorises metadata *and* blob access, not only the API entry point."""

    def __init__(self, store: MetadataStore, config: SecurityConfig | None = None) -> None:
        self.store = store
        self.config = config or SecurityConfig()
        self.audit: list[dict[str, Any]] = []

    def _record(self, principal: Principal, action: str, subject: str, allowed: bool) -> None:
        self.audit.append(
            {
                "identity": principal.identity,
                "tenant_id": principal.tenant_id,
                "action": action,
                "subject_digest": subject,
                "allowed": allowed,
            }
        )

    def authorize_read(self, principal: Principal, tenant_id: str, digest: str) -> None:
        """A cross-tenant probe is denied identically whether or not it exists."""
        allowed = not self.config.tenant_isolation or principal.tenant_id == tenant_id
        self._record(principal, "read", digest, allowed)
        if not allowed:
            raise PermissionDenied("artifact is not accessible", digest=digest)

    def authorize_write(self, principal: Principal, tenant_id: str, digest: str) -> None:
        allowed = principal.can_write and (
            not self.config.tenant_isolation or principal.tenant_id == tenant_id
        )
        self._record(principal, "write", digest, allowed)
        if not allowed:
            raise PermissionDenied("write is not permitted", digest=digest)

    def authorize_publish(self, principal: Principal, tree_digest: str) -> None:
        allowed = principal.can_publish and principal.trust_namespace.satisfies(TrustNamespace.BRANCH)
        self._record(principal, "publish", tree_digest, allowed)
        if not allowed:
            raise PermissionDenied("publication is not permitted", tree_digest=tree_digest)

    def authorize_destructive(self, principal: Principal, subject: str) -> None:
        self._record(principal, "destructive", subject, principal.can_gc)
        if not principal.can_gc:
            raise PermissionDenied("destructive operations are not permitted", subject=subject)

    def check_promotion(
        self,
        principal: Principal,
        requested_level: ValidationLevel,
        producer_identity: str,
    ) -> None:
        """An untrusted producer cannot elevate its own validation level."""
        if not principal.trust_namespace.satisfies(TrustNamespace.BRANCH) and requested_level.rank > (
            ValidationLevel.UNVERIFIED.rank
        ):
            raise PermissionDenied(
                "untrusted producers cannot claim a validation level",
                trust_namespace=str(principal.trust_namespace),
                requested=str(requested_level),
            )
        if principal.identity == producer_identity and requested_level.rank >= (
            ValidationLevel.TEST_VERIFIED.rank
        ):
            raise ProvenanceInvalid(
                "producer-only evidence cannot raise validation to TEST_VERIFIED or above",
                producer=producer_identity,
            )


# --------------------------------------------------------------------------
# revocation
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class RevocationEffect:
    action_entries: tuple[str, ...]
    trees: tuple[str, ...]
    checkpoints: tuple[str, ...]
    certificates: tuple[str, ...]
    artifacts: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_entries": list(self.action_entries),
            "trees": list(self.trees),
            "checkpoints": list(self.checkpoints),
            "certificates": list(self.certificates),
            "artifacts": list(self.artifacts),
        }


class RevocationService:
    """Revoking one artifact must reach everything that depends on it."""

    def __init__(self, store: MetadataStore, clock: Clock = SYSTEM_CLOCK) -> None:
        self.store = store
        self.clock = clock

    def revoke_artifact(self, tenant_id: str, digest: str, reason: str) -> RevocationEffect:
        from dataclasses import replace as _replace

        self.store.add_revocation(tenant_id, "artifact", digest, reason)
        self.store.set_artifact_state(tenant_id, digest, ArtifactStorageState.QUARANTINED)

        reachable = self._reverse_closure(tenant_id, digest)
        action_entries: list[str] = []
        for entry in self.store.list_action_entries(tenant_id):
            if entry.result_manifest_digest == digest or entry.result_manifest_digest in reachable:
                self.store.update_action_entry(
                    _replace(entry, status=CacheEntryStatus.REVOKED, quarantine_reason=reason)
                )
                action_entries.append(entry.action_key)
                self.store.add_revocation(tenant_id, "action_key", entry.action_key, reason)

        trees: list[str] = []
        for tree_digest in self.store.published_trees(tenant_id):
            targets = set(self.store.artifact_targets(tenant_id, "file_tree", tree_digest))
            if digest in targets or targets & reachable:
                trees.append(tree_digest)
                self.store.add_revocation(tenant_id, "tree", tree_digest, reason)

        checkpoints: list[str] = []
        certificates: list[str] = []
        for kind, source_id, _ in self.store.artifact_referrers(tenant_id, digest):
            if kind == "checkpoint":
                from .enums import CheckpointStatus

                self.store.set_checkpoint_status(source_id, CheckpointStatus.QUARANTINED)
                checkpoints.append(source_id)
        for tree_digest in trees:
            for certificate_id in self.store.certificates_for_tree(tenant_id, tree_digest):
                self.store.set_certificate_status(certificate_id, "REVOKED")
                certificates.append(certificate_id)

        return RevocationEffect(
            action_entries=tuple(sorted(set(action_entries))),
            trees=tuple(sorted(set(trees))),
            checkpoints=tuple(sorted(set(checkpoints))),
            certificates=tuple(sorted(set(certificates))),
            artifacts=tuple(sorted({digest, *reachable})),
        )

    def _reverse_closure(self, tenant_id: str, digest: str) -> set[str]:
        """Artifacts that transitively contain or reference the revoked one."""
        seen: set[str] = set()
        frontier = [digest]
        while frontier:
            current = frontier.pop()
            for kind, source_id, _ in self.store.artifact_referrers(tenant_id, current):
                if kind in ("action_result", "file_tree", "checkpoint") and source_id not in seen:
                    seen.add(source_id)
                    frontier.append(source_id)
        return seen

    def is_revoked(self, tenant_id: str, kind: str, subject: str) -> bool:
        return self.store.is_revoked(tenant_id, kind, subject)


# --------------------------------------------------------------------------
# encryption at rest (envelope)
# --------------------------------------------------------------------------
ENVELOPE_VERSION = 1
NONCE_BYTES = 12
KEY_BYTES = 32


class EnvelopeCipher:
    """AES-256-GCM envelope encryption with per-tenant key separation.

    The tenant identifier, the key identifier and the format version are bound
    in as additional authenticated data, so a ciphertext produced for one
    tenant cannot be decrypted -- or even accepted -- under another, and the
    header cannot be edited without breaking the tag.

    Key rotation: ``rotate`` installs a new active key for a tenant while the
    previous keys stay available for decryption, so existing ciphertexts remain
    readable without a re-encryption sweep.
    """

    def __init__(
        self,
        tenant_keys: Mapping[str, bytes | Mapping[str, bytes]],
        active_key_ids: Mapping[str, str] | None = None,
    ) -> None:
        self._keys: dict[str, dict[str, bytes]] = {}
        self._active: dict[str, str] = {}
        for tenant_id, material in tenant_keys.items():
            if isinstance(material, Mapping):
                keyset = {key_id: _as_aes_key(value) for key_id, value in material.items()}
                self._keys[tenant_id] = keyset
                self._active[tenant_id] = (active_key_ids or {}).get(tenant_id, sorted(keyset)[0])
            else:
                key_id = (active_key_ids or {}).get(tenant_id, "k1")
                self._keys[tenant_id] = {key_id: _as_aes_key(material)}
                self._active[tenant_id] = key_id

    @staticmethod
    def generate_key() -> bytes:
        return secrets.token_bytes(KEY_BYTES)

    def rotate(self, tenant_id: str, key_id: str, key: bytes | None = None) -> str:
        material = _as_aes_key(key) if key is not None else self.generate_key()
        self._keys.setdefault(tenant_id, {})[key_id] = material
        self._active[tenant_id] = key_id
        return key_id

    def _aad(self, tenant_id: str, key_id: str) -> bytes:
        return canonical_json_bytes(
            {"version": ENVELOPE_VERSION, "tenant_id": tenant_id, "key_id": key_id}
        )

    def encrypt(self, tenant_id: str, data: bytes) -> bytes:
        keyset = self._keys.get(tenant_id)
        if not keyset:
            raise PermissionDenied("no encryption key for tenant", tenant_id=tenant_id)
        key_id = self._active[tenant_id]
        nonce = secrets.token_bytes(NONCE_BYTES)
        body = AESGCM(keyset[key_id]).encrypt(nonce, data, self._aad(tenant_id, key_id))
        header = bytes([ENVELOPE_VERSION, len(key_id.encode("utf-8"))]) + key_id.encode("utf-8")
        return header + nonce + body

    def decrypt(self, tenant_id: str, blob: bytes) -> bytes:
        keyset = self._keys.get(tenant_id)
        if not keyset:
            raise PermissionDenied("no encryption key for tenant", tenant_id=tenant_id)
        if len(blob) < 2:
            raise ConflictError("ciphertext is truncated")
        version, key_id_length = blob[0], blob[1]
        if version != ENVELOPE_VERSION:
            raise ConflictError("unsupported envelope version", version=version)
        offset = 2 + key_id_length
        if len(blob) < offset + NONCE_BYTES + 16:
            raise ConflictError("ciphertext is truncated")
        key_id = blob[2:offset].decode("utf-8", errors="replace")
        nonce = blob[offset : offset + NONCE_BYTES]
        body = blob[offset + NONCE_BYTES :]
        key = keyset.get(key_id)
        if key is None:
            raise PermissionDenied("unknown encryption key for tenant", tenant_id=tenant_id, key_id=key_id)
        try:
            return AESGCM(key).decrypt(nonce, body, self._aad(tenant_id, key_id))
        except InvalidTag as exc:
            raise ProvenanceInvalid("ciphertext failed authentication") from exc

    def key_ids(self, tenant_id: str) -> tuple[str, ...]:
        return tuple(sorted(self._keys.get(tenant_id, {})))


def _as_aes_key(value: bytes) -> bytes:
    material = bytes(value)
    if len(material) != KEY_BYTES:
        # Derive a fixed-length key so callers may pass a passphrase, while the
        # cipher itself always operates on a full-strength 256-bit key.
        material = sha256(material).digest()
    return material


# --------------------------------------------------------------------------
# facade
# --------------------------------------------------------------------------
@dataclass
class SecurityGate:
    """One place the pipeline calls before uploading or publishing."""

    scanner: SecretScanner = field(default_factory=SecretScanner)
    config: SecurityConfig = field(default_factory=SecurityConfig)

    def check_before_remote_upload(self, root: Path) -> list[SecretFinding]:
        if not self.config.scan_secrets_before_remote_upload:
            return []
        findings = self.scanner.scan_tree(root)
        if findings:
            raise SecretDetected(
                "secret material blocked from the shared cache",
                findings=[finding.to_dict() for finding in findings][:20],
            )
        return findings

    def check_before_publish(self, root: Path) -> dict[str, Any]:
        report: dict[str, Any] = {}
        if self.config.reject_symlink_escape:
            escapes = assert_no_symlinks(root)
            if escapes:
                raise UnsafePath("publish candidate contains escaping symlinks", paths=escapes[:20])
            report["symlink_escapes"] = []
        offenders = assert_executable_policy(root, self.config.allow_executable_output)
        if offenders:
            raise ContractViolation("executable output is not permitted", paths=offenders[:20])
        if self.config.scan_secrets_before_publish:
            findings = self.scanner.scan_tree(root)
            if findings:
                raise SecretDetected(
                    "secret material blocked from publication",
                    findings=[finding.to_dict() for finding in findings][:20],
                )
            report["secret_findings"] = 0
        return report


def audit_summary(controller: AccessController) -> dict[str, Any]:
    denied = [event for event in controller.audit if not event["allowed"]]
    return {
        "events": len(controller.audit),
        "denied": len(denied),
        "denied_actions": sorted({event["action"] for event in denied}),
    }


def redact(values: Mapping[str, Any], sensitive: Iterable[str] = ()) -> dict[str, Any]:
    """Strip anything that must not reach telemetry."""
    blocked = {name.lower() for name in sensitive} | {
        "password", "secret", "token", "api_key", "authorization", "prompt", "source", "code",
    }
    out: dict[str, Any] = {}
    for key, value in sorted(values.items()):
        if any(marker in key.lower() for marker in blocked):
            out[key] = "<redacted>"
        elif isinstance(value, dict):
            out[key] = redact(value, sensitive)
        else:
            out[key] = value
    return out
