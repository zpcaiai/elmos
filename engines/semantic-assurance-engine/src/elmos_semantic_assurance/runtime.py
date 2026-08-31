"""Fail-closed runtime for the 132 exact semantic-assurance Skills."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .adapters import AdapterSet, ExecutionAdapter
from .canonical import digest_value
from .contracts import Operation, SkillRequest, TrustedIdentity
from .handlers import HandlerContext, execute_binding
from .registry import SkillBinding, SkillRegistry
from .store import SemanticAssuranceStore

EXECUTE_ROLE = "semantic-assurance:execute"


class AuthorizationError(PermissionError):
    """Raised when trusted host identity does not authorize an invocation."""


@dataclass(frozen=True, slots=True)
class RuntimeStatus:
    registered_skills: int
    exact_handlers: int
    contract_digest: str
    package_blockers: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": "elmos-semantic-assurance-engine",
            "version": "1.0.0",
            "status": "BLOCKED_EXTERNAL_EVIDENCE_REQUIRED",
            "registeredSkills": self.registered_skills,
            "exactHandlers": self.exact_handlers,
            "compiledContractDigest": self.contract_digest,
            "implementationState": "RUNTIME_CODE_COMPLETE",
            "localCapabilityState": "CODE_COMPLETE_LOCAL_BOUNDED",
            "externalEvidenceStatus": "NOT_RUN",
            "certificationStatus": "NOT_CERTIFIED",
            "readiness": "BLOCKED_EXTERNAL_EVIDENCE_REQUIRED",
            "packageBlockers": [dict(item) for item in self.package_blockers],
        }


ExactHandler = Callable[[Mapping[str, Any], TrustedIdentity], dict[str, Any]]


class SemanticAssuranceRuntime:
    """Dispatch only digest-bound, allowlisted Skills through typed operations.

    The archive never selects code, commands, providers or credentials.  Every
    source Skill gets an exact callable installed from the validated compiled
    contract; there is deliberately no unknown-name or unknown-operation
    fallback.
    """

    def __init__(
        self,
        *,
        registry: SkillRegistry | None = None,
        store: SemanticAssuranceStore | None = None,
        adapters: AdapterSet | None = None,
        max_request_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        if max_request_bytes < 1024 or max_request_bytes > 16 * 1024 * 1024:
            raise ValueError("max_request_bytes must be between 1 KiB and 16 MiB")
        self.registry = registry or SkillRegistry()
        self.store = store or SemanticAssuranceStore()
        self.adapters = adapters or AdapterSet()
        self.max_request_bytes = max_request_bytes
        self._handlers: dict[str, ExactHandler] = {}
        for binding_document in self.registry.list():
            binding = self.registry.get(binding_document["sourceName"])
            if binding.installed_name in self._handlers:
                raise RuntimeError(f"duplicate exact handler: {binding.installed_name}")
            self._handlers[binding.installed_name] = self._bind(binding)
        if len(self._handlers) != self.registry.count:
            raise RuntimeError("exact handler registry is incomplete")

    @property
    def handler_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(
            registered_skills=self.registry.count,
            exact_handlers=len(self._handlers),
            contract_digest=self.registry.contract_digest,
            package_blockers=self.registry.package_blockers,
        )

    def dispatch(
        self,
        installed_name: str,
        request: Mapping[str, Any],
        identity: TrustedIdentity,
    ) -> dict[str, Any]:
        try:
            handler = self._handlers[installed_name]
        except KeyError as exc:
            raise KeyError(
                f"unknown installed semantic-assurance Skill: {installed_name}"
            ) from exc
        return handler(request, identity)

    def _bind(self, binding: SkillBinding) -> ExactHandler:
        def exact_handler(
            raw_request: Mapping[str, Any],
            identity: TrustedIdentity,
        ) -> dict[str, Any]:
            return self._execute(binding, raw_request, identity)

        exact_handler.__name__ = binding.handler_id
        exact_handler.__qualname__ = (
            f"SemanticAssuranceRuntime.{binding.handler_id}"
        )
        return exact_handler

    def _execute(
        self,
        binding: SkillBinding,
        raw_request: Mapping[str, Any],
        identity: TrustedIdentity,
    ) -> dict[str, Any]:
        if EXECUTE_ROLE not in identity.roles:
            raise AuthorizationError(
                f"trusted identity lacks required role {EXECUTE_ROLE}"
            )
        if identity.authorization_ref is None:
            raise AuthorizationError(
                "trusted identity requires an authorization reference"
            )
        request = SkillRequest.parse(
            raw_request,
            identity,
            max_bytes=self.max_request_bytes,
        )
        if "artifact-write" not in request.allowed_effects:
            raise AuthorizationError(
                "artifact-write must be explicitly authorized for durable execution"
            )
        identity_document = {
            "tenantId": identity.tenant_id,
            "projectId": identity.project_id,
            "actorId": identity.actor_id,
            "roles": sorted(identity.roles),
            "authorizationRef": identity.authorization_ref,
        }
        request_digest = digest_value(
            {
                "request": request.to_digest_document(binding.source_name),
                "trustedIdentity": identity_document,
            }
        )
        replay = self.store.replay(
            request.scope,
            binding.source_name,
            request.idempotency_key,
            request_digest,
        )
        if replay is not None:
            return replay
        context = HandlerContext(
            binding=binding,
            request=request,
            identity=identity,
            request_digest=request_digest,
            store=self.store,
            adapter=self._adapter_for(binding.operation),
        )
        outcome, artifact_contents = execute_binding(context)
        response = {
            "schemaVersion": "elmos.semantic-assurance.response/v1",
            "packageId": "elmos-semantic-assurance-expansion-skills-v1.0.0",
            "requestDigest": request_digest,
            "trustedActorId": identity.actor_id,
            "scopeDigest": digest_value(request.scope.to_dict()),
            "compiledContractDigest": self.registry.contract_digest,
            **outcome.to_dict(),
        }
        return self.store.complete(
            request.scope,
            binding.source_name,
            request.idempotency_key,
            request.subject_id,
            request_digest,
            response,
            artifact_contents,
            actor_id=identity.actor_id,
        )

    def _adapter_for(self, operation: Operation) -> ExecutionAdapter | None:
        if operation is Operation.NATIVE_EXECUTION:
            return self.adapters.native
        if operation is Operation.FORMAL_EXECUTION:
            return self.adapters.formal
        if operation is Operation.FUZZ_EXECUTION:
            return self.adapters.fuzz
        return None


__all__ = [
    "EXECUTE_ROLE",
    "AuthorizationError",
    "RuntimeStatus",
    "SemanticAssuranceRuntime",
]
