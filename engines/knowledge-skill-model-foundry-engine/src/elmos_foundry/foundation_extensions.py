"""Exact, bounded local semantics for Pack 00 Foundation extensions.

This module implements exact repository-owned handlers for:
- contract-migration-manager: Schema migration, compatibility preservation and dual-write planning.
- extension-sdk-and-codegen: Deterministic typed SDK and client scaffold contract generation.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .canonical import canonical_digest, canonical_value
from .domain import TenantScope
from .local_semantics import (
    CatalogView,
    LocalHandler,
    LocalSemanticRuntime,
    _inputs,
    _mapping,
    _response,
    _sequence,
    _text,
)
from .store import FoundryStore


FOUNDATION_EXTENSION_SKILLS = frozenset(
    {
        "contract-migration-manager",
        "extension-sdk-and-codegen",
    }
)

_PACKAGE_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)*\Z")


def _scope_check(value: Mapping[str, Any], scope: TenantScope, label: str) -> None:
    tenant_id = value.get("tenant_id")
    project_id = value.get("project_id")
    if tenant_id is not None and tenant_id != scope.tenant_id:
        raise ValueError(f"{label} tenant_id does not match authenticated scope")
    if project_id is not None and project_id != scope.project_id:
        raise ValueError(f"{label} project_id does not match authenticated scope")


def _contract_migration(
    skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str
) -> Mapping[str, Any]:
    values = _inputs(payload)
    requirement = _mapping(values["business requirement"], "business requirement")
    architecture = _mapping(values["architecture decision"], "architecture decision")
    policy = _mapping(values["policy profile"], "policy profile")
    runtime = _mapping(values["runtime capability inventory"], "runtime capability inventory")
    del runtime

    _scope_check(policy, scope, "policy profile")
    source_version = _text(requirement.get("source_version", "1.0.0"), "source_version")
    target_version = _text(requirement.get("target_version", "2.0.0"), "target_version")
    if source_version == target_version:
        raise ValueError("contract migration target_version must differ from source_version")

    strategy = _text(architecture.get("strategy", "expand-contract"), "strategy")
    valid_strategies = {"expand-contract", "dual-write", "parallel-run", "blue-green"}
    if strategy not in valid_strategies:
        raise ValueError(f"migration strategy '{strategy}' is unsupported; must be one of {sorted(valid_strategies)}")

    rollback_strategy = _text(
        architecture.get("rollback_strategy", "compensate-and-revert"),
        "rollback_strategy",
    )
    compatibility_mode = _text(
        policy.get("compatibility_mode", "backward-compatible"),
        "compatibility_mode",
    )
    if compatibility_mode not in {"backward-compatible", "fully-compatible", "breaking-with-shim"}:
        raise ValueError(f"unsupported compatibility_mode: {compatibility_mode}")

    changes = _sequence(
        requirement.get("schema_changes", [{"kind": "add_field", "field": "version"}]),
        "schema_changes",
        minimum=1,
        maximum=1000,
    )

    contract_plan = {
        "schema_version": "elmos.foundry.contract-migration.v1",
        "migration_id": f"mig-{canonical_digest(values)[7:39]}",
        "skill_name": skill,
        "source_version": source_version,
        "target_version": target_version,
        "strategy": strategy,
        "rollback_strategy": rollback_strategy,
        "compatibility_mode": compatibility_mode,
        "change_count": len(changes),
        "changes": canonical_value(changes),
        "zero_downtime_supported": strategy in {"expand-contract", "dual-write"},
        "rehearsal_required": True,
        "dual_run_verified": False,
        "tenant_id": scope.tenant_id,
        "project_id": scope.project_id,
        "invocation_id": invocation,
        "effects_performed": False,
    }

    return _response(
        LocalSemanticRuntime._foundation_outputs(
            skill,
            values,
            {
                **contract_plan,
                "effect_authorized": False,
                "external_evidence_status": "NOT_RUN",
                "certification_status": "NOT_CERTIFIED",
            },
        )
    )


def _extension_codegen(
    skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str
) -> Mapping[str, Any]:
    values = _inputs(payload)
    requirement = _mapping(values["business requirement"], "business requirement")
    architecture = _mapping(values["architecture decision"], "architecture decision")
    policy = _mapping(values["policy profile"], "policy profile")
    runtime = _mapping(values["runtime capability inventory"], "runtime capability inventory")
    del runtime

    _scope_check(policy, scope, "policy profile")
    target_language = _text(requirement.get("target_language", "python"), "target_language").lower()
    valid_languages = {"csharp", "go", "java", "python", "rust", "typescript"}
    if target_language not in valid_languages:
        raise ValueError(f"target_language '{target_language}' unsupported; must be one of {sorted(valid_languages)}")

    package_name = _text(requirement.get("package_name", "elmos-client-sdk"), "package_name")
    if not _PACKAGE_NAME_PATTERN.match(package_name):
        raise ValueError(f"package_name '{package_name}' does not match canonical package naming convention")

    generation_mode = _text(architecture.get("generation_mode", "typed-interfaces"), "generation_mode")
    valid_modes = {"adapter-stubs", "client-scaffold", "full-sdk", "typed-interfaces"}
    if generation_mode not in valid_modes:
        raise ValueError(f"generation_mode '{generation_mode}' unsupported; must be one of {sorted(valid_modes)}")

    skills_to_generate = _sequence(
        requirement.get("skills", ["artifact-identity-and-hashing"]),
        "skills",
        minimum=1,
        maximum=1310,
    )
    for item in skills_to_generate:
        _text(item, "skill identity", maximum=256)

    codegen_manifest = {
        "schema_version": "elmos.foundry.extension-sdk-codegen.v1",
        "codegen_id": f"sdk-{canonical_digest(values)[7:39]}",
        "skill_name": skill,
        "target_language": target_language,
        "package_name": package_name,
        "generation_mode": generation_mode,
        "skill_count": len(skills_to_generate),
        "target_skills": sorted(set(str(item) for item in skills_to_generate)),
        "type_safety_level": "STRICT_TYPED",
        "telemetry_hooks_included": True,
        "fail_closed_stubs_emitted": True,
        "tenant_id": scope.tenant_id,
        "project_id": scope.project_id,
        "invocation_id": invocation,
        "codegen_executed_locally": True,
        "external_effects_performed": False,
    }

    return _response(
        LocalSemanticRuntime._foundation_outputs(
            skill,
            values,
            {
                **codegen_manifest,
                "effect_authorized": False,
                "external_evidence_status": "NOT_RUN",
                "certification_status": "NOT_CERTIFIED",
            },
        )
    )


def build_foundation_extension_handlers(
    catalog: CatalogView, store: FoundryStore | None = None
) -> dict[str, LocalHandler]:
    del store
    handlers: dict[str, LocalHandler] = {
        "contract-migration-manager": _contract_migration,
        "extension-sdk-and-codegen": _extension_codegen,
    }
    if set(handlers) != FOUNDATION_EXTENSION_SKILLS:
        raise RuntimeError("foundation extension handler registry is not exact")
    missing = sorted(FOUNDATION_EXTENSION_SKILLS - set(catalog.atomic_skills))
    if missing:
        raise RuntimeError(f"foundation extension Skills are absent from catalog: {missing}")
    return handlers


__all__ = ["FOUNDATION_EXTENSION_SKILLS", "build_foundation_extension_handlers"]
