"""Fail-closed local policy decisions; never signatures or certification."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import math
import time
from typing import Any

from .canonical import require_identifier, validate_digest
from .domain import (
    ConsentStatus,
    DatasetItem,
    GateLevel,
    LifecycleState,
    RightsClass,
    SkillContract,
    TenantScope,
)

ContextVerifier = Callable[[TenantScope, str | None], TenantScope]
ApprovalVerifier = Callable[[Mapping[str, Any], TenantScope, SkillContract], bool]


class PolicyEngine:
    def __init__(
        self,
        context_verifier: ContextVerifier | None = None,
        *,
        approval_verifier: ApprovalVerifier | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._context_verifier = context_verifier
        self._approval_verifier = approval_verifier
        self._clock = clock

    def _context(
        self,
        value: object,
        capability: str,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
    ) -> TenantScope | None:
        if not isinstance(value, TenantScope) or self._context_verifier is None:
            return None
        try:
            verified = self._context_verifier(value, capability)
        except Exception:
            return None
        if (
            not isinstance(verified, TenantScope)
            or not verified.authenticated
            or verified.binding_digest != value.binding_digest
        ):
            return None
        if tenant_id is not None and verified.tenant_id != tenant_id:
            return None
        if project_id and verified.project_id != project_id:
            return None
        return verified

    def evaluate_training_eligibility(
        self,
        dataset_item: DatasetItem | Mapping[str, Any],
        *,
        security_context: TenantScope | None = None,
        purpose: str | None = None,
    ) -> Mapping[str, Any]:
        violations: list[str] = []
        try:
            if isinstance(dataset_item, DatasetItem):
                consent, rights, quarantine, quality = (
                    ConsentStatus(dataset_item.consent_status),
                    RightsClass(dataset_item.rights_class),
                    dataset_item.quarantine,
                    dataset_item.quality_score,
                )
                if not isinstance(quarantine, bool):
                    raise ValueError("quarantine must be boolean")
                tenant_id = require_identifier(dataset_item.tenant_id, "tenant_id")
                project_id = require_identifier(dataset_item.project_id, "project_id")
            else:
                required = {
                    "consent_status",
                    "rights_class",
                    "quarantine",
                    "quality_score",
                    "tenant_id",
                    "project_id",
                }
                missing = sorted(required - set(dataset_item))
                if missing:
                    raise ValueError(f"missing required inputs: {missing}")
                consent, rights = (
                    ConsentStatus(dataset_item["consent_status"]),
                    RightsClass(dataset_item["rights_class"]),
                )
                quarantine = dataset_item["quarantine"]
                if not isinstance(quarantine, bool):
                    raise ValueError("quarantine must be boolean")
                raw_quality = dataset_item["quality_score"]
                if isinstance(raw_quality, bool) or not isinstance(raw_quality, (int, float)):
                    raise ValueError("quality_score must be numeric")
                quality = float(raw_quality)
                tenant_id = require_identifier(str(dataset_item["tenant_id"]), "tenant_id")
                project_id = require_identifier(str(dataset_item["project_id"]), "project_id")
        except (KeyError, TypeError, ValueError) as exc:
            return {
                "policy": "training-eligibility",
                "decision": "DENY",
                "eligible": False,
                "violations": (f"invalid policy input: {exc}",),
                "certification_status": "NOT_CERTIFIED",
            }
        if not math.isfinite(quality) or not 0 <= quality <= 1:
            violations.append("Quality score must be finite and in [0,1]")
        elif quality < 0.7:
            violations.append("Quality score is below 0.70")
        if quarantine:
            violations.append("Item is under quarantine")
        if consent is ConsentStatus.DENY:
            violations.append("Training consent is explicitly denied")
        training_context = self._context(
            security_context,
            "foundry.training.use",
            tenant_id=tenant_id,
            project_id=project_id,
        )
        if training_context is None:
            violations.append("Training use lacks a host-verified tenant/project capability")
        if not isinstance(purpose, str) or not purpose:
            violations.append("Training use requires an exact purpose")
        elif training_context is not None and training_context.purpose != purpose:
            violations.append("Training purpose does not match leased context")
        if consent is ConsentStatus.CONDITIONAL:
            if (
                self._context(
                    security_context,
                    "foundry.training.conditional",
                    tenant_id=tenant_id,
                    project_id=project_id,
                )
                is None
            ):
                violations.append("Conditional consent lacks a host-verified capability")
        capability = {
            RightsClass.RESTRICTED: "foundry.training.restricted",
            RightsClass.CUSTOMER_PROPRIETARY: "foundry.training.customer-proprietary",
        }.get(rights)
        if (
            capability
            and self._context(
                security_context, capability, tenant_id=tenant_id, project_id=project_id
            )
            is None
        ):
            violations.append(f"{rights.value} data lacks an exact host-verified exemption")
        eligible = not violations
        return {
            "policy": "training-eligibility",
            "decision": "ALLOW" if eligible else "DENY",
            "eligible": eligible,
            "violations": tuple(violations),
            "certification_status": "NOT_CERTIFIED",
        }

    def evaluate_skill_execution(
        self, skill_contract: SkillContract | Mapping[str, Any], caller_context: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        violations: list[str] = []
        contract: SkillContract | None = None
        if isinstance(skill_contract, SkillContract):
            contract = skill_contract
            risk, status, skill_name = (
                contract.risk_class,
                contract.status.value,
                contract.skill_name,
            )
        else:
            try:
                required = {
                    "skill_name",
                    "pack",
                    "owner",
                    "risk_class",
                    "status",
                    "version",
                    "content_hash",
                }
                missing = sorted(required - set(skill_contract))
                if missing:
                    raise ValueError(f"missing contract fields: {missing}")
                skill_name = require_identifier(str(skill_contract["skill_name"]), "skill_name")
                risk = str(skill_contract["risk_class"])
                state = skill_contract["status"]
                status = (
                    state.value
                    if isinstance(state, LifecycleState)
                    else LifecycleState(str(state)).value
                )
                contract = SkillContract(
                    skill_name,
                    str(skill_contract["pack"]),
                    str(skill_contract["owner"]),
                    risk,
                    LifecycleState(status),
                    str(skill_contract["version"]),
                    str(skill_contract["content_hash"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                violations.append(f"invalid skill contract: {exc}")
                risk, status, skill_name = "unknown", "INVALID", "invalid"
        executable = {
            LifecycleState.PROFILED.value,
            LifecycleState.PLANNED.value,
            LifecycleState.EVIDENCE_SEALED.value,
            LifecycleState.CERTIFIED.value,
        }
        if status not in executable:
            violations.append(f"Skill status {status} is not locally executable")
        verified = self._context(caller_context.get("security_context"), "foundry.skill.execute")
        if verified is None:
            violations.append("Skill execution lacks a host-minted capability lease")
        elif (
            caller_context.get("purpose") is not None
            and caller_context["purpose"] != verified.purpose
        ):
            violations.append("Invocation purpose does not match leased context")
        if risk == "critical":
            approval = caller_context.get("human_approval")
            if not isinstance(approval, Mapping):
                violations.append("Critical skill requires a verifier-backed approval record")
            elif verified is None or contract is None or self._approval_verifier is None:
                violations.append("No trusted critical-approval verifier is configured")
            else:
                try:
                    approver = require_identifier(
                        str(approval["approver_actor_id"]), "approver_actor_id"
                    )
                    target = require_identifier(str(approval["skill_name"]), "approval.skill_name")
                    validate_digest(str(approval["approval_digest"]), "approval_digest")
                    expiry = approval["expires_at"]
                    if isinstance(expiry, bool) or not isinstance(expiry, int):
                        raise ValueError("approval expiry must be integer")
                    if approval.get("authorized") is not True:
                        raise ValueError("approval is not explicitly authorized")
                    if approver == verified.actor_id:
                        raise ValueError("requester cannot self-approve")
                    if target != skill_name:
                        raise ValueError("approval targets a different skill")
                    if expiry <= int(self._clock()):
                        raise ValueError("approval expired")
                    if not self._approval_verifier(approval, verified, contract):
                        raise ValueError("trusted verification failed")
                except (KeyError, TypeError, ValueError) as exc:
                    violations.append(f"Critical approval is invalid: {exc}")
        allowed = not violations
        return {
            "policy": "skill-execution",
            "decision": "ALLOW" if allowed else "DENY",
            "allowed": allowed,
            "violations": tuple(violations),
            "skill_name": skill_name,
            "certification_status": "NOT_CERTIFIED",
        }

    def evaluate_model_promotion(
        self,
        target_gate: GateLevel,
        eval_metrics: Mapping[str, Any],
        proof_obligations_satisfied: bool,
    ) -> Mapping[str, Any]:
        if not isinstance(target_gate, GateLevel):
            raise TypeError("target_gate must be GateLevel")
        violations: list[str] = []
        if not isinstance(proof_obligations_satisfied, bool) or not proof_obligations_satisfied:
            violations.append("Required proof obligations are not satisfied")

        def metric(name: str, integer: bool = False) -> float | int | None:
            value = eval_metrics.get(name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                violations.append(f"Metric {name} is missing, non-numeric, or non-finite")
                return None
            if integer and (not isinstance(value, int) or value < 0):
                violations.append(f"Metric {name} must be non-negative integer")
                return None
            return value

        if target_gate is GateLevel.E1_UNIT_EVAL:
            value = metric("unit_eval_score")
            if value is not None and (not 0 <= value <= 1 or value < 0.85):
                violations.append("Unit evaluation score does not meet 0.85")
        elif target_gate is GateLevel.E2_INTEGRATION:
            value = metric("integration_pass_rate")
            if value is not None and (not 0 <= value <= 1 or value < 0.95):
                violations.append("Integration pass rate does not meet 0.95")
        elif target_gate is GateLevel.E3_SHADOW_CANARY:
            value = metric("canary_error_rate")
            if value is not None and (not 0 <= value <= 1 or value > 0.01):
                violations.append("Canary error rate exceeds 0.01")
        else:
            value = metric("regression_count", True)
            if value is not None and value != 0:
                violations.append("Readiness requires zero regressions")
            if target_gate is GateLevel.E5_FORMAL_PROVEN:
                violations.append(
                    "Formal proof requires an independently verified external decision"
                )
        external = target_gate in {
            GateLevel.E3_SHADOW_CANARY,
            GateLevel.E4_PRODUCTION_CERTIFIED,
            GateLevel.E5_FORMAL_PROVEN,
        }
        approved = not violations and not external
        ready = not violations and external
        return {
            "policy": "model-promotion",
            "target_gate": target_gate.value,
            "decision": "ALLOW_LOCAL"
            if approved
            else "READY_FOR_EXTERNAL_GATE"
            if ready
            else "DENY",
            "approved": approved,
            "ready_for_external_gate": ready,
            "violations": tuple(violations),
            "evidence_state": "COLLECTED_SELF_ATTESTED",
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }


__all__ = ["ApprovalVerifier", "ContextVerifier", "PolicyEngine"]
