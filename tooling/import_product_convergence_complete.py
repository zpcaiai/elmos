#!/usr/bin/env python3
"""Integrate the supplied 40-Skill convergence package without Batch 46 collisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import skill_creator_tools
import yaml


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "batch46-product-convergence-complete-skills"
AGENT_SKILL_ROOT = ROOT / ".agents" / "skills"
INSTALL_MANIFEST = (
    ROOT
    / "docs"
    / "product-closure-convergence"
    / "batch46-complete-installed-manifest.json"
)
NORMALIZED_DEPENDENCIES = (
    ROOT
    / "docs"
    / "product-closure-convergence"
    / "batch46-complete-normalized-prerequisites.json"
)
EXPECTED_SOURCE_IDS = [str(number) for number in range(1497, 1537)]
CACHE_PARTS = {"__pycache__", ".DS_Store"}

# Product Convergence is an overlay. The source package's b46-* names collide
# with global Project Synthesis Batch 46, so every source Skill resolves to one
# existing semantic owner or to one new conv-* owner.
ALIAS_BY_SOURCE_NAME = {
    "b46-product-convergence-reference-implementation-factory": "conv-product-convergence-orchestrator",
    "b46-unified-capability-package-metamodel": "conv-capability-package-metamodel",
    "b46-capability-dependency-graph": "conv-capability-dependency-graph",
    "b46-global-migration-lifecycle-state-machine": "conv-global-project-lifecycle",
    "b46-durable-workflow-runtime-kernel": "conv-durable-workflow-runtime",
    "b46-unified-policy-engine": "conv-unified-policy-engine",
    "b46-global-evidence-graph": "conv-global-evidence-graph",
    "b46-capability-registry-support-matrix": "conv-capability-registry-support-matrix",
    "b46-pack-lifecycle-version-certification": "conv-pack-lifecycle-certification-unifier",
    "b46-core-extension-boundary-plugin-kernel": "conv-core-extension-boundary",
    "b46-meta-skill-layering-capability-resolver": "conv-skill-layering-routing",
    "b46-skill-registry-compiler-governance": "conv-skill-registry-compiler",
    "b46-skill-deduplication-foundation-extraction": "conv-duplicate-skill-consolidation",
    "b46-test-pyramid-real-system-classification": "conv-test-pyramid-real-system-classification",
    "b46-benchmark-corpus-governance": "conv-benchmark-corpus-governance",
    "b46-maintainability-idiomaticity-gate": "conv-maintainability-gate",
    "b46-product-information-architecture-customer-journey": "conv-product-information-architecture",
    "b46-migration-design-studio": "conv-migration-design-studio",
    "b46-customer-handoff-maintenance-acceptance": "conv-customer-handoff-operability",
    "b46-control-plane-modular-monolith": "conv-control-plane-modular-monolith",
    "b46-private-runner-reference-execution-plane": "conv-private-runner-reference-implementation",
    "b46-deterministic-transformation-priority": "conv-deterministic-migration-engine-reference",
    "b46-reference-route-java-spring-csharp-aspnet": "conv-java-spring-csharp-reference-route",
    "b46-reference-repository-corpus-design-partner": "conv-reference-repository-design-partner-corpus",
    "b46-unified-evals-benchmark-platform": "conv-validation-lab-evidence-store",
    "b46-recipe-promotion-knowledge-governance": "conv-recipe-promotion-knowledge-governance",
    "b46-product-edition-scope-rationalization": "conv-edition-commercial-package-simplification",
    "b46-standardized-product-packaging-delivery-contract": "conv-edition-commercial-package-simplification",
    "b46-verified-migrated-workload-value-metric": "conv-verified-migrated-workload-metrics",
    "b46-descope-defer-portfolio-governance": "conv-architecture-decision-change-control",
    "b46-reference-architecture-blueprint": "conv-reference-architecture-blueprint",
    "b46-convergence-roadmap-p0-p3": "conv-convergence-roadmap-p0-p3",
    "b46-integration-contract-anti-corruption-layer": "conv-integration-contract-anti-corruption-layer",
    "b46-reference-implementation-release-train": "conv-reference-implementation-release-train",
    "b46-convergence-observability-debt-dashboard": "conv-convergence-observability-debt-dashboard",
    "b46-design-partner-production-validation": "conv-design-partner-pilot",
    "b46-repeatable-profitable-delivery-model": "conv-repeatable-profitable-delivery-model",
    "b46-customer-success-sla-operations-proof": "conv-customer-success-sla-operations-proof",
    "b46-reference-product-acceptance-review": "conv-reference-product-acceptance-review",
    "b46-product-convergence-complete-certification-gate": "conv-product-convergence-readiness-gate",
}

NEW_SOURCE_NAMES = {
    "b46-reference-repository-corpus-design-partner",
    "b46-recipe-promotion-knowledge-governance",
    "b46-reference-architecture-blueprint",
    "b46-convergence-roadmap-p0-p3",
    "b46-integration-contract-anti-corruption-layer",
    "b46-reference-implementation-release-train",
    "b46-convergence-observability-debt-dashboard",
    "b46-repeatable-profitable-delivery-model",
    "b46-customer-success-sla-operations-proof",
    "b46-reference-product-acceptance-review",
}


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def source_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not CACHE_PARTS.intersection(path.parts)
        and path.suffix != ".pyc"
    )


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if match is None:
        fail(f"invalid Skill frontmatter: {path}")
    frontmatter = yaml.safe_load(match.group(1))
    if not isinstance(frontmatter, dict):
        fail(f"Skill frontmatter must be an object: {path}")
    return frontmatter, text[match.end() :].lstrip("\n")


def expected_interface(name: str, generator: ModuleType) -> str:
    return "\n".join(
        [
            "interface:",
            f"  display_name: {generator.yaml_quote(generator.format_display_name(name))}",
            "  short_description: "
            + generator.yaml_quote("Run this ELMOS product-convergence Skill with evidence"),
            "  default_prompt: "
            + generator.yaml_quote(
                f"Use ${name} to execute this ELMOS product-convergence Skill with fail-closed evidence."
            ),
            "",
        ]
    )


def write_exact(path: Path, data: bytes) -> None:
    if path.exists():
        if path.is_file() and path.read_bytes() == data:
            return
        fail(f"refusing to overwrite different file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write_json_exact(path: Path, value: Any) -> None:
    write_exact(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
    )


def validate_checksums() -> dict[str, str]:
    checksum_path = PACKAGE / "CHECKSUMS.sha256"
    checksums: dict[str, str] = {}
    for number, line in enumerate(
        checksum_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        parts = line.split("  ", 1)
        if (
            len(parts) != 2
            or not re.fullmatch(r"[0-9a-f]{64}", parts[0])
            or parts[1] in checksums
        ):
            fail(f"invalid source checksum line {number}")
        checksums[parts[1]] = parts[0]
    actual = {
        path.relative_to(PACKAGE).as_posix()
        for path in source_files(PACKAGE)
        if path.name != "CHECKSUMS.sha256"
    }
    if actual != set(checksums):
        fail(
            "source checksum inventory drift: "
            f"missing={sorted(set(checksums)-actual)}, extra={sorted(actual-set(checksums))}"
        )
    for relative, digest in checksums.items():
        if sha256_file(PACKAGE / relative) != digest:
            fail(f"source checksum mismatch: {relative}")
    expected_inventory = [
        relative for relative in checksums if relative != "FILE_MANIFEST.txt"
    ]
    inventory = (PACKAGE / "FILE_MANIFEST.txt").read_text(encoding="utf-8").splitlines()
    if inventory != expected_inventory:
        fail("source FILE_MANIFEST.txt does not exactly enumerate the package")
    return checksums


def load_source_registry(validate_skill: Any) -> list[dict[str, Any]]:
    manifest = load_json(PACKAGE / "manifest.json")
    if (
        manifest.get("bundle") != PACKAGE.name
        or manifest.get("version") != "2.0.0"
        or manifest.get("skill_range") != "1497-1536"
        or manifest.get("skill_count") != 40
        or manifest.get("schema_count") != 29
    ):
        fail("source package identity or declared counts are invalid")
    schemas = list((PACKAGE / "schemas" / "batch46-complete").glob("*.json"))
    if len(schemas) != 29:
        fail("source package must contain exactly 29 Schemas")
    registry = load_json(
        PACKAGE / "convergence-packs" / "reference-product" / "skill-registry.json"
    ).get("skills")
    if not isinstance(registry, list) or len(registry) != 40:
        fail("source Skill registry must contain exactly 40 Skills")
    if [entry.get("skill_id") for entry in registry] != EXPECTED_SOURCE_IDS:
        fail("source Skill IDs must be exactly 1497 through 1536")
    if set(ALIAS_BY_SOURCE_NAME) != {entry.get("name") for entry in registry}:
        fail("the exact source-to-runtime alias map is incomplete or stale")
    for entry in registry:
        name = entry["name"]
        source = PACKAGE / ".agents" / "skills" / name / "SKILL.md"
        if not source.is_file():
            fail(f"source Skill is missing: {name}")
        frontmatter, _ = parse_frontmatter(source)
        if frontmatter.get("name") != name:
            fail(f"source Skill frontmatter mismatch: {name}")
        valid, message = validate_skill(source.parent)
        if not valid:
            fail(f"source Skill is not skill-creator compatible: {name}: {message}")
    return registry


def normalized_prerequisites(registry: list[dict[str, Any]]) -> dict[str, list[str]]:
    dependencies = {
        entry["skill_id"]: list(entry.get("prerequisites", [])) for entry in registry
    }
    # The source registry contains 1497<->1498 and 1500<->1501 cycles and two
    # range pseudo-identifiers. The normalized overlay makes the orchestrator
    # an entry point, orders lifecycle before workflow, and expands the review
    # dependency range to exact source IDs.
    dependencies["1497"] = []
    dependencies["1498"] = []
    dependencies["1500"] = ["1498"]
    dependencies["1501"] = ["1498", "1500"]
    dependencies["1535"] = [str(number) for number in range(1498, 1535)]
    known = set(dependencies)
    for skill_id, prerequisites in dependencies.items():
        if any(item not in known for item in prerequisites):
            fail(f"normalized prerequisite is unknown for {skill_id}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(skill_id: str) -> None:
        if skill_id in visiting:
            fail(f"normalized prerequisite cycle at {skill_id}")
        if skill_id in visited:
            return
        visiting.add(skill_id)
        for prerequisite in dependencies[skill_id]:
            visit(prerequisite)
        visiting.remove(skill_id)
        visited.add(skill_id)

    for skill_id in dependencies:
        visit(skill_id)
    return dependencies


def normalized_skill(entry: dict[str, Any]) -> bytes:
    source = PACKAGE / ".agents" / "skills" / entry["name"] / "SKILL.md"
    frontmatter, body = parse_frontmatter(source)
    alias = ALIAS_BY_SOURCE_NAME[entry["name"]]
    normalized = {
        "name": alias,
        "description": frontmatter["description"],
        "metadata": {
            "source_package": PACKAGE.name,
            "source_id": entry["skill_id"],
            "source_name": entry["name"],
            "source_sha256": "sha256:" + sha256_file(source),
            "normalized_namespace": "product-convergence-overlay",
            "source_batch_label": "package-local-batch46-product-convergence",
        },
    }
    note = """
## ELMOS repository integration

- 本Skill的`Batch 46`标签仅属于来源包，不是全局Project Synthesis Batch 46。
- 产品收敛总入口仍为`$conv-product-convergence-orchestrator`。
- 唯一仓库就绪判定脚本为`python3 scripts/product-convergence/run_repository_convergence_gate.py product-convergence --evidence-root .`。
- 来源包的正向自测、模板或本地静态校验不是客户、生产、Private Runner或认证证据；未真实执行的外部证据保持`NOT_RUN`。
"""
    rendered = (
        "---\n"
        + yaml.safe_dump(normalized, allow_unicode=True, sort_keys=False).strip()
        + "\n---\n\n"
        + body.rstrip()
        + "\n"
        + note
    )
    return rendered.encode()


def expected_manifest(
    registry: list[dict[str, Any]],
    checksums: dict[str, str],
    prerequisites: dict[str, list[str]],
) -> dict[str, Any]:
    records = []
    for entry in registry:
        source_name = entry["name"]
        source = PACKAGE / ".agents" / "skills" / source_name / "SKILL.md"
        alias = ALIAS_BY_SOURCE_NAME[source_name]
        target = AGENT_SKILL_ROOT / alias / "SKILL.md"
        interface = target.parent / "agents" / "openai.yaml"
        record = {
            "source_id": entry["skill_id"],
            "source_name": source_name,
            "source_path": source.relative_to(ROOT).as_posix(),
            "source_sha256": "sha256:" + sha256_file(source),
            "installed_alias": alias,
            "normalized_prerequisites": prerequisites[entry["skill_id"]],
        }
        if source_name in NEW_SOURCE_NAMES:
            record.update(
                {
                    "disposition": "installed_missing_semantic_owner",
                    "installed_path": target.relative_to(ROOT).as_posix(),
                    "installed_sha256": "sha256:" + sha256_file(target),
                    "interface_sha256": "sha256:" + sha256_file(interface),
                }
            )
        else:
            record.update(
                {
                    "disposition": "reused_existing_semantic_owner",
                    "installed_path": target.relative_to(ROOT).as_posix(),
                    "installed_sha256": "sha256:" + sha256_file(target),
                    "interface_sha256": "sha256:" + sha256_file(interface),
                }
            )
        records.append(record)
    return {
        "schema_version": "1.0",
        "source_package": PACKAGE.name,
        "source_package_version": "2.0.0",
        "source_package_files": len(checksums),
        "source_skill_count": 40,
        "source_schema_count": 29,
        "source_skill_range": "1497-1536",
        "namespace_policy": {
            "source_batch_label": "package-local-batch46-product-convergence",
            "global_batch46": "Project Synthesis PG001 start; never overwritten",
            "runtime_namespace": "conv-* Product Convergence overlay",
        },
        "source_registry_repairs": {
            "source_gate_authoritative": False,
            "source_gate_positive_fixture_is_external_evidence": False,
            "source_gate_maximum_authority": "LOCAL_ENGINEERING_EVIDENCE",
            "runtime_gate": "scripts/product-convergence/run_repository_convergence_gate.py",
            "maximum_runtime_decision": "READY_FOR_EXTERNAL_GATE",
            "repaired_cycles": ["1497<->1498", "1500<->1501"],
            "expanded_range_dependencies": ["1498-1534", "1498-1536"],
        },
        "installed_new_semantic_owners": len(NEW_SOURCE_NAMES),
        "reused_existing_semantic_owners": 40 - len(NEW_SOURCE_NAMES),
        "external_evidence": "NOT_RUN",
        "certified": False,
        "production_certified": False,
        "skills": records,
    }


def verify_runtime_target(
    entry: dict[str, Any], validate_skill: Any, generator: ModuleType
) -> None:
    source_name = entry["name"]
    alias = ALIAS_BY_SOURCE_NAME[source_name]
    target = AGENT_SKILL_ROOT / alias
    skill_path = target / "SKILL.md"
    interface_path = target / "agents" / "openai.yaml"
    if not skill_path.is_file():
        fail(f"runtime semantic owner is missing: {alias}")
    if source_name in NEW_SOURCE_NAMES and skill_path.read_bytes() != normalized_skill(entry):
        fail(f"normalized runtime Skill is missing or changed: {alias}")
    valid, message = validate_skill(target)
    if not valid:
        fail(f"installed runtime Skill is not skill-creator compatible: {alias}: {message}")
    if interface_path.read_text(encoding="utf-8") != expected_interface(alias, generator):
        fail(f"runtime Skill interface is missing or changed: {alias}")


def install() -> None:
    generator = skill_creator_tools
    validate_skill = skill_creator_tools.validate_skill
    checksums = validate_checksums()
    registry = load_source_registry(validate_skill)
    prerequisites = normalized_prerequisites(registry)
    for entry in registry:
        if entry["name"] not in NEW_SOURCE_NAMES:
            continue
        alias = ALIAS_BY_SOURCE_NAME[entry["name"]]
        target = AGENT_SKILL_ROOT / alias
        write_exact(target / "SKILL.md", normalized_skill(entry))
        write_exact(
            target / "agents" / "openai.yaml",
            expected_interface(alias, generator).encode(),
        )
    for entry in registry:
        verify_runtime_target(entry, validate_skill, generator)
    write_json_exact(
        NORMALIZED_DEPENDENCIES,
        {
            "schema_version": "1.0",
            "source_package": PACKAGE.name,
            "dependencies": prerequisites,
        },
    )
    write_json_exact(
        INSTALL_MANIFEST,
        expected_manifest(registry, checksums, prerequisites),
    )
    verify()


def verify() -> None:
    generator = skill_creator_tools
    validate_skill = skill_creator_tools.validate_skill
    checksums = validate_checksums()
    registry = load_source_registry(validate_skill)
    prerequisites = normalized_prerequisites(registry)
    for entry in registry:
        verify_runtime_target(entry, validate_skill, generator)
    if load_json(NORMALIZED_DEPENDENCIES) != {
        "schema_version": "1.0",
        "source_package": PACKAGE.name,
        "dependencies": prerequisites,
    }:
        fail("normalized convergence dependency graph is missing or stale")
    expected = expected_manifest(registry, checksums, prerequisites)
    if load_json(INSTALL_MANIFEST) != expected:
        fail("complete convergence installed manifest is missing or stale")
    if any(
        path.is_dir()
        for path in AGENT_SKILL_ROOT.glob("b46-*")
    ):
        fail("colliding b46-* source Skills must not be installed in .agents/skills")
    print(
        json.dumps(
            {
                "status": "PASS",
                "source_files": len(checksums),
                "source_skills": len(registry),
                "source_schemas": 29,
                "installed_new_semantic_owners": len(NEW_SOURCE_NAMES),
                "reused_existing_semantic_owners": 40 - len(NEW_SOURCE_NAMES),
                "normalized_dependency_nodes": len(prerequisites),
                "skill_creator_compatible_runtime_owners": len(
                    set(ALIAS_BY_SOURCE_NAME.values())
                ),
                "source_gate_authoritative": False,
                "repository_gate": "scripts/product-convergence/run_repository_convergence_gate.py",
                "external_evidence": "NOT_RUN",
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    if args.install:
        install()
    else:
        verify()


if __name__ == "__main__":
    main()
