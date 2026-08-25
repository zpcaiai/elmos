"""DAG-aware future reuse: ELMOS usually knows what happens next.

A general-purpose cache guesses the future from the past because that is all it
has. ELMOS has the actual conversion plan: which nodes run, in what order, and
which artifacts each one consumes. That turns three normally-heuristic
decisions into arithmetic:

- **What to protect.** An artifact whose consumer runs inside the horizon is
  not a candidate for eviction, whatever its recency says.
- **What to fetch, and when.** A remote object can be pulled while its
  consumer's predecessors are still running -- but only when the transfer is
  cheaper than the rebuild it saves, and only inside a declared bandwidth and
  concurrency budget.
- **Whether to fetch at all.** When a slow link makes restoring a 600 MB build
  output slower than deterministically rebuilding it, the right move is to
  bypass the cache. `SOTA-08` is exactly this case.

Two rules keep this from becoming a way to smuggle prediction into correctness:
prefetch never changes an ActionKey, a stage order, a side effect or a
publication; and only *declared* dependencies drive it. There is no file
discovery here, and a mispredicted prefetch costs bandwidth, never correctness.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .canonical import digest_of
from .dag import ConversionDag, DagNode
from .errors import ContractViolation

SCHEMA_VERSION = "1.1.0"


@dataclass(frozen=True)
class Artifact:
    """One immutable input, as the scheduler sees it."""

    key: str
    size_bytes: int
    restore_ms: float
    recompute_ms: float
    resident: bool = False
    remote: bool = True

    @property
    def net_benefit_ms(self) -> float:
        return max(self.recompute_ms - self.restore_ms, 0.0)

    @property
    def cost_density(self) -> float:
        return self.net_benefit_ms / max(self.size_bytes, 1)


@dataclass(frozen=True)
class PrefetchDecision:
    key: str
    consumer_node: str
    issue_at_position: int
    expected_benefit_ms: float
    transfer_ms: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "consumer_node": self.consumer_node,
            "issue_at_position": self.issue_at_position,
            "expected_benefit_ms": round(self.expected_benefit_ms, 6),
            "transfer_ms": round(self.transfer_ms, 6),
            "reason": self.reason,
        }


class PrefetchReason(str, Enum):
    ISSUED = "ISSUED"
    SKIPPED_ALREADY_RESIDENT = "SKIPPED_ALREADY_RESIDENT"
    SKIPPED_NOT_REMOTE = "SKIPPED_NOT_REMOTE"
    SKIPPED_BENEFIT_BELOW_COST = "SKIPPED_BENEFIT_BELOW_COST"
    SKIPPED_BANDWIDTH_BUDGET = "SKIPPED_BANDWIDTH_BUDGET"
    SKIPPED_CONCURRENCY_BUDGET = "SKIPPED_CONCURRENCY_BUDGET"
    SKIPPED_BEYOND_HORIZON = "SKIPPED_BEYOND_HORIZON"
    CANCELLED_BRANCH_RESOLVED = "CANCELLED_BRANCH_RESOLVED"
    BYPASS_RECOMPUTE_CHEAPER = "BYPASS_RECOMPUTE_CHEAPER"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class FutureUseIndex:
    """Which artifact is needed next, and how far away that is.

    Built from the *planned* order, so "next use" is knowledge rather than
    prediction. `known_future` records that distinction, because a metric that
    mixes the two is how a paper's prefetch precision stops meaning anything.
    """

    def __init__(
        self,
        order: Sequence[str],
        consumes: Mapping[str, Sequence[str]],
        artifacts: Mapping[str, Artifact],
        produces: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        self.order = tuple(order)
        self.consumes = {node: tuple(keys) for node, keys in consumes.items()}
        self.produces = {node: tuple(keys) for node, keys in (produces or {}).items()}
        self.artifacts = dict(artifacts)
        self._positions: dict[str, list[int]] = {}
        for position, node_id in enumerate(self.order):
            for key in self.consumes.get(node_id, ()):  # declared inputs only
                self._positions.setdefault(key, []).append(position)
        unknown = set(self.consumes) - set(self.order)
        if unknown:
            raise ContractViolation("consumers outside the planned order", nodes=sorted(unknown))

    @classmethod
    def from_dag(
        cls,
        dag: ConversionDag,
        artifacts: Mapping[str, Artifact],
        *,
        produces: Mapping[str, Sequence[str]] | None = None,
    ) -> FutureUseIndex:
        """Take the order and the edges from the real DAG, not from a guess.

        A node consumes whatever its declared dependencies produce; when the
        caller does not supply a producer map, a node's ``logical_outputs`` are
        used, which is the same declaration the cache keys on.
        """
        order = dag.topological_order()
        outputs = {
            node.node_id: tuple(produces[node.node_id])
            if produces and node.node_id in produces
            else tuple(node.logical_outputs)
            for node in dag.nodes
        }
        consumes: dict[str, list[str]] = {}
        for node_id in order:
            wanted: list[str] = []
            for dependency in dag.dependencies(node_id):
                wanted.extend(outputs.get(dependency, ()))
            consumes[node_id] = wanted
        return cls(order, consumes, artifacts, produces=outputs)

    def next_use(self, key: str, position: int) -> int | None:
        """Distance in scheduled steps to the next consumer, or ``None``."""
        upcoming = [item for item in self._positions.get(key, ()) if item >= position]
        return (upcoming[0] - position) if upcoming else None

    def known_future(self, key: str) -> bool:
        return key in self._positions

    def protected_keys(self, position: int, horizon: int) -> frozenset[str]:
        """Everything a consumer will need within ``horizon`` scheduled steps."""
        protected = set()
        for key in self._positions:
            distance = self.next_use(key, position)
            if distance is not None and distance <= horizon:
                protected.add(key)
        return frozenset(protected)

    def victim_rank(self, key: str, position: int) -> tuple[float, float, str]:
        """Sort key for eviction: furthest next use first, then cheapest to rebuild.

        Belady evicts the furthest future reference. ELMOS cannot do that in
        general, but inside the planned window it can, and outside it falls back
        to cost density -- which is the honest version of "we do not know".
        """
        distance = self.next_use(key, position)
        artifact = self.artifacts.get(key)
        density = artifact.cost_density if artifact else 0.0
        return (-(distance if distance is not None else 1e9), density, key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "order": list(self.order),
            "artifacts": len(self.artifacts),
            "known_future_keys": len(self._positions),
            "digest": digest_of(
                {"order": list(self.order), "consumes": {k: list(v) for k, v in sorted(self.consumes.items())}}
            ),
        }


@dataclass
class PrefetchBudget:
    """The bounds a prefetcher may not exceed, whatever it predicts."""

    horizon: int = 4
    max_in_flight: int = 4
    max_bytes: int = 512 * 1024 * 1024
    bandwidth_bytes_per_ms: float = 20_000.0
    per_tenant_bytes: int = 256 * 1024 * 1024

    def transfer_ms(self, size_bytes: int) -> float:
        return size_bytes / max(self.bandwidth_bytes_per_ms, 1e-9)


@dataclass
class PrefetchMetrics:
    issued: int = 0
    used: int = 0
    late: int = 0
    cancelled: int = 0
    wasted_bytes: int = 0
    fetched_bytes: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    critical_path_saved_ms: float = 0.0

    @property
    def precision(self) -> float:
        """Of what was fetched, how much was actually used."""
        return self.used / self.issued if self.issued else 0.0

    @property
    def late_rate(self) -> float:
        return self.late / self.issued if self.issued else 0.0

    def coverage(self, opportunities: int) -> float:
        return self.used / opportunities if opportunities else 0.0

    def to_dict(self, opportunities: int = 0) -> dict[str, Any]:
        return {
            "issued": self.issued,
            "used": self.used,
            "late": self.late,
            "cancelled": self.cancelled,
            "wasted_bytes": self.wasted_bytes,
            "fetched_bytes": self.fetched_bytes,
            "precision": round(self.precision, 6),
            "late_rate": round(self.late_rate, 6),
            "coverage": round(self.coverage(opportunities), 6),
            "critical_path_saved_ms": round(self.critical_path_saved_ms, 6),
            "skipped": dict(sorted(self.skipped.items())),
        }


class PrefetchPlanner:
    """Issue, cancel and account for prefetches inside a declared budget."""

    def __init__(self, index: FutureUseIndex, budget: PrefetchBudget | None = None) -> None:
        self.index = index
        self.budget = budget or PrefetchBudget()
        self.metrics = PrefetchMetrics()
        self.in_flight: dict[str, PrefetchDecision] = {}
        self.completed: set[str] = set()

    def plan(self, position: int, resident: Iterable[str] = ()) -> list[PrefetchDecision]:
        """What to fetch now, in earliest-beneficial-use order."""
        resident_keys = set(resident)
        candidates: list[tuple[int, str]] = []
        for key in self.index.artifacts:
            distance = self.index.next_use(key, position)
            if distance is None:
                continue
            if distance > self.budget.horizon:
                self._skip(PrefetchReason.SKIPPED_BEYOND_HORIZON)
                continue
            candidates.append((distance, key))

        issued: list[PrefetchDecision] = []
        bytes_planned = 0
        for distance, key in sorted(candidates):
            artifact = self.index.artifacts[key]
            if key in resident_keys or artifact.resident or key in self.completed:
                self._skip(PrefetchReason.SKIPPED_ALREADY_RESIDENT)
                continue
            if not artifact.remote:
                self._skip(PrefetchReason.SKIPPED_NOT_REMOTE)
                continue
            if key in self.in_flight:
                continue
            transfer = self.budget.transfer_ms(artifact.size_bytes)
            if transfer >= artifact.recompute_ms:
                # Fetching costs more than rebuilding: this is a bypass, and it
                # is a decision worth recording rather than a silent skip.
                self._skip(PrefetchReason.BYPASS_RECOMPUTE_CHEAPER)
                continue
            if artifact.net_benefit_ms <= transfer:
                self._skip(PrefetchReason.SKIPPED_BENEFIT_BELOW_COST)
                continue
            # ``in_flight`` already includes what this call has issued.
            if len(self.in_flight) >= self.budget.max_in_flight:
                self._skip(PrefetchReason.SKIPPED_CONCURRENCY_BUDGET)
                continue
            if bytes_planned + artifact.size_bytes > self.budget.max_bytes:
                self._skip(PrefetchReason.SKIPPED_BANDWIDTH_BUDGET)
                continue

            decision = PrefetchDecision(
                key=key,
                consumer_node=self.index.order[min(position + distance, len(self.index.order) - 1)],
                issue_at_position=position,
                expected_benefit_ms=artifact.net_benefit_ms,
                transfer_ms=transfer,
                reason=PrefetchReason.ISSUED.value,
            )
            issued.append(decision)
            self.in_flight[key] = decision
            bytes_planned += artifact.size_bytes
            self.metrics.issued += 1
            self.metrics.fetched_bytes += artifact.size_bytes
        return issued

    def _skip(self, reason: PrefetchReason) -> None:
        self.metrics.skipped[reason.value] = self.metrics.skipped.get(reason.value, 0) + 1

    def complete(self, key: str) -> None:
        """A transfer finished before its consumer needed it."""
        if key in self.in_flight:
            del self.in_flight[key]
            self.completed.add(key)

    def cancel(
        self, keys: Iterable[str], reason: str = PrefetchReason.CANCELLED_BRANCH_RESOLVED.value
    ) -> int:
        """A branch resolved the other way; stop paying for what it needed."""
        cancelled = 0
        for key in list(keys):
            decision = self.in_flight.pop(key, None)
            if decision is None:
                continue
            cancelled += 1
            self.metrics.cancelled += 1
            self.metrics.skipped[reason] = self.metrics.skipped.get(reason, 0) + 1
            artifact = self.index.artifacts.get(key)
            if artifact is not None:
                self.metrics.wasted_bytes += artifact.size_bytes
                self.metrics.fetched_bytes -= artifact.size_bytes
        return cancelled

    def observe_consumption(self, key: str, *, arrived_in_time: bool) -> None:
        """Record whether a prefetched object was actually used, and in time."""
        if key not in self.completed and key not in self.in_flight:
            return
        self.metrics.used += 1
        artifact = self.index.artifacts.get(key)
        if not arrived_in_time:
            self.metrics.late += 1
        elif artifact is not None:
            self.metrics.critical_path_saved_ms += artifact.net_benefit_ms
        self.complete(key)

    def observe_unused(self, key: str) -> None:
        """A prefetched object nobody consumed: pure waste, counted as such."""
        artifact = self.index.artifacts.get(key)
        if artifact is not None and (key in self.completed or key in self.in_flight):
            self.metrics.wasted_bytes += artifact.size_bytes
        self.in_flight.pop(key, None)
        self.completed.discard(key)

    def should_throttle(self, minimum_precision: float = 0.5, minimum_samples: int = 8) -> bool:
        """Wrong predictions have to be able to switch this off."""
        if self.metrics.issued < minimum_samples:
            return False
        return self.metrics.precision < minimum_precision


def restore_or_recompute(
    artifact: Artifact, budget: PrefetchBudget, *, decompression_ms: float = 0.0
) -> tuple[str, dict[str, Any]]:
    """Fetch it or rebuild it -- whichever actually finishes sooner.

    On a slow link a large deterministic artifact is faster to rebuild than to
    download, and a cache that always restores is then making the build slower
    while reporting a hit.
    """
    transfer = budget.transfer_ms(artifact.size_bytes) + artifact.restore_ms + decompression_ms
    explanation = {
        "key": artifact.key,
        "transfer_ms": round(transfer, 6),
        "recompute_ms": round(artifact.recompute_ms, 6),
        "size_bytes": artifact.size_bytes,
    }
    if transfer >= artifact.recompute_ms:
        explanation["reason"] = PrefetchReason.BYPASS_RECOMPUTE_CHEAPER.value
        return "RECOMPUTE", explanation
    explanation["reason"] = "RESTORE_CHEAPER"
    return "RESTORE", explanation


@dataclass(frozen=True)
class Placement:
    node_id: str
    worker: str
    reason: str
    resident_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "worker": self.worker,
            "reason": self.reason,
            "resident_bytes": self.resident_bytes,
        }


class LocalityScheduler:
    """Prefer the worker that already holds the inputs -- within limits.

    Cache locality is worth real time, but a scheduler that only chases it
    starves workers and inverts the critical path. So a worker is preferred
    only while it is under its fair share; past that, locality loses.
    """

    def __init__(
        self,
        index: FutureUseIndex,
        workers: Sequence[str],
        *,
        fair_share_slack: float = 1.5,
    ) -> None:
        if not workers:
            raise ContractViolation("at least one worker is required")
        self.index = index
        self.workers = tuple(workers)
        self.fair_share_slack = fair_share_slack
        self.resident: dict[str, set[str]] = {worker: set() for worker in workers}
        self.assigned: dict[str, int] = {worker: 0 for worker in workers}

    def place(self, node: DagNode | str) -> Placement:
        node_id = node if isinstance(node, str) else node.node_id
        wanted = set(self.index.consumes.get(node_id, ()))
        produced = set(self.index.produces.get(node_id, ()))
        total_assigned = sum(self.assigned.values()) or 1
        fair_share = total_assigned / len(self.workers)

        best_worker = None
        best_bytes = -1
        for worker in self.workers:
            if self.assigned[worker] > fair_share * self.fair_share_slack:
                continue  # this worker is already carrying more than its share
            held = wanted & self.resident[worker]
            resident_bytes = sum(
                self.index.artifacts[key].size_bytes for key in held if key in self.index.artifacts
            )
            if resident_bytes > best_bytes:
                best_worker, best_bytes = worker, resident_bytes

        if best_worker is None or best_bytes <= 0:
            # Nothing to be gained from locality: balance instead.
            best_worker = min(self.workers, key=lambda worker: (self.assigned[worker], worker))
            reason = "BALANCED"
            best_bytes = 0
        else:
            reason = "CACHE_LOCALITY"
        self.assigned[best_worker] += 1
        # After the node runs, both its inputs and its outputs are on that
        # worker; that is what the *next* node's locality decision sees.
        self.resident[best_worker].update(wanted | produced)
        return Placement(node_id, best_worker, reason, max(best_bytes, 0))

    def mark_resident(self, worker: str, keys: Iterable[str]) -> None:
        self.resident.setdefault(worker, set()).update(keys)
