"""Deadline-bounded, correctness-first planning across all cache layers.

The coordinator separates lookup from authority. Every accepted candidate is
bound to the exact tenant/project/authorization/compatibility/work identity,
meets the requested validation floor, stays inside resource budgets, and is
attributed to concrete avoided work exactly once. Optional-layer failure is a
typed slow-path decision, never a reason to weaken correctness.
"""

from __future__ import annotations

import math
import multiprocessing
import os
import pickle
import re
import signal
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from enum import StrEnum
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from types import MappingProxyType
from typing import Any, Generic, Protocol, TypeVar, cast

from .canonical import digest_of, require_digest
from .enums import ValidationLevel
from .errors import ContractViolation

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}$")
_DEFAULT_SINGLEFLIGHT_OWNER_LEASE_SECONDS = 30.0
_MAX_SINGLEFLIGHT_OWNER_LEASE_SECONDS = 300.0
_DEFAULT_SINGLEFLIGHT_ORPHAN_LIMIT = 32
_MAX_SINGLEFLIGHT_ORPHAN_LIMIT = 1024


class _StringEnum(StrEnum):
    pass


class CacheLayer(_StringEnum):
    CHECKPOINT = "CHECKPOINT"
    ACTION = "ACTION"
    CAS = "CAS"
    ENVIRONMENT = "ENVIRONMENT"
    NATIVE_BUILD = "NATIVE_BUILD"
    PROVIDER_PREFIX = "PROVIDER_PREFIX"


class ProbeOutcome(_StringEnum):
    HIT = "HIT"
    MISS = "MISS"
    BYPASS = "BYPASS"
    ERROR = "ERROR"


class ReuseDecision(_StringEnum):
    """Closed v1.2 planner decisions."""

    RESUME_CHECKPOINT = "RESUME_CHECKPOINT"
    REUSE_EXACT_RESULT = "REUSE_EXACT_RESULT"
    RESTORE_ARTIFACTS = "RESTORE_ARTIFACTS"
    WARM_ENVIRONMENT = "WARM_ENVIRONMENT"
    USE_NATIVE_BUILD = "USE_NATIVE_BUILD"
    USE_PROMPT_PREFIX = "USE_PROMPT_PREFIX"
    EXECUTE_REMAINDER = "EXECUTE_REMAINDER"
    FULL_RECOMPUTE = "FULL_RECOMPUTE"


class ReconciliationStatus(_StringEnum):
    RECONCILED = "RECONCILED"
    DIVERGED = "DIVERGED"


_LAYER_ORDER: tuple[CacheLayer, ...] = (
    CacheLayer.CHECKPOINT,
    CacheLayer.ACTION,
    CacheLayer.CAS,
    CacheLayer.ENVIRONMENT,
    CacheLayer.NATIVE_BUILD,
    CacheLayer.PROVIDER_PREFIX,
)

_EXACT_RESULT_LAYERS = frozenset({CacheLayer.CHECKPOINT, CacheLayer.ACTION})
_LAYER_DECISION: Mapping[CacheLayer, ReuseDecision] = MappingProxyType(
    {
        CacheLayer.CHECKPOINT: ReuseDecision.RESUME_CHECKPOINT,
        CacheLayer.ACTION: ReuseDecision.REUSE_EXACT_RESULT,
        CacheLayer.CAS: ReuseDecision.RESTORE_ARTIFACTS,
        CacheLayer.ENVIRONMENT: ReuseDecision.WARM_ENVIRONMENT,
        CacheLayer.NATIVE_BUILD: ReuseDecision.USE_NATIVE_BUILD,
        CacheLayer.PROVIDER_PREFIX: ReuseDecision.USE_PROMPT_PREFIX,
    }
)


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(f"{field_name} must be a bounded identifier", field=field_name)
    return value


def _finite_non_negative(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContractViolation(f"{field_name} must be numeric", field=field_name)
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ContractViolation(f"{field_name} must be finite and non-negative", field=field_name)
    return number


def _non_negative_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractViolation(f"{field_name} must be a non-negative integer", field=field_name)
    return value


@dataclass(frozen=True)
class ReuseIdentity:
    """Every authority and compatibility dimension shared work is bound to."""

    tenant_id: str
    project_id: str
    authorization_digest: str
    compatibility_digest: str
    work_digest: str

    def __post_init__(self) -> None:
        _identifier(self.tenant_id, "tenant_id")
        _identifier(self.project_id, "project_id")
        require_digest(self.authorization_digest)
        require_digest(self.compatibility_digest)
        require_digest(self.work_digest)

    @property
    def singleflight_key(self) -> str:
        return digest_of(
            {
                "tenant_id": self.tenant_id,
                "project_id": self.project_id,
                "authorization_digest": self.authorization_digest,
                "compatibility_digest": self.compatibility_digest,
                "work_digest": self.work_digest,
            }
        )


@dataclass(frozen=True)
class WorkDependency:
    """One exact typed edge to a dependency output."""

    work_id: str
    output_digest: str

    def __post_init__(self) -> None:
        _identifier(self.work_id, "dependency_work_id")
        require_digest(self.output_digest)


@dataclass(frozen=True)
class DagWorkUnit:
    work_id: str
    work_digest: str
    dependencies: tuple[WorkDependency, ...] = ()
    minimum_validation: ValidationLevel = ValidationLevel.UNVERIFIED

    def __post_init__(self) -> None:
        _identifier(self.work_id, "work_id")
        require_digest(self.work_digest)
        if not isinstance(self.minimum_validation, ValidationLevel):
            raise ContractViolation("DAG minimum_validation must use ValidationLevel")
        if self.minimum_validation is ValidationLevel.QUARANTINED:
            raise ContractViolation("a DAG work unit cannot require QUARANTINED validation")
        names = [item.work_id for item in self.dependencies]
        if len(names) != len(set(names)):
            raise ContractViolation("DAG work unit contains duplicate dependencies", work_id=self.work_id)
        object.__setattr__(self, "dependencies", tuple(sorted(self.dependencies, key=lambda item: item.work_id)))


@dataclass(frozen=True)
class VerifiedBoundary:
    """A digest-bound, validated output that may cut a typed DAG traversal."""

    work_id: str
    work_digest: str
    dependencies: tuple[WorkDependency, ...]
    validation_level: ValidationLevel
    evidence_digest: str

    def __post_init__(self) -> None:
        _identifier(self.work_id, "boundary_work_id")
        require_digest(self.work_digest)
        require_digest(self.evidence_digest)
        if not isinstance(self.validation_level, ValidationLevel):
            raise ContractViolation("boundary validation_level must use ValidationLevel")
        if self.validation_level is ValidationLevel.QUARANTINED:
            raise ContractViolation("a verified boundary cannot be QUARANTINED")
        names = [item.work_id for item in self.dependencies]
        if len(names) != len(set(names)):
            raise ContractViolation("verified boundary contains duplicate dependencies")
        object.__setattr__(self, "dependencies", tuple(sorted(self.dependencies, key=lambda item: item.work_id)))


@dataclass(frozen=True)
class ReuseBudgets:
    """Hard bounds for one coordinator decision."""

    decision_timeout_ms: float = 1_000.0
    per_probe_timeout_ms: float = 250.0
    max_lookup_ms: float = 1_000.0
    max_remote_bytes: int = 1 << 30
    max_provider_write_tokens: int = 1_000_000
    max_prefetch_bytes: int = 1 << 30
    max_restore_ms: float = 1_000_000.0
    max_probes: int = 6

    def __post_init__(self) -> None:
        for name in (
            "decision_timeout_ms",
            "per_probe_timeout_ms",
            "max_lookup_ms",
            "max_restore_ms",
        ):
            number = _finite_non_negative(getattr(self, name), name)
            if number <= 0:
                raise ContractViolation(f"{name} must be greater than zero", field=name)
            object.__setattr__(self, name, number)
        for name in (
            "max_remote_bytes",
            "max_provider_write_tokens",
            "max_prefetch_bytes",
            "max_probes",
        ):
            number = _non_negative_integer(getattr(self, name), name)
            if name == "max_probes" and number <= 0:
                raise ContractViolation("max_probes must be greater than zero")
            object.__setattr__(self, name, number)

    def to_dict(self) -> dict[str, int | float]:
        return {
            "decision_timeout_ms": self.decision_timeout_ms,
            "per_probe_timeout_ms": self.per_probe_timeout_ms,
            "max_lookup_ms": self.max_lookup_ms,
            "max_remote_bytes": self.max_remote_bytes,
            "max_provider_write_tokens": self.max_provider_write_tokens,
            "max_prefetch_bytes": self.max_prefetch_bytes,
            "max_restore_ms": self.max_restore_ms,
            "max_probes": self.max_probes,
        }


@dataclass(frozen=True)
class ReuseRequest:
    request_id: str
    identity: ReuseIdentity
    minimum_validation: ValidationLevel
    allow_provider_prefix: bool = True
    budgets: ReuseBudgets = field(default_factory=ReuseBudgets)
    decision_deadline_monotonic: float | None = None
    work_graph: tuple[DagWorkUnit, ...] = ()
    requested_work_ids: tuple[str, ...] = ()
    negative_failure_classes: Mapping[CacheLayer, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _identifier(self.request_id, "request_id")
        if not isinstance(self.identity, ReuseIdentity):
            raise ContractViolation("identity must be ReuseIdentity")
        if not isinstance(self.minimum_validation, ValidationLevel):
            raise ContractViolation("minimum_validation must use ValidationLevel")
        if self.minimum_validation is ValidationLevel.QUARANTINED:
            raise ContractViolation("QUARANTINED cannot be a reuse validation floor")
        if not isinstance(self.allow_provider_prefix, bool):
            raise ContractViolation("allow_provider_prefix must be boolean")
        if not isinstance(self.budgets, ReuseBudgets):
            raise ContractViolation("budgets must be ReuseBudgets")
        if self.decision_deadline_monotonic is not None:
            object.__setattr__(
                self,
                "decision_deadline_monotonic",
                _finite_non_negative(self.decision_deadline_monotonic, "decision_deadline_monotonic"),
            )
        graph = tuple(sorted(self.work_graph, key=lambda item: item.work_id))
        if any(not isinstance(item, DagWorkUnit) for item in graph):
            raise ContractViolation("work_graph must contain DagWorkUnit values")
        graph_by_id = {item.work_id: item for item in graph}
        if len(graph_by_id) != len(graph):
            raise ContractViolation("work_graph contains duplicate work IDs")
        for unit in graph:
            for dependency in unit.dependencies:
                target = graph_by_id.get(dependency.work_id)
                if target is None:
                    raise ContractViolation(
                        "DAG dependency is absent from the work graph",
                        work_id=unit.work_id,
                        dependency=dependency.work_id,
                    )
                if dependency.output_digest != target.work_digest:
                    raise ContractViolation(
                        "DAG dependency digest does not match its work unit",
                        work_id=unit.work_id,
                        dependency=dependency.work_id,
                    )
        _assert_acyclic(graph_by_id)
        requested = self.requested_work_ids
        if graph and not requested:
            dependency_ids = {
                dependency.work_id for unit in graph for dependency in unit.dependencies
            }
            requested = tuple(sorted(set(graph_by_id) - dependency_ids))
        if not graph and requested:
            raise ContractViolation("requested_work_ids require a work_graph")
        if len(requested) != len(set(requested)):
            raise ContractViolation("requested_work_ids contains duplicates")
        for work_id in requested:
            if work_id not in graph_by_id:
                raise ContractViolation("requested work is absent from the graph", work_id=work_id)
        failures: dict[CacheLayer, str] = {}
        for layer, failure_class in self.negative_failure_classes.items():
            if not isinstance(layer, CacheLayer):
                raise ContractViolation("negative failure class has an unknown layer")
            failures[layer] = _identifier(failure_class, "failure_class")
        object.__setattr__(self, "work_graph", graph)
        object.__setattr__(self, "requested_work_ids", tuple(sorted(requested)))
        object.__setattr__(self, "negative_failure_classes", MappingProxyType(failures))

    @property
    def graph_by_id(self) -> Mapping[str, DagWorkUnit]:
        return MappingProxyType({unit.work_id: unit for unit in self.work_graph})


@dataclass(frozen=True)
class LayerProbeResult:
    layer: CacheLayer
    outcome: ProbeOutcome
    reason_code: str
    identity: ReuseIdentity
    artifact_digest: str | None = None
    validation_level: ValidationLevel = ValidationLevel.UNVERIFIED
    verified: bool = False
    authorised: bool = False
    compatible: bool = False
    complete_result: bool = False
    lookup_ms: float = 0.0
    restore_ms: float = 0.0
    verify_ms: float = 0.0
    recompute_ms: float = 0.0
    remote_bytes: int = 0
    provider_write_tokens: int = 0
    prefetch_bytes: int = 0
    avoided_work_ids: tuple[str, ...] = ()
    verified_boundaries: tuple[VerifiedBoundary, ...] = ()
    failure_class: str | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.layer, CacheLayer) or not isinstance(self.outcome, ProbeOutcome):
            raise ContractViolation("probe result uses an unknown layer or outcome")
        if not isinstance(self.identity, ReuseIdentity):
            raise ContractViolation("probe result identity must be ReuseIdentity")
        if not isinstance(self.validation_level, ValidationLevel):
            raise ContractViolation("probe validation_level must use ValidationLevel")
        for name in ("verified", "authorised", "compatible", "complete_result"):
            if not isinstance(getattr(self, name), bool):
                raise ContractViolation(f"{name} must be boolean", field=name)
        _identifier(self.reason_code, "reason_code")
        if self.artifact_digest is not None:
            require_digest(self.artifact_digest)
        for name in ("lookup_ms", "restore_ms", "verify_ms", "recompute_ms"):
            object.__setattr__(self, name, _finite_non_negative(getattr(self, name), name))
        for name in ("remote_bytes", "provider_write_tokens", "prefetch_bytes"):
            object.__setattr__(self, name, _non_negative_integer(getattr(self, name), name))
        if self.complete_result and self.layer not in _EXACT_RESULT_LAYERS:
            raise ContractViolation(
                "only checkpoint and exact Action Cache may declare a complete result",
                layer=str(self.layer),
            )
        if self.outcome is ProbeOutcome.HIT:
            if self.artifact_digest is None:
                raise ContractViolation("a cache hit must identify immutable material", layer=str(self.layer))
            if not self.avoided_work_ids:
                raise ContractViolation("a cache hit must identify concrete avoided work", layer=str(self.layer))
        avoided = tuple(sorted(self.avoided_work_ids))
        if any(not value for value in avoided) or len(avoided) != len(set(avoided)):
            raise ContractViolation("avoided_work_ids must be unique non-empty identifiers")
        for work_id in avoided:
            _identifier(work_id, "avoided_work_id")
        boundaries = tuple(sorted(self.verified_boundaries, key=lambda item: item.work_id))
        if len(boundaries) != len({item.work_id for item in boundaries}):
            raise ContractViolation("probe result contains duplicate verified boundaries")
        if not {item.work_id for item in boundaries} <= set(avoided):
            raise ContractViolation("every verified boundary must name attributed avoided work")
        if self.failure_class is not None:
            _identifier(self.failure_class, "failure_class")
        object.__setattr__(self, "avoided_work_ids", avoided)
        object.__setattr__(self, "verified_boundaries", boundaries)
        object.__setattr__(self, "detail", MappingProxyType(dict(self.detail)))

    @property
    def net_saved_ms(self) -> float:
        return self.recompute_ms - self.restore_ms - self.verify_ms

    def legal_for(self, request: ReuseRequest) -> tuple[bool, str]:
        if self.identity != request.identity:
            return False, "IDENTITY_MISMATCH"
        if not self.authorised:
            return False, "AUTHORIZATION_DENIED"
        if not self.compatible:
            return False, "COMPATIBILITY_MISMATCH"
        if not self.verified:
            return False, "UNVERIFIED_MATERIAL"
        if not self.validation_level.satisfies(request.minimum_validation):
            return False, "VALIDATION_TOO_LOW"
        if self.net_saved_ms <= 0:
            return False, "RESTORE_MORE_EXPENSIVE_THAN_RECOMPUTE"
        if self.verified_boundaries:
            if not request.work_graph:
                return False, "BOUNDARY_GRAPH_MISSING"
            graph = request.graph_by_id
            for boundary in self.verified_boundaries:
                unit = graph.get(boundary.work_id)
                if unit is None:
                    return False, "BOUNDARY_WORK_UNKNOWN"
                if boundary.work_digest != unit.work_digest or boundary.dependencies != unit.dependencies:
                    return False, "BOUNDARY_DEPENDENCY_MISMATCH"
                if not boundary.validation_level.satisfies(request.minimum_validation):
                    return False, "BOUNDARY_VALIDATION_TOO_LOW"
                if not boundary.validation_level.satisfies(unit.minimum_validation):
                    return False, "BOUNDARY_VALIDATION_TOO_LOW"
        return True, "LEGAL_HIT"


Probe = Callable[[], LayerProbeResult]


@dataclass(frozen=True)
class PlannedLayer:
    layer: CacheLayer
    decision: ReuseDecision
    outcome: ProbeOutcome
    accepted: bool
    reason_code: str
    artifact_digest: str | None
    predicted_saved_ms: float
    complete_result: bool
    avoided_work_ids: tuple[str, ...]
    attributed_work_ids: tuple[str, ...] = ()
    supporting_work_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": str(self.layer),
            "decision": str(self.decision),
            "outcome": str(self.outcome),
            "accepted": self.accepted,
            "reason_code": self.reason_code,
            "artifact_digest": self.artifact_digest,
            "predicted_saved_ms": self.predicted_saved_ms,
            "complete_result": self.complete_result,
            "avoided_work_ids": list(self.avoided_work_ids),
            "attributed_work_ids": list(self.attributed_work_ids),
            "supporting_work_ids": list(self.supporting_work_ids),
        }


@dataclass(frozen=True)
class ReuseAttribution:
    work_id: str
    primary_layer: CacheLayer
    supporting_layers: tuple[CacheLayer, ...]
    predicted_saved_ms: float

    def __post_init__(self) -> None:
        _identifier(self.work_id, "attribution_work_id")
        object.__setattr__(
            self,
            "predicted_saved_ms",
            _finite_non_negative(self.predicted_saved_ms, "predicted_saved_ms"),
        )
        if self.primary_layer in self.supporting_layers:
            raise ContractViolation("primary attribution layer cannot also be supporting")
        if len(self.supporting_layers) != len(set(self.supporting_layers)):
            raise ContractViolation("supporting attribution layers must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_id": self.work_id,
            "primary_layer": str(self.primary_layer),
            "supporting_layers": [str(layer) for layer in self.supporting_layers],
            "predicted_saved_ms": self.predicted_saved_ms,
        }


@dataclass(frozen=True)
class BudgetUsage:
    decision_elapsed_ms: float
    lookup_ms: float
    remote_bytes: int
    provider_write_tokens: int
    prefetch_bytes: int
    restore_ms: float
    breaches: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_elapsed_ms": self.decision_elapsed_ms,
            "lookup_ms": self.lookup_ms,
            "remote_bytes": self.remote_bytes,
            "provider_write_tokens": self.provider_write_tokens,
            "prefetch_bytes": self.prefetch_bytes,
            "restore_ms": self.restore_ms,
            "breaches": list(self.breaches),
        }


@dataclass(frozen=True)
class ReusePlan:
    request_id: str
    identity_digest: str
    plan_digest: str
    complete_result_layer: CacheLayer | None
    execution_required: bool
    decisions: tuple[ReuseDecision, ...]
    layers: tuple[PlannedLayer, ...]
    attributions: tuple[ReuseAttribution, ...]
    verified_boundary_ids: tuple[str, ...]
    remaining_work_ids: tuple[str, ...]
    budget_usage: BudgetUsage

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.2.0",
            "request_id": self.request_id,
            "identity_digest": self.identity_digest,
            "plan_digest": self.plan_digest,
            "complete_result_layer": (
                str(self.complete_result_layer) if self.complete_result_layer is not None else None
            ),
            "execution_required": self.execution_required,
            "decisions": [str(decision) for decision in self.decisions],
            "layers": [layer.to_dict() for layer in self.layers],
            "attributions": [item.to_dict() for item in self.attributions],
            "verified_boundary_ids": list(self.verified_boundary_ids),
            "remaining_work_ids": list(self.remaining_work_ids),
            "budget_usage": self.budget_usage.to_dict(),
        }


class AttributionLedger:
    """Assign each avoided unit to one primary cache layer exactly once."""

    def __init__(self) -> None:
        self._owners: dict[str, CacheLayer] = {}
        self._saved_ms: dict[CacheLayer, float] = {}

    def record(self, layer: CacheLayer, work_id: str, saved_ms: float) -> None:
        _identifier(work_id, "attribution_work_id")
        saved = _finite_non_negative(saved_ms, "attributed_saved_ms")
        existing = self._owners.get(work_id)
        if existing is not None:
            raise ContractViolation(
                "avoided work cannot be attributed twice",
                work_id=work_id,
                first_layer=str(existing),
                second_layer=str(layer),
            )
        self._owners[work_id] = layer
        self._saved_ms[layer] = self._saved_ms.get(layer, 0.0) + saved

    def owner(self, work_id: str) -> CacheLayer | None:
        return self._owners.get(work_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_owners": {key: str(value) for key, value in sorted(self._owners.items())},
            "saved_ms_by_layer": {
                str(layer): value
                for layer, value in sorted(self._saved_ms.items(), key=lambda item: str(item[0]))
            },
            "total_saved_ms": sum(self._saved_ms.values()),
        }


@dataclass(frozen=True)
class NegativeBackoffPolicy:
    base_delay_seconds: float = 0.25
    maximum_delay_seconds: float = 30.0

    def __post_init__(self) -> None:
        base = _finite_non_negative(self.base_delay_seconds, "base_delay_seconds")
        maximum = _finite_non_negative(self.maximum_delay_seconds, "maximum_delay_seconds")
        if base <= 0 or maximum < base:
            raise ContractViolation("negative backoff delays are invalid")
        object.__setattr__(self, "base_delay_seconds", base)
        object.__setattr__(self, "maximum_delay_seconds", maximum)


@dataclass(frozen=True)
class NegativeBackoffEntry:
    identity_digest: str
    failure_class: str
    failures: int
    retry_after_monotonic: float

    def __post_init__(self) -> None:
        require_digest(self.identity_digest)
        _identifier(self.failure_class, "failure_class")
        if self.failures < 1:
            raise ContractViolation("negative backoff failures must be positive")
        _finite_non_negative(self.retry_after_monotonic, "retry_after_monotonic")


class NegativeBackoff:
    """Exact-identity deterministic-failure backoff."""

    def __init__(self, policy: NegativeBackoffPolicy | None = None) -> None:
        self.policy = policy or NegativeBackoffPolicy()
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, str], NegativeBackoffEntry] = {}

    def record(
        self,
        identity: ReuseIdentity,
        failure_class: str,
        now_monotonic: float,
    ) -> NegativeBackoffEntry:
        failure = _identifier(failure_class, "failure_class")
        now = _finite_non_negative(now_monotonic, "now_monotonic")
        key = (identity.singleflight_key, failure)
        with self._lock:
            existing = self._entries.get(key)
            failures = 1 if existing is None else existing.failures + 1
            delay = min(
                self.policy.maximum_delay_seconds,
                self.policy.base_delay_seconds * (2 ** (failures - 1)),
            )
            entry = NegativeBackoffEntry(key[0], failure, failures, now + delay)
            self._entries[key] = entry
            return entry

    def active(
        self,
        identity: ReuseIdentity,
        failure_class: str,
        now_monotonic: float,
    ) -> NegativeBackoffEntry | None:
        failure = _identifier(failure_class, "failure_class")
        now = _finite_non_negative(now_monotonic, "now_monotonic")
        key = (identity.singleflight_key, failure)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if now >= entry.retry_after_monotonic:
                del self._entries[key]
                return None
            return entry

    def clear(self, identity: ReuseIdentity, failure_class: str) -> None:
        with self._lock:
            self._entries.pop(
                (identity.singleflight_key, _identifier(failure_class, "failure_class")),
                None,
            )


@dataclass(frozen=True)
class RealizedLayer:
    layer: CacheLayer
    successful: bool
    avoided_work_ids: tuple[str, ...]
    actual_saved_ms: float

    def __post_init__(self) -> None:
        if not isinstance(self.successful, bool):
            raise ContractViolation("realized successful must be boolean")
        avoided = tuple(sorted(self.avoided_work_ids))
        if any(not item for item in avoided) or len(avoided) != len(set(avoided)):
            raise ContractViolation("realized avoided work IDs must be unique and non-empty")
        for work_id in avoided:
            _identifier(work_id, "realized_work_id")
        saved = _finite_non_negative(self.actual_saved_ms, "actual_saved_ms")
        if not self.successful and (avoided or saved != 0):
            raise ContractViolation("a failed realized layer cannot claim avoided work or savings")
        object.__setattr__(self, "avoided_work_ids", avoided)
        object.__setattr__(self, "actual_saved_ms", saved)


@dataclass(frozen=True)
class PlanRealization:
    request_id: str
    plan_digest: str
    layers: tuple[RealizedLayer, ...]
    executed_work_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.request_id, "request_id")
        require_digest(self.plan_digest)
        if len(self.layers) != len({item.layer for item in self.layers}):
            raise ContractViolation("a realization may record each layer only once")
        executed = tuple(sorted(self.executed_work_ids))
        if any(not item for item in executed) or len(executed) != len(set(executed)):
            raise ContractViolation("executed work IDs must be unique and non-empty")
        for work_id in executed:
            _identifier(work_id, "executed_work_id")
        realized = [work for layer in self.layers if layer.successful for work in layer.avoided_work_ids]
        if len(realized) != len(set(realized)):
            raise ContractViolation("realized avoided work cannot be attributed twice")
        overlap = set(realized) & set(executed)
        if overlap:
            raise ContractViolation("work cannot be both avoided and executed", work_ids=sorted(overlap))
        object.__setattr__(self, "executed_work_ids", executed)


@dataclass(frozen=True)
class ReconciliationReport:
    status: ReconciliationStatus
    planned_saved_ms: float
    realized_saved_ms: float
    relative_error: float
    unrealized_work_ids: tuple[str, ...]
    unplanned_work_ids: tuple[str, ...]
    wrong_owner_work_ids: tuple[str, ...]
    missing_executed_work_ids: tuple[str, ...]
    unexpected_executed_work_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": str(self.status),
            "planned_saved_ms": self.planned_saved_ms,
            "realized_saved_ms": self.realized_saved_ms,
            "relative_error": self.relative_error,
            "unrealized_work_ids": list(self.unrealized_work_ids),
            "unplanned_work_ids": list(self.unplanned_work_ids),
            "wrong_owner_work_ids": list(self.wrong_owner_work_ids),
            "missing_executed_work_ids": list(self.missing_executed_work_ids),
            "unexpected_executed_work_ids": list(self.unexpected_executed_work_ids),
        }


class WaiterCancelled(RuntimeError):
    """One singleflight waiter cancelled without cancelling shared work."""


T = TypeVar("T")


@dataclass
class _Flight(Generic[T]):
    """One exact shared execution with an independent, non-renewable lease."""

    future: Future[T]
    lease_deadline: float
    expired: threading.Event
    reaper: threading.Timer
    waiters: int = 0


class Singleflight(Generic[T]):
    """Coalesce exact identities while preserving independent waiter control."""

    def __init__(
        self,
        monotonic: Callable[[], float] = time.monotonic,
        *,
        owner_lease_seconds: float = _DEFAULT_SINGLEFLIGHT_OWNER_LEASE_SECONDS,
        orphan_limit: int = _DEFAULT_SINGLEFLIGHT_ORPHAN_LIMIT,
    ) -> None:
        lease = _finite_non_negative(owner_lease_seconds, "owner_lease_seconds")
        if lease <= 0 or lease > _MAX_SINGLEFLIGHT_OWNER_LEASE_SECONDS:
            raise ContractViolation(
                "singleflight owner lease must be positive and bounded",
                maximum_seconds=_MAX_SINGLEFLIGHT_OWNER_LEASE_SECONDS,
            )
        if (
            isinstance(orphan_limit, bool)
            or not isinstance(orphan_limit, int)
            or orphan_limit < 1
            or orphan_limit > _MAX_SINGLEFLIGHT_ORPHAN_LIMIT
        ):
            raise ContractViolation(
                "singleflight orphan limit must be a positive bounded integer",
                maximum=_MAX_SINGLEFLIGHT_ORPHAN_LIMIT,
            )
        self._lock = threading.Lock()
        self._in_flight: dict[str, _Flight[T]] = {}
        self._monotonic = monotonic
        self._owner_lease_seconds = lease
        self._orphan_limit = orphan_limit
        self._orphaned_owners = 0

    def run(
        self,
        identity: ReuseIdentity,
        operation: Callable[[], T],
        *,
        timeout_seconds: float | None = None,
        deadline_monotonic: float | None = None,
        cancel_event: threading.Event | None = None,
    ) -> T:
        if timeout_seconds is not None:
            timeout_seconds = _finite_non_negative(timeout_seconds, "timeout_seconds")
        if deadline_monotonic is not None:
            deadline_monotonic = _finite_non_negative(deadline_monotonic, "deadline_monotonic")
        key = identity.singleflight_key
        with self._lock:
            self._reap_expired_locked(self._monotonic())
            flight = self._in_flight.get(key)
            if flight is not None and flight.future.done():
                flight.reaper.cancel()
                del self._in_flight[key]
                flight = None
            if flight is None:
                if self._orphaned_owners >= self._orphan_limit:
                    raise TimeoutError(
                        "singleflight orphan capacity is exhausted; refusing new execution"
                    )
                future: Future[T] = Future()
                lease_deadline = self._monotonic() + self._owner_lease_seconds
                expired = threading.Event()
                reaper = threading.Timer(
                    self._owner_lease_seconds,
                    self._expire,
                    args=(key, future, expired),
                )
                reaper.name = f"elmos-singleflight-reaper-{key[-12:]}"
                reaper.daemon = True
                flight = _Flight(future, lease_deadline, expired, reaper)
                self._in_flight[key] = flight
                worker = threading.Thread(
                    target=self._execute,
                    args=(key, flight, operation),
                    name=f"elmos-singleflight-{key[-12:]}",
                    daemon=True,
                )
                try:
                    reaper.start()
                    worker.start()
                except BaseException:
                    reaper.cancel()
                    if self._in_flight.get(key) is flight:
                        del self._in_flight[key]
                    raise
            flight.waiters += 1
        deadline = deadline_monotonic
        if timeout_seconds is not None:
            timeout_deadline = self._monotonic() + timeout_seconds
            deadline = timeout_deadline if deadline is None else min(deadline, timeout_deadline)
        deadline = flight.lease_deadline if deadline is None else min(deadline, flight.lease_deadline)
        try:
            return self._wait(key, flight, deadline, cancel_event)
        finally:
            with self._lock:
                flight.waiters -= 1

    def _execute(
        self,
        key: str,
        flight: _Flight[T],
        operation: Callable[[], T],
    ) -> None:
        try:
            flight.future.set_result(operation())
        except BaseException as error:
            flight.future.set_exception(error)
        finally:
            flight.reaper.cancel()
            with self._lock:
                if flight.expired.is_set():
                    self._orphaned_owners -= 1
                if self._in_flight.get(key) is flight:
                    del self._in_flight[key]

    def _wait(
        self,
        key: str,
        flight: _Flight[T],
        deadline: float | None,
        cancel_event: threading.Event | None,
    ) -> T:
        while True:
            if flight.expired.is_set():
                raise TimeoutError("singleflight owner lease exceeded")
            if cancel_event is not None and cancel_event.is_set():
                raise WaiterCancelled("singleflight waiter cancelled")
            remaining = None if deadline is None else deadline - self._monotonic()
            if remaining is not None and remaining <= 0:
                raise TimeoutError("singleflight waiter deadline exceeded")
            wait_for = remaining
            if cancel_event is not None:
                wait_for = 0.01 if remaining is None else min(remaining, 0.01)
            try:
                return flight.future.result(timeout=wait_for)
            except FutureTimeout:
                if flight.expired.is_set():
                    raise TimeoutError("singleflight owner lease exceeded") from None
                if deadline is not None and self._monotonic() >= deadline:
                    if deadline >= flight.lease_deadline:
                        self._expire(key, flight.future, flight.expired)
                    raise TimeoutError("singleflight waiter deadline exceeded") from None

    def _expire(self, key: str, future: Future[T], expired: threading.Event) -> None:
        """Detach only the exact expired owner; its execution is never cancelled."""

        with self._lock:
            current = self._in_flight.get(key)
            if current is not None and current.future is future:
                if future.done():
                    return
                if not expired.is_set():
                    expired.set()
                    self._orphaned_owners += 1
                del self._in_flight[key]

    def _reap_expired_locked(self, now: float) -> None:
        expired = [
            (key, flight)
            for key, flight in self._in_flight.items()
            if now >= flight.lease_deadline
        ]
        for key, flight in expired:
            if flight.future.done():
                continue
            if not flight.expired.is_set():
                flight.expired.set()
                self._orphaned_owners += 1
            flight.reaper.cancel()
            del self._in_flight[key]

    @property
    def active_count(self) -> int:
        """Number of current owners, excluding lazily observed expired leases."""

        with self._lock:
            self._reap_expired_locked(self._monotonic())
            return len(self._in_flight)

    def active_waiter_count(self, identity: ReuseIdentity) -> int:
        """Return waiters attached to the current exact owner for diagnostics."""

        key = identity.singleflight_key
        with self._lock:
            self._reap_expired_locked(self._monotonic())
            current = self._in_flight.get(key)
            return 0 if current is None else current.waiters

    @property
    def orphaned_owner_count(self) -> int:
        """Detached operations still running, bounded by ``orphan_limit``."""

        with self._lock:
            return self._orphaned_owners


@dataclass
class _ResourceTracker:
    remote_bytes: int = 0
    provider_write_tokens: int = 0
    prefetch_bytes: int = 0
    restore_ms: float = 0.0

    def reason(self, result: LayerProbeResult, budgets: ReuseBudgets) -> str | None:
        if self.remote_bytes + result.remote_bytes > budgets.max_remote_bytes:
            return "REMOTE_BYTES_BUDGET_EXCEEDED"
        if self.provider_write_tokens + result.provider_write_tokens > budgets.max_provider_write_tokens:
            return "PROVIDER_WRITE_BUDGET_EXCEEDED"
        if self.prefetch_bytes + result.prefetch_bytes > budgets.max_prefetch_bytes:
            return "PREFETCH_BUDGET_EXCEEDED"
        if self.restore_ms + result.restore_ms + result.verify_ms > budgets.max_restore_ms:
            return "RESTORE_BUDGET_EXCEEDED"
        return None

    def consume(self, result: LayerProbeResult) -> None:
        self.remote_bytes += result.remote_bytes
        self.provider_write_tokens += result.provider_write_tokens
        self.prefetch_bytes += result.prefetch_bytes
        self.restore_ms += result.restore_ms + result.verify_ms


@dataclass(frozen=True)
class _ProbeEnvelope:
    """Typed, bounded message returned by a disposable probe worker."""

    kind: str
    completed_monotonic: float
    result: dict[str, Any] | None = None
    exception_type: str | None = None
    exception_digest: str | None = None


@dataclass
class _ActiveProbe:
    process: BaseProcess
    connection: Connection
    submitted_wall: float
    deadline_wall: float
    timeout_reason: str
    start_method: str


class _ProbeIsolationContext(Protocol):
    def Pipe(self, *, duplex: bool) -> tuple[Connection, Connection]: ...  # noqa: N802

    def Process(  # noqa: N802
        self,
        *,
        target: Callable[..., Any],
        args: tuple[Any, ...],
        name: str,
    ) -> BaseProcess: ...

    def get_start_method(self) -> str: ...


def _probe_result_payload(result: LayerProbeResult) -> dict[str, Any]:
    """Remove the non-pickleable mapping proxy without weakening validation."""

    return {
        "layer": result.layer,
        "outcome": result.outcome,
        "reason_code": result.reason_code,
        "identity": result.identity,
        "artifact_digest": result.artifact_digest,
        "validation_level": result.validation_level,
        "verified": result.verified,
        "authorised": result.authorised,
        "compatible": result.compatible,
        "complete_result": result.complete_result,
        "lookup_ms": result.lookup_ms,
        "restore_ms": result.restore_ms,
        "verify_ms": result.verify_ms,
        "recompute_ms": result.recompute_ms,
        "remote_bytes": result.remote_bytes,
        "provider_write_tokens": result.provider_write_tokens,
        "prefetch_bytes": result.prefetch_bytes,
        "avoided_work_ids": result.avoided_work_ids,
        "verified_boundaries": result.verified_boundaries,
        "failure_class": result.failure_class,
        "detail": dict(result.detail),
    }


def _probe_worker(connection: Connection, probe: Probe) -> None:
    """Run one untrusted probe in a process that the parent can hard-reclaim."""

    if os.name == "posix":
        try:
            os.setsid()
        except OSError:
            # The parent retains the direct process handle as a fallback.
            pass
    try:
        try:
            candidate = probe()
        except BaseException as exc:
            envelope = _ProbeEnvelope(
                "EXCEPTION",
                time.monotonic(),
                exception_type=type(exc).__name__,
                exception_digest=digest_of(str(exc)),
            )
        else:
            if isinstance(candidate, LayerProbeResult):
                envelope = _ProbeEnvelope(
                    "RESULT",
                    time.monotonic(),
                    result=_probe_result_payload(candidate),
                )
            else:
                envelope = _ProbeEnvelope("INVALID_RESULT", time.monotonic())
        try:
            connection.send(envelope)
        except BaseException as exc:
            fallback = _ProbeEnvelope(
                "TRANSPORT_ERROR",
                time.monotonic(),
                exception_type=type(exc).__name__,
                exception_digest=digest_of(str(exc)),
            )
            try:
                connection.send(fallback)
            except BaseException:
                return
    finally:
        connection.close()


def _probe_isolation_context(probe: Probe) -> tuple[_ProbeIsolationContext | None, str]:
    """Select a reclaimable stdlib process context or fail closed."""

    methods = tuple(multiprocessing.get_all_start_methods())
    if "fork" in methods:
        return cast(_ProbeIsolationContext, multiprocessing.get_context("fork")), ""
    limitation = "PROBE_NOT_TRANSPORTABLE"
    for method in ("spawn", "forkserver"):
        if method not in methods:
            continue
        try:
            pickle.dumps(probe, protocol=pickle.HIGHEST_PROTOCOL)
        except (pickle.PickleError, TypeError, AttributeError) as exc:
            limitation = f"{method}:{type(exc).__name__}"
            continue
        return cast(_ProbeIsolationContext, multiprocessing.get_context(method)), ""
    if not methods:
        return None, "NO_MULTIPROCESSING_START_METHOD"
    return None, limitation


def _safe_exception_type(value: str | None) -> str:
    if isinstance(value, str) and len(value) <= 200 and _IDENTIFIER.fullmatch(value):
        return value
    return "UnknownException"


def _reclaim_probe_process(process: BaseProcess) -> bool:
    """Kill the worker process group, reap the direct child, and report success."""

    if not process.is_alive():
        process.join(0)
        return True
    killed = False
    if os.name == "posix" and process.pid is not None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            killed = True
        except (OSError, ProcessLookupError):
            pass
    if not killed:
        try:
            process.kill()
        except (AttributeError, OSError):
            try:
                process.terminate()
            except OSError:
                pass
    process.join(0.25)
    if process.is_alive():
        try:
            process.terminate()
        except OSError:
            pass
        process.join(0.1)
    return not process.is_alive()


class MultiLayerCacheCoordinator:
    """Probe safe stores concurrently and produce a fail-closed reuse plan."""

    def __init__(
        self,
        max_parallel_probes: int = 6,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        negative_backoff_policy: NegativeBackoffPolicy | None = None,
        singleflight_owner_lease_seconds: float = _DEFAULT_SINGLEFLIGHT_OWNER_LEASE_SECONDS,
        singleflight_orphan_limit: int = _DEFAULT_SINGLEFLIGHT_ORPHAN_LIMIT,
    ) -> None:
        if max_parallel_probes < 1:
            raise ContractViolation("max_parallel_probes must be positive")
        self.max_parallel_probes = max_parallel_probes
        self._monotonic = monotonic
        self.singleflight: Singleflight[Any] = Singleflight(
            monotonic,
            owner_lease_seconds=singleflight_owner_lease_seconds,
            orphan_limit=singleflight_orphan_limit,
        )
        self.negative_backoff = NegativeBackoff(negative_backoff_policy)
        self._recent_failure_classes: dict[tuple[str, CacheLayer], str] = {}
        self._failure_lock = threading.Lock()

    def plan(self, request: ReuseRequest, probes: Mapping[CacheLayer, Probe]) -> ReusePlan:
        if not isinstance(request, ReuseRequest):
            raise ContractViolation("request must be ReuseRequest")
        unknown = set(probes) - set(_LAYER_ORDER)
        if unknown:
            raise ContractViolation("unknown cache layer", layers=sorted(str(layer) for layer in unknown))
        if len(probes) > request.budgets.max_probes:
            raise ContractViolation(
                "probe fan-out exceeds the request budget",
                probes=len(probes),
                maximum=request.budgets.max_probes,
            )
        started = self._monotonic()
        duration_deadline = started + request.budgets.decision_timeout_ms / 1_000.0
        deadline = duration_deadline
        if request.decision_deadline_monotonic is not None:
            deadline = min(deadline, request.decision_deadline_monotonic)
        results = self._probe(request, probes, started, deadline)

        return self._plan_prevalidated_results(request, results, started, deadline)

    def plan_prevalidated(
        self,
        request: ReuseRequest,
        results: Mapping[CacheLayer, LayerProbeResult],
        *,
        decision_started_monotonic: float | None = None,
    ) -> ReusePlan:
        """Plan from results already verified by an authoritative lookup.

        Production callers sometimes have to perform a stateful authoritative
        lookup before the coordinator is consulted (the Action Cache records
        hit accounting, for example).  Re-running that lookup in an isolated
        probe would duplicate side effects and make the first result stale.
        This seam skips process creation, but it does *not* skip any planner
        check: identity, authorization, compatibility, validation, cost and
        every request budget are evaluated exactly as for normal probes.
        """

        if not isinstance(request, ReuseRequest):
            raise ContractViolation("request must be ReuseRequest")
        if len(results) > request.budgets.max_probes:
            raise ContractViolation(
                "prevalidated result fan-out exceeds the request budget",
                results=len(results),
                maximum=request.budgets.max_probes,
            )
        checked: dict[CacheLayer, LayerProbeResult] = {}
        for layer, result in results.items():
            if not isinstance(layer, CacheLayer) or not isinstance(result, LayerProbeResult):
                raise ContractViolation("prevalidated results use an unknown cache layer")
            if result.layer is not layer:
                raise ContractViolation(
                    "prevalidated result layer does not match its mapping key",
                    key=str(layer),
                    result=str(result.layer),
                )
            checked[layer] = result
        now = self._monotonic()
        started = (
            now
            if decision_started_monotonic is None
            else _finite_non_negative(
                decision_started_monotonic,
                "decision_started_monotonic",
            )
        )
        if started > now:
            raise ContractViolation("decision start cannot be in the future")
        deadline = started + request.budgets.decision_timeout_ms / 1_000.0
        if request.decision_deadline_monotonic is not None:
            deadline = min(deadline, request.decision_deadline_monotonic)
        return self._plan_prevalidated_results(request, checked, started, deadline)

    def _plan_prevalidated_results(
        self,
        request: ReuseRequest,
        results: Mapping[CacheLayer, LayerProbeResult],
        started: float,
        deadline: float,
    ) -> ReusePlan:
        deadline_exceeded = self._monotonic() > deadline

        provisional: dict[CacheLayer, tuple[bool, str]] = {}
        cumulative_lookup_ms = 0.0
        breaches: set[str] = set()
        for layer in _LAYER_ORDER:
            result = results.get(layer)
            if result is None:
                continue
            cumulative_lookup_ms += result.lookup_ms
            accepted = False
            reason = result.reason_code
            if deadline_exceeded:
                breaches.add("DECISION_DEADLINE_EXCEEDED")
                if result.outcome is ProbeOutcome.HIT:
                    reason = "DECISION_DEADLINE_EXCEEDED"
            elif cumulative_lookup_ms > request.budgets.max_lookup_ms:
                breaches.add("LOOKUP_BUDGET_EXCEEDED")
                if result.outcome is ProbeOutcome.HIT:
                    reason = "LOOKUP_BUDGET_EXCEEDED"
            elif result.outcome is ProbeOutcome.HIT:
                accepted, reason = result.legal_for(request)
            provisional[layer] = (accepted, reason)

        tracker = _ResourceTracker()
        accepted_layers_set: set[CacheLayer] = set()
        complete: CacheLayer | None = None
        for layer in (CacheLayer.CHECKPOINT, CacheLayer.ACTION):
            result = results.get(layer)
            if result is None or not result.complete_result or not provisional[layer][0]:
                continue
            budget_reason = tracker.reason(result, request.budgets)
            if budget_reason is not None:
                provisional[layer] = (False, budget_reason)
                breaches.add(budget_reason)
                continue
            tracker.consume(result)
            accepted_layers_set.add(layer)
            complete = layer
            break

        if complete is None:
            for layer in _LAYER_ORDER:
                result = results.get(layer)
                if result is None or not provisional[layer][0]:
                    continue
                budget_reason = tracker.reason(result, request.budgets)
                if budget_reason is not None:
                    provisional[layer] = (False, budget_reason)
                    breaches.add(budget_reason)
                    continue
                tracker.consume(result)
                accepted_layers_set.add(layer)
        else:
            for layer, (legal, _reason) in tuple(provisional.items()):
                if layer is not complete and legal:
                    provisional[layer] = (False, "SUPERSEDED_BY_EXACT_RESULT")

        accepted_results = tuple(
            results[layer] for layer in _LAYER_ORDER if layer in accepted_layers_set
        )
        attribution_by_work, layer_attribution = _build_attributions(accepted_results)
        planned: list[PlannedLayer] = []
        for layer in _LAYER_ORDER:
            result = results.get(layer)
            if result is None:
                continue
            accepted, reason = provisional[layer]
            owned, supporting, saved = layer_attribution.get(layer, ((), (), 0.0))
            planned.append(
                PlannedLayer(
                    layer=layer,
                    decision=_LAYER_DECISION[layer],
                    outcome=result.outcome,
                    accepted=accepted,
                    reason_code=reason,
                    artifact_digest=result.artifact_digest,
                    predicted_saved_ms=saved if accepted else 0.0,
                    complete_result=result.complete_result,
                    avoided_work_ids=result.avoided_work_ids if accepted else (),
                    attributed_work_ids=owned if accepted else (),
                    supporting_work_ids=supporting if accepted else (),
                )
            )

        verified_boundary_ids, remaining = _remaining_work(request, accepted_results, complete)
        if complete is not None:
            execution_required = False
        elif request.work_graph:
            execution_required = bool(remaining)
        else:
            execution_required = True
        decisions = tuple(_LAYER_DECISION[layer] for layer in _LAYER_ORDER if layer in accepted_layers_set)
        if execution_required:
            decisions += (
                ReuseDecision.EXECUTE_REMAINDER
                if accepted_layers_set
                else ReuseDecision.FULL_RECOMPUTE,
            )
        elif not decisions:
            decisions = (ReuseDecision.FULL_RECOMPUTE,)
            execution_required = True

        elapsed_ms = max(0.0, (self._monotonic() - started) * 1_000.0)
        if elapsed_ms > request.budgets.decision_timeout_ms or self._monotonic() > deadline:
            breaches.add("DECISION_DEADLINE_EXCEEDED")
        usage = BudgetUsage(
            decision_elapsed_ms=elapsed_ms,
            lookup_ms=cumulative_lookup_ms,
            remote_bytes=tracker.remote_bytes,
            provider_write_tokens=tracker.provider_write_tokens,
            prefetch_bytes=tracker.prefetch_bytes,
            restore_ms=tracker.restore_ms,
            breaches=tuple(sorted(breaches)),
        )
        body = {
            "schema_version": "1.2.0",
            "request_id": request.request_id,
            "identity": request.identity.singleflight_key,
            "minimum_validation": str(request.minimum_validation),
            "budgets": request.budgets.to_dict(),
            "complete_result_layer": str(complete) if complete is not None else None,
            "execution_required": execution_required,
            "decisions": [str(item) for item in decisions],
            "layers": [item.to_dict() for item in planned],
            "attributions": [item.to_dict() for item in attribution_by_work],
            "verified_boundary_ids": list(verified_boundary_ids),
            "remaining_work_ids": list(remaining),
            "budget_usage": {
                key: value for key, value in usage.to_dict().items() if key != "decision_elapsed_ms"
            },
        }
        return ReusePlan(
            request_id=request.request_id,
            identity_digest=request.identity.singleflight_key,
            plan_digest=digest_of(body),
            complete_result_layer=complete,
            execution_required=execution_required,
            decisions=decisions,
            layers=tuple(planned),
            attributions=attribution_by_work,
            verified_boundary_ids=verified_boundary_ids,
            remaining_work_ids=remaining,
            budget_usage=usage,
        )

    def _probe(
        self,
        request: ReuseRequest,
        probes: Mapping[CacheLayer, Probe],
        _started: float,
        deadline: float,
    ) -> dict[CacheLayer, LayerProbeResult]:
        selected: dict[CacheLayer, Probe] = {}
        results: dict[CacheLayer, LayerProbeResult] = {}
        now = self._monotonic()
        for layer, probe in probes.items():
            if not request.allow_provider_prefix and layer is CacheLayer.PROVIDER_PREFIX:
                continue
            failure_class = self._failure_class(request, layer)
            if failure_class is not None and self.negative_backoff.active(
                request.identity,
                failure_class,
                now,
            ) is not None:
                results[layer] = LayerProbeResult(
                    layer=layer,
                    outcome=ProbeOutcome.BYPASS,
                    reason_code="NEGATIVE_BACKOFF_ACTIVE",
                    identity=request.identity,
                    failure_class=failure_class,
                )
                continue
            selected[layer] = probe
        if not selected:
            return results
        if deadline <= self._monotonic():
            for layer in selected:
                results[layer] = LayerProbeResult(
                    layer=layer,
                    outcome=ProbeOutcome.ERROR,
                    reason_code="DECISION_DEADLINE_EXCEEDED",
                    identity=request.identity,
                )
            return results

        pending = [(layer, selected[layer]) for layer in _LAYER_ORDER if layer in selected]
        active: dict[CacheLayer, _ActiveProbe] = {}
        try:
            while pending or active:
                while pending and len(active) < self.max_parallel_probes:
                    layer, probe = pending.pop(0)
                    submitted_at = self._monotonic()
                    probe_deadline = (
                        submitted_at + request.budgets.per_probe_timeout_ms / 1_000.0
                    )
                    effective_deadline = min(deadline, probe_deadline)
                    timeout_reason = (
                        "DECISION_DEADLINE_EXCEEDED"
                        if deadline <= probe_deadline
                        else "LOOKUP_TIMEOUT"
                    )
                    remaining = max(0.0, effective_deadline - submitted_at)
                    if remaining <= 0:
                        result = self._probe_failure(
                            request,
                            layer,
                            timeout_reason,
                            "LOOKUP_TIMEOUT",
                        )
                        results[layer] = result
                        self._observe_failure(request, result)
                        continue
                    worker, failure = self._start_probe_worker(
                        request,
                        layer,
                        probe,
                        remaining,
                        timeout_reason,
                    )
                    if failure is not None:
                        results[layer] = failure
                        self._observe_failure(request, failure)
                    elif worker is not None:
                        active[layer] = worker

                progressed = False
                for layer in _LAYER_ORDER:
                    worker = active.get(layer)
                    if worker is None:
                        continue
                    completed = self._poll_probe_worker(request, layer, worker)
                    if completed is None:
                        continue
                    progressed = True
                    del active[layer]
                    results[layer] = completed
                    self._observe_failure(request, completed)

                if active and not progressed:
                    nearest = min(worker.deadline_wall for worker in active.values())
                    time.sleep(max(0.0, min(0.005, nearest - time.monotonic())))
        finally:
            for worker in active.values():
                self._close_probe_worker(worker)
        return results

    def _start_probe_worker(
        self,
        request: ReuseRequest,
        layer: CacheLayer,
        probe: Probe,
        timeout_seconds: float,
        timeout_reason: str,
    ) -> tuple[_ActiveProbe | None, LayerProbeResult | None]:
        submitted_wall = time.monotonic()
        context, limitation = _probe_isolation_context(probe)
        if context is None:
            return None, self._probe_failure(
                request,
                layer,
                "PROBE_ISOLATION_UNAVAILABLE",
                "PROBE_ISOLATION_UNAVAILABLE",
                detail={"platform_limitation": limitation},
            )
        parent_connection, child_connection = context.Pipe(duplex=False)
        process = context.Process(
            target=_probe_worker,
            args=(child_connection, probe),
            name=f"elmos-cache-probe-{layer.value.lower()}",
        )
        process.daemon = True
        try:
            process.start()
        except BaseException as exc:
            parent_connection.close()
            child_connection.close()
            try:
                if process.is_alive():
                    _reclaim_probe_process(process)
                process.close()
            except (AssertionError, ValueError):
                pass
            return None, self._probe_failure(
                request,
                layer,
                "PROBE_ISOLATION_START_FAILED",
                "PROBE_ISOLATION_START_FAILED",
                detail={
                    "exception_type": type(exc).__name__,
                    "exception_digest": digest_of(str(exc)),
                    "isolation_start_method": context.get_start_method(),
                },
            )
        child_connection.close()
        return (
            _ActiveProbe(
                process=process,
                connection=parent_connection,
                submitted_wall=submitted_wall,
                deadline_wall=submitted_wall + timeout_seconds,
                timeout_reason=timeout_reason,
                start_method=context.get_start_method(),
            ),
            None,
        )

    def _poll_probe_worker(
        self,
        request: ReuseRequest,
        layer: CacheLayer,
        worker: _ActiveProbe,
    ) -> LayerProbeResult | None:
        envelope: _ProbeEnvelope | None = None
        receive_error: BaseException | None = None
        ready = worker.connection.poll(0)
        if not ready and not worker.process.is_alive():
            worker.process.join(0)
            remaining = max(0.0, worker.deadline_wall - time.monotonic())
            ready = worker.connection.poll(min(0.01, remaining))
        if ready:
            try:
                received = worker.connection.recv()
            except BaseException as exc:
                receive_error = exc
            else:
                if isinstance(received, _ProbeEnvelope):
                    envelope = received
                else:
                    receive_error = TypeError("probe returned an invalid envelope")
        elif time.monotonic() < worker.deadline_wall and worker.process.is_alive():
            return None

        elapsed_ms = max(0.0, (time.monotonic() - worker.submitted_wall) * 1_000.0)
        timed_out = (
            time.monotonic() >= worker.deadline_wall
            if envelope is None
            else envelope.completed_monotonic > worker.deadline_wall
        )
        reclaimed = self._close_probe_worker(worker)
        isolation_detail = {
            "hard_deadline_enforced": True,
            "worker_reclaimed": reclaimed,
            "isolation_start_method": worker.start_method,
        }
        if timed_out:
            return self._probe_failure(
                request,
                layer,
                worker.timeout_reason,
                "LOOKUP_TIMEOUT",
                lookup_ms=elapsed_ms,
                detail=isolation_detail,
            )
        if receive_error is not None:
            return self._probe_failure(
                request,
                layer,
                "PROBE_TRANSPORT_ERROR",
                "PROBE_TRANSPORT_ERROR",
                lookup_ms=elapsed_ms,
                detail={
                    **isolation_detail,
                    "exception_type": type(receive_error).__name__,
                    "exception_digest": digest_of(str(receive_error)),
                },
            )
        if envelope is None:
            return self._probe_failure(
                request,
                layer,
                "PROBE_WORKER_NO_RESULT",
                "PROBE_WORKER_NO_RESULT",
                lookup_ms=elapsed_ms,
                detail=isolation_detail,
            )
        if envelope.kind == "EXCEPTION":
            exception_type = _safe_exception_type(envelope.exception_type)
            return self._probe_failure(
                request,
                layer,
                f"LOOKUP_ERROR_{exception_type}",
                exception_type,
                lookup_ms=elapsed_ms,
                detail={
                    **isolation_detail,
                    "exception_digest": envelope.exception_digest,
                },
            )
        if envelope.kind == "TRANSPORT_ERROR":
            return self._probe_failure(
                request,
                layer,
                "PROBE_TRANSPORT_ERROR",
                "PROBE_TRANSPORT_ERROR",
                lookup_ms=elapsed_ms,
                detail={
                    **isolation_detail,
                    "exception_type": envelope.exception_type,
                    "exception_digest": envelope.exception_digest,
                },
            )
        if envelope.kind != "RESULT" or envelope.result is None:
            return self._probe_failure(
                request,
                layer,
                "PROBE_CONTRACT_ERROR",
                "PROBE_CONTRACT",
                lookup_ms=elapsed_ms,
                detail=isolation_detail,
            )
        try:
            result = LayerProbeResult(**envelope.result)
        except (ContractViolation, TypeError, ValueError) as exc:
            return self._probe_failure(
                request,
                layer,
                "PROBE_TRANSPORT_ERROR",
                "PROBE_TRANSPORT_ERROR",
                lookup_ms=elapsed_ms,
                detail={
                    **isolation_detail,
                    "exception_type": type(exc).__name__,
                    "exception_digest": digest_of(str(exc)),
                },
            )
        if result.layer is not layer:
            return self._probe_failure(
                request,
                layer,
                "PROBE_LAYER_MISMATCH",
                "PROBE_CONTRACT",
                lookup_ms=elapsed_ms,
                detail=isolation_detail,
            )
        return result

    @staticmethod
    def _close_probe_worker(worker: _ActiveProbe) -> bool:
        worker.connection.close()
        reclaimed = _reclaim_probe_process(worker.process)
        if reclaimed:
            worker.process.close()
        return reclaimed

    @staticmethod
    def _probe_failure(
        request: ReuseRequest,
        layer: CacheLayer,
        reason_code: str,
        failure_class: str,
        *,
        lookup_ms: float = 0.0,
        detail: Mapping[str, Any] | None = None,
    ) -> LayerProbeResult:
        return LayerProbeResult(
            layer=layer,
            outcome=ProbeOutcome.ERROR,
            reason_code=reason_code,
            identity=request.identity,
            lookup_ms=lookup_ms,
            failure_class=failure_class,
            detail={} if detail is None else detail,
        )

    def _failure_class(self, request: ReuseRequest, layer: CacheLayer) -> str | None:
        configured = request.negative_failure_classes.get(layer)
        if configured is not None:
            return configured
        with self._failure_lock:
            return self._recent_failure_classes.get((request.identity.singleflight_key, layer))

    def _observe_failure(self, request: ReuseRequest, result: LayerProbeResult) -> None:
        key = (request.identity.singleflight_key, result.layer)
        if result.outcome in {ProbeOutcome.ERROR, ProbeOutcome.MISS} and result.failure_class is not None:
            self.negative_backoff.record(request.identity, result.failure_class, self._monotonic())
            with self._failure_lock:
                self._recent_failure_classes[key] = result.failure_class
        elif result.outcome is ProbeOutcome.HIT:
            failure_class = self._failure_class(request, result.layer)
            if failure_class is not None:
                self.negative_backoff.clear(request.identity, failure_class)
            with self._failure_lock:
                self._recent_failure_classes.pop(key, None)

    def execute_singleflight(
        self,
        identity: ReuseIdentity,
        operation: Callable[[], T],
        *,
        timeout_seconds: float | None = None,
        deadline_monotonic: float | None = None,
        cancel_event: threading.Event | None = None,
    ) -> T:
        typed = cast(Singleflight[T], self.singleflight)
        return typed.run(
            identity,
            operation,
            timeout_seconds=timeout_seconds,
            deadline_monotonic=deadline_monotonic,
            cancel_event=cancel_event,
        )


def _assert_acyclic(graph: Mapping[str, DagWorkUnit]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(work_id: str) -> None:
        if work_id in visited:
            return
        if work_id in visiting:
            raise ContractViolation("work_graph contains a dependency cycle", work_id=work_id)
        visiting.add(work_id)
        for dependency in graph[work_id].dependencies:
            visit(dependency.work_id)
        visiting.remove(work_id)
        visited.add(work_id)

    for work_id in sorted(graph):
        visit(work_id)


def _build_attributions(
    accepted: Sequence[LayerProbeResult],
) -> tuple[
    tuple[ReuseAttribution, ...],
    Mapping[CacheLayer, tuple[tuple[str, ...], tuple[str, ...], float]],
]:
    owners: dict[str, CacheLayer] = {}
    predicted: dict[str, float] = {}
    supporting: dict[str, list[CacheLayer]] = {}
    layer_owned: dict[CacheLayer, list[str]] = {}
    layer_supporting: dict[CacheLayer, list[str]] = {}
    for result in accepted:
        per_work = max(0.0, result.net_saved_ms) / len(result.avoided_work_ids)
        for work_id in result.avoided_work_ids:
            owner = owners.get(work_id)
            if owner is None:
                owners[work_id] = result.layer
                predicted[work_id] = per_work
                supporting[work_id] = []
                layer_owned.setdefault(result.layer, []).append(work_id)
            else:
                supporting[work_id].append(result.layer)
                layer_supporting.setdefault(result.layer, []).append(work_id)
    records = tuple(
        ReuseAttribution(
            work_id=work_id,
            primary_layer=owners[work_id],
            supporting_layers=tuple(supporting[work_id]),
            predicted_saved_ms=predicted[work_id],
        )
        for work_id in sorted(owners)
    )
    per_layer: dict[CacheLayer, tuple[tuple[str, ...], tuple[str, ...], float]] = {}
    for result in accepted:
        owned = tuple(sorted(layer_owned.get(result.layer, [])))
        enabled = tuple(sorted(layer_supporting.get(result.layer, [])))
        per_layer[result.layer] = (
            owned,
            enabled,
            sum(predicted[work_id] for work_id in owned),
        )
    return records, MappingProxyType(per_layer)


def _remaining_work(
    request: ReuseRequest,
    accepted: Sequence[LayerProbeResult],
    complete: CacheLayer | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not request.work_graph or complete is not None:
        boundaries = tuple(
            sorted(
                {
                    boundary.work_id
                    for result in accepted
                    for boundary in result.verified_boundaries
                }
            )
        )
        return boundaries, ()
    verified = {
        boundary.work_id for result in accepted for boundary in result.verified_boundaries
    }
    graph = request.graph_by_id
    remaining: set[str] = set()

    def require(work_id: str) -> None:
        if work_id in verified or work_id in remaining:
            return
        remaining.add(work_id)
        for dependency in graph[work_id].dependencies:
            require(dependency.work_id)

    for target in request.requested_work_ids:
        require(target)
    return tuple(sorted(verified)), tuple(sorted(remaining))


def accepted_layers(plan: ReusePlan) -> tuple[PlannedLayer, ...]:
    return tuple(layer for layer in plan.layers if layer.accepted)


def predicted_savings(plan: ReusePlan) -> float:
    """Sum primary attribution only; supporting layers are never double-counted."""

    return sum(item.predicted_saved_ms for item in plan.attributions)


def reconcile_plan(
    plan: ReusePlan,
    realization: PlanRealization,
    *,
    tolerance_ratio: float = 0.005,
) -> ReconciliationReport:
    """Reconcile planned primary ownership and DAG execution with raw outcomes."""

    tolerance = _finite_non_negative(tolerance_ratio, "tolerance_ratio")
    if tolerance > 1:
        raise ContractViolation("tolerance_ratio cannot exceed one")
    if realization.request_id != plan.request_id or realization.plan_digest != plan.plan_digest:
        raise ContractViolation("realization is not bound to this exact plan")
    planned_owners = {item.work_id: item.primary_layer for item in plan.attributions}
    realized_owners = {
        work_id: layer.layer
        for layer in realization.layers
        if layer.successful
        for work_id in layer.avoided_work_ids
    }
    planned_ids = set(planned_owners)
    realized_ids = set(realized_owners)
    unrealized = tuple(sorted(planned_ids - realized_ids))
    unplanned = tuple(sorted(realized_ids - planned_ids))
    wrong_owner = tuple(
        sorted(
            work_id
            for work_id in planned_ids & realized_ids
            if planned_owners[work_id] is not realized_owners[work_id]
        )
    )
    expected_executed = set(plan.remaining_work_ids)
    actual_executed = set(realization.executed_work_ids)
    missing_executed = tuple(sorted(expected_executed - actual_executed))
    unexpected_executed = tuple(sorted(actual_executed - expected_executed))
    planned_saved = predicted_savings(plan)
    realized_saved = sum(layer.actual_saved_ms for layer in realization.layers if layer.successful)
    relative_error = abs(realized_saved - planned_saved) / max(planned_saved, 1e-9)
    reconciled = not any(
        (unrealized, unplanned, wrong_owner, missing_executed, unexpected_executed)
    ) and relative_error <= tolerance
    return ReconciliationReport(
        status=ReconciliationStatus.RECONCILED if reconciled else ReconciliationStatus.DIVERGED,
        planned_saved_ms=planned_saved,
        realized_saved_ms=realized_saved,
        relative_error=relative_error,
        unrealized_work_ids=unrealized,
        unplanned_work_ids=unplanned,
        wrong_owner_work_ids=wrong_owner,
        missing_executed_work_ids=missing_executed,
        unexpected_executed_work_ids=unexpected_executed,
    )


def layer_order() -> tuple[CacheLayer, ...]:
    return _LAYER_ORDER


__all__ = [
    "AttributionLedger",
    "BudgetUsage",
    "CacheLayer",
    "DagWorkUnit",
    "LayerProbeResult",
    "MultiLayerCacheCoordinator",
    "NegativeBackoff",
    "NegativeBackoffEntry",
    "NegativeBackoffPolicy",
    "PlanRealization",
    "PlannedLayer",
    "ProbeOutcome",
    "RealizedLayer",
    "ReconciliationReport",
    "ReconciliationStatus",
    "ReuseAttribution",
    "ReuseBudgets",
    "ReuseDecision",
    "ReuseIdentity",
    "ReusePlan",
    "ReuseRequest",
    "Singleflight",
    "VerifiedBoundary",
    "WaiterCancelled",
    "WorkDependency",
    "accepted_layers",
    "layer_order",
    "predicted_savings",
    "reconcile_plan",
]
