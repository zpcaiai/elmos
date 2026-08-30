"""Strict request, authority, and canonical JSON contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import time
from typing import Any, Mapping


class ContractError(ValueError):
    """A caller-controlled value failed a fail-closed contract."""


class AuthorityError(ContractError):
    """A request did not match host-minted execution authority."""


class IdempotencyConflict(ContractError):
    """An idempotency key was reused with different canonical input."""


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,199}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_REQUEST_INPUT_BYTES = 8 * 1024 * 1024
_REQUEST_KEYS = frozenset(
    {
        "schema_version",
        "request_id",
        "tenant_id",
        "project_id",
        "actor_id",
        "revision_digest",
        "environment_authority_id",
        "idempotency_key",
        "inputs",
    }
)


def require_identifier(value: Any, label: str, *, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise ContractError(f"{label} must be a non-empty bounded string")
    if not _IDENTIFIER.fullmatch(value) or ".." in value or "//" in value:
        raise ContractError(f"{label} contains unsupported characters")
    return value


def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ContractError(f"{label} must be a lowercase sha256 digest")
    return value


def _strict_json(value: Any, label: str, *, depth: int = 0) -> Any:
    if depth > 32:
        raise ContractError(f"{label} exceeds the maximum nesting depth")
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError(f"{label} contains a non-finite number")
        return value
    if isinstance(value, str):
        if len(value.encode("utf-8")) > 1_048_576:
            raise ContractError(f"{label} contains an oversized string")
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > 10_000:
            raise ContractError(f"{label} contains too many array items")
        return [_strict_json(item, label, depth=depth + 1) for item in value]
    if isinstance(value, Mapping):
        if len(value) > 10_000:
            raise ContractError(f"{label} contains too many object members")
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key.encode("utf-8")) > 256:
                raise ContractError(f"{label} contains an invalid object key")
            normalized[key] = _strict_json(item, label, depth=depth + 1)
        return normalized
    raise ContractError(f"{label} is not strict JSON")


def canonical_json(value: Any) -> bytes:
    normalized = _strict_json(value, "document")
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def digest_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class RuntimeRequest:
    schema_version: str
    request_id: str
    tenant_id: str
    project_id: str
    actor_id: str
    revision_digest: str
    environment_authority_id: str
    idempotency_key: str
    inputs: Mapping[str, Any]

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> "RuntimeRequest":
        if not isinstance(value, Mapping):
            raise ContractError("request must be an object")
        unknown = set(value) - _REQUEST_KEYS
        missing = _REQUEST_KEYS - set(value)
        if unknown or missing:
            raise ContractError(
                f"request fields differ: missing={sorted(missing)} unknown={sorted(unknown)}"
            )
        if value.get("schema_version") != "1.0":
            raise ContractError("request.schema_version must be '1.0'")
        inputs = _strict_json(value.get("inputs"), "request.inputs")
        if not isinstance(inputs, dict):
            raise ContractError("request.inputs must be an object")
        if len(canonical_json(inputs)) > _MAX_REQUEST_INPUT_BYTES:
            raise ContractError("request.inputs exceeds the 8 MiB canonical limit")
        if "_runtime_context" in inputs or "authority" in inputs or "capabilities" in inputs:
            raise ContractError("request.inputs attempts to set a runtime-owned field")
        return cls(
            schema_version="1.0",
            request_id=require_identifier(value.get("request_id"), "request.request_id"),
            tenant_id=require_identifier(value.get("tenant_id"), "request.tenant_id"),
            project_id=require_identifier(value.get("project_id"), "request.project_id"),
            actor_id=require_identifier(value.get("actor_id"), "request.actor_id"),
            revision_digest=require_digest(
                value.get("revision_digest"), "request.revision_digest"
            ),
            environment_authority_id=require_identifier(
                value.get("environment_authority_id"),
                "request.environment_authority_id",
            ),
            idempotency_key=require_identifier(
                value.get("idempotency_key"), "request.idempotency_key"
            ),
            inputs=inputs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "actor_id": self.actor_id,
            "revision_digest": self.revision_digest,
            "environment_authority_id": self.environment_authority_id,
            "idempotency_key": self.idempotency_key,
            "inputs": dict(self.inputs),
        }


@dataclass(frozen=True)
class ExecutionAuthority:
    """Trusted host context; never parse this object from Skill inputs."""

    tenant_id: str
    project_id: str
    actor_id: str
    revision_digest: str
    environment_authority_id: str
    allowed_skills: frozenset[str]
    allowed_effects: frozenset[str] = frozenset({"local-analysis"})
    allowed_toolchains: frozenset[str] = frozenset()
    allowed_providers: frozenset[str] = frozenset()
    verified_evidence_digests: frozenset[str] = frozenset()
    repository_root: Path | None = None
    expires_at_epoch_seconds: int | None = None

    def __post_init__(self) -> None:
        require_identifier(self.tenant_id, "authority.tenant_id")
        require_identifier(self.project_id, "authority.project_id")
        require_identifier(self.actor_id, "authority.actor_id")
        require_digest(self.revision_digest, "authority.revision_digest")
        require_identifier(
            self.environment_authority_id, "authority.environment_authority_id"
        )
        if not self.allowed_skills:
            raise AuthorityError("authority.allowed_skills may not be empty")
        for skill in self.allowed_skills:
            if skill != "*":
                require_identifier(skill, "authority.allowed_skills[]")
        for effect in self.allowed_effects:
            require_identifier(effect, "authority.allowed_effects[]")
        for toolchain in self.allowed_toolchains:
            require_identifier(toolchain, "authority.allowed_toolchains[]")
        for provider in self.allowed_providers:
            require_identifier(provider, "authority.allowed_providers[]")
        for evidence_digest in self.verified_evidence_digests:
            require_digest(evidence_digest, "authority.verified_evidence_digests[]")
        if self.repository_root is not None:
            root = Path(self.repository_root)
            if not root.is_absolute() or root.is_symlink() or not root.is_dir():
                raise AuthorityError("authority.repository_root must be an absolute real directory")
        if self.expires_at_epoch_seconds is not None and self.expires_at_epoch_seconds <= 0:
            raise AuthorityError("authority expiry must be a positive epoch timestamp")

    def authorize_scope(self, request: RuntimeRequest) -> None:
        """Bind a request to this host-minted authority without granting a Skill.

        Evidence validators and other lower-level public APIs use this boundary
        when they do not receive a Skill name.  Keeping the scope check in one
        method prevents those APIs from accepting an expired or cross-tenant
        authority merely because a receipt digest is allowlisted.
        """

        if self.expires_at_epoch_seconds is not None and time.time() >= self.expires_at_epoch_seconds:
            raise AuthorityError("execution authority has expired")
        expected = (
            self.tenant_id,
            self.project_id,
            self.actor_id,
            self.revision_digest,
            self.environment_authority_id,
        )
        observed = (
            request.tenant_id,
            request.project_id,
            request.actor_id,
            request.revision_digest,
            request.environment_authority_id,
        )
        if expected != observed:
            raise AuthorityError("request scope does not match host-minted authority")

    def authorize(self, skill: str, request: RuntimeRequest) -> None:
        self.authorize_scope(request)
        if "*" not in self.allowed_skills and skill not in self.allowed_skills:
            raise AuthorityError("requested Skill is outside host-minted authority")
