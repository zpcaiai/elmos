"""Privacy-minimal execution telemetry and cost aggregation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class TelemetrySample:
    tenant_id: str
    task_id: str
    model: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    wall_clock_ms: int = 0

    def __post_init__(self) -> None:
        if min(self.input_tokens, self.cached_input_tokens, self.output_tokens, self.wall_clock_ms) < 0 or self.cost_usd < 0:
            raise ValueError("telemetry quantities cannot be negative")


def aggregate(samples: Iterable[TelemetrySample]) -> dict[str, object]:
    values = list(samples)
    return {
        "sample_count": len(values),
        "input_tokens": sum(item.input_tokens for item in values),
        "cached_input_tokens": sum(item.cached_input_tokens for item in values),
        "output_tokens": sum(item.output_tokens for item in values),
        "cost_usd": str(sum((item.cost_usd for item in values), Decimal(0))),
        "wall_clock_ms": sum(item.wall_clock_ms for item in values),
        "source": "runtime_observations",
    }
