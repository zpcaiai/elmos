#!/usr/bin/env python3
"""Assess external-gate prerequisites for the Spring Boot 4.1.0 Pack.

This command is a read-only readiness audit. It does not execute a source
repository, transform code, create a container, or modify Pack certification
evidence. In particular, a rootless preflight result is only a prerequisite
observation; it cannot promote local route evidence or manufacture an
independent verifier result.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACK = ROOT / "framework-packs" / "spring-to-boot-4-1-0"
ROOTLESS_RUNNER = ROOT / "scripts" / "operations" / "rootless_project_runner.py"
EXTERNAL_EVIDENCE_BOUNDARY = {
    "authorized_customer_repository": "NOT_RUN",
    "customer_holdout": "NOT_RUN",
    "customer_acceptance": "NOT_RUN",
    "rootless_runner": "NOT_RUN",
    "rootless_transformer": "NOT_RUN",
    "rootless_verifier": "NOT_RUN",
    "independent_review": "NOT_RUN",
    "external_certification": "NOT_RUN",
}


class ReadinessError(RuntimeError):
    """The Pack is malformed for a readiness assessment."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"INVALID_JSON:{path}") from exc
    if not isinstance(value, dict):
        raise ReadinessError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def non_readme_files(path: Path) -> list[str]:
    if not path.is_dir():
        return []
    return sorted(
        str(item.relative_to(path))
        for item in path.rglob("*")
        if item.is_file() and item.name.lower() not in {"readme", "readme.md"}
    )


def corpus_readiness(path: Path, role: str) -> dict[str, Any]:
    files = non_readme_files(path)
    if not files:
        return {
            "role": role,
            "status": "NOT_RUN",
            "evidence_files": [],
            "reason": "NO_INDEPENDENT_CORPUS_EVIDENCE",
        }
    return {
        "role": role,
        "status": "EVIDENCE_PENDING",
        "evidence_files": files,
        "reason": "CORPUS_PRESENT_BUT_NO_EXECUTION_OR_INDEPENDENT_VERIFICATION",
    }


def rootless_preflight(engine: Path | None) -> dict[str, Any]:
    if engine is None:
        return {
            "role": "protected_rootless_runner",
            "status": "NOT_RUN",
            "reason": "CONTAINER_ENGINE_NOT_SELECTED",
        }
    if not engine.is_absolute() or not engine.is_file():
        return {
            "role": "protected_rootless_runner",
            "status": "BLOCKED",
            "engine": str(engine),
            "reason": "CONTAINER_ENGINE_INVALID",
        }
    try:
        result = subprocess.run(
            [sys.executable, str(ROOTLESS_RUNNER), "preflight", "--engine", str(engine)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "role": "protected_rootless_runner",
            "status": "BLOCKED",
            "engine": str(engine),
            "reason": f"PREFLIGHT_EXECUTION_FAILED:{type(exc).__name__}",
        }
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if result.returncode == 0 and payload.get("status") == "READY":
        status = "PREFLIGHT_READY"
        reason = "PREFLIGHT_ONLY_EXECUTION_NOT_RUN"
    else:
        status = "BLOCKED"
        reason = str(payload.get("reason") or "PREFLIGHT_FAILED")
    return {
        "role": "protected_rootless_runner",
        "status": status,
        "engine": str(engine),
        "reason": reason,
        "exit_code": result.returncode,
    }


def assess(pack: Path, *, engine: Path | None = None) -> dict[str, Any]:
    manifest = load_json(pack / "pack.json")
    if manifest.get("pack_key") != "spring-to-boot-4-1-0":
        raise ReadinessError("PACK_KEY_MISMATCH")
    if manifest.get("status") != "experimental":
        raise ReadinessError("PACK_STATUS_MUST_REMAIN_EXPERIMENTAL")
    matrix = load_json(pack / "version-matrix.json")
    tuples = matrix.get("tuples")
    if not isinstance(tuples, list):
        raise ReadinessError("VERSION_MATRIX_TUPLES_INVALID")
    local_routes = [
        item["id"]
        for item in tuples
        if isinstance(item, dict) and item.get("execution_status") == "PASSED_LOCAL"
    ]
    holdout = corpus_readiness(pack / "corpus" / "holdout", "independent_holdout")
    representative = corpus_readiness(
        pack / "corpus" / "real-repository", "representative_repository"
    )
    checks = [rootless_preflight(engine), holdout, representative]
    checks.append(
        {
            "role": "independent_verifier",
            "status": "NOT_RUN",
            "reason": "NO_SEPARATE_VERIFIER_RECEIPT_BOUND",
        }
    )
    return {
        "schema_version": 1,
        "record_type": "SPRING_BOOT_4_1_EXTERNAL_READINESS_AUDIT",
        "pack_key": manifest["pack_key"],
        "local_route_evidence": {
            "status": "PASSED_LOCAL" if local_routes else "NOT_RUN",
            "routes": sorted(local_routes),
        },
        "readiness_checks": checks,
        "external_evidence_boundary": dict(EXTERNAL_EVIDENCE_BOUNDARY),
        "certification_status": "NOT_CERTIFIED",
        "decision": "READY_FOR_EXTERNAL_GATE"
        if all(item["status"] == "PREFLIGHT_READY" for item in checks)
        else "NOT_READY_FOR_EXTERNAL_GATE",
        "certification_eligible": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-dir", type=Path, default=DEFAULT_PACK)
    parser.add_argument(
        "--engine",
        type=Path,
        help="optional absolute Docker or Podman executable for read-only preflight",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = assess(
            args.pack_dir.resolve(),
            # Keep the caller's executable spelling. The rootless runner's
            # allowlist intentionally evaluates the declared entry point and
            # must not be bypassed or changed by this read-only wrapper.
            engine=args.engine.absolute() if args.engine else None,
        )
    except (OSError, ReadinessError) as exc:
        print(json.dumps({"status": "FAILED", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["decision"] == "READY_FOR_EXTERNAL_GATE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
