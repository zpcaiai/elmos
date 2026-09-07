#!/usr/bin/env python3
"""Collect an exact, fail-closed Batch 105-108 release status.

This command observes Git worktrees and GitHub checks, verifies the local V63
Testcontainers/Flyway report, and re-runs the conservative release gate.  A
local integration pass never promotes an external boundary or certification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from modernization_proof_release_state import (
    EXECUTED_AWAITING_VERIFICATION,
    EXTERNAL_BOUNDARIES,
    NOT_RUN,
)
from run_modernization_proof_release_gate import evaluate_release_gate, sha256_file


COMMIT = re.compile(r"^[0-9a-f]{40}$")
DIGEST_REFERENCE = re.compile(r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
EXPECTED_TEST_SUITE = "io.elmos.persistence.FlywayMigrationTest"
EXPECTED_POSTGRES_TAG = "postgres:17.5-alpine"
EXPECTED_MIGRATION = "V63__modernization_proof_execution_jobs.sql"
EXPECTED_TEST_SOURCE = "FlywayMigrationTest.java"
FAILED_CHECK_STATES = {
    "ACTION_REQUIRED",
    "CANCELLED",
    "ERROR",
    "FAILURE",
    "STARTUP_FAILURE",
    "STALE",
    "TIMED_OUT",
}
PENDING_CHECK_STATES = {
    "EXPECTED",
    "IN_PROGRESS",
    "PENDING",
    "QUEUED",
    "REQUESTED",
    "WAITING",
}
SUCCESS_CHECK_STATES = {"SUCCESS"}


class StatusCollectionFailure(RuntimeError):
    """Raised when a required observation cannot be made safely."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def run(command: Sequence[str], *, cwd: Path | None = None) -> str:
    process = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise StatusCollectionFailure(
            f"observation command failed: {command[0]} {command[1]}"
        )
    return process.stdout


def observe_worktree(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    head = run(["git", "rev-parse", "HEAD"], cwd=resolved).strip()
    if not COMMIT.fullmatch(head):
        raise StatusCollectionFailure(f"invalid Git HEAD for {resolved}")
    status = run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=resolved,
    )
    entries = status.splitlines()
    return {
        "path": str(resolved),
        "head_sha": head,
        "clean": not entries,
        "dirty_entry_count": len(entries),
        "status_sha256": sha256_bytes(status.encode("utf-8")),
    }


def normalize_check(check: dict[str, Any]) -> dict[str, Any]:
    if check.get("__typename") == "CheckRun":
        state = str(check.get("conclusion") or check.get("status") or "UNKNOWN")
        return {
            "kind": "CHECK_RUN",
            "name": check.get("name"),
            "workflow": check.get("workflowName"),
            "state": state.upper(),
            "url": check.get("detailsUrl"),
        }
    return {
        "kind": "STATUS_CONTEXT",
        "name": check.get("context"),
        "workflow": None,
        "state": str(check.get("state") or "UNKNOWN").upper(),
        "url": check.get("targetUrl"),
    }


def classify_check_rollup(checks: object) -> dict[str, Any]:
    normalized = (
        [normalize_check(check) for check in checks if isinstance(check, dict)]
        if isinstance(checks, list)
        else []
    )
    failures = [check for check in normalized if check["state"] in FAILED_CHECK_STATES]
    pending = [check for check in normalized if check["state"] in PENDING_CHECK_STATES]
    successes = [
        check for check in normalized if check["state"] in SUCCESS_CHECK_STATES
    ]
    other = [
        check
        for check in normalized
        if check not in failures and check not in pending and check not in successes
    ]
    if failures:
        status = "FAILED"
    elif pending or other:
        status = "IN_PROGRESS"
    elif normalized and len(successes) == len(normalized):
        status = "PASSED"
    else:
        status = "NOT_RUN"
    return {
        "status": status,
        "claimed_passed": status == "PASSED",
        "total_count": len(normalized),
        "failure_count": len(failures),
        "pending_count": len(pending),
        "success_count": len(successes),
        "other_non_success_count": len(other),
        "checks": normalized,
    }


def classify_pr_check_domains(checks: object) -> dict[str, Any]:
    """Separate GitHub Actions CI from provider/deployment status checks.

    GitHub's ``statusCheckRollup`` combines Actions workflow checks with legacy
    status contexts and third-party check runs.  Treating that combined list as
    ``remote_ci`` makes a Vercel preview failure look like a failed CI workflow.
    Keep both domains fail-closed, but report them without changing their
    meaning.
    """

    raw_checks = (
        [check for check in checks if isinstance(check, dict)]
        if isinstance(checks, list)
        else []
    )
    remote_ci_checks = [
        check
        for check in raw_checks
        if check.get("__typename") == "CheckRun"
        and isinstance(check.get("workflowName"), str)
        and bool(check["workflowName"].strip())
    ]
    external_checks = [
        check for check in raw_checks if check not in remote_ci_checks
    ]
    return {
        "remote_ci": classify_check_rollup(remote_ci_checks),
        "external_checks": classify_check_rollup(external_checks),
    }


def observe_pr(repository: str, number: int, expected_head: str) -> dict[str, Any]:
    document = json.loads(
        run(
            [
                "gh",
                "pr",
                "view",
                str(number),
                "--repo",
                repository,
                "--json",
                (
                    "number,state,isDraft,headRefName,headRefOid,baseRefName,"
                    "statusCheckRollup,url,author"
                ),
            ]
        )
    )
    expected_url = f"https://github.com/{repository}/pull/{number}"
    if (
        document.get("number") != number
        or document.get("url") != expected_url
        or document.get("state") != "OPEN"
        or document.get("isDraft") is not True
        or document.get("baseRefName") != "main"
        or document.get("headRefOid") != expected_head
    ):
        raise StatusCollectionFailure(
            "Draft PR observation does not match release subject"
        )
    check_domains = classify_pr_check_domains(document.get("statusCheckRollup"))
    observation = {
        "provider": "github",
        "repository": repository,
        "number": number,
        "url": expected_url,
        "state": "OPEN",
        "draft": True,
        "head_ref": document.get("headRefName"),
        "head_sha": expected_head,
        "base_ref": "main",
        "author": (document.get("author") or {}).get("login"),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        **check_domains,
    }
    observation["observation_sha256"] = sha256_bytes(canonical_json(observation))
    return observation


def inspect_postgres_image(tag: str) -> dict[str, Any]:
    if tag != EXPECTED_POSTGRES_TAG:
        raise StatusCollectionFailure(
            f"PostgreSQL image must be exactly {EXPECTED_POSTGRES_TAG}"
        )
    document = json.loads(run(["docker", "image", "inspect", tag]))
    if not isinstance(document, list) or len(document) != 1:
        raise StatusCollectionFailure("PostgreSQL image inspection was ambiguous")
    image = document[0]
    digests = [
        item
        for item in image.get("RepoDigests") or []
        if isinstance(item, str) and DIGEST_REFERENCE.fullmatch(item)
    ]
    postgres_digests = [item for item in digests if item.startswith("postgres@sha256:")]
    if len(postgres_digests) != 1:
        raise StatusCollectionFailure(
            "PostgreSQL image lacks one exact repository digest"
        )
    return {
        "tag": tag,
        "immutable_reference": postgres_digests[0],
        "local_image_id": image.get("Id"),
        "platform": f"{image.get('Os')}/{image.get('Architecture')}",
    }


def file_binding(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "path": str(resolved),
        "sha256": sha256_file(resolved),
        "byte_count": resolved.stat().st_size,
    }


def evaluate_v63_integration(
    *,
    xml_report: Path,
    text_report: Path,
    migration: Path,
    test_source: Path,
    postgres_image: dict[str, Any],
) -> dict[str, Any]:
    bindings = {
        "surefire_xml": file_binding(xml_report),
        "surefire_text": file_binding(text_report),
        "migration": file_binding(migration),
        "test_source": file_binding(test_source),
    }
    blockers: list[str] = []
    if migration.name != EXPECTED_MIGRATION:
        blockers.append("V63_MIGRATION_SUBJECT_INVALID")
    if test_source.name != EXPECTED_TEST_SOURCE:
        blockers.append("V63_TEST_SOURCE_SUBJECT_INVALID")
    try:
        suite = ET.parse(xml_report).getroot()
    except (ET.ParseError, OSError):
        suite = None
        blockers.append("V63_SUREFIRE_XML_INVALID")
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    if suite is not None:
        if suite.tag != "testsuite" or suite.get("name") != EXPECTED_TEST_SUITE:
            blockers.append("V63_TEST_SUITE_IDENTITY_INVALID")
        for key in counts:
            try:
                counts[key] = int(suite.get(key, "-1"))
            except ValueError:
                counts[key] = -1
                blockers.append(f"V63_{key.upper()}_COUNT_INVALID")
    text_summary = text_report.read_text(encoding="utf-8")
    xml_text = xml_report.read_text(encoding="utf-8")
    migration_text = migration.read_text(encoding="utf-8")
    test_source_text = test_source.read_text(encoding="utf-8")
    if "Tests run: 1, Failures: 0, Errors: 0, Skipped: 0" not in text_summary:
        blockers.append("V63_SUREFIRE_TEXT_SUMMARY_NOT_PASSED")
    if f"Creating container for image: {EXPECTED_POSTGRES_TAG}" not in xml_text:
        blockers.append("V63_POSTGRES_CONTAINER_EXECUTION_NOT_OBSERVED")
    flyway_match = re.search(
        r'Successfully applied ([0-9]+) migrations to schema "public", '
        r"now at version v([0-9]+)",
        xml_text,
    )
    if flyway_match is None:
        blockers.append("V63_FLYWAY_FULL_MIGRATION_NOT_OBSERVED")
        flyway_observation = None
    else:
        flyway_observation = {
            "migrations_applied": int(flyway_match.group(1)),
            "final_version": flyway_match.group(2),
        }
    if flyway_match is None or int(flyway_match.group(2)) < 63:
        blockers.append("V63_FLYWAY_VERSION_NOT_OBSERVED")
    if counts != {"tests": 1, "failures": 0, "errors": 0, "skipped": 0}:
        blockers.append("V63_SUREFIRE_COUNTS_NOT_PASSED")
    immutable_postgres = postgres_image.get("immutable_reference")
    if (
        postgres_image.get("tag") != EXPECTED_POSTGRES_TAG
        or not isinstance(immutable_postgres, str)
        or not immutable_postgres.startswith("postgres@sha256:")
    ):
        blockers.append("V63_POSTGRES_IMAGE_NOT_DIGEST_BOUND")
    if "MODERNIZATION_PROOF" not in migration_text:
        blockers.append("V63_MIGRATION_CONTRACT_NOT_OBSERVED")
    required_test_markers = {
        "flyway_schema_history",
        "version = '63'",
        "MODERNIZATION_PROOF",
        "UNKNOWN_PROOF_LINE",
        "worker:latest",
        "assertThrows",
    }
    if any(marker not in test_source_text for marker in required_test_markers):
        blockers.append("V63_TEST_ASSERTION_CONTRACT_INCOMPLETE")
    return {
        "status": "PASSED" if not blockers else "BLOCKED",
        "scope": "LOCAL_ENGINEERING_INTEGRATION",
        "test_suite": EXPECTED_TEST_SUITE,
        "migration_version": "63",
        "flyway_schema": "public",
        "flyway_observation": flyway_observation,
        "test_counts": counts,
        "postgres_image": postgres_image,
        "evidence": bindings,
        "blockers": sorted(set(blockers)),
        "production_equivalent": False,
        "promotes_external_boundary": False,
        "certifies_release": False,
    }


def copy_evidence(source: Path, destination: Path) -> Path:
    if source.resolve() == destination.resolve():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return destination


def collect_status(
    *,
    image_receipt_path: Path,
    closure_path: Path,
    primary_worktree: Path,
    source_worktree: Path,
    repository: str,
    pr_number: int,
    xml_report: Path,
    text_report: Path,
    migration: Path,
    test_source: Path,
    postgres_image: dict[str, Any],
) -> dict[str, Any]:
    image_receipt = json.loads(image_receipt_path.read_text(encoding="utf-8"))
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    gate = evaluate_release_gate(
        image_receipt,
        image_receipt_path=image_receipt_path,
        closure=closure,
        closure_path=closure_path,
    )
    source_commit = image_receipt.get("source_commit")
    primary = observe_worktree(primary_worktree)
    source = observe_worktree(source_worktree)
    blockers = list(gate["blockers"])
    if source["head_sha"] != source_commit:
        blockers.append("SOURCE_WORKTREE_HEAD_MISMATCH")
    if source["clean"] is not True:
        blockers.append("SOURCE_WORKTREE_NOT_CLEAN_AT_STATUS_COLLECTION")
    image_boundaries = image_receipt.get("external_boundaries") or {}
    if set(image_boundaries) != set(EXTERNAL_BOUNDARIES) or any(
        state != NOT_RUN for state in image_boundaries.values()
    ):
        blockers.append("IMAGE_BUILD_BOUNDARIES_NOT_ALL_NOT_RUN")
    effective_boundaries = gate["effective_external_boundaries"]
    if effective_boundaries.get("SCM_DRAFT_PULL_REQUEST") != (
        EXECUTED_AWAITING_VERIFICATION
    ):
        blockers.append("SCM_DRAFT_PULL_REQUEST_EXECUTION_NOT_RECORDED")
    for boundary in EXTERNAL_BOUNDARIES:
        if boundary != "SCM_DRAFT_PULL_REQUEST" and (
            effective_boundaries.get(boundary) != NOT_RUN
        ):
            blockers.append(f"{boundary}_UNEXPECTED_STATE")
    pr = observe_pr(repository, pr_number, str(source_commit))
    ci = pr["remote_ci"]
    if ci["failure_count"]:
        blockers.append("REMOTE_CI_FAILED")
    if ci["pending_count"] or ci["other_non_success_count"]:
        blockers.append("REMOTE_CI_IN_PROGRESS_OR_NON_SUCCESS")
    if ci["status"] != "PASSED":
        blockers.append("REMOTE_CI_NOT_PASSED")
    external_checks = pr["external_checks"]
    if external_checks["failure_count"]:
        blockers.append("EXTERNAL_CHECK_FAILED")
    if (
        external_checks["pending_count"]
        or external_checks["other_non_success_count"]
    ):
        blockers.append("EXTERNAL_CHECK_IN_PROGRESS_OR_NON_SUCCESS")
    v63 = evaluate_v63_integration(
        xml_report=xml_report,
        text_report=text_report,
        migration=migration,
        test_source=test_source,
        postgres_image=postgres_image,
    )
    if v63["status"] != "PASSED":
        blockers.extend(v63["blockers"] or ["V63_FLYWAY_NOT_PASSED"])
    blockers = sorted(set(blockers))
    return {
        **gate,
        "schema_version": 3,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "decision": "BLOCKED" if blockers else gate["decision"],
        "blockers": blockers,
        "boundary_state_layers": {
            "image_build_external_boundaries": image_boundaries,
            "release_closure_effective_boundaries": effective_boundaries,
        },
        "worktrees": {
            "primary": primary,
            "isolated_image_source": source,
            "image_source_was_clean_before_build": image_receipt.get(
                "source_worktree_clean_before"
            ),
            "image_source_was_clean_after_build": image_receipt.get(
                "source_worktree_clean_after"
            ),
        },
        "scm_draft_pull_request": pr,
        "local_engineering_evidence": {"v63_flyway_testcontainers": v63},
        "production_ready": False,
        "certified": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-receipt", required=True, type=Path)
    parser.add_argument("--release-closure", required=True, type=Path)
    parser.add_argument("--primary-worktree", required=True, type=Path)
    parser.add_argument("--source-worktree", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--v63-surefire-xml", required=True, type=Path)
    parser.add_argument("--v63-surefire-text", required=True, type=Path)
    parser.add_argument("--v63-migration", required=True, type=Path)
    parser.add_argument("--v63-test-source", required=True, type=Path)
    parser.add_argument("--postgres-image", default=EXPECTED_POSTGRES_TAG)
    parser.add_argument("--evidence-directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not REPOSITORY.fullmatch(args.repository) or args.pr <= 0:
        raise SystemExit("invalid GitHub repository or PR number")
    evidence_dir = args.evidence_directory.resolve()
    xml_report = copy_evidence(
        args.v63_surefire_xml,
        evidence_dir / "v63-flyway-testcontainers-surefire.xml",
    )
    text_report = copy_evidence(
        args.v63_surefire_text,
        evidence_dir / "v63-flyway-testcontainers-surefire.txt",
    )
    result = collect_status(
        image_receipt_path=args.image_receipt,
        closure_path=args.release_closure,
        primary_worktree=args.primary_worktree,
        source_worktree=args.source_worktree,
        repository=args.repository,
        pr_number=args.pr,
        xml_report=xml_report,
        text_report=text_report,
        migration=args.v63_migration,
        test_source=args.v63_test_source,
        postgres_image=inspect_postgres_image(args.postgres_image),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["decision"] == "READY_FOR_EXTERNAL_GATE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
