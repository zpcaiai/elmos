"""Content-addressed artifacts, independent verification and release gates."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .errors import ContractError
from .models import (
    Status,
    bytes_digest,
    canonical_json,
    digest,
    require_mapping,
    utc_now,
)
from .storage import DurableStore


def content_bytes(content: Any) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    return canonical_json(content)


def create_artifact(payload: Mapping[str, Any], *, store: DurableStore | None = None, tenant_id: str = "local", run_id: str | None = None) -> dict[str, Any]:
    content = content_bytes(payload.get("content"))
    producer = require_mapping(payload.get("producer_step", {}), "producer_step")
    security_label = str(payload.get("security_label", "INTERNAL"))
    if security_label == "SECRET" or re.search(rb"(?:password|authorization|private[_-]?key)\s*[:=]", content, re.IGNORECASE):
        raise ContractError("SECRET_EXPOSURE", "secret-like material cannot be persisted as an artifact")
    artifact = {"artifact_id": str(__import__("uuid").uuid4()), "tenant_id": tenant_id, "kind": str(payload.get("kind", "evidence")), "content_hash": bytes_digest(content), "size_bytes": len(content), "media_type": str(payload.get("media_type", "application/json")), "producer": producer, "repo_snapshot_sha": payload.get("repo_snapshot"), "task_spec_version": payload.get("task_spec_version"), "created_at": utc_now()}
    if store is not None:
        persisted = store.put_artifact(tenant_id=tenant_id, content=content, kind=artifact["kind"], media_type=artifact["media_type"], run_id=run_id, metadata={"producer": producer, "security_label": security_label})
        artifact.update(persisted)
    evidence = {"evidence_id": str(__import__("uuid").uuid4()), "claim": f"artifact {artifact['content_hash']} is content-addressed", "evidence_type": "artifact-integrity", "source": {"artifact_id": artifact["artifact_id"], "content_hash": artifact["content_hash"], "byte_count": len(content)}, "confidence": 1.0, "captured_at": utc_now()}
    if store is not None:
        evidence = store.put_evidence(tenant_id=tenant_id, claim=evidence["claim"], evidence_type=evidence["evidence_type"], source=evidence["source"], run_id=run_id, confidence=1.0, snapshot_sha=payload.get("repo_snapshot"))
    # The record below attests that the bytes hash to the recorded address.  It
    # is not a binding: nothing ties this artifact to the inputs it was produced
    # from, so evidence minted against one snapshot is byte-identical in
    # structure to evidence minted against another and can be cited for either.
    # The kernel engine binds `inputDigests`; supply `repo_snapshot.inputDigests`
    # to route this Skill there.  An unqualified "verified": true in a field
    # called integrity_record is a claim a reader will take for provenance.
    integrity_record = {
        "algorithm": "SHA-256",
        "verified": bytes_digest(content) == artifact["content_hash"],
        "byte_count": len(content),
        "binding": "content-address-only",
        "input_digests_bound": False,
        "method_note": (
            "the content address was recomputed over the supplied bytes; the "
            "evidence is not bound to the input digests it was produced from, so "
            "it cannot show which snapshot it is evidence about"
        ),
    }
    return {
        "artifact": artifact,
        "evidence": evidence,
        "provenance_edge": {"from": producer, "to": artifact["content_hash"],
                            "relation": "produced"},
        "retention_decision": {"security_label": security_label, "retention": "policy-bound"},
        "integrity_record": integrity_record,
    }


def verification_mesh(change_set: Any, validation: Any, task_spec: Mapping[str, Any], snapshot: Mapping[str, Any], policies: Any) -> dict[str, Any]:
    validations = validation if isinstance(validation, list) else []
    findings: list[dict[str, Any]] = []
    for item in validations:
        row = require_mapping(item, "validation_dag[]")
        status = str(row.get("status", "NOT_RUN")).upper()
        if status in {"FAIL", "FAILED", "BLOCKED"}:
            severity = str(row.get("severity", "P1"))
            findings.append({"id": f"finding:{digest(row)[:20]}", "severity": severity, "status": "OPEN", "confidence": float(row.get("confidence", 1.0)), "description": str(row.get("description", "validation failed")), "evidence_ids": list(row.get("evidence_ids", [])), "reproducer": row.get("reproducer")})
    high = [finding for finding in findings if finding["severity"] in {"P0", "P1"}]
    high_verified = all(bool(item.get("independent_verification")) for item in high)
    gate = "PASS" if not high and all(str(item.get("status", "NOT_RUN")).upper() in {"PASS", "PASSED"} for item in validations) else "BLOCKED" if any(str(item.get("status", "NOT_RUN")).upper() == "NOT_RUN" for item in validations) else "FAIL"
    # A validation row in this input shape is a self-reported status.  It names
    # no verifier, so nothing here can check that the thing which checked the
    # change is independent of the thing that produced it - and there is no
    # second opinion to disagree with, so there is no dissent to preserve
    # either.  `high_severity_independent` reads as a measurement and is not
    # one: `independent_verification` is never set on a finding built here, so
    # the flag is False whenever a P0/P1 finding exists and vacuously True when
    # none does.  A PASS from this engine means "no row reported a failure",
    # which is a weaker fact than the field name suggests.
    honesty = {
        "independence_checked": False,
        "dissent_preserved": False,
        "verdict_replication": "UNREPLICATED",
    }
    declared = task_spec.get("acceptance_criteria", [])
    coverage = {
        "criteria": len(declared) if isinstance(declared, list) else 0,
        "validators": len(validations),
        "high_severity_independent": high_verified,
        "high_severity_independent_vacuous": not high,
        **honesty,
    }
    recommendation = {
        "status": gate if high_verified else "BLOCKED",
        "reason": "all required validators passed" if gate == "PASS" and high_verified
        else "high-severity findings require independent verification" if not high_verified
        else "validation incomplete",
        **honesty,
        "method_note": (
            "validation rows carry no verifier identity or independence class, so "
            "no verifier was checked against verifying its own output and no "
            "minority verdict was recorded; supply verdicts with verifiers and a "
            "quorum policy to route this Skill to the verification-mesh engine"
        ),
    }
    return {"verification_run": {"status": "COMPLETED", "validator_count": len(validations), "snapshot_sha": snapshot.get("sha256") or digest(snapshot)}, "findings": findings, "finding_validations": [{"finding_id": item["id"], "independent": bool(item.get("independent_verification")), "status": "VALIDATED" if item.get("independent_verification") else "PENDING"} for item in high], "coverage_report": coverage, "release_recommendation": recommendation}


def release_gate(payload: Mapping[str, Any]) -> dict[str, Any]:
    criteria = payload.get("acceptance_criteria", [])
    if isinstance(criteria, Mapping):
        criteria = [{"id": key, "status": value} for key, value in criteria.items()]
    validations = payload.get("validation_results", [])
    if isinstance(validations, Mapping):
        validations = [{"id": key, "status": value} for key, value in validations.items()]
    validation_by_id = {str(item.get("id", item.get("gate", index))): item for index, item in enumerate(validations) if isinstance(item, Mapping)}
    gate_results = []
    for index, criterion in enumerate(criteria if isinstance(criteria, list) else []):
        item = criterion if isinstance(criterion, Mapping) else {"id": str(criterion)}
        gate_id = str(item.get("id", index))
        result = validation_by_id.get(gate_id, item)
        status = str(result.get("status", "NOT_RUN")).upper()
        gate_results.append({"id": gate_id, "status": "PASS" if status in {"PASS", "PASSED", "ACCEPTED"} else status, "evidence_ids": list(result.get("evidence_ids", []))})
    if not gate_results and isinstance(validations, list):
        gate_results = [{"id": str(item.get("id", index)), "status": str(item.get("status", "NOT_RUN")).upper(), "evidence_ids": list(item.get("evidence_ids", []))} for index, item in enumerate(validations) if isinstance(item, Mapping)]
    open_findings = []
    for finding in payload.get("findings", []):
        if isinstance(finding, Mapping) and str(finding.get("status", "OPEN")).upper() == "OPEN":
            open_findings.append(finding)
    artifacts = payload.get("artifacts", [])
    artifact_valid = all(isinstance(item, Mapping) and item.get("content_hash") and item.get("integrity_verified", item.get("content_hash", "").startswith("sha256:")) for item in artifacts) if isinstance(artifacts, list) else False
    approvals = payload.get("approvals", [])
    approved = bool(approvals) and all(isinstance(item, Mapping) and str(item.get("status", "")).upper() in {"APPROVED", "PASS", "ACCEPTED"} for item in approvals)
    deployment = payload.get("deployment_results", {})
    deployment = require_mapping(deployment, "deployment_results") if isinstance(deployment, Mapping) else {}
    health = require_mapping(deployment.get("health", payload.get("health", {})), "deployment_results.health")
    rollback_ready = bool(deployment.get("rollback_ready", payload.get("rollback_ready", False)))
    all_pass = bool(gate_results) and all(item["status"] == "PASS" for item in gate_results)
    critical_open = any(str(item.get("severity", "P1")) in {"P0", "P1"} for item in open_findings)
    health_ok = all(health.get(name) is True for name in ("livez", "readyz", "metrics", "version"))
    missing: list[str] = []
    if not all_pass:
        missing.append("all-mandatory-gates-pass")
    if critical_open:
        missing.append("no-open-P0-P1")
    if not rollback_ready:
        missing.append("rollback-ready")
    if not health_ok:
        missing.append("deployment-health")
    if not artifact_valid:
        missing.append("artifact-integrity")
    if not approved:
        missing.append("independent-approval")
    deployment_evidence = deployment.get("deployment_evidence")
    if not isinstance(deployment_evidence, list) or not deployment_evidence:
        missing.append("deployment-evidence")
    # This Skill consumes caller-supplied summaries and therefore cannot issue
    # P05. Only CertificationEngine can bind current signed evidence, persisted
    # customer acceptance and T00-T08 case identities to the candidate digest.
    missing.append("trusted-certification-engine-required")
    if any(item["status"] in {"FAIL", "FAILED", "REJECTED"} for item in gate_results) or critical_open:
        decision = Status.REJECTED.value
    else:
        decision = Status.BLOCKED.value
    # A gate that never produced a verdict is neither a pass nor a failure, and
    # `reasons` alone flattens the two into "all-mandatory-gates-pass": a reader
    # cannot tell "two gates failed" from "two gates never ran", which are
    # different incidents with different next actions.  Artifact integrity is the
    # sharper case: `artifact_valid` is `all()` over the supplied artifacts, so an
    # empty list satisfies it vacuously and "artifact-integrity" is then absent
    # from `reasons` because nothing was checked, not because anything passed.
    observed = {"PASS", "FAIL", "FAILED", "REJECTED"}
    unobserved_gates = [row["id"] for row in gate_results if row["status"] not in observed]
    acceptance = {
        "decision": decision,
        "independent": True,
        "decided_at": utc_now(),
        "reasons": missing,
        "completion_claim_ignored_for_acceptance": True,
        "unobserved_gates": unobserved_gates,
        "gate_statuses": {row["id"]: row["status"] for row in gate_results},
        "artifact_integrity_checked": bool(artifacts) if isinstance(artifacts, list) else False,
        "method_note": (
            "a gate listed in unobserved_gates (NOT_RUN, SKIPPED, or any other "
            "non-verdict) blocks acceptance but is not a failure; "
            "artifact_integrity_checked is false when no artifacts were supplied, "
            "in which case the artifact-integrity requirement is absent from "
            "reasons because nothing was checked, not because it was satisfied"
        ),
    }
    ready_for_external_gate = set(missing) == {"trusted-certification-engine-required"}
    return {"acceptance_decision": acceptance, "gate_results": gate_results, "release_bundle": {"status": "READY_FOR_EXTERNAL_GATE" if ready_for_external_gate else "NOT_READY", "artifact_hashes": [item.get("content_hash") for item in artifacts if isinstance(item, Mapping)]}, "rollback_bundle": {"status": "READY" if rollback_ready else "NOT_READY", "required": True}, "deployment_complete_attestation": {"status": decision, "attested": False, "gate": "P05_DEPLOYMENT_COMPLETE_NOT_ISSUED"}}


def security_assurance(change: Mapping[str, Any], diff: Any, index: Mapping[str, Any], policy: Mapping[str, Any], deployment_artifact: Any) -> dict[str, Any]:
    text = str(diff if diff is not None else change)
    findings: list[dict[str, Any]] = []
    if re.search(r"(?i)(api[_-]?key|password|secret|private[_-]?key)\s*[:=]\s*['\"]?[^\s'\"]+", text):
        findings.append({"id": "security:secret-exposure", "severity": "P0", "status": "OPEN", "description": "secret-like material detected in change input"})
    if re.search(r"(?i)ignore (?:all|previous) instructions|disable (?:security|policy)|exfiltrate", text):
        findings.append({"id": "security:prompt-injection", "severity": "P1", "status": "OPEN", "description": "repository text contains prompt-injection markers"})
    layers = policy.get("required_layers", ["rules", "sast", "sca", "sbom"]) if isinstance(policy, Mapping) else ["rules", "sast", "sca", "sbom"]
    layer_results = {str(layer): "PASS" if isinstance(deployment_artifact, Mapping) and deployment_artifact.get(str(layer)) in {True, "PASS", "PASSED"} else "NOT_RUN" for layer in layers}
    gate = "FAIL" if findings else "BLOCKED" if any(value == "NOT_RUN" for value in layer_results.values()) else "PASS"
    return {"security_findings": findings, "threat_model_delta": {"new_surfaces": ["untrusted-repository-text"], "index_partial": bool(index.get("partial"))}, "security_gate": {"status": gate, "layers": layer_results, "critical_open": bool(findings)}, "sbom_references": list(deployment_artifact.get("sbom_references", [])) if isinstance(deployment_artifact, Mapping) else [], "waiver": {"status": "NOT_APPLICABLE" if not findings else "REQUIRED", "expires_at": None}}
