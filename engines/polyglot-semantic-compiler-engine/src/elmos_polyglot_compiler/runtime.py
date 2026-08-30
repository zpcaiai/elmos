"""Exact allowlisted runtime for all 300 Polyglot Semantic Skills."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .catalog import CompiledCatalog, load_catalog
from .contracts import (
    AuthorityError,
    ContractError,
    ExecutionAuthority,
    IdempotencyConflict,
    RuntimeRequest,
    digest_json,
)
from .evidence import ContentAddressedArtifactStore
from .external import ExternalRunner
from .handlers import execute_compiled_skill
from .models import (
    CapabilityMode,
    CertificationState,
    EvidenceState,
    ExecutionState,
    SkillDefinition,
)
from .store import SqliteExecutionStore


class SkillRuntimeError(ValueError):
    pass


_RUNTIME_CONTRACT_VERSION = "elmos.polyglot-runtime-contract.v2"


SkillHandler = Callable[
    [RuntimeRequest, ExecutionAuthority, CompiledCatalog], Mapping[str, Any]
]


@dataclass(frozen=True)
class HandlerBinding:
    ordinal: int
    source_id: str
    skill: str
    handler_id: str
    batch: str
    layer: str
    operation_family: str
    capability_mode: str
    handler: SkillHandler

    def to_dict(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "source_id": self.source_id,
            "skill": self.skill,
            "handler_id": self.handler_id,
            "batch": self.batch,
            "layer": self.layer,
            "operation_family": self.operation_family,
            "capability_mode": self.capability_mode,
        }


def _make_handler(
    definition: SkillDefinition, external_runner: ExternalRunner | None = None
) -> SkillHandler:
    def handler(
        request: RuntimeRequest,
        authority: ExecutionAuthority,
        catalog: CompiledCatalog,
    ) -> Mapping[str, Any]:
        return execute_compiled_skill(
            definition,
            request,
            authority,
            catalog,
            external_runner=external_runner,
        )

    handler.__name__ = "execute_" + definition.name.replace("-", "_")
    handler.__qualname__ = handler.__name__
    handler.__polyglot_source_id__ = definition.source_id  # type: ignore[attr-defined]
    return handler


def build_registry(
    catalog: CompiledCatalog, external_runner: ExternalRunner | None = None
) -> Mapping[str, HandlerBinding]:
    registry: dict[str, HandlerBinding] = {}
    for definition in catalog.skills:
        handler = _make_handler(definition, external_runner)
        registry[definition.name] = HandlerBinding(
            ordinal=definition.ordinal,
            source_id=definition.source_id,
            skill=definition.name,
            handler_id=handler.__name__,
            batch=definition.batch.value,
            layer=definition.layer,
            operation_family=definition.operation_family,
            capability_mode=definition.capability_mode.value,
            handler=handler,
        )
    return MappingProxyType(registry)


def validate_registry(
    catalog: CompiledCatalog, registry: Mapping[str, HandlerBinding]
) -> None:
    bindings = list(registry.values())
    if len(bindings) != 300 or tuple(registry) != tuple(item.name for item in catalog.skills):
        raise SkillRuntimeError("runtime registry must bind the exact 300 catalog Skills")
    if tuple(item.ordinal for item in bindings) != tuple(range(1, 301)):
        raise SkillRuntimeError("runtime registry ordinals must be contiguous")
    if len({item.source_id for item in bindings}) != 300:
        raise SkillRuntimeError("runtime source IDs must be unique")
    if len({item.handler_id for item in bindings}) != 300:
        raise SkillRuntimeError("every Skill must have a unique handler ID")
    if len({id(item.handler) for item in bindings}) != 300:
        raise SkillRuntimeError("every Skill must own a distinct callable")
    for definition, binding in zip(catalog.skills, bindings, strict=True):
        if (
            binding.skill != definition.name
            or binding.source_id != definition.source_id
            or binding.batch != definition.batch.value
            or binding.layer != definition.layer
            or binding.operation_family != definition.operation_family
            or binding.capability_mode != definition.capability_mode.value
            or binding.handler.__name__ != binding.handler_id
            or getattr(binding.handler, "__polyglot_source_id__", None)
            != definition.source_id
        ):
            raise SkillRuntimeError(f"runtime binding drift detected: {definition.name}")


def _validate_operation(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "state",
        "code",
        "implementation_state",
        "outputs",
        "unavailable",
        "warnings",
        "external_effects_performed",
        "external_evidence",
        "certification",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ContractError("handler output fields differ from the exact runtime contract")
    if value.get("state") not in {
        item.value for item in ExecutionState
    }:
        raise ContractError("handler output state is unsupported")
    if not isinstance(value.get("code"), str) or not value.get("code"):
        raise ContractError("handler output code is invalid")
    if not isinstance(value.get("outputs"), Mapping):
        raise ContractError("handler outputs must be an object")
    if not isinstance(value.get("unavailable"), list) or any(
        not isinstance(item, str) for item in value["unavailable"]
    ):
        raise ContractError("handler unavailable values must be a string array")
    if not isinstance(value.get("warnings"), list) or any(
        not isinstance(item, str) for item in value["warnings"]
    ):
        raise ContractError("handler warnings must be a string array")
    if value.get("external_effects_performed") is not False:
        raise ContractError("local runtime handlers may not claim external effects")
    if value.get("implementation_state") not in {
        item.value for item in CapabilityMode
    }:
        raise ContractError("handler implementation state is unsupported")
    if value.get("external_evidence") not in {item.value for item in EvidenceState}:
        raise ContractError("handler evidence state is unsupported")
    if value.get("certification") not in {
        CertificationState.NOT_CERTIFIED.value,
        CertificationState.READY_FOR_EXTERNAL_GATE.value,
    }:
        raise ContractError("local runtime handlers may not certify")
    certification = value["certification"]
    state = value["state"]
    evidence = value["external_evidence"]
    if certification == CertificationState.READY_FOR_EXTERNAL_GATE.value and (
        state != ExecutionState.READY_FOR_EXTERNAL_GATE.value
        or evidence != EvidenceState.INDEPENDENTLY_VERIFIED.value
    ):
        raise ContractError(
            "gate-ready certification state requires independently verified gate-ready evidence"
        )
    outputs = value["outputs"]
    if certification == CertificationState.READY_FOR_EXTERNAL_GATE.value and outputs.get(
        "verdict"
    ) in {"DIVERGENT", "UNDETERMINED", "INCONCLUSIVE", "NOT_RUN"}:
        raise ContractError("non-success verdict may not be promoted to gate ready")
    return dict(value)


class SkillRuntime:
    def __init__(
        self,
        *,
        state_store: SqliteExecutionStore,
        artifact_store: ContentAddressedArtifactStore,
        catalog: CompiledCatalog | None = None,
        registry: Mapping[str, HandlerBinding] | None = None,
        external_runner: ExternalRunner | None = None,
    ):
        self.catalog = catalog or load_catalog()
        self.external_runner = external_runner
        self.registry = registry or build_registry(self.catalog, external_runner)
        validate_registry(self.catalog, self.registry)
        self.runtime_contract_digest = digest_json(
            {
                "schema_version": _RUNTIME_CONTRACT_VERSION,
                "catalog_digest": self.catalog.digest,
                "bindings": [binding.to_dict() for binding in self.registry.values()],
            }
        )
        self.state_store = state_store
        self.artifact_store = artifact_store

    def execute(
        self,
        skill_name: str,
        request_value: Mapping[str, Any],
        *,
        authority: ExecutionAuthority,
    ) -> dict[str, Any]:
        if not isinstance(skill_name, str) or skill_name not in self.registry:
            raise SkillRuntimeError(f"unknown Polyglot Semantic Skill: {skill_name!r}")
        binding = self.registry[skill_name]
        request: RuntimeRequest | None = None
        request_digest: str | None = None
        authorized = False
        try:
            request = RuntimeRequest.parse(request_value)
            authority.authorize(skill_name, request)
            authorized = True
            request_digest = self.state_store.request_digest(
                skill_name,
                request,
                runtime_contract_digest=self.runtime_contract_digest,
            )
            replay = self.state_store.lookup(
                skill_name=skill_name,
                request=request,
                request_digest=request_digest,
            )
            if replay is not None:
                return replay
            operation = _validate_operation(
                binding.handler(request, authority, self.catalog)
            )
        except IdempotencyConflict:
            raise
        except (AuthorityError, ContractError) as exc:
            operation = {
                "state": "BLOCKED",
                "code": "REQUEST_CONTRACT_REJECTED",
                "implementation_state": binding.capability_mode,
                "outputs": {
                    "error_type": type(exc).__name__,
                    "request_binding": "EXACT_NORMALIZED" if request is not None else "UNAVAILABLE",
                },
                "unavailable": ["valid request and host-minted authority"],
                "warnings": [],
                "external_effects_performed": False,
                "external_evidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            }
        except Exception as exc:
            operation = {
                "state": "FAILED",
                "code": "LOCAL_HANDLER_FAILED",
                "implementation_state": binding.capability_mode,
                "outputs": {"error_type": type(exc).__name__},
                "unavailable": ["valid local handler result"],
                "warnings": [],
                "external_effects_performed": False,
                "external_evidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            }

        request_binding = request.to_dict() if request is not None else None
        if request_digest is None:
            try:
                request_digest = digest_json(
                    {"skill": skill_name, "rejected_request": dict(request_value)}
                )
            except Exception:
                request_digest = None
        request_artifact = (
            self.artifact_store.put_json(
                {
                    "schema_version": "1.0",
                    "skill": skill_name,
                    "source_id": binding.source_id,
                    "request": request_binding,
                    "request_digest": request_digest,
                }
            )
            if authorized
            else None
        )
        operation_artifact = (
            self.artifact_store.put_json(
                {
                    "schema_version": "1.0",
                    "skill": skill_name,
                    "source_id": binding.source_id,
                    "request_digest": request_digest,
                    "operation": operation,
                }
            )
            if authorized
            else None
        )
        result: dict[str, Any] = {
            "schema_version": "1.0",
            "skill": skill_name,
            "source_id": binding.source_id,
            "handler_id": binding.handler_id,
            "runtime_contract_digest": self.runtime_contract_digest,
            "catalog_digest": self.catalog.digest,
            "request_id": request.request_id if request is not None else None,
            "tenant_id": request.tenant_id if request is not None else None,
            "project_id": request.project_id if request is not None else None,
            "actor_id": request.actor_id if request is not None else None,
            "revision_digest": request.revision_digest if request is not None else None,
            "environment_authority_id": (
                request.environment_authority_id if request is not None else None
            ),
            "request_digest": request_digest,
            "request_binding": "EXACT_NORMALIZED" if request_binding is not None else "UNAVAILABLE",
            **operation,
            "request_artifact": request_artifact,
            "artifact": operation_artifact,
        }
        result["result_digest"] = digest_json(result)
        if not authorized or request is None or request_digest is None:
            return result
        return self.state_store.commit(
            skill_name=skill_name,
            request=request,
            request_digest=request_digest,
            result=result,
        )


def capability_manifest(catalog: CompiledCatalog | None = None) -> dict[str, Any]:
    compiled = catalog or load_catalog()
    registry = build_registry(compiled)
    validate_registry(compiled, registry)
    return {
        "schema_version": "1.0",
        "package": "elmos-polyglot-skills",
        "version": "3.0.0",
        "catalog_digest": compiled.digest,
        "runtime_contract_digest": digest_json(
            {
                "schema_version": _RUNTIME_CONTRACT_VERSION,
                "catalog_digest": compiled.digest,
                "bindings": [binding.to_dict() for binding in registry.values()],
            }
        ),
        "skills": [binding.to_dict() for binding in registry.values()],
        "counts": {
            "skills": len(registry),
            "dependency_edges": sum(
                len(item.dependencies) for item in compiled.skills
            ),
            "route_cells": len(compiled.routes),
            "reference_routes": len(compiled.reference_routes),
        },
        "implementation": "CODE_COMPLETE_LOCAL_CONTROL_PLANE",
        "external_runtime": "NOT_RUN",
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


__all__ = [
    "HandlerBinding",
    "SkillRuntime",
    "SkillRuntimeError",
    "build_registry",
    "capability_manifest",
    "validate_registry",
]
