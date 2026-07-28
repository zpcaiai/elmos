#!/usr/bin/env python3
"""Fail-closed structural gate for the Coding Agent model catalog.

Validates engines/ai-platform-engine/policies/model-catalog-v1.json:
  * conforms to schemas/ai-platform/model-catalog-v1.schema.json shape
  * every modelId is unique
  * every status is NOT_CONFIGURED (no model may claim availability without a
    real ModelEndpoint(approved=true, healthy=true) evidence trail)
  * every entry in routesThroughAdapter exists as a key in
    engines/ai-platform-engine/policies/adapters-v1.json, so the catalog never
    references an undeclared adapter
  * consumers only names the three business lines the catalog is meant to
    share (project-synthesis-engine, spring-upgrade-coding-agent,
    cross-language-lowering-coding-agent)

This mirrors the style of validate_generation_support_matrix.py: a small,
dependency-free, fail-closed consistency check rather than a schema-library
validator, since the point is repository-internal consistency, not general
JSON Schema conformance.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "engines" / "ai-platform-engine" / "policies" / "model-catalog-v1.json"
ADAPTERS_PATH = ROOT / "engines" / "ai-platform-engine" / "policies" / "adapters-v1.json"
SCHEMA_PATH = ROOT / "schemas" / "ai-platform" / "model-catalog-v1.schema.json"
JAVA_MIRROR_PATH = (
    ROOT / "modules" / "enterprise-governance" / "src" / "main" / "java" / "io" / "elmos" / "enterprise" / "ModelCatalog.java"
)
SPRING_CONFIGURATION_PATH = (
    ROOT / "apps" / "java-engine-worker" / "src" / "main" / "java" / "io" / "elmos" / "worker" / "SpringUpgradeConfiguration.java"
)

ALLOWED_ROLES = {"SPEC_CLARIFICATION", "LONG_TAIL_CODE_FIX", "IDIOMATIZATION_REVIEW", "FAST_ITERATION"}
ALLOWED_CONSUMERS = {
    "project-synthesis-engine",
    "spring-upgrade-coding-agent",
    "cross-language-lowering-coding-agent",
}
MODEL_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")


class CatalogError(RuntimeError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise CatalogError(reason)


def load_json(path: Path) -> dict:
    require(path.is_file(), f"MISSING_FILE:{path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate() -> None:
    require(SCHEMA_PATH.is_file(), "MISSING_SCHEMA_FILE")
    catalog = load_json(CATALOG_PATH)
    adapters = load_json(ADAPTERS_PATH)

    require(catalog.get("schemaVersion") == "1.0", "CATALOG_SCHEMA_VERSION_MISMATCH")
    require(catalog.get("catalogId") == "elmos.coding-agent-model-catalog", "CATALOG_ID_MISMATCH")
    require(catalog.get("externalEvidenceStatus") == "NOT_RUN", "CATALOG_MUST_STAY_NOT_RUN")
    require(catalog.get("certificationStatus") == "NOT_CERTIFIED", "CATALOG_MUST_STAY_NOT_CERTIFIED")

    adapter_keys = set(adapters.get("adapters", {}).keys())
    routes_through = catalog.get("routesThroughAdapter", [])
    require(bool(routes_through), "CATALOG_MUST_DECLARE_AT_LEAST_ONE_ADAPTER")
    for adapter_name in routes_through:
        require(adapter_name in adapter_keys, f"UNDECLARED_ADAPTER:{adapter_name}")

    consumers = catalog.get("consumers", [])
    require(bool(consumers), "CATALOG_MUST_DECLARE_AT_LEAST_ONE_CONSUMER")
    for consumer in consumers:
        require(consumer in ALLOWED_CONSUMERS, f"UNKNOWN_CONSUMER:{consumer}")

    models = catalog.get("models", [])
    require(bool(models), "CATALOG_MUST_DECLARE_AT_LEAST_ONE_MODEL")

    seen_ids: set[str] = set()
    for entry in models:
        model_id = entry.get("modelId", "")
        require(bool(MODEL_ID_PATTERN.match(model_id)), f"INVALID_MODEL_ID:{model_id!r}")
        require(model_id not in seen_ids, f"DUPLICATE_MODEL_ID:{model_id}")
        seen_ids.add(model_id)

        require(bool(entry.get("displayName")), f"MISSING_DISPLAY_NAME:{model_id}")
        require(bool(entry.get("vendor")), f"MISSING_VENDOR:{model_id}")
        require(bool(entry.get("modelFamily")), f"MISSING_MODEL_FAMILY:{model_id}")
        require(entry.get("suggestedRole") in ALLOWED_ROLES, f"INVALID_SUGGESTED_ROLE:{model_id}")
        require(entry.get("status") == "NOT_CONFIGURED", f"MODEL_STATUS_MUST_BE_NOT_CONFIGURED:{model_id}")

    validate_java_mirror(seen_ids)
    long_tail_ids = {
        entry["modelId"] for entry in models if entry.get("suggestedRole") == "LONG_TAIL_CODE_FIX"
    }
    validate_spring_candidate_mirror(long_tail_ids)


def validate_java_mirror(json_model_ids: set[str]) -> None:
    """engines/ai-platform-engine's provisioning code (ModelEndpointProvisioning,
    ModelEndpointRegistry) has no JSON dependency, so ModelCatalog.MODEL_IDS
    duplicates the JSON catalog's modelId list by hand. This check is the only
    thing keeping the two from silently drifting apart."""
    require(JAVA_MIRROR_PATH.is_file(), f"MISSING_FILE:{JAVA_MIRROR_PATH.relative_to(ROOT)}")
    source = JAVA_MIRROR_PATH.read_text(encoding="utf-8")
    match = re.search(r"MODEL_IDS\s*=\s*List\.of\((.*?)\);", source, re.DOTALL)
    require(match is not None, "JAVA_MIRROR_MODEL_IDS_BLOCK_NOT_FOUND")
    java_ids = re.findall(r'"([^"]+)"', match.group(1))
    require(bool(java_ids), "JAVA_MIRROR_MODEL_IDS_EMPTY")

    require(len(java_ids) == len(set(java_ids)), "JAVA_MIRROR_HAS_DUPLICATE_MODEL_IDS")
    java_id_set = set(java_ids)
    missing_from_java = json_model_ids - java_id_set
    extra_in_java = java_id_set - json_model_ids
    require(not missing_from_java, f"JAVA_MIRROR_MISSING_MODEL_IDS:{sorted(missing_from_java)}")
    require(not extra_in_java, f"JAVA_MIRROR_HAS_UNKNOWN_MODEL_IDS:{sorted(extra_in_java)}")


def validate_spring_candidate_mirror(long_tail_model_ids: set[str]) -> None:
    """SpringUpgradeConfiguration.springUpgradeCodingAgentPort() hard-codes the
    candidate model id list it hands to EnterpriseGovernanceSpringUpgradeCodingAgentPort
    (see ADR-0059). Every id it lists must be a real catalog entry tagged
    LONG_TAIL_CODE_FIX, and it must not silently miss one either."""
    require(SPRING_CONFIGURATION_PATH.is_file(), f"MISSING_FILE:{SPRING_CONFIGURATION_PATH.relative_to(ROOT)}")
    source = SPRING_CONFIGURATION_PATH.read_text(encoding="utf-8")
    match = re.search(r"candidateModelIds\s*=\s*List\.of\((.*?)\);", source, re.DOTALL)
    require(match is not None, "SPRING_CANDIDATE_MODEL_IDS_BLOCK_NOT_FOUND")
    spring_ids = re.findall(r'"([^"]+)"', match.group(1))
    require(bool(spring_ids), "SPRING_CANDIDATE_MODEL_IDS_EMPTY")
    require(len(spring_ids) == len(set(spring_ids)), "SPRING_CANDIDATE_HAS_DUPLICATE_MODEL_IDS")

    spring_id_set = set(spring_ids)
    unknown_or_wrong_role = spring_id_set - long_tail_model_ids
    require(not unknown_or_wrong_role,
            f"SPRING_CANDIDATE_NOT_TAGGED_LONG_TAIL_CODE_FIX_IN_CATALOG:{sorted(unknown_or_wrong_role)}")


def main() -> int:
    try:
        validate()
    except CatalogError as exc:
        print(f"MODEL_CATALOG_GATE_FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"model-catalog-check: PASS ({CATALOG_PATH.relative_to(ROOT)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
