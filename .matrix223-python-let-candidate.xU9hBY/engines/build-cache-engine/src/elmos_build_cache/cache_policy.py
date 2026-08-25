"""The cache policy portfolio: one SPI, six production policies.

ELMOS objects are not homogeneous web objects. A 20 KB symbol table, a 5 MB
semantic IR partition and a 600 MB native build output differ by orders of
magnitude in size, transfer time, recomputation cost and critical-path impact,
so a single global LRU is not an architecture -- it is an assumption. This
module implements the portfolio the SOTA specification requires behind one
interface, so a deployment can choose per tier and a benchmark can compare them
on identical traces.

Three rules hold for every policy here, and they are what separate a cache
policy from a correctness decision:

1. **Policy never decides validity.** Exact ActionKeys, immutable CAS digests,
   validation levels, trust namespaces and tenant authorization are checked
   before a policy is consulted. A policy only answers "keep, admit, or evict".
2. **Protected roots are never victims.** Active runs, checkpoints, published
   trees, pins and legal holds are protected; when the only remaining victims
   are protected, admission is *refused* with a reason rather than protection
   being broken.
3. **Every decision carries a reason code.** An operator asking why an object
   was not admitted gets an answer from the policy, not from a guess.

Policies are deterministic: the same sequence of accesses against the same
configuration produces the same decisions and the same counters. That is what
makes the replay simulator's comparisons meaningful, and it is asserted by
`SOTA-01` in the acceptance matrix.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import OrderedDict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .canonical import digest_of
from .errors import ContractViolation

SCHEMA_VERSION = "1.1.0"


class PolicyName(str, Enum):
    """The fixed policies. Adaptive selection composes these, never replaces them."""

    LRU = "LRU"
    SIEVE = "SIEVE"
    S3_FIFO = "S3_FIFO"
    W_TINY_LFU = "W_TINY_LFU"
    SIZE_AWARE_TINY_LFU = "SIZE_AWARE_TINY_LFU"
    GDSF = "GDSF"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class Reason(str, Enum):
    """Why a policy did what it did. Closed set: an operator can grep for these."""

    HIT = "HIT"
    ADMITTED = "ADMITTED"
    ADMITTED_FROM_GHOST = "ADMITTED_FROM_GHOST"
    PROMOTED = "PROMOTED"
    PROTECTED = "PROTECTED"
    OBJECT_EXCEEDS_CAPACITY = "OBJECT_EXCEEDS_CAPACITY"
    CAPACITY_FULLY_PROTECTED = "CAPACITY_FULLY_PROTECTED"
    REJECTED_BY_FREQUENCY = "REJECTED_BY_FREQUENCY"
    REJECTED_BY_VALUE_DENSITY = "REJECTED_BY_VALUE_DENSITY"
    EVICTED_LRU = "EVICTED_LRU"
    EVICTED_SIEVE_UNVISITED = "EVICTED_SIEVE_UNVISITED"
    EVICTED_SMALL_QUEUE = "EVICTED_SMALL_QUEUE"
    EVICTED_MAIN_QUEUE = "EVICTED_MAIN_QUEUE"
    EVICTED_WINDOW = "EVICTED_WINDOW"
    EVICTED_PROBATION = "EVICTED_PROBATION"
    EVICTED_LOWEST_VALUE_DENSITY = "EVICTED_LOWEST_VALUE_DENSITY"


@dataclass(frozen=True)
class CacheObject:
    """What a policy is allowed to know about an object.

    Deliberately numeric and hashed: no paths, no source, no prompts, no tenant
    names. The same shape is what the trace records, so a replayed decision is
    the decision production would have taken.
    """

    key: str
    size_bytes: int
    recompute_ms: float = 1.0
    restore_ms: float = 0.0
    model_tokens: int = 0
    critical_path_weight: float = 0.0
    stage_class: str = "unknown"
    validation_level: str = "UNVERIFIED"
    tenant_hash: str = ""
    next_use_distance: int | None = None

    def __post_init__(self) -> None:
        if self.size_bytes < 0:
            raise ContractViolation("size_bytes must be non-negative", key=self.key)
        if self.recompute_ms < 0 or self.restore_ms < 0:
            raise ContractViolation("costs must be non-negative", key=self.key)

    @property
    def net_recompute_ms(self) -> float:
        """What is actually saved by a hit: recompute minus the restore it costs."""
        return max(self.recompute_ms - self.restore_ms, 0.0)


@dataclass(frozen=True)
class Decision:
    """The outcome of one access, with the reasons that produced it."""

    hit: bool
    admitted: bool
    evicted: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    bypass_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hit": self.hit,
            "admitted": self.admitted,
            "evicted": list(self.evicted),
            "reasons": list(self.reasons),
            "bypass_reason": self.bypass_reason,
        }


@dataclass
class PolicyCounters:
    """Bounded-overhead accounting every policy exposes."""

    hits: int = 0
    misses: int = 0
    admissions: int = 0
    rejections: int = 0
    evictions: int = 0
    protected_skips: int = 0
    invalidations: int = 0
    bytes_admitted: int = 0
    bytes_evicted: int = 0
    metadata_entries: int = 0
    peak_metadata_entries: int = 0

    @property
    def churn(self) -> float:
        """Evictions per admission: the write-amplification proxy."""
        return self.evictions / self.admissions if self.admissions else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "admissions": self.admissions,
            "rejections": self.rejections,
            "evictions": self.evictions,
            "protected_skips": self.protected_skips,
            "invalidations": self.invalidations,
            "bytes_admitted": self.bytes_admitted,
            "bytes_evicted": self.bytes_evicted,
            "metadata_entries": self.metadata_entries,
            "peak_metadata_entries": self.peak_metadata_entries,
            "churn": round(self.churn, 6),
        }


@dataclass
class _Entry:
    key: str
    size_bytes: int
    recompute_ms: float
    restore_ms: float
    frequency: int = 0
    visited: bool = False
    priority: float = 0.0

    @property
    def value_density(self) -> float:
        """Saved work per byte held. The unit a size-aware policy compares."""
        return max(self.recompute_ms - self.restore_ms, 0.001) / max(self.size_bytes, 1)


class CachePolicy(ABC):
    """The SPI. Everything else in ELMOS talks to a policy through this."""

    name: PolicyName = PolicyName.LRU
    #: Attributes holding resident ``_Entry`` objects, for invalidation.
    _STORES: tuple[str, ...] = ("_entries",)

    def __init__(self, capacity_bytes: int) -> None:
        if capacity_bytes <= 0:
            raise ContractViolation("capacity_bytes must be positive", capacity=capacity_bytes)
        self.capacity_bytes = capacity_bytes
        self.used_bytes = 0
        self.counters = PolicyCounters()
        self._protected: set[str] = set()

    # -- protected roots ---------------------------------------------------
    def protect(self, key: str) -> None:
        """Mark an object unevictable: an active run, checkpoint, pin or hold."""
        self._protected.add(key)

    def unprotect(self, key: str) -> None:
        self._protected.discard(key)

    def protected(self) -> frozenset[str]:
        return frozenset(self._protected)

    def is_protected(self, key: str) -> bool:
        return key in self._protected

    # -- the operation ------------------------------------------------------
    def access(self, obj: CacheObject) -> Decision:
        """One GET. A hit updates policy state; a miss may admit and evict."""
        entry = self._lookup(obj.key)
        if entry is not None:
            self._assert_immutable(entry, obj)
            self.counters.hits += 1
            self._on_hit(entry)
            return Decision(hit=True, admitted=True, reasons=(Reason.HIT.value,))

        self.counters.misses += 1
        if obj.size_bytes > self.capacity_bytes:
            self.counters.rejections += 1
            return Decision(
                hit=False,
                admitted=False,
                reasons=(Reason.OBJECT_EXCEEDS_CAPACITY.value,),
                bypass_reason=Reason.OBJECT_EXCEEDS_CAPACITY.value,
            )
        decision = self._on_miss(obj)
        if decision.admitted:
            self.counters.admissions += 1
            self.counters.bytes_admitted += obj.size_bytes
        else:
            self.counters.rejections += 1
        self._record_metadata_size()
        return decision

    def put(self, obj: CacheObject) -> Decision:
        """An explicit PUT. Same admission path as a miss, without counting a miss."""
        if self._lookup(obj.key) is not None:
            return Decision(hit=True, admitted=True, reasons=(Reason.HIT.value,))
        if obj.size_bytes > self.capacity_bytes:
            self.counters.rejections += 1
            return Decision(
                False, False, reasons=(Reason.OBJECT_EXCEEDS_CAPACITY.value,),
                bypass_reason=Reason.OBJECT_EXCEEDS_CAPACITY.value,
            )
        decision = self._on_miss(obj)
        if decision.admitted:
            self.counters.admissions += 1
            self.counters.bytes_admitted += obj.size_bytes
        else:
            self.counters.rejections += 1
        self._record_metadata_size()
        return decision

    def contains(self, key: str) -> bool:
        return self._lookup(key) is not None

    def forget(self, key: str) -> bool:
        """Drop an entry the correctness plane has invalidated.

        This is not an eviction and must never be counted as one: the object
        did not lose a capacity contest, it stopped being valid (revoked,
        quarantined, or its run was cancelled). Ghost/history state is left
        alone, because a content-addressed key that comes back is the same
        bytes and its past frequency is still evidence.
        """
        removed = False
        for attribute in self._STORES:
            store = getattr(self, attribute, None)
            if not isinstance(store, dict):
                continue
            entry = store.pop(key, None)
            if entry is not None:
                self.used_bytes -= entry.size_bytes
                removed = True
        if removed:
            self.counters.invalidations += 1
            self._record_metadata_size()
        return removed

    def resize(self, capacity_bytes: int) -> tuple[str, ...]:
        """Shrink or grow in place, evicting only what the new bound requires."""
        if capacity_bytes <= 0:
            raise ContractViolation("capacity_bytes must be positive", capacity=capacity_bytes)
        self.capacity_bytes = capacity_bytes
        evicted: list[str] = []
        while self.used_bytes > self.capacity_bytes:
            victim = self._evict_one()
            if victim is None:
                break
            evicted.append(victim)
        return tuple(evicted)

    # -- state --------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """Serialise policy state so a restart does not throw away history."""
        return {
            "schema_version": SCHEMA_VERSION,
            "policy": self.name.value,
            "capacity_bytes": self.capacity_bytes,
            "used_bytes": self.used_bytes,
            "protected": sorted(self._protected),
            "counters": self.counters.to_dict(),
            "state": self._snapshot_state(),
        }

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        if snapshot.get("policy") != self.name.value:
            raise ContractViolation(
                "policy snapshot belongs to another policy",
                expected=self.name.value,
                found=snapshot.get("policy"),
            )
        if snapshot.get("schema_version") != SCHEMA_VERSION:
            raise ContractViolation("policy snapshot schema mismatch", found=snapshot.get("schema_version"))
        self.capacity_bytes = int(snapshot["capacity_bytes"])
        self._protected = set(snapshot.get("protected", ()))
        self._restore_state(snapshot["state"])
        self.used_bytes = int(snapshot["used_bytes"])

    def state_digest(self) -> str:
        """Fingerprint of the *policy state*, deliberately excluding counters.

        Counters are per-process observability; policy state is what a restart
        has to reproduce. Keeping them apart is what lets a restored policy be
        compared to the one that was snapshotted.
        """
        snapshot = self.snapshot()
        snapshot.pop("counters", None)
        return digest_of(snapshot)

    def explain(self, key: str) -> dict[str, Any]:
        """What the policy currently knows about one key."""
        entry = self._lookup(key)
        if entry is None:
            return {"key": key, "present": False, "protected": self.is_protected(key)}
        return {
            "key": key,
            "present": True,
            "protected": self.is_protected(key),
            "size_bytes": entry.size_bytes,
            "frequency": entry.frequency,
            "visited": entry.visited,
            "value_density": round(entry.value_density, 9),
            "policy": self.name.value,
        }

    def keys(self) -> tuple[str, ...]:
        return tuple(self._iter_keys())

    # -- hooks --------------------------------------------------------------
    @abstractmethod
    def _lookup(self, key: str) -> _Entry | None: ...

    @abstractmethod
    def _on_hit(self, entry: _Entry) -> None: ...

    @abstractmethod
    def _on_miss(self, obj: CacheObject) -> Decision: ...

    @abstractmethod
    def _evict_one(self) -> str | None:
        """Remove exactly one unprotected victim, or return ``None``."""

    @abstractmethod
    def _iter_keys(self) -> Iterable[str]: ...

    @abstractmethod
    def _snapshot_state(self) -> dict[str, Any]: ...

    @abstractmethod
    def _restore_state(self, state: Mapping[str, Any]) -> None: ...

    # -- shared helpers -----------------------------------------------------
    @staticmethod
    def _assert_immutable(entry: _Entry, obj: CacheObject) -> None:
        """An exact key identifies immutable bytes; a size change is a broken key."""
        if entry.size_bytes != obj.size_bytes:
            raise ContractViolation(
                "immutable cache key changed size",
                key=obj.key,
                held=entry.size_bytes,
                offered=obj.size_bytes,
            )

    def _make_room(self, size_bytes: int) -> tuple[list[str], str | None]:
        """Evict until ``size_bytes`` fits, or report why it cannot."""
        evicted: list[str] = []
        while self.used_bytes + size_bytes > self.capacity_bytes:
            victim = self._evict_one()
            if victim is None:
                self.counters.protected_skips += 1
                return evicted, Reason.CAPACITY_FULLY_PROTECTED.value
            evicted.append(victim)
        return evicted, None

    def _record_metadata_size(self) -> None:
        count = self._metadata_entries()
        self.counters.metadata_entries = count
        self.counters.peak_metadata_entries = max(self.counters.peak_metadata_entries, count)

    def _metadata_entries(self) -> int:
        return len(tuple(self._iter_keys()))

    @staticmethod
    def _entry_to_dict(entry: _Entry) -> dict[str, Any]:
        return {
            "key": entry.key,
            "size_bytes": entry.size_bytes,
            "recompute_ms": entry.recompute_ms,
            "restore_ms": entry.restore_ms,
            "frequency": entry.frequency,
            "visited": entry.visited,
            "priority": entry.priority,
        }

    @staticmethod
    def _entry_from_dict(value: Mapping[str, Any]) -> _Entry:
        return _Entry(
            key=str(value["key"]),
            size_bytes=int(value["size_bytes"]),
            recompute_ms=float(value["recompute_ms"]),
            restore_ms=float(value["restore_ms"]),
            frequency=int(value.get("frequency", 0)),
            visited=bool(value.get("visited", False)),
            priority=float(value.get("priority", 0.0)),
        )

    @staticmethod
    def _entry_of(obj: CacheObject) -> _Entry:
        return _Entry(
            key=obj.key,
            size_bytes=obj.size_bytes,
            recompute_ms=obj.recompute_ms,
            restore_ms=obj.restore_ms,
            frequency=1,
        )


# ==========================================================================
# LRU -- the baseline, kept honest about being one
# ==========================================================================
class LruPolicy(CachePolicy):
    """Recency only. Retained as a mandatory baseline, not as a default.

    Every claim that a newer policy wins is measured against this, at equal
    capacity, on the same trace.
    """

    name = PolicyName.LRU

    def __init__(self, capacity_bytes: int) -> None:
        super().__init__(capacity_bytes)
        self._entries: OrderedDict[str, _Entry] = OrderedDict()

    def _lookup(self, key: str) -> _Entry | None:
        return self._entries.get(key)

    def _on_hit(self, entry: _Entry) -> None:
        entry.frequency += 1
        self._entries.move_to_end(entry.key)

    def _on_miss(self, obj: CacheObject) -> Decision:
        evicted, blocked = self._make_room(obj.size_bytes)
        if blocked is not None:
            return Decision(False, False, tuple(evicted), (blocked,), bypass_reason=blocked)
        self._entries[obj.key] = self._entry_of(obj)
        self.used_bytes += obj.size_bytes
        return Decision(False, True, tuple(evicted), (Reason.ADMITTED.value,))

    def _evict_one(self) -> str | None:
        for key in list(self._entries):
            if self.is_protected(key):
                continue
            entry = self._entries.pop(key)
            self.used_bytes -= entry.size_bytes
            self.counters.evictions += 1
            self.counters.bytes_evicted += entry.size_bytes
            return key
        return None

    def _iter_keys(self) -> Iterable[str]:
        return tuple(self._entries)

    def _snapshot_state(self) -> dict[str, Any]:
        return {"entries": [self._entry_to_dict(entry) for entry in self._entries.values()]}

    def _restore_state(self, state: Mapping[str, Any]) -> None:
        self._entries = OrderedDict(
            (str(item["key"]), self._entry_from_dict(item)) for item in state["entries"]
        )


# ==========================================================================
# SIEVE -- NSDI 2024
# ==========================================================================
class SievePolicy(CachePolicy):
    """FIFO order plus a visited bit, swept by a moving hand.

    A hit sets a bit and touches nothing else -- no list reordering, no lock on
    the hit path -- which is why it holds up under the concurrency a local CAS
    sees. The sweep clears visited bits as it passes, so a scan that touches
    each object once cannot promote itself past objects that are actually
    reused.
    """

    name = PolicyName.SIEVE

    def __init__(self, capacity_bytes: int) -> None:
        super().__init__(capacity_bytes)
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._hand: int = 0

    def _lookup(self, key: str) -> _Entry | None:
        return self._entries.get(key)

    def _on_hit(self, entry: _Entry) -> None:
        entry.frequency += 1
        entry.visited = True  # the whole hit path

    def _on_miss(self, obj: CacheObject) -> Decision:
        evicted, blocked = self._make_room(obj.size_bytes)
        if blocked is not None:
            return Decision(False, False, tuple(evicted), (blocked,), bypass_reason=blocked)
        self._entries[obj.key] = self._entry_of(obj)
        self.used_bytes += obj.size_bytes
        return Decision(False, True, tuple(evicted), (Reason.ADMITTED.value,))

    def _evict_one(self) -> str | None:
        order = list(self._entries)
        if not order:
            return None
        index = self._hand % len(order)
        for _ in range(len(order) * 2):
            key = order[index]
            entry = self._entries[key]
            if self.is_protected(key):
                index = (index + 1) % len(order)
                continue
            if entry.visited:
                entry.visited = False
                index = (index + 1) % len(order)
                continue
            self._entries.pop(key)
            self.used_bytes -= entry.size_bytes
            self.counters.evictions += 1
            self.counters.bytes_evicted += entry.size_bytes
            self._hand = index % max(len(self._entries), 1)
            return key
        return None

    def _iter_keys(self) -> Iterable[str]:
        return tuple(self._entries)

    def _snapshot_state(self) -> dict[str, Any]:
        return {
            "hand": self._hand,
            "entries": [self._entry_to_dict(entry) for entry in self._entries.values()],
        }

    def _restore_state(self, state: Mapping[str, Any]) -> None:
        self._hand = int(state.get("hand", 0))
        self._entries = OrderedDict(
            (str(item["key"]), self._entry_from_dict(item)) for item in state["entries"]
        )


# ==========================================================================
# S3-FIFO -- SOSP 2023
# ==========================================================================
class S3FifoPolicy(CachePolicy):
    """A small FIFO filters one-hit wonders before they can pollute the main queue.

    Roughly a tenth of the capacity is a probation queue. An object evicted
    from it without a second access leaves only a *ghost* -- its key, no bytes.
    An object that comes back while its ghost is alive is admitted straight to
    the main queue. Build traces are full of objects touched exactly once, and
    this is the cheapest known way to stop them evicting the objects that are
    touched fifty times.
    """

    name = PolicyName.S3_FIFO
    _STORES = ("_small", "_main")

    def __init__(self, capacity_bytes: int, small_ratio: float = 0.1, ghost_ratio: float = 1.0) -> None:
        super().__init__(capacity_bytes)
        if not 0 < small_ratio < 1:
            raise ContractViolation("small_ratio must be in (0, 1)", small_ratio=small_ratio)
        self.small_ratio = small_ratio
        self.ghost_ratio = ghost_ratio
        self._small: OrderedDict[str, _Entry] = OrderedDict()
        self._main: OrderedDict[str, _Entry] = OrderedDict()
        self._ghost: deque[str] = deque()
        self._ghost_set: set[str] = set()

    @property
    def small_capacity(self) -> int:
        return max(int(self.capacity_bytes * self.small_ratio), 1)

    @property
    def ghost_capacity(self) -> int:
        """Remember about as many keys as the cache holds objects.

        The paper sizes the ghost queue like the main queue -- in entries, not
        bytes -- because its job is to recognise a key that comes back "soon",
        and "soon" is measured in objects. Deriving it from the current
        occupancy keeps that true for a byte-sized cache holding a handful of
        large artifacts or thousands of tiny ones.
        """
        occupancy = len(self._small) + len(self._main)
        return max(int(occupancy * self.ghost_ratio), 16)

    def _lookup(self, key: str) -> _Entry | None:
        return self._small.get(key) or self._main.get(key)

    def _on_hit(self, entry: _Entry) -> None:
        entry.frequency = min(entry.frequency + 1, 3)  # bounded, as the paper has it

    def _on_miss(self, obj: CacheObject) -> Decision:
        reasons: list[str] = []
        from_ghost = obj.key in self._ghost_set
        if from_ghost:
            self._ghost_set.discard(obj.key)
            try:
                self._ghost.remove(obj.key)
            except ValueError:  # pragma: no cover - deque/set kept in step
                pass
            reasons.append(Reason.ADMITTED_FROM_GHOST.value)
        else:
            reasons.append(Reason.ADMITTED.value)

        evicted, blocked = self._make_room(obj.size_bytes)
        if blocked is not None:
            return Decision(False, False, tuple(evicted), (blocked,), bypass_reason=blocked)

        entry = self._entry_of(obj)
        entry.frequency = 1 if from_ghost else 0
        target = self._main if from_ghost else self._small
        target[obj.key] = entry
        self.used_bytes += obj.size_bytes
        # The probation queue is drained during eviction, not eagerly on every
        # insert. Draining eagerly would mean that in a byte-sized cache whose
        # objects are large relative to capacity, every newcomer is thrown out
        # before it can prove itself -- which is the opposite of what the small
        # queue is for.
        return Decision(False, True, tuple(evicted), tuple(reasons))

    @staticmethod
    def _queue_bytes(queue: OrderedDict[str, _Entry]) -> int:
        return sum(entry.size_bytes for entry in queue.values())

    def _demote_from_small(self) -> tuple[str | None, bool]:
        """Take one object out of probation.

        Returns ``(victim, progressed)``. A promotion frees no bytes but is
        still progress -- conflating it with "nothing to evict" is how a cache
        ends up refusing admission while holding evictable objects.
        """
        for key in list(self._small):
            if self.is_protected(key):
                continue
            entry = self._small.pop(key)
            if entry.frequency >= 1:
                # Seen twice: it earns a place in the main queue.
                self._main[key] = entry
                return None, True
            self.used_bytes -= entry.size_bytes
            self.counters.evictions += 1
            self.counters.bytes_evicted += entry.size_bytes
            self._remember_ghost(key)
            return key, True
        return None, False

    def _evict_from_main(self) -> str | None:
        for _ in range(len(self._main) * 2 + 1):
            if not self._main:
                return None
            key, entry = next(iter(self._main.items()))
            self._main.pop(key)
            if self.is_protected(key):
                self._main[key] = entry  # re-queue; protection is not a demotion
                continue
            if entry.frequency > 0:
                entry.frequency -= 1
                self._main[key] = entry  # second chance
                continue
            self.used_bytes -= entry.size_bytes
            self.counters.evictions += 1
            self.counters.bytes_evicted += entry.size_bytes
            return key
        return None

    def _evict_one(self) -> str | None:
        # Promotions make progress without freeing bytes, so this keeps asking
        # until something is actually evicted or nothing can be.
        for _ in range(len(self._small) + len(self._main) + 2):
            if self._queue_bytes(self._small) > self.small_capacity or not self._main:
                victim, progressed = self._demote_from_small()
                if victim is not None:
                    return victim
                if progressed:
                    continue
            victim = self._evict_from_main()
            if victim is not None:
                return victim
            victim, progressed = self._demote_from_small()
            if victim is not None:
                return victim
            if not progressed:
                return None
        return None

    def _remember_ghost(self, key: str) -> None:
        self._ghost.append(key)
        self._ghost_set.add(key)
        while len(self._ghost) > self.ghost_capacity:
            oldest = self._ghost.popleft()
            self._ghost_set.discard(oldest)

    def _iter_keys(self) -> Iterable[str]:
        return (*self._small, *self._main)

    def _snapshot_state(self) -> dict[str, Any]:
        return {
            "small_ratio": self.small_ratio,
            "ghost_ratio": self.ghost_ratio,
            "small": [self._entry_to_dict(entry) for entry in self._small.values()],
            "main": [self._entry_to_dict(entry) for entry in self._main.values()],
            "ghost": list(self._ghost),
        }

    def _restore_state(self, state: Mapping[str, Any]) -> None:
        self.small_ratio = float(state.get("small_ratio", self.small_ratio))
        self.ghost_ratio = float(state.get("ghost_ratio", self.ghost_ratio))
        self._small = OrderedDict(
            (str(item["key"]), self._entry_from_dict(item)) for item in state["small"]
        )
        self._main = OrderedDict(
            (str(item["key"]), self._entry_from_dict(item)) for item in state["main"]
        )
        self._ghost = deque(str(key) for key in state.get("ghost", ()))
        self._ghost_set = set(self._ghost)


# ==========================================================================
# TinyLFU family
# ==========================================================================
class FrequencySketch:
    """Count-Min sketch with a doorkeeper and periodic halving.

    Frequency history for a large cache cannot be an exact counter per key --
    that is as big as the cache. This is the standard approximation: four
    hashed counters per key, a Bloom-style doorkeeper so a first sighting costs
    one bit rather than four counters, and a halving pass so the estimate
    tracks a moving workload instead of the whole history.
    """

    def __init__(self, width: int = 4096, depth: int = 4, sample_factor: int = 10) -> None:
        if width <= 0 or depth <= 0:
            raise ContractViolation("sketch dimensions must be positive", width=width, depth=depth)
        self.width = width
        self.depth = depth
        self.sample_size = width * sample_factor
        self.additions = 0
        self._table = [[0] * width for _ in range(depth)]
        self._doorkeeper = [False] * width

    def _indexes(self, key: str) -> list[int]:
        # Deterministic and stable across processes: the digest, not hash().
        digest = digest_of({"k": key}).split(":", 1)[1]
        return [
            int(digest[index * 8 : (index + 1) * 8], 16) % self.width for index in range(self.depth)
        ]

    def increment(self, key: str) -> None:
        indexes = self._indexes(key)
        door = indexes[0]
        if not self._doorkeeper[door]:
            self._doorkeeper[door] = True
            self.additions += 1
            self._maybe_reset()
            return
        for row, index in enumerate(indexes):
            if self._table[row][index] < 15:  # 4-bit counters
                self._table[row][index] += 1
        self.additions += 1
        self._maybe_reset()

    def estimate(self, key: str) -> int:
        indexes = self._indexes(key)
        counted = min(self._table[row][index] for row, index in enumerate(indexes))
        return counted + (1 if self._doorkeeper[indexes[0]] else 0)

    def _maybe_reset(self) -> None:
        if self.additions < self.sample_size:
            return
        self.additions = 0
        self._doorkeeper = [False] * self.width
        for row in range(self.depth):
            self._table[row] = [value >> 1 for value in self._table[row]]

    def snapshot(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "depth": self.depth,
            "sample_size": self.sample_size,
            "additions": self.additions,
            "table": self._table,
            "doorkeeper": [index for index, flag in enumerate(self._doorkeeper) if flag],
        }

    @classmethod
    def from_snapshot(cls, state: Mapping[str, Any]) -> FrequencySketch:
        sketch = cls(width=int(state["width"]), depth=int(state["depth"]))
        sketch.sample_size = int(state["sample_size"])
        sketch.additions = int(state["additions"])
        sketch._table = [list(map(int, row)) for row in state["table"]]
        sketch._doorkeeper = [False] * sketch.width
        for index in state.get("doorkeeper", ()):
            sketch._doorkeeper[int(index)] = True
        return sketch


class WTinyLfuPolicy(CachePolicy):
    """A small recency window in front of a frequency-admitted main cache.

    New objects land in the window, so a burst of first accesses is served
    without disturbing the main region. When the window overflows, its victim
    must *out-frequent* the main region's next victim to get in. That is what
    stops a monorepo scan from evicting the hot metadata it walks past.

    ``size_aware`` switches the comparison from frequency to frequency per
    byte, which is the right question when a 20 KB manifest and a 600 MB build
    output are competing for the same shared capacity.
    """

    name = PolicyName.W_TINY_LFU
    _STORES = ("_window", "_main")

    def __init__(
        self,
        capacity_bytes: int,
        window_ratio: float = 0.01,
        size_aware: bool = False,
        sketch: FrequencySketch | None = None,
    ) -> None:
        super().__init__(capacity_bytes)
        if not 0 < window_ratio < 1:
            raise ContractViolation("window_ratio must be in (0, 1)", window_ratio=window_ratio)
        self.window_ratio = window_ratio
        self.size_aware = size_aware
        if size_aware:
            self.name = PolicyName.SIZE_AWARE_TINY_LFU
        self.sketch = sketch or FrequencySketch()
        self._window: OrderedDict[str, _Entry] = OrderedDict()
        self._main: OrderedDict[str, _Entry] = OrderedDict()

    @property
    def window_capacity(self) -> int:
        return max(int(self.capacity_bytes * self.window_ratio), 1)

    def _lookup(self, key: str) -> _Entry | None:
        return self._window.get(key) or self._main.get(key)

    def _on_hit(self, entry: _Entry) -> None:
        entry.frequency += 1
        self.sketch.increment(entry.key)
        if entry.key in self._window:
            self._window.move_to_end(entry.key)
        else:
            self._main.move_to_end(entry.key)

    def _score(self, entry: _Entry) -> float:
        estimate = float(self.sketch.estimate(entry.key))
        if not self.size_aware:
            return estimate
        return estimate / max(entry.size_bytes, 1)

    @property
    def main_capacity(self) -> int:
        return max(self.capacity_bytes - self.window_capacity, 1)

    def _on_miss(self, obj: CacheObject) -> Decision:
        """Window first, then a frequency contest for every main-region slot.

        The order matters. Making room by plain eviction *before* the contest
        would let any newcomer displace a resident simply by arriving, which is
        exactly the behaviour TinyLFU exists to prevent: the candidate has to
        out-frequent (or, size-aware, out-value) the incumbent it would push
        out, and if it cannot, the candidate is the one that is dropped.
        """
        self.sketch.increment(obj.key)
        entry = self._entry_of(obj)
        self._window[obj.key] = entry
        self.used_bytes += obj.size_bytes
        evicted: list[str] = []
        reasons = [Reason.ADMITTED.value]

        while self._bytes(self._window) > self.window_capacity:
            candidate_key = next(iter(self._window))
            if self.is_protected(candidate_key) and len(self._window) == 1:
                break
            candidate: _Entry | None = self._window.pop(candidate_key)
            assert candidate is not None
            while self._bytes(self._main) + candidate.size_bytes > self.main_capacity:
                victim_key = self._main_victim()
                if victim_key is None:
                    break  # everything in main is protected; capacity wins below
                victim = self._main[victim_key]
                # Strictly greater: on a tie the incumbent wins. That is what
                # makes a cyclic scan unable to flush a resident set of equal
                # frequency, and it is the difference from plain FIFO.
                if self._score(candidate) > self._score(victim):
                    self._main.pop(victim_key)
                    self.used_bytes -= victim.size_bytes
                    self.counters.evictions += 1
                    self.counters.bytes_evicted += victim.size_bytes
                    evicted.append(victim_key)
                    continue
                self.used_bytes -= candidate.size_bytes
                self.counters.evictions += 1
                self.counters.bytes_evicted += candidate.size_bytes
                evicted.append(candidate_key)
                reasons.append(
                    Reason.REJECTED_BY_VALUE_DENSITY.value
                    if self.size_aware
                    else Reason.REJECTED_BY_FREQUENCY.value
                )
                candidate = None
                break
            if candidate is None:
                continue
            self._main[candidate_key] = candidate

        # Total capacity is still a hard bound: the contest can leave the main
        # region over its share when everything below it is protected.
        rejected_by_value = obj.key in evicted
        while self.used_bytes > self.capacity_bytes:
            victim_key = self._evict_one()
            if victim_key is None:
                break
            evicted.append(victim_key)
            if victim_key == obj.key:
                # Nothing evictable was worth less than the newcomer, so the
                # newcomer is what gives way. Protection is not negotiable.
                self.counters.protected_skips += 1
                return Decision(
                    False,
                    False,
                    tuple(evicted),
                    (*reasons, Reason.CAPACITY_FULLY_PROTECTED.value),
                    bypass_reason=Reason.CAPACITY_FULLY_PROTECTED.value,
                )

        if obj.key not in self._window and obj.key not in self._main:
            return Decision(
                False,
                False,
                tuple(evicted),
                tuple(reasons),
                bypass_reason=None if rejected_by_value else Reason.CAPACITY_FULLY_PROTECTED.value,
            )
        return Decision(False, True, tuple(evicted), tuple(reasons))

    @staticmethod
    def _bytes(queue: OrderedDict[str, _Entry]) -> int:
        return sum(entry.size_bytes for entry in queue.values())

    def _main_victim(self) -> str | None:
        for key in self._main:
            if not self.is_protected(key):
                return key
        return None

    def _evict_one(self) -> str | None:
        for source, reason in ((self._main, Reason.EVICTED_PROBATION), (self._window, Reason.EVICTED_WINDOW)):
            for key in list(source):
                if self.is_protected(key):
                    continue
                entry = source.pop(key)
                self.used_bytes -= entry.size_bytes
                self.counters.evictions += 1
                self.counters.bytes_evicted += entry.size_bytes
                del reason
                return key
        return None

    def _iter_keys(self) -> Iterable[str]:
        return (*self._window, *self._main)

    def _snapshot_state(self) -> dict[str, Any]:
        return {
            "window_ratio": self.window_ratio,
            "size_aware": self.size_aware,
            "window": [self._entry_to_dict(entry) for entry in self._window.values()],
            "main": [self._entry_to_dict(entry) for entry in self._main.values()],
            "sketch": self.sketch.snapshot(),
        }

    def _restore_state(self, state: Mapping[str, Any]) -> None:
        self.window_ratio = float(state["window_ratio"])
        self.size_aware = bool(state["size_aware"])
        self._window = OrderedDict(
            (str(item["key"]), self._entry_from_dict(item)) for item in state["window"]
        )
        self._main = OrderedDict(
            (str(item["key"]), self._entry_from_dict(item)) for item in state["main"]
        )
        self.sketch = FrequencySketch.from_snapshot(state["sketch"])


class SizeAwareTinyLfuPolicy(WTinyLfuPolicy):
    """W-TinyLFU that compares frequency per byte rather than frequency."""

    name = PolicyName.SIZE_AWARE_TINY_LFU

    def __init__(self, capacity_bytes: int, window_ratio: float = 0.01) -> None:
        super().__init__(capacity_bytes, window_ratio=window_ratio, size_aware=True)


# ==========================================================================
# GDSF
# ==========================================================================
class GdsfPolicy(CachePolicy):
    """Greedy-Dual Size Frequency: keep what is expensive to rebuild per byte.

    Priority is ``clock + frequency × saved_work ÷ size``, and the clock is set
    to the priority of whatever was last evicted, so an object cannot sit at
    the top of the heap forever on the strength of one ancient burst. This is
    the policy for the tier holding model output and compiler output, where the
    cost of a miss varies by three orders of magnitude between objects.
    """

    name = PolicyName.GDSF

    def __init__(self, capacity_bytes: int) -> None:
        super().__init__(capacity_bytes)
        self._entries: dict[str, _Entry] = {}
        self._clock = 0.0

    def _priority(self, entry: _Entry) -> float:
        saved = max(entry.recompute_ms - entry.restore_ms, 0.001)
        return self._clock + entry.frequency * saved / max(entry.size_bytes, 1)

    def _lookup(self, key: str) -> _Entry | None:
        return self._entries.get(key)

    def _on_hit(self, entry: _Entry) -> None:
        entry.frequency += 1
        entry.priority = self._priority(entry)

    def _on_miss(self, obj: CacheObject) -> Decision:
        entry = self._entry_of(obj)
        entry.priority = self._priority(entry)
        # A new object that cannot outrank the cheapest resident is not worth
        # the eviction it would cause.
        if self.used_bytes + obj.size_bytes > self.capacity_bytes:
            weakest = self._weakest()
            if weakest is not None and self._entries[weakest].priority > entry.priority:
                self.counters.rejections -= 0  # counted by ``access``
                return Decision(
                    False, False, (), (Reason.REJECTED_BY_VALUE_DENSITY.value,),
                    bypass_reason=Reason.REJECTED_BY_VALUE_DENSITY.value,
                )
        evicted, blocked = self._make_room(obj.size_bytes)
        if blocked is not None:
            return Decision(False, False, tuple(evicted), (blocked,), bypass_reason=blocked)
        self._entries[obj.key] = entry
        self.used_bytes += obj.size_bytes
        return Decision(False, True, tuple(evicted), (Reason.ADMITTED.value,))

    def _weakest(self) -> str | None:
        candidates = [key for key in self._entries if not self.is_protected(key)]
        if not candidates:
            return None
        return min(candidates, key=lambda key: (self._entries[key].priority, key))

    def _evict_one(self) -> str | None:
        key = self._weakest()
        if key is None:
            return None
        entry = self._entries.pop(key)
        self._clock = max(self._clock, entry.priority)
        self.used_bytes -= entry.size_bytes
        self.counters.evictions += 1
        self.counters.bytes_evicted += entry.size_bytes
        return key

    def _iter_keys(self) -> Iterable[str]:
        return tuple(self._entries)

    def _snapshot_state(self) -> dict[str, Any]:
        return {
            "clock": self._clock,
            "entries": [self._entry_to_dict(entry) for entry in self._entries.values()],
        }

    def _restore_state(self, state: Mapping[str, Any]) -> None:
        self._clock = float(state["clock"])
        self._entries = {
            str(item["key"]): self._entry_from_dict(item) for item in state["entries"]
        }


POLICIES: dict[PolicyName, type[CachePolicy]] = {
    PolicyName.LRU: LruPolicy,
    PolicyName.SIEVE: SievePolicy,
    PolicyName.S3_FIFO: S3FifoPolicy,
    PolicyName.W_TINY_LFU: WTinyLfuPolicy,
    PolicyName.SIZE_AWARE_TINY_LFU: SizeAwareTinyLfuPolicy,
    PolicyName.GDSF: GdsfPolicy,
}


def create_policy(name: str | PolicyName, capacity_bytes: int, **parameters: Any) -> CachePolicy:
    """Build one policy by name. Unknown names fail loudly rather than defaulting."""
    try:
        policy_name = PolicyName(str(name))
    except ValueError as error:
        raise ContractViolation(
            "unknown cache policy", policy=str(name), known=sorted(item.value for item in PolicyName)
        ) from error
    return POLICIES[policy_name](capacity_bytes, **parameters)


def restore_policy(snapshot: Mapping[str, Any]) -> CachePolicy:
    """Rebuild a policy from its own snapshot, history included."""
    policy = create_policy(str(snapshot["policy"]), int(snapshot["capacity_bytes"]))
    policy.restore(snapshot)
    return policy
