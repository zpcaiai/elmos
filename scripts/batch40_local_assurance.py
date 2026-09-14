#!/usr/bin/env python3
"""Measure bounded, repository-owned Batch 40 assurance controls.

This checker deliberately stops at the local engineering boundary.  It audits
the exact CI workflow and the evidence graph already present in a Batch 40
pack.  It does not sign artifacts, invent an independent verifier, populate
holdout corpora, or change certification status.

Exit codes:
  0: every local control passed
  2: input or scope is invalid
  3: one or more local controls failed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml


PINNED_ACTION = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*@[0-9a-f]{40}$"
)
TIMESTAMP_FIELDS = ("queriedAt", "finishedAt", "generatedAt")


class AssuranceError(ValueError):
    """Raised when the requested assurance scope cannot be evaluated."""


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def git_revision(repo: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    revision = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise AssuranceError("repository HEAD is not an exact Git revision")
    return revision


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssuranceError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise AssuranceError(f"{label} must be a JSON object")
    return payload


def parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise AssuranceError(f"{label} has no evidence timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AssuranceError(f"{label} timestamp is not ISO-8601") from exc
    if parsed.tzinfo is None:
        raise AssuranceError(f"{label} timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def evidence_files(pack: Path, role: str) -> dict[str, Path]:
    directory = pack / "evidence" / role
    if not directory.is_dir():
        return {}
    return {
        path.name.removesuffix(".json"): path
        for path in directory.glob("*.json")
        if path.is_file()
    }


def workflow_controls(workflow_path: Path) -> list[dict[str, Any]]:
    try:
        raw = workflow_path.read_text(encoding="utf-8")
        workflow = yaml.safe_load(raw)
    except (OSError, yaml.YAMLError) as exc:
        raise AssuranceError(f"workflow is unreadable: {exc}") from exc
    if not isinstance(workflow, dict) or not isinstance(workflow.get("jobs"), dict):
        raise AssuranceError("workflow must contain a jobs mapping")

    controls: list[dict[str, Any]] = []

    def record(control_id: str, statement: str, passed: bool, details: list[str]) -> None:
        controls.append({
            "controlId": control_id,
            "statement": statement,
            "status": "PASS" if passed else "FAIL",
            "details": details,
        })

    permissions = workflow.get("permissions")
    permission_failures: list[str] = []
    if permissions != {"contents": "read"}:
        permission_failures.append("top-level permissions must be exactly contents: read")
    for job_id, job in workflow["jobs"].items():
        if isinstance(job, dict) and "permissions" in job:
            permission_failures.append(f"job {job_id} overrides workflow permissions")
    record(
        "B40-CI-LEAST-PRIVILEGE",
        "The CI workflow grants only repository-content read permission.",
        not permission_failures,
        permission_failures or ["top-level permissions are exactly contents: read"],
    )

    unpinned: list[str] = []
    checkout_persistence: list[str] = []
    soft_failures: list[str] = []
    action_count = checkout_count = 0
    timeout_failures: list[str] = []
    runner_failures: list[str] = []
    for job_id, job in workflow["jobs"].items():
        if not isinstance(job, dict):
            timeout_failures.append(f"job {job_id} is not a mapping")
            continue
        if job.get("continue-on-error") is True:
            soft_failures.append(f"job {job_id} sets continue-on-error")
        timeout = job.get("timeout-minutes")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            timeout_failures.append(f"job {job_id} has no positive timeout-minutes")
        runner = job.get("runs-on")
        if (
            not isinstance(runner, str)
            or not runner
            or "${{" in runner
            or runner.endswith("-latest")
        ):
            runner_failures.append(
                f"job {job_id} uses a missing, floating, or dynamic runner label: {runner}"
            )
        for index, step in enumerate(job.get("steps", [])):
            if isinstance(step, dict) and step.get("continue-on-error") is True:
                soft_failures.append(f"{job_id} step {index + 1} sets continue-on-error")
            if not isinstance(step, dict) or "uses" not in step:
                continue
            action_count += 1
            action = step["uses"]
            label = f"{job_id} step {index + 1}"
            if not isinstance(action, str):
                unpinned.append(f"{label} has a non-string uses value")
                continue
            normalized = action.split("#", 1)[0].strip()
            if normalized.startswith("./") or normalized.startswith("docker://"):
                continue
            if not PINNED_ACTION.fullmatch(normalized):
                unpinned.append(f"{label} is not pinned to a 40-character commit: {normalized}")
            if normalized.startswith("actions/checkout@"):
                checkout_count += 1
                with_values = step.get("with")
                persisted = with_values.get("persist-credentials") if isinstance(with_values, dict) else None
                if persisted is not False and str(persisted).lower() != "false":
                    checkout_persistence.append(f"{label} does not set persist-credentials: false")
    record(
        "B40-CI-ACTION-PINS",
        "Every external GitHub Action is pinned to an immutable commit.",
        action_count > 0 and not unpinned,
        unpinned or [f"{action_count} action references are immutable"],
    )
    record(
        "B40-CI-CHECKOUT-CREDENTIALS",
        "Every checkout removes the workflow token from local Git configuration.",
        checkout_count > 0 and not checkout_persistence,
        checkout_persistence or [f"{checkout_count} checkout steps disable credential persistence"],
    )
    record(
        "B40-CI-BOUNDED-JOBS",
        "Every CI job has an explicit positive timeout.",
        not timeout_failures,
        timeout_failures or [f"{len(workflow['jobs'])} jobs have explicit timeouts"],
    )
    record(
        "B40-CI-STATIC-RUNNERS",
        "Every CI job selects a literal, non-floating runner label.",
        not runner_failures,
        runner_failures or [f"{len(workflow['jobs'])} jobs use literal runner labels"],
    )
    record(
        "B40-CI-TRUSTED-EVENTS",
        "The CI workflow does not execute through pull_request_target.",
        not re.search(r"(?m)^\s*pull_request_target\s*:", raw),
        (["pull_request_target is configured"] if re.search(r"(?m)^\s*pull_request_target\s*:", raw)
         else ["pull_request_target is absent"]),
    )
    record(
        "B40-CI-NO-SOFT-FAILURES",
        "No job or step in the exact CI workflow weakens failure propagation with continue-on-error.",
        not soft_failures,
        soft_failures or ["no continue-on-error setting is enabled"],
    )
    return controls


def threat_model_control(path: Path) -> tuple[dict[str, Any], dict[str, Any], float]:
    model = load_object(path, "supply-chain threat model")
    expected = model.get("expectedThreatIds")
    threats = model.get("threats")
    failures: list[str] = []
    if not isinstance(expected, list) or not expected or len(expected) != len(set(expected)):
        failures.append("expectedThreatIds must be a non-empty unique list")
        expected = []
    if not isinstance(threats, list):
        failures.append("threats must be a list")
        threats = []
    records = {
        item.get("threatId"): item
        for item in threats
        if isinstance(item, dict) and isinstance(item.get("threatId"), str)
    }
    if len(records) != len(threats):
        failures.append("threat IDs must be present and unique")
    missing = sorted(set(expected) - set(records))
    unexpected = sorted(set(records) - set(expected))
    if missing:
        failures.append(f"missing expected threats: {missing}")
    if unexpected:
        failures.append(f"unexpected threats: {unexpected}")
    required = (
        "owner", "assets", "trustBoundaries", "controls", "evidenceRequirement", "residualRisk"
    )
    complete = 0
    for threat_id in expected:
        record = records.get(threat_id, {})
        invalid = []
        for field in required:
            value = record.get(field)
            if isinstance(value, list):
                valid = bool(value) and all(isinstance(item, str) and item for item in value)
            else:
                valid = isinstance(value, str) and bool(value)
            if not valid:
                invalid.append(field)
        if invalid:
            failures.append(f"{threat_id} has incomplete fields: {invalid}")
        else:
            complete += 1
    coverage = round(complete / len(expected), 4) if expected else 0.0
    control = {
        "controlId": "B40-THREAT-MODEL-COVERAGE",
        "statement": "Every expected supply-chain threat has assets, boundaries, controls, evidence requirements, ownership, and residual risk.",
        "status": "PASS" if not failures and coverage == 1.0 else "FAIL",
        "details": failures or [f"{complete}/{len(expected)} expected threats are complete"],
    }
    summary = {
        "id": model.get("id"),
        "owner": model.get("owner"),
        "scope": model.get("scope"),
        "expectedThreatCount": len(expected),
        "completeThreatCount": complete,
        "threats": threats,
    }
    return control, summary, coverage


def analyze(
    repo: Path,
    pack: Path,
    workflow_path: Path,
    threat_model_path: Path,
    max_age_days: int,
) -> dict[str, Any]:
    repo = repo.resolve()
    pack = pack.resolve()
    workflow_path = workflow_path.resolve()
    threat_model_path = threat_model_path.resolve()
    if max_age_days <= 0:
        raise AssuranceError("max-age-days must be positive")
    if (
        not repo.is_dir()
        or not pack.is_dir()
        or not workflow_path.is_file()
        or not threat_model_path.is_file()
    ):
        raise AssuranceError("repository, pack, workflow, and threat-model paths must exist")

    evidence = load_object(pack / "evidence.json", "evidence.json")
    claims = load_object(pack / "claims.json", "claims.json")
    declared_claims = evidence.get("claims")
    narratives = {
        item.get("claimId"): item
        for item in claims.get("claims", [])
        if isinstance(item, dict) and isinstance(item.get("claimId"), str)
    }
    if not isinstance(declared_claims, list) or not declared_claims:
        raise AssuranceError("evidence.json must declare at least one claim")
    # The checker cannot include its own output claim in the graph it measures:
    # doing so would create a recursive digest.  The exclusion is explicit and
    # the remaining canonical claim set is content-addressed below.
    declared_claims = [
        item for item in declared_claims
        if not isinstance(item, dict) or item.get("claimId") != "b40-local-assurance-controls"
    ]
    narratives = {
        key: value for key, value in narratives.items()
        if key != "b40-local-assurance-controls"
    }

    execution = evidence_files(pack, "execution")
    provenance = evidence_files(pack, "provenance")
    controls = workflow_controls(workflow_path)
    threat_control, threat_model, threat_coverage = threat_model_control(threat_model_path)
    controls.append(threat_control)
    resolved_refs = total_refs = 0
    claims_with_provenance = 0
    freshness: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    oldest = now - timedelta(days=max_age_days)
    trace_failures: list[str] = []
    authorization_failures: list[str] = []
    limitation_failures: list[str] = []
    provenance_failures: list[str] = []
    referenced_execution: set[str] = set()

    for claim in declared_claims:
        if not isinstance(claim, dict) or not isinstance(claim.get("claimId"), str):
            trace_failures.append("evidence.json contains a malformed claim")
            continue
        claim_id = claim["claimId"]
        evidence_refs = claim.get("evidenceRefs", [])
        provenance_refs = claim.get("provenanceRefs", [])
        if not isinstance(evidence_refs, list) or not evidence_refs:
            trace_failures.append(f"claim {claim_id} has no evidenceRefs")
            evidence_refs = []
        if not isinstance(provenance_refs, list) or not provenance_refs:
            provenance_failures.append(f"claim {claim_id} has no provenanceRefs")
            provenance_refs = []
        claim_provenance_resolved = bool(provenance_refs)
        for ref in evidence_refs:
            total_refs += 1
            if ref in execution:
                resolved_refs += 1
                referenced_execution.add(ref)
            else:
                trace_failures.append(f"claim {claim_id} evidence ref {ref} does not resolve")
        for ref in provenance_refs:
            total_refs += 1
            if ref in provenance:
                provenance_record = load_object(provenance[ref], f"provenance evidence {ref}")
                evidence_id = provenance_record.get("evidenceId")
                run_report = provenance_record.get("runReport")
                if evidence_id not in evidence_refs:
                    claim_provenance_resolved = False
                    provenance_failures.append(
                        f"claim {claim_id} provenance {ref} binds unexpected evidence {evidence_id}"
                    )
                elif not isinstance(run_report, dict):
                    claim_provenance_resolved = False
                    provenance_failures.append(f"provenance {ref} has no content-addressed runReport")
                else:
                    run_path = run_report.get("path")
                    expected_path = f"evidence/execution/{evidence_id}.json"
                    if run_path != expected_path or evidence_id not in execution:
                        claim_provenance_resolved = False
                        provenance_failures.append(
                            f"provenance {ref} runReport path does not bind {expected_path}"
                        )
                    elif run_report.get("sha256") != sha256_file(execution[evidence_id]):
                        claim_provenance_resolved = False
                        provenance_failures.append(
                            f"provenance {ref} digest does not match evidence {evidence_id}"
                        )
                    else:
                        resolved_refs += 1
            else:
                claim_provenance_resolved = False
                provenance_failures.append(f"claim {claim_id} provenance ref {ref} does not resolve")
        if claim_provenance_resolved:
            claims_with_provenance += 1
        if claim.get("externalOperationExecuted") and not claim.get("authorizationRefs"):
            authorization_failures.append(f"claim {claim_id} has an external operation without authorization")
        narrative = narratives.get(claim_id)
        if claim.get("status") == "PASS" and (
            not isinstance(narrative, dict) or not narrative.get("limitations")
        ):
            limitation_failures.append(f"passing claim {claim_id} has no explicit limitations")

    fresh_count = 0
    for ref in sorted(referenced_execution):
        payload = load_object(execution[ref], f"execution evidence {ref}")
        timestamp_field = next((field for field in TIMESTAMP_FIELDS if payload.get(field)), None)
        is_fresh = False
        timestamp = None
        problem = None
        if timestamp_field is None:
            problem = "no supported timestamp"
        else:
            try:
                parsed = parse_time(payload[timestamp_field], ref)
                timestamp = parsed.isoformat().replace("+00:00", "Z")
                is_fresh = oldest <= parsed <= now + timedelta(minutes=5)
                if not is_fresh:
                    problem = f"outside {max_age_days}-day freshness window"
            except AssuranceError as exc:
                problem = str(exc)
        fresh_count += int(is_fresh)
        freshness.append({
            "evidenceRef": ref,
            "timestamp": timestamp,
            "fresh": is_fresh,
            "problem": problem,
        })

    def append_control(control_id: str, statement: str, failures: list[str]) -> None:
        controls.append({
            "controlId": control_id,
            "statement": statement,
            "status": "PASS" if not failures else "FAIL",
            "details": failures or ["all in-scope records passed"],
        })

    append_control("B40-EVIDENCE-REFS", "Every claim evidence reference resolves.", trace_failures)
    append_control("B40-PROVENANCE-REFS", "Every claim has resolvable provenance.", provenance_failures)
    append_control("B40-EXTERNAL-AUTHORITY", "Every recorded external operation has authorization.", authorization_failures)
    append_control("B40-CLAIM-BOUNDARIES", "Every passing claim states its limitations.", limitation_failures)
    freshness_failures = [
        f"{item['evidenceRef']}: {item['problem']}" for item in freshness if not item["fresh"]
    ]
    if not freshness:
        freshness_failures.append("no referenced execution evidence was available")
    append_control("B40-EVIDENCE-FRESHNESS", "Referenced execution evidence is current.", freshness_failures)

    passed = sum(item["status"] == "PASS" for item in controls)
    metrics = {
        "auditEvidenceFreshnessRate": round(fresh_count / len(freshness), 4) if freshness else 0.0,
        "evidenceTraceCoverage": round(resolved_refs / total_refs, 4) if total_refs else 0.0,
        "provenanceCoverage": round(claims_with_provenance / len(declared_claims), 4),
        "secureSdlcControlCoverage": round(passed / len(controls), 4) if controls else 0.0,
        "threatModelCoverage": threat_coverage,
    }
    failed_controls = [item["controlId"] for item in controls if item["status"] != "PASS"]
    return {
        "check": "batch40-local-assurance",
        "batch": 40,
        "status": "PASS" if not failed_controls else "BLOCKED",
        "repositoryRevision": git_revision(repo),
        "startedAt": now.isoformat().replace("+00:00", "Z"),
        "finishedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "replayCommand": (
            "uv run --quiet --with pyyaml python scripts/batch40_local_assurance.py "
            "--pack mature-product-packs/batch40/elmos-platform-supply-chain"
        ),
        "toolDigest": sha256_file(Path(__file__)),
        "scope": {
            "workflow": workflow_path.relative_to(repo).as_posix(),
            "threatModel": threat_model_path.relative_to(repo).as_posix(),
            "pack": pack.relative_to(repo).as_posix(),
            "claimCount": len(declared_claims),
            "controlCount": len(controls),
            "freshnessWindowDays": max_age_days,
        },
        "inputs": {
            "workflowSha256": sha256_file(workflow_path),
            "threatModelSha256": sha256_file(threat_model_path),
            "evidenceClaimSetSha256": sha256_json(declared_claims),
            "claimNarrativeSetSha256": sha256_json(
                [narratives[key] for key in sorted(narratives)]
            ),
        },
        "metrics": metrics,
        "controls": controls,
        "threatModel": threat_model,
        "freshness": freshness,
        "failedControls": failed_controls,
        "limitations": [
            "The measurement covers the exact CI workflow and claims currently declared by this pack; it is not whole-product or whole-supply-chain coverage.",
            "Repository-local checks are self-attested and do not replace an independent assessor, independent corpus, accountable approval, or external signature.",
            "The action-pin audit proves immutable references in the workflow text; it does not independently attest GitHub runner images or action publisher provenance.",
            "Freshness means evidence timestamps fall inside the configured local window; it does not establish that an external verifier reproduced the evidence.",
            "The checker excludes its own claim from evidence-graph metrics to avoid a recursive digest; the exact non-recursive claim and narrative sets are content-addressed in inputs.",
        ],
        "externalOperationExecuted": False,
        "independentVerification": "NOT_RUN",
        "certificationStatus": "NOT_CERTIFIED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--workflow", type=Path, default=Path(".github/workflows/ci.yml"))
    parser.add_argument(
        "--threat-model",
        type=Path,
        default=Path("config/batch40-supply-chain-threat-model.json"),
    )
    parser.add_argument("--max-age-days", type=int, default=30)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        report = analyze(
            arguments.repo,
            arguments.pack,
            arguments.workflow,
            arguments.threat_model,
            arguments.max_age_days,
        )
    except AssuranceError as exc:
        report = {"check": "batch40-local-assurance", "batch": 40, "status": "INVALID", "error": str(exc)}
        code = 2
    else:
        code = 0 if report["status"] == "PASS" else 3
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload, encoding="utf-8")
        print(f"wrote {arguments.output}")
    else:
        print(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
