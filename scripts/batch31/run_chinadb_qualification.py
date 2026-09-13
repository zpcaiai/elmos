#!/usr/bin/env python3
"""Validate externally produced ChinaDB Protocol 1.2.0 evidence.

This command is deliberately an intake-only gate. It cannot provision a
database, mint trust identities, sign receipts, or manufacture performance
measurements. The operator must provide a request containing the original
signed receipt chain and a separately pinned trust store outside the Git
checkout.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSPILER_SRC = (
    REPO_ROOT / "engines" / "database-data-engine" / "sql-transpiler" / "src"
)
if str(TRANSPILER_SRC) not in sys.path:
    sys.path.insert(0, str(TRANSPILER_SRC))


def _outside_repository(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return resolved
    raise ValueError(
        f"{label} must be supplied from an external evidence mount, not the Git checkout"
    )


def _write_result(path: Path | None, result: dict[str, object]) -> None:
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if path is None:
        sys.stdout.write(payload)
        return
    destination = path.expanduser().resolve()
    try:
        destination.relative_to(REPO_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("qualification output must not overwrite checked-in evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an external ChinaDB qualification receipt chain"
    )
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--trust-store", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--expected-runner-attestation-digest",
        help="Bind required targets to the dedicated Runner attestation digest",
    )
    completion = parser.add_mutually_exclusive_group(required=True)
    completion.add_argument(
        "--require-target",
        action="append",
        dest="required_targets",
        metavar="TARGET_ID",
        help="Require one target to reach PRODUCTION_DEFINITION_OF_DONE; repeatable",
    )
    completion.add_argument(
        "--require-all",
        action="store_true",
        help="Require all 13 targets to reach PRODUCTION_DEFINITION_OF_DONE",
    )
    args = parser.parse_args()

    try:
        request_path = _outside_repository(args.request, "qualification request")
        trust_path = _outside_repository(args.trust_store, "operator trust store")
        from elmos_sql_transpiler.production_qualification import (
            evaluate_production_qualification,
            parse_production_qualification_json,
            parse_production_trust_store_json,
        )

        request = parse_production_qualification_json(request_path.read_bytes())
        trust_store = parse_production_trust_store_json(trust_path.read_bytes())
        result = evaluate_production_qualification(
            request,
            trust_store=trust_store,
            now=datetime.now(UTC),
        )
    except (OSError, ValueError) as error:
        print(f"CHINADB_QUALIFICATION_INPUT_INVALID: {error}", file=sys.stderr)
        return 2

    states = {target["targetId"]: target["state"] for target in result["targets"]}
    required = set(states) if args.require_all else set(args.required_targets or ())
    unknown = required - set(states)
    if unknown:
        print(
            f"CHINADB_QUALIFICATION_TARGET_UNKNOWN: {sorted(unknown)}",
            file=sys.stderr,
        )
        return 2
    expected_attestation = args.expected_runner_attestation_digest
    if expected_attestation is not None:
        if not (
            expected_attestation.startswith("sha256:")
            and len(expected_attestation) == 71
            and all(
                character in "0123456789abcdef"
                for character in expected_attestation[7:]
            )
        ):
            print(
                "CHINADB_QUALIFICATION_INPUT_INVALID: expected Runner attestation must be a sha256 digest",
                file=sys.stderr,
            )
            return 2
        request_targets = {target["targetId"]: target for target in request["targets"]}
        mismatched = []
        for target_id in sorted(required):
            execution = request_targets[target_id].get("receipts", {}).get("execution")
            observed = None
            if isinstance(execution, dict):
                payload = execution.get("payload")
                if isinstance(payload, dict):
                    performance = payload.get("performanceSummary")
                    if isinstance(performance, dict):
                        observed = performance.get("runnerAttestationDigest")
            if observed != expected_attestation:
                mismatched.append(target_id)
        if mismatched:
            print(
                "CHINADB_QUALIFICATION_RUNNER_ATTESTATION_MISMATCH: "
                + json.dumps(mismatched),
                file=sys.stderr,
            )
            return 1
    incomplete = {
        target_id: states[target_id]
        for target_id in sorted(required)
        if states[target_id] != "PRODUCTION_DEFINITION_OF_DONE"
    }
    if incomplete:
        print(
            "CHINADB_QUALIFICATION_NOT_COMPLETE: "
            + json.dumps(incomplete, sort_keys=True),
            file=sys.stderr,
        )
        return 1
    try:
        _write_result(args.output, result)
    except (OSError, ValueError) as error:
        print(f"CHINADB_QUALIFICATION_OUTPUT_INVALID: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
