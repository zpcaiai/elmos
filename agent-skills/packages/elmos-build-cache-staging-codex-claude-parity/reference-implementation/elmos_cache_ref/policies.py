from __future__ import annotations

import hashlib
import math
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from statistics import median
from typing import Iterable, Mapping, Protocol


@dataclass(slots=True)
class CacheEntry:
    key: str
    size_bytes: int
    recompute_ms: float = 1.0
    restore_ms: float = 0.0
    frequency: int = 0
    visited: bool = False
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def net_value(self) -> float:
        return max(self.recompute_ms - self.restore_ms, 0.001)


@dataclass(frozen=True, slots=True)
class AccessResult:
    hit: bool
    admitted: bool
    evicted: tuple[str, ...] = ()
    bypass_reason: str | None = None


class CachePolicy(Protocol):
    name: str
    capacity_bytes: int
    used_bytes: int

    def access(
        self,
        key: str,
        size_bytes: int,
        *,
        recompute_ms: float = 1.0,
        restore_ms: float = 0.0,
    ) -> AccessResult: ...

    def contains(self, key: str) -> bool: ...


class _BasePolicy:
    name = "BASE"

    def __init__(self, capacity_bytes: int) -> None:
        if capacity_bytes <= 0:
            raise ValueError("capacity_bytes must be positive")
        self.capacity_bytes = capacity_bytes
        self.used_bytes = 0

    def _new_entry(
        self,
        key: str,
        size_bytes: int,
        recompute_ms: float,
        restore_ms: float,
    ) -> CacheEntry:
        if size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        return CacheEntry(
            key=key,
            size_bytes=size_bytes,
            recompute_ms=max(recompute_ms, 0.0),
            restore_ms=max(restore_ms, 0.0),
        )

    @staticmethod
    def _validate_existing_size(entry: CacheEntry, size_bytes: int) -> None:
        # ELMOS exact cache keys identify immutable objects. A size change for the
        # same key signals a broken trace or key contract and should not be hidden.
        if entry.size_bytes != size_bytes:
            raise ValueError(
                f"immutable cache key {entry.key!r} changed size "
                f"from {entry.size_bytes} to {size_bytes}"
            )


class LRUCache(_BasePolicy):
    name = "LRU"

    def __init__(self, capacity_bytes: int) -> None:
        super().__init__(capacity_bytes)
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()

    def contains(self, key: str) -> bool:
        return key in self._entries

    def access(
        self,
        key: str,
        size_bytes: int,
        *,
        recompute_ms: float = 1.0,
        restore_ms: float = 0.0,
    ) -> AccessResult:
        existing = self._entries.get(key)
        if existing is not None:
            self._validate_existing_size(existing, size_bytes)
            existing.frequency += 1
            self._entries.move_to_end(key)
            return AccessResult(hit=True, admitted=True)

        if size_bytes > self.capacity_bytes:
            return AccessResult(False, False, bypass_reason="OBJECT_EXCEEDS_CAPACITY")

        evicted: list[str] = []
        while self.used_bytes + size_bytes > self.capacity_bytes:
            victim_key, victim = self._entries.popitem(last=False)
            self.used_bytes -= victim.size_bytes
            evicted.append(victim_key)

        entry = self._new_entry(key, size_bytes, recompute_ms, restore_ms)
        entry.frequency = 1
        self._entries[key] = entry
        self.used_bytes += size_bytes
        return AccessResult(False, True, tuple(evicted))


class SieveCache(_BasePolicy):
    """A compact educational SIEVE implementation.

    Production implementations should use an intrusive queue/hand representation;
    this reference keeps the semantics visible and deterministic for trace replay.
    """

    name = "SIEVE"

    def __init__(self, capacity_bytes: int) -> None:
        super().__init__(capacity_bytes)
        self._entries: dict[str, CacheEntry] = {}
        self._queue: deque[str] = deque()

    def contains(self, key: str) -> bool:
        return key in self._entries

    def _evict_one(self) -> str:
        if not self._queue:
            raise RuntimeError("cannot evict from an empty SIEVE cache")
        # A visited entry receives a second chance. A hit only sets a bit and does
        # not mutate queue order, mirroring SIEVE's low-overhead data path.
        while True:
            key = self._queue.popleft()
            entry = self._entries[key]
            if entry.visited:
                entry.visited = False
                self._queue.append(key)
                continue
            del self._entries[key]
            self.used_bytes -= entry.size_bytes
            return key

    def access(
        self,
        key: str,
        size_bytes: int,
        *,
        recompute_ms: float = 1.0,
        restore_ms: float = 0.0,
    ) -> AccessResult:
        existing = self._entries.get(key)
        if existing is not None:
            self._validate_existing_size(existing, size_bytes)
            existing.visited = True
            existing.frequency += 1
            return AccessResult(True, True)

        if size_bytes > self.capacity_bytes:
            return AccessResult(False, False, bypass_reason="OBJECT_EXCEEDS_CAPACITY")

        evicted: list[str] = []
        while self.used_bytes + size_bytes > self.capacity_bytes:
            evicted.append(self._evict_one())

        entry = self._new_entry(key, size_bytes, recompute_ms, restore_ms)
        self._entries[key] = entry
        self._queue.append(key)
        self.used_bytes += size_bytes
        return AccessResult(False, True, tuple(evicted))


class S3FIFOCache(_BasePolicy):
    """Three-queue FIFO policy with quick demotion of one-hit objects.

    The implementation follows the production-relevant structure—small FIFO,
    main FIFO, and bounded ghost history—while staying intentionally compact.
    """

    name = "S3_FIFO"

    def __init__(
        self,
        capacity_bytes: int,
        *,
        small_ratio: float = 0.10,
        ghost_max_entries: int = 8192,
    ) -> None:
        super().__init__(capacity_bytes)
        if not 0 < small_ratio < 1:
            raise ValueError("small_ratio must be between 0 and 1")
        self.small_target_bytes = max(1, int(capacity_bytes * small_ratio))
        self._small: OrderedDict[str, CacheEntry] = OrderedDict()
        self._main: OrderedDict[str, CacheEntry] = OrderedDict()
        self._ghost: OrderedDict[str, None] = OrderedDict()
        self._small_bytes = 0
        self._main_bytes = 0
        self._ghost_max_entries = max(1, ghost_max_entries)

    def contains(self, key: str) -> bool:
        return key in self._small or key in self._main

    def _remember_ghost(self, key: str) -> None:
        self._ghost[key] = None
        self._ghost.move_to_end(key)
        while len(self._ghost) > self._ghost_max_entries:
            self._ghost.popitem(last=False)

    def _evict_small(self) -> str | None:
        if not self._small:
            return None
        key, entry = self._small.popitem(last=False)
        self._small_bytes -= entry.size_bytes
        if entry.frequency > 1 and entry.size_bytes <= self.capacity_bytes:
            # Reused objects graduate to the main FIFO. Queue order remains FIFO.
            entry.frequency = min(entry.frequency - 1, 3)
            self._main[key] = entry
            self._main_bytes += entry.size_bytes
            return None
        self.used_bytes -= entry.size_bytes
        self._remember_ghost(key)
        return key

    def _evict_main(self) -> str | None:
        if not self._main:
            return None
        # Frequency is a tiny bounded counter; frequently reused objects receive
        # limited second chances without an LRU list mutation on every hit.
        for _ in range(max(1, len(self._main) * 4)):
            key, entry = self._main.popitem(last=False)
            if entry.frequency > 0:
                entry.frequency -= 1
                self._main[key] = entry
                continue
            self._main_bytes -= entry.size_bytes
            self.used_bytes -= entry.size_bytes
            self._remember_ghost(key)
            return key
        # Defensive progress guarantee if counters were externally corrupted.
        key, entry = self._main.popitem(last=False)
        self._main_bytes -= entry.size_bytes
        self.used_bytes -= entry.size_bytes
        self._remember_ghost(key)
        return key

    def _rebalance(self) -> tuple[str, ...]:
        evicted: list[str] = []
        while self.used_bytes > self.capacity_bytes:
            victim: str | None
            if self._small and (
                self._small_bytes > self.small_target_bytes or not self._main
            ):
                victim = self._evict_small()
            else:
                victim = self._evict_main()
                if victim is None:
                    victim = self._evict_small()
            if victim is not None:
                evicted.append(victim)
            if victim is None and not self._small and not self._main:
                raise RuntimeError("S3-FIFO rebalance made no progress")
        return tuple(evicted)

    def access(
        self,
        key: str,
        size_bytes: int,
        *,
        recompute_ms: float = 1.0,
        restore_ms: float = 0.0,
    ) -> AccessResult:
        existing = self._small.get(key)
        if existing is not None:
            self._validate_existing_size(existing, size_bytes)
            existing.frequency = min(existing.frequency + 1, 3)
            return AccessResult(True, True)
        existing = self._main.get(key)
        if existing is not None:
            self._validate_existing_size(existing, size_bytes)
            existing.frequency = min(existing.frequency + 1, 3)
            return AccessResult(True, True)

        if size_bytes > self.capacity_bytes:
            return AccessResult(False, False, bypass_reason="OBJECT_EXCEEDS_CAPACITY")

        entry = self._new_entry(key, size_bytes, recompute_ms, restore_ms)
        if key in self._ghost or size_bytes > self.small_target_bytes:
            self._ghost.pop(key, None)
            entry.frequency = 1
            self._main[key] = entry
            self._main_bytes += size_bytes
        else:
            self._small[key] = entry
            self._small_bytes += size_bytes
        self.used_bytes += size_bytes
        evicted = self._rebalance()
        return AccessResult(False, self.contains(key), evicted)


class FrequencySketch:
    """TinyLFU-style Doorkeeper plus compact count-min frequency sketch."""

    def __init__(self, width: int = 2048, depth: int = 4, sample_size: int = 20_000) -> None:
        if width <= 0 or depth <= 0 or sample_size <= 0:
            raise ValueError("frequency sketch dimensions must be positive")
        self.width = width
        self.depth = depth
        self.sample_size = sample_size
        self._tables = [[0] * width for _ in range(depth)]
        self._doorkeeper: set[str] = set()
        self._events = 0

    @staticmethod
    def _hash(key: str, seed: int) -> int:
        digest = hashlib.blake2b(
            key.encode("utf-8"), digest_size=8, person=f"elmos{seed:02d}".encode("ascii")
        ).digest()
        return int.from_bytes(digest, "big")

    def increment(self, key: str) -> None:
        self._events += 1
        if key not in self._doorkeeper:
            self._doorkeeper.add(key)
        else:
            for depth in range(self.depth):
                index = self._hash(key, depth) % self.width
                if self._tables[depth][index] < 15:
                    self._tables[depth][index] += 1
        if self._events >= self.sample_size:
            self._age()

    def estimate(self, key: str) -> int:
        estimate = min(
            self._tables[depth][self._hash(key, depth) % self.width]
            for depth in range(self.depth)
        )
        return estimate + (1 if key in self._doorkeeper else 0)

    def _age(self) -> None:
        for table in self._tables:
            for index, value in enumerate(table):
                table[index] = value >> 1
        self._doorkeeper.clear()
        self._events = 0


class WTinyLFUCache(_BasePolicy):
    name = "W_TINY_LFU"

    def __init__(
        self,
        capacity_bytes: int,
        *,
        window_ratio: float = 0.01,
        size_aware: bool = False,
        sketch_width: int = 2048,
    ) -> None:
        super().__init__(capacity_bytes)
        if not 0 < window_ratio < 1:
            raise ValueError("window_ratio must be between 0 and 1")
        self.window_capacity = max(1, int(capacity_bytes * window_ratio))
        self.main_capacity = max(1, capacity_bytes - self.window_capacity)
        self.size_aware = size_aware
        self.name = "SIZE_AWARE_TINY_LFU" if size_aware else "W_TINY_LFU"
        self._window: OrderedDict[str, CacheEntry] = OrderedDict()
        self._main: OrderedDict[str, CacheEntry] = OrderedDict()
        self._window_bytes = 0
        self._main_bytes = 0
        self.sketch = FrequencySketch(width=sketch_width)

    def contains(self, key: str) -> bool:
        return key in self._window or key in self._main

    def _score(self, entry: CacheEntry) -> float:
        frequency = max(1, self.sketch.estimate(entry.key))
        if not self.size_aware:
            return float(frequency)
        return frequency * entry.net_value / max(1, entry.size_bytes)

    def _admit_main(self, candidate: CacheEntry) -> tuple[bool, list[str]]:
        evicted: list[str] = []
        if candidate.size_bytes > self.main_capacity:
            return False, evicted

        while self._main_bytes + candidate.size_bytes > self.main_capacity:
            if not self._main:
                return False, evicted
            victim_key = next(iter(self._main))
            victim = self._main[victim_key]
            if self._score(candidate) < self._score(victim):
                return False, evicted
            self._main.pop(victim_key)
            self._main_bytes -= victim.size_bytes
            self.used_bytes -= victim.size_bytes
            evicted.append(victim_key)

        self._main[candidate.key] = candidate
        self._main_bytes += candidate.size_bytes
        self.used_bytes += candidate.size_bytes
        return True, evicted

    def access(
        self,
        key: str,
        size_bytes: int,
        *,
        recompute_ms: float = 1.0,
        restore_ms: float = 0.0,
    ) -> AccessResult:
        self.sketch.increment(key)

        existing = self._window.get(key)
        if existing is not None:
            self._validate_existing_size(existing, size_bytes)
            existing.frequency += 1
            self._window.move_to_end(key)
            return AccessResult(True, True)
        existing = self._main.get(key)
        if existing is not None:
            self._validate_existing_size(existing, size_bytes)
            existing.frequency += 1
            self._main.move_to_end(key)
            return AccessResult(True, True)

        if size_bytes > self.capacity_bytes:
            return AccessResult(False, False, bypass_reason="OBJECT_EXCEEDS_CAPACITY")

        entry = self._new_entry(key, size_bytes, recompute_ms, restore_ms)
        entry.frequency = 1
        evicted: list[str] = []

        if size_bytes > self.window_capacity:
            admitted, main_evicted = self._admit_main(entry)
            evicted.extend(main_evicted)
            return AccessResult(False, admitted, tuple(evicted), None if admitted else "ADMISSION_REJECTED")

        self._window[key] = entry
        self._window_bytes += size_bytes
        self.used_bytes += size_bytes

        while self._window_bytes > self.window_capacity:
            candidate_key, candidate = self._window.popitem(last=False)
            self._window_bytes -= candidate.size_bytes
            self.used_bytes -= candidate.size_bytes
            admitted, main_evicted = self._admit_main(candidate)
            evicted.extend(main_evicted)
            if not admitted:
                evicted.append(candidate_key)

        return AccessResult(False, self.contains(key), tuple(evicted))


class GDSFCache(_BasePolicy):
    """GreedyDual-Size-Frequency using recomputation value as retrieval cost."""

    name = "GDSF"

    def __init__(self, capacity_bytes: int) -> None:
        super().__init__(capacity_bytes)
        self._entries: dict[str, CacheEntry] = {}
        self._scores: dict[str, float] = {}
        self._inflation = 0.0

    def contains(self, key: str) -> bool:
        return key in self._entries

    def _score(self, entry: CacheEntry) -> float:
        return self._inflation + entry.frequency * entry.net_value / max(1, entry.size_bytes)

    def access(
        self,
        key: str,
        size_bytes: int,
        *,
        recompute_ms: float = 1.0,
        restore_ms: float = 0.0,
    ) -> AccessResult:
        existing = self._entries.get(key)
        if existing is not None:
            self._validate_existing_size(existing, size_bytes)
            existing.frequency += 1
            existing.recompute_ms = max(existing.recompute_ms, recompute_ms)
            existing.restore_ms = min(existing.restore_ms, restore_ms)
            self._scores[key] = self._score(existing)
            return AccessResult(True, True)

        if size_bytes > self.capacity_bytes:
            return AccessResult(False, False, bypass_reason="OBJECT_EXCEEDS_CAPACITY")

        evicted: list[str] = []
        while self.used_bytes + size_bytes > self.capacity_bytes:
            victim_key = min(self._scores, key=self._scores.__getitem__)
            victim_score = self._scores.pop(victim_key)
            victim = self._entries.pop(victim_key)
            self.used_bytes -= victim.size_bytes
            self._inflation = max(self._inflation, victim_score)
            evicted.append(victim_key)

        entry = self._new_entry(key, size_bytes, recompute_ms, restore_ms)
        entry.frequency = 1
        self._entries[key] = entry
        self._scores[key] = self._score(entry)
        self.used_bytes += size_bytes
        return AccessResult(False, True, tuple(evicted))


@dataclass(frozen=True, slots=True)
class WorkloadFeatures:
    request_count: int
    unique_count: int
    one_hit_ratio: float
    reuse_ratio: float
    median_size: float
    p90_size: float
    size_cv: float
    cost_cv: float
    known_future_ratio: float = 0.0

    @classmethod
    def from_events(cls, events: Iterable[Mapping[str, object]]) -> "WorkloadFeatures":
        event_list = list(events)
        if not event_list:
            return cls(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        counts: dict[str, int] = {}
        sizes: list[float] = []
        costs: list[float] = []
        known_future = 0
        for event in event_list:
            key = str(event["key"])
            counts[key] = counts.get(key, 0) + 1
            sizes.append(float(event.get("size_bytes", 0)))
            costs.append(float(event.get("recompute_ms", 0)))
            if event.get("next_use_distance") is not None:
                known_future += 1
        unique = len(counts)
        one_hit = sum(1 for count in counts.values() if count == 1)
        reuse_requests = sum(max(0, count - 1) for count in counts.values())
        sorted_sizes = sorted(sizes)
        p90_index = min(len(sorted_sizes) - 1, math.ceil(len(sorted_sizes) * 0.9) - 1)

        def cv(values: list[float]) -> float:
            mean = sum(values) / len(values)
            if mean == 0:
                return 0.0
            variance = sum((value - mean) ** 2 for value in values) / len(values)
            return math.sqrt(variance) / mean

        return cls(
            request_count=len(event_list),
            unique_count=unique,
            one_hit_ratio=one_hit / max(1, unique),
            reuse_ratio=reuse_requests / len(event_list),
            median_size=median(sizes),
            p90_size=sorted_sizes[p90_index],
            size_cv=cv(sizes),
            cost_cv=cv(costs),
            known_future_ratio=known_future / len(event_list),
        )


@dataclass(frozen=True, slots=True)
class PolicyChoice:
    policy: str
    reason_codes: tuple[str, ...]
    confidence: float


class PolicyRouter:
    """Deterministic, off-path first-stage selector.

    This is intentionally interpretable. A learned selector can replace it only
    after shadow/canary certification and must preserve the same fallback API.
    """

    def choose(
        self,
        features: WorkloadFeatures,
        *,
        objective: str = "BALANCED",
    ) -> PolicyChoice:
        reasons: list[str] = []
        if features.request_count < 100:
            return PolicyChoice("S3_FIFO", ("INSUFFICIENT_TRACE", "STRONG_FIXED_FALLBACK"), 0.35)
        if features.known_future_ratio >= 0.70:
            reasons.append("DAG_FUTURE_REUSE_AVAILABLE")
        if features.size_cv >= 1.5 or features.cost_cv >= 1.5:
            reasons.extend(("HETEROGENEOUS_SIZE_OR_COST", "VALUE_DENSITY_REQUIRED"))
            return PolicyChoice("GDSF", tuple(reasons), 0.80)
        if features.one_hit_ratio >= 0.60:
            reasons.extend(("ONE_HIT_RATIO_HIGH", "QUICK_DEMOTION_REQUIRED"))
            return PolicyChoice("S3_FIFO", tuple(reasons), 0.85)
        if features.reuse_ratio >= 0.45:
            reasons.extend(("TEMPORAL_REUSE_HIGH", "FREQUENCY_ADMISSION_USEFUL"))
            return PolicyChoice("W_TINY_LFU", tuple(reasons), 0.78)
        if objective == "BYTE_NETWORK" and features.p90_size > max(1.0, features.median_size * 4):
            return PolicyChoice("GDSF", ("BYTE_OBJECTIVE", "LARGE_OBJECT_TAIL"), 0.72)
        return PolicyChoice("SIEVE", ("MIXED_WORKLOAD", "LOW_OVERHEAD_FALLBACK"), 0.66)


def create_policy(name: str, capacity_bytes: int) -> CachePolicy:
    normalized = name.upper().replace("-", "_")
    if normalized == "LRU":
        return LRUCache(capacity_bytes)
    if normalized == "SIEVE":
        return SieveCache(capacity_bytes)
    if normalized in {"S3FIFO", "S3_FIFO"}:
        return S3FIFOCache(capacity_bytes)
    if normalized in {"WTINYLFU", "W_TINY_LFU"}:
        return WTinyLFUCache(capacity_bytes)
    if normalized in {"SIZE_AWARE_TINY_LFU", "SIZE_AWARE_W_TINY_LFU"}:
        return WTinyLFUCache(capacity_bytes, size_aware=True)
    if normalized == "GDSF":
        return GDSFCache(capacity_bytes)
    raise ValueError(f"unsupported reference policy: {name}")
