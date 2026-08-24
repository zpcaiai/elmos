"""Fail-closed dispatcher for the bounded local software-factory runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .capabilities import CAPABILITY_CONTRACTS, CapabilityContract
from .canonical import canonical_digest, strict_json_copy
from .handlers import HandlerContext, HandlerOutcome, handle
from .models import (
    CONTRACT_VERSION,
    ContractError,
    ExecutionError,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ScopeEnvelope,
)
from .public_methods import PUBLIC_METHODS, PublicMethodBinding, public_method
from .registry import SkillBinding, SkillRegistry, load_registry


_ARRAY_INPUTS = frozenset(
    {
        "nodes", "invariants", "requested_permissions", "tools", "inventory", "edges",
        "capabilities", "unknowns", "requirements", "rules", "roles", "evidence_refs",
        "claims", "changes", "failures", "candidates", "data_classes", "entries",
        "argv", "scenario_set",
    }
)
_OBJECT_INPUTS = frozenset(
    {
        "job", "target_profile", "rollback", "task", "usage", "candidate",
        "execution_contract", "event", "tool_call", "output", "limits", "lsp_request",
        "api_request", "repository_snapshot", "query", "target_ir", "workspace_request",
        "journal_event", "handoff", "build_request", "test_request", "generator_profile",
        "journey", "workload", "evidence_bundle", "outcome", "training_request",
    }
)
_INTEGER_INPUTS = frozenset({"budget_micros", "capacity", "value_score"})
_STRING_INPUTS = frozenset(
    {
        "package_id", "config_revision", "upstream_ref", "session_id", "task_id", "prompt",
        "sandbox_mode", "trace_ref", "tracker_cursor", "review_ref", "provider",
        "failure_signature", "corpus_version",
    }
)


def _required_input_error(
    capability: CapabilityContract | PublicMethodBinding,
    request: ExecutionRequest,
) -> ExecutionError | None:
    missing: list[str] = []
    invalid: list[str] = []
    for field in capability.required_inputs:
        if field == "target_skill_or_public_method":
            if not any(request.payload.get(name) for name in ("target_skill", "public_method")):
                missing.append(field)
            continue
        if field == "source_revision":
            continue
        if field not in request.payload:
            missing.append(field)
            continue
        value = request.payload[field]
        if field in _ARRAY_INPUTS and not isinstance(value, list):
            invalid.append(field)
        elif field in _OBJECT_INPUTS and not isinstance(value, Mapping):
            invalid.append(field)
        elif field in _INTEGER_INPUTS and (isinstance(value, bool) or not isinstance(value, int)):
            invalid.append(field)
        elif field in _STRING_INPUTS and (
            not isinstance(value, str) or not value or len(value) > 192
        ):
            invalid.append(field)
        elif field not in _ARRAY_INPUTS | _OBJECT_INPUTS | _INTEGER_INPUTS | _STRING_INPUTS and value is None:
            invalid.append(field)
    if missing:
        return ExecutionError(
            "REQUIRED_INPUT_MISSING",
            "capability request is missing required inputs",
            False,
            {"missing": sorted(missing)},
        )
    if invalid:
        return ExecutionError(
            "REQUIRED_INPUT_INVALID",
            "capability request has required inputs with invalid types",
            False,
            {"invalid": sorted(invalid)},
        )
    return None


def _unresolved_envelope(document: object) -> ScopeEnvelope:
    value = document if isinstance(document, Mapping) else {}

    def token(name: str) -> str:
        candidate = value.get(name)
        if isinstance(candidate, str) and candidate and len(candidate) <= 192:
            return candidate
        return "unresolved"

    return ScopeEnvelope(
        tenant_id=token("tenant_id"),
        project_id=token("project_id"),
        correlation_id=token("correlation_id"),
        policy_revision=token("policy_revision"),
        source_revision=token("source_revision"),
        idempotency_key=None,
    )


class SoftwareFactoryEngine:
    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self.registry = registry or load_registry()
        if set(CAPABILITY_CONTRACTS) != set(self.registry.bindings):
            missing = sorted(set(self.registry.bindings) - set(CAPABILITY_CONTRACTS))
            extra = sorted(set(CAPABILITY_CONTRACTS) - set(self.registry.bindings))
            raise RuntimeError(
                f"capability contracts do not match Skill bindings; missing={missing}, extra={extra}"
            )
        for package in self.registry.packages.values():
            package_skills = (package.name, *package.child_skills)
            expected_adapter_actions = frozenset(
                CAPABILITY_CONTRACTS[name].action
                for name in package_skills
                if CAPABILITY_CONTRACTS[name].mode == "requires_adapter"
            )
            expected_adapter_actions |= frozenset(
                method.action
                for method in PUBLIC_METHODS.values()
                if method.package_id == package.package_id
                and method.execution_mode == "requires_adapter"
            )
            if package.adapter_actions != expected_adapter_actions:
                raise RuntimeError(
                    f"{package.package_id} adapter actions drift from capability registry"
                )

    def _result(
        self,
        *,
        binding: SkillBinding,
        request: ExecutionRequest,
        outcome: HandlerOutcome,
        evidence: tuple[Mapping[str, Any], ...] = (),
        warnings: tuple[str, ...] = (),
        public_binding: PublicMethodBinding | None = None,
    ) -> ExecutionResult:
        capability = CAPABILITY_CONTRACTS.get(binding.name)
        binding_contract: dict[str, Any] = {
            "skill_name": binding.name,
            "kind": binding.kind.value,
            "package_id": binding.package_id,
            "capability_key": binding.name.removeprefix("elmos-"),
            "operation": binding.operation,
            "required_package_receipts": list(binding.dependencies),
            "adapter_boundary": sorted(binding.adapter_actions),
        }
        if capability is not None:
            binding_contract.update(
                {
                    "capability_action": capability.action,
                    "capability_mode": capability.mode,
                    "required_inputs": list(capability.required_inputs),
                }
            )
        if public_binding is not None:
            binding_contract["public_method"] = public_binding.method
            binding_contract["public_method_mode"] = public_binding.execution_mode
            binding_contract["required_inputs"] = list(public_binding.required_inputs)
            binding_contract["domain_errors"] = list(public_binding.domain_errors)
            binding_contract["platform_errors"] = list(public_binding.platform_errors)
            binding_contract["effective_action"] = public_binding.action
            binding_contract["effective_mode"] = public_binding.execution_mode
        elif capability is not None:
            binding_contract["effective_action"] = capability.action
            binding_contract["effective_mode"] = capability.mode
        output = {"binding_contract": binding_contract, **outcome.output}
        return ExecutionResult.create(
            status=outcome.status,
            skill_name=binding.name,
            package_id=binding.package_id,
            operation=binding.operation,
            envelope=request.envelope,
            output=output,
            error=outcome.error,
            evidence=evidence,
            warnings=(
                "Local execution is engineering evidence only; certification remains NOT_CERTIFIED.",
                *warnings,
            ),
            registry_digest=self.registry.registry_digest,
            request_digest=request.request_digest,
        )

    def _scope_error(self, request: ExecutionRequest) -> ExecutionError | None:
        envelope = request.envelope
        for receipt in request.dependencies:
            if (
                receipt.tenant_id != envelope.tenant_id
                or receipt.project_id != envelope.project_id
                or receipt.correlation_id != envelope.correlation_id
                or receipt.policy_revision != envelope.policy_revision
                or receipt.source_revision != envelope.source_revision
            ):
                return ExecutionError(
                    "DEPENDENCY_SCOPE_MISMATCH",
                    f"dependency receipt {receipt.package_id} does not match the request scope",
                )
            receipt_binding = self.registry.binding(receipt.skill_name)
            if receipt_binding is None or receipt_binding.package_id != receipt.package_id:
                return ExecutionError(
                    "DEPENDENCY_IDENTITY_MISMATCH",
                    f"dependency receipt {receipt.package_id} has an invalid Skill identity",
                )
            if receipt.status is not ExecutionStatus.EXECUTED:
                return ExecutionError(
                    "DEPENDENCY_NOT_EXECUTED",
                    f"dependency receipt {receipt.package_id} is not EXECUTED",
                )
        for observation in request.observations:
            if (
                observation.tenant_id != envelope.tenant_id
                or observation.project_id != envelope.project_id
                or observation.correlation_id != envelope.correlation_id
                or observation.policy_revision != envelope.policy_revision
                or observation.source_revision != envelope.source_revision
            ):
                return ExecutionError(
                    "EVIDENCE_SCOPE_MISMATCH",
                    f"external observation {observation.observation_id} does not match the request scope",
                )
        return None

    @staticmethod
    def _observation_evidence(request: ExecutionRequest) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            {
                "observation_id": observation.observation_id,
                "action": observation.action,
                "evidence_digest": observation.evidence_digest,
                "observation_digest": observation.observation_digest,
                "byte_count": observation.byte_count,
                "executor_id": observation.executor_id,
                "verifier_id": observation.verifier_id,
                "authorized_claim": observation.authorized,
                "verified_claim": observation.verified,
                "trust_state": "CALLER_ASSERTED_NOT_LOCALLY_VERIFIED",
            }
            for observation in request.observations
        )

    def execute(
        self,
        skill_name: str,
        document: object,
        *,
        public_binding: PublicMethodBinding | None = None,
    ) -> ExecutionResult:
        request = ExecutionRequest.from_mapping(document)
        binding = self.registry.binding(skill_name)
        if binding is None:
            unresolved = SkillBinding(
                name=skill_name if isinstance(skill_name, str) and skill_name else "unresolved-skill",
                package_id="UNRESOLVED",
                kind=next(iter(self.registry.bindings.values())).kind,
                operation="unresolved",
                dependencies=(),
                adapter_actions=frozenset(),
            )
            return self._result(
                binding=unresolved,
                request=request,
                outcome=HandlerOutcome(
                    ExecutionStatus.BLOCKED,
                    {},
                    ExecutionError("SKILL_NOT_FOUND", "requested Skill is not bound by this runtime"),
                ),
            )

        capability = CAPABILITY_CONTRACTS[binding.name]
        scope_error = self._scope_error(request)
        if scope_error is not None:
            return self._result(
                binding=binding,
                request=request,
                outcome=HandlerOutcome(ExecutionStatus.BLOCKED, {}, scope_error),
            )

        if skill_name not in request.policy.allowed_skills:
            return self._result(
                binding=binding,
                request=request,
                outcome=HandlerOutcome(
                    ExecutionStatus.BLOCKED,
                    {},
                    ExecutionError("POLICY_DENIED", "policy does not allow the requested Skill"),
                ),
            )
        action = request.payload.get("action", capability.action)
        if not isinstance(action, str) or not action:
            return self._result(
                binding=binding,
                request=request,
                outcome=HandlerOutcome(
                    ExecutionStatus.BLOCKED,
                    {},
                    ExecutionError("PAYLOAD_INVALID", "payload.action must be a non-empty string"),
                ),
            )
        if binding.kind.value == "child" and action != capability.action:
            return self._result(
                binding=binding,
                request=request,
                outcome=HandlerOutcome(
                    ExecutionStatus.BLOCKED,
                    {"required_action": capability.action, "requested_action": action},
                    ExecutionError(
                        "CAPABILITY_ACTION_MISMATCH",
                        "child Skill may execute only its exact capability action",
                    ),
                ),
            )
        if action not in request.policy.allowed_actions:
            return self._result(
                binding=binding,
                request=request,
                outcome=HandlerOutcome(
                    ExecutionStatus.BLOCKED,
                    {},
                    ExecutionError("POLICY_DENIED", "policy does not allow the requested action"),
                ),
            )
        if (
            action in request.policy.approval_required_actions
            and action not in request.policy.approved_actions
        ):
            return self._result(
                binding=binding,
                request=request,
                outcome=HandlerOutcome(
                    ExecutionStatus.BLOCKED,
                    {},
                    ExecutionError("APPROVAL_REQUIRED", "action requires an approval not present in policy"),
                ),
            )

        input_error = _required_input_error(public_binding or capability, request)
        if input_error is not None:
            return self._result(
                binding=binding,
                request=request,
                outcome=HandlerOutcome(ExecutionStatus.BLOCKED, {}, input_error),
                public_binding=public_binding,
            )

        provided_dependencies = {receipt.package_id for receipt in request.dependencies}
        missing_dependencies = sorted(set(binding.dependencies) - provided_dependencies)
        if missing_dependencies:
            return self._result(
                binding=binding,
                request=request,
                outcome=HandlerOutcome(
                    ExecutionStatus.BLOCKED,
                    {"missing_package_receipts": missing_dependencies},
                    ExecutionError("DEPENDENCY_BLOCKED", "required package receipts are missing"),
                ),
            )

        evidence = self._observation_evidence(request)
        adapter_required = (
            (public_binding.execution_mode == "requires_adapter" if public_binding is not None else capability.mode == "requires_adapter")
            or action in binding.adapter_actions
        )
        if adapter_required:
            if request.envelope.idempotency_key is None:
                return self._result(
                    binding=binding,
                    request=request,
                    outcome=HandlerOutcome(
                        ExecutionStatus.BLOCKED,
                        {},
                        ExecutionError(
                            "IDEMPOTENCY_KEY_REQUIRED",
                            "external or side-effecting actions require an idempotency key",
                        ),
                    ),
                    evidence=evidence,
                    public_binding=public_binding,
                )
            provider = request.payload.get("provider")
            if provider is not None and provider not in request.policy.allowed_providers:
                return self._result(
                    binding=binding,
                    request=request,
                    outcome=HandlerOutcome(
                        ExecutionStatus.BLOCKED,
                        {},
                        ExecutionError("POLICY_DENIED", "provider is not allowed by policy"),
                    ),
                    evidence=evidence,
                    public_binding=public_binding,
                )
            matching = [item for item in evidence if item["action"] == action]
            return self._result(
                binding=binding,
                request=request,
                outcome=HandlerOutcome(
                    ExecutionStatus.REQUIRES_ADAPTER,
                    {
                        "adapter_requirement": {
                            "action": action,
                            "observation_claim_count": len(matching),
                            "missing_capabilities": [
                                "adapter_execution",
                                "evidence_byte_resolution",
                                "signature_and_trust_root_verification",
                                "external_authorization_verification",
                            ],
                        },
                        "side_effect_state": "NOT_STARTED",
                    },
                    ExecutionError(
                        "ADAPTER_REQUIRED",
                        "the bounded local runtime cannot perform or prove this external action",
                    ),
                ),
                evidence=evidence,
                warnings=(
                    "External observations are caller-supplied integrity claims and never substitute for adapter execution or trust verification.",
                    "No external action or side effect was started.",
                ),
                public_binding=public_binding,
            )

        if binding.kind.value == "root":
            target = request.payload.get("target_skill")
            method_name = request.payload.get("public_method")
            if target is None and method_name is not None:
                method_binding = public_method(method_name) if isinstance(method_name, str) else None
                target = (
                    self.registry.packages[method_binding.package_id].name
                    if method_binding is not None
                    else None
                )
            target_binding = self.registry.binding(target) if isinstance(target, str) else None
            if target_binding is None:
                outcome = HandlerOutcome(
                    ExecutionStatus.BLOCKED,
                    {},
                    ExecutionError("ROUTE_NOT_FOUND", "root route requires a registered target_skill or public_method"),
                )
            else:
                outcome = HandlerOutcome(
                    ExecutionStatus.EXECUTED,
                    {
                        "resolved_target": target_binding.name,
                        "package_id": target_binding.package_id,
                        "operation": target_binding.operation,
                        "required_package_receipts": list(target_binding.dependencies),
                        "adapter_boundary": sorted(target_binding.adapter_actions),
                        "execution_state": "ROUTED_NOT_EXECUTED",
                    },
                )
        else:
            package = self.registry.packages[binding.package_id]
            effective_contract = public_binding or capability
            outcome = handle(
                binding.operation,
                request,
                package,
                self.registry,
                HandlerContext(
                    skill_name=binding.name,
                    capability_identity=(
                        public_binding.method if public_binding is not None else binding.name
                    ),
                    capability_action=effective_contract.action,
                    required_inputs=effective_contract.required_inputs,
                ),
            )
            if (
                public_binding is not None
                and outcome.error is not None
                and outcome.error.code
                not in set(public_binding.domain_errors) | set(public_binding.platform_errors)
            ):
                original_error = outcome.error
                outcome = HandlerOutcome(
                    outcome.status,
                    outcome.output,
                    ExecutionError(
                        public_binding.domain_errors[0],
                        original_error.message,
                        original_error.retryable,
                        {
                            "runtime_error_code": original_error.code,
                            **({} if original_error.details is None else original_error.details),
                        },
                    ),
                )
        warnings: tuple[str, ...] = ()
        if request.dependencies:
            warnings += ("Dependency receipts are canonical integrity records, not signatures or independent attestations.",)
        if evidence:
            warnings += ("External observations were recorded as unverified caller assertions only.",)
        return self._result(
            binding=binding,
            request=request,
            outcome=outcome,
            evidence=evidence,
            warnings=warnings,
            public_binding=public_binding,
        )

    def execute_method(self, method_name: str, document: object) -> ExecutionResult:
        binding = public_method(method_name)
        if binding is None:
            request = ExecutionRequest.from_mapping(document)
            unresolved = SkillBinding(
                name="unresolved-public-method",
                package_id="UNRESOLVED",
                kind=next(iter(self.registry.bindings.values())).kind,
                operation="unresolved",
                dependencies=(),
                adapter_actions=frozenset(),
            )
            return self._result(
                binding=unresolved,
                request=request,
                outcome=HandlerOutcome(
                    ExecutionStatus.BLOCKED,
                    {},
                    ExecutionError("METHOD_NOT_FOUND", "requested public method is not registered"),
                ),
            )
        copied = strict_json_copy(document, field="request")
        if not isinstance(copied, dict):
            raise ContractError("request must be an object")
        payload = copied.get("payload", {})
        if not isinstance(payload, dict):
            raise ContractError("request.payload must be an object")
        if "action" in payload and payload["action"] != binding.action:
            raise ContractError("request payload.action conflicts with public method binding")
        copied["payload"] = {**payload, "action": binding.action}
        package_skill = self.registry.packages[binding.package_id].name
        return self.execute(package_skill, copied, public_binding=binding)


def dispatch_skill(skill_name: str, document: object) -> dict[str, Any]:
    engine = SoftwareFactoryEngine()
    try:
        return engine.execute(skill_name, document).as_dict()
    except (ContractError, TypeError, ValueError) as exc:
        envelope = _unresolved_envelope(document)
        binding = engine.registry.binding(skill_name)
        try:
            input_digest = canonical_digest(strict_json_copy(document, field="request"))
        except (TypeError, ValueError):
            input_digest = None
        result = ExecutionResult.create(
            status=ExecutionStatus.FAILED,
            skill_name=binding.name if binding is not None else "unresolved-skill",
            package_id=binding.package_id if binding is not None else "UNRESOLVED",
            operation=binding.operation if binding is not None else "unresolved",
            envelope=envelope,
            output={"input_digest": input_digest},
            error=ExecutionError("REQUEST_INVALID", str(exc)),
            evidence=(),
            warnings=("No handler or adapter was executed.",),
            registry_digest=engine.registry.registry_digest,
            request_digest=input_digest or canonical_digest({"request_state": "UNRESOLVED_INVALID"}),
        )
        return result.as_dict()
