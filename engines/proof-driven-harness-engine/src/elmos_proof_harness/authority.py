"""Environment authority and tool-request checks.

``EnvironmentAuthority.authorize`` is the single local PEP entry point.  It
binds tenant/project/actor/run, time window, execution epoch, fencing token,
authority revision, exact tool/capability/operation, path, network and parameter
constraints before consulting the required policy engine.  Any unknown value
or evaluation failure is denied.
"""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
from urllib.parse import urlsplit

from .canonical import digest_object, require_sha256_digest
from .contracts import SecurityContext
from .errors import AuthorizationError, ValidationError
from .policy import PolicyApproval, PolicyEngine, PolicyRequest


AuthorityError = AuthorizationError


class NetworkMode(StrEnum):
    DENY = "DENY"
    ALLOWLIST = "ALLOWLIST"
    SETUP_ONLY = "SETUP_ONLY"


@dataclass(frozen=True, slots=True)
class Capability:
    name: str
    tools: frozenset[str]
    operations: frozenset[str]
    path_prefixes: tuple[str, ...] = ()
    network_hosts: frozenset[str] = frozenset()
    parameters: Mapping[str, frozenset[str]] = field(default_factory=dict)
    side_effects_allowed: bool = False

    def __post_init__(self) -> None:
        tools = frozenset(self.tools)
        operations = frozenset(self.operations)
        path_prefixes = tuple(self.path_prefixes)
        network_hosts = frozenset(self.network_hosts)
        parameters = {
            name: frozenset(values)
            for name, values in self.parameters.items()
        }
        if not self.name or not tools or not operations:
            raise ValidationError("capability name, tools and operations are required")
        if any(not isinstance(value, str) or not value for value in (*tools, *operations)):
            raise ValidationError("capability tools and operations must be non-empty strings")
        if any(not isinstance(path, str) or not path or "\x00" in path or not os.path.isabs(path) for path in path_prefixes):
            raise ValidationError("capability path prefixes must be absolute paths")
        path_prefixes = tuple((os.path.realpath(path).rstrip(os.sep) or os.sep) for path in path_prefixes)
        if any(not isinstance(host, str) or not host or host != host.strip().lower() for host in network_hosts):
            raise ValidationError("capability network hosts must be normalized non-empty strings")
        if any(
            not isinstance(name, str)
            or not name
            or not values
            or any(not isinstance(value, str) for value in values)
            for name, values in parameters.items()
        ):
            raise ValidationError("capability parameter constraints must be non-empty string sets")
        object.__setattr__(self, "tools", tools)
        object.__setattr__(self, "operations", operations)
        object.__setattr__(self, "path_prefixes", path_prefixes)
        object.__setattr__(self, "network_hosts", network_hosts)
        object.__setattr__(self, "parameters", MappingProxyType(parameters))


@dataclass(frozen=True, slots=True)
class ToolRequest:
    context: SecurityContext
    capability: str
    tool: str
    operation: str
    path: str | None = None
    network_url: str | None = None
    resolved_ip: str | None = None
    parameters: Mapping[str, str] = field(default_factory=dict)
    phase: str = "execution"
    side_effect: bool = False

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) and value for value in (self.capability, self.tool, self.operation, self.phase)):
            raise ValidationError("tool request identity is incomplete")
        parameters = dict(self.parameters)
        if any(
            not isinstance(name, str)
            or not name
            or not isinstance(value, str)
            for name, value in parameters.items()
        ):
            raise ValidationError("tool request parameters must be string pairs")
        object.__setattr__(self, "parameters", MappingProxyType(parameters))


@dataclass(frozen=True, slots=True)
class AuthorityDecision:
    authority_id: str
    authority_revision: str
    policy_revision: str | None
    capability: str
    tool: str
    operation: str
    authorized_at: datetime


@dataclass(frozen=True, slots=True)
class EnvironmentAuthority:
    authority_id: str
    tenant_id: str
    project_id: str
    actor_id: str
    run_id: str
    execution_epoch: int
    fencing_generation: int
    environment_id: str
    execution_source: str
    capabilities: tuple[Capability, ...]
    read_paths: tuple[str, ...]
    write_paths: tuple[str, ...]
    network_mode: NetworkMode
    network_allowlist: frozenset[str]
    valid_from: datetime
    expires_at: datetime
    policy_bundle_sha256: str
    revision: str | None = None
    revoked: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        object.__setattr__(self, "read_paths", tuple(self._normalize_path(path) for path in self.read_paths))
        object.__setattr__(self, "write_paths", tuple(self._normalize_path(path) for path in self.write_paths))
        object.__setattr__(self, "network_allowlist", frozenset(self.network_allowlist))
        if not all((self.authority_id, self.tenant_id, self.project_id, self.actor_id, self.run_id, self.environment_id, self.execution_source)):
            raise ValidationError("authority bindings are incomplete")
        if self.execution_epoch < 1 or self.fencing_generation < 1:
            raise ValidationError("authority epoch and fence must be positive")
        if (
            self.valid_from.tzinfo is None
            or self.valid_from.utcoffset() is None
            or self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None
            or self.valid_from >= self.expires_at
        ):
            raise ValidationError("authority validity window is invalid")
        require_sha256_digest(self.policy_bundle_sha256, field="policy_bundle_sha256")
        if not self.capabilities:
            raise ValidationError("authority must contain at least one capability")
        names = [capability.name for capability in self.capabilities]
        if len(names) != len(set(names)):
            raise ValidationError("capability names must be unique")
        for path in (*self.read_paths, *self.write_paths):
            self._normalize_path(path)
        if any(not host or host != host.strip().lower() for host in self.network_allowlist):
            raise ValidationError("authority network allowlist entries must be normalized")
        calculated = self.calculated_revision()
        if self.revision is None:
            object.__setattr__(self, "revision", calculated)
        elif self.revision != calculated:
            raise ValidationError("authority revision does not match content", code="AUTHORITY_REVISION_MISMATCH")

    def calculated_revision(self) -> str:
        return digest_object(
            {
                "authority_id": self.authority_id,
                "tenant_id": self.tenant_id,
                "project_id": self.project_id,
                "actor_id": self.actor_id,
                "run_id": self.run_id,
                "execution_epoch": self.execution_epoch,
                "fencing_generation": self.fencing_generation,
                "environment_id": self.environment_id,
                "execution_source": self.execution_source,
                "capabilities": self.capabilities,
                "read_paths": self.read_paths,
                "write_paths": self.write_paths,
                "network_mode": self.network_mode,
                "network_allowlist": self.network_allowlist,
                "valid_from": self.valid_from,
                "expires_at": self.expires_at,
                "policy_bundle_sha256": self.policy_bundle_sha256,
                "revoked": self.revoked,
            },
            domain="environment-authority",
        )

    def authorize(
        self,
        request: ToolRequest,
        *,
        now: datetime,
        policy: PolicyEngine | None = None,
        approval: PolicyApproval | None = None,
    ) -> AuthorityDecision:
        if now.tzinfo is None or now.utcoffset() is None:
            self._deny("authorization time must be timezone-aware", "INVALID_AUTH_TIME")
        if self.revoked:
            self._deny("authority is revoked", "AUTHORITY_REVOKED")
        context = request.context
        exact = {
            "tenant_id": (context.tenant_id, self.tenant_id),
            "project_id": (context.project_id, self.project_id),
            "actor_id": (context.actor_id, self.actor_id),
            "run_id": (context.run_id, self.run_id),
            "execution_epoch": (context.execution_epoch, self.execution_epoch),
            "fencing_generation": (context.fencing_generation, self.fencing_generation),
        }
        mismatched = [name for name, (actual, expected) in exact.items() if actual != expected]
        if mismatched:
            code = "STALE_FENCE" if "fencing_generation" in mismatched else "AUTHORITY_SCOPE_MISMATCH"
            self._deny("request is not bound to this authority", code, {"fields": mismatched})
        if context.authority_revision != self.revision:
            self._deny("authority revision is stale", "AUTHORITY_REVISION_STALE")
        if not (self.valid_from <= now < self.expires_at):
            self._deny("authority is outside its validity window", "AUTHORITY_EXPIRED")
        capability = next((item for item in self.capabilities if item.name == request.capability), None)
        if capability is None:
            self._deny("capability is not granted", "CAPABILITY_DENIED")
        assert capability is not None
        if request.tool not in capability.tools:
            self._deny("tool is not granted", "TOOL_DENIED")
        if request.operation not in capability.operations:
            self._deny("operation is not granted", "OPERATION_DENIED")
        if request.side_effect and not capability.side_effects_allowed:
            self._deny("side effects are not granted", "SIDE_EFFECT_DENIED")
        self._check_parameters(capability, request)
        self._check_path(capability, request)
        host = self._check_network(capability, request)
        policy_revision: str | None = None
        if policy is None:
            self._deny("policy engine is unavailable", "POLICY_UNAVAILABLE")
        if policy.revision != self.policy_bundle_sha256:
            self._deny("policy bundle revision mismatch", "POLICY_REVISION_MISMATCH")
        evaluation = policy.require_allow(
            PolicyRequest(
                context=context,
                capability=request.capability,
                tool=request.tool,
                operation=request.operation,
                path=request.path,
                network_host=host,
                side_effect=request.side_effect,
            ),
            now=now,
            approval=approval,
        )
        policy_revision = evaluation.policy_revision
        return AuthorityDecision(
            authority_id=self.authority_id,
            authority_revision=self.revision or "",
            policy_revision=policy_revision,
            capability=request.capability,
            tool=request.tool,
            operation=request.operation,
            authorized_at=now,
        )

    def _check_parameters(self, capability: Capability, request: ToolRequest) -> None:
        unknown = set(request.parameters) - set(capability.parameters)
        if unknown:
            self._deny("request contains unconstrained parameters", "PARAMETER_DENIED", {"parameters": sorted(unknown)})
        for name, value in request.parameters.items():
            if value not in capability.parameters[name]:
                self._deny("parameter value is not granted", "PARAMETER_VALUE_DENIED", {"parameter": name})

    def _check_path(self, capability: Capability, request: ToolRequest) -> None:
        if request.path is None:
            if capability.path_prefixes and request.network_url is None:
                self._deny("capability requires an exact path binding", "PATH_REQUIRED")
            return
        if not capability.path_prefixes:
            self._deny("capability does not grant filesystem access", "CAPABILITY_PATH_DENIED")
        normalized = self._normalize_path(request.path)
        if request.operation == "read":
            allowed = self.read_paths
        elif request.operation in {"write", "delete", "execute", "create"}:
            allowed = self.write_paths
        else:
            self._deny("path-bearing operation is not classified", "PATH_OPERATION_UNKNOWN")
            return
        if not allowed or not any(self._within(normalized, item) for item in allowed):
            self._deny("path is outside authority roots", "PATH_DENIED")
        if capability.path_prefixes and not any(self._within(normalized, item) for item in capability.path_prefixes):
            self._deny("path violates capability constraint", "CAPABILITY_PATH_DENIED")

    def _check_network(self, capability: Capability, request: ToolRequest) -> str | None:
        if request.network_url is None:
            if request.resolved_ip is not None:
                self._deny("resolved ip without network url", "NETWORK_REQUEST_INVALID")
            return None
        if self.network_mode is NetworkMode.DENY:
            self._deny("network is denied", "NETWORK_DENIED")
        if self.network_mode is NetworkMode.SETUP_ONLY and request.phase != "setup":
            self._deny("network is setup-only", "NETWORK_PHASE_DENIED")
        try:
            parsed = urlsplit(request.network_url)
            parsed_host = parsed.hostname
            port = parsed.port or 443
        except ValueError:
            self._deny("network URL is malformed", "NETWORK_URL_DENIED")
            return None
        if parsed.scheme not in {"https"} or not parsed_host or parsed.username or parsed.password:
            self._deny("network URL is not an approved HTTPS endpoint", "NETWORK_URL_DENIED")
        host = parsed_host.rstrip(".").lower()
        endpoint = f"{host}:{port}"
        if not capability.network_hosts:
            self._deny("capability does not grant network access", "CAPABILITY_NETWORK_DENIED")
        allowed = self.network_allowlist.intersection(capability.network_hosts)
        if not allowed:
            self._deny("authority and capability network constraints do not intersect", "NETWORK_HOST_DENIED")
        if host not in allowed and endpoint not in allowed:
            self._deny("network host is not allowlisted", "NETWORK_HOST_DENIED")
        if request.resolved_ip is None:
            self._deny("a pinned resolved IP is required for network authorization", "NETWORK_IP_REQUIRED")
        try:
            ip = ipaddress.ip_address(request.resolved_ip)
        except ValueError:
            self._deny("resolved IP is invalid", "NETWORK_IP_INVALID")
            return host
        if ip.is_unspecified or ip.is_multicast or ip.is_loopback or ip.is_link_local or ip.is_private:
            if str(ip) not in allowed:
                self._deny("resolved IP is unsafe or not explicitly allowed", "NETWORK_IP_DENIED")
        return host

    @staticmethod
    def _normalize_path(path: str) -> str:
        if not path or "\x00" in path or not os.path.isabs(path):
            raise AuthorizationError("absolute non-empty path is required", code="PATH_INVALID")
        normalized = os.path.realpath(path)
        if not os.path.isabs(normalized):
            raise AuthorizationError("path normalization failed", code="PATH_INVALID")
        return normalized.rstrip(os.sep) or os.sep

    @classmethod
    def _within(cls, path: str, prefix: str) -> bool:
        root = prefix.rstrip(os.sep) or os.sep
        if not os.path.isabs(root):
            return False
        try:
            return os.path.commonpath((path, root)) == root
        except ValueError:
            return False

    @staticmethod
    def _deny(message: str, code: str, details: Mapping[str, object] | None = None) -> None:
        raise AuthorizationError(message, code=code, details=details)
