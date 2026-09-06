"""Fresh-process CAS API comparisons; local engineering evidence, not an SLO."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import resource
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "engines/build-cache-engine/src"),
    str(ROOT / "engines/polyglot-route-engine/src"),
]
MODES = ("python-bytes", "native-bytes", "python-file", "native-file", "python-stream", "python-read", "native-read")


def sample(mode: str, mib: int, library: Path) -> dict[str, object]:
    os.environ["ELMOS_NATIVE_LIB"] = str(library)
    from elmos_build_cache import native_cas_bridge
    from elmos_build_cache.cas import ContentAddressableStore

    if mode.startswith("native"):
        lib = native_cas_bridge.get_native_lib()
        if lib is None or (mode == "native-file" and not hasattr(lib, "elmos_cas_put_fd")):
            raise RuntimeError("required native ABI unavailable; refusing a mislabeled fallback sample")
    with tempfile.TemporaryDirectory(prefix="elmos-r2-cas-profile-") as temporary:
        root = Path(temporary)
        source = root / "source"
        random_bytes = random.Random(20260906)
        with source.open("wb") as output:
            for _ in range(mib * 16):
                output.write(random_bytes.randbytes(65536))
        store = ContentAddressableStore(
            root / "store", native_file_io=mode == "native-file", native_bytes_io=mode in {"native-bytes", "native-read"},
        )
        payload = source.read_bytes() if mode.endswith("bytes") else None
        if mode.endswith("read"):
            digest = store.put_file(source)
        tracemalloc.start()
        start = time.perf_counter()
        if mode.endswith("read"):
            read_payload = store.get_bytes(digest)
        elif payload is not None:
            digest = store.put_bytes(payload)
        elif mode.endswith("file"):
            digest = store.put_file(source)
        else:
            with source.open("rb") as stream:
                digest = store.put_stream(stream)
        elapsed = time.perf_counter() - start
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        if mode.endswith("read"):
            assert digest == "sha256:" + hashlib.sha256(read_payload).hexdigest()
        verified = hashlib.sha256()
        for chunk in store.open_stream(digest):
            verified.update(chunk)
        assert digest == "sha256:" + verified.hexdigest()
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {
            "mode": mode, "seconds": elapsed, "output_identity": digest,
            "python_peak_bytes": peak, "process_peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-library", type=Path, required=True)
    parser.add_argument("--file-mib", type=int, default=8, choices=range(1, 65))
    parser.add_argument("--rounds", type=int, default=3, choices=range(1, 11))
    parser.add_argument("--sample", choices=MODES)
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    library = arguments.native_library.resolve(strict=True)
    if arguments.sample:
        print(json.dumps(sample(arguments.sample, arguments.file_mib, library), sort_keys=True))
        return
    from elmos_polyglot_route.process_io import run_bounded
    samples = []
    for _ in range(arguments.rounds):
        for mode in arguments.modes:
            result = run_bounded([
                sys.executable, str(Path(__file__).resolve()), "--sample", mode,
                "--file-mib", str(arguments.file_mib), "--native-library", str(library),
            ], timeout=180, check=True, max_stream_bytes=64 * 1024)
            samples.append(json.loads(result.stdout))
    assert len({sample["output_identity"] for sample in samples}) == 1
    sources = [
        ROOT / "engines/build-cache-engine/src/elmos_build_cache/cas.py",
        ROOT / "engines/build-cache-engine/src/elmos_build_cache/native_cas_bridge.py",
        Path(__file__).resolve(),
    ]
    report = {
        "evidence": "LOCAL_EXECUTED_SELF_ATTESTED", "production_slo": "NOT_RUN",
        "independent_verification": "NOT_RUN", "shared_development_host": True,
        "file_mib": arguments.file_mib, "rounds": arguments.rounds,
        "host": platform.platform(), "python": platform.python_version(),
        "native_library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        "samples": samples,
        "median_seconds": {
            mode: statistics.median(item["seconds"] for item in samples if item["mode"] == mode) for mode in arguments.modes
        },
        "boundaries": [
            "Data generation, read-fixture publication, and post-operation verification are outside the timed region.",
            "Bytes inputs are allocated before tracemalloc starts; native allocations are not counted by tracemalloc.",
            "RSS includes process setup and inputs; shared-host scheduling noise is not production tail latency.",
            "Three samples do not establish p95/p99 or cross-platform superiority.",
        ],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        with arguments.output.open("x", encoding="utf-8") as output:
            output.write(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
