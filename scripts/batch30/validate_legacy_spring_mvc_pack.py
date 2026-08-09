#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PACK_KEY = "spring-framework-5-3-mvc-to-spring-boot-3-5-3"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACK = ROOT / "framework-packs" / PACK_KEY

EXPECTED_DOMAINS = {
    "web",
    "dependency-injection",
    "configuration",
    "validation",
    "authentication",
    "authorization",
    "persistence",
    "transactions",
    "error-handling",
    "servlet-filters-and-interceptors",
    "messaging",
    "cache",
    "scheduler",
    "views-and-static-resources",
    "lifecycle",
}

REQUIRED_FILES = {
    "pack.json",
    "support-matrix.json",
    "version-matrix.json",
    "source-fingerprint/manifest.json",
    "source-fingerprint/evidence.json",
    "contracts/framework-contract-model.json",
    "target-profile/profile.json",
    "target-profile/dependency-locks/spring-boot-3.5.3.properties",
    "recipes/manifest.json",
    "recipes/spring-framework-5.3-mvc-to-spring-boot-3.5.3.yml",
    "adapters/runtime-adapter.json",
    "compatibility/manifest.json",
    "coexistence/manifest.json",
    "corpus/development/reference-inputs.json",
    "corpus/development/legacy-spring-mvc/pom.xml",
    "corpus/development/legacy-spring-mvc/src/main/webapp/WEB-INF/web.xml",
    "corpus/development/legacy-spring-mvc/src/main/resources/WEB-INF/spring/root-context.xml",
    "corpus/development/legacy-spring-mvc/src/main/resources/WEB-INF/spring/servlet-context.xml",
    "corpus/development/negative/README.md",
    "corpus/holdout/reference-inputs.json",
    "corpus/real-repository/reference-inputs.json",
    "certification/evidence.json",
    "certification/certification.json",
    "certification/gate-report.md",
    "certification/gap-inventory.md",
}

RUNTIME_GATE_FIELDS = {
    "source_build",
    "source_startup",
    "openrewrite_execution",
    "target_build",
    "target_startup",
    "behavior_equivalence",
    "negative_corpus",
    "holdout",
    "representative_repository",
    "authorized_customer_repository",
    "rootless_transformer",
    "rootless_verifier",
    "rootless_runner",
    "independent_review",
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the fail-closed traditional Spring MVC Batch 30 pack."
    )
    parser.add_argument("--pack-dir", default=str(DEFAULT_PACK))
    args = parser.parse_args()
    pack = Path(args.pack_dir).resolve()
    errors: list[str] = []

    for relative in sorted(REQUIRED_FILES):
        if not (pack / relative).is_file():
            errors.append(f"missing required file: {relative}")

    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1

    manifest = load(pack / "pack.json")
    certification = load(pack / "certification/certification.json")
    evidence = load(pack / "certification/evidence.json")
    support = load(pack / "support-matrix.json")
    version_matrix = load(pack / "version-matrix.json")
    fingerprint = load(pack / "source-fingerprint/manifest.json")
    fingerprint_evidence = load(pack / "source-fingerprint/evidence.json")
    fcm = load(pack / "contracts/framework-contract-model.json")
    target = load(pack / "target-profile/profile.json")
    recipe = load(pack / "recipes/manifest.json")
    adapter = load(pack / "adapters/runtime-adapter.json")

    if manifest.get("pack_key") != PACK_KEY:
        errors.append("pack_key is not exact")
    if manifest.get("mode") != "modernization":
        errors.append("pack mode must be modernization")
    if manifest.get("status") != "experimental":
        errors.append("pack status must remain experimental")
    if manifest.get("source", {}).get("framework") != "spring-framework-mvc":
        errors.append("source framework must be spring-framework-mvc")
    if manifest.get("source", {}).get("framework_versions") != ["5.3.39"]:
        errors.append("source framework version must be exactly 5.3.39")
    if manifest.get("source", {}).get("runtime_versions") != ["11"]:
        errors.append("source Java version must be exactly 11")
    if manifest.get("source", {}).get("build_tools") != ["maven-3.9.11"]:
        errors.append("source Maven version must be exactly 3.9.11")
    if manifest.get("target", {}).get("framework_versions") != ["3.5.3"]:
        errors.append("target Spring Boot version must be exactly 3.5.3")
    if manifest.get("target", {}).get("runtime_versions") != ["21"]:
        errors.append("target Java version must be exactly 21")
    if manifest.get("target", {}).get("build_tools") != ["maven-3.9.11"]:
        errors.append("target Maven version must be exactly 3.9.11")

    statuses = {item.get("status") for item in support.get("capabilities", [])}
    if statuses & {"supported", "certified"}:
        errors.append("experimental pack cannot contain supported/certified capabilities")
    if len(support.get("capabilities", [])) != len(
        {item.get("id") for item in support.get("capabilities", [])}
    ):
        errors.append("support capability ids must be unique")

    fcm_domains = {item.get("domain") for item in fcm.get("capabilities", [])}
    missing_domains = EXPECTED_DOMAINS - fcm_domains
    if missing_domains:
        errors.append(f"FCM missing domains: {sorted(missing_domains)}")
    for item in fcm.get("capabilities", []):
        if item.get("behavior_verification_status") != "NOT_RUN":
            errors.append(f"FCM behavior status must remain NOT_RUN: {item.get('id')}")
        if not item.get("obligations"):
            errors.append(f"FCM capability lacks obligations: {item.get('id')}")
        if not item.get("target_strategy"):
            errors.append(f"FCM capability lacks target strategy: {item.get('id')}")
    if fcm.get("extraction_status") != "NOT_RUN":
        errors.append("FCM extraction must remain NOT_RUN")

    if fingerprint.get("exact_tuple", {}).get("framework_version") != "5.3.39":
        errors.append("fingerprint tuple is not exact")
    if fingerprint_evidence.get("execution_status") != "NOT_RUN":
        errors.append("source fingerprint evidence must remain NOT_RUN")
    if fingerprint_evidence.get("coverage") is not None:
        errors.append("unexecuted source fingerprint cannot claim coverage")

    if target.get("framework_versions") != ["3.5.3"]:
        errors.append("target profile framework tuple is not exact")
    if target.get("runtime_versions") != ["21"]:
        errors.append("target profile runtime tuple is not exact")
    if target.get("build", {}).get("execution_status") != "NOT_RUN":
        errors.append("target build must remain NOT_RUN")
    if target.get("startup", {}).get("execution_status") != "NOT_RUN":
        errors.append("target startup must remain NOT_RUN")

    if recipe.get("deterministic") is not True:
        errors.append("recipe must be deterministic")
    if recipe.get("rewrite_spring") != "6.35.0":
        errors.append("rewrite-spring must be pinned to 6.35.0")
    if recipe.get("rewrite_maven_plugin") != "6.44.0":
        errors.append("rewrite Maven plugin must be pinned to 6.44.0")
    if recipe.get("execution_status") != "NOT_RUN":
        errors.append("recipe execution must remain NOT_RUN")

    if adapter.get("implementation") != "NOT_WIRED":
        errors.append("experimental pack must not claim runtime wiring")
    if adapter.get("route_catalog_registration") != "NOT_PRESENT":
        errors.append("route catalog registration must remain absent")
    if adapter.get("local_execution_port_registration") != "NOT_PRESENT":
        errors.append("local execution port registration must remain absent")

    if certification.get("status") != "experimental":
        errors.append("certification status must remain experimental")
    if certification.get("certification_decision") != "NOT_CERTIFIED":
        errors.append("certification decision must remain NOT_CERTIFIED")
    gate_results = certification.get("gate_results", {})
    for field in sorted(RUNTIME_GATE_FIELDS):
        if gate_results.get(field) != "NOT_RUN":
            errors.append(f"runtime gate must remain NOT_RUN: {field}")
    for value in certification.get("metrics", {}).values():
        if value is not None:
            errors.append("unexecuted certification metrics must remain null")
            break

    if evidence.get("runs") != []:
        errors.append("unexecuted evidence cannot contain runs")
    if evidence.get("metric_status") != "NOT_RUN":
        errors.append("evidence metric status must remain NOT_RUN")
    if evidence.get("external_execution_status") != "NOT_RUN":
        errors.append("external execution must remain NOT_RUN")
    for value in evidence.get("metrics", {}).values():
        if value is not None:
            errors.append("unexecuted evidence metrics must remain null")
            break

    for corpus in ("holdout", "real-repository"):
        corpus_manifest = load(pack / f"corpus/{corpus}/reference-inputs.json")
        if corpus_manifest.get("execution_status") != "NOT_RUN":
            errors.append(f"{corpus} execution must remain NOT_RUN")
        if corpus_manifest.get("inputs") != []:
            errors.append(f"{corpus} inputs must remain empty until selected")

    pom = (pack / "corpus/development/legacy-spring-mvc/pom.xml").read_text(encoding="utf-8")
    for token in (
        "<packaging>war</packaging>",
        "<maven.compiler.release>11</maven.compiler.release>",
        "<spring-framework.version>5.3.39</spring-framework.version>",
        "<servlet-api.version>4.0.1</servlet-api.version>",
    ):
        if token not in pom:
            errors.append(f"fixture POM missing exact token: {token}")

    recipe_text = (
        pack / "recipes/spring-framework-5.3-mvc-to-spring-boot-3.5.3.yml"
    ).read_text(encoding="utf-8")
    for token in (
        "UpgradeToJava21",
        "UpgradeSpringFramework_6_2",
        "spring-boot-starter-web",
        "version: 3.5.3",
    ):
        if token not in recipe_text:
            errors.append(f"recipe missing deterministic step: {token}")
    if "latest" in recipe_text.lower():
        errors.append("recipe must not use latest")

    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"OK: {pack} status=experimental decision=NOT_CERTIFIED execution=NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
