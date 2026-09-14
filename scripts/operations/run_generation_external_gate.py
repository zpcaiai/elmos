#!/usr/bin/env python3
"""Validate real external Project Synthesis runtime receipts.

This gate deliberately performs no source scan and cannot manufacture external
evidence. It accepts only content-addressed receipts produced by an authorized
hosted run and keeps certification separate from external runtime verification.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = ROOT / "engines" / "project-synthesis-engine"
sys.path.insert(0, str(ENGINE_ROOT / "src"))

from elmos_project_synthesis.evidence_identity import source_identity  # noqa: E402
from elmos_project_synthesis.models import SUPPORTED_LANGUAGES  # noqa: E402

AUTH_MODES = ("jwt", "oidc")
EXPECTED_PAIRS = {(language, auth) for language in SUPPORTED_LANGUAGES for auth in AUTH_MODES}
REQUIRED_CHECKS = {
    "native_build",
    "native_tests",
    "database_migration",
    "startup_liveness",
    "startup_readiness",
    "auth_negative",
    "crud",
    "tenant_isolation",
    "cleanup",
}
DIGEST = re.compile(r"^[0-9a-f]{64}$")
IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,199}$")
PROVIDERS = {"AWS_RDS", "GCP_CLOUD_SQL", "ALIYUN_RDS", "OTHER_EXTERNAL"}


class ExternalGateError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp(value: Any) -> dt.datetime:
    if not isinstance(value, str):
        raise ExternalGateError("OBSERVED_AT_INVALID")
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as error:
        raise ExternalGateError("OBSERVED_AT_INVALID") from error
    if parsed.tzinfo is None:
        raise ExternalGateError("OBSERVED_AT_TIMEZONE_REQUIRED")
    return parsed.astimezone(dt.UTC)


def _safe_evidence_file(directory: Path, raw_path: Any) -> Path:
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path:
        raise ExternalGateError("EVIDENCE_PATH_INVALID")
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ExternalGateError("EVIDENCE_PATH_INVALID")
    candidate = directory.joinpath(relative)
    if candidate.is_symlink() or not candidate.is_file():
        raise ExternalGateError("EVIDENCE_FILE_MISSING_OR_UNSAFE")
    resolved = candidate.resolve(strict=True)
    root = directory.resolve(strict=True)
    if root not in resolved.parents:
        raise ExternalGateError("EVIDENCE_PATH_ESCAPE")
    return resolved


def validate_receipt(
    receipt: dict[str, Any],
    *,
    evidence_dir: Path,
    engine_sha256: str,
    now: dt.datetime,
) -> list[str]:
    reasons: list[str] = []

    def require(condition: bool, reason: str) -> None:
        if not condition:
            reasons.append(reason)

    require(receipt.get("kind") == "elmos.project-synthesis.external-runtime-receipt", "KIND_INVALID")
    require(receipt.get("schema_version") == "1.0.0", "SCHEMA_VERSION_INVALID")
    language = receipt.get("language")
    auth_mode = receipt.get("auth_mode")
    require(language in SUPPORTED_LANGUAGES, "LANGUAGE_INVALID")
    require(auth_mode in AUTH_MODES, "AUTH_MODE_INVALID")
    require(receipt.get("status") == "PASSED", "RUNTIME_STATUS_NOT_PASSED")
    require(receipt.get("environment_class") == "EXTERNAL_HOSTED", "ENVIRONMENT_CLASS_INVALID")

    subject = receipt.get("evidence_subject")
    require(isinstance(subject, dict), "EVIDENCE_SUBJECT_INVALID")
    if isinstance(subject, dict):
        require(subject.get("engine_source_sha256") == engine_sha256, "ENGINE_SOURCE_DIGEST_MISMATCH")
        require(
            isinstance(subject.get("generated_artifact_sha256"), str)
            and DIGEST.fullmatch(subject["generated_artifact_sha256"]) is not None,
            "GENERATED_ARTIFACT_DIGEST_INVALID",
        )

    provider = receipt.get("provider")
    require(isinstance(provider, dict), "PROVIDER_INVALID")
    if isinstance(provider, dict):
        require(provider.get("service") in PROVIDERS, "PROVIDER_SERVICE_INVALID")
        require(provider.get("database_engine") == "postgresql", "DATABASE_ENGINE_INVALID")
        require(provider.get("database_version") == "17.5", "DATABASE_VERSION_INVALID")
        require(provider.get("ssl_verified") is True, "DATABASE_TLS_NOT_VERIFIED")
        require(provider.get("minimum_tls") in {"TLSv1.2", "TLSv1.3"}, "DATABASE_TLS_VERSION_INVALID")
        require(isinstance(provider.get("region"), str) and bool(provider["region"]), "PROVIDER_REGION_MISSING")

    executor = receipt.get("executor")
    verifier = receipt.get("verifier")
    require(isinstance(executor, str) and IDENTITY.fullmatch(executor) is not None, "EXECUTOR_INVALID")
    require(isinstance(verifier, str) and IDENTITY.fullmatch(verifier) is not None, "VERIFIER_INVALID")
    require(executor != verifier, "INDEPENDENT_VERIFIER_REQUIRED")

    checks = receipt.get("checks")
    require(isinstance(checks, dict), "CHECKS_INVALID")
    if isinstance(checks, dict):
        require(set(checks) == REQUIRED_CHECKS, "CHECK_SET_INCOMPLETE_OR_UNKNOWN")
        require(all(value == "PASSED" for value in checks.values()), "CHECK_NOT_PASSED")

    try:
        observed_at = _timestamp(receipt.get("observed_at"))
        require(observed_at <= now + dt.timedelta(minutes=5), "OBSERVED_AT_IN_FUTURE")
        require(now - observed_at <= dt.timedelta(days=30), "RECEIPT_EXPIRED")
    except ExternalGateError as error:
        reasons.append(str(error))

    evidence = receipt.get("evidence")
    require(isinstance(evidence, list) and bool(evidence), "EVIDENCE_FILES_REQUIRED")
    seen_paths: set[str] = set()
    if isinstance(evidence, list):
        for item in evidence:
            if not isinstance(item, dict):
                reasons.append("EVIDENCE_ENTRY_INVALID")
                continue
            raw_path = item.get("path")
            if not isinstance(raw_path, str) or raw_path in seen_paths:
                reasons.append("EVIDENCE_PATH_DUPLICATED_OR_INVALID")
                continue
            seen_paths.add(raw_path)
            expected = item.get("sha256")
            if not isinstance(expected, str) or DIGEST.fullmatch(expected) is None:
                reasons.append("EVIDENCE_DIGEST_INVALID")
                continue
            try:
                actual = _sha256(_safe_evidence_file(evidence_dir, raw_path))
            except ExternalGateError as error:
                reasons.append(str(error))
                continue
            if actual != expected:
                reasons.append("EVIDENCE_DIGEST_MISMATCH")
    return sorted(set(reasons))


def run_gate(evidence_dir: Path, *, now: dt.datetime | None = None) -> dict[str, Any]:
    if evidence_dir.is_symlink() or not evidence_dir.is_dir():
        return {
            "status": "BLOCKED",
            "decision": "NOT_CERTIFIED",
            "reasons": ["EXTERNAL_EVIDENCE_DIRECTORY_MISSING_OR_UNSAFE"],
        }
    observed = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    engine = source_identity(ENGINE_ROOT)
    results: list[dict[str, Any]] = []
    pairs: set[tuple[str, str]] = set()
    for path in sorted(evidence_dir.glob("*.receipt.json")):
        if path.is_symlink() or path.stat().st_size > 1024 * 1024:
            results.append({"receipt": path.name, "status": "FAILED", "reasons": ["RECEIPT_FILE_UNSAFE"]})
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            results.append({"receipt": path.name, "status": "FAILED", "reasons": ["RECEIPT_JSON_INVALID"]})
            continue
        if not isinstance(loaded, dict):
            results.append({"receipt": path.name, "status": "FAILED", "reasons": ["RECEIPT_OBJECT_REQUIRED"]})
            continue
        pair = (str(loaded.get("language")), str(loaded.get("auth_mode")))
        reasons = validate_receipt(
            loaded,
            evidence_dir=evidence_dir,
            engine_sha256=str(engine["sha256"]),
            now=observed,
        )
        if pair in pairs:
            reasons.append("PROFILE_RECEIPT_DUPLICATED")
        pairs.add(pair)
        results.append(
            {
                "receipt": path.name,
                "language": pair[0],
                "auth_mode": pair[1],
                "status": "PASSED" if not reasons else "FAILED",
                "reasons": sorted(set(reasons)),
            }
        )
    missing = sorted(f"{language}/{auth}" for language, auth in EXPECTED_PAIRS - pairs)
    extra = sorted(f"{language}/{auth}" for language, auth in pairs - EXPECTED_PAIRS)
    passed = not missing and not extra and len(results) == 16 and all(item["status"] == "PASSED" for item in results)
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.project-synthesis.external-runtime-gate",
        "observed_at": observed.replace(microsecond=0).isoformat(),
        "status": "PASSED_EXTERNAL" if passed else "BLOCKED",
        "decision": "READY_FOR_INDEPENDENT_CERTIFICATION" if passed else "NOT_CERTIFIED",
        "engine_source": engine,
        "expected_profile_count": 16,
        "validated_profile_count": sum(item["status"] == "PASSED" for item in results),
        "missing_profiles": missing,
        "extra_profiles": extra,
        "receipts": results,
        "certification_status": "NOT_CERTIFIED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate externally produced Project Synthesis receipts.")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = run_gate(arguments.evidence_dir)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        if arguments.output.is_symlink() or arguments.output.suffix != ".json":
            raise SystemExit("OUTPUT_PATH_UNSAFE")
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] == "PASSED_EXTERNAL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
