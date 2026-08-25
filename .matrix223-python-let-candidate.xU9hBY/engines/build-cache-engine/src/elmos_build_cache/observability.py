"""Telemetry, hit-rate accounting and performance gates.

Two rules shape everything here:

* **Nothing sensitive leaves.** Source paths, code, raw prompts, secrets and
  full digests are never metric labels. Labels are bounded, low-cardinality
  values; digests appear only truncated, inside trace attributes, and only when
  policy allows.
* **Hit rate is not one number.** It is reported per stage together with the
  work actually avoided -- CPU, wall clock, compiler time and model tokens --
  because a 95% hit rate on cheap stages and 0% on generation is a bad day
  reported as a good one.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from .canonical import digest_of
from .clock import SYSTEM_CLOCK, Clock
from .enums import MissReason

SCHEMA_VERSION = "1.0.0"

#: Span names, fixed so dashboards do not depend on call-site strings.
SPAN_LOOKUP = "elmos.cache.lookup"
SPAN_MATERIALIZE = "elmos.cache.materialize"
SPAN_EXECUTE = "elmos.stage.execute"
SPAN_WRITE = "elmos.staging.write"
SPAN_SEAL = "elmos.staging.seal"
SPAN_PROMOTE = "elmos.staging.promote"
SPAN_CHECKPOINT = "elmos.checkpoint.commit"
SPAN_RESUME = "elmos.checkpoint.resume"
SPAN_UPLOAD = "elmos.remote.upload"
SPAN_PUBLISH = "elmos.publish.tree"
SPAN_GC = "elmos.gc.apply"

ALL_SPANS: tuple[str, ...] = (
    SPAN_LOOKUP,
    SPAN_MATERIALIZE,
    SPAN_EXECUTE,
    SPAN_WRITE,
    SPAN_SEAL,
    SPAN_PROMOTE,
    SPAN_CHECKPOINT,
    SPAN_RESUME,
    SPAN_UPLOAD,
    SPAN_PUBLISH,
    SPAN_GC,
)

#: Label keys allowed on metrics. Anything else is dropped, not sanitised,
#: because a silently truncated label is worse than a missing one.
ALLOWED_LABELS: frozenset[str] = frozenset(
    {
        "stage_id",
        "granularity",
        "outcome",
        "miss_reason",
        "trust_namespace",
        "validation_level",
        "tenant_bucket",
        "adapter",
        "backend",
        "language",
        "resource_class",
    }
)

FORBIDDEN_LABEL_MARKERS: tuple[str, ...] = (
    "path",
    "prompt",
    "source",
    "secret",
    "token",
    "digest",
    "content",
    "code",
    "run_id",
    "node_id",
    "user",
)


def safe_labels(labels: Mapping[str, Any]) -> dict[str, str]:
    """Keep only allowlisted, low-cardinality labels."""
    out: dict[str, str] = {}
    for key, value in sorted(labels.items()):
        lowered = key.lower()
        if key not in ALLOWED_LABELS:
            continue
        if any(marker in lowered for marker in FORBIDDEN_LABEL_MARKERS):
            continue
        out[key] = str(value)[:64]
    return out


def tenant_bucket(tenant_id: str) -> str:
    """Bucket tenants so per-tenant series stay bounded."""
    return "t" + digest_of(tenant_id)[7:11]


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------
@dataclass
class Histogram:
    values: list[float] = field(default_factory=list)

    def observe(self, value: float) -> None:
        self.values.append(value)

    def quantile(self, q: float) -> float:
        if not self.values:
            return 0.0
        ordered = sorted(self.values)
        index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
        return ordered[index]

    def summary(self) -> dict[str, float]:
        if not self.values:
            return {"count": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0, "mean": 0.0}
        return {
            "count": len(self.values),
            "p50": round(self.quantile(0.50), 3),
            "p95": round(self.quantile(0.95), 3),
            "p99": round(self.quantile(0.99), 3),
            "max": round(max(self.values), 3),
            "mean": round(sum(self.values) / len(self.values), 3),
        }


class MetricsRegistry:
    """Prometheus-shaped counters, gauges and histograms, in-process."""

    def __init__(self) -> None:
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._histograms: dict[tuple[str, tuple[tuple[str, str], ...]], Histogram] = defaultdict(Histogram)

    @staticmethod
    def _key(name: str, labels: Mapping[str, Any]) -> tuple[str, tuple[tuple[str, str], ...]]:
        return name, tuple(sorted(safe_labels(labels).items()))

    def increment(self, name: str, value: float = 1.0, **labels: Any) -> None:
        self._counters[self._key(name, labels)] += value

    def gauge(self, name: str, value: float, **labels: Any) -> None:
        self._gauges[self._key(name, labels)] = value

    def observe(self, name: str, value: float, **labels: Any) -> None:
        self._histograms[self._key(name, labels)].observe(value)

    def counter_value(self, name: str, **labels: Any) -> float:
        return self._counters.get(self._key(name, labels), 0.0)

    def histogram(self, name: str, **labels: Any) -> Histogram:
        return self._histograms[self._key(name, labels)]

    def snapshot(self) -> dict[str, Any]:
        def render(key: tuple[str, tuple[tuple[str, str], ...]]) -> str:
            name, labels = key
            if not labels:
                return name
            rendered = ",".join(f'{k}="{v}"' for k, v in labels)
            return f"{name}{{{rendered}}}"

        return {
            "counters": {render(key): value for key, value in sorted(self._counters.items())},
            "gauges": {render(key): value for key, value in sorted(self._gauges.items())},
            "histograms": {
                render(key): histogram.summary() for key, histogram in sorted(self._histograms.items())
            },
        }

    def expose(self) -> str:
        """Prometheus text exposition."""
        lines: list[str] = []
        snapshot = self.snapshot()
        for name, value in snapshot["counters"].items():
            lines.append(f"{name} {value}")
        for name, value in snapshot["gauges"].items():
            lines.append(f"{name} {value}")
        for name, summary in snapshot["histograms"].items():
            base = name.split("{", 1)[0]
            suffix = name[len(base) :]
            for stat, value in summary.items():
                joined = f"{base}_{stat}{suffix}" if suffix else f"{base}_{stat}"
                lines.append(f"{joined} {value}")
        return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# tracing
# --------------------------------------------------------------------------
@dataclass
class Span:
    name: str
    attributes: dict[str, Any]
    started_at: float
    duration_ms: float = 0.0
    status: str = "OK"
    events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "attributes": self.attributes,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
            "events": self.events,
        }


class Tracer:
    """Correlates run/node/ActionKey/artifact/staged-file/checkpoint IDs.

    Correlation IDs are trace *attributes*, never metric labels: they are
    high-cardinality by nature and belong in a trace, not a time series.
    """

    def __init__(
        self,
        metrics: MetricsRegistry | None = None,
        clock: Clock = SYSTEM_CLOCK,
        otel_tracer: Any | None = None,
        disclose_digests: bool = False,
    ) -> None:
        self.metrics = metrics or MetricsRegistry()
        self.clock = clock
        self.otel = otel_tracer
        self.disclose_digests = disclose_digests
        self.spans: list[Span] = []

    def _attributes(self, values: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in sorted(values.items()):
            if value is None:
                continue
            if isinstance(value, str) and value.startswith("sha256:") and not self.disclose_digests:
                out[key] = value[:19] + "..."
            elif any(marker in key.lower() for marker in ("prompt", "secret", "token", "source_text")):
                out[key] = "<redacted>"
            else:
                out[key] = value
        return out

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[Span]:
        span = Span(name=name, attributes=self._attributes(attributes), started_at=self.clock.now())
        started = time.perf_counter()
        otel_span = None
        if self.otel is not None:  # pragma: no cover - requires the otel extra
            otel_span = self.otel.start_span(name)
            for key, value in span.attributes.items():
                otel_span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.status = "ERROR"
            span.events.append({"event": "exception", "type": type(exc).__name__})
            raise
        finally:
            span.duration_ms = (time.perf_counter() - started) * 1000.0
            self.spans.append(span)
            self.metrics.observe(
                "elmos_span_duration_ms",
                span.duration_ms,
                stage_id=str(attributes.get("stage_id", "unknown")),
                outcome=span.status,
            )
            if otel_span is not None:  # pragma: no cover
                otel_span.end()

    def correlated(self, run_id: str, node_id: str) -> dict[str, str]:
        return {"run_id": run_id, "node_id": node_id}

    def summary(self) -> dict[str, Any]:
        by_name: dict[str, Histogram] = defaultdict(Histogram)
        for span in self.spans:
            by_name[span.name].observe(span.duration_ms)
        return {name: histogram.summary() for name, histogram in sorted(by_name.items())}


# --------------------------------------------------------------------------
# hit-rate accounting
# --------------------------------------------------------------------------
@dataclass
class StageAccount:
    stage_id: str
    local_hits: int = 0
    remote_hits: int = 0
    partial_hits: int = 0
    misses: int = 0
    saved_cpu_ms: int = 0
    saved_wall_ms: int = 0
    saved_compiler_ms: int = 0
    saved_model_tokens: int = 0
    executed_cpu_ms: int = 0
    executed_wall_ms: int = 0
    miss_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return self.local_hits + self.remote_hits + self.partial_hits + self.misses

    @property
    def hit_rate(self) -> float:
        return 0.0 if not self.total else (self.local_hits + self.remote_hits) / self.total

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "local_hits": self.local_hits,
            "remote_hits": self.remote_hits,
            "partial_hits": self.partial_hits,
            "misses": self.misses,
            "hit_rate": round(self.hit_rate, 4),
            "saved_cpu_ms": self.saved_cpu_ms,
            "saved_wall_ms": self.saved_wall_ms,
            "saved_compiler_ms": self.saved_compiler_ms,
            "saved_model_tokens": self.saved_model_tokens,
            "executed_cpu_ms": self.executed_cpu_ms,
            "executed_wall_ms": self.executed_wall_ms,
            "miss_reasons": dict(sorted(self.miss_reasons.items())),
        }


class CacheAccounting:
    def __init__(self, metrics: MetricsRegistry | None = None) -> None:
        self.metrics = metrics or MetricsRegistry()
        self.stages: dict[str, StageAccount] = {}
        self.bytes_stored = 0
        self.bytes_deduplicated = 0
        self.bytes_restored = 0
        self.bytes_uploaded = 0
        self.bytes_downloaded = 0
        self.bytes_evicted = 0
        self.stale_leases = 0
        self.recovery_attempts = 0
        self.digest_mismatches = 0
        self.corruptions = 0
        self.nondeterminism = 0
        self.quarantines = 0
        self.workspace_bytes = 0
        self.workspace_files = 0
        self.workspace_inodes = 0
        self.quota_failures = 0

    def _stage(self, stage_id: str) -> StageAccount:
        return self.stages.setdefault(stage_id, StageAccount(stage_id))

    def record_hit(
        self,
        stage_id: str,
        source: str = "local",
        saved_cpu_ms: int = 0,
        saved_wall_ms: int = 0,
        saved_compiler_ms: int = 0,
        saved_model_tokens: int = 0,
    ) -> None:
        account = self._stage(stage_id)
        if source == "remote":
            account.remote_hits += 1
        elif source == "partial":
            account.partial_hits += 1
        else:
            account.local_hits += 1
        account.saved_cpu_ms += saved_cpu_ms
        account.saved_wall_ms += saved_wall_ms
        account.saved_compiler_ms += saved_compiler_ms
        account.saved_model_tokens += saved_model_tokens
        self.metrics.increment("elmos_cache_hits_total", 1, stage_id=stage_id, outcome=source)
        self.metrics.increment("elmos_saved_cpu_ms_total", saved_cpu_ms, stage_id=stage_id)
        self.metrics.increment("elmos_saved_model_tokens_total", saved_model_tokens, stage_id=stage_id)

    def record_miss(
        self,
        stage_id: str,
        reasons: Sequence[MissReason] = (),
        executed_cpu_ms: int = 0,
        executed_wall_ms: int = 0,
    ) -> None:
        account = self._stage(stage_id)
        account.misses += 1
        account.executed_cpu_ms += executed_cpu_ms
        account.executed_wall_ms += executed_wall_ms
        for reason in reasons or (MissReason.NO_ENTRY,):
            key = str(reason)
            account.miss_reasons[key] = account.miss_reasons.get(key, 0) + 1
            self.metrics.increment(
                "elmos_cache_misses_total", 1, stage_id=stage_id, miss_reason=key
            )

    def record_storage(
        self, stored: int = 0, deduplicated: int = 0, restored: int = 0, evicted: int = 0
    ) -> None:
        self.bytes_stored += stored
        self.bytes_deduplicated += deduplicated
        self.bytes_restored += restored
        self.bytes_evicted += evicted
        self.metrics.gauge("elmos_cache_bytes_stored", self.bytes_stored)
        self.metrics.gauge("elmos_cache_bytes_deduplicated", self.bytes_deduplicated)

    def record_transfer(self, uploaded: int = 0, downloaded: int = 0) -> None:
        self.bytes_uploaded += uploaded
        self.bytes_downloaded += downloaded
        self.metrics.increment("elmos_remote_bytes_uploaded_total", uploaded)
        self.metrics.increment("elmos_remote_bytes_downloaded_total", downloaded)

    def record_incident(self, kind: str) -> None:
        mapping = {
            "stale_lease": "stale_leases",
            "recovery": "recovery_attempts",
            "digest_mismatch": "digest_mismatches",
            "corruption": "corruptions",
            "nondeterminism": "nondeterminism",
            "quarantine": "quarantines",
            "quota": "quota_failures",
        }
        attribute = mapping.get(kind)
        if attribute is None:
            return
        setattr(self, attribute, getattr(self, attribute) + 1)
        self.metrics.increment("elmos_incidents_total", 1, outcome=kind)

    def record_workspace(self, bytes_used: int, files: int, inodes: int = 0) -> None:
        self.workspace_bytes = bytes_used
        self.workspace_files = files
        self.workspace_inodes = inodes
        self.metrics.gauge("elmos_workspace_bytes", bytes_used)
        self.metrics.gauge("elmos_workspace_files", files)

    def overall(self) -> dict[str, Any]:
        total = sum(account.total for account in self.stages.values())
        hits = sum(account.local_hits + account.remote_hits for account in self.stages.values())
        return {
            "stages": [account.to_dict() for account in sorted(self.stages.values(), key=lambda a: a.stage_id)],
            "overall_hit_rate": round(hits / total, 4) if total else 0.0,
            "saved": {
                "cpu_ms": sum(a.saved_cpu_ms for a in self.stages.values()),
                "wall_ms": sum(a.saved_wall_ms for a in self.stages.values()),
                "compiler_ms": sum(a.saved_compiler_ms for a in self.stages.values()),
                "model_tokens": sum(a.saved_model_tokens for a in self.stages.values()),
            },
            "bytes": {
                "stored": self.bytes_stored,
                "deduplicated": self.bytes_deduplicated,
                "restored": self.bytes_restored,
                "uploaded": self.bytes_uploaded,
                "downloaded": self.bytes_downloaded,
                "evicted": self.bytes_evicted,
            },
            "incidents": {
                "stale_leases": self.stale_leases,
                "recovery_attempts": self.recovery_attempts,
                "digest_mismatches": self.digest_mismatches,
                "corruptions": self.corruptions,
                "nondeterminism": self.nondeterminism,
                "quarantines": self.quarantines,
                "quota_failures": self.quota_failures,
            },
            "workspace": {
                "bytes": self.workspace_bytes,
                "files": self.workspace_files,
                "inodes": self.workspace_inodes,
            },
        }

    def top_miss_reasons(self, limit: int = 10) -> list[tuple[str, int]]:
        totals: dict[str, int] = defaultdict(int)
        for account in self.stages.values():
            for reason, count in account.miss_reasons.items():
                totals[reason] += count
        return sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:limit]


# --------------------------------------------------------------------------
# benchmarks and SLOs
# --------------------------------------------------------------------------
BENCHMARK_SCENARIOS: tuple[str, ...] = (
    "identical-rerun",
    "formatting-only",
    "private-body",
    "public-api",
    "route-event-schema",
    "rule-pack-upgrade",
    "toolchain-upgrade",
    "dependency-lock",
    "prompt-model-snapshot",
    "remote-outage-recovery",
)


@dataclass(frozen=True)
class BenchmarkResult:
    scenario: str
    stage_hit_rate: float
    wall_ms: float
    saved_wall_ms: float
    saved_model_tokens: int
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "stage_hit_rate": round(self.stage_hit_rate, 4),
            "wall_ms": round(self.wall_ms, 2),
            "saved_wall_ms": round(self.saved_wall_ms, 2),
            "saved_model_tokens": self.saved_model_tokens,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class Slo:
    name: str
    metric: str
    quantile: float
    budget_ms: float | None = None
    min_hit_rate: float | None = None

    def evaluate(self, observed: float) -> dict[str, Any]:
        if self.budget_ms is not None:
            passed = observed <= self.budget_ms
            return {
                "name": self.name,
                "observed": round(observed, 3),
                "budget_ms": self.budget_ms,
                "passed": passed,
            }
        passed = self.min_hit_rate is None or observed >= self.min_hit_rate
        return {
            "name": self.name,
            "observed": round(observed, 4),
            "min_hit_rate": self.min_hit_rate,
            "passed": passed,
        }


DEFAULT_SLOS: tuple[Slo, ...] = (
    Slo("lookup-p95", SPAN_LOOKUP, 0.95, budget_ms=50.0),
    Slo("workspace-allocation-p95", "elmos.workspace.allocate", 0.95, budget_ms=2000.0),
    Slo("seal-p95", SPAN_SEAL, 0.95, budget_ms=200.0),
    Slo("promote-p95", SPAN_PROMOTE, 0.95, budget_ms=500.0),
    Slo("checkpoint-p95", SPAN_CHECKPOINT, 0.95, budget_ms=1500.0),
    Slo("resume-p95", SPAN_RESUME, 0.95, budget_ms=3000.0),
    Slo("publish-p95", SPAN_PUBLISH, 0.95, budget_ms=5000.0),
    Slo("no-change-reuse", "hit_rate:identical-rerun", 0.0, min_hit_rate=0.95),
    Slo("small-change-reuse", "hit_rate:private-body", 0.0, min_hit_rate=0.70),
)


class PerformanceGate:
    """Regression gate: SLO breaches fail the release, not a dashboard."""

    def __init__(self, slos: Sequence[Slo] = DEFAULT_SLOS) -> None:
        self.slos = list(slos)

    def evaluate(
        self, tracer: Tracer, benchmarks: Mapping[str, BenchmarkResult] | None = None
    ) -> dict[str, Any]:
        spans = tracer.summary()
        benchmarks = benchmarks or {}
        results: list[dict[str, Any]] = []
        for slo in self.slos:
            if slo.metric.startswith("hit_rate:"):
                scenario = slo.metric.split(":", 1)[1]
                benchmark = benchmarks.get(scenario)
                if benchmark is None:
                    results.append({"name": slo.name, "passed": False, "observed": None, "reason": "not measured"})
                    continue
                results.append(slo.evaluate(benchmark.stage_hit_rate))
                continue
            summary = spans.get(slo.metric)
            if summary is None:
                results.append({"name": slo.name, "passed": True, "observed": None, "reason": "no samples"})
                continue
            results.append(slo.evaluate(summary["p95"]))
        return {
            "passed": all(item.get("passed", False) for item in results),
            "results": results,
        }


@dataclass
class TuningKnobs:
    """The levers the performance skill asks operators to tune, with defaults."""

    dag_granularity: str = "file"
    local_lru_bytes: int = 20 * 1024**3
    compression: str = "zstd"
    chunk_size_bytes: int = 8 * 1024 * 1024
    prefetch_depth: int = 2
    max_concurrency: int = 8
    locality_scheduling: bool = True
    recompute_bypass_ratio: float = 1.0

    def recommend(self, accounting: CacheAccounting, tracer: Tracer) -> list[str]:
        """Turn measurements into concrete, checkable suggestions."""
        advice: list[str] = []
        overall = accounting.overall()
        if overall["overall_hit_rate"] < 0.5 and accounting.stages:
            worst = min(accounting.stages.values(), key=lambda a: a.hit_rate)
            advice.append(
                f"lowest hit rate is {worst.stage_id} at {worst.hit_rate:.0%}; "
                f"top miss reasons {sorted(worst.miss_reasons.items())[:3]}"
            )
        spans = tracer.summary()
        restore = spans.get(SPAN_MATERIALIZE)
        if restore and restore["p95"] > 1000:
            advice.append("materialisation p95 exceeds 1s; consider reflink materialisation or larger chunks")
        if accounting.bytes_downloaded > accounting.bytes_restored * 4 and accounting.bytes_restored:
            advice.append("remote download volume dominates local restore; raise prefetch_depth")
        if accounting.quota_failures:
            advice.append("workspace quota failures observed; raise quota_gb_per_run or shard the DAG")
        if accounting.nondeterminism:
            advice.append("nondeterministic stages detected; pin seeds and model snapshots before caching")
        if not advice:
            advice.append("no tuning action indicated by the current measurements")
        return advice


def summarize_run(
    accounting: CacheAccounting, tracer: Tracer, gate: PerformanceGate | None = None
) -> dict[str, Any]:
    gate = gate or PerformanceGate()
    return {
        "schema_version": SCHEMA_VERSION,
        "accounting": accounting.overall(),
        "top_miss_reasons": accounting.top_miss_reasons(),
        "spans": tracer.summary(),
        "slo": gate.evaluate(tracer),
    }


def correlation_fields(
    run_id: str,
    node_id: str | None = None,
    action_key: str | None = None,
    artifact_digest: str | None = None,
    staged_file_id: str | None = None,
    checkpoint_id: str | None = None,
    lease_epoch: int | None = None,
) -> dict[str, Any]:
    """The correlation set every failure trace must carry."""
    return {
        key: value
        for key, value in {
            "run_id": run_id,
            "node_id": node_id,
            "action_key": action_key,
            "artifact_digest": artifact_digest,
            "staged_file_id": staged_file_id,
            "checkpoint_id": checkpoint_id,
            "lease_epoch": lease_epoch,
        }.items()
        if value is not None
    }


def iter_span_names(spans: Iterable[Span]) -> tuple[str, ...]:
    return tuple(sorted({span.name for span in spans}))
