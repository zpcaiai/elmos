"""stdin/stdout-only CLI for catalog inspection and bounded plan compilation."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .canonical import MAX_JSON_BYTES, CanonicalError, strict_json_loads
from .catalog import CatalogError
from .contracts import ContractError
from .runtime import RuntimeError, capability_manifest, execute_skill


def _emit(value: Any, stream: Any) -> None:
    stream.write(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("catalog", "run"))
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "catalog":
            _emit(capability_manifest(), sys.stdout)
            return 0
        document = strict_json_loads(
            sys.stdin.read(MAX_JSON_BYTES + 1), label="stdin request"
        )
        _emit(execute_skill(document), sys.stdout)
        return 0
    except (
        CanonicalError,
        CatalogError,
        ContractError,
        RuntimeError,
    ) as exc:
        _emit(
            {
                "schema_version": "elmos.database-bigdata.error.v1",
                "state": "BLOCKED",
                "code": "REQUEST_OR_RUNTIME_CONTRACT_REJECTED",
                "error_type": type(exc).__name__,
                "message": str(exc),
                "external_effects_performed": False,
                "skill_implementation_state": "DECLARED",
                "runtime_evidence": "NOT_RUN",
                "production_certification": "NOT_CERTIFIED",
            },
            sys.stderr,
        )
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
