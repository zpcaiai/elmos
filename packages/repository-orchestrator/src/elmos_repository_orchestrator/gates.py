"""Authoritative local package and repository-readiness gates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .catalog import SKILL_NAMES, SKILL_SPECS
from .contracts import ContractError, Status, integer_value, parse_timestamp, require_mapping, require_string, require_string_sequence
from .evidence import EvidenceRecord


REQUIRED_LOCAL_CHECKS = (
    "handler_registry",
    "runtime_contracts",
    "unit_tests",
    "cli_smoke",
)


def _verify_check_report(path: Path, *, check_id: str, evidence: EvidenceRecord) -> None:
    if evidence.byte_count > 1_048_576:
        raise ContractError("check_report_too_large", "gate check report exceeds 1 MiB")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("invalid_check_report", "gate evidence must be a UTF-8 JSON check report") from exc
    report = require_mapping(raw, "check_report")
    allowed = {
        "schema_version",
        "check_id",
        "outcome",
        "exit_code",
        "observed_at",
        "command_argv",
        "artifact_digest",
        "authorization_id",
        "executor_id",
        "verifier_id",
        "evidence_class",
        "synthetic",
    }
    unknown = sorted(set(report) - allowed)
    if unknown:
        raise ContractError("unknown_check_report_field", "unknown check report field(s): " + ", ".join(unknown))
    if report.get("schema_version") != "elmos.repository-orchestrator.local-check.v1":
        raise ContractError("check_report_schema_mismatch", "unexpected local check report schema")
    if report.get("check_id") != check_id:
        raise ContractError("check_report_id_mismatch", "check report does not match requested check")
    if report.get("outcome") != "pass" or integer_value(report.get("exit_code"), "check_report.exit_code") != 0:
        raise ContractError("check_report_not_passing", "check report does not record a zero-exit pass")
    parse_timestamp(report.get("observed_at"), "check_report.observed_at")
    require_string_sequence(report.get("command_argv"), "check_report.command_argv", allow_empty=False)
    artifact_digest = require_string(report.get("artifact_digest"), "check_report.artifact_digest")
    if not artifact_digest.startswith("sha256:") or len(artifact_digest) != 71:
        raise ContractError("invalid_artifact_digest", "check report artifact digest is invalid")
    if report.get("authorization_id") != evidence.authorization_id:
        raise ContractError("authorization_binding_mismatch", "check report authorization is not evidence-bound")
    if report.get("executor_id") != evidence.executor_id or report.get("verifier_id") != evidence.verifier_id:
        raise ContractError("actor_binding_mismatch", "check report actors are not evidence-bound")
    if report.get("evidence_class") != evidence.evidence_class:
        raise ContractError("evidence_class_mismatch", "check report evidence class is not metadata-bound")
    if report.get("synthetic") is not False:
        raise ContractError("synthetic_check_forbidden", "synthetic evidence cannot pass the authoritative gate")


@dataclass(frozen=True, slots=True)
class GateDecision:
    status: Status
    certification: Status
    reasons: tuple[str, ...]
    verified_checks: tuple[str, ...]
    handler_coverage: tuple[str, ...]
    required_capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status not in {Status.LOCAL_ENGINEERING_VALIDATED, Status.BLOCKED}:
            raise ContractError("invalid_gate_status", "authoritative package gate returns validated or blocked")
        if self.certification is not Status.NOT_CERTIFIED:
            raise ContractError("certification_forbidden", "local package gate never certifies")

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "certification": self.certification.value,
            "reasons": list(self.reasons),
            "verified_checks": list(self.verified_checks),
            "handler_coverage": list(self.handler_coverage),
            "required_capabilities": list(self.required_capabilities),
            "maximum_local_status": Status.LOCAL_ENGINEERING_VALIDATED.value,
            "certified": False,
        }


def validate_handler_registry(registry: Mapping[str, Any], handler_names: Iterable[str]) -> tuple[str, ...]:
    value = require_mapping(registry, "handler_registry")
    if value.get("schema_version") != "elmos.repository-orchestrator.handler-registry.v1":
        raise ContractError("registry_schema_mismatch", "unexpected handler registry schema_version")
    if value.get("runtime_module") != "elmos_repository_orchestrator.runtime" or value.get("runtime_callable") != "dispatch":
        raise ContractError("runtime_binding_mismatch", "handler registry must bind elmos_repository_orchestrator.runtime:dispatch")
    entries = value.get("skills")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes, bytearray)):
        raise ContractError("invalid_handler_registry", "handler registry skills must be an array")
    seen: dict[str, Mapping[str, Any]] = {}
    for raw in entries:
        entry = require_mapping(raw, "handler_registry.skills[]")
        name = require_string(entry.get("name"), "handler_registry.skills[].name")
        if name in seen:
            raise ContractError("duplicate_handler", f"duplicate handler registry Skill: {name}")
        seen[name] = entry
    if set(seen) != set(SKILL_NAMES):
        raise ContractError("handler_registry_coverage", "static handler registry must contain the exact 37 Skills")
    runtime_names = set(handler_names)
    if runtime_names != set(SKILL_NAMES):
        raise ContractError("dispatcher_coverage", "runtime dispatcher must contain the exact 37 Skills")
    for name in SKILL_NAMES:
        spec = SKILL_SPECS[name]
        entry = seen[name]
        if entry.get("handler") != spec.handler:
            raise ContractError("handler_binding_mismatch", f"handler mismatch for {name}")
        if entry.get("canonical_owner") != spec.canonical_owner:
            raise ContractError("owner_binding_mismatch", f"canonical owner mismatch for {name}")
        if entry.get("adapter_requirement") != spec.adapter_requirement:
            raise ContractError("adapter_binding_mismatch", f"adapter requirement mismatch for {name}")
    return tuple(name for name in SKILL_NAMES)


def _required_capabilities(payload: Mapping[str, Any], required_skills: Sequence[str]) -> tuple[str, ...]:
    claim_scope = payload.get("claim_scope", "local_contracts")
    if claim_scope not in {"local_contracts", "adapter_execution", "external_readiness"}:
        raise ContractError("invalid_claim_scope", "claim_scope must be local_contracts, adapter_execution, or external_readiness")
    explicit = require_string_sequence(payload.get("required_capabilities", []), "required_capabilities")
    allowed = {"repository", "provider", "runner", "worktree", "scm", "external"}
    if set(explicit) - allowed:
        raise ContractError("unknown_capability", "required_capabilities contains an unknown capability")
    required = set(explicit)
    if claim_scope in {"adapter_execution", "external_readiness"}:
        required.update(
            spec.adapter_requirement
            for name, spec in SKILL_SPECS.items()
            if name in required_skills and spec.adapter_requirement is not None
        )
    if claim_scope == "external_readiness":
        required.add("external")
    return tuple(sorted(required))


def run_package_gate(
    payload: Mapping[str, Any],
    *,
    evidence_root: Path,
    static_registry: Mapping[str, Any],
    handler_names: Iterable[str],
) -> GateDecision:
    value = require_mapping(payload, "gate_request")
    reasons: list[str] = []
    verified_checks: list[str] = []
    try:
        coverage = validate_handler_registry(static_registry, handler_names)
    except ContractError as exc:
        coverage = tuple(sorted(set(handler_names)))
        reasons.append(f"{exc.code}:{exc}")
    required_skills = require_string_sequence(value.get("required_skills", list(SKILL_NAMES)), "required_skills", allow_empty=False)
    unknown_skills = sorted(set(required_skills) - set(SKILL_NAMES))
    if unknown_skills:
        reasons.append("unknown_required_skills:" + ",".join(unknown_skills))
    full_coverage = value.get("require_full_coverage", True)
    if not isinstance(full_coverage, bool):
        raise ContractError("invalid_full_coverage", "require_full_coverage must be boolean")
    missing_required = sorted(set(SKILL_NAMES) - set(required_skills)) if full_coverage else []
    if missing_required:
        reasons.append("required_skill_coverage_incomplete:" + ",".join(missing_required))
    capabilities = _required_capabilities(value, required_skills)
    raw_checks = value.get("checks")
    if not isinstance(raw_checks, Sequence) or isinstance(raw_checks, (str, bytes, bytearray)):
        raise ContractError("invalid_gate_checks", "gate checks must be an array")
    checks: dict[str, Mapping[str, Any]] = {}
    for raw in raw_checks:
        check = require_mapping(raw, "checks[]")
        check_id = require_string(check.get("check_id"), "checks[].check_id")
        unknown_check_fields = sorted(set(check) - {"check_id", "evidence"})
        if unknown_check_fields:
            reasons.append(f"caller_check_fields_forbidden:{check_id}:" + ",".join(unknown_check_fields))
        if check_id in checks:
            reasons.append(f"duplicate_check:{check_id}")
        checks[check_id] = check
    required_check_ids = set(REQUIRED_LOCAL_CHECKS) | {f"capability:{item}" for item in capabilities}
    for check_id in sorted(required_check_ids):
        check = checks.get(check_id)
        if check is None:
            reasons.append(f"missing_check:{check_id}")
            continue
        evidence_payload = check.get("evidence")
        if not isinstance(evidence_payload, Mapping):
            reasons.append(f"missing_evidence:{check_id}")
            continue
        try:
            evidence = EvidenceRecord.from_payload(evidence_payload)
            evidence_path = evidence.verify(evidence_root, require_independent=True)
            if evidence.status is not Status.LOCAL_ENGINEERING_VALIDATED:
                raise ContractError("non_passing_evidence", "evidence status is not locally validated")
            _verify_check_report(evidence_path, check_id=check_id, evidence=evidence)
            capability = check_id.partition(":")[2] if check_id.startswith("capability:") else None
            expected_class = capability or "local"
            if evidence.evidence_class != expected_class:
                raise ContractError("capability_evidence_class", f"{check_id} requires {expected_class}-class evidence")
        except ContractError as exc:
            reasons.append(f"invalid_evidence:{check_id}:{exc.code}")
            continue
        verified_checks.append(check_id)
    return GateDecision(
        status=Status.BLOCKED if reasons else Status.LOCAL_ENGINEERING_VALIDATED,
        certification=Status.NOT_CERTIFIED,
        reasons=tuple(sorted(set(reasons))),
        verified_checks=tuple(sorted(verified_checks)),
        handler_coverage=coverage,
        required_capabilities=capabilities,
    )
