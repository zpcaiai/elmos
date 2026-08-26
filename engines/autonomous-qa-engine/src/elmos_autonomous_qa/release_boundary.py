"""Fail-closed preparation contracts for external QA and release evidence.

The local engine may describe an external execution or certification review, but
it is not an external runner, signer, verifier, or production authority.  This
module deliberately contains no subprocess, network, filesystem, or provider
calls.  A trusted service may later consume the immutable plans and attach raw
receipts through its own authenticated, independently verifiable boundary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .adapters import AdapterContractError, Capability, UnsupportedAdapterError, adapter_for, capability_plan
from .contracts import ContractError, digest_json, require_resource_id, require_text


_SHA256_PREFIX = "sha256:"
_MAX_TIMEOUT_SECONDS = 3_600
_MAX_OUTPUT_BYTES = 100 * 1024 * 1024
_EXTERNAL_EVIDENCE_ROLES = (
    "provider_identity_attestation",
    "toolchain_identity",
    "raw_exit_status",
    "raw_stdout_stderr_digests",
    "source_artifact_binding",
    "durable_idempotency_receipt",
    "independent_verifier_receipt",
)
_CERTIFICATION_EVIDENCE_ROLES = (
    "project_manifest_signature",
    "evidence_manifest_signature",
    "trusted_signer_resolution",
    "independent_corpus",
    "independent_verification",
    "external_validation",
    "scoped_authorization",
    "concurrency_fence",
)


class ExternalProvider(Protocol):
    """Code-level provider seam owned by a trusted service assembly.

    Implementations are intentionally not callable through this module's JSON
    contracts.  The protocol is a typed seam for a separately governed runner;
    this package only validates its descriptor and prepares a request.
    """

    descriptor: "ExternalProviderDescriptor"

    def execute(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        """Execute through an independently governed provider (never called here)."""


@dataclass(frozen=True)
class ExternalProviderDescriptor:
    provider_key: str
    provider_version: str
    attestation_digest: str
    capabilities: frozenset[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_key": self.provider_key,
            "provider_version": self.provider_version,
            "attestation_digest": self.attestation_digest,
            "capabilities": sorted(self.capabilities),
        }


class ExternalProviderRegistry:
    """Immutable-by-default provider registry for trusted service assembly.

    The default registry is empty.  Registration is a code-level dependency
    injection point, not a caller-controlled operation.  Providers still do not
    run here; a trusted runner must own execution, raw evidence, and receipts.
    """

    def __init__(self, providers: Sequence[ExternalProvider] = ()) -> None:
        normalized: dict[str, ExternalProvider] = {}
        for provider in providers:
            descriptor = getattr(provider, "descriptor", None)
            if not isinstance(descriptor, ExternalProviderDescriptor):
                raise ContractError("external provider descriptor is required")
            _validate_provider_descriptor(descriptor)
            if descriptor.provider_key in normalized:
                raise ContractError("external provider keys must be unique")
            normalized[descriptor.provider_key] = provider
        self._providers = normalized

    def resolve(self, provider_key: str) -> ExternalProvider | None:
        return self._providers.get(provider_key)

    def describe(self) -> tuple[ExternalProviderDescriptor, ...]:
        return tuple(
            provider.descriptor
            for provider in sorted(
                self._providers.values(), key=lambda item: item.descriptor.provider_key
            )
        )


EXTERNAL_PROVIDER_REGISTRY = ExternalProviderRegistry()


def _exact_object(
    value: Any,
    field: str,
    *,
    allowed: frozenset[str],
    required: frozenset[str] = frozenset(),
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        raise ContractError(f"{field} must be an exact string-keyed object")
    unknown = sorted(set(value).difference(allowed))
    missing = sorted(set(required).difference(value))
    if unknown:
        raise ContractError(f"{field} has unsupported fields: {unknown}")
    if missing:
        raise ContractError(f"{field} is missing required fields: {missing}")
    return value


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.startswith(_SHA256_PREFIX):
        raise ContractError(f"{field} must be a lowercase sha256 digest")
    suffix = value[len(_SHA256_PREFIX) :]
    if len(suffix) != 64 or any(char not in "0123456789abcdef" for char in suffix):
        raise ContractError(f"{field} must be a lowercase sha256 digest")
    return value


def _identity(value: Any, field: str) -> str:
    return require_resource_id(value, field)


def _fence(value: Any, *, run_id: str, holder_id: str) -> dict[str, Any]:
    exact = _exact_object(
        value,
        "fence",
        allowed=frozenset({"resource_id", "epoch", "holder_id"}),
        required=frozenset({"resource_id", "epoch", "holder_id"}),
    )
    resource_id = _identity(exact["resource_id"], "fence.resource_id")
    epoch = exact["epoch"]
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 1:
        raise ContractError("fence.epoch must be a positive integer")
    fence_holder = _identity(exact["holder_id"], "fence.holder_id")
    if resource_id != run_id:
        raise ContractError("fence.resource_id must equal run_id")
    if fence_holder != holder_id:
        raise ContractError("fence.holder_id must equal executor_id")
    return {"resource_id": resource_id, "epoch": epoch, "holder_id": fence_holder}


def _parameters(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or any(
        type(key) is not str or not isinstance(item, str) for key, item in value.items()
    ):
        raise ContractError("parameters must be a string-to-string object")
    return {key: value[key] for key in sorted(value)}


def _validate_provider_descriptor(descriptor: ExternalProviderDescriptor) -> None:
    _identity(descriptor.provider_key, "provider.provider_key")
    require_text(descriptor.provider_version, "provider.provider_version", maximum=128)
    _digest(descriptor.attestation_digest, "provider.attestation_digest")
    if not descriptor.capabilities:
        raise ContractError("provider.capabilities may not be empty")
    for capability in descriptor.capabilities:
        require_resource_id(capability, "provider.capabilities[]")


def _base_outputs(
    *,
    request_digest: str,
    idempotency_key: str,
    fence: Mapping[str, Any],
    external_status: str = "NOT_RUN",
) -> dict[str, Any]:
    return {
        "request_digest": request_digest,
        "idempotency_key": idempotency_key,
        "durable_receipt": "NOT_RUN",
        "external_execution": external_status,
        "external_evidence": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "caller_assertions_accepted": False,
        "provider_invoked": False,
        "command_execution_performed": False,
        "network_calls_performed": False,
        "file_writes_performed": False,
        "fence": dict(fence),
        "fence_validation": "LOCAL_STRUCTURAL_ONLY",
        "stale_fence_results_rejected": True,
    }


def prepare_external_execution(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Prepare an exact external runner request without executing it."""

    request = _exact_object(
        inputs,
        "external execution request",
        allowed=frozenset(
            {
                "tenant_id",
                "project_id",
                "run_id",
                "idempotency_key",
                "adapter_key",
                "capability",
                "parameters",
                "source_digest",
                "artifact_digest",
                "authorization_ref",
                "actor_id",
                "executor_id",
                "provider_key",
                "provider_version",
                "provider_attestation_digest",
                "timeout_seconds",
                "output_limit_bytes",
                "network_policy",
                "fence",
            }
        ),
        required=frozenset(
            {
                "tenant_id",
                "project_id",
                "run_id",
                "idempotency_key",
                "adapter_key",
                "capability",
                "parameters",
                "source_digest",
                "artifact_digest",
                "authorization_ref",
                "actor_id",
                "executor_id",
                "provider_key",
                "provider_version",
                "provider_attestation_digest",
                "timeout_seconds",
                "output_limit_bytes",
                "network_policy",
                "fence",
            }
        ),
    )
    tenant_id = _identity(request["tenant_id"], "tenant_id")
    project_id = _identity(request["project_id"], "project_id")
    run_id = _identity(request["run_id"], "run_id")
    idempotency_key = _identity(request["idempotency_key"], "idempotency_key")
    adapter_key = _identity(request["adapter_key"], "adapter_key")
    capability_name = _identity(request["capability"], "capability")
    parameters = _parameters(request["parameters"])
    source_digest = _digest(request["source_digest"], "source_digest")
    artifact_digest = _digest(request["artifact_digest"], "artifact_digest")
    authorization_ref = _identity(request["authorization_ref"], "authorization_ref")
    actor_id = _identity(request["actor_id"], "actor_id")
    executor_id = _identity(request["executor_id"], "executor_id")
    provider_key = _identity(request["provider_key"], "provider_key")
    provider_version = require_text(
        request["provider_version"], "provider_version", maximum=128
    )
    provider_attestation_digest = _digest(
        request["provider_attestation_digest"], "provider_attestation_digest"
    )
    timeout_seconds = request["timeout_seconds"]
    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or timeout_seconds < 1
        or timeout_seconds > _MAX_TIMEOUT_SECONDS
    ):
        raise ContractError("timeout_seconds must be an integer from 1 to 3600")
    output_limit_bytes = request["output_limit_bytes"]
    if (
        not isinstance(output_limit_bytes, int)
        or isinstance(output_limit_bytes, bool)
        or output_limit_bytes < 1
        or output_limit_bytes > _MAX_OUTPUT_BYTES
    ):
        raise ContractError("output_limit_bytes exceeds the bounded runner contract")
    network_policy = request["network_policy"]
    if network_policy not in {"DENY_ALL", "ALLOWLIST_ONLY"}:
        raise ContractError("network_policy must be DENY_ALL or ALLOWLIST_ONLY")
    fence = _fence(request["fence"], run_id=run_id, holder_id=executor_id)

    normalized = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "run_id": run_id,
        "idempotency_key": idempotency_key,
        "adapter_key": adapter_key,
        "capability": capability_name,
        "parameters": parameters,
        "source_digest": source_digest,
        "artifact_digest": artifact_digest,
        "authorization_ref": authorization_ref,
        "actor_id": actor_id,
        "executor_id": executor_id,
        "provider_key": provider_key,
        "provider_version": provider_version,
        "provider_attestation_digest": provider_attestation_digest,
        "timeout_seconds": timeout_seconds,
        "output_limit_bytes": output_limit_bytes,
        "network_policy": network_policy,
        "fence": fence,
    }
    try:
        adapter = adapter_for(adapter_key)
    except UnsupportedAdapterError:
        return {
            "state": "NOT_APPLICABLE",
            "code": "UNSUPPORTED_ADAPTER",
            "outputs": {
                **_base_outputs(
                    request_digest=digest_json(normalized),
                    idempotency_key=idempotency_key,
                    fence=fence,
                ),
                "supported": False,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "required_external_evidence": list(_EXTERNAL_EVIDENCE_ROLES),
            },
            "implementation_state": "LOCAL_VALIDATED",
        }
    try:
        capability = Capability(capability_name)
    except ValueError:
        return {
            "state": "NOT_APPLICABLE",
            "code": "UNSUPPORTED_ADAPTER_CAPABILITY",
            "outputs": {
                **_base_outputs(
                    request_digest=digest_json(normalized),
                    idempotency_key=idempotency_key,
                    fence=fence,
                ),
                "supported": False,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "required_external_evidence": list(_EXTERNAL_EVIDENCE_ROLES),
            },
            "implementation_state": "LOCAL_VALIDATED",
        }
    try:
        commands = capability_plan(adapter_key, capability, parameters=parameters).require_commands()
    except AdapterContractError:
        return {
            "state": "NOT_APPLICABLE",
            "code": "UNSUPPORTED_ADAPTER_CAPABILITY",
            "outputs": {
                **_base_outputs(
                    request_digest=digest_json(normalized),
                    idempotency_key=idempotency_key,
                    fence=fence,
                ),
                "supported": False,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "required_external_evidence": list(_EXTERNAL_EVIDENCE_ROLES),
            },
            "implementation_state": "LOCAL_VALIDATED",
        }
    provider = EXTERNAL_PROVIDER_REGISTRY.resolve(provider_key)
    provider_registered = provider is not None
    provider_descriptor = provider.descriptor.as_dict() if provider else None
    provider_matches = bool(
        provider
        and provider.descriptor.provider_version == provider_version
        and provider.descriptor.attestation_digest == provider_attestation_digest
        and capability.value in provider.descriptor.capabilities
    )
    plan = {
        **normalized,
        "commands": [
            {"argv": list(command.argv), "cwd": command.cwd, "shell": False}
            for command in commands
        ],
        "required_external_evidence": list(_EXTERNAL_EVIDENCE_ROLES),
        "execution_status": "NOT_RUN",
        "provider_registered": provider_registered,
        "provider_descriptor": provider_descriptor,
        "provider_matches": provider_matches,
    }
    plan_digest = digest_json(plan)
    output = {
        **_base_outputs(
            request_digest=plan_digest,
            idempotency_key=idempotency_key,
            fence=fence,
        ),
        "tenant_id": tenant_id,
        "project_id": project_id,
        "adapter_key": adapter.key,
        "capability": capability.value,
        "supported": True,
        "provider_key": provider_key,
        "provider_registered": provider_registered,
        "provider_attestation_validated": provider_matches,
        "plan": plan,
        "plan_digest": plan_digest,
        "required_external_evidence": list(_EXTERNAL_EVIDENCE_ROLES),
    }
    code = "EXTERNAL_EXECUTION_NOT_RUN"
    if not provider_registered:
        code = "EXTERNAL_PROVIDER_NOT_REGISTERED"
    elif not provider_matches:
        code = "EXTERNAL_PROVIDER_ATTESTATION_MISMATCH"
    return {
        "state": "NOT_RUN",
        "code": code,
        "outputs": output,
        "implementation_state": "EXTERNAL_ADAPTER_REQUIRED",
    }


def prepare_independent_verification(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Prepare a verifier request; no verifier, corpus, or signature is invoked."""

    request = _exact_object(
        inputs,
        "independent verification request",
        allowed=frozenset(
            {
                "tenant_id",
                "project_id",
                "run_id",
                "idempotency_key",
                "evidence_manifest_digest",
                "raw_evidence_digest",
                "independent_corpus_digest",
                "authorization_ref",
                "executor_id",
                "verifier_id",
                "verifier_scope",
                "fence",
            }
        ),
        required=frozenset(
            {
                "tenant_id",
                "project_id",
                "run_id",
                "idempotency_key",
                "evidence_manifest_digest",
                "raw_evidence_digest",
                "independent_corpus_digest",
                "authorization_ref",
                "executor_id",
                "verifier_id",
                "verifier_scope",
                "fence",
            }
        ),
    )
    tenant_id = _identity(request["tenant_id"], "tenant_id")
    project_id = _identity(request["project_id"], "project_id")
    run_id = _identity(request["run_id"], "run_id")
    idempotency_key = _identity(request["idempotency_key"], "idempotency_key")
    evidence_manifest_digest = _digest(
        request["evidence_manifest_digest"], "evidence_manifest_digest"
    )
    raw_evidence_digest = _digest(request["raw_evidence_digest"], "raw_evidence_digest")
    independent_corpus_digest = _digest(
        request["independent_corpus_digest"], "independent_corpus_digest"
    )
    authorization_ref = _identity(request["authorization_ref"], "authorization_ref")
    executor_id = _identity(request["executor_id"], "executor_id")
    verifier_id = _identity(request["verifier_id"], "verifier_id")
    if executor_id == verifier_id:
        raise ContractError("executor_id and verifier_id must be different identities")
    raw_scope = request["verifier_scope"]
    if not isinstance(raw_scope, list) or not raw_scope:
        raise ContractError("verifier_scope must be a non-empty resource array")
    verifier_scope = sorted({_identity(item, "verifier_scope[]") for item in raw_scope})
    fence = _fence(request["fence"], run_id=run_id, holder_id=executor_id)
    normalized = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "run_id": run_id,
        "idempotency_key": idempotency_key,
        "evidence_manifest_digest": evidence_manifest_digest,
        "raw_evidence_digest": raw_evidence_digest,
        "independent_corpus_digest": independent_corpus_digest,
        "authorization_ref": authorization_ref,
        "executor_id": executor_id,
        "verifier_id": verifier_id,
        "verifier_scope": verifier_scope,
        "fence": fence,
    }
    request_digest = digest_json(normalized)
    return {
        "state": "PARTIAL",
        "code": "INDEPENDENT_VERIFICATION_PLAN_READY",
        "outputs": {
            "request_digest": request_digest,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "run_id": run_id,
            "idempotency_key": idempotency_key,
            "executor_id": executor_id,
            "verifier_id": verifier_id,
            "verifier_scope": verifier_scope,
            "authorization_ref": authorization_ref,
            "fence": fence,
            "fence_validation": "LOCAL_STRUCTURAL_ONLY",
            "stale_fence_results_rejected": True,
            "independent_verification": "NOT_RUN",
            "independent_verifier_receipt": "NOT_RUN",
            "external_evidence": "NOT_RUN",
            "production_certification": "NOT_CERTIFIED",
            "caller_assertions_accepted": False,
            "decision": "READY_FOR_EXTERNAL_GATE",
            "required_evidence_roles": [
                "independent_corpus_digest",
                "raw_evidence_digest",
                "independent_verifier_identity",
                "independent_verifier_receipt",
                "authorization_receipt",
                "concurrency_fence_receipt",
            ],
        },
        "implementation_state": "LOCAL_VALIDATED",
    }


def prepare_certification_review(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Prepare a B37 review package while permanently refusing certification."""

    request = _exact_object(
        inputs,
        "certification review request",
        allowed=frozenset(
            {
                "tenant_id",
                "project_id",
                "run_id",
                "idempotency_key",
                "gate_decision",
                "gate_report_digest",
                "project_manifest_digest",
                "evidence_manifest_digest",
                "independent_corpus_digest",
                "authorization_ref",
                "executor_id",
                "verifier_id",
                "signer_id",
                "trust_store_digest",
                "fence",
            }
        ),
        required=frozenset(
            {
                "tenant_id",
                "project_id",
                "run_id",
                "idempotency_key",
                "gate_decision",
                "gate_report_digest",
                "project_manifest_digest",
                "evidence_manifest_digest",
                "independent_corpus_digest",
                "authorization_ref",
                "executor_id",
                "verifier_id",
                "signer_id",
                "trust_store_digest",
                "fence",
            }
        ),
    )
    tenant_id = _identity(request["tenant_id"], "tenant_id")
    project_id = _identity(request["project_id"], "project_id")
    run_id = _identity(request["run_id"], "run_id")
    idempotency_key = _identity(request["idempotency_key"], "idempotency_key")
    gate_decision = require_text(request["gate_decision"], "gate_decision", maximum=64)
    gate_report_digest = _digest(request["gate_report_digest"], "gate_report_digest")
    project_manifest_digest = _digest(
        request["project_manifest_digest"], "project_manifest_digest"
    )
    evidence_manifest_digest = _digest(
        request["evidence_manifest_digest"], "evidence_manifest_digest"
    )
    independent_corpus_digest = _digest(
        request["independent_corpus_digest"], "independent_corpus_digest"
    )
    authorization_ref = _identity(request["authorization_ref"], "authorization_ref")
    executor_id = _identity(request["executor_id"], "executor_id")
    verifier_id = _identity(request["verifier_id"], "verifier_id")
    signer_id = _identity(request["signer_id"], "signer_id")
    if len({executor_id, verifier_id, signer_id}) != 3:
        raise ContractError("executor, verifier, and signer identities must be distinct")
    trust_store_digest = _digest(request["trust_store_digest"], "trust_store_digest")
    fence = _fence(request["fence"], run_id=run_id, holder_id=executor_id)
    normalized = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "run_id": run_id,
        "idempotency_key": idempotency_key,
        "gate_decision": gate_decision,
        "gate_report_digest": gate_report_digest,
        "project_manifest_digest": project_manifest_digest,
        "evidence_manifest_digest": evidence_manifest_digest,
        "independent_corpus_digest": independent_corpus_digest,
        "authorization_ref": authorization_ref,
        "executor_id": executor_id,
        "verifier_id": verifier_id,
        "signer_id": signer_id,
        "trust_store_digest": trust_store_digest,
        "fence": fence,
    }
    request_digest = digest_json(normalized)
    ready = gate_decision == "READY_FOR_EXTERNAL_GATE"
    return {
        "state": "SUCCEEDED" if ready else "BLOCKED",
        "code": "CERTIFICATION_REVIEW_READY" if ready else "QUALITY_GATE_NOT_READY",
        "outputs": {
            "decision": "READY_FOR_EXTERNAL_GATE" if ready else "BLOCKED",
            "request_digest": request_digest,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "run_id": run_id,
            "idempotency_key": idempotency_key,
            "executor_id": executor_id,
            "verifier_id": verifier_id,
            "signer_id": signer_id,
            "fence": fence,
            "fence_validation": "LOCAL_STRUCTURAL_ONLY",
            "stale_fence_results_rejected": True,
            "required_evidence_roles": list(_CERTIFICATION_EVIDENCE_ROLES),
            "external_validation": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "trusted_external_receipt": "NOT_RUN",
            "production_certification": "NOT_CERTIFIED",
            "certified": False,
            "caller_certification_assertions_accepted": False,
            "certification_boundary": (
                "Only an authorized independent external authority may validate "
                "signed evidence and issue a production certificate."
            ),
        },
        "implementation_state": "LOCAL_VALIDATED",
    }
