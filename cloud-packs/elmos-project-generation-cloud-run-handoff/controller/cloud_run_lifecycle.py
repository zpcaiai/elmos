#!/usr/bin/env python3
"""Offline Cloud Run lifecycle planner and fail-closed evidence validator.

This controller does not call Google Cloud. It emits exact argv plans for an
approved workflow and validates the resulting evidence envelope. A successful
local validation is capped at READY_FOR_EXTERNAL_GATE and never certifies a
deployment.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


PACK_KEY = "elmos-project-generation-cloud-run-handoff"
REGION = "asia-east1"
SCHEMA = "elmos.cloud-run-lifecycle-request.v1"
EVIDENCE_SCHEMA = "elmos.cloud-run-lifecycle-evidence.v1"
MAX_JSON_BYTES = 1024 * 1024
PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,61}[a-z0-9]$")
ACTOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,199}$")
DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
IMAGE_RE = re.compile(r"^[^\s@]+@sha256:[a-f0-9]{64}$")
ACTIONS = ("plan", "canary", "promote", "abort", "rollback", "destroy", "orphan", "drift", "cost")
MUTATING_ACTIONS = ("canary", "promote", "abort", "rollback", "destroy")
COST_CATEGORIES = {
    "compute",
    "requests",
    "storage",
    "data-transfer",
    "observability",
    "backup",
    "disaster-recovery",
    "support",
    "licenses",
}


class LifecycleError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise LifecycleError("JSON_FILE_UNSAFE")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise LifecycleError("JSON_FILE_TOO_LARGE")
    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise LifecycleError("JSON_OBJECT_REQUIRED")
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"INVALID_JSON_CONSTANT:{value}")


def _digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise LifecycleError(f"{label}_INVALID")
    return float(value)


def validate_request(request: dict[str, Any], *, now: dt.datetime | None = None) -> None:
    allowed = {
        "schema_version",
        "pack_key",
        "project_id",
        "region",
        "service_name",
        "release_id",
        "candidate_revision",
        "previous_revision",
        "image",
        "runtime_service_account",
        "config_digest",
        "cpu",
        "memory",
        "concurrency",
        "min_instances",
        "max_instances",
        "timeout_seconds",
        "budget",
        "owner",
        "ttl_expires_at",
    }
    if set(request) != allowed:
        raise LifecycleError("REQUEST_FIELDS_MISMATCH")
    if request.get("schema_version") != SCHEMA or request.get("pack_key") != PACK_KEY:
        raise LifecycleError("REQUEST_SCHEMA_OR_PACK_MISMATCH")
    project = request.get("project_id")
    service = request.get("service_name")
    release = request.get("release_id")
    candidate = request.get("candidate_revision")
    previous = request.get("previous_revision")
    if not isinstance(project, str) or PROJECT_RE.fullmatch(project) is None or project.startswith("replace-"):
        raise LifecycleError("PROJECT_ID_INVALID")
    if request.get("region") != REGION:
        raise LifecycleError("TARGET_REGION_MISMATCH")
    if not isinstance(service, str) or NAME_RE.fullmatch(service) is None:
        raise LifecycleError("SERVICE_NAME_INVALID")
    if not isinstance(release, str) or NAME_RE.fullmatch(release) is None or len(release) > 20:
        raise LifecycleError("RELEASE_ID_INVALID")
    if candidate != f"{service}-{release}" or not isinstance(candidate, str) or len(candidate) > 63:
        raise LifecycleError("CANDIDATE_REVISION_NOT_EXACT")
    if not isinstance(previous, str) or NAME_RE.fullmatch(previous) is None or previous == candidate:
        raise LifecycleError("PREVIOUS_REVISION_INVALID")
    image = request.get("image")
    prefix = f"{REGION}-docker.pkg.dev/{project}/"
    if (
        not isinstance(image, str)
        or IMAGE_RE.fullmatch(image) is None
        or not image.startswith(prefix)
        or image.endswith("@sha256:" + "0" * 64)
    ):
        raise LifecycleError("IMAGE_DIGEST_OR_REGISTRY_INVALID")
    account = request.get("runtime_service_account")
    if (
        not isinstance(account, str)
        or not account.endswith(f"@{project}.iam.gserviceaccount.com")
        or account.startswith("default@")
        or "-compute@developer.gserviceaccount.com" in account
    ):
        raise LifecycleError("RUNTIME_SERVICE_ACCOUNT_INVALID")
    config_digest = request.get("config_digest")
    if not isinstance(config_digest, str) or DIGEST_RE.fullmatch(config_digest) is None:
        raise LifecycleError("CONFIG_DIGEST_INVALID")
    if request.get("cpu") not in {"1", "2", "4", "8"}:
        raise LifecycleError("CPU_INVALID")
    memory = request.get("memory")
    if not isinstance(memory, str) or re.fullmatch(r"[1-9][0-9]*(Mi|Gi)", memory) is None:
        raise LifecycleError("MEMORY_INVALID")
    for field, lower, upper in (
        ("concurrency", 1, 1000),
        ("min_instances", 0, 100),
        ("max_instances", 1, 1000),
        ("timeout_seconds", 1, 3600),
    ):
        value = request.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
            raise LifecycleError(f"{field.upper()}_INVALID")
    if request["min_instances"] > request["max_instances"]:
        raise LifecycleError("INSTANCE_RANGE_INVALID")
    budget = request.get("budget")
    if not isinstance(budget, dict) or set(budget) != {"currency", "monthly_limit", "test_limit"}:
        raise LifecycleError("BUDGET_INVALID")
    if budget.get("currency") != "USD" or _number(budget.get("monthly_limit"), "MONTHLY_LIMIT") > 50:
        raise LifecycleError("BUDGET_INVALID")
    if _number(budget.get("test_limit"), "TEST_LIMIT") > budget["monthly_limit"]:
        raise LifecycleError("BUDGET_INVALID")
    owner = request.get("owner")
    if not isinstance(owner, str) or ACTOR_RE.fullmatch(owner) is None:
        raise LifecycleError("OWNER_INVALID")
    try:
        expiry = dt.datetime.fromisoformat(str(request["ttl_expires_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as error:
        raise LifecycleError("TTL_INVALID") from error
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        raise LifecycleError("TTL_TIMEZONE_REQUIRED")
    observed = now or dt.datetime.now(dt.timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise LifecycleError("TTL_CLOCK_INVALID")
    remaining = expiry.astimezone(dt.timezone.utc) - observed.astimezone(dt.timezone.utc)
    if remaining <= dt.timedelta(0):
        raise LifecycleError("TTL_EXPIRED")
    if remaining > dt.timedelta(hours=24):
        raise LifecycleError("TTL_EXCEEDS_24_HOURS")


def build_plan(request: dict[str, Any], *, now: dt.datetime | None = None) -> dict[str, Any]:
    validate_request(request, now=now)
    project = request["project_id"]
    region = request["region"]
    service = request["service_name"]
    candidate = request["candidate_revision"]
    previous = request["previous_revision"]
    common = [f"--project={project}", f"--region={region}", "--quiet", "--format=json"]
    canary = [
        "gcloud", "run", "deploy", service,
        f"--image={request['image']}",
        f"--service-account={request['runtime_service_account']}",
        "--ingress=internal",
        "--no-allow-unauthenticated",
        "--no-traffic",
        f"--tag=candidate-{request['release_id']}",
        f"--revision-suffix={request['release_id']}",
        f"--cpu={request['cpu']}",
        f"--memory={request['memory']}",
        f"--concurrency={request['concurrency']}",
        f"--min-instances={request['min_instances']}",
        f"--max-instances={request['max_instances']}",
        f"--timeout={request['timeout_seconds']}s",
        f"--set-annotations=elmos.dev/config-digest={request['config_digest']}",
        *common,
    ]
    commands = {
        "plan": [
            ["gcloud", "run", "services", "describe", service, *common],
            ["gcloud", "artifacts", "docker", "images", "describe", request["image"], f"--project={project}", "--format=json"],
        ],
        "canary": [canary],
        "promote": [[
            "gcloud", "run", "services", "update-traffic", service,
            f"--to-revisions={candidate}=100", *common,
        ]],
        "abort": [
            ["gcloud", "run", "services", "update-traffic", service, f"--remove-tags=candidate-{request['release_id']}", *common],
            ["gcloud", "run", "revisions", "delete", candidate, *common],
        ],
        "rollback": [[
            "gcloud", "run", "services", "update-traffic", service,
            f"--to-revisions={previous}=100", *common,
        ]],
        "destroy": [["gcloud", "run", "services", "delete", service, *common]],
        "orphan": [
            ["gcloud", "run", "revisions", "list", f"--service={service}", *common],
            ["gcloud", "artifacts", "docker", "images", "list", f"{region}-docker.pkg.dev/{project}", f"--project={project}", "--format=json"],
        ],
        "drift": [
            ["gcloud", "run", "services", "describe", service, *common],
            ["gcloud", "run", "services", "get-iam-policy", service, *common],
        ],
        "cost": [["gcloud", "billing", "projects", "describe", project, "--format=json"]],
    }
    return {
        "schema_version": "elmos.cloud-run-lifecycle-plan.v1",
        "status": "BLOCKED_PREREQUISITES",
        "pack_key": PACK_KEY,
        "request_digest": _digest(request),
        "exact_target": {"provider": "google-cloud", "api": "cloud-run-v2", "region": REGION},
        "commands": commands,
        "execution_authorized": False,
        "blocking_prerequisites": {
            "immutable_secret_version_refs": "NOT_IMPLEMENTED",
            "vercel_to_internal_cloud_run_network_bridge": "NOT_IMPLEMENTED",
        },
        "separate_authorization_required": list(MUTATING_ACTIONS),
        "unknown_provider_outcome": "BLOCKED_RECONCILIATION_REQUIRED",
        "external_execution_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


def _passed(actions: dict[str, Any], name: str) -> dict[str, Any]:
    value = actions.get(name)
    if not isinstance(value, dict) or value.get("status") != "PASSED":
        raise LifecycleError(f"{name.upper()}_EVIDENCE_NOT_PASSED")
    return value


def _authorization(action: dict[str, Any], name: str, executor: str) -> None:
    authorization = action.get("authorization")
    if not isinstance(authorization, dict):
        raise LifecycleError(f"{name.upper()}_AUTHORIZATION_MISSING")
    if authorization.get("action") != name or not isinstance(authorization.get("digest"), str):
        raise LifecycleError(f"{name.upper()}_AUTHORIZATION_SCOPE_INVALID")
    if DIGEST_RE.fullmatch(authorization["digest"]) is None:
        raise LifecycleError(f"{name.upper()}_AUTHORIZATION_SCOPE_INVALID")
    approver = authorization.get("approver")
    if not isinstance(approver, str) or ACTOR_RE.fullmatch(approver) is None or approver == executor:
        raise LifecycleError(f"{name.upper()}_AUTHORIZATION_SEPARATION_INVALID")


def validate_evidence(
    request: dict[str, Any],
    evidence: dict[str, Any],
    *,
    allow_synthetic_contract_test: bool = False,
    now: dt.datetime | None = None,
) -> str:
    validate_request(request, now=now)
    if evidence.get("schema_version") != EVIDENCE_SCHEMA or evidence.get("pack_key") != PACK_KEY:
        raise LifecycleError("EVIDENCE_SCHEMA_OR_PACK_MISMATCH")
    if evidence.get("request_digest") != _digest(request):
        raise LifecycleError("EVIDENCE_REQUEST_DIGEST_MISMATCH")
    synthetic = evidence.get("synthetic") is True
    if (
        not synthetic
        or evidence.get("evidence_class") != "LOCAL_CONTRACT_TEST"
        or evidence.get("external_execution") != "NOT_RUN"
    ):
        raise LifecycleError("EXTERNAL_EVIDENCE_REQUIRES_BATCH33_GATE")
    if not allow_synthetic_contract_test:
        raise LifecycleError("LOCAL_CONTRACT_TEST_FLAG_REQUIRED")
    executor = evidence.get("executor")
    verifier = evidence.get("independent_verifier")
    if (
        not isinstance(executor, str)
        or ACTOR_RE.fullmatch(executor) is None
        or not isinstance(verifier, str)
        or ACTOR_RE.fullmatch(verifier) is None
        or executor == verifier
    ):
        raise LifecycleError("INDEPENDENT_VERIFIER_REQUIRED")
    if evidence.get("certification") != "NOT_CERTIFIED":
        raise LifecycleError("CONTROLLER_CANNOT_CERTIFY")

    actions = evidence.get("actions")
    if not isinstance(actions, dict) or set(actions) != set(ACTIONS):
        raise LifecycleError("ACTION_EVIDENCE_SET_INCOMPLETE")
    records = {name: _passed(actions, name) for name in ACTIONS}
    for name in MUTATING_ACTIONS:
        _authorization(records[name], name, executor)

    if records["plan"].get("no_unapproved_replacement_or_deletion") is not True:
        raise LifecycleError("PLAN_DESTRUCTIVE_CHANGE_UNRESOLVED")
    canary = records["canary"]
    if (
        canary.get("revision") != request["candidate_revision"]
        or canary.get("image") != request["image"]
        or canary.get("traffic_percent") != 0
        or canary.get("private_ingress") is not True
        or canary.get("authenticated_health") != "PASSED"
    ):
        raise LifecycleError("CANARY_CONTRACT_FAILED")
    promote = records["promote"]
    if (
        promote.get("revision") != request["candidate_revision"]
        or promote.get("traffic_percent") != 100
        or promote.get("private_health") != "PASSED"
    ):
        raise LifecycleError("PROMOTION_CONTRACT_FAILED")
    abort = records["abort"]
    if (
        abort.get("traffic_percent") != 0
        or abort.get("previous_revision_traffic_unchanged") is not True
        or abort.get("candidate_disposition") not in {"DELETED", "RETAINED_BY_APPROVED_POLICY"}
    ):
        raise LifecycleError("ABORT_CONTRACT_FAILED")
    rollback = records["rollback"]
    if (
        rollback.get("revision") != request["previous_revision"]
        or rollback.get("traffic_percent") != 100
        or rollback.get("private_health") != "PASSED"
    ):
        raise LifecycleError("ROLLBACK_CONTRACT_FAILED")
    if records["destroy"].get("service_absent") is not True or records["destroy"].get("owned_inventory_bound") is not True:
        raise LifecycleError("DESTROY_CONTRACT_FAILED")
    orphan = records["orphan"]
    if any(orphan.get(name) != 0 for name in ("unknown_resources", "orphaned_resources", "billable_orphans")):
        raise LifecycleError("ORPHAN_OR_UNKNOWN_RESOURCE_DETECTED")
    drift = records["drift"]
    if (
        drift.get("config_digest") != request["config_digest"]
        or any(drift.get(name) != 0 for name in ("unknown_drift", "protected_replacements", "protected_deletions"))
    ):
        raise LifecycleError("DRIFT_CONTRACT_FAILED")
    cost = records["cost"]
    budget = request["budget"]
    if cost.get("currency") != budget["currency"]:
        raise LifecycleError("COST_CURRENCY_MISMATCH")
    if _number(cost.get("monthly_forecast"), "MONTHLY_FORECAST") > budget["monthly_limit"]:
        raise LifecycleError("MONTHLY_BUDGET_EXCEEDED")
    if _number(cost.get("test_spend"), "TEST_SPEND") > budget["test_limit"]:
        raise LifecycleError("TEST_BUDGET_EXCEEDED")
    categories = cost.get("included_categories")
    if not isinstance(categories, list) or not COST_CATEGORIES.issubset(set(categories)):
        raise LifecycleError("COST_CATEGORIES_INCOMPLETE")

    artifacts = evidence.get("artifacts")
    required_roles = {
        "provider-plan",
        "canary-describe",
        "canary-health",
        "promotion-traffic",
        "abort-drill",
        "rollback-drill",
        "destroy-observation",
        "orphan-inventory",
        "drift-inventory",
        "cost-observation",
    }
    if not isinstance(artifacts, list):
        raise LifecycleError("EVIDENCE_ARTIFACTS_REQUIRED")
    roles: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {"role", "sha256", "byte_size"}:
            raise LifecycleError("EVIDENCE_ARTIFACT_INVALID")
        role = artifact.get("role")
        if not isinstance(role, str) or role in roles:
            raise LifecycleError("EVIDENCE_ARTIFACT_ROLE_INVALID")
        roles.add(role)
        artifact_digest = artifact.get("sha256")
        if not isinstance(artifact_digest, str) or DIGEST_RE.fullmatch(artifact_digest) is None:
            raise LifecycleError("EVIDENCE_ARTIFACT_DIGEST_INVALID")
        byte_size = artifact.get("byte_size")
        if isinstance(byte_size, bool) or not isinstance(byte_size, int) or byte_size < 1:
            raise LifecycleError("EVIDENCE_ARTIFACT_SIZE_INVALID")
    if not required_roles.issubset(roles):
        raise LifecycleError("EVIDENCE_ARTIFACT_ROLES_INCOMPLETE")
    return "LOCAL_CONTRACT_VALID"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "validate-evidence"))
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    try:
        request = _load(args.request)
        if args.action == "plan":
            output = build_plan(request)
        else:
            if args.evidence is None:
                raise LifecycleError("EVIDENCE_FILE_REQUIRED")
            decision = validate_evidence(request, _load(args.evidence))
            output = {
                "status": decision,
                "certification": "NOT_CERTIFIED",
                "certification_effect": "NONE_REQUIRES_BATCH33_GATE",
            }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    except (LifecycleError, OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({
            "status": "BLOCKED",
            "reason": str(error).split(":", 1)[0],
            "external_execution_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
