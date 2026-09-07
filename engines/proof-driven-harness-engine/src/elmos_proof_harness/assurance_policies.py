"""Host-owned policies for the v3.1 runtime-assurance boundary.

The delta runtime consumes these objects as trusted configuration.  Repository
payloads cannot add roots, publishers, privileged paths, or checkout identity.
All policies are immutable after construction and fail closed on ambiguity.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path, PurePosixPath
import stat
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .canonical import canonical_json_bytes, freeze_json
from .errors import IntegrityError, ValidationError


_TRUST_DOMAINS = frozenset(
    {"USER", "ENTERPRISE", "MARKETPLACE", "REPOSITORY", "EPHEMERAL"}
)
_PRIVILEGED_KINDS = frozenset(
    {"FILESYSTEM", "SANDBOX", "SECRET", "EXECUTOR", "EMITTER"}
)


def _text(value: Any, field: str, *, maximum: int = 2048) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise ValidationError(f"{field} is invalid", details={"field": field})
    return value


def _canonical_absolute_path(value: Any, field: str) -> str:
    candidate = _text(value, field)
    parsed = PurePosixPath(candidate)
    if not parsed.is_absolute() or ".." in parsed.parts or "\\" in candidate:
        raise ValidationError(
            f"{field} must be a canonical absolute POSIX path",
            details={"field": field},
        )
    normalized = parsed.as_posix()
    if normalized != candidate:
        raise ValidationError(f"{field} is not canonical", details={"field": field})
    return normalized


def _sha256(value: Any, field: str) -> str:
    candidate = _text(value, field, maximum=71)
    if (
        len(candidate) != 71
        or not candidate.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in candidate[7:])
    ):
        raise ValidationError(f"{field} must be a canonical sha256 digest")
    return candidate


def _read_regular_nofollow(path: Path, *, limit: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValidationError("trusted policy file cannot be opened safely") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise ValidationError("trusted policy file is not a bounded regular file")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 8192))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > limit:
            raise ValidationError("trusted policy file exceeds its byte limit")
        return content
    finally:
        os.close(descriptor)


class HostSecurityContextSigner:
    """Deterministic, restart-safe signer for host-minted security contexts."""

    trusted_for_production = True

    def __init__(self, key: bytes, *, key_id: str, issuer: str) -> None:
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError(
                "security-context signing key must contain at least 32 bytes"
            )
        self._key = bytes(key)
        self.key_id = _text(key_id, "key_id", maximum=128)
        self.issuer = _text(issuer, "issuer", maximum=255)

    def _payload(self, value: Mapping[str, Any]) -> bytes:
        if not isinstance(value, Mapping):
            raise ValidationError("security-context signing payload must be an object")
        return canonical_json_bytes(
            {
                "domain": "elmos.host-minted-security-context.v2",
                "keyId": self.key_id,
                "issuer": self.issuer,
                "context": freeze_json(value),
            }
        )

    def sign(self, value: Mapping[str, Any]) -> str:
        digest = hmac.new(self._key, self._payload(value), hashlib.sha256).hexdigest()
        return f"hmac-sha256:{self.key_id}:{digest}"

    def verify(self, value: Mapping[str, Any], signature: str) -> bool:
        candidate = _text(signature, "security context signature", maximum=512)
        parts = candidate.split(":", 2)
        if len(parts) != 3 or parts[0] != "hmac-sha256":
            return False
        if not hmac.compare_digest(parts[1], self.key_id):
            return False
        expected = self.sign(value)
        return hmac.compare_digest(expected, candidate)


@dataclass(frozen=True, slots=True)
class PrivilegedPathContract:
    path: str
    kind: str
    remote: bool = False
    mutable: bool = False
    allowed_arguments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _canonical_absolute_path(self.path, "path"))
        if self.kind not in _PRIVILEGED_KINDS:
            raise ValidationError("privileged path kind is unsupported")
        if not isinstance(self.remote, bool) or not isinstance(self.mutable, bool):
            raise ValidationError("privileged path flags must be boolean")
        arguments = tuple(
            _text(item, "allowed privileged argument", maximum=512)
            for item in self.allowed_arguments
        )
        if len(arguments) != len(set(arguments)) or len(arguments) > 128:
            raise ValidationError("allowed privileged arguments are invalid")
        object.__setattr__(self, "allowed_arguments", arguments)

    def to_wire(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "remote": self.remote,
            "mutable": self.mutable,
            "allowedArguments": list(self.allowed_arguments),
        }


class PrivilegedPathPolicy:
    """Default-deny validation of argument-bearing privileged resources."""

    trusted_for_production = True

    def __init__(self, contracts: Iterable[PrivilegedPathContract] = ()) -> None:
        checked: dict[str, PrivilegedPathContract] = {}
        for contract in contracts:
            if not isinstance(contract, PrivilegedPathContract):
                raise TypeError("privileged path contracts must be typed")
            if contract.path in checked:
                raise ValueError("privileged path contract is duplicated")
            checked[contract.path] = contract
        self._contracts = MappingProxyType(checked)

    def validate_entitlements(self, entitlements: Mapping[str, Any]) -> None:
        if not isinstance(entitlements, Mapping):
            raise ValidationError("entitlements must be an object")
        raw_paths = entitlements.get("privilegedPaths", ())
        if raw_paths in (None, ()):
            return
        if not isinstance(raw_paths, (list, tuple)) or len(raw_paths) > 128:
            raise ValidationError("privilegedPaths must be a bounded array")
        seen: set[str] = set()
        for raw in raw_paths:
            if not isinstance(raw, Mapping) or set(raw) != {
                "path",
                "kind",
                "remote",
                "mutable",
                "arguments",
            }:
                raise ValidationError(
                    "privileged path request has an unsupported shape"
                )
            path = _canonical_absolute_path(raw.get("path"), "privileged path")
            if path in seen:
                raise ValidationError("privileged path request is duplicated")
            seen.add(path)
            contract = self._contracts.get(path)
            if contract is None:
                raise ValidationError("privileged path is not declared by the Host")
            kind = _text(raw.get("kind"), "privileged path kind", maximum=64)
            remote = raw.get("remote")
            mutable = raw.get("mutable")
            arguments = raw.get("arguments")
            if not isinstance(remote, bool) or not isinstance(mutable, bool):
                raise ValidationError("privileged path flags must be boolean")
            if not isinstance(arguments, (list, tuple)) or len(arguments) > 128:
                raise ValidationError("privileged path arguments are invalid")
            requested_arguments = tuple(
                _text(item, "privileged path argument", maximum=512)
                for item in arguments
            )
            if len(requested_arguments) != len(set(requested_arguments)):
                raise ValidationError("privileged path arguments contain duplicates")
            if (
                kind != contract.kind
                or remote != contract.remote
                or mutable != contract.mutable
                or not set(requested_arguments) <= set(contract.allowed_arguments)
            ):
                raise ValidationError(
                    "privileged path request exceeds the Host contract"
                )


class SkillTrustDomainPolicy:
    """Bind each Skill trust domain to an exact root and publisher inventory."""

    trusted_for_production = True

    def __init__(
        self,
        roots: Mapping[str, Path],
        *,
        publishers: Mapping[str, Iterable[str]],
    ) -> None:
        checked_roots: dict[str, Path] = {}
        checked_publishers: dict[str, frozenset[str]] = {}
        if not roots:
            raise ValueError("at least one Skill trust-domain root is required")
        for domain, root in roots.items():
            if domain not in _TRUST_DOMAINS:
                raise ValueError("Skill trust domain is unsupported")
            supplied = Path(root)
            if supplied.is_symlink():
                raise ValueError("Skill trust-domain root must be a real directory")
            candidate = supplied.resolve(strict=True)
            if not candidate.is_dir():
                raise ValueError("Skill trust-domain root must be a real directory")
            checked_roots[domain] = candidate
        for domain, values in publishers.items():
            if domain not in checked_roots:
                raise ValueError("publisher inventory lacks a matching trust root")
            allowed = frozenset(
                _text(item, "trusted Skill publisher", maximum=255) for item in values
            )
            if not allowed:
                raise ValueError("trusted Skill publisher inventory cannot be empty")
            checked_publishers[domain] = allowed
        if set(checked_roots) != set(checked_publishers):
            raise ValueError("every Skill trust root requires a publisher inventory")
        self._roots = MappingProxyType(checked_roots)
        self._publishers = MappingProxyType(checked_publishers)

    def authorize(self, *, domain: str, publisher: str) -> Path:
        if domain not in self._roots:
            raise ValidationError("Skill trust domain is not configured")
        candidate = _text(publisher, "Skill publisher", maximum=255)
        if candidate not in self._publishers[domain]:
            raise ValidationError("Skill publisher is not trusted for this domain")
        return self._roots[domain]

    @staticmethod
    def signature_envelope(
        *,
        skill_id: str,
        publisher: str,
        origin: str,
        canonical_uri: str,
        package_digest: str,
        trust_domain: str,
        install_scope: str,
        authorization_semantics: Iterable[str],
    ) -> bytes:
        return canonical_json_bytes(
            {
                "domain": "elmos.skill-trust-provenance.v1",
                "skillId": _text(skill_id, "skill_id"),
                "publisher": _text(publisher, "publisher"),
                "origin": _text(origin, "origin"),
                "canonicalUri": _text(canonical_uri, "canonical_uri"),
                "packageDigest": _sha256(package_digest, "package_digest"),
                "trustDomain": _text(trust_domain, "trust_domain"),
                "installScope": _text(install_scope, "install_scope"),
                "authorizationSemantics": sorted(
                    _text(item, "authorization semantic")
                    for item in authorization_semantics
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class ManagedWorktreeIdentity:
    workspace_id: str
    repository_id: str
    base_revision: str
    checkout_path: Path
    git_dir: Path
    device: int
    inode: int

    def __post_init__(self) -> None:
        _text(self.workspace_id, "workspace_id", maximum=512)
        _text(self.repository_id, "repository_id", maximum=512)
        revision = _text(self.base_revision, "base_revision", maximum=64)
        if len(revision) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in revision
        ):
            raise ValidationError(
                "managed worktree base_revision must be an exact Git object id"
            )
        if self.device < 0 or self.inode < 1:
            raise ValidationError("managed worktree inode identity is invalid")


class ManagedWorktreeRegistry:
    """Live, no-symlink registry for linked Git worktrees (never primaries)."""

    trusted_for_production = True

    def __init__(self, identities: Iterable[ManagedWorktreeIdentity] = ()) -> None:
        checked: dict[str, ManagedWorktreeIdentity] = {}
        paths: list[Path] = []
        for identity in identities:
            if not isinstance(identity, ManagedWorktreeIdentity):
                raise TypeError("managed worktree identity must be typed")
            self.verify(identity)
            if identity.workspace_id in checked:
                raise ValueError("managed worktree identity is duplicated")
            path = identity.checkout_path.resolve(strict=True)
            if any(
                path == prior
                or path.is_relative_to(prior)
                or prior.is_relative_to(path)
                for prior in paths
            ):
                raise ValueError("nested or duplicate managed worktrees are forbidden")
            checked[identity.workspace_id] = identity
            paths.append(path)
        self._identities = MappingProxyType(checked)

    @staticmethod
    def discover(
        *,
        workspace_id: str,
        repository_id: str,
        base_revision: str,
        checkout_path: Path,
    ) -> ManagedWorktreeIdentity:
        supplied = Path(checkout_path)
        metadata = os.lstat(supplied)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ValidationError("workspace checkout must be a real directory")
        resolved = supplied.resolve(strict=True)
        marker = resolved / ".git"
        marker_metadata = os.lstat(marker)
        if stat.S_ISDIR(marker_metadata.st_mode):
            raise ValidationError(
                "primary Git checkout cannot receive a workspace lease"
            )
        if not stat.S_ISREG(marker_metadata.st_mode) or stat.S_ISLNK(
            marker_metadata.st_mode
        ):
            raise ValidationError("workspace is not a registered linked Git worktree")
        marker_bytes = _read_regular_nofollow(marker, limit=8192)
        if len(marker_bytes) > 8192 or b"\x00" in marker_bytes:
            raise ValidationError("linked worktree .git pointer is invalid")
        try:
            marker_text = marker_bytes.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise ValidationError("linked worktree .git pointer is not UTF-8") from exc
        prefix = "gitdir: "
        if not marker_text.startswith(prefix):
            raise ValidationError("linked worktree .git pointer is invalid")
        raw_git_dir = Path(marker_text.removeprefix(prefix))
        if not raw_git_dir.is_absolute():
            raw_git_dir = resolved / raw_git_dir
        raw_git_metadata = os.lstat(raw_git_dir)
        if stat.S_ISLNK(raw_git_metadata.st_mode):
            raise ValidationError("workspace Git directory cannot be a symlink")
        git_dir = raw_git_dir.resolve(strict=True)
        if (
            not git_dir.is_dir()
            or git_dir.is_symlink()
            or git_dir.parent.name != "worktrees"
        ):
            raise ValidationError("workspace .git pointer is not a managed worktree")
        resolved_metadata = os.stat(resolved, follow_symlinks=False)
        if (metadata.st_dev, metadata.st_ino) != (
            resolved_metadata.st_dev,
            resolved_metadata.st_ino,
        ):
            raise IntegrityError(
                "workspace checkout changed during discovery",
                code="WORKSPACE_IDENTITY_TOCTOU",
            )
        return ManagedWorktreeIdentity(
            _text(workspace_id, "workspace_id", maximum=512),
            _text(repository_id, "repository_id", maximum=512),
            _text(base_revision, "base_revision", maximum=512),
            resolved,
            git_dir,
            metadata.st_dev,
            metadata.st_ino,
        )

    @staticmethod
    def verify(identity: ManagedWorktreeIdentity) -> None:
        try:
            current = os.stat(identity.checkout_path, follow_symlinks=False)
        except OSError as exc:
            raise IntegrityError(
                "managed worktree checkout is unavailable",
                code="WORKSPACE_IDENTITY_DRIFT",
            ) from exc
        if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (
            identity.device,
            identity.inode,
        ):
            raise IntegrityError(
                "managed worktree inode identity drifted",
                code="WORKSPACE_IDENTITY_DRIFT",
            )
        marker = identity.checkout_path / ".git"
        try:
            marker_is_symlink = marker.is_symlink()
            marker_is_file = marker.is_file()
        except OSError as exc:
            raise IntegrityError(
                "managed worktree .git pointer is unavailable",
                code="WORKSPACE_IDENTITY_DRIFT",
            ) from exc
        if marker_is_symlink or not marker_is_file:
            raise IntegrityError(
                "managed worktree .git pointer drifted",
                code="WORKSPACE_IDENTITY_DRIFT",
            )
        try:
            marker_text = (
                _read_regular_nofollow(marker, limit=8192).decode("utf-8").strip()
            )
        except (ValidationError, UnicodeError) as exc:
            raise IntegrityError(
                "managed worktree .git pointer is unreadable",
                code="WORKSPACE_IDENTITY_DRIFT",
            ) from exc
        if not marker_text.startswith("gitdir: "):
            raise IntegrityError(
                "managed worktree .git pointer drifted",
                code="WORKSPACE_IDENTITY_DRIFT",
            )
        raw_git_dir = Path(marker_text.removeprefix("gitdir: "))
        if not raw_git_dir.is_absolute():
            raw_git_dir = identity.checkout_path / raw_git_dir
        try:
            resolved_git_dir = raw_git_dir.resolve(strict=True)
        except OSError as exc:
            raise IntegrityError(
                "managed worktree Git directory is unavailable",
                code="WORKSPACE_IDENTITY_DRIFT",
            ) from exc
        if resolved_git_dir != identity.git_dir:
            raise IntegrityError(
                "managed worktree Git directory drifted",
                code="WORKSPACE_IDENTITY_DRIFT",
            )

    def require(self, workspace_id: str) -> ManagedWorktreeIdentity:
        identity = self._identities.get(
            _text(workspace_id, "workspace_id", maximum=512)
        )
        if identity is None:
            raise ValidationError("workspace is not registered by the Host")
        self.verify(identity)
        return identity


__all__ = [
    "HostSecurityContextSigner",
    "ManagedWorktreeIdentity",
    "ManagedWorktreeRegistry",
    "PrivilegedPathContract",
    "PrivilegedPathPolicy",
    "SkillTrustDomainPolicy",
]
