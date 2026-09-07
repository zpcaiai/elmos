"""Low-cardinality, thread-safe operational metrics for the local service."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import math
import threading
import time
from typing import Iterator, Mapping


_DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(values: tuple[tuple[str, str], ...]) -> str:
    if not values:
        return ""
    return "{" + ",".join(f'{key}="{_escape(value)}"' for key, value in values) + "}"


@dataclass(slots=True)
class _Histogram:
    buckets: tuple[float, ...]
    counts: list[int]
    total_count: int = 0
    total_sum: float = 0.0

    @classmethod
    def create(cls, buckets: tuple[float, ...]) -> "_Histogram":
        return cls(buckets, [0] * len(buckets))

    def observe(self, value: float) -> None:
        self.total_count += 1
        self.total_sum += value
        for index, bucket in enumerate(self.buckets):
            if value <= bucket:
                self.counts[index] += 1


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._histograms: dict[tuple[str, tuple[tuple[str, str], ...]], _Histogram] = {}

    @staticmethod
    def _key(name: str, labels: Mapping[str, str] | None) -> tuple[str, tuple[tuple[str, str], ...]]:
        if not name or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_:" for char in name):
            raise ValueError("invalid metric name")
        normalized = tuple(sorted((str(key), str(value)) for key, value in (labels or {}).items()))
        if len(normalized) > 8:
            raise ValueError("metric label cardinality is too high")
        return name, normalized

    def increment(self, name: str, amount: float = 1.0, labels: Mapping[str, str] | None = None) -> None:
        if not math.isfinite(amount) or amount < 0:
            raise ValueError("counter amount must be finite and non-negative")
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + amount

    def gauge(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        if not math.isfinite(value):
            raise ValueError("gauge value must be finite")
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def observe(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str] | None = None,
        *,
        buckets: tuple[float, ...] = _DEFAULT_BUCKETS,
    ) -> None:
        if not math.isfinite(value) or value < 0:
            raise ValueError("histogram observation must be finite and non-negative")
        if tuple(sorted(set(buckets))) != buckets:
            raise ValueError("histogram buckets must be sorted and unique")
        key = self._key(name, labels)
        with self._lock:
            histogram = self._histograms.setdefault(key, _Histogram.create(buckets))
            if histogram.buckets != buckets:
                raise ValueError("histogram buckets cannot change")
            histogram.observe(value)

    @contextmanager
    def timed(self, name: str, labels: Mapping[str, str] | None = None) -> Iterator[None]:
        started = time.monotonic()
        try:
            yield
        finally:
            self.observe(name, time.monotonic() - started, labels)

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (name, labels), value in sorted(self._counters.items()):
                lines.append(f"{name}{_labels(labels)} {value:g}")
            for (name, labels), value in sorted(self._gauges.items()):
                lines.append(f"{name}{_labels(labels)} {value:g}")
            for (name, labels), histogram in sorted(self._histograms.items()):
                for bucket, count in zip(histogram.buckets, histogram.counts):
                    bucket_labels = tuple(sorted((*labels, ("le", f"{bucket:g}"))))
                    lines.append(f"{name}_bucket{_labels(bucket_labels)} {count}")
                infinity_labels = tuple(sorted((*labels, ("le", "+Inf"))))
                lines.append(f"{name}_bucket{_labels(infinity_labels)} {histogram.total_count}")
                lines.append(f"{name}_sum{_labels(labels)} {histogram.total_sum:g}")
                lines.append(f"{name}_count{_labels(labels)} {histogram.total_count}")
        return "\n".join(lines) + ("\n" if lines else "")


__all__ = ["MetricsRegistry"]
