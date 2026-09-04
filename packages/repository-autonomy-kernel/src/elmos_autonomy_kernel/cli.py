"""Command-line surface for the autonomy kernel.

Three verbs, deliberately: ``catalogue`` says what this build can do,
``run`` invokes one capability, and ``doctor`` reports whether the build is
complete and its stores are reachable.  Everything reads JSON on stdin or from a
file and writes JSON on stdout, so the kernel composes with a shell the same way
it composes with a workflow engine.

The exit code is the contract: 0 for SUCCEEDED, 2 for PARTIAL, 3 for
INTERRUPTED, 4 for FAILED, 5 for NOT_APPLICABLE.  A caller must be able to tell
a partial result from a success without parsing anything, because "did it work"
answered by a zero exit code on a partial run is how half-finished work reaches
production.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import _bind_all_capabilities
from .contracts import Status, canonical_json
from .errors import CODES, KernelError
from .registry import DESCRIPTORS, bound_skills, dispatch, unbound_skills

__all__ = ["main"]

_EXIT_FOR_STATUS = {
    Status.SUCCEEDED: 0,
    Status.PARTIAL: 2,
    Status.INTERRUPTED: 3,
    Status.FAILED: 4,
    Status.NOT_APPLICABLE: 5,
}

_MAX_INPUT_BYTES = 32 * 1024 * 1024


def _read_request(path: str | None) -> Mapping[str, Any]:
    raw = sys.stdin.buffer.read() if path in (None, "-") else Path(path).read_bytes()
    if len(raw) > _MAX_INPUT_BYTES:
        raise KernelError(
            code="INPUT_TOO_LARGE",
            message=f"request exceeds {_MAX_INPUT_BYTES} bytes",
            recommended_action="pass large inputs through the artifact store",
        )
    if not raw.strip():
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="no request was supplied on stdin or --input",
            recommended_action="pipe a JSON object in, or pass --input FILE",
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"request is not valid JSON: {exc}",
            recommended_action="check the request body",
        ) from exc
    if not isinstance(payload, dict):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"request must be a JSON object, got {type(payload).__name__}",
            recommended_action="wrap the payload in an object",
        )
    return payload


def _catalogue() -> dict[str, Any]:
    bound = set(bound_skills())
    return {
        "package": "elmos-autonomy-kernel",
        "capabilities": [
            {
                "id": descriptor.skill_id,
                "title": descriptor.title,
                "priority": descriptor.priority,
                "capabilityPack": descriptor.capability_pack,
                "version": descriptor.version,
                "inputs": list(descriptor.inputs),
                "outputs": list(descriptor.outputs),
                "invariants": list(descriptor.invariants),
                "gates": list(descriptor.gates),
                "bound": descriptor.skill_id in bound,
            }
            for descriptor in sorted(DESCRIPTORS.values(), key=lambda item: item.skill_id)
        ],
        "counts": {
            "declared": len(DESCRIPTORS),
            "bound": len(bound),
            "unbound": len(unbound_skills()),
            "failureCodes": len(CODES),
        },
    }


def _doctor() -> dict[str, Any]:
    """Report build completeness.

    A capability declared but unbound is reported by name.  Summarising it as a
    count would let a partial build look like a healthy one, which is the same
    class of lie as reporting an unmeasured cost as zero.
    """

    missing = list(unbound_skills())
    return {
        "complete": not missing,
        "declared": len(DESCRIPTORS),
        "bound": len(bound_skills()),
        "unboundCapabilities": missing,
        "failureCodesRegistered": len(CODES),
        "pythonVersion": sys.version.split()[0],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="elmos-autonomy",
        description="Invoke the ELMOS repository autonomy kernel.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("catalogue", help="list every declared capability and whether it is bound")
    sub.add_parser("doctor", help="report build completeness")

    run = sub.add_parser("run", help="invoke one capability")
    run.add_argument("capability", help="capability id, e.g. durable-run-orchestrator")
    run.add_argument("--input", "-i", default="-",
                     help="request JSON file, or - for stdin (default)")

    args = parser.parse_args(argv)
    _bind_all_capabilities()

    try:
        if args.command == "catalogue":
            print(canonical_json(_catalogue()))
            return 0
        if args.command == "doctor":
            report = _doctor()
            print(canonical_json(report))
            return 0 if report["complete"] else 1

        request = _read_request(args.input)
        result = dispatch(args.capability, request)
        print(canonical_json(result.to_payload()))
        return _EXIT_FOR_STATUS[result.status]
    except KernelError as error:
        print(canonical_json({"error": error.to_payload()}), file=sys.stderr)
        return 4


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
