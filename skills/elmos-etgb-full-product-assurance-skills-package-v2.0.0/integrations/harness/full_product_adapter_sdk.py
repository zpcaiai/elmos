from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class AdapterUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdapterContext:
    tenant_id: str
    run_id: str
    case_run_id: str
    candidate_digest: str
    environment_id: str
    authority_id: str
    owner_id: str
    fencing_token: int
    idempotency_key: str


@dataclass(frozen=True)
class PhaseResult:
    phase: str
    status: str
    checkpoint_digest: str
    evidence: dict[str, Any]


class FullProductAdapter(Protocol):
    adapter_id: str

    def execute(self, case: dict[str, Any], context: AdapterContext) -> list[PhaseResult]: ...


class AdapterRegistry:
    """Reference fail-closed registry. Production adapters must be explicitly registered."""

    def __init__(self) -> None:
        self._adapters: dict[str, FullProductAdapter] = {}

    def register(self, adapter: FullProductAdapter) -> None:
        if not adapter.adapter_id.startswith("external-"):
            raise ValueError("production adapter IDs must be external-* names")
        if adapter.adapter_id in self._adapters:
            raise ValueError(f"duplicate adapter: {adapter.adapter_id}")
        self._adapters[adapter.adapter_id] = adapter

    def resolve(self, adapter_id: str) -> FullProductAdapter:
        try:
            return self._adapters[adapter_id]
        except KeyError as exc:
            raise AdapterUnavailableError(f"adapter is not conformantly registered: {adapter_id}") from exc

    def conformance_status(self, required: set[str]) -> dict[str, Any]:
        registered = set(self._adapters)
        missing = sorted(required - registered)
        unexpected = sorted(registered - required)
        return {
            "complete": not missing and not unexpected,
            "required": len(required),
            "registered": len(registered),
            "missing": missing,
            "unexpected": unexpected,
        }
