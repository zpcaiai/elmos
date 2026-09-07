#!/usr/bin/env python3
"""Resolve, plan, and evidence-evaluate Precision Migration B01-B44 Skills.

Repository content is data, never an executable command source.  Approved
adapters are dispatched separately by :mod:`scripts.precision_migration.adapters`.
This module verifies content bytes, signed authorization/proof/approval records,
exact Skill maturity, and the conservative per-request decision.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from scripts.precision_migration.trust import (
    TrustStore,
    canonical_digest,
    configured_roots,
    request_binding_digest,
    verify_content_reference,
)


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "docs" / "precision-migration-b01-44" / "installed-manifest.json"
ALLOWED_MODES = {"assess", "transform", "validate", "repair", "certify"}
EVIDENCE_STATES = {"PASS", "FAIL", "NOT_RUN", "INCONCLUSIVE"}
STATUS_VALUES = {
    "PROVED",
    "VERIFIED",
    "CONDITIONALLY_VERIFIED",
    "REQUIRES_ADAPTER",
    "REQUIRES_HUMAN_REVIEW",
    "UNSUPPORTED",
    "FAILED",
}
MATURITY_VALUES = {
    "SPEC_ONLY",
    "INSTALLED",
    "ADAPTER_DECLARED",
    "ADAPTER_CONTRACT_PASSED",
    "LOCAL_EXECUTED",
    "HOLDOUT_PASSED",
    "EXTERNAL_VERIFIED",
    "CERTIFIED",
}
LOSS_CLASSES = {
    "LOSSLESS",
    "NORMALIZED",
    "APPROXIMATE",
    "REQUIRES_ADAPTER",
    "UNVERIFIED",
    "UNSUPPORTED",
}
REQUIRED_BY_MODE = {
    "assess": {"input-provenance", "assessment-schema"},
    "transform": {
        "input-provenance",
        "source-build",
        "target-build",
        "source-target-differential",
        "artifact-provenance",
    },
    "validate": {
        "input-provenance",
        "source-build",
        "target-build",
        "negative-tests",
        "source-target-differential",
        "artifact-provenance",
    },
    "repair": {
        "input-provenance",
        "failure-reproduction",
        "target-build",
        "regression-tests",
        "differential-replay",
        "artifact-provenance",
    },
    "certify": {
        "input-provenance",
        "source-build",
        "target-build",
        "negative-tests",
        "source-target-differential",
        "artifact-provenance",
        "independent-review",
    },
}
def valid_digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"installed manifest is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("namespace") != "precision-migration-b01-44":
        raise ValueError("installed manifest namespace is invalid")
    if payload.get("runtime_skill_count") != 632:
        raise ValueError("installed manifest must contain exactly 632 Runtime Skills")
    return payload


@dataclass(frozen=True)
class Registry:
    manifest: dict[str, Any]
    by_runtime_name: dict[str, dict[str, Any]]
    by_source_name: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, path: Path = MANIFEST_PATH) -> "Registry":
        manifest = load_manifest(path)
        records = manifest.get("skills")
        if not isinstance(records, list):
            raise ValueError("installed manifest Skills must be an array")
        by_runtime: dict[str, dict[str, Any]] = {}
        by_source: dict[str, dict[str, Any]] = {}
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("installed manifest contains a non-object Skill")
            name = record.get("name")
            source_name = record.get("source_name")
            if not isinstance(name, str) or not isinstance(source_name, str):
                raise ValueError("installed Skill identity is invalid")
            if name in by_runtime or source_name in by_source:
                raise ValueError(f"duplicate installed Skill identity: {name}")
            by_runtime[name] = record
            by_source[source_name] = record
        if len(by_runtime) != 632:
            raise ValueError("registry identity count is invalid")
        return cls(manifest, by_runtime, by_source)

    def resolve(self, name: str) -> dict[str, Any]:
        record = self.by_runtime_name.get(name) or self.by_source_name.get(name)
        if record is None:
            raise KeyError(f"unknown Precision Migration Skill: {name}")
        return record


def batch_plan(registry: Registry, record: dict[str, Any]) -> dict[str, Any]:
    target_batch = record.get("batch")
    mandatory_groups: list[tuple[str, list[int]]] = [
        ("assessment", [2, 3, 4]),
        ("semantic-recovery", [5, 6, 7, 8, 9, 10]),
        ("test-asset-baseline", [28, 29]),
    ]
    if isinstance(target_batch, int):
        mandatory_groups.append(("selected-capability", [target_batch]))
    mandatory_groups.extend(
        [
            ("differential-and-repair", [30, 31, 32]),
            ("evidence-gate", [41]),
            ("shadow-canary-cutover", [42]),
        ]
    )
    seen: set[int] = set()
    stages: list[dict[str, Any]] = []
    for group, batches in mandatory_groups:
        entries = []
        for batch in batches:
            if batch in seen:
                continue
            seen.add(batch)
            orchestrator = next(
                item
                for item in registry.manifest["skills"]
                if item.get("batch") == batch and item.get("kind") == "batch-orchestrator"
            )
            child_count = registry.manifest["batch_counts"][f"B{batch:02d}"]
            entries.append(
                {
                    "batch": batch,
                    "orchestrator": orchestrator["name"],
                    "child_skill_count": child_count,
                    "external_evidence_status": "NOT_RUN",
                }
            )
        if entries:
            stages.append({"stage": group, "batches": entries})
    plan = {
        "schema_version": 1,
        "namespace": registry.manifest["namespace"],
        "requested_skill": record["name"],
        "source_skill": record["source_name"],
        "requested_batch": target_batch,
        "stages": stages,
        "policies": {
            "unresolved_differences": "block",
            "allow_test_weakening": False,
            "require_provenance": True,
            "production_operation_authorized": False,
        },
        "maximum_local_decision": "READY_FOR_EXTERNAL_GATE",
        "production_certification": "NOT_CERTIFIED",
    }
    plan["plan_digest"] = canonical_digest(plan)
    return plan


def unresolved(code: str, message: str, *, blocking: bool = True) -> dict[str, Any]:
    return {"code": code, "message": message, "blocking": blocking}


def validate_assets(
    inputs: Any,
    roots: tuple[Path, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    if not isinstance(inputs, dict):
        return [unresolved("INVALID_INPUT", "inputs must be an object")], verified
    assets = inputs.get("assets")
    if not isinstance(assets, list) or not assets:
        issues.append(
            unresolved(
                "MISSING_INPUT_PROVENANCE",
                "inputs.assets must contain at least one digest-bound source asset",
            )
        )
        return issues, verified
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            issues.append(unresolved("INVALID_INPUT_ASSET", f"inputs.assets[{index}] must be an object"))
            continue
        if not isinstance(asset.get("uri"), str) or not asset["uri"]:
            issues.append(unresolved("INVALID_INPUT_ASSET", f"inputs.assets[{index}].uri is required"))
        if not valid_digest(asset.get("digest")):
            issues.append(
                unresolved(
                    "INVALID_INPUT_DIGEST",
                    f"inputs.assets[{index}].digest must be sha256:<64 lowercase hex>",
                )
            )
        if not isinstance(asset.get("sensitivity"), str) or not asset["sensitivity"]:
            issues.append(
                unresolved(
                    "MISSING_INPUT_CLASSIFICATION",
                    f"inputs.assets[{index}].sensitivity is required",
                )
            )
        try:
            observed = verify_content_reference(asset, roots)
        except (OSError, ValueError) as exc:
            issues.append(
                unresolved(
                    "INPUT_CONTENT_UNVERIFIED",
                    f"inputs.assets[{index}] content verification failed: {exc}",
                )
            )
        else:
            verified.append(
                {
                    **observed,
                    "sensitivity": asset.get("sensitivity"),
                    "version": asset.get("version"),
                }
            )
    return issues, verified


def validate_evidence(
    evidence: Any,
    *,
    request: dict[str, Any],
    roots: tuple[Path, ...],
    trust_store: TrustStore | None,
    now: datetime | None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    by_kind: dict[str, dict[str, Any]] = {}
    verified_records: list[dict[str, Any]] = []
    if not isinstance(evidence, list):
        return [unresolved("INVALID_EVIDENCE", "evidence must be an array")], by_kind, verified_records
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            issues.append(unresolved("INVALID_EVIDENCE", f"evidence[{index}] must be an object"))
            continue
        kind = item.get("kind")
        state = item.get("state")
        if not isinstance(kind, str) or not kind:
            issues.append(unresolved("INVALID_EVIDENCE_KIND", f"evidence[{index}].kind is required"))
            continue
        if kind in by_kind:
            issues.append(unresolved("DUPLICATE_EVIDENCE_KIND", f"duplicate evidence kind: {kind}"))
            continue
        if state not in EVIDENCE_STATES:
            issues.append(unresolved("INVALID_EVIDENCE_STATE", f"evidence {kind} has invalid state"))
            continue
        by_kind[kind] = item
        if state == "PASS":
            for field in ("artifact_uri", "executor", "verifier", "replay_command", "environment_digest"):
                if not isinstance(item.get(field), str) or not item[field]:
                    issues.append(unresolved("INCOMPLETE_PASS_EVIDENCE", f"PASS evidence {kind} lacks {field}"))
            if not valid_digest(item.get("digest")):
                issues.append(unresolved("INVALID_EVIDENCE_DIGEST", f"PASS evidence {kind} lacks a valid digest"))
            if not isinstance(item.get("size_bytes"), int) or isinstance(item.get("size_bytes"), bool):
                issues.append(unresolved("INVALID_EVIDENCE_SIZE", f"PASS evidence {kind} lacks size_bytes"))
            if (
                isinstance(item.get("executor"), str)
                and item.get("executor") == item.get("verifier")
            ):
                issues.append(unresolved("SELF_VERIFICATION", f"PASS evidence {kind} is self-verified"))
            try:
                observed = verify_content_reference(item, roots)
            except (OSError, ValueError) as exc:
                issues.append(
                    unresolved(
                        "EVIDENCE_CONTENT_UNVERIFIED",
                        f"PASS evidence {kind} content verification failed: {exc}",
                    )
                )
            else:
                authorization = item.get("authorization")
                if trust_store is None:
                    issues.append(
                        unresolved(
                            "TRUST_STORE_REQUIRED",
                            f"PASS evidence {kind} requires a configured trust store",
                        )
                    )
                else:
                    try:
                        verified_authorization = trust_store.verify_envelope(
                            authorization,
                            required_role="evidence-authorizer",
                            bindings={
                                "record_type": "EVIDENCE_AUTHORIZATION",
                                "request_id": request.get("request_id"),
                                "skill": request.get("skill"),
                                "evidence_kind": kind,
                                "artifact_digest": item.get("digest"),
                                "executor": item.get("executor"),
                                "verifier": item.get("verifier"),
                                "request_digest": request_binding_digest(request),
                            },
                            now=now,
                        )
                    except (OSError, ValueError, subprocess.SubprocessError) as exc:
                        issues.append(
                            unresolved(
                                "EVIDENCE_AUTHORIZATION_INVALID",
                                f"PASS evidence {kind} authorization failed: {exc}",
                            )
                        )
                    else:
                        verified_records.append(
                            {
                                "kind": kind,
                                "state": "PASS",
                                **observed,
                                "executor": item.get("executor"),
                                "verifier": item.get("verifier"),
                                "replay_command": item.get("replay_command"),
                                "environment_digest": item.get("environment_digest"),
                                "authorization": verified_authorization,
                            }
                        )
        if state == "FAIL":
            issues.append(unresolved("VALIDATION_FAILED", f"evidence gate failed: {kind}"))
        elif state in {"NOT_RUN", "INCONCLUSIVE"}:
            issues.append(unresolved("MISSING_EVIDENCE", f"evidence {kind} is {state}"))
    return issues, by_kind, verified_records


def validate_losses(losses: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    if losses is None:
        return issues, normalized
    if not isinstance(losses, list):
        return [unresolved("INVALID_SEMANTIC_LOSS", "semantic_losses must be an array")], normalized
    for index, item in enumerate(losses):
        if not isinstance(item, dict):
            issues.append(unresolved("INVALID_SEMANTIC_LOSS", f"semantic_losses[{index}] must be an object"))
            continue
        classification = item.get("classification")
        if classification not in LOSS_CLASSES:
            issues.append(unresolved("INVALID_SEMANTIC_LOSS", f"semantic_losses[{index}] classification is invalid"))
            continue
        if not isinstance(item.get("scope"), str) or not isinstance(item.get("dimension"), str):
            issues.append(unresolved("INVALID_SEMANTIC_LOSS", f"semantic_losses[{index}] lacks scope or dimension"))
            continue
        normalized.append(item)
        if classification == "UNSUPPORTED":
            issues.append(unresolved("UNSUPPORTED_SEMANTICS", f"unsupported semantic scope: {item['scope']}"))
        elif classification == "REQUIRES_ADAPTER":
            issues.append(unresolved("ADAPTER_REQUIRED", f"semantic adapter required: {item['scope']}"))
        elif classification in {"APPROXIMATE", "UNVERIFIED"}:
            issues.append(unresolved("SEMANTIC_LOSS_UNVERIFIED", f"semantic loss is not verified: {item['scope']}"))
    return issues, normalized


def validate_approval(
    request: dict[str, Any],
    runtime_name: str,
    *,
    trust_store: TrustStore | None,
    now: datetime | None,
) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]]]:
    approvals = request.get("approvals")
    if not isinstance(approvals, list):
        return False, [], []
    issues: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    participants = {
        str(value)
        for item in request.get("evidence", [])
        if isinstance(item, dict)
        for value in (item.get("executor"), item.get("verifier"))
        if isinstance(value, str) and value
    }
    for approval in approvals:
        if not isinstance(approval, dict):
            issues.append(unresolved("APPROVAL_INVALID", "approval must be a signed envelope"))
            continue
        payload = approval.get("payload")
        if not isinstance(payload, dict):
            issues.append(unresolved("APPROVAL_INVALID", "approval payload is required"))
            continue
        scope = payload.get("scope")
        if scope not in {runtime_name, "precision-migration-b01-44"}:
            issues.append(unresolved("APPROVAL_SCOPE_INVALID", "approval scope does not cover this Skill"))
            continue
        approver = payload.get("approver")
        if not isinstance(approver, str) or not approver:
            issues.append(unresolved("APPROVAL_INVALID", "approval approver is required"))
            continue
        policy = request.get("policy") if isinstance(request.get("policy"), dict) else {}
        request_actor = policy.get("request_actor")
        if approver in participants or approver == request_actor:
            issues.append(
                unresolved(
                    "APPROVAL_SOD_VIOLATION",
                    "approver must be separate from requester, executor, and verifier",
                )
            )
            continue
        if trust_store is None:
            issues.append(unresolved("TRUST_STORE_REQUIRED", "signed approval requires a configured trust store"))
            continue
        try:
            record = trust_store.verify_envelope(
                approval,
                required_role="release-approver",
                bindings={
                    "record_type": "HUMAN_APPROVAL",
                    "request_id": request.get("request_id"),
                    "scope": scope,
                    "decision": "APPROVED",
                    "request_digest": request_binding_digest(request),
                },
                now=now,
            )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            issues.append(unresolved("APPROVAL_INVALID", f"approval verification failed: {exc}"))
            continue
        verified.append({**record, "scope": scope, "approver": approver})
    return bool(verified), issues, verified


def validate_machine_proof(
    request: dict[str, Any],
    evidence_by_kind: dict[str, dict[str, Any]],
    *,
    trust_store: TrustStore | None,
    now: datetime | None,
) -> tuple[bool, list[dict[str, Any]], dict[str, Any] | None]:
    if request.get("claimed_status") != "PROVED":
        return False, [], None
    proof = evidence_by_kind.get("machine-proof")
    if not proof or proof.get("state") != "PASS":
        return False, [unresolved("INVALID_PROOF_CLAIM", "PROVED requires PASS machine-proof evidence")], None
    envelope = proof.get("proof_record")
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, dict):
        return False, [unresolved("INVALID_PROOF_RECORD", "machine proof requires a signed proof_record")], None
    required_fields = {
        "solver": str,
        "solver_version": str,
        "theory": str,
        "options": dict,
        "bounds": dict,
        "assumptions_digest": str,
        "input_digest": str,
    }
    for field, expected_type in required_fields.items():
        value = payload.get(field)
        if not isinstance(value, expected_type) or (hasattr(value, "__len__") and len(value) == 0):
            return False, [unresolved("INVALID_PROOF_RECORD", f"machine proof payload lacks {field}")], None
    if not valid_digest(payload.get("assumptions_digest")) or not valid_digest(payload.get("input_digest")):
        return False, [unresolved("INVALID_PROOF_RECORD", "machine proof input and assumptions digests are invalid")], None
    if trust_store is None:
        return False, [unresolved("TRUST_STORE_REQUIRED", "machine proof requires a configured trust store")], None
    try:
        verified = trust_store.verify_envelope(
            envelope,
            required_role="proof-verifier",
            bindings={
                "record_type": "MACHINE_PROOF",
                "request_id": request.get("request_id"),
                "skill": request.get("skill"),
                "artifact_digest": proof.get("digest"),
                "request_digest": request_binding_digest(request),
                "result": "PROVED",
                "proof_scope": "bounded-core",
            },
            now=now,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return False, [unresolved("INVALID_PROOF_RECORD", f"machine proof verification failed: {exc}")], None
    return True, [], {**verified, "solver": payload["solver"], "solver_version": payload["solver_version"], "bounds": payload["bounds"]}


def requires_human_approval(request: dict[str, Any], record: dict[str, Any]) -> bool:
    policy = request.get("policy") if isinstance(request.get("policy"), dict) else {}
    risk = policy.get("risk_level", "medium")
    return risk in {"high", "critical"} or record.get("batch") in {42, 44}


def derive_status(
    request: dict[str, Any],
    record: dict[str, Any],
    issues: list[dict[str, Any]],
    evidence_by_kind: dict[str, dict[str, Any]],
    losses: list[dict[str, Any]],
    *,
    approval_ok: bool,
    proof_ok: bool,
) -> str:
    codes = {item["code"] for item in issues}
    fatal_codes = {
        "VALIDATION_FAILED",
        "UNAUTHORIZED_EVIDENCE",
        "SELF_VERIFICATION",
        "INCOMPLETE_PASS_EVIDENCE",
        "DUPLICATE_EVIDENCE_KIND",
        "TEST_WEAKENING_FORBIDDEN",
        "DIFFERENCE_POLICY_INVALID",
        "PROVENANCE_POLICY_INVALID",
        "EVIDENCE_CONTENT_UNVERIFIED",
        "EVIDENCE_AUTHORIZATION_INVALID",
        "INPUT_CONTENT_UNVERIFIED",
        "TRUST_STORE_REQUIRED",
        "APPROVAL_INVALID",
        "APPROVAL_SCOPE_INVALID",
        "APPROVAL_SOD_VIOLATION",
        "INVALID_PROOF_RECORD",
    }
    if codes & fatal_codes or any(code.startswith("INVALID_") for code in codes):
        return "FAILED"
    if "UNSUPPORTED_SEMANTICS" in codes:
        return "UNSUPPORTED"
    maturity = record.get("maturity", "SPEC_ONLY")
    if maturity not in MATURITY_VALUES:
        return "FAILED"
    if "ADAPTER_REQUIRED" in codes or maturity in {"SPEC_ONLY", "INSTALLED"}:
        return "REQUIRES_ADAPTER"
    if requires_human_approval(request, record) and not approval_ok:
        return "REQUIRES_HUMAN_REVIEW"
    claimed = request.get("claimed_status")
    if claimed is not None and claimed not in STATUS_VALUES:
        return "FAILED"
    if claimed == "PROVED":
        if not proof_ok:
            return "FAILED"
    blocking = [item for item in issues if item.get("blocking")]
    if blocking:
        return "CONDITIONALLY_VERIFIED"
    if any(item.get("classification") not in {"LOSSLESS", "NORMALIZED"} for item in losses):
        return "CONDITIONALLY_VERIFIED"
    return "PROVED" if claimed == "PROVED" else "VERIFIED"


def evaluate(
    request: dict[str, Any],
    registry: Registry | None = None,
    *,
    evidence_roots: Iterable[Path] | None = None,
    trust_store: TrustStore | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    registry = registry or Registry.load()
    roots = configured_roots(evidence_roots)
    if isinstance(trust_store, Path):
        trust_store = TrustStore.load(trust_store)
    issues: list[dict[str, Any]] = []
    skill = request.get("skill")
    if not isinstance(skill, str) or not skill:
        record = {
            "name": "unknown",
            "source_name": "unknown",
            "batch": None,
            "kind": "skill",
            "binding": {"adapter": "none", "binding_state": "PARTIAL"},
        }
        issues.append(unresolved("INVALID_SKILL", "skill is required"))
    else:
        try:
            record = registry.resolve(skill)
        except KeyError as exc:
            record = {
                "name": skill,
                "source_name": skill,
                "batch": None,
                "kind": "skill",
                "binding": {"adapter": "none", "binding_state": "PARTIAL"},
            }
            issues.append(unresolved("INVALID_SKILL", str(exc)))
    mode = request.get("mode")
    if mode not in ALLOWED_MODES:
        issues.append(unresolved("INVALID_MODE", f"mode must be one of {sorted(ALLOWED_MODES)}"))
        mode = "assess"
    policy = request.get("policy")
    if not isinstance(policy, dict):
        issues.append(unresolved("INVALID_POLICY", "policy must be an object"))
        policy = {}
    if policy.get("allow_test_weakening") is not False:
        issues.append(unresolved("TEST_WEAKENING_FORBIDDEN", "policy.allow_test_weakening must be false"))
    if policy.get("unresolved_differences") != "block":
        issues.append(unresolved("DIFFERENCE_POLICY_INVALID", "policy.unresolved_differences must be block"))
    if policy.get("require_provenance") is not True:
        issues.append(unresolved("PROVENANCE_POLICY_INVALID", "policy.require_provenance must be true"))
    asset_issues, verified_inputs = validate_assets(request.get("inputs"), roots)
    issues.extend(asset_issues)
    evidence_issues, evidence_by_kind, verified_evidence = validate_evidence(
        request.get("evidence"),
        request=request,
        roots=roots,
        trust_store=trust_store,
        now=now,
    )
    issues.extend(evidence_issues)
    for kind in sorted(REQUIRED_BY_MODE[str(mode)]):
        evidence = evidence_by_kind.get(kind)
        if evidence is None:
            issues.append(unresolved("MISSING_EVIDENCE", f"required evidence is missing: {kind}"))
        elif evidence.get("state") != "PASS":
            issues.append(unresolved("MISSING_EVIDENCE", f"required evidence did not pass: {kind}"))
    loss_issues, losses = validate_losses(request.get("semantic_losses"))
    issues.extend(loss_issues)
    approval_ok, approval_issues, verified_approvals = validate_approval(
        request,
        str(record["name"]),
        trust_store=trust_store,
        now=now,
    )
    issues.extend(approval_issues)
    proof_ok, proof_issues, verified_proof = validate_machine_proof(
        request,
        evidence_by_kind,
        trust_store=trust_store,
        now=now,
    )
    issues.extend(proof_issues)

    # Deterministically de-duplicate repeated observations without hiding any code.
    unique_issues: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in issues:
        key = (str(item["code"]), str(item["message"]))
        if key not in seen:
            unique_issues.append(item)
            seen.add(key)
    status = derive_status(
        request,
        record,
        unique_issues,
        evidence_by_kind,
        losses,
        approval_ok=approval_ok,
        proof_ok=proof_ok,
    )
    required = sorted(REQUIRED_BY_MODE[str(mode)])
    verified_kinds = {item["kind"] for item in verified_evidence}
    gate_rows = [
        {
            "name": kind,
            "required": True,
            "result": (
                "PASS"
                if kind in verified_kinds
                else evidence_by_kind[kind]["state"]
                if kind in evidence_by_kind and evidence_by_kind[kind]["state"] != "PASS"
                else "INCONCLUSIVE"
            ),
        }
        for kind in required
    ]
    gate_blocked = status not in {"VERIFIED", "PROVED"}
    release_gate = {
        "gates": gate_rows,
        "decision": "BLOCK" if gate_blocked else "SHADOW_ONLY",
        "unresolved": unique_issues,
        "approvals": verified_approvals,
        "maximum_local_decision": "SHADOW_ONLY",
        "production_operation_authorized": False,
    }
    result_without_digest = {
        "schema_version": 1,
        "request_id": request.get("request_id"),
        "namespace": registry.manifest["namespace"],
        "skill": record["name"],
        "source_skill": record["source_name"],
        "batch": record.get("batch"),
        "mode": mode,
        "status": status,
        "adapter": record.get("binding", {}).get("adapter"),
        "adapter_maturity": record.get("maturity", "SPEC_ONLY"),
        "artifacts": [
            {"kind": "skill-result", "path": "skill-result.json"},
            {"kind": "evidence-manifest", "path": "evidence-manifest.json"},
            {"kind": "semantic-loss-ledger", "path": "semantic-loss-ledger.json"},
            {"kind": "release-gate", "path": "release-gate.json"},
        ],
        "inputs": verified_inputs,
        "evidence": verified_evidence,
        "proof": verified_proof,
        "semantic_losses": losses,
        "unresolved": unique_issues,
        "next_actions": [
            item["message"] for item in unique_issues if item.get("blocking")
        ],
        "release_gate": release_gate,
        "external_evidence_status": (
            "COMPLETE_FOR_REQUEST" if not gate_blocked else "NOT_RUN_OR_INCOMPLETE"
        ),
        "production_certification": "NOT_CERTIFIED",
        "production_operation_authorized": False,
    }
    return {**result_without_digest, "result_digest": canonical_digest(result_without_digest)}


def write_bundle(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "skill-result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence_manifest = {
        "skill": result["skill"],
        "version": "1.0.0",
        "status": result["status"],
        "inputs": result["inputs"],
        "toolchain": {
            "adapter": result["adapter"],
            "adapter_maturity": result["adapter_maturity"],
        },
        "models": [],
        "findings": result["unresolved"],
        "changes": [],
        "tests": [item for item in result["evidence"] if "test" in str(item.get("kind", ""))],
        "proofs": [item for item in result["evidence"] if item.get("kind") == "machine-proof"],
        "unresolved": result["unresolved"],
        "approvals": result["release_gate"]["approvals"],
    }
    (output_dir / "evidence-manifest.json").write_text(
        json.dumps(evidence_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "semantic-loss-ledger.json").write_text(
        json.dumps({"items": result["semantic_losses"]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "release-gate.json").write_text(
        json.dumps(result["release_gate"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--batch", type=int)
    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument("--skill", required=True)
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--skill", required=True)
    run_parser = subparsers.add_parser("evaluate")
    run_parser.add_argument("--request", type=Path, required=True)
    run_parser.add_argument("--output-dir", type=Path)
    run_parser.add_argument(
        "--evidence-root",
        type=Path,
        action="append",
        default=[],
        help="approved local root for input and evidence content (repeatable)",
    )
    run_parser.add_argument(
        "--trust-store",
        type=Path,
        help="immutable Ed25519 trust store for evidence, proof, and approval records",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        registry = Registry.load()
        if args.command == "list":
            records = registry.manifest["skills"]
            if args.batch is not None:
                records = [item for item in records if item.get("batch") == args.batch]
            emit(
                {
                    "count": len(records),
                    "skills": [
                        {
                            "name": item["name"],
                            "source_name": item["source_name"],
                            "batch": item.get("batch"),
                            "kind": item["kind"],
                        }
                        for item in records
                    ],
                }
            )
            return 0
        record = registry.resolve(args.skill)
        if args.command == "resolve":
            emit(record)
            return 0
        if args.command == "plan":
            emit(batch_plan(registry, record))
            return 0
        request = json.loads(args.request.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise ValueError("request root must be an object")
        result = evaluate(
            request,
            registry,
            evidence_roots=args.evidence_root,
            trust_store=args.trust_store,
        )
        if args.output_dir:
            write_bundle(result, args.output_dir)
        emit(result)
        return 0 if result["status"] in {"PROVED", "VERIFIED", "CONDITIONALLY_VERIFIED", "REQUIRES_ADAPTER", "REQUIRES_HUMAN_REVIEW", "UNSUPPORTED"} else 2
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
