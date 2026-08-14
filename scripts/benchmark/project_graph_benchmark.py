#!/usr/bin/env python3
"""Reproducible benchmark for the repository-discovery path.

`docs/batch34/BENCHMARK_SPEC.md` requires latency percentiles, throughput,
environment digest, and cold/warm runs to be recorded.  Nothing in the
repository produced them, so module selection for optimisation work had no
evidence behind it.  This closes that gap for the one path that every
repository-scale run goes through.

The output is a single JSON document so a run can be diffed against an earlier
one, and so a regression is a failed comparison rather than someone's memory of
how fast it used to feel.

    python3 scripts/benchmark/project_graph_benchmark.py CORPUS [CORPUS ...] \
        --repeats 15 --output evidence/benchmarks/project-graph.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

ENGINE_SRC = Path(__file__).resolve().parents[2] / "engines" / "polyglot-route-engine" / "src"
sys.path.insert(0, str(ENGINE_SRC))

from elmos_polyglot_route import project_graph as pg  # noqa: E402


def environment_digest() -> dict[str, object]:
    """Identify the machine well enough that two runs can be compared at all.

    A percentile is meaningless without it: 40ms on eight idle cores and 40ms
    on a throttled shared runner are not the same measurement.
    """
    source = hashlib.sha256()
    for path in sorted(ENGINE_SRC.rglob("*.py")):
        source.update(path.relative_to(ENGINE_SRC).as_posix().encode())
        source.update(path.read_bytes())
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "system": platform.system(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "engine_source_sha256": source.hexdigest(),
    }


def percentiles(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)

    def at(fraction: float) -> float:
        # Nearest-rank, so a percentile is always an observation that actually
        # happened rather than an interpolation between two that did not.
        index = max(0, min(len(ordered) - 1, round(fraction * len(ordered) + 0.5) - 1))
        return ordered[index]

    return {
        "min_ms": ordered[0] * 1000,
        "p50_ms": at(0.50) * 1000,
        "p95_ms": at(0.95) * 1000,
        "p99_ms": at(0.99) * 1000,
        "max_ms": ordered[-1] * 1000,
        "mean_ms": statistics.fmean(ordered) * 1000,
        "stdev_ms": (statistics.stdev(ordered) * 1000) if len(ordered) > 1 else 0.0,
    }


def measure(corpus: Path, repeats: int) -> dict[str, object]:
    scanned, issues = pg._walk_repository(corpus)
    file_count = len(scanned)
    byte_count = sum(item.byte_count or 0 for item in scanned)

    # The first observation is reported separately rather than discarded: a cold
    # page cache is what a fresh runner actually experiences, and hiding it
    # behind a warm-up flatters every number after it.
    cold_start = time.perf_counter()
    graph = pg.build_project_graph(corpus, "benchmark/corpus")
    cold = time.perf_counter() - cold_start

    walk_samples: list[float] = []
    graph_samples: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        pg._walk_repository(corpus)
        walk_samples.append(time.perf_counter() - start)
        start = time.perf_counter()
        pg.build_project_graph(corpus, "benchmark/corpus")
        graph_samples.append(time.perf_counter() - start)

    warm = statistics.median(graph_samples)
    return {
        "corpus": corpus.as_posix(),
        "files": file_count,
        "bytes": byte_count,
        "inventory_issues": len(issues),
        "graph_sha256": graph["graph_sha256"],
        "repeats": repeats,
        "cold_ms": cold * 1000,
        "warm_median_ms": warm * 1000,
        "cold_penalty": (cold / warm) if warm else None,
        "walk_repository": percentiles(walk_samples),
        "build_project_graph": percentiles(graph_samples),
        "throughput": {
            "files_per_second": file_count / warm if warm else None,
            "megabytes_per_second": (byte_count / 1e6) / warm if warm else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpora", nargs="+", type=Path)
    parser.add_argument("--repeats", type=int, default=15)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    report = {
        "schema": "elmos.benchmark.project-graph.v1",
        "environment": environment_digest(),
        "measurements": [measure(corpus.resolve(), arguments.repeats) for corpus in arguments.corpora],
    }

    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(text)

    for measurement in report["measurements"]:
        graph = measurement["build_project_graph"]
        print(
            f"{Path(measurement['corpus']).name:<14} "
            f"files={measurement['files']:>5}  "
            f"p50={graph['p50_ms']:8.1f}ms  p95={graph['p95_ms']:8.1f}ms  "
            f"cold={measurement['cold_ms']:8.1f}ms  "
            f"{measurement['throughput']['files_per_second']:>8,.0f} files/s"
        )
    if arguments.output:
        print(f"\nwritten to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
