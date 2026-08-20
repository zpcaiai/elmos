from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .policies import CachePolicy, WorkloadFeatures, create_policy


@dataclass(frozen=True, slots=True)
class TraceEvent:
    key: str
    size_bytes: int
    recompute_ms: float
    restore_ms: float = 0.0
    model_tokens: int = 0
    critical_path_weight: float = 0.0
    stage_class: str = "unknown"
    next_use_distance: int | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "TraceEvent":
        return cls(
            key=str(value["key"]),
            size_bytes=int(value["size_bytes"]),
            recompute_ms=float(value.get("recompute_ms", 0.0)),
            restore_ms=float(value.get("restore_ms", 0.0)),
            model_tokens=int(value.get("model_tokens", 0)),
            critical_path_weight=float(value.get("critical_path_weight", 0.0)),
            stage_class=str(value.get("stage_class", "unknown")),
            next_use_distance=(
                int(value["next_use_distance"])
                if value.get("next_use_distance") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class SimulationReport:
    policy: str
    capacity_bytes: int
    requests: int
    hits: int
    misses: int
    admitted_misses: int
    bypassed_misses: int
    evictions: int
    request_bytes: int
    hit_bytes: int
    total_recompute_ms: float
    avoided_recompute_ms: float
    restore_ms_on_hits: float
    net_saved_ms: float
    total_model_tokens: int
    avoided_model_tokens: int
    critical_path_saved_ms: float
    object_hit_ratio: float
    byte_hit_ratio: float
    avoided_compute_ratio: float
    avoided_model_token_ratio: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_jsonl(path: Path) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            events.append(TraceEvent.from_mapping(value))
        except Exception as exc:  # pragma: no cover - error path is message-focused
            raise ValueError(f"invalid trace line {line_number}: {exc}") from exc
    return events


def simulate(policy: CachePolicy, events: Iterable[TraceEvent]) -> SimulationReport:
    requests = hits = misses = admitted_misses = bypassed_misses = evictions = 0
    request_bytes = hit_bytes = total_model_tokens = avoided_model_tokens = 0
    total_recompute_ms = avoided_recompute_ms = restore_ms_on_hits = 0.0
    critical_path_saved_ms = 0.0

    for event in events:
        requests += 1
        request_bytes += event.size_bytes
        total_recompute_ms += event.recompute_ms
        total_model_tokens += event.model_tokens
        result = policy.access(
            event.key,
            event.size_bytes,
            recompute_ms=event.recompute_ms,
            restore_ms=event.restore_ms,
        )
        evictions += len(result.evicted)
        if result.hit:
            hits += 1
            hit_bytes += event.size_bytes
            avoided_recompute_ms += event.recompute_ms
            restore_ms_on_hits += event.restore_ms
            avoided_model_tokens += event.model_tokens
            critical_path_saved_ms += max(event.recompute_ms - event.restore_ms, 0.0) * event.critical_path_weight
        else:
            misses += 1
            if result.admitted:
                admitted_misses += 1
            else:
                bypassed_misses += 1

    net_saved_ms = max(avoided_recompute_ms - restore_ms_on_hits, 0.0)
    return SimulationReport(
        policy=policy.name,
        capacity_bytes=policy.capacity_bytes,
        requests=requests,
        hits=hits,
        misses=misses,
        admitted_misses=admitted_misses,
        bypassed_misses=bypassed_misses,
        evictions=evictions,
        request_bytes=request_bytes,
        hit_bytes=hit_bytes,
        total_recompute_ms=total_recompute_ms,
        avoided_recompute_ms=avoided_recompute_ms,
        restore_ms_on_hits=restore_ms_on_hits,
        net_saved_ms=net_saved_ms,
        total_model_tokens=total_model_tokens,
        avoided_model_tokens=avoided_model_tokens,
        critical_path_saved_ms=critical_path_saved_ms,
        object_hit_ratio=hits / requests if requests else 0.0,
        byte_hit_ratio=hit_bytes / request_bytes if request_bytes else 0.0,
        avoided_compute_ratio=(
            avoided_recompute_ms / total_recompute_ms if total_recompute_ms else 0.0
        ),
        avoided_model_token_ratio=(
            avoided_model_tokens / total_model_tokens if total_model_tokens else 0.0
        ),
    )


def compare(
    policy_names: Iterable[str],
    capacity_bytes: int,
    events: Iterable[TraceEvent],
) -> list[SimulationReport]:
    event_list = list(events)
    return [
        simulate(create_policy(name, capacity_bytes), event_list)
        for name in policy_names
    ]


def workload_features(events: Iterable[TraceEvent]) -> WorkloadFeatures:
    return WorkloadFeatures.from_events(
        {
            "key": event.key,
            "size_bytes": event.size_bytes,
            "recompute_ms": event.recompute_ms,
            "next_use_distance": event.next_use_distance,
        }
        for event in events
    )
