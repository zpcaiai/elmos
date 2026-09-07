"""Cache traces: capture that is safe to keep, and corpora that are safe to trust.

A policy comparison is only as good as the trace it replays, and a trace of a
code-conversion cache is a privacy problem waiting to happen: the natural thing
to log -- paths, keys, tenants, prompts -- is exactly the thing that must never
land in a corpus that gets copied around for benchmarking.

So a `CacheTraceEvent` here is *numbers and digests only*. Keys arrive already
hashed (an ActionKey is a digest), the tenant is an HMAC under a capture-time
secret that is never written to the corpus, and `assert_privacy` refuses a
corpus containing any string that is not a digest or a member of a closed
vocabulary. That check is what `SOTA-14` asks for, and it is enforced rather
than asserted in a document.

The other half of this module is corpus discipline. A policy that is tuned and
then evaluated on the same events is not evidence of anything, so a corpus
carries explicit, time-separated splits, each with its own digest, plus:

- `detect_leakage`, which refuses a split whose "future" information could not
  have been known at decision time;
- `detect_drift`, which reports how far one window has moved from another;
- `sufficient_sample`, which says when a window is simply too small to certify.

Nine workload generators produce the shapes the acceptance matrix names --
identical rerun, formatting-only change, one-file edit, public-interface edit,
rule-pack upgrade, model change, monorepo scan, large binaries and multi-tenant
bursts -- so a run can be reproduced without shipping a customer's trace.
"""

from __future__ import annotations

import hmac
import json
import math
import statistics
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

from .canonical import digest_of, sha256_bytes
from .errors import ContractViolation

SCHEMA_VERSION = "1.1.0"

#: A digest as every ELMOS surface spells it.
DIGEST_PREFIX = "sha256:"


class Tier(str, Enum):
    L0_MEMORY = "L0_MEMORY"
    L1_LOCAL_CAS = "L1_LOCAL_CAS"
    L2_REMOTE_CAS = "L2_REMOTE_CAS"
    STAGING = "STAGING"
    CHECKPOINT = "CHECKPOINT"
    SEMANTIC_CANDIDATE = "SEMANTIC_CANDIDATE"


class Access(str, Enum):
    GET = "GET"
    PUT = "PUT"
    PREFETCH = "PREFETCH"
    BYPASS = "BYPASS"
    PROTECT = "PROTECT"
    UNPROTECT = "UNPROTECT"
    EVICT = "EVICT"


#: Splits a corpus must keep apart. Tuning may touch the first three; the test
#: window exists precisely so that nothing did.
class Split(str, Enum):
    WARMUP = "warmup"
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"
    DRIFT = "drift"
    ADVERSARIAL = "adversarial"


@dataclass(frozen=True)
class CacheTraceEvent:
    """One cache access, recorded in a form that cannot leak content."""

    event_id: str
    timestamp_bucket: int
    tier: str
    key_hash: str
    namespace_hash: str
    size_bytes: int
    access: str
    stage_class: str
    recompute_ms: float
    restore_ms: float
    schema_version: str = SCHEMA_VERSION
    validation_level: str = "UNVERIFIED"
    model_tokens: int = 0
    critical_path_weight: float = 0.0
    dag_step: int | None = None
    next_use_distance: int | None = None
    hit: bool | None = None
    policy_epoch: str | None = None

    def __post_init__(self) -> None:
        for name, value in (("key_hash", self.key_hash), ("namespace_hash", self.namespace_hash)):
            if not value.startswith(DIGEST_PREFIX) or len(value) != len(DIGEST_PREFIX) + 64:
                raise ContractViolation(f"{name} must be a sha256 digest", value=value[:32])
        if self.size_bytes < 0 or self.recompute_ms < 0 or self.restore_ms < 0:
            raise ContractViolation("trace magnitudes must be non-negative", event=self.event_id)
        Tier(self.tier)
        Access(self.access)

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CacheTraceEvent:
        known = {field_name for field_name in cls.__dataclass_fields__}
        unknown = set(value) - known
        if unknown:
            raise ContractViolation("unknown trace fields", fields=sorted(unknown))
        return cls(**{key: value[key] for key in value})

    @property
    def net_recompute_ms(self) -> float:
        return max(self.recompute_ms - self.restore_ms, 0.0)


# --------------------------------------------------------------------------
# capture
# --------------------------------------------------------------------------
class TraceRecorder:
    """Low-overhead capture with sampling, redaction and a per-tenant budget.

    Sampling is *deterministic in the key*, not random: the same key is either
    always sampled or never, so a sampled trace still contains whole reuse
    chains rather than a scatter of unrelated accesses that would make every
    reuse distance meaningless.
    """

    def __init__(
        self,
        tenant_secret: bytes,
        sample_rate: float = 1.0,
        per_tenant_budget: int = 1_000_000,
    ) -> None:
        if not 0 < sample_rate <= 1:
            raise ContractViolation("sample_rate must be in (0, 1]", sample_rate=sample_rate)
        if not tenant_secret:
            raise ContractViolation("a tenant secret is required to pseudonymise tenants")
        self._secret = bytes(tenant_secret)
        self.sample_rate = sample_rate
        self.per_tenant_budget = per_tenant_budget
        self.events: list[CacheTraceEvent] = []
        self.dropped_by_sampling = 0
        self.dropped_by_budget = 0
        self._per_tenant: dict[str, int] = {}
        self._sequence = 0

    def namespace_hash(self, tenant_id: str, trust_namespace: str = "") -> str:
        """An HMAC, not a hash.

        A tenant id is low-entropy; a bare digest of one is reversible by
        anybody with a list of plausible names. The secret stays in the
        recorder and is never written to the corpus, so the pseudonym is stable
        within a corpus and useless outside it.
        """
        mac = hmac.new(self._secret, f"{tenant_id}\x00{trust_namespace}".encode(), sha256)
        return DIGEST_PREFIX + mac.hexdigest()

    def _sampled(self, key_hash: str) -> bool:
        if self.sample_rate >= 1.0:
            return True
        bucket = int(key_hash[-8:], 16) / 0xFFFFFFFF
        return bucket < self.sample_rate

    def record(
        self,
        *,
        key_hash: str,
        tenant_id: str,
        tier: Tier | str,
        access: Access | str,
        size_bytes: int,
        stage_class: str,
        recompute_ms: float,
        restore_ms: float,
        timestamp_bucket: int | None = None,
        trust_namespace: str = "",
        validation_level: str = "UNVERIFIED",
        model_tokens: int = 0,
        critical_path_weight: float = 0.0,
        dag_step: int | None = None,
        next_use_distance: int | None = None,
        hit: bool | None = None,
        policy_epoch: str | None = None,
    ) -> CacheTraceEvent | None:
        """Record one access, or return ``None`` when sampling or the budget drops it."""
        namespace = self.namespace_hash(tenant_id, trust_namespace)
        if not self._sampled(key_hash):
            self.dropped_by_sampling += 1
            return None
        used = self._per_tenant.get(namespace, 0)
        if used >= self.per_tenant_budget:
            self.dropped_by_budget += 1
            return None
        self._per_tenant[namespace] = used + 1
        self._sequence += 1
        event = CacheTraceEvent(
            event_id=f"evt-{self._sequence:012d}",
            timestamp_bucket=self._sequence if timestamp_bucket is None else timestamp_bucket,
            tier=str(Tier(tier).value if not isinstance(tier, str) else Tier(tier).value),
            key_hash=key_hash,
            namespace_hash=namespace,
            size_bytes=size_bytes,
            access=str(Access(access).value if not isinstance(access, str) else Access(access).value),
            stage_class=stage_class,
            recompute_ms=float(recompute_ms),
            restore_ms=float(restore_ms),
            validation_level=validation_level,
            model_tokens=int(model_tokens),
            critical_path_weight=float(critical_path_weight),
            dag_step=dag_step,
            next_use_distance=next_use_distance,
            hit=hit,
            policy_epoch=policy_epoch,
        )
        self.events.append(event)
        return event

    def stats(self) -> dict[str, Any]:
        return {
            "captured": len(self.events),
            "dropped_by_sampling": self.dropped_by_sampling,
            "dropped_by_budget": self.dropped_by_budget,
            "tenants": len(self._per_tenant),
            "sample_rate": self.sample_rate,
        }


#: Fields whose value is free text and therefore has to come from a closed set.
_CLOSED_VOCABULARY: dict[str, frozenset[str]] = {
    "tier": frozenset(item.value for item in Tier),
    "access": frozenset(item.value for item in Access),
    "validation_level": frozenset(
        {"UNVERIFIED", "COMPILE_VERIFIED", "TEST_VERIFIED", "BEHAVIOR_VERIFIED", "PRODUCTION_CERTIFIED"}
    ),
}

#: A stage class is a short identifier, not a path or a sentence.
_MAX_STAGE_CLASS = 64


def assert_privacy(events: Iterable[CacheTraceEvent]) -> None:
    """Refuse a corpus that could carry content, a path, a prompt or a name.

    The rule is positive, not a blocklist: every string field must be a digest,
    a member of a closed vocabulary, a short identifier, or an event id. There
    is no way to smuggle a file path past that by spelling it differently.
    """
    for event in events:
        for name, allowed in _CLOSED_VOCABULARY.items():
            value = getattr(event, name)
            if value not in allowed:
                raise ContractViolation(
                    "trace field is outside its closed vocabulary", field=name, value=str(value)[:40]
                )
        for name in ("key_hash", "namespace_hash"):
            value = getattr(event, name)
            if not value.startswith(DIGEST_PREFIX) or len(value) != len(DIGEST_PREFIX) + 64:
                raise ContractViolation("trace field is not a digest", field=name)
        stage = event.stage_class
        if len(stage) > _MAX_STAGE_CLASS or any(char in stage for char in "/\\ '\"\n\t"):
            raise ContractViolation("stage_class must be a short identifier", value=stage[:60])
        if event.policy_epoch is not None and len(event.policy_epoch) > 64:
            raise ContractViolation("policy_epoch is too long to be an identifier")


# --------------------------------------------------------------------------
# corpus
# --------------------------------------------------------------------------
@dataclass
class TraceCorpus:
    """Events plus the splits that make a comparison mean something."""

    events: tuple[CacheTraceEvent, ...]
    splits: dict[str, tuple[int, int]] = field(default_factory=dict)
    label: str = "corpus"

    def __post_init__(self) -> None:
        assert_privacy(self.events)
        if not self.splits:
            self.splits = default_splits(len(self.events))
        self._validate_splits()

    def _validate_splits(self) -> None:
        seen: list[tuple[int, int, str]] = []
        for name, (start, end) in sorted(self.splits.items(), key=lambda item: item[1]):
            Split(name)
            if start < 0 or end > len(self.events) or start > end:
                raise ContractViolation("split bounds are outside the corpus", split=name)
            for other_start, other_end, other in seen:
                if start < other_end and other_start < end:
                    raise ContractViolation(
                        "splits overlap in time; tuning would leak into evaluation",
                        first=other,
                        second=name,
                    )
            seen.append((start, end, name))

    def split(self, name: str | Split) -> tuple[CacheTraceEvent, ...]:
        start, end = self.splits[str(Split(name).value)]
        return self.events[start:end]

    def digest(self) -> str:
        return digest_of(
            {
                "schema_version": SCHEMA_VERSION,
                "label": self.label,
                "events": [event.to_dict() for event in self.events],
            }
        )

    def split_digests(self) -> dict[str, str]:
        return {
            name: digest_of([event.to_dict() for event in self.split(name)])
            for name in sorted(self.splits)
        }

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "label": self.label,
            "events": len(self.events),
            "corpus_digest": self.digest(),
            "splits": {name: list(bounds) for name, bounds in sorted(self.splits.items())},
            "split_digests": self.split_digests(),
            "features": workload_features(self.events),
        }

    # -- persistence ------------------------------------------------------
    def write_jsonl(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for event in self.events:
                handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")
        return path

    @classmethod
    def read_jsonl(cls, path: Path, label: str = "corpus") -> TraceCorpus:
        events = []
        with Path(path).open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    events.append(CacheTraceEvent.from_dict(json.loads(line)))
        return cls(tuple(events), label=label)


def default_splits(count: int) -> dict[str, tuple[int, int]]:
    """Time-ordered, non-overlapping, with the test window last and untouched."""
    if count < 10:
        return {Split.TEST.value: (0, count)}
    warmup = max(count // 10, 1)
    train = max(count // 2, 1)
    validation = max(count // 5, 1)
    bounds = {
        Split.WARMUP.value: (0, warmup),
        Split.TRAIN.value: (warmup, warmup + train),
        Split.VALIDATION.value: (warmup + train, warmup + train + validation),
        Split.TEST.value: (warmup + train + validation, count),
    }
    return {name: value for name, value in bounds.items() if value[0] < value[1]}


# --------------------------------------------------------------------------
# workload fingerprint
# --------------------------------------------------------------------------
def workload_features(events: Sequence[CacheTraceEvent]) -> dict[str, float]:
    """The compact fingerprint a selector is allowed to see.

    Everything here is computable off the hit path from counts and sizes, which
    is the point: the selector must never need to touch object content, and its
    input must be cheap enough to compute continuously.
    """
    if not events:
        return {}
    sizes = [float(event.size_bytes) for event in events]
    costs = [float(event.recompute_ms) for event in events]
    counts: dict[str, int] = {}
    order: list[str] = []
    for event in events:
        if event.key_hash not in counts:
            order.append(event.key_hash)
        counts[event.key_hash] = counts.get(event.key_hash, 0) + 1

    unique = len(counts)
    one_hit = sum(1 for value in counts.values() if value == 1)
    reuse_distances = _reuse_distances(events)
    tenants = {event.namespace_hash for event in events}
    per_tenant = _per_tenant_counts(events)
    largest_tenant = max(per_tenant.values()) / len(events) if per_tenant else 0.0
    known_future = sum(1 for event in events if event.next_use_distance is not None) / len(events)
    stages = {event.stage_class for event in events}

    features = {
        "request_count": float(len(events)),
        "unique_count": float(unique),
        "one_hit_ratio": one_hit / unique if unique else 0.0,
        "reuse_ratio": 1.0 - (unique / len(events)),
        "median_size": float(statistics.median(sizes)),
        "p90_size": float(_quantile(sizes, 0.9)),
        "size_cv": _coefficient_of_variation(sizes),
        "cost_cv": _coefficient_of_variation(costs),
        "size_cost_correlation": _correlation(sizes, costs),
        "known_future_ratio": known_future,
        "tenant_count": float(len(tenants)),
        "tenant_concentration": largest_tenant,
        "stage_count": float(len(stages)),
        "model_token_ratio": (
            sum(event.model_tokens for event in events) / max(sum(1 for _ in events), 1)
        ),
        "critical_path_mean": statistics.fmean(event.critical_path_weight for event in events),
    }
    if reuse_distances:
        features["reuse_distance_p50"] = float(_quantile(reuse_distances, 0.5))
        features["reuse_distance_p90"] = float(_quantile(reuse_distances, 0.9))
    else:
        features["reuse_distance_p50"] = 0.0
        features["reuse_distance_p90"] = 0.0
    return {name: round(value, 9) for name, value in features.items()}


def _reuse_distances(events: Sequence[CacheTraceEvent]) -> list[float]:
    last: dict[str, int] = {}
    distances: list[float] = []
    for index, event in enumerate(events):
        previous = last.get(event.key_hash)
        if previous is not None:
            distances.append(float(index - previous))
        last[event.key_hash] = index
    return distances


def _per_tenant_counts(events: Sequence[CacheTraceEvent]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        counts[event.namespace_hash] = counts.get(event.namespace_hash, 0) + 1
    return counts


def _quantile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(math.ceil(fraction * len(ordered))) - 1, len(ordered) - 1)
    return ordered[max(index, 0)]


def _coefficient_of_variation(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = statistics.fmean(values)
    if mean == 0:
        return 0.0
    return statistics.pstdev(values) / mean


def _correlation(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) < 2 or len(right) < 2:
        return 0.0
    try:
        return statistics.correlation(left, right)
    except statistics.StatisticsError:  # constant series
        return 0.0


# --------------------------------------------------------------------------
# corpus quality gates
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class CorpusFinding:
    kind: str
    detail: str
    blocking: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "detail": self.detail, "blocking": self.blocking}


def detect_leakage(corpus: TraceCorpus) -> tuple[CorpusFinding, ...]:
    """Refuse futures that could not have been known when the decision was made.

    ``next_use_distance`` is legitimate only when it comes from the *planned*
    DAG. A value that points past the end of its own split, or a split that
    shares keys with the untouched test window in a way that reveals its
    contents, is future information leaking backwards.
    """
    findings: list[CorpusFinding] = []
    for name, (start, end) in sorted(corpus.splits.items()):
        window = corpus.events[start:end]
        for offset, event in enumerate(window):
            if event.next_use_distance is None:
                continue
            if event.next_use_distance < 0:
                findings.append(CorpusFinding("NEGATIVE_NEXT_USE", f"{name}[{offset}]"))
            elif offset + event.next_use_distance >= len(window) + len(corpus.events) - end:
                findings.append(
                    CorpusFinding(
                        "NEXT_USE_BEYOND_HORIZON",
                        f"{name}[{offset}] points {event.next_use_distance} events ahead",
                    )
                )
    if Split.TRAIN.value in corpus.splits and Split.TEST.value in corpus.splits:
        train_end = corpus.splits[Split.TRAIN.value][1]
        test_start = corpus.splits[Split.TEST.value][0]
        if test_start < train_end:
            findings.append(CorpusFinding("TEST_BEFORE_TRAIN", "the test window is not time-separated"))
    return tuple(findings)


def detect_drift(
    reference: Sequence[CacheTraceEvent],
    candidate: Sequence[CacheTraceEvent],
    threshold: float = 0.25,
) -> dict[str, Any]:
    """How far the candidate window has moved from the reference.

    Reported per feature as a relative shift, plus a single ``drifted`` verdict.
    A drifting workload is not a reason to distrust the cache -- it is a reason
    to stop trusting a policy that was tuned before the shift.
    """
    left = workload_features(reference)
    right = workload_features(candidate)
    shifts: dict[str, float] = {}
    for name, value in left.items():
        other = right.get(name, 0.0)
        scale = max(abs(value), abs(other), 1e-9)
        shifts[name] = round(abs(value - other) / scale, 6)
    drifted = sorted(name for name, shift in shifts.items() if shift > threshold)
    return {
        "threshold": threshold,
        "shifts": shifts,
        "drifted_features": drifted,
        "drifted": bool(drifted),
        "max_shift": max(shifts.values()) if shifts else 0.0,
    }


def sufficient_sample(
    events: Sequence[CacheTraceEvent], minimum_events: int = 200, minimum_keys: int = 20
) -> tuple[bool, str]:
    """Is this window big enough to certify anything?"""
    if len(events) < minimum_events:
        return False, f"{len(events)} events is below the {minimum_events}-event floor"
    unique = len({event.key_hash for event in events})
    if unique < minimum_keys:
        return False, f"{unique} distinct keys is below the {minimum_keys}-key floor"
    return True, "sample size is sufficient"


def key_hash(value: str) -> str:
    """The digest form used for trace keys, for callers holding a plain id."""
    return value if value.startswith(DIGEST_PREFIX) else sha256_bytes(value.encode("utf-8"))


# --------------------------------------------------------------------------
# generators: the shapes the acceptance matrix names
# --------------------------------------------------------------------------
#: Stage classes with the cost profile each one actually has in ELMOS.
STAGE_PROFILE: dict[str, tuple[int, float, float, int]] = {
    # stage: (size_bytes, recompute_ms, restore_ms, model_tokens)
    "snapshot": (24_000, 12.0, 1.0, 0),
    "ast": (48_000, 40.0, 2.0, 0),
    "ir": (256_000, 220.0, 9.0, 0),
    "generation": (96_000, 8_000.0, 4.0, 15_000),
    "compile": (4_000_000, 900.0, 120.0, 0),
    "test": (512_000, 2_400.0, 20.0, 0),
    "manifest": (6_000, 3.0, 0.5, 0),
}


class _Builder:
    """Deterministic event construction shared by every generator."""

    def __init__(self, tenant: str = "tenant-a", secret: bytes = b"generator-secret") -> None:
        self.recorder = TraceRecorder(secret)
        self.tenant = tenant
        self.step = 0

    def emit(
        self,
        key: str,
        stage: str,
        *,
        tenant: str | None = None,
        tier: Tier = Tier.L1_LOCAL_CAS,
        size_bytes: int | None = None,
        next_use_distance: int | None = None,
        access: Access = Access.GET,
    ) -> CacheTraceEvent:
        size, recompute, restore, tokens = STAGE_PROFILE.get(stage, (10_000, 10.0, 1.0, 0))
        event = self.recorder.record(
            key_hash=key_hash(key),
            tenant_id=tenant or self.tenant,
            tier=tier,
            access=access,
            size_bytes=size if size_bytes is None else size_bytes,
            stage_class=stage,
            recompute_ms=recompute,
            restore_ms=restore,
            model_tokens=tokens,
            critical_path_weight=1.0 if stage in ("generation", "compile", "test") else 0.2,
            timestamp_bucket=self.step,
            next_use_distance=next_use_distance,
        )
        self.step += 1
        assert event is not None  # sample_rate is 1.0 for generators
        return event

    def corpus(self, label: str) -> TraceCorpus:
        return TraceCorpus(tuple(self.recorder.events), label=label)


def generate_identical_rerun(modules: int = 40, runs: int = 3) -> TraceCorpus:
    """The best case: nothing changed, everything should be a hit after run one."""
    builder = _Builder()
    for _ in range(runs):
        for index in range(modules):
            for stage in ("snapshot", "ast", "ir", "generation", "compile"):
                builder.emit(f"{stage}:module-{index}", stage)
    return builder.corpus("identical-rerun")


def generate_formatting_only(modules: int = 40) -> TraceCorpus:
    """Whitespace moved: raw digests change, semantic keys do not."""
    builder = _Builder()
    for run in range(2):
        for index in range(modules):
            builder.emit(f"snapshot:module-{index}:run-{run}", "snapshot")  # raw digest moves
            for stage in ("ast", "ir", "generation", "compile"):
                builder.emit(f"{stage}:module-{index}", stage)  # semantic key does not
    return builder.corpus("formatting-only")


def generate_single_file_edit(modules: int = 40, edited: int = 7) -> TraceCorpus:
    builder = _Builder()
    for run in range(2):
        for index in range(modules):
            suffix = f":run-{run}" if (run and index == edited) else ""
            for stage in ("snapshot", "ast", "ir", "generation", "compile"):
                builder.emit(f"{stage}:module-{index}{suffix}", stage)
    return builder.corpus("single-file-edit")


def generate_interface_edit(modules: int = 40, edited: int = 3, dependents: int = 9) -> TraceCorpus:
    """A public signature moved: the edited module and its dependents re-run."""
    builder = _Builder()
    for run in range(2):
        for index in range(modules):
            invalid = run and (index == edited or index % modules < dependents)
            suffix = f":run-{run}" if invalid else ""
            for stage in ("snapshot", "ast", "ir", "generation", "compile"):
                builder.emit(f"{stage}:module-{index}{suffix}", stage)
    return builder.corpus("interface-edit")


def generate_rule_pack_upgrade(modules: int = 40) -> TraceCorpus:
    """Everything downstream of the rule pack changes; the analysis half does not."""
    builder = _Builder()
    for run in range(2):
        for index in range(modules):
            for stage in ("snapshot", "ast", "ir"):
                builder.emit(f"{stage}:module-{index}", stage)
            for stage in ("generation", "compile"):
                builder.emit(f"{stage}:module-{index}:rules-{run}", stage)
    return builder.corpus("rule-pack-upgrade")


def generate_model_change(modules: int = 30) -> TraceCorpus:
    """A model snapshot bump: only the generation stage loses its keys."""
    builder = _Builder()
    for run in range(2):
        for index in range(modules):
            for stage in ("snapshot", "ast", "ir", "compile"):
                builder.emit(f"{stage}:module-{index}", stage)
            builder.emit(f"generation:module-{index}:model-{run}", "generation")
    return builder.corpus("model-change")


def generate_monorepo_scan(files: int = 1600, hot: int = 12, burst: int = 400) -> TraceCorpus:
    """The scan that breaks LRU.

    A repository walk touches hundreds of files exactly once, then work returns
    to a small hot set. The scan between two visits to the hot set is larger
    than the cache, so a pure recency policy has evicted the hot set every time
    it comes back. Scan-resistant policies do not.
    """
    builder = _Builder()
    scanned = 0
    while scanned < files:
        for _ in range(min(burst, files - scanned)):
            builder.emit(f"snapshot:scan-{scanned}", "snapshot")
            scanned += 1
        for round_index in range(3):
            for index in range(hot):
                builder.emit(f"ir:hot-{index}", "ir")
            del round_index
    return builder.corpus("monorepo-scan")


def generate_large_binaries(count: int = 60, hot_manifests: int = 25) -> TraceCorpus:
    """Heterogeneous sizes: 4 MB build outputs against 6 KB manifests."""
    builder = _Builder()
    for index in range(count):
        builder.emit(f"compile:artifact-{index}", "compile")
        for manifest in range(hot_manifests):
            builder.emit(f"manifest:m-{manifest}", "manifest")
    return builder.corpus("large-binaries")


def generate_multi_tenant_burst(tenants: int = 4, per_tenant: int = 80, burst_factor: int = 6) -> TraceCorpus:
    """One tenant bursts; the others must still get their share."""
    builder = _Builder()
    for index in range(per_tenant):
        for tenant in range(tenants):
            repeats = burst_factor if tenant == 0 else 1
            for repeat in range(repeats):
                builder.emit(
                    f"ir:tenant-{tenant}-object-{(index + repeat) % per_tenant}",
                    "ir",
                    tenant=f"tenant-{tenant}",
                )
    return builder.corpus("multi-tenant-burst")


def generate_dag_known_future(modules: int = 30) -> TraceCorpus:
    """A planned graph: every event carries the distance to its next consumer."""
    builder = _Builder()
    # Produce every IR partition, then consume each one twice: once to generate
    # the target and once to compile it. The repeats are what give an event a
    # *known* next use rather than a predicted one.
    plan = [(f"ir:module-{index}", "ir") for index in range(modules)]
    for index in range(modules):
        plan.append((f"ir:module-{index}", "ir"))
        plan.append((f"generation:module-{index}", "generation"))
    for index in range(modules):
        plan.append((f"generation:module-{index}", "generation"))
        plan.append((f"compile:module-{index}", "compile"))
    positions: dict[str, list[int]] = {}
    for index, (key, _) in enumerate(plan):
        positions.setdefault(key, []).append(index)
    for index, (key, stage) in enumerate(plan):
        upcoming = [position for position in positions[key] if position > index]
        distance = (upcoming[0] - index) if upcoming else None
        builder.emit(key, stage, next_use_distance=distance)
    return builder.corpus("dag-known-future")


#: Name -> generator, for a benchmark matrix that wants them all. Each takes no
#: required arguments and returns a corpus, so a caller can iterate blindly.
GENERATORS: dict[str, Callable[[], TraceCorpus]] = {
    "identical-rerun": generate_identical_rerun,
    "formatting-only": generate_formatting_only,
    "single-file-edit": generate_single_file_edit,
    "interface-edit": generate_interface_edit,
    "rule-pack-upgrade": generate_rule_pack_upgrade,
    "model-change": generate_model_change,
    "monorepo-scan": generate_monorepo_scan,
    "large-binaries": generate_large_binaries,
    "multi-tenant-burst": generate_multi_tenant_burst,
    "dag-known-future": generate_dag_known_future,
}
