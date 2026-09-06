#!/usr/bin/env python3
"""Local, isolated before/after kernel measurements; never a production SLO gate.

Run with the polyglot Python 3.12 venv. Every sample is a fresh subprocess;
input creation precedes timing. Native mode requires the newly built library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[2]
for engine, package in (("build-cache-engine", "src"), ("polyglot-route-engine", "src")):
    sys.path.insert(0, str(ROOT / "engines" / engine / package))


def sample(mode: str, file_mib: int, graph_files: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="elmos-profile-") as temporary:
        root = Path(temporary)
        if mode.startswith("cas-"):
            from elmos_build_cache.cas import ContentAddressableStore
            source = root / "source.bin"
            block = hashlib.shake_256(b"elmos-concurrency-profile-v1").digest(65536)
            with source.open("wb") as output:
                for _ in range(file_mib * 16):
                    output.write(block)
            store = ContentAddressableStore(root / "store")
            if mode == "cas-rust":
                from elmos_build_cache.native_cas_bridge import get_native_lib
                library = get_native_lib()
                if library is None or not hasattr(library, "elmos_cas_put_fd"):
                    raise RuntimeError("new Rust fd ABI is required")
            tracemalloc.start()
            start = time.perf_counter()
            if mode == "cas-rust":
                # Explicit ABI comparison, independent of the selected production default.
                from elmos_build_cache.native_cas_bridge import native_put_file_descriptor
                with source.open("rb") as input_file:
                    digest = native_put_file_descriptor(store.root, input_file.fileno(), file_mib << 20, None, "blob")
            else:
                with source.open("rb") as input_file:
                    digest = store.put_stream(input_file)
            elapsed = time.perf_counter() - start
            peak = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            # Independently verify the published bytes, outside the timed region.
            verifier = hashlib.sha256()
            for chunk in store.open_stream(digest):
                verifier.update(chunk)
            assert digest == "sha256:" + verifier.hexdigest()
            identity = digest
        else:
            from elmos_polyglot_route.project_graph import (
                build_project_graph, capture_project_snapshot,
                materialize_project_graph, verify_project_snapshot,
            )
            project = root / "project"
            project.mkdir()
            for index in range(graph_files):
                (project / f"source_{index}.py").write_text(
                    f"def function_{index}(value: int) -> int:\n    return value + {index}\n"
                    + "# workload padding\n" * 256
                )
            tracemalloc.start()
            start = time.perf_counter()
            if mode == "graph-repeated":
                first = build_project_graph(project, "local:profile")
                assert build_project_graph(project, "local:profile") == first
                assert build_project_graph(project, "local:profile") == first
            else:
                snapshot = capture_project_snapshot(project)
                first = materialize_project_graph(snapshot, "local:profile")
                assert verify_project_snapshot(snapshot)
                assert verify_project_snapshot(snapshot)
            elapsed = time.perf_counter() - start
            peak = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            identity = hashlib.sha256(json.dumps(first, sort_keys=True).encode()).hexdigest()
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != "darwin":
            rss *= 1024
        return {"mode": mode, "seconds": elapsed, "python_peak_bytes": peak,
                "process_peak_rss_bytes": rss, "output_identity": identity}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", choices=["cas-python", "cas-rust", "graph-repeated", "graph-snapshot"])
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--file-mib", type=int, default=64)
    parser.add_argument("--graph-files", type=int, default=64)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 30 or not 1 <= args.file_mib <= 512 or not 1 <= args.graph_files <= 1000:
        parser.error("bounded profile dimensions exceeded")
    if args.sample:
        print(json.dumps(sample(args.sample, args.file_mib, args.graph_files)))
        return
    source_paths = [Path(__file__).resolve(), ROOT / "engines/build-cache-engine/src/elmos_build_cache/cas.py",
                    ROOT / "engines/build-cache-engine/src/elmos_build_cache/native_cas_bridge.py",
                    ROOT / "engines/polyglot-route-engine/src/elmos_polyglot_route/project_graph.py"]
    digests = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
    native_path = os.environ.get("ELMOS_NATIVE_LIB")
    native_digest = hashlib.sha256(Path(native_path).read_bytes()).hexdigest() if native_path else None
    results = []
    for _ in range(args.rounds):
        for mode in ("cas-python", "cas-rust", "graph-repeated", "graph-snapshot"):
            command = [sys.executable, str(Path(__file__).resolve()), "--sample", mode,
                       "--file-mib", str(args.file_mib), "--graph-files", str(args.graph_files)]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=300)
            results.append(json.loads(result.stdout))
    for modes in (("cas-python", "cas-rust"), ("graph-repeated", "graph-snapshot")):
        assert len({r["output_identity"] for r in results if r["mode"] in modes}) == 1
    report = {"evidence": "LOCAL_EXECUTED_SELF_ATTESTED", "production_slo": "NOT_RUN",
              "host": platform.platform(), "python": platform.python_version(),
              "native_library": os.environ.get("ELMOS_NATIVE_LIB"),
              "native_library_sha256": native_digest, "source_sha256": digests,
              "file_mib": args.file_mib, "graph_files": args.graph_files, "samples": results,
              "medians": {mode: {field: statistics.median(r[field] for r in results if r["mode"] == mode)
                                  for field in ("seconds", "python_peak_bytes", "process_peak_rss_bytes")}
                          for mode in {r["mode"] for r in results}}}
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded)


if __name__ == "__main__":
    main()
