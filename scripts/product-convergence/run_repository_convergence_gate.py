#!/usr/bin/env python3
"""Conservative repository authority for the convergence readiness overlay."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "product-closure-convergence"))
from evidence_integrity import verify_file_descriptor, verify_independent_record  # noqa: E402


REQUIRED_CRITERIA = (
    "unified_core",
    "private_runner",
    "reference_engine",
    "reference_route",
    "validation_lab",
    "maintainability",
    "customer_handoff",
    "unit_economics",
)
EXPECTED_SKILL_IDS = [f"CONV-{number:03d}" for number in range(1, 33)]
FUZZY_VERSION = re.compile(r"(?:\bcurrent\b|\blatest\b|(?:^|[ .])x(?:$|[ .]))", re.IGNORECASE)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def descriptor_json(value: Any, evidence_root: Path, label: str, reasons: list[str]) -> dict[str, Any]:
    ok, reason = verify_file_descriptor(value, evidence_root, label)
    if not ok:
        reasons.append(reason)
        return {}
    try:
        path = (evidence_root / value["path"]).resolve()
        document = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        reasons.append(f"{label} must contain valid JSON: {exc}")
        return {}
    if not isinstance(document, dict):
        reasons.append(f"{label} JSON must be an object")
        return {}
    return document


def validate_repository_facts(bundle: Path, evidence_root: Path, reasons: list[str]) -> None:
    plan = load_json(bundle / "convergence-plan.json")
    if plan.get("status") not in {"approved", "executing", "completed"}:
        reasons.append("convergence plan must be approved before readiness review")
    if plan.get("p0_skills") != EXPECTED_SKILL_IDS:
        reasons.append("convergence plan must preserve all 32 ordered P0 Skills")
    owners = plan.get("owners")
    if not isinstance(owners, dict) or set(owners) != set(EXPECTED_SKILL_IDS) or any(
        not isinstance(value, str) or not value.strip() for value in owners.values()
    ):
        reasons.append("every P0 convergence Skill requires an explicit owner")
    if not isinstance(plan.get("milestones"), list) or not plan["milestones"]:
        reasons.append("at least one bounded convergence milestone is required")
    if not isinstance(plan.get("blocking_items"), list) or plan["blocking_items"]:
        reasons.append("convergence blocking items must be an empty list")

    capabilities = load_json(bundle / "capability-registry.json").get("capabilities")
    if not isinstance(capabilities, list):
        capabilities = []
    by_capability = {
        item.get("capability_id"): item for item in capabilities if isinstance(item, dict)
    }
    for criterion in REQUIRED_CRITERIA:
        capability = by_capability.get(criterion)
        if not isinstance(capability, dict) or capability.get("status") not in {"supported", "certified"}:
            reasons.append(f"required capability is not supported: {criterion}")
            continue
        evidence = capability.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            reasons.append(f"required capability has no evidence: {criterion}")
            continue
        for index, descriptor in enumerate(evidence):
            descriptor_json(descriptor, evidence_root, f"capability[{criterion}].evidence[{index}]", reasons)

    dependency_nodes = {
        node.get("id")
        for node in load_json(bundle / "dependency-graph.json").get("nodes", [])
        if isinstance(node, dict)
    }
    if not set(REQUIRED_CRITERIA).issubset(dependency_nodes):
        reasons.append("dependency graph does not cover all readiness capabilities")
    evidence_nodes = load_json(bundle / "evidence-graph.json").get("nodes")
    if not isinstance(evidence_nodes, list) or not evidence_nodes:
        reasons.append("evidence graph must contain evidence-bearing nodes")

    route = load_json(bundle / "reference-route-plan.json")
    if route.get("status") != "accepted":
        reasons.append("reference route must be accepted")
    versions = [
        *route.get("source", {}).get("language_versions", []),
        *route.get("source", {}).get("framework_versions", []),
        *route.get("target", {}).get("language_versions", []),
        *route.get("target", {}).get("framework_versions", []),
    ]
    if not versions or any(not isinstance(version, str) or FUZZY_VERSION.search(version) for version in versions):
        reasons.append("reference route versions must be exact and cannot use current/latest/x")
    route_evidence = route.get("evidence")
    if not isinstance(route_evidence, list) or not route_evidence:
        reasons.append("reference route requires bound execution evidence")
    else:
        for index, descriptor in enumerate(route_evidence):
            document = descriptor_json(descriptor, evidence_root, f"reference_route.evidence[{index}]", reasons)
            if document and (document.get("status") != "passed" or document.get("execution_mode") != "real"):
                reasons.append(f"reference_route.evidence[{index}] is not a passed real execution")

    corpora = load_json(bundle / "benchmark-corpus.json").get("corpora")
    classes = {item.get("class") for item in corpora or [] if isinstance(item, dict)}
    customer_tenants = {
        item.get("tenant_id")
        for item in corpora or []
        if isinstance(item, dict) and item.get("class") == "customer-private" and item.get("tenant_id")
    }
    if "internal-holdout" not in classes or len(customer_tenants) < 2:
        reasons.append("benchmark corpus requires an internal holdout and two isolated customer-private tenants")

    handoff = load_json(bundle / "handoff-package.json")
    exercises = handoff.get("exercises")
    if not isinstance(exercises, list) or not exercises or any(item.get("status") != "passed" for item in exercises):
        reasons.append("all customer handoff exercises must pass")
    approvals = handoff.get("customer_approvals")
    approval_orgs = {
        item.get("organization_id")
        for item in approvals or []
        if isinstance(item, dict) and item.get("accepted") is True and item.get("organization_id")
    }
    if len(approval_orgs) < 2:
        reasons.append("customer handoff requires two distinct accepted organizations")


def evaluate(bundle: Path, evidence_root: Path) -> dict[str, Any]:
    reasons: list[str] = []
    validator = Path(__file__).with_name("validate_convergence_bundle.py")
    validation = subprocess.run(
        [sys.executable, str(validator), str(bundle)],
        capture_output=True,
        text=True,
        check=False,
    )
    if validation.returncode != 0:
        reasons.append("convergence bundle structural validation failed")
    try:
        validate_repository_facts(bundle, evidence_root, reasons)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        reasons.append(f"repository convergence facts are invalid: {exc}")
    request = load_json(bundle / "readiness-gate.json")
    criteria = request.get("criteria")
    if request.get("status") != "passed":
        reasons.append("readiness request status is not passed")
    if not isinstance(criteria, dict) or any(criteria.get(name) is not True for name in REQUIRED_CRITERIA):
        reasons.append("all eight convergence criteria must pass")
    findings = request.get("zero_tolerance_findings")
    if not isinstance(findings, list) or findings:
        reasons.append("zero-tolerance findings must be an empty list")

    repository_evidence = request.get("repository_evidence")
    if not isinstance(repository_evidence, dict):
        reasons.append("repository_evidence is required")
        repository_evidence = {}
    artifact_manifest = descriptor_json(
        repository_evidence.get("artifact_manifest"), evidence_root, "artifact_manifest", reasons
    )
    if artifact_manifest and (
        not isinstance(artifact_manifest.get("source_commit"), str)
        or not isinstance(artifact_manifest.get("target_commit"), str)
        or not isinstance(artifact_manifest.get("artifacts"), list)
        or not artifact_manifest["artifacts"]
    ):
        reasons.append("artifact_manifest must bind source/target commits and non-empty artifacts")
    environment_manifest = descriptor_json(
        repository_evidence.get("environment_manifest"), evidence_root, "environment_manifest", reasons
    )
    if environment_manifest and (
        environment_manifest.get("execution_mode") not in {"real", "approved-equivalent"}
        or not isinstance(environment_manifest.get("environment_id"), str)
        or not isinstance(environment_manifest.get("tool_versions"), dict)
        or not environment_manifest["tool_versions"]
        or not isinstance(environment_manifest.get("authorization_ref"), str)
    ):
        reasons.append("environment_manifest must bind an authorized real environment and tool versions")

    criterion_evidence = request.get("criterion_evidence")
    if not isinstance(criterion_evidence, dict) or set(criterion_evidence) != set(REQUIRED_CRITERIA):
        reasons.append("criterion_evidence must bind all eight exact readiness criteria")
        criterion_evidence = {}
    for criterion in REQUIRED_CRITERIA:
        document = descriptor_json(
            criterion_evidence.get(criterion), evidence_root, f"criterion_evidence[{criterion}]", reasons
        )
        if document and (document.get("criterion") != criterion or document.get("status") != "passed"):
            reasons.append(f"criterion_evidence[{criterion}] content is not a matching passed result")
    artifact_manifest = repository_evidence.get("artifact_manifest")
    environment_manifest = repository_evidence.get("environment_manifest")
    if (
        not isinstance(artifact_manifest, dict)
        or request.get("artifact_sha256") != str(artifact_manifest.get("sha256", "")).removeprefix("sha256:")
    ):
        reasons.append("artifact_sha256 must exactly bind artifact_manifest.sha256")
    if (
        not isinstance(environment_manifest, dict)
        or request.get("environment_sha256") != str(environment_manifest.get("sha256", "")).removeprefix("sha256:")
    ):
        reasons.append("environment_sha256 must exactly bind environment_manifest.sha256")

    partners = request.get("design_partner_evidence")
    if not isinstance(partners, list):
        partners = []
        reasons.append("design_partner_evidence must be a list")
    partner_orgs: set[str] = set()
    for index, record in enumerate(partners):
        ok, reason = verify_independent_record(
            record,
            evidence_root,
            f"design_partner_evidence[{index}]",
            organization_required=True,
        )
        if not ok:
            reasons.append(reason)
        elif isinstance(record.get("organization_id"), str):
            partner_orgs.add(record["organization_id"])
    if len(partner_orgs) < 2:
        reasons.append("two distinct independently verified design-partner organizations are required")

    reviews = request.get("independent_review_evidence")
    if not isinstance(reviews, list):
        reviews = []
        reasons.append("independent_review_evidence must be a list")
    valid_reviewers: set[str] = set()
    partner_people = {
        str(record.get(field))
        for record in partners
        if isinstance(record, dict)
        for field in ("executor_id", "verifier_id")
        if record.get(field)
    }
    for index, record in enumerate(reviews):
        ok, reason = verify_independent_record(
            record,
            evidence_root,
            f"independent_review_evidence[{index}]",
            organization_required=False,
        )
        if not ok:
            reasons.append(reason)
        elif record.get("verifier_id") in partner_people:
            reasons.append(f"independent_review_evidence[{index}] reviewer is not independent of partner execution")
        else:
            valid_reviewers.add(str(record.get("verifier_id")))
    if not valid_reviewers:
        reasons.append("one independent review distinct from partner execution is required")

    handoff_approvals = load_json(bundle / "handoff-package.json").get("customer_approvals", [])
    handoff_orgs = {
        item.get("organization_id")
        for item in handoff_approvals
        if isinstance(item, dict) and item.get("accepted") is True
    }
    if partner_orgs and not partner_orgs.issubset(handoff_orgs):
        reasons.append("design-partner organizations must match accepted customer handoff organizations")

    decision = "BLOCKED" if reasons else "READY_FOR_EXTERNAL_GATE"
    return {
        "schema_version": "1.0",
        "decision": decision,
        "maximum_decision": "READY_FOR_EXTERNAL_GATE",
        "external_evidence": "NOT_RUN" if reasons else "BOUND_FOR_EXTERNAL_REVIEW",
        "certified": False,
        "production_certified": False,
        "approves_deployment": False,
        "approves_customer_acceptance": False,
        "design_partner_organizations": len(partner_orgs),
        "independent_reviewers": len(valid_reviewers),
        "reasons": sorted(set(reasons)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    evidence_root = args.evidence_root or args.bundle
    result = evaluate(args.bundle.resolve(), evidence_root.resolve())
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    raise SystemExit(0 if result["decision"] == "READY_FOR_EXTERNAL_GATE" else 2)


if __name__ == "__main__":
    main()
