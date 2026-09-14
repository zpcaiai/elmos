#!/usr/bin/env python3
"""Fail closed when the Project Synthesis P0 launch contract drifts."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SOURCE = ROOT / "engines" / "project-synthesis-engine" / "src"
sys.path.insert(0, str(ENGINE_SOURCE))

from elmos_project_synthesis.container_images import POSTGRES_IMAGE  # noqa: E402
from elmos_project_synthesis.models import (  # noqa: E402
    P0_AUTH_MODES,
    P0_EXACT_QUALIFICATION_TOOLCHAINS,
    P0_POSTGRESQL_VERSION,
    STARTER_MULTI_ENTITY_TARGETS,
    SUPPORTED_LANGUAGES,
    SUPPORTED_PROFILE_TARGETS,
    p0_scope_payload,
)

SCOPE_PATH = ROOT / "docs" / "project-synthesis" / "p0-launch-scope-v1.json"
SUPPORT_PATH = ROOT / "docs" / "project-synthesis" / "bundled-emitter-support.json"
PROVIDER_OBSERVATION_PATH = ROOT / "docs" / "project-synthesis" / "provider-observation-2026-09-04.json"

EXPECTED_EXACT_VERSIONS = {
    "java": ("21.0.11", "3.9.10"),
    "python": ("3.12.12", "0.11.16"),
    "csharp": ("10.0.301",),
    "typescript": ("26.0.0", "10.12.4"),
    "go": ("1.25.0",),
    "kotlin": ("2.2.20", "21.0.11", "8.14.3"),
    "php": ("8.4.12",),
    "rust": ("1.89.0", "1.89.0"),
}


class ScopeFailure(RuntimeError):
    """A stable P0 scope-contract failure."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ScopeFailure(reason)


def canonical_json(document: object) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def main() -> int:
    scope = json.loads(SCOPE_PATH.read_text(encoding="utf-8"))
    expected = p0_scope_payload()
    require(scope == expected, "P0_SCOPE_RUNTIME_DRIFT")
    require(tuple(item["language"] for item in scope["languages"]) == SUPPORTED_LANGUAGES, "P0_LANGUAGE_DRIFT")
    require(
        {
            language: tuple(item["version"] for item in P0_EXACT_QUALIFICATION_TOOLCHAINS[language])
            for language in SUPPORTED_LANGUAGES
        }
        == EXPECTED_EXACT_VERSIONS,
        "P0_EXACT_QUALIFICATION_TOOLCHAIN_DRIFT",
    )
    require("managed_provider_observation" not in scope, "P0_SCOPE_CONTAINS_TIME_VARYING_OBSERVATION")
    require(
        scope.get("managed_provider_contract")
        == {
            "database_exact_version_observation": "REQUIRED_SEPARATE_DIGEST_BOUND_EVIDENCE",
            "oidc_required_jwk_kty": "RSA",
            "oidc_required_jwk_algorithm": "RS256",
            "algorithm_mismatch_policy": "BLOCKED",
            "provider_evidence_status": "NOT_RUN",
        },
        "P0_MANAGED_PROVIDER_CONTRACT_DRIFT",
    )
    require(frozenset(scope["multi_entity_languages"]) == STARTER_MULTI_ENTITY_TARGETS, "P0_MULTI_ENTITY_DRIFT")
    require(tuple(item["mode"] for item in scope["authentication"]) == P0_AUTH_MODES, "P0_AUTH_MODE_DRIFT")
    require(
        scope["persistence"]["exact_local_runtime_version"] == P0_POSTGRESQL_VERSION,
        "P0_POSTGRESQL_VERSION_DRIFT",
    )
    require(
        POSTGRES_IMAGE.startswith(f"postgres:{P0_POSTGRESQL_VERSION}-") and "@sha256:" in POSTGRES_IMAGE,
        "P0_POSTGRES_IMAGE_DRIFT",
    )
    for auth_mode in P0_AUTH_MODES:
        require(
            SUPPORTED_PROFILE_TARGETS.get(("postgresql", auth_mode)) == frozenset(SUPPORTED_LANGUAGES),
            f"P0_{auth_mode.upper()}_TARGET_DRIFT",
        )

    support = json.loads(SUPPORT_PATH.read_text(encoding="utf-8"))
    require(
        tuple(item.get("language") for item in support.get("profiles", [])) == SUPPORTED_LANGUAGES,
        "P0_SUPPORT_MATRIX_LANGUAGE_DRIFT",
    )
    require(support.get("external_evidence_status") == "NOT_RUN", "P0_EXTERNAL_EVIDENCE_OVERCLAIM")
    require(support.get("certification_status") == "NOT_CERTIFIED", "P0_CERTIFICATION_OVERCLAIM")
    require(support.get("p0_launch_scope") == SCOPE_PATH.relative_to(ROOT).as_posix(), "P0_SCOPE_PATH_DRIFT")
    multi_entity = support.get("multi_entity")
    require(isinstance(multi_entity, dict), "P0_MULTI_ENTITY_SUPPORT_INVALID")
    require(tuple(multi_entity.get("emitter_support", [])) == SUPPORTED_LANGUAGES, "P0_MULTI_ENTITY_SUPPORT_DRIFT")
    receipt_coverage = multi_entity.get("committed_local_matrix_coverage")
    require(isinstance(receipt_coverage, dict), "P0_MULTI_ENTITY_RECEIPT_COVERAGE_INVALID")
    local_matrix = json.loads((ROOT / str(support["local_evidence"])).read_text(encoding="utf-8"))
    cases = local_matrix.get("cases")
    require(isinstance(cases, list), "P0_LOCAL_MATRIX_CASES_INVALID")
    observed_multi = sorted(
        {
            str(case.get("language"))
            for case in cases
            if isinstance(case, dict) and case.get("entity_shape") == "multi-entity"
        }
    )
    observed_single_only = sorted(set(SUPPORTED_LANGUAGES) - set(observed_multi))
    require(
        sorted(receipt_coverage.get("multi_entity", [])) == observed_multi,
        "P0_MULTI_ENTITY_RECEIPT_CLAIM_DRIFT",
    )
    require(
        sorted(receipt_coverage.get("single_entity_only_in_that_receipt", [])) == observed_single_only,
        "P0_SINGLE_ENTITY_RECEIPT_CLAIM_DRIFT",
    )
    require(
        receipt_coverage.get("fresh_current_sha_evidence_status") == "NOT_RUN",
        "P0_CURRENT_SHA_EVIDENCE_OVERCLAIM",
    )
    supply_chain = support.get("supply_chain")
    require(isinstance(supply_chain, dict), "P0_SUPPLY_CHAIN_POLICY_INVALID")
    require(
        supply_chain.get("transitive_inventory_policy") == "REQUIRED_COMPLETE_FOR_RELEASE",
        "P0_SBOM_POLICY_DRIFT",
    )
    require(
        supply_chain.get("artifact_integrity_policy")
        == "REQUIRED_COMPLETE_OR_NOT_APPLICABLE_FOR_RELEASE",
        "P0_ARTIFACT_INTEGRITY_POLICY_DRIFT",
    )
    require(
        supply_chain.get("dependency_graph_status") == "INCOMPLETE_FLATTENED",
        "P0_DEPENDENCY_GRAPH_OVERCLAIM",
    )
    require(
        supply_chain.get("release_signature") == "REQUIRED_TRUSTED_ED25519",
        "P0_SIGNATURE_POLICY_DRIFT",
    )
    require(supply_chain.get("current_sha_evidence_status") == "NOT_RUN", "P0_CURRENT_SHA_EVIDENCE_OVERCLAIM")

    provider = json.loads(PROVIDER_OBSERVATION_PATH.read_text(encoding="utf-8"))
    require(
        support.get("managed_provider_observation", {}).get("path")
        == PROVIDER_OBSERVATION_PATH.relative_to(ROOT).as_posix(),
        "P0_PROVIDER_OBSERVATION_PATH_DRIFT",
    )
    require(provider.get("scope_id") == scope["scope_id"], "P0_PROVIDER_OBSERVATION_SCOPE_DRIFT")
    require(
        provider.get("observation", {}).get("database_server_version") == "17.11",
        "P0_MANAGED_DATABASE_OBSERVATION_DRIFT",
    )
    require(
        provider.get("observation", {}).get("jwk_algorithm") == "EdDSA"
        and provider.get("observation", {}).get("jwk_kty") == "OKP"
        and provider.get("assessment", {}).get("compatibility") == "ALGORITHM_MISMATCH"
        and provider.get("assessment", {}).get("launch_gate") == "BLOCKED",
        "P0_MANAGED_OIDC_MISMATCH_DRIFT",
    )
    require(
        provider.get("boundaries")
        == {
            "certification_status": "NOT_CERTIFIED",
            "database_migration_write_status": "NOT_RUN",
            "evidence_class": "OPERATOR_REPORTED_READ_ONLY",
            "raw_provider_receipt_status": "NOT_PROVIDED",
        },
        "P0_PROVIDER_EVIDENCE_BOUNDARY_DRIFT",
    )

    print(
        json.dumps(
            {
                "status": "PASSED",
                "scope_id": scope["scope_id"],
                "scope_sha256": hashlib.sha256(canonical_json(scope)).hexdigest(),
                "project_kind": scope["project_kind"],
                "language_count": len(scope["languages"]),
                "auth_modes": list(P0_AUTH_MODES),
                "local_postgresql_version": P0_POSTGRESQL_VERSION,
                "managed_provider_evidence_status": "NOT_RUN",
                "certification_status": "NOT_CERTIFIED",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, TypeError, ValueError, ScopeFailure) as error:
        print(json.dumps({"status": "FAILED", "reason": str(error)}, sort_keys=True))
        raise SystemExit(2) from error
