"""Run a real Temporal probe or one of its replaceable worker processes."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from elmos_openhands.qualification_probes import ProbeResult
from elmos_openhands.temporal_qualification import run_temporal_probe, run_temporal_worker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_temporal_probe")
    subparsers = parser.add_subparsers(dest="command", required=True)
    probe = subparsers.add_parser("probe")
    probe.add_argument("--address", required=True)
    probe.add_argument("--evidence-root", required=True)
    worker = subparsers.add_parser("worker")
    worker.add_argument("--address", required=True)
    worker.add_argument("--task-queue", required=True)
    worker.add_argument("--marker", required=True)
    worker.add_argument("--stall-once", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "worker":
        asyncio.run(
            run_temporal_worker(
                args.address,
                args.task_queue,
                args.marker,
                stall_once=args.stall_once,
            )
        )
        return 0
    try:
        script = str(Path(__file__).resolve(strict=True))
        result = asyncio.run(
            run_temporal_probe(
                address=args.address,
                worker_command=(sys.executable, script),
                evidence_root=args.evidence_root,
            )
        )
    except Exception as error:  # noqa: BLE001 - CLI boundary emits bounded failure evidence
        result = ProbeResult(
            "temporal-real",
            "FAIL",
            {},
            (type(error).__name__,),
            {"error": str(error)[:2000]},
        )
    print(json.dumps(result.as_dict(), sort_keys=True, separators=(",", ":")))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
