"""Provider Adapter Service Provider Interface (SPI).

Defines the clean boundary contract that every native direct adapter, gateway adapter,
and self-hosted inference engine must satisfy without leaking vendor types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Iterator, Mapping

from ..domain.contracts import (
    ExecutionLane,
    InferenceRequest,
    InferenceResponse,
    InferenceStreamChunk,
    ModelExecutionPlan,
    ProviderDeployment,
    RouteRequest,
    VerifiedSecurityContext,
)
from ..registry.registry import HealthSnapshot


class ProviderAdapter(ABC):
    """Abstract interface implemented by all execution lane adapters."""

    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Unique identifier for this adapter implementation."""
        ...

    @property
    @abstractmethod
    def supported_lanes(self) -> tuple[ExecutionLane, ...]:
        """Execution lanes supported by this adapter."""
        ...

    @abstractmethod
    def supports(self, plan: ModelExecutionPlan) -> bool:
        """Returns True if this adapter can execute the resolved plan."""
        ...

    @abstractmethod
    def validate(self, plan: ModelExecutionPlan) -> None:
        """Validates adapter-specific preconditions; raises ProviderError if unsupported."""
        ...

    @abstractmethod
    def execute(
        self,
        request: RouteRequest,
        plan: ModelExecutionPlan,
        security_context: VerifiedSecurityContext | None = None,
    ) -> InferenceResponse:
        """Synchronously executes the inference request according to the execution plan."""
        ...

    @abstractmethod
    def stream(
        self,
        request: RouteRequest,
        plan: ModelExecutionPlan,
        security_context: VerifiedSecurityContext | None = None,
    ) -> Iterator[InferenceStreamChunk]:
        """Streams inference chunks for the given request and execution plan."""
        ...

    @abstractmethod
    def estimate_cost(
        self,
        request: RouteRequest,
        plan: ModelExecutionPlan,
    ) -> float:
        """Calculates preflight estimated cost for this request and plan."""
        ...

    @abstractmethod
    def cancel(self, execution_id: str) -> bool:
        """Cancels an in-flight execution if supported by the provider."""
        ...

    @abstractmethod
    def health_probe(self, deployment: ProviderDeployment) -> HealthSnapshot:
        """Probes the physical deployment endpoint and returns updated health."""
        ...
