"""Explicit, in-process compiler, LSP, and DAP adapter boundary.

The intelligence runtime never discovers executables, opens sockets, or starts
subprocesses.  A host must register an exact adapter object and the invocation
must match its declared protocol, operation, authority, and source digest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

from .canonical import digest_object, freeze_json, require_sha256_digest


_ADAPTER_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_PROTOCOLS = frozenset({"compiler", "lsp", "dap"})


class AdapterStatus(str, Enum):
    """Conservative outcomes for an exact adapter invocation."""

    SUCCEEDED = "SUCCEEDED"
    NOT_RUN = "NOT_RUN"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    DENIED = "DENIED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class AdapterManifest:
    adapter_id: str
    protocol: str
    version: str
    operations: tuple[str, ...]
    required_authority: tuple[str, ...] = ()
    side_effects: tuple[str, ...] = ()
    implementation_digest: str | None = None

    def __post_init__(self) -> None:
        if not _ADAPTER_ID.fullmatch(self.adapter_id):
            raise ValueError("adapter_id must be a bounded lowercase identity")
        if self.protocol not in _PROTOCOLS:
            raise ValueError("adapter protocol must be compiler, lsp, or dap")
        if not self.version.strip():
            raise ValueError("adapter version is required")
        if not self.operations or any(not value.strip() for value in self.operations):
            raise ValueError("adapter operations must be non-empty")
        if len(set(self.operations)) != len(self.operations):
            raise ValueError("adapter operations must be unique")
        if len(set(self.required_authority)) != len(self.required_authority):
            raise ValueError("adapter authority entries must be unique")
        if self.side_effects:
            raise ValueError(
                "semantic/runtime-proof adapters must be side-effect free; "
                "external effects require a separately governed service"
            )
        if self.implementation_digest is not None:
            require_sha256_digest(self.implementation_digest)


@dataclass(frozen=True, slots=True)
class AdapterRequest:
    request_id: str
    adapter_id: str
    protocol: str
    operation: str
    source_digest: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    granted_authority: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.request_id.strip() or len(self.request_id) > 256:
            raise ValueError("request_id is required and bounded")
        if not _ADAPTER_ID.fullmatch(self.adapter_id):
            raise ValueError("adapter_id is invalid")
        if self.protocol not in _PROTOCOLS:
            raise ValueError("request protocol is invalid")
        if not self.operation.strip() or len(self.operation) > 256:
            raise ValueError("operation is required and bounded")
        require_sha256_digest(self.source_digest)
        if len(set(self.granted_authority)) != len(self.granted_authority):
            raise ValueError("granted_authority must be unique")
        frozen = freeze_json(dict(self.payload))
        if not isinstance(frozen, Mapping):
            raise ValueError("adapter payload must be a JSON object")
        object.__setattr__(self, "payload", frozen)

    @property
    def request_digest(self) -> str:
        return digest_object(
            {
                "request_id": self.request_id,
                "adapter_id": self.adapter_id,
                "protocol": self.protocol,
                "operation": self.operation,
                "source_digest": self.source_digest,
                "payload": self.payload,
                "granted_authority": self.granted_authority,
            },
            domain="adapter-request",
        )


@dataclass(frozen=True, slots=True)
class AdapterEvidence:
    evidence_id: str
    artifact_digest: str
    producer: str
    tool_version: str
    input_digest: str

    def __post_init__(self) -> None:
        if not self.evidence_id.strip() or not self.producer.strip():
            raise ValueError("adapter evidence identity and producer are required")
        if not self.tool_version.strip():
            raise ValueError("adapter evidence tool_version is required")
        require_sha256_digest(self.artifact_digest)
        require_sha256_digest(self.input_digest)


@dataclass(frozen=True, slots=True)
class AdapterResult:
    status: AdapterStatus
    request_digest: str
    adapter_id: str
    protocol: str
    operation: str
    output: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[AdapterEvidence, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_digest)
        frozen = freeze_json(dict(self.output))
        if not isinstance(frozen, Mapping):
            raise ValueError("adapter output must be a JSON object")
        object.__setattr__(self, "output", frozen)
        if self.status is AdapterStatus.SUCCEEDED:
            if not self.evidence:
                raise ValueError("successful adapter result requires evidence")
            if any(item.input_digest != self.request_digest for item in self.evidence):
                raise ValueError("adapter evidence must bind the exact request")
        elif not self.reason:
            raise ValueError("non-success adapter result requires a reason")

    @property
    def usable(self) -> bool:
        return self.status is AdapterStatus.SUCCEEDED and bool(self.evidence)


class ExactAdapter(Protocol):
    """Host-supplied adapter.  Registration is explicit; discovery is absent."""

    manifest: AdapterManifest

    def invoke(self, request: AdapterRequest) -> AdapterResult: ...


class AdapterRegistry:
    """Exact adapter registry with no executable or network fallback."""

    def __init__(self, adapters: Sequence[ExactAdapter] = ()) -> None:
        self._adapters: dict[str, ExactAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: ExactAdapter) -> None:
        manifest = adapter.manifest
        if manifest.adapter_id in self._adapters:
            raise ValueError(f"adapter is already registered: {manifest.adapter_id}")
        self._adapters[manifest.adapter_id] = adapter

    def manifests(self, protocol: str | None = None) -> tuple[AdapterManifest, ...]:
        if protocol is not None and protocol not in _PROTOCOLS:
            raise ValueError("unknown adapter protocol")
        return tuple(
            adapter.manifest
            for _, adapter in sorted(self._adapters.items())
            if protocol is None or adapter.manifest.protocol == protocol
        )

    def discovery(self, protocol: str) -> Mapping[str, Any]:
        manifests = self.manifests(protocol)
        return MappingProxyType(
            {
                "protocol": protocol,
                "status": (
                    AdapterStatus.SUCCEEDED.value
                    if manifests
                    else AdapterStatus.NOT_RUN.value
                ),
                "adapters": tuple(
                    {
                        "adapter_id": item.adapter_id,
                        "version": item.version,
                        "operations": item.operations,
                        "implementation_digest": item.implementation_digest,
                    }
                    for item in manifests
                ),
                "implicit_discovery": False,
                "subprocess_started": False,
                "network_accessed": False,
            }
        )

    def invoke(self, request: AdapterRequest) -> AdapterResult:
        adapter = self._adapters.get(request.adapter_id)
        if adapter is None:
            return _failure_result(
                AdapterStatus.NOT_RUN,
                request,
                "exact adapter is not registered",
            )
        manifest = adapter.manifest
        if manifest.protocol != request.protocol:
            return _failure_result(
                AdapterStatus.DENIED,
                request,
                "adapter protocol does not match the exact request",
            )
        if request.operation not in manifest.operations:
            return _failure_result(
                AdapterStatus.NOT_RUN,
                request,
                "adapter does not declare the exact operation",
            )
        missing = sorted(set(manifest.required_authority) - set(request.granted_authority))
        if missing:
            return _failure_result(
                AdapterStatus.DENIED,
                request,
                f"missing adapter authority: {', '.join(missing)}",
            )
        try:
            result = adapter.invoke(request)
        except Exception as exc:  # the host adapter is an isolation boundary
            return _failure_result(
                AdapterStatus.FAILED,
                request,
                f"adapter raised {type(exc).__name__}",
            )
        if (
            result.request_digest != request.request_digest
            or result.adapter_id != request.adapter_id
            or result.protocol != request.protocol
            or result.operation != request.operation
        ):
            return _failure_result(
                AdapterStatus.INSUFFICIENT_EVIDENCE,
                request,
                "adapter result is not bound to the exact invocation",
            )
        return result


def _failure_result(
    status: AdapterStatus,
    request: AdapterRequest,
    reason: str,
) -> AdapterResult:
    return AdapterResult(
        status=status,
        request_digest=request.request_digest,
        adapter_id=request.adapter_id,
        protocol=request.protocol,
        operation=request.operation,
        reason=reason,
    )


__all__ = [
    "AdapterEvidence",
    "AdapterManifest",
    "AdapterRegistry",
    "AdapterRequest",
    "AdapterResult",
    "AdapterStatus",
    "ExactAdapter",
]
