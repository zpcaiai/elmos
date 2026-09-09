"""Prepare an unsigned independent-verification bundle for generation.

This module never signs. An Agent or the original executor cannot satisfy the
independent-verifier gate. The receipt stays NOT_RUN / NOT_CERTIFIED until a
distinct human verifier replays the recorded command in their own environment
and supplies a trust-store signature outside this repository.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

REPLAY_COMMAND = (
    "uv --directory engines/project-synthesis-engine run --locked "
    "python scripts/run_production_matrix.py --output docs/project-synthesis/local-production-profile-matrix.json"
)


def build_independent_replay_bundle(
    *,
    matrix_path: Path,
    output_dir: Path,
    producer: str,
) -> dict[str, Any]:
    if not matrix_path.is_file() or matrix_path.is_symlink():
        raise ValueError("INDEPENDENT_REPLAY_MATRIX_MISSING")
    raw = matrix_path.read_bytes()
    matrix = json.loads(raw.decode("utf-8"))
    if not isinstance(matrix, dict):
        raise ValueError("INDEPENDENT_REPLAY_MATRIX_INVALID")
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = {
        "schema_version": "1.0.0",
        "kind": "elmos.generation-independent-replay-bundle",
        "producer": producer,
        "producer_role": "executor",
        "replay": REPLAY_COMMAND,
        "matrix_path": str(matrix_path),
        "matrix_sha256": hashlib.sha256(raw).hexdigest(),
        "passed_count": matrix.get("passed_count"),
        "case_count": matrix.get("case_count"),
        "entity_shapes": sorted(
            {
                str(case.get("entity_shape"))
                for case in matrix.get("cases", [])
                if isinstance(case, dict)
            }
        ),
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "independent_verifier": None,
        "independent_verification_status": "NOT_RUN",
        "external_certification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "signature": None,
        "trust_store": None,
        "forbidden": [
            "An Agent cannot sign this bundle.",
            "The executor who produced the matrix cannot be the verifier.",
            "A local PASSED_LOCAL receipt cannot be rewritten to CERTIFIED here.",
        ],
        "required_from_verifier": [
            "Replay the recorded command in a distinct environment.",
            "Write a certification-request.json whose signer_id is not the producer.",
            "Attach a trust-store anchor outside this repository.",
            "Keep independent_verification_status NOT_RUN until that signature verifies.",
        ],
    }
    target = output_dir / "independent-replay-bundle.json"
    target.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return bundle
