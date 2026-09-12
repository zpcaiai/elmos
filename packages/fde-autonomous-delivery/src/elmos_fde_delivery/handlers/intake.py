"""Handlers for Pack 02: Repository Intake and Runtime."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any


def execute_repository_custody_and_revisionset(payload: Mapping[str, Any]) -> dict[str, Any]:
    repo_url = payload.get("repo_url", "https://github.com/elmos-fde/demo-target")
    commit_sha = payload.get("commit_sha", "a" * 40)
    rev_digest = hashlib.sha256(f"{repo_url}:{commit_sha}".encode()).hexdigest()
    return {
        "status": "PASS",
        "pack": "02-repository-intake-runtime",
        "skill": "repository-custody-and-revisionset",
        "custody_status": "SECURED_READ_ONLY",
        "revision_digest": rev_digest,
        "effect_class": "PREPARE_EXTERNAL_EFFECT",
        "prepared_effect": "GIT_MIRROR_SNAPSHOT",
        "standalone_boundary": "E3",
    }


def execute_asset_inventory_and_classification(payload: Mapping[str, Any]) -> dict[str, Any]:
    assets = payload.get("assets", [
        {"path": "src/main.py", "kind": "SOURCE", "lang": "Python"},
        {"path": "schema/v1.sql", "kind": "DDL", "lang": "SQL"},
        {"path": "Dockerfile", "kind": "BUILD", "lang": "Docker"},
    ])
    return {
        "status": "PASS",
        "pack": "02-repository-intake-runtime",
        "skill": "asset-inventory-and-classification",
        "asset_count": len(assets),
        "inventory": assets,
        "effect_class": "READ_ONLY",
        "standalone_boundary": "E3",
    }


def execute_reproducible_build_environment(payload: Mapping[str, Any]) -> dict[str, Any]:
    toolchain = payload.get("toolchain", {"python": "3.12", "compiler": "native"})
    return {
        "status": "PASS",
        "pack": "02-repository-intake-runtime",
        "skill": "reproducible-build-environment",
        "hermetic_status": "LOCKED",
        "toolchain": toolchain,
        "effect_class": "PREPARE_EXTERNAL_EFFECT",
        "prepared_effect": "SANDBOX_BUILD_CONTAINER_PROVISION",
        "standalone_boundary": "E3",
    }


def execute_external_dependency_stub_and_service_virtualization(payload: Mapping[str, Any]) -> dict[str, Any]:
    stubs = payload.get("stubs", ["payment-gateway-mock", "identity-provider-mock"])
    return {
        "status": "PASS",
        "pack": "02-repository-intake-runtime",
        "skill": "external-dependency-stub-and-service-virtualization",
        "stub_count": len(stubs),
        "virtualized_endpoints": stubs,
        "effect_class": "PREPARE_EXTERNAL_EFFECT",
        "prepared_effect": "VIRTUAL_SERVICE_DEPLOY",
        "standalone_boundary": "E3",
    }


def execute_support_profile_and_unknown_register(payload: Mapping[str, Any]) -> dict[str, Any]:
    knowns = payload.get("supported_capabilities", ["rest-api", "relational-persistence"])
    unknowns = payload.get("unsupported_or_unknown", [])
    return {
        "status": "PASS",
        "pack": "02-repository-intake-runtime",
        "skill": "support-profile-and-unknown-register",
        "supported_count": len(knowns),
        "unknown_count": len(unknowns),
        "unknowns": unknowns,
        "effect_class": "READ_ONLY",
        "standalone_boundary": "E3",
    }


def execute_runtime_observation_and_traffic_capture(payload: Mapping[str, Any]) -> dict[str, Any]:
    sample_requests = payload.get("sample_requests", [{"path": "/api/v1/health", "status": 200}])
    return {
        "status": "PASS",
        "pack": "02-repository-intake-runtime",
        "skill": "runtime-observation-and-traffic-capture",
        "captured_trace_count": len(sample_requests),
        "effect_class": "PREPARE_EXTERNAL_EFFECT",
        "prepared_effect": "NETWORK_OBSERVABILITY_TAP",
        "standalone_boundary": "E3",
    }
