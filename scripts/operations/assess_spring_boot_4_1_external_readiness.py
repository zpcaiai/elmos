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
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACK = ROOT / "framework-packs" / "spring-to-boot-4-1-0"
ROOTLESS_RUNNER = ROOT / "scripts" / "operations" / "rootless_project_runner.py"
DEFAULT_LOCAL_EXECUTION_RECEIPT = (
    DEFAULT_PACK
    / "certification"
    / "local-execution"
    / "2026-08-27"
    / "local-rootless-execution.json"
)
# A Podman machine can briefly reject `info` while its VM or API socket is
# coming up. Retry only that transport-level condition; policy failures such
# as a non-rootless engine must remain immediate and explicit.
PREFLIGHT_MAX_ATTEMPTS = 3
PREFLIGHT_RETRY_DELAY_SECONDS = 0.5
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


def local_execution_readiness(
    pack: Path, receipt_path: Path | None = None
) -> dict[str, Any]:
    """Validate local execution without promoting it to external evidence."""

    root = (pack / "certification" / "local-execution").resolve()
    candidate = (receipt_path or DEFAULT_LOCAL_EXECUTION_RECEIPT).resolve()
    base = {"role": "local_execution", "receipt": str(candidate)}
    if not candidate.is_relative_to(root):
        return {
            **base,
            "status": "BLOCKED",
            "reason": "LOCAL_EXECUTION_RECEIPT_OUTSIDE_PACK_BOUNDARY",
        }
    if candidate.is_symlink() or not candidate.is_file():
        return {
            **base,
            "status": "NOT_RUN",
            "reason": "LOCAL_EXECUTION_RECEIPT_MISSING",
        }
    try:
        receipt = load_json(candidate)
    except ReadinessError as error:
        return {
            **base,
            "status": "BLOCKED",
            "reason": f"LOCAL_EXECUTION_RECEIPT_INVALID:{error}",
        }

    failures: list[str] = []
    raw_evidence = receipt.get("raw_evidence")
    expected_raw_evidence = {
        "route-reference-evidence.json",
        "rootless-diagnose.json",
        "rootless-start.json",
        "rootless-status.json",
        "rootless-stop.json",
    }
    raw_payloads: dict[str, dict[str, Any]] = {}
    if not isinstance(raw_evidence, list) or {
        item.get("path") for item in raw_evidence if isinstance(item, dict)
    } != expected_raw_evidence or len(raw_evidence) != len(expected_raw_evidence):
        failures.append("raw_evidence must bind the five local execution receipts")
    else:
        evidence_root = candidate.parent.resolve()
        for item in raw_evidence:
            if not isinstance(item, dict):
                failures.append("raw_evidence entries must be objects")
                break
            relative_path = item.get("path")
            if not isinstance(relative_path, str):
                failures.append("raw_evidence.path must be a relative path")
                break
            raw_path = Path(relative_path)
            if raw_path.is_absolute() or ".." in raw_path.parts:
                failures.append("raw_evidence paths must stay inside the receipt directory")
                break
            evidence_file = candidate.parent / raw_path
            try:
                resolved_evidence_file = evidence_file.resolve(strict=True)
                resolved_evidence_file.relative_to(evidence_root)
            except (OSError, ValueError):
                failures.append(f"raw_evidence file is missing or escapes the Pack: {relative_path}")
                break
            if evidence_file.is_symlink() or not evidence_file.is_file():
                failures.append(f"raw_evidence file is not a regular file: {relative_path}")
                break
            expected_bytes = item.get("bytes")
            expected_sha256 = item.get("sha256")
            if not isinstance(expected_bytes, int) or expected_bytes <= 0:
                failures.append(f"raw_evidence bytes are invalid: {relative_path}")
                break
            if not isinstance(expected_sha256, str) or not re.fullmatch(
                r"[0-9a-f]{64}", expected_sha256
            ):
                failures.append(f"raw_evidence sha256 is invalid: {relative_path}")
                break
            if evidence_file.stat().st_size != expected_bytes:
                failures.append(f"raw_evidence byte count mismatch: {relative_path}")
                break
            if hashlib.sha256(evidence_file.read_bytes()).hexdigest() != expected_sha256:
                failures.append(f"raw_evidence digest mismatch: {relative_path}")
                break
            try:
                raw_payloads[relative_path] = load_json(evidence_file)
            except ReadinessError:
                failures.append(f"raw_evidence is not a JSON object: {relative_path}")
                break

        if not failures:
            route = raw_payloads["route-reference-evidence.json"]
            source = route.get("source")
            target = route.get("target")
            source_runtime = source.get("runtime") if isinstance(source, dict) else None
            target_runtime = target.get("runtime") if isinstance(target, dict) else None
            receipt_source = receipt.get("source")
            receipt_target = receipt.get("target")
            if route.get("route_id") != receipt.get("route_id"):
                failures.append("route raw evidence does not bind route_id")
            if route.get("execution_status") != "PASSED_LOCAL":
                failures.append("route raw evidence must be PASSED_LOCAL")
            for label, raw_side, receipt_side, expected_version in (
                ("source", source, receipt_source, "3.5.3"),
                ("target", target, receipt_target, "4.1.0"),
            ):
                if not isinstance(raw_side, dict) or not isinstance(receipt_side, dict):
                    failures.append(f"route raw evidence is missing {label} details")
                    continue
                if raw_side.get("boot") != expected_version:
                    failures.append(f"route raw evidence {label} Boot version mismatch")
                if raw_side.get("build") != "PASSED":
                    failures.append(f"route raw evidence {label} build must be PASSED")
                if not isinstance(raw_side.get("runtime"), dict):
                    failures.append(f"route raw evidence {label} runtime is missing")
                raw_runtime = raw_side.get("runtime")
                if not isinstance(raw_runtime, dict):
                    continue
                if raw_runtime.get("jar_sha256") != receipt_side.get("jar_sha256"):
                    failures.append(f"route raw evidence {label} JAR digest is not bound")
            for label, runtime in (("source", source_runtime), ("target", target_runtime)):
                if not isinstance(runtime, dict):
                    continue
                health = runtime.get("health")
                if not isinstance(health, dict) or health.get("status") != "UP":
                    failures.append(f"route raw evidence {label} health must be UP")

            diagnose = raw_payloads["rootless-diagnose.json"]
            start = raw_payloads["rootless-start.json"]
            status = raw_payloads["rootless-status.json"]
            stop = raw_payloads["rootless-stop.json"]
            receipt_rootless = receipt.get("rootless_runtime")
            if not isinstance(receipt_rootless, dict):
                failures.append("rootless runtime receipt is missing")
            else:
                if diagnose.get("status") != "READY" or diagnose.get("rootless") is not True:
                    failures.append("rootless diagnose must be READY and rootless")
                if diagnose.get("build_network") != "none":
                    failures.append("rootless diagnose must bind build_network=none")
                if diagnose.get("toolchain_cache") != "CACHED":
                    failures.append("rootless diagnose must bind the cached toolchain")
                if receipt_rootless.get("base_image") not in diagnose.get("required_images", []):
                    failures.append("rootless base image is not bound to diagnose evidence")
                for field in (
                    "container_id",
                    "host_port",
                    "executor",
                    "health",
                    "network_policy",
                    "read_only",
                    "user",
                ):
                    if start.get(field) != receipt_rootless.get(field):
                        failures.append(f"rootless start evidence is not bound: {field}")
                if start.get("status") != receipt_rootless.get("start_status"):
                    failures.append("rootless start status is not bound")
                if status.get("status") != "RUNNING" or status.get("health") != start.get("health"):
                    failures.append("rootless status must prove the healthy RUNNING state")
                if status.get("host_port") != start.get("host_port"):
                    failures.append("rootless status host port is not bound")
                if stop.get("status") != receipt_rootless.get("stop_status"):
                    failures.append("rootless stop status is not bound")
                if stop.get("job_id") != receipt_rootless.get("job_id"):
                    failures.append("rootless stop job is not bound")
                if stop.get("requested_lease_id") != receipt_rootless.get("lease_id"):
                    failures.append("rootless stop lease is not bound")
                target_jar_sha256 = (
                    receipt_target.get("jar_sha256")
                    if isinstance(receipt_target, dict)
                    else None
                )
                if receipt_rootless.get("target_jar_sha256") != target_jar_sha256:
                    failures.append("rootless target JAR digest is not bound to route evidence")

    exact_values = {
        "pack_key": "spring-to-boot-4-1-0",
        "evidence_class": "LOCAL_NON_CERTIFYING_ROOTLESS_EXECUTION",
        "execution_scope": "LOCAL_DEVELOPMENT_REFERENCE_FIXTURE_ONLY",
        "execution_status": "PASSED_LOCAL_ROOTLESS",
        "certification_status": "NOT_CERTIFIED",
        "route_id": "boot-3.5-maven-to-boot-4.1.0-java-21",
    }
    for field, expected in exact_values.items():
        if receipt.get(field) != expected:
            failures.append(f"{field}={expected}")
    if receipt.get("certification_eligible") is not False:
        failures.append("certification_eligible=false")
    if receipt.get("tuple") != {
        "source_spring_boot": "3.5.3",
        "source_java": "21",
        "target_spring_boot": "4.1.0",
        "target_java": "21",
        "build": "maven-3.9.11",
    }:
        failures.append("tuple must bind the exact Boot 3.5.3 to Boot 4.1.0 route")

    required_stages = {
        "source_build",
        "transformation",
        "target_build",
        "source_startup",
        "target_startup",
        "rootless_target_startup",
    }
    stages = receipt.get("stages")
    if not isinstance(stages, dict) or set(stages) != required_stages:
        failures.append("stages must contain exactly the six local execution stages")
    elif any(value != "PASSED" for value in stages.values()):
        failures.append("all local execution stages must be PASSED")

    rootless = receipt.get("rootless_runtime")
    if not isinstance(rootless, dict):
        failures.append("rootless_runtime is missing")
    else:
        for field, expected in {
            "status": "PASSED_LOCAL",
            "executor": "ROOTLESS_CONTAINER",
            "engine": "podman",
            "build_network": "none",
            "health": "loopback-identity-verified",
            "application_health": "UP",
            "user": "501:20",
        }.items():
            if rootless.get(field) != expected:
                failures.append(f"rootless_runtime.{field}={expected}")
        for field in ("rootless", "read_only", "network_internal_only"):
            if rootless.get(field) is not True:
                failures.append(f"rootless_runtime.{field}=true")
        if (
            rootless.get("start_status") != "RUNNING"
            or rootless.get("stop_status") != "STOPPED"
        ):
            failures.append("rootless runtime must prove RUNNING then STOPPED")
        target_digest = rootless.get("target_jar_sha256")
        if not isinstance(target_digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", target_digest
        ):
            failures.append("rootless target JAR must be content-addressed")

    for role in (
        "independent_holdout",
        "representative_repository",
        "independent_verification",
    ):
        if receipt.get(role) != "NOT_RUN":
            failures.append(f"{role}=NOT_RUN")
    boundary = receipt.get("external_evidence_boundary")
    if not isinstance(boundary, dict) or set(boundary) != set(EXTERNAL_EVIDENCE_BOUNDARY):
        failures.append("external_evidence_boundary inventory is incomplete")
    elif any(value != "NOT_RUN" for value in boundary.values()):
        failures.append("external_evidence_boundary values must remain NOT_RUN")
    if failures:
        return {
            **base,
            "status": "BLOCKED",
            "reason": f"LOCAL_EXECUTION_RECEIPT_INVALID:{failures[0]}",
        }
    return {
        **base,
        "status": "EXECUTED_LOCAL_NON_CERTIFYING",
        "reason": "LOCAL_SOURCE_TARGET_TRANSFORM_STARTUP_AND_ROOTLESS_STARTUP_RECORDED",
        "receipt_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
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
    command = [
        sys.executable,
        str(ROOTLESS_RUNNER),
        "preflight",
        "--engine",
        str(engine),
    ]
    for attempt in range(1, PREFLIGHT_MAX_ATTEMPTS + 1):
        try:
            result = subprocess.run(
                command,
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
                "attempts": attempt,
            }
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        if result.returncode == 0 and payload.get("status") == "READY":
            return {
                "role": "protected_rootless_runner",
                "status": "PREFLIGHT_READY",
                "engine": str(engine),
                "reason": "PREFLIGHT_ONLY_EXECUTION_NOT_RUN",
                "exit_code": result.returncode,
                "attempts": attempt,
            }
        reason = str(payload.get("reason") or "PREFLIGHT_FAILED")
        if reason != "CONTAINER_ENGINE_UNAVAILABLE" or attempt == PREFLIGHT_MAX_ATTEMPTS:
            return {
                "role": "protected_rootless_runner",
                "status": "BLOCKED",
                "engine": str(engine),
                "reason": reason,
                "exit_code": result.returncode,
                "attempts": attempt,
            }
        time.sleep(PREFLIGHT_RETRY_DELAY_SECONDS)
    raise AssertionError("preflight retry loop exhausted unexpectedly")


def assess(
    pack: Path,
    *,
    engine: Path | None = None,
    local_execution_receipt: Path | None = None,
) -> dict[str, Any]:
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
    rootless = rootless_preflight(engine)
    local_execution = local_execution_readiness(pack, local_execution_receipt)
    if (
        rootless["status"] == "PREFLIGHT_READY"
        and local_execution["status"] == "EXECUTED_LOCAL_NON_CERTIFYING"
    ):
        rootless["reason"] = (
            "PREFLIGHT_AND_LOCAL_ROOTLESS_EXECUTION_RECORDED_EXTERNAL_NOT_RUN"
        )
        rootless["execution_receipt_sha256"] = local_execution["receipt_sha256"]
    checks = [rootless, local_execution, holdout, representative]
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
    parser.add_argument(
        "--local-execution-receipt",
        type=Path,
        help="optional Pack-bound local non-certifying execution receipt",
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
            local_execution_receipt=(
                args.local_execution_receipt.absolute()
                if args.local_execution_receipt
                else None
            ),
        )
    except (OSError, ReadinessError) as exc:
        print(json.dumps({"status": "FAILED", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["decision"] == "READY_FOR_EXTERNAL_GATE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
