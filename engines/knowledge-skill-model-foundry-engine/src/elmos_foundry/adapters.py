"""Typed, fail-closed adapter bindings for Foundry Skill invocations.

Adapters are trusted runtime configuration, never data discovered in the
source Skill package. Every binding is pinned to an exact identity, version,
digest, Skill set and effect class. External effects additionally require a
trusted permit verifier; a caller-created ``authorized=True`` value has no
authority by itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
import time
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from .canonical import canonical_digest, canonical_value, require_identifier, validate_digest
from .domain import TenantScope
from .store import FoundryStore, IdempotencyConflict, RunState, StoreError


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class EffectClass(str, Enum):
    """Maximum effect authority of one exact adapter binding."""

    LOCAL_DETERMINISTIC = "LOCAL_DETERMINISTIC"
    EXTERNAL_READ = "EXTERNAL_READ"
    EXTERNAL_MUTATION = "EXTERNAL_MUTATION"
    PRIVILEGED_EXTERNAL = "PRIVILEGED_EXTERNAL"

    @property
    def is_external(self) -> bool:
        return self is not EffectClass.LOCAL_DETERMINISTIC


@dataclass(frozen=True, slots=True)
class AdapterBinding:
    """Digest-bound identity and exact Skill scope for a runtime adapter."""

    adapter_id: str
    version: str
    digest: str
    exact_skills: tuple[str, ...]
    effect_class: EffectClass
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_identifier(self.adapter_id, "adapter_id")
        require_identifier(self.version, "adapter_version")
        if not _SHA256_RE.fullmatch(self.digest):
            raise ValueError("adapter digest must be a lowercase SHA-256")
        if not isinstance(self.effect_class, EffectClass):
            raise TypeError("effect_class must be an EffectClass")
        if not self.exact_skills or len(set(self.exact_skills)) != len(self.exact_skills):
            raise ValueError("adapter exact_skills must be non-empty and unique")
        for name in self.exact_skills:
            require_identifier(name, "adapter_skill_name")
        normalized_metadata = canonical_value(self.metadata)
        if not isinstance(normalized_metadata, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in normalized_metadata.items()
        ):
            raise ValueError("adapter metadata must be a string-to-string object")
        object.__setattr__(self, "exact_skills", tuple(sorted(self.exact_skills)))
        object.__setattr__(self, "metadata", MappingProxyType(normalized_metadata))


@dataclass(frozen=True, slots=True)
class ExternalAdapterRoute:
    """Non-executable route identity consumed only by a host-owned broker."""

    route_id: str
    version: str
    digest: str
    operation: str

    def __post_init__(self) -> None:
        for field_name in ("route_id", "version", "operation"):
            require_identifier(getattr(self, field_name), field_name)
        if not _SHA256_RE.fullmatch(self.digest):
            raise ValueError("external route digest must be a lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class InvocationPermit:
    """Exact, expiring authorization claim subject to trusted verification.

    The permit is data, not authority.  It must match the complete invocation
    request and be accepted by the host-configured verifier before a durable
    replay claim is recorded.
    """

    permit_id: str
    authorization_id: str
    invocation_id: str
    adapter_id: str
    adapter_version: str
    adapter_digest: str
    broker_id: str
    broker_version: str
    broker_digest: str
    route_id: str
    route_digest: str
    skill_name: str
    tenant_id: str
    project_id: str
    actor_id: str
    effect_class: EffectClass
    operation: str
    payload_digest: str
    purpose: str
    environment_id: str
    workspace_digest: str
    revision_set_id: str
    issued_at: int
    expires_at: int
    nonce: str
    policy_decision_id: str
    policy_decision_digest: str
    authorized_tools: tuple[str, ...]
    authorized_gates: tuple[str, ...]
    gate_evidence_digest: str
    critical_approval_id: str | None = None
    critical_approval_digest: str | None = None
    authorized: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "permit_id",
            "authorization_id",
            "invocation_id",
            "adapter_id",
            "adapter_version",
            "broker_id",
            "broker_version",
            "route_id",
            "skill_name",
            "tenant_id",
            "project_id",
            "actor_id",
            "operation",
            "purpose",
            "environment_id",
            "nonce",
            "policy_decision_id",
        ):
            require_identifier(getattr(self, field_name), field_name)
        for field_name in ("adapter_digest", "broker_digest", "route_digest"):
            if not _SHA256_RE.fullmatch(getattr(self, field_name)):
                raise ValueError(f"permit {field_name} must be a lowercase SHA-256")
        for field_name in (
            "payload_digest",
            "workspace_digest",
            "revision_set_id",
            "policy_decision_digest",
            "gate_evidence_digest",
        ):
            validate_digest(getattr(self, field_name), field_name)
        for field_name in ("issued_at", "expires_at"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.issued_at <= 0 or self.expires_at <= self.issued_at:
            raise ValueError("permit validity interval is invalid")
        tools = tuple(self.authorized_tools)
        if tools != tuple(sorted(set(tools))):
            raise ValueError("authorized_tools must be unique and canonically sorted")
        for tool in tools:
            require_identifier(tool, "authorized_tool")
        object.__setattr__(self, "authorized_tools", tools)
        gates = tuple(self.authorized_gates)
        if gates != tuple(sorted(set(gates))):
            raise ValueError("authorized_gates must be unique and canonically sorted")
        for gate in gates:
            require_identifier(gate, "authorized_gate")
        object.__setattr__(self, "authorized_gates", gates)
        for field_name in ("critical_approval_id", "critical_approval_digest"):
            value = getattr(self, field_name)
            if value is not None:
                if field_name.endswith("_digest"):
                    validate_digest(value, field_name)
                else:
                    require_identifier(value, field_name)
        if (self.critical_approval_id is None) != (self.critical_approval_digest is None):
            raise ValueError("critical approval id and digest must be supplied together")
        if not isinstance(self.effect_class, EffectClass):
            raise TypeError("permit effect_class must be an EffectClass")
        if not isinstance(self.authorized, bool):
            raise TypeError("permit authorized must be a boolean")


@dataclass(frozen=True, slots=True)
class InvocationRequest:
    """Canonical request exposed to the trusted permit verifier."""

    skill_name: str
    operation: str
    payload_digest: str
    tenant_id: str
    project_id: str
    actor_id: str
    purpose: str
    environment_id: str
    workspace_digest: str
    revision_set_id: str
    invocation_id: str
    adapter_id: str
    adapter_version: str
    adapter_digest: str
    broker_id: str
    broker_version: str
    broker_digest: str
    route_id: str
    route_digest: str
    effect_class: EffectClass
    risk_class: str
    required_inputs: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    required_gates: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "skill_name",
            "operation",
            "tenant_id",
            "project_id",
            "actor_id",
            "purpose",
            "environment_id",
            "invocation_id",
            "adapter_id",
            "adapter_version",
            "broker_id",
            "broker_version",
            "route_id",
            "risk_class",
        ):
            require_identifier(getattr(self, field_name), field_name)
        for field_name in ("payload_digest", "workspace_digest", "revision_set_id"):
            validate_digest(getattr(self, field_name), field_name)
        for field_name in ("adapter_digest", "broker_digest", "route_digest"):
            if not _SHA256_RE.fullmatch(getattr(self, field_name)):
                raise ValueError(f"request {field_name} must be a lowercase SHA-256")
        if not isinstance(self.effect_class, EffectClass):
            raise TypeError("request effect_class must be an EffectClass")
        inputs = tuple(self.required_inputs)
        if not inputs or inputs != tuple(sorted(set(inputs))):
            raise ValueError("required_inputs must be non-empty, unique, and sorted")
        for input_name in inputs:
            if not isinstance(input_name, str) or not input_name:
                raise ValueError("required input names must be non-empty strings")
        object.__setattr__(self, "required_inputs", inputs)
        tools = tuple(self.allowed_tools)
        if not tools or tools != tuple(sorted(set(tools))):
            raise ValueError("allowed_tools must be non-empty, unique, and sorted")
        for tool in tools:
            require_identifier(tool, "allowed_tool")
        object.__setattr__(self, "allowed_tools", tools)
        gates = tuple(self.required_gates)
        if not gates or gates != tuple(sorted(set(gates))):
            raise ValueError("required_gates must be non-empty, unique, and sorted")
        for gate in gates:
            require_identifier(gate, "required_gate")
        object.__setattr__(self, "required_gates", gates)

    @property
    def binding_digest(self) -> str:
        return canonical_digest(self.binding_document())

    def binding_document(self) -> Mapping[str, Any]:
        return {
            "schema_version": "elmos.foundry.external-invocation.v1",
            "skill_name": self.skill_name,
            "operation": self.operation,
            "payload_digest": self.payload_digest,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "actor_id": self.actor_id,
            "purpose": self.purpose,
            "environment_id": self.environment_id,
            "workspace_digest": self.workspace_digest,
            "revision_set_id": self.revision_set_id,
            "invocation_id": self.invocation_id,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "adapter_digest": self.adapter_digest,
            "broker_id": self.broker_id,
            "broker_version": self.broker_version,
            "broker_digest": self.broker_digest,
            "route_id": self.route_id,
            "route_digest": self.route_digest,
            "effect_class": self.effect_class.value,
            "risk_class": self.risk_class,
            "required_inputs": list(self.required_inputs),
            "allowed_tools": list(self.allowed_tools),
            "required_gates": list(self.required_gates),
        }


@dataclass(frozen=True, slots=True)
class AdapterResult:
    status: str
    outputs: Mapping[str, Any]
    external_evidence_status: str = "NOT_RUN"
    certification_status: str = "NOT_CERTIFIED"
    external_effects_performed: bool = False
    error: str | None = None

    def __post_init__(self) -> None:
        normalized = canonical_value(self.outputs)
        if not isinstance(normalized, dict):
            raise TypeError("adapter outputs must be an object")
        object.__setattr__(self, "outputs", MappingProxyType(normalized))
        if self.certification_status != "NOT_CERTIFIED":
            raise ValueError("a Foundry adapter result cannot self-certify")


AdapterCallable = Callable[[str, Mapping[str, Any], TenantScope, str], Mapping[str, Any]]
PermitVerifier = Callable[
    [InvocationPermit, AdapterBinding, TenantScope, InvocationRequest], bool
]
ExternalBrokerExecutor = Callable[
    [
        ExternalAdapterRoute,
        AdapterBinding,
        InvocationRequest,
        InvocationPermit,
        Mapping[str, Any],
        TenantScope,
    ],
    Mapping[str, Any],
]
ExternalResultVerifier = Callable[
    [
        ExternalAdapterRoute,
        AdapterBinding,
        InvocationRequest,
        InvocationPermit,
        Mapping[str, Any],
        TenantScope,
    ],
    bool,
]


@dataclass(frozen=True, slots=True)
class ExternalExecutionBroker:
    """Explicit host trust boundary for out-of-process/tool-broker execution.

    The registry never hands an arbitrary Python adapter callable to this
    broker.  It supplies a non-executable route plus the exact authorized
    request.  Production hosts are responsible for attesting this broker and
    enforcing its sandbox/tool capabilities.
    """

    broker_id: str
    version: str
    digest: str
    execute: ExternalBrokerExecutor
    verify_result: ExternalResultVerifier

    def __post_init__(self) -> None:
        require_identifier(self.broker_id, "broker_id")
        require_identifier(self.version, "broker_version")
        if not _SHA256_RE.fullmatch(self.digest):
            raise ValueError("broker digest must be a lowercase SHA-256")
        if not callable(self.execute) or not callable(self.verify_result):
            raise TypeError("broker execute and verify_result must be callable")


class AdapterRegistry:
    """Exact adapter registry with no fallback and no forgeable permit path."""

    def __init__(
        self,
        *,
        permit_verifier: PermitVerifier | None = None,
        external_broker: ExternalExecutionBroker | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if permit_verifier is not None and not callable(permit_verifier):
            raise TypeError("permit_verifier must be callable")
        if external_broker is not None and not isinstance(
            external_broker, ExternalExecutionBroker
        ):
            raise TypeError("external_broker must be an ExternalExecutionBroker")
        self._permit_verifier = permit_verifier
        self._external_broker = external_broker
        self._clock = clock
        self._bindings: dict[str, AdapterBinding] = {}
        self._implementations: dict[str, AdapterCallable] = {}
        self._external_routes: dict[str, ExternalAdapterRoute] = {}
        self._skill_owner: dict[str, str] = {}

    def register(
        self,
        binding: AdapterBinding,
        implementation: AdapterCallable | ExternalAdapterRoute,
    ) -> None:
        if not isinstance(binding, AdapterBinding):
            raise TypeError("binding must be an AdapterBinding")
        if binding.adapter_id in self._bindings:
            raise ValueError(f"adapter already registered: {binding.adapter_id}")
        if binding.effect_class.is_external:
            if not isinstance(implementation, ExternalAdapterRoute):
                raise TypeError(
                    "external bindings require a non-executable ExternalAdapterRoute"
                )
        elif not callable(implementation):
            raise TypeError("local adapter implementation must be callable")
        collisions = sorted(
            skill for skill in binding.exact_skills if skill in self._skill_owner
        )
        if collisions:
            raise ValueError(
                "each Skill may have at most one exact adapter binding: "
                + ", ".join(collisions)
            )
        self._bindings[binding.adapter_id] = binding
        if isinstance(implementation, ExternalAdapterRoute):
            self._external_routes[binding.adapter_id] = implementation
        else:
            self._implementations[binding.adapter_id] = implementation
        for skill in binding.exact_skills:
            self._skill_owner[skill] = binding.adapter_id

    def binding_for(self, skill_name: str) -> AdapterBinding | None:
        adapter_id = self._skill_owner.get(skill_name)
        return self._bindings.get(adapter_id) if adapter_id else None

    def describe(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            MappingProxyType(
                {
                    "adapter_id": binding.adapter_id,
                    "version": binding.version,
                    "digest": binding.digest,
                    "exact_skills": binding.exact_skills,
                    "effect_class": binding.effect_class.value,
                }
            )
            for binding in sorted(self._bindings.values(), key=lambda item: item.adapter_id)
        )

    def invoke(
        self,
        *,
        skill_name: str,
        payload: Mapping[str, Any],
        tenant_scope: TenantScope,
        invocation_id: str,
        adapter_id: str | None,
        permit: InvocationPermit | None,
        risk_class: str,
        required_inputs: Sequence[str],
        required_outputs: Sequence[str],
        allowed_tools: Sequence[str],
        required_gates: Sequence[str],
        store: FoundryStore | None,
    ) -> AdapterResult:
        binding = self.binding_for(skill_name)
        if binding is None:
            return self._not_run(
                "REQUIRES_ADAPTER",
                skill_name,
                "no exact digest-bound adapter is registered",
            )
        if adapter_id != binding.adapter_id:
            return AdapterResult(
                status="REQUIRES_ADAPTER",
                outputs={
                    "skill": skill_name,
                    "execution_status": "NOT_RUN",
                    "required_adapter": binding.adapter_id,
                    "reason": "requested adapter identity does not match the exact binding",
                },
            )
        try:
            normalized_payload = canonical_value(payload)
            if not isinstance(normalized_payload, dict):
                raise TypeError("adapter payload must be an object")
            operation, declared_inputs = self._validate_adapter_payload(
                payload=normalized_payload,
                required_inputs=required_inputs,
            )
        except (TypeError, ValueError) as exc:
            return self._not_run(
                "NOT_RUN",
                skill_name,
                "adapter request binding is invalid: " + _safe_error_text(str(exc)),
            )
        external_claims: tuple[tuple[str, str], ...] = ()
        request: InvocationRequest | None = None
        route: ExternalAdapterRoute | None = None
        if binding.effect_class.is_external:
            if self._external_broker is None:
                return self._not_run(
                    "NOT_RUN",
                    skill_name,
                    "external execution requires an explicitly configured host-owned broker",
                )
            route = self._external_routes.get(binding.adapter_id)
            if route is None:
                return self._not_run(
                    "NOT_RUN", skill_name, "external adapter route is not registered"
                )
            if operation != route.operation:
                return self._not_run(
                    "NOT_RUN",
                    skill_name,
                    "requested operation does not match the exact host-owned broker route",
                )
            try:
                request = self._request(
                    binding=binding,
                    broker=self._external_broker,
                    route=route,
                    skill_name=skill_name,
                    payload=normalized_payload,
                    tenant_scope=tenant_scope,
                    invocation_id=invocation_id,
                    risk_class=risk_class,
                    operation=operation,
                    declared_inputs=declared_inputs,
                    allowed_tools=allowed_tools,
                    required_gates=required_gates,
                )
            except (TypeError, ValueError) as exc:
                return self._not_run(
                    "NOT_RUN",
                    skill_name,
                    "external request binding is invalid: " + _safe_error_text(str(exc)),
                )
            permit_error = self._validate_permit(
                permit=permit,
                binding=binding,
                tenant_scope=tenant_scope,
                request=request,
            )
            if permit_error:
                return self._not_run("NOT_RUN", skill_name, permit_error)
            verifier_error = self._verify_permit_authority(
                permit=permit,
                binding=binding,
                tenant_scope=tenant_scope,
                request=request,
            )
            if verifier_error:
                return self._not_run("NOT_RUN", skill_name, verifier_error)
            ledger_claims = self._claim_external_execution(
                permit=permit,
                request=request,
                tenant_scope=tenant_scope,
                store=store,
            )
            if isinstance(ledger_claims, str):
                return self._not_run("NOT_RUN", skill_name, ledger_claims)
            external_claims = ledger_claims

        if binding.effect_class.is_external:
            assert (
                permit is not None
                and store is not None
                and request is not None
                and route is not None
                and self._external_broker is not None
            )
            result = self._execute_external_binding(
                binding=binding,
                route=route,
                broker=self._external_broker,
                request=request,
                permit=permit,
                skill_name=skill_name,
                payload=normalized_payload,
                tenant_scope=tenant_scope,
                required_outputs=required_outputs,
            )
            return self._finalize_external_execution(
                result=result,
                claims=external_claims,
                tenant_scope=tenant_scope,
                store=store,
            )
        return self._execute_binding(
            binding=binding,
            skill_name=skill_name,
            payload=normalized_payload,
            tenant_scope=tenant_scope,
            invocation_id=invocation_id,
            required_outputs=required_outputs,
        )

    def _execute_binding(
        self,
        *,
        binding: AdapterBinding,
        skill_name: str,
        payload: Mapping[str, Any],
        tenant_scope: TenantScope,
        invocation_id: str,
        required_outputs: Sequence[str],
    ) -> AdapterResult:
        try:
            raw = self._implementations[binding.adapter_id](
                skill_name, payload, tenant_scope, invocation_id
            )
            normalized = canonical_value(raw)
        except Exception as exc:
            return AdapterResult(
                status="FAILED",
                outputs={
                    "skill": skill_name,
                    "execution_status": "FAILED",
                    "adapter_id": binding.adapter_id,
                    "effect_outcome": (
                        "UNKNOWN" if binding.effect_class.is_external else "NOT_APPLICABLE"
                    ),
                },
                error=(
                    f"adapter execution failed: {type(exc).__name__}: "
                    f"{_safe_error_text(str(exc))}"
                ),
                external_effects_performed=binding.effect_class.is_external,
            )
        return self._interpret_adapter_result(
            binding=binding,
            skill_name=skill_name,
            normalized=normalized,
            required_outputs=required_outputs,
            external_result_verified=False,
        )

    def _execute_external_binding(
        self,
        *,
        binding: AdapterBinding,
        route: ExternalAdapterRoute,
        broker: ExternalExecutionBroker,
        request: InvocationRequest,
        permit: InvocationPermit,
        skill_name: str,
        payload: Mapping[str, Any],
        tenant_scope: TenantScope,
        required_outputs: Sequence[str],
    ) -> AdapterResult:
        try:
            raw = broker.execute(route, binding, request, permit, payload, tenant_scope)
            normalized = canonical_value(raw)
        except Exception as exc:
            return AdapterResult(
                status="FAILED",
                outputs={
                    "skill": skill_name,
                    "execution_status": "FAILED",
                    "adapter_id": binding.adapter_id,
                    "broker_id": broker.broker_id,
                    "route_id": route.route_id,
                    "effect_outcome": "UNKNOWN",
                },
                error=(
                    f"external broker execution failed: {type(exc).__name__}: "
                    f"{_safe_error_text(str(exc))}"
                ),
                external_effects_performed=True,
            )
        verified = False
        if isinstance(normalized, dict) and normalized.get("status") == "SUCCEEDED":
            receipt = normalized.get("provider_receipt")
            if not isinstance(receipt, Mapping):
                return AdapterResult(
                    status="FAILED",
                    outputs={
                        "skill": skill_name,
                        "execution_status": "FAILED",
                        "adapter_id": binding.adapter_id,
                        "broker_id": broker.broker_id,
                        "route_id": route.route_id,
                        "effect_outcome": "UNKNOWN",
                    },
                    error="external success lacks a verifier-bound provider receipt",
                    external_effects_performed=True,
                )
            try:
                validate_digest(receipt.get("receipt_digest"), "provider_receipt.receipt_digest")
                if receipt.get("request_binding_digest") != request.binding_digest:
                    raise ValueError("provider receipt targets a different request")
                if receipt.get("outcome") != "CONFIRMED":
                    raise ValueError("provider receipt does not confirm the outcome")
                verified = broker.verify_result(
                    route, binding, request, permit, normalized, tenant_scope
                )
            except Exception as exc:
                return AdapterResult(
                    status="FAILED",
                    outputs={
                        "skill": skill_name,
                        "execution_status": "FAILED",
                        "adapter_id": binding.adapter_id,
                        "broker_id": broker.broker_id,
                        "route_id": route.route_id,
                        "effect_outcome": "UNKNOWN",
                    },
                    error=(
                        "external provider receipt verification failed: "
                        + _safe_error_text(str(exc))
                    ),
                    external_effects_performed=True,
                )
            if verified is not True:
                return AdapterResult(
                    status="FAILED",
                    outputs={
                        "skill": skill_name,
                        "execution_status": "FAILED",
                        "adapter_id": binding.adapter_id,
                        "broker_id": broker.broker_id,
                        "route_id": route.route_id,
                        "effect_outcome": "UNKNOWN",
                    },
                    error="trusted external result verifier denied the provider receipt",
                    external_effects_performed=True,
                )
        return self._interpret_adapter_result(
            binding=binding,
            skill_name=skill_name,
            normalized=normalized,
            required_outputs=required_outputs,
            external_result_verified=verified,
            broker=broker,
            route=route,
        )

    @staticmethod
    def _interpret_adapter_result(
        *,
        binding: AdapterBinding,
        skill_name: str,
        normalized: Any,
        required_outputs: Sequence[str],
        external_result_verified: bool,
        broker: ExternalExecutionBroker | None = None,
        route: ExternalAdapterRoute | None = None,
    ) -> AdapterResult:
        if not isinstance(normalized, dict):
            return AdapterResult(
                status="FAILED",
                outputs={
                    "skill": skill_name,
                    "execution_status": "FAILED",
                    "adapter_id": binding.adapter_id,
                    "effect_outcome": (
                        "UNKNOWN" if binding.effect_class.is_external else "NOT_APPLICABLE"
                    ),
                },
                error="adapter returned a non-object result",
                external_effects_performed=binding.effect_class.is_external,
            )
        status = normalized.get("status")
        if not isinstance(status, str) or status not in {
            "SUCCEEDED",
            "FAILED",
            "UNKNOWN",
            "INCONCLUSIVE",
        }:
            return AdapterResult(
                status="FAILED",
                outputs={
                    "skill": skill_name,
                    "execution_status": "FAILED",
                    "adapter_id": binding.adapter_id,
                    "effect_outcome": (
                        "UNKNOWN" if binding.effect_class.is_external else "NOT_APPLICABLE"
                    ),
                },
                error="adapter result has an unsupported or missing status",
                external_effects_performed=binding.effect_class.is_external,
            )
        if status == "SUCCEEDED":
            declared_outputs = tuple(sorted(set(required_outputs)))
            raw_outputs = normalized.get("outputs")
            if not isinstance(raw_outputs, Mapping):
                return AdapterResult(
                    status="FAILED",
                    outputs={
                        "skill": skill_name,
                        "execution_status": "FAILED",
                        "adapter_id": binding.adapter_id,
                        "effect_outcome": (
                            "UNKNOWN"
                            if binding.effect_class.is_external
                            else "NOT_APPLICABLE"
                        ),
                    },
                    error="successful adapter result is missing its declared outputs object",
                    external_effects_performed=binding.effect_class.is_external,
                )
            actual_outputs = set(raw_outputs)
            expected_outputs = set(declared_outputs)
            empty_outputs = sorted(
                name
                for name in expected_outputs & actual_outputs
                if raw_outputs[name] is None
                or raw_outputs[name] == ""
            )
            missing_outputs = sorted(expected_outputs - actual_outputs)
            extra_outputs = sorted(actual_outputs - expected_outputs)
            if missing_outputs or extra_outputs or empty_outputs:
                return AdapterResult(
                    status="FAILED",
                    outputs={
                        "skill": skill_name,
                        "execution_status": "FAILED",
                        "adapter_id": binding.adapter_id,
                        "effect_outcome": (
                            "UNKNOWN"
                            if binding.effect_class.is_external
                            else "NOT_APPLICABLE"
                        ),
                        "declared_output_validation": {
                            "missing": missing_outputs,
                            "extra": extra_outputs,
                            "empty": empty_outputs,
                        },
                    },
                    error="successful adapter result violates the exact declared output contract",
                    external_effects_performed=binding.effect_class.is_external,
                )
        certification_claim = normalized.get("certification_status")
        if certification_claim is not None and certification_claim != "NOT_CERTIFIED":
            return AdapterResult(
                status="FAILED",
                outputs={
                    "skill": skill_name,
                    "execution_status": "FAILED",
                    "adapter_id": binding.adapter_id,
                    "effect_outcome": (
                        "UNKNOWN" if binding.effect_class.is_external else "NOT_APPLICABLE"
                    ),
                },
                error="adapter result attempted to claim certification",
                external_effects_performed=binding.effect_class.is_external,
            )
        confirmed_external = (
            binding.effect_class.is_external
            and status == "SUCCEEDED"
            and external_result_verified
        )
        return AdapterResult(
            status=str(status),
            outputs={
                "skill": skill_name,
                "execution_status": str(status),
                "adapter_id": binding.adapter_id,
                "adapter_version": binding.version,
                "adapter_digest": binding.digest,
                "broker_id": None if broker is None else broker.broker_id,
                "broker_digest": None if broker is None else broker.digest,
                "route_id": None if route is None else route.route_id,
                "route_digest": None if route is None else route.digest,
                "effect_class": binding.effect_class.value,
                "effect_outcome": (
                    "CONFIRMED"
                    if confirmed_external
                    else "UNKNOWN"
                    if binding.effect_class.is_external
                    else "NOT_APPLICABLE"
                ),
                "result": normalized,
            },
            external_evidence_status=(
                "PROVIDER_RECEIPT_VERIFIED" if confirmed_external else "NOT_RUN"
            ),
            external_effects_performed=binding.effect_class.is_external,
        )

    def _request(
        self,
        *,
        binding: AdapterBinding,
        broker: ExternalExecutionBroker,
        route: ExternalAdapterRoute,
        skill_name: str,
        payload: Mapping[str, Any],
        tenant_scope: TenantScope,
        invocation_id: str,
        risk_class: str,
        operation: str,
        declared_inputs: Sequence[str],
        allowed_tools: Sequence[str],
        required_gates: Sequence[str],
    ) -> InvocationRequest:
        gates = tuple(sorted(set(required_gates)))
        tools = tuple(sorted(set(allowed_tools)))
        return InvocationRequest(
            skill_name=skill_name,
            operation=operation,
            payload_digest=canonical_digest(payload),
            tenant_id=tenant_scope.tenant_id,
            project_id=tenant_scope.project_id,
            actor_id=tenant_scope.actor_id,
            purpose=tenant_scope.purpose,
            environment_id=tenant_scope.environment_id,
            workspace_digest=tenant_scope.workspace_digest,
            revision_set_id=tenant_scope.revision_set_id,
            invocation_id=invocation_id,
            adapter_id=binding.adapter_id,
            adapter_version=binding.version,
            adapter_digest=binding.digest,
            broker_id=broker.broker_id,
            broker_version=broker.version,
            broker_digest=broker.digest,
            route_id=route.route_id,
            route_digest=route.digest,
            effect_class=binding.effect_class,
            risk_class=risk_class,
            required_inputs=tuple(declared_inputs),
            allowed_tools=tools,
            required_gates=gates,
        )

    @staticmethod
    def _validate_adapter_payload(
        *,
        payload: Mapping[str, Any],
        required_inputs: Sequence[str],
    ) -> tuple[str, tuple[str, ...]]:
        """Validate the common semantic request boundary for every adapter class.

        Local deterministic bindings are still executable code.  They must not
        bypass the exact Skill contract merely because they have no provider
        side effect.  The returned values are derived from the same canonical
        payload snapshot that is subsequently authorized and executed.
        """

        operation = payload.get("operation")
        if not isinstance(operation, str) or not operation:
            raise ValueError("adapter operation must be a non-empty string")
        extra_envelope_fields = sorted(set(payload) - {"operation", "inputs"})
        if extra_envelope_fields:
            raise ValueError(
                "adapter request has undeclared envelope fields: "
                + ", ".join(extra_envelope_fields)
            )
        declared_inputs = tuple(sorted(set(required_inputs)))
        supplied_inputs = payload.get("inputs")
        if not isinstance(supplied_inputs, Mapping):
            raise ValueError("adapter requires a typed inputs object")
        undeclared_inputs = tuple(sorted(set(supplied_inputs) - set(declared_inputs)))
        if undeclared_inputs:
            raise ValueError(
                "adapter request has undeclared inputs: " + ", ".join(undeclared_inputs)
            )
        missing_inputs = tuple(
            input_name
            for input_name in declared_inputs
            if input_name not in supplied_inputs
            or supplied_inputs[input_name] is None
            or supplied_inputs[input_name] == ""
            or supplied_inputs[input_name] == []
            or supplied_inputs[input_name] == {}
        )
        if missing_inputs:
            raise ValueError(
                "adapter is missing required inputs: " + ", ".join(missing_inputs)
            )
        return operation, declared_inputs

    @staticmethod
    def _not_run(status: str, skill_name: str, reason: str) -> AdapterResult:
        return AdapterResult(
            status=status,
            outputs={
                "skill": skill_name,
                "execution_status": "NOT_RUN",
                "reason": reason,
            },
            error=reason if status == "NOT_RUN" else None,
        )

    def _validate_permit(
        self,
        *,
        permit: InvocationPermit | None,
        binding: AdapterBinding,
        tenant_scope: TenantScope,
        request: InvocationRequest,
    ) -> str | None:
        if permit is None:
            return "explicit invocation-scoped authorization permit is required"
        expected = {
            "invocation_id": request.invocation_id,
            "adapter_id": binding.adapter_id,
            "adapter_version": binding.version,
            "adapter_digest": binding.digest,
            "broker_id": request.broker_id,
            "broker_version": request.broker_version,
            "broker_digest": request.broker_digest,
            "route_id": request.route_id,
            "route_digest": request.route_digest,
            "skill_name": request.skill_name,
            "tenant_id": tenant_scope.tenant_id,
            "project_id": tenant_scope.project_id,
            "actor_id": tenant_scope.actor_id,
            "effect_class": binding.effect_class,
            "operation": request.operation,
            "payload_digest": request.payload_digest,
            "purpose": request.purpose,
            "environment_id": request.environment_id,
            "workspace_digest": request.workspace_digest,
            "revision_set_id": request.revision_set_id,
            "authorized_tools": request.allowed_tools,
            "authorized_gates": request.required_gates,
        }
        for field_name, expected_value in expected.items():
            if getattr(permit, field_name) != expected_value:
                return f"permit {field_name} does not match the invocation"
        if permit.authorized is not True:
            return "permit is not authorized"
        now = int(self._clock())
        if permit.issued_at > now + 5:
            return "permit was issued in the future"
        if permit.issued_at < tenant_scope.issued_at:
            return "permit predates the host capability lease"
        if now >= permit.expires_at:
            return "permit has expired"
        if permit.expires_at > tenant_scope.expires_at:
            return "permit outlives the host capability lease"
        if permit.expires_at - permit.issued_at > 3600:
            return "permit lifetime exceeds the maximum"
        if not permit.policy_decision_id or not permit.policy_decision_digest:
            return "exact policy authorization is required"
        if not request.required_gates or not permit.gate_evidence_digest:
            return "all required gates need digest-bound authorization"
        if request.risk_class == "critical" and (
            permit.critical_approval_id is None
            or permit.critical_approval_digest is None
        ):
            return "critical execution requires independent approval binding"
        return None

    def _verify_permit_authority(
        self,
        *,
        permit: InvocationPermit | None,
        binding: AdapterBinding,
        tenant_scope: TenantScope,
        request: InvocationRequest,
    ) -> str | None:
        if permit is None:
            return "explicit invocation-scoped authorization permit is required"
        if self._permit_verifier is None:
            return "trusted permit verifier is not configured"
        try:
            verified = self._permit_verifier(permit, binding, tenant_scope, request)
        except Exception as exc:
            return f"trusted permit verification failed: {type(exc).__name__}"
        if verified is not True:
            return "trusted permit verifier denied authorization"
        return None

    @staticmethod
    def _claim_external_execution(
        *,
        permit: InvocationPermit | None,
        request: InvocationRequest,
        tenant_scope: TenantScope,
        store: FoundryStore | None,
    ) -> tuple[tuple[str, str], ...] | str:
        if permit is None:
            return "explicit invocation-scoped authorization permit is required"
        if store is None or store.path is None:
            return "durable external-execution store is required"
        ledger_request = {
            "schema_version": "elmos.foundry.external-execution-ledger.v1",
            "request": request.binding_document(),
            "request_binding_digest": request.binding_digest,
            "broker_id": request.broker_id,
            "broker_version": request.broker_version,
            "broker_digest": request.broker_digest,
            "route_id": request.route_id,
            "route_digest": request.route_digest,
            "permit_id": permit.permit_id,
            "authorization_id": permit.authorization_id,
            "nonce": permit.nonce,
            "policy_decision_id": permit.policy_decision_id,
            "policy_decision_digest": permit.policy_decision_digest,
            "authorized_tools": list(permit.authorized_tools),
            "authorized_gates": list(permit.authorized_gates),
            "gate_evidence_digest": permit.gate_evidence_digest,
            "critical_approval_id": permit.critical_approval_id,
            "critical_approval_digest": permit.critical_approval_digest,
            "permit_issued_at": permit.issued_at,
            "permit_expires_at": permit.expires_at,
        }
        claim_specs = (
            ("external-adapter-permit", permit.permit_id),
            ("external-adapter-invocation", request.invocation_id),
            ("external-adapter-nonce", permit.nonce),
        )
        claims: list[tuple[str, str]] = []
        for operation, idempotency_key in claim_specs:
            claim_request = dict(ledger_request)
            claim_request["claim_type"] = operation
            try:
                decision = store.begin_run(
                    tenant_scope,
                    operation,
                    idempotency_key,
                    claim_request,
                    run_id=_external_run_id(operation, idempotency_key),
                )
                if decision.replayed:
                    return f"external execution replay is blocked by {operation}"
                store.transition_run(
                    tenant_scope,
                    decision.record.run_id,
                    RunState.PENDING,
                    RunState.RUNNING,
                    reason="trusted-permit-and-request-binding-accepted",
                )
                claims.append((operation, decision.record.run_id))
            except IdempotencyConflict:
                return (
                    "external invocation idempotency binding conflicts with stored request"
                )
            except StoreError as exc:
                return f"durable replay claim failed: {type(exc).__name__}"
        return tuple(claims)

    @staticmethod
    def _finalize_external_execution(
        *,
        result: AdapterResult,
        claims: tuple[tuple[str, str], ...],
        tenant_scope: TenantScope,
        store: FoundryStore,
    ) -> AdapterResult:
        target = RunState.SUCCEEDED if result.status == "SUCCEEDED" else RunState.FAILED
        try:
            for _operation, run_id in claims:
                store.transition_run(
                    tenant_scope,
                    run_id,
                    RunState.RUNNING,
                    target,
                    reason=f"adapter-result-{result.status.lower()}",
                    response={
                        "status": result.status,
                        "outputs": dict(result.outputs),
                        "external_evidence_status": result.external_evidence_status,
                        "certification_status": result.certification_status,
                        "external_effects_performed": result.external_effects_performed,
                        "error": result.error,
                    },
                )
        except StoreError as exc:
            return AdapterResult(
                status="FAILED",
                outputs={
                    "execution_status": "FAILED",
                    "effect_outcome": "UNKNOWN",
                    "reason": "external execution completed but durable finalization failed",
                },
                external_evidence_status="NOT_RUN",
                external_effects_performed=result.external_effects_performed,
                error=f"durable finalization failed: {type(exc).__name__}",
            )
        return result


def _safe_error_text(value: str) -> str:
    """Bound adapter-controlled exception text before evidence hashing/logging."""

    return "".join(
        character if ord(character) >= 0x20 and ord(character) != 0x7F else "?"
        for character in value
    )[:512]


def _external_run_id(claim_type: str, claim_value: str) -> str:
    return "external-" + canonical_digest(
        {"claim_type": claim_type, "claim_value": claim_value}
    ).removeprefix("sha256:")


__all__ = [
    "AdapterBinding",
    "AdapterRegistry",
    "AdapterResult",
    "EffectClass",
    "ExternalAdapterRoute",
    "ExternalExecutionBroker",
    "ExternalBrokerExecutor",
    "ExternalResultVerifier",
    "InvocationPermit",
    "InvocationRequest",
    "PermitVerifier",
]
