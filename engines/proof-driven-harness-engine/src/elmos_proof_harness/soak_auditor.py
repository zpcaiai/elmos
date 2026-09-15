"""Industrial-grade soak testing runner and physical resource leak auditor (FDs, RSS, Threads)."""

from __future__ import annotations

import gc
import logging
import os
import platform
import resource
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

logger = logging.getLogger("elmos_proof_harness.soak_auditor")


class ResourceLeakError(RuntimeError):
    """Raised when soak testing detects physical resource leakage."""


@dataclass(frozen=True)
class ResourceAuditSnapshot:
    timestamp: float
    open_fd_count: int
    rss_memory_mb: float
    active_thread_count: int
    tracked_objects_count: int


@dataclass(frozen=True)
class LeakReport:
    initial: ResourceAuditSnapshot
    final: ResourceAuditSnapshot
    fd_delta: int
    rss_growth_mb: float
    thread_delta: int
    object_delta: int
    iterations_completed: int
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float

    @property
    def has_fd_leak(self) -> bool:
        return self.fd_delta > 0

    @property
    def has_thread_leak(self) -> bool:
        return self.thread_delta > 0


class ResourceLeakAuditor:
    """Audits process physical resources (open file descriptors, RSS memory, threads) to detect leaks."""

    @classmethod
    def get_open_fd_count(cls) -> int:
        """Determines the number of currently open file descriptors in the process."""
        dev_fd = Path("/dev/fd")
        proc_fd = Path(f"/proc/{os.getpid()}/fd")

        if dev_fd.exists():
            try:
                # /dev/fd lists currently opened descriptors
                return len(list(dev_fd.iterdir()))
            except Exception:
                pass
        elif proc_fd.exists():
            try:
                return len(list(proc_fd.iterdir()))
            except Exception:
                pass

        # Fallback estimation
        return -1

    @classmethod
    def get_rss_memory_mb(cls) -> float:
        """Retrieves maximum resident set size in Megabytes."""
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # On macOS, ru_maxrss is in bytes; on Linux, it is in kilobytes.
        if platform.system().lower() == "darwin":
            return usage.ru_maxrss / (1024.0 * 1024.0)
        else:
            return usage.ru_maxrss / 1024.0

    @classmethod
    def take_snapshot(cls) -> ResourceAuditSnapshot:
        """Forces garbage collection and captures a deterministic physical resource snapshot."""
        gc.collect()
        time.sleep(0.01)
        return ResourceAuditSnapshot(
            timestamp=time.monotonic(),
            open_fd_count=cls.get_open_fd_count(),
            rss_memory_mb=cls.get_rss_memory_mb(),
            active_thread_count=threading.active_count(),
            tracked_objects_count=len(gc.get_objects()),
        )

    @classmethod
    def analyze(
        cls,
        baseline: ResourceAuditSnapshot,
        final: ResourceAuditSnapshot,
        iterations: int,
        latencies_ms: Sequence[float],
    ) -> LeakReport:
        sorted_lat = sorted(latencies_ms) if latencies_ms else [0.0]
        n = len(sorted_lat)

        def pct(p: float) -> float:
            idx = min(int(n * p), n - 1)
            return sorted_lat[idx]

        return LeakReport(
            initial=baseline,
            final=final,
            fd_delta=final.open_fd_count - baseline.open_fd_count if baseline.open_fd_count >= 0 else 0,
            rss_growth_mb=max(0.0, final.rss_memory_mb - baseline.rss_memory_mb),
            thread_delta=final.active_thread_count - baseline.active_thread_count,
            object_delta=final.tracked_objects_count - baseline.tracked_objects_count,
            iterations_completed=iterations,
            p50_latency_ms=pct(0.50),
            p95_latency_ms=pct(0.95),
            p99_latency_ms=pct(0.99),
        )


class SoakTestRunner:
    """Runs intensive repetitive workload loops to verify stability and zero resource leaks."""

    def __init__(
        self,
        max_allowed_rss_growth_mb: float = 15.0,
        max_allowed_fd_leak: int = 0,
        max_allowed_thread_leak: int = 0,
    ) -> None:
        self.max_rss_growth = max_allowed_rss_growth_mb
        self.max_fd_leak = max_allowed_fd_leak
        self.max_thread_leak = max_allowed_thread_leak

    def run_soak(
        self,
        workload_fn: Callable[[int], Any],
        iterations: int = 100,
        warmup_iterations: int = 5,
    ) -> LeakReport:
        """Executes a soak test with baseline and final resource leak assertions."""
        # 1. Warmup
        for i in range(warmup_iterations):
            workload_fn(i)

        # 2. Baseline
        baseline = ResourceLeakAuditor.take_snapshot()
        latencies: list[float] = []

        # 3. Execution loop
        for i in range(iterations):
            start = time.monotonic()
            workload_fn(i)
            elapsed_ms = (time.monotonic() - start) * 1000.0
            latencies.append(elapsed_ms)

        # 4. Final snapshot after full GC
        final = ResourceLeakAuditor.take_snapshot()
        report = ResourceLeakAuditor.analyze(baseline, final, iterations, latencies)

        # 5. Strict industrial assertions
        if report.fd_delta > self.max_fd_leak:
            raise ResourceLeakError(
                f"Soak test failed with open file descriptor leak: {report.fd_delta} new FDs unclosed "
                f"(initial={baseline.open_fd_count}, final={final.open_fd_count})"
            )

        if report.thread_delta > self.max_thread_leak:
            raise ResourceLeakError(
                f"Soak test failed with thread leak: {report.thread_delta} threads unjoined "
                f"(initial={baseline.active_thread_count}, final={final.active_thread_count})"
            )

        if report.rss_growth_mb > self.max_rss_growth:
            raise ResourceLeakError(
                f"Soak test exceeded allowable RSS memory growth: {report.rss_growth_mb:.2f}MB > limit {self.max_rss_growth}MB"
            )

        return report
