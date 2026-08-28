"""Provider-neutral agent decision adapters."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Protocol

from .errors import ContractViolation, NotConfigured
from .models import Action, CompletionProposal, Identity, Usage


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    provider: str
    protocol_version: str = "1.0"
    supports_checkpoints: bool = False
    supports_streaming: bool = False
    supports_tool_calls: bool = True
    supported_tools: frozenset[str] = frozenset()
    regions: frozenset[str] = frozenset({"local"})


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    identity: Identity
    model: str
    context: Mapping[str, Any]
    tool_schemas: tuple[Mapping[str, Any], ...] = ()
    checkpoint: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    action: Action | None = None
    completion: CompletionProposal | None = None
    usage: Usage = Usage()
    provider_checkpoint: Mapping[str, Any] | None = None
    raw_events: tuple[Mapping[str, Any], ...] = ()
    provider: str | None = None

    def __post_init__(self) -> None:
        if (self.action is None) == (self.completion is None):
            raise ContractViolation("provider response must contain exactly one action or completion")


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    kind: str
    payload: Mapping[str, Any]
    timestamp: float = field(default_factory=time.time)


class ProviderAdapter(Protocol):
    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def decide(self, request: ProviderRequest) -> ProviderResponse: ...


class NativeAgentAdapter:
    """Deterministic in-process adapter used for local qualification."""

    def __init__(self, decisions: Iterable[ProviderResponse] = (), *, provider: str = "native") -> None:
        self._capabilities = ProviderCapabilities(provider, supports_checkpoints=True, supports_streaming=True)
        self._decisions = list(decisions)
        self._index = 0

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    def decide(self, request: ProviderRequest) -> ProviderResponse:
        if self._index >= len(self._decisions):
            raise NotConfigured("native adapter has no deterministic decision")
        response = self._decisions[self._index]
        self._index += 1
        return response


class JsonTransport(Protocol):
    def __call__(self, provider: str, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class JsonProviderAdapter:
    """Normalizes an injected provider transport without owning network access."""

    def __init__(self, provider: str, transport: JsonTransport, *, capabilities: ProviderCapabilities | None = None) -> None:
        self._provider = provider
        self._transport = transport
        self._capabilities = capabilities or ProviderCapabilities(provider, supports_checkpoints=True, supports_streaming=True)

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    def decide(self, request: ProviderRequest) -> ProviderResponse:
        if request.identity.tenant_id == "":
            raise ContractViolation("provider request is missing tenant scope")
        payload = {
            "schema_version": "1.0",
            "tenant_id": request.identity.tenant_id,
            "project_id": request.identity.project_id,
            "task_id": request.identity.task_id,
            "run_id": request.identity.run_id,
            "node_id": request.identity.node_id,
            "model": request.model,
            "context": dict(request.context),
            "tool_schemas": [dict(schema) for schema in request.tool_schemas],
            "checkpoint": request.checkpoint,
        }
        result = self._transport(self._provider, payload)
        return replace(normalize_provider_response(result, request.identity), provider=self._provider)


class CodexCompatibleAdapter(JsonProviderAdapter):
    def __init__(self, transport: JsonTransport) -> None:
        super().__init__("codex-compatible", transport, capabilities=ProviderCapabilities("codex-compatible", supports_checkpoints=True, supports_streaming=True))


class ClaudeCompatibleAdapter(JsonProviderAdapter):
    def __init__(self, transport: JsonTransport) -> None:
        super().__init__("claude-compatible", transport, capabilities=ProviderCapabilities("claude-compatible", supports_checkpoints=False, supports_streaming=True))


class OpenHandsCompatibleAdapter(JsonProviderAdapter):
    def __init__(self, transport: JsonTransport) -> None:
        super().__init__("openhands-compatible", transport, capabilities=ProviderCapabilities("openhands-compatible", supports_checkpoints=True, supports_streaming=True))


def normalize_provider_response(payload: Mapping[str, Any], identity: Identity) -> ProviderResponse:
    kind = payload.get("kind")
    usage = Usage(**dict(payload.get("usage", {})))
    if kind == "action":
        action = Action(
            action_id=str(payload["action_id"]),
            tool=str(payload["tool"]),
            args=dict(payload.get("args", {})),
            risk_context=dict(payload.get("risk_context", {})),
            idempotency_key=str(payload.get("idempotency_key", payload["action_id"])),
            read_scope=tuple(payload.get("read_scope", ())),
            write_scope=tuple(payload.get("write_scope", ())),
            expected_side_effects=tuple(payload.get("expected_side_effects", ())),
            required_capabilities=tuple(payload.get("required_capabilities", ())),
            timeout_seconds=float(payload.get("timeout_seconds", 30.0)),
        )
        return ProviderResponse(action=action, usage=usage, provider_checkpoint=payload.get("checkpoint"), raw_events=(dict(payload),))
    if kind == "completion":
        proposal = CompletionProposal(
            run_id=identity.run_id,
            summary=str(payload.get("summary", "")),
            claimed_status=str(payload.get("status", "succeeded")),
            requirement_refs=tuple(payload.get("requirement_refs", ())),
            test_refs=tuple(payload.get("test_refs", ())),
            provider_text=str(payload.get("provider_text", "")),
            evidence_refs=tuple(_artifact_ref(item) for item in payload.get("evidence_refs", ())),
        )
        return ProviderResponse(completion=proposal, usage=usage, provider_checkpoint=payload.get("checkpoint"), raw_events=(dict(payload),))
    raise ContractViolation("provider response kind must be action or completion")


@dataclass(frozen=True, slots=True)
class RouteConstraints:
    allowed_providers: frozenset[str] = frozenset()
    required_region: str = "local"
    require_checkpoint: bool = False
    max_cost_micros: int | None = None


class ProviderRouter:
    def __init__(self, adapters: Iterable[ProviderAdapter]) -> None:
        self._adapters = {adapter.capabilities.provider: adapter for adapter in adapters}
        self._failures: dict[str, int] = {name: 0 for name in self._adapters}
        self._open_until: dict[str, float] = {}
        self._lock = threading.RLock()

    def choose(self, constraints: RouteConstraints, *, exclude: frozenset[str] = frozenset()) -> ProviderAdapter:
        names = sorted(self._adapters)
        if constraints.allowed_providers:
            names = [name for name in names if name in constraints.allowed_providers]
        names = [name for name in names if name not in exclude]
        for name in names:
            adapter = self._adapters[name]
            capabilities = adapter.capabilities
            if constraints.required_region not in capabilities.regions:
                continue
            if constraints.require_checkpoint and not capabilities.supports_checkpoints:
                continue
            with self._lock:
                if self._open_until.get(name, 0) > time.time():
                    continue
            return adapter
        raise NotConfigured("no provider satisfies route constraints")

    def call(self, request: ProviderRequest, constraints: RouteConstraints) -> ProviderResponse:
        excluded: set[str] = set()
        last_error: Exception | None = None
        while True:
            try:
                adapter = self.choose(constraints, exclude=frozenset(excluded))
            except NotConfigured:
                if last_error is not None:
                    raise last_error
                raise
            provider = adapter.capabilities.provider
            try:
                response = adapter.decide(request)
                if constraints.max_cost_micros is not None and response.usage.cost_micros > constraints.max_cost_micros:
                    raise ContractViolation("provider response exceeds route cost ceiling")
            except Exception as error:
                last_error = error
                excluded.add(provider)
                with self._lock:
                    self._failures[provider] += 1
                    if self._failures[provider] >= 3:
                        self._open_until[provider] = time.time() + 30.0
                continue
            with self._lock:
                self._failures[provider] = 0
                self._open_until.pop(provider, None)
            return replace(response, provider=response.provider or provider)


def _artifact_ref(value: Any):
    from .models import ArtifactRef

    if not isinstance(value, Mapping):
        raise ContractViolation("provider evidence_refs must contain artifact objects")
    return ArtifactRef(**dict(value))
