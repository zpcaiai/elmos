#!/usr/bin/env python3
"""Re-evaluate Batch 105-108 release receipts without trusting status fields.

This local gate can emit at most READY_FOR_EXTERNAL_GATE.  It cannot approve a
production deployment or certify the product, even when all supplied evidence
is internally consistent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_modernization_proof_image import (
    IMMUTABLE_REFERENCE,
    classify_scout_scan,
    is_local_registry,
)
from modernization_proof_release_state import (
    EXECUTED_AWAITING_VERIFICATION,
    EXTERNAL_BOUNDARIES,
    INDEPENDENTLY_VERIFIED,
    ReleaseStateFailure,
    validate_external_boundaries,
    validate_observation_transition,
)


SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_INDEPENDENT_ROLES = {"RAW_EXECUTION", "INDEPENDENT_VERIFICATION"}


def canonical_json(document: Any) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def add_blocker(blockers: list[str], blocker: str) -> None:
    if blocker not in blockers:
        blockers.append(blocker)


def resolve_evidence_path(raw_path: object, root: Path) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path:
        return None
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def verify_file_binding(
    binding: dict[str, Any], *, root: Path, prefix: str, blockers: list[str]
) -> Path | None:
    path = resolve_evidence_path(binding.get("path"), root)
    expected_sha = binding.get("sha256")
    expected_bytes = binding.get("byte_count")
    if path is None:
        add_blocker(blockers, f"{prefix}_PATH_INVALID")
        return None
    if not path.is_file():
        add_blocker(blockers, f"{prefix}_FILE_MISSING")
        return None
    if not isinstance(expected_bytes, int) or expected_bytes != path.stat().st_size:
        add_blocker(blockers, f"{prefix}_BYTE_COUNT_MISMATCH")
    if not isinstance(expected_sha, str) or not SHA256.fullmatch(expected_sha):
        add_blocker(blockers, f"{prefix}_SHA256_INVALID")
    elif sha256_file(path) != expected_sha:
        add_blocker(blockers, f"{prefix}_SHA256_MISMATCH")
    return path


def validate_scan(
    scan: dict[str, Any], *, evidence_root: Path, blockers: list[str]
) -> None:
    status = scan.get("status")
    if status == "PASSED":
        report = resolve_evidence_path(scan.get("report_path"), evidence_root)
        if report is None or not report.is_file():
            add_blocker(blockers, "VULNERABILITY_SCAN_REPORT_MISSING")
            return
        observed = classify_scout_scan(0, report)
        if observed.get("status") != "PASSED" or observed.get("finding_count") != 0:
            add_blocker(blockers, "VULNERABILITY_SCAN_NOT_CLEAN")
        if scan.get("exit_code") != 0:
            add_blocker(blockers, "VULNERABILITY_SCAN_EXIT_CODE_INVALID")
        if scan.get("report_sha256") != sha256_file(report):
            add_blocker(blockers, "VULNERABILITY_SCAN_SHA256_MISMATCH")
    elif status == "FAILED":
        add_blocker(blockers, "VULNERABILITY_SCAN_FAILED")
    elif status == "BLOCKED":
        add_blocker(blockers, "VULNERABILITY_SCAN_BLOCKED")
        if scan.get("reason") == "DOCKER_SCOUT_AUTHENTICATION_REQUIRED":
            add_blocker(blockers, "DOCKER_SCOUT_AUTHENTICATION_REQUIRED")
    elif status == "NOT_RUN":
        add_blocker(blockers, "VULNERABILITY_SCAN_NOT_RUN")
    else:
        add_blocker(blockers, "VULNERABILITY_SCAN_STATE_INVALID")


def validate_independent_evidence(
    boundary: str,
    record: object,
    *,
    source_commit: str,
    immutable_reference: str,
    evidence_root: Path,
    blockers: list[str],
) -> None:
    prefix = f"{boundary}_INDEPENDENT_VERIFICATION"
    if not isinstance(record, dict):
        add_blocker(blockers, f"{prefix}_MISSING")
        return
    if record.get("state") != INDEPENDENTLY_VERIFIED:
        add_blocker(blockers, f"{prefix}_STATE_INVALID")
    if record.get("source_commit") != source_commit:
        add_blocker(blockers, f"{prefix}_SOURCE_MISMATCH")
    if record.get("immutable_reference") != immutable_reference:
        add_blocker(blockers, f"{prefix}_IMAGE_MISMATCH")
    executor = record.get("executor")
    verifier = record.get("independent_verifier")
    if not isinstance(executor, str) or not executor:
        add_blocker(blockers, f"{prefix}_EXECUTOR_MISSING")
    if not isinstance(verifier, str) or not verifier:
        add_blocker(blockers, f"{prefix}_VERIFIER_MISSING")
    elif verifier == executor:
        add_blocker(blockers, f"{prefix}_SELF_VERIFICATION")
    if not isinstance(record.get("authorization_reference"), str) or not record.get(
        "authorization_reference"
    ):
        add_blocker(blockers, f"{prefix}_AUTHORIZATION_MISSING")
    evidence_refs = record.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        add_blocker(blockers, f"{prefix}_EVIDENCE_MISSING")
        return
    roles: set[str] = set()
    for index, item in enumerate(evidence_refs):
        if not isinstance(item, dict):
            add_blocker(blockers, f"{prefix}_EVIDENCE_{index}_INVALID")
            continue
        role = item.get("role")
        if isinstance(role, str):
            roles.add(role)
        verify_file_binding(
            item,
            root=evidence_root,
            prefix=f"{prefix}_EVIDENCE_{index}",
            blockers=blockers,
        )
    if not REQUIRED_INDEPENDENT_ROLES.issubset(roles):
        add_blocker(blockers, f"{prefix}_ROLES_INCOMPLETE")


def validate_pr_closure(
    closure: dict[str, Any],
    *,
    image_receipt: dict[str, Any],
    image_receipt_path: Path,
    blockers: list[str],
) -> tuple[dict[str, str] | None, dict[str, Any]]:
    if closure.get("production_ready") is not False:
        add_blocker(blockers, "CLOSURE_ASSERTED_PRODUCTION_READY")
    if closure.get("certified") is not False:
        add_blocker(blockers, "CLOSURE_ASSERTED_CERTIFIED")
    if closure.get("independently_verified") is not False:
        add_blocker(blockers, "CLOSURE_ASSERTED_INDEPENDENT_VERIFICATION")

    image_binding = closure.get("image_receipt") or {}
    if image_binding.get("sha256") != sha256_file(image_receipt_path):
        add_blocker(blockers, "CLOSURE_IMAGE_RECEIPT_SHA256_MISMATCH")
    if image_binding.get("source_commit") != image_receipt.get("source_commit"):
        add_blocker(blockers, "CLOSURE_SOURCE_COMMIT_MISMATCH")
    if image_binding.get("immutable_reference") != image_receipt.get(
        "immutable_reference"
    ):
        add_blocker(blockers, "CLOSURE_IMAGE_REFERENCE_MISMATCH")

    before = image_receipt.get("external_boundaries") or {}
    after = closure.get("external_boundaries") or {}
    normalized_after: dict[str, str] | None = None
    try:
        normalized_after = validate_observation_transition(
            before, after, boundary="SCM_DRAFT_PULL_REQUEST"
        )
    except ReleaseStateFailure:
        add_blocker(blockers, "CLOSURE_EXTERNAL_BOUNDARY_TRANSITION_INVALID")

    observation = closure.get("scm_draft_pull_request") or {}
    observed_digest = observation.get("observation_sha256")
    digest_subject = dict(observation)
    digest_subject.pop("observation_sha256", None)
    if observed_digest != sha256_bytes(canonical_json(digest_subject)):
        add_blocker(blockers, "SCM_OBSERVATION_SHA256_MISMATCH")
    if observation.get("state") != "open" or observation.get("draft") is not True:
        add_blocker(blockers, "SCM_DRAFT_PR_NOT_OPEN")
    if observation.get("head_sha") != image_receipt.get("source_commit"):
        add_blocker(blockers, "SCM_DRAFT_PR_HEAD_MISMATCH")

    external_evidence = closure.get("external_evidence") or {}
    scm_evidence = external_evidence.get("SCM_DRAFT_PULL_REQUEST") or {}
    if scm_evidence.get("state") != EXECUTED_AWAITING_VERIFICATION:
        add_blocker(blockers, "SCM_EXECUTION_EVIDENCE_STATE_INVALID")
    if scm_evidence.get("observation_sha256") != observed_digest:
        add_blocker(blockers, "SCM_EXECUTION_EVIDENCE_DIGEST_MISMATCH")
    if scm_evidence.get("source_commit") != image_receipt.get("source_commit"):
        add_blocker(blockers, "SCM_EXECUTION_EVIDENCE_SOURCE_MISMATCH")
    if scm_evidence.get("immutable_reference") != image_receipt.get(
        "immutable_reference"
    ):
        add_blocker(blockers, "SCM_EXECUTION_EVIDENCE_IMAGE_MISMATCH")
    return normalized_after, external_evidence


def evaluate_release_gate(
    image_receipt: dict[str, Any],
    *,
    image_receipt_path: Path,
    closure: dict[str, Any] | None = None,
    closure_path: Path | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    evidence_root = image_receipt_path.resolve().parent
    source_commit = str(image_receipt.get("source_commit", ""))
    immutable_reference = str(image_receipt.get("immutable_reference", ""))

    if image_receipt.get("production_ready") is not False:
        add_blocker(blockers, "IMAGE_RECEIPT_ASSERTED_PRODUCTION_READY")
    if image_receipt.get("certified") is not False:
        add_blocker(blockers, "IMAGE_RECEIPT_ASSERTED_CERTIFIED")
    if not COMMIT.fullmatch(source_commit):
        add_blocker(blockers, "SOURCE_COMMIT_INVALID")
    if image_receipt.get("source_worktree_clean") is not True:
        add_blocker(blockers, "SOURCE_WORKTREE_NOT_CLEAN")
    if image_receipt.get("source_worktree_clean_before") is not True:
        add_blocker(blockers, "SOURCE_WORKTREE_NOT_CLEAN_BEFORE_BUILD")
    if image_receipt.get("source_worktree_clean_after") is not True:
        add_blocker(blockers, "SOURCE_WORKTREE_NOT_CLEAN_AFTER_BUILD")
    if not IMMUTABLE_REFERENCE.fullmatch(immutable_reference):
        add_blocker(blockers, "IMMUTABLE_IMAGE_REFERENCE_INVALID")
    else:
        repository = immutable_reference.split("@", 1)[0]
        if is_local_registry(repository):
            add_blocker(blockers, "EXTERNAL_REGISTRY_NOT_CONFIGURED")

    if (image_receipt.get("image_contract") or {}).get("status") != "PASSED":
        add_blocker(blockers, "IMAGE_CONTRACT_NOT_PASSED")
    smoke = image_receipt.get("container_smoke") or {}
    if smoke.get("status") != "PASSED":
        add_blocker(blockers, "CONTAINER_SMOKE_NOT_PASSED")
    smoke_result = evidence_root / "container-smoke-result.json"
    if not smoke_result.is_file():
        add_blocker(blockers, "CONTAINER_SMOKE_EVIDENCE_MISSING")
    elif smoke.get("result_sha256") != sha256_file(smoke_result):
        add_blocker(blockers, "CONTAINER_SMOKE_EVIDENCE_SHA256_MISMATCH")

    runtime_environment = image_receipt.get("runtime_environment") or {}
    runtime_binding = {
        "path": runtime_environment.get("path"),
        "sha256": runtime_environment.get("sha256"),
        "byte_count": None,
    }
    runtime_path = resolve_evidence_path(runtime_binding["path"], evidence_root)
    if runtime_path is None or not runtime_path.is_file():
        add_blocker(blockers, "RUNNER_IMAGE_ENVIRONMENT_MISSING")
    else:
        runtime_binding["byte_count"] = runtime_path.stat().st_size
        verify_file_binding(
            runtime_binding,
            root=evidence_root,
            prefix="RUNNER_IMAGE_ENVIRONMENT",
            blockers=blockers,
        )
        expected_assignment = (
            f"ELMOS_RUNNER_IMAGE_MODERNIZATION_PROOF={immutable_reference}\n"
        )
        if runtime_path.read_text(encoding="utf-8") != expected_assignment:
            add_blocker(blockers, "RUNNER_IMAGE_ENVIRONMENT_VALUE_MISMATCH")
        if runtime_path.stat().st_mode & 0o777 != 0o600:
            add_blocker(blockers, "RUNNER_IMAGE_ENVIRONMENT_MODE_INVALID")

    validate_scan(
        image_receipt.get("vulnerability_scan") or {},
        evidence_root=evidence_root,
        blockers=blockers,
    )

    try:
        effective_boundaries = validate_external_boundaries(
            image_receipt.get("external_boundaries") or {}
        )
    except ReleaseStateFailure:
        add_blocker(blockers, "IMAGE_EXTERNAL_BOUNDARIES_INVALID")
        effective_boundaries = {boundary: "INVALID" for boundary in EXTERNAL_BOUNDARIES}

    external_evidence: dict[str, Any] = {}
    if closure is not None:
        if closure_path is None:
            add_blocker(blockers, "CLOSURE_PATH_MISSING")
        transitioned, external_evidence = validate_pr_closure(
            closure,
            image_receipt=image_receipt,
            image_receipt_path=image_receipt_path,
            blockers=blockers,
        )
        if transitioned is not None:
            effective_boundaries = transitioned

    for boundary, state in effective_boundaries.items():
        if state == INDEPENDENTLY_VERIFIED:
            validate_independent_evidence(
                boundary,
                external_evidence.get(boundary),
                source_commit=source_commit,
                immutable_reference=immutable_reference,
                evidence_root=(closure_path or image_receipt_path).resolve().parent,
                blockers=blockers,
            )
        else:
            add_blocker(blockers, f"{boundary}_{state}")

    decision = "READY_FOR_EXTERNAL_GATE" if not blockers else "BLOCKED"
    return {
        "schema_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "image_receipt": {
            "path": str(image_receipt_path.resolve()),
            "sha256": sha256_file(image_receipt_path),
            "source_commit": source_commit,
            "immutable_reference": immutable_reference,
        },
        "release_closure": (
            {
                "path": str(closure_path.resolve()),
                "sha256": sha256_file(closure_path),
            }
            if closure is not None and closure_path is not None
            else None
        ),
        "effective_external_boundaries": effective_boundaries,
        "blockers": sorted(blockers),
        "maximum_local_decision": "READY_FOR_EXTERNAL_GATE",
        "production_ready": False,
        "certified": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-receipt", required=True, type=Path)
    parser.add_argument("--release-closure", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image_receipt = json.loads(args.image_receipt.read_text(encoding="utf-8"))
    closure = (
        json.loads(args.release_closure.read_text(encoding="utf-8"))
        if args.release_closure
        else None
    )
    result = evaluate_release_gate(
        image_receipt,
        image_receipt_path=args.image_receipt,
        closure=closure,
        closure_path=args.release_closure,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["decision"] == "READY_FOR_EXTERNAL_GATE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
