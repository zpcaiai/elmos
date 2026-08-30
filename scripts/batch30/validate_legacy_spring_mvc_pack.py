#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


PACK_KEY = "spring-framework-5-3-mvc-to-spring-boot-3-5-3"
SOURCE_COMMIT = "7e1c098541143c96cce7d9a637fffe57d0e2baae"
SOURCE_GIT_TREE_SHA = "4e1a0354cb51cfb2479ea049063226d3a9df2b67"
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.batch30.certification_campaign import (  # noqa: E402
    CampaignError,
    validate_campaign_plan,
)

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
    "target-profile/scaffold/manifest.json",
    "target-profile/scaffold/materialize_target.py",
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
    "corpus/development/legacy-spring-mvc/src/test/java/io/elmos/legacy/web/LegacyOrderControllerTest.java",
    "corpus/development/negative/README.md",
    "corpus/holdout/reference-inputs.json",
    "corpus/real-repository/reference-inputs.json",
    "corpus/customer/README.md",
    "corpus/customer/reference-inputs.json",
    "certification/evidence.json",
    "certification/certification.json",
    "certification/p0-p11-campaign.json",
    "certification/gate-report.md",
    "certification/gap-inventory.md",
}

LOCAL_RUNTIME_GATE_FIELDS = {
    "source_build",
    "source_startup",
    "openrewrite_execution",
    "target_build",
    "target_startup",
    "behavior_equivalence",
}

EXTERNAL_RUNTIME_GATE_FIELDS = {
    "negative_corpus",
    "holdout",
    "representative_repository",
    "authorized_customer_repository",
    "customer_holdout",
    "customer_acceptance",
    "rootless_transformer",
    "rootless_verifier",
    "rootless_runner",
    "independent_review",
    "external_certification",
}

LOCAL_EVIDENCE_REQUIRED_SUFFIXES = {
    "exact-tuple-binding.json",
    "qualification-policy.json",
    "supplemental/supplemental-index.json",
    "supplemental/supplemental-local-evidence.json",
    "supplemental/sbom-local-inventory.json",
    "supplemental/source-artifacts/legacy-spring-mvc-5.3.39.war",
    "supplemental/raw/source-build.log",
    "supplemental/raw/source-rollback.log",
    "supplemental/raw/target-ab.txt",
    "supplemental/raw/target-startup.log",
}
EXPECTED_HARNESS_FILES = {
    "pom.xml",
    "apps/java-engine-worker/src/main/java/io/elmos/worker/LocalSpringUpgradeExecutionPort.java",
    "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringCapabilityFingerprint.java",
    "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringDeploymentGuidance.java",
    "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringFeatureCatalog.java",
    "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringMvcExactTargetMaterializer.java",
    "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringMvcWarRuntime.java",
    "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringRouteCatalog.java",
    "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringUpgradeModels.java",
    "apps/java-engine-worker/src/main/resources/rewrite/spring-framework-5.3-mvc-to-spring-boot-3.5.3.yml",
    "apps/java-engine-worker/src/main/resources/spring-mvc/exact-5.3.39-fixture-manifest.json",
    "apps/java-engine-worker/src/main/resources/spring-mvc/target-profile/profile.json",
    "apps/java-engine-worker/src/main/resources/spring-mvc/target-profile/scaffold-manifest.json",
    "apps/java-engine-worker/src/test/java/io/elmos/worker/SpringMvcExactLocalQualificationIT.java",
    "recipes/elmos-java-recipes/pom.xml",
    "recipes/elmos-java-recipes/src/main/java/io/elmos/recipes/RewriteSpringFoundation.java",
    "recipes/elmos-java-recipes/src/main/java/io/elmos/recipes/SpringSecurityLambdaChain.java",
    "recipes/elmos-java-recipes/src/test/java/io/elmos/recipes/RewriteSpringFoundationTest.java",
    "recipes/elmos-java-recipes/src/test/java/io/elmos/recipes/SpringSecurityLambdaChainTest.java",
}
EXPECTED_RECIPE_SEED_FILES = {
    "io/elmos/elmos-parent/0.1.0-SNAPSHOT/elmos-parent-0.1.0-SNAPSHOT.pom": {
        "bytes": 10_461,
        "sha256": "ada08c7433515cf79992c725f180ef12398803b4eb1372444821cc951e10efa8",
    },
    "io/elmos/elmos-java-recipes/0.1.0-SNAPSHOT/"
    "elmos-java-recipes-0.1.0-SNAPSHOT.pom": {
        "bytes": 751,
        "sha256": "22775dc1c4ceebb891eccd4f6c10f8e4e4f63c1ccdf7a909935b81df7b9f311a",
    },
    "io/elmos/elmos-java-recipes/0.1.0-SNAPSHOT/"
    "elmos-java-recipes-0.1.0-SNAPSHOT.jar": {
        "bytes": 7_464,
        "sha256": "a2291b649d9d84a36f455e3ef8eb477efdfda9a05c6b9026b76391d8e6a0d45c",
    },
}
EXPECTED_RECIPE_BINDING = {
    "coordinate": "io.elmos:elmos-java-recipes:0.1.0-SNAPSHOT",
    "build_output_timestamp": "2026-08-28T00:00:00Z",
    "jar_sha256": "sha256:"
    "a2291b649d9d84a36f455e3ef8eb477efdfda9a05c6b9026b76391d8e6a0d45c",
    "recipe_pom_sha256": "sha256:"
    "22775dc1c4ceebb891eccd4f6c10f8e4e4f63c1ccdf7a909935b81df7b9f311a",
    "parent_pom_sha256": "sha256:"
    "ada08c7433515cf79992c725f180ef12398803b4eb1372444821cc951e10efa8",
    "files": [
        {"path": path, **value}
        for path, value in sorted(EXPECTED_RECIPE_SEED_FILES.items())
    ],
}
CONTROLLED_TARGET_PROFILE_RESOURCES = (
    {
        "pack_path": "target-profile/profile.json",
        "worker_path": "apps/java-engine-worker/src/main/resources/spring-mvc/target-profile/profile.json",
        "resource": "classpath:/spring-mvc/target-profile/profile.json",
        "bytes": 3731,
        "sha256": "8042f1bed7cde57d13e9794b7a694437d5b12d40f0eb4948c656d942a9297ee1",
    },
    {
        "pack_path": "target-profile/scaffold/manifest.json",
        "worker_path": "apps/java-engine-worker/src/main/resources/spring-mvc/target-profile/scaffold-manifest.json",
        "resource": "classpath:/spring-mvc/target-profile/scaffold-manifest.json",
        "bytes": 1773,
        "sha256": "a2e741b1a535c690633b27e0301f6931ad287e2b0ddd3fefb97cb5194d5819d6",
    },
)
EXPECTED_MATERIALIZER_GENERATOR_BINDING = {
    "materializer_contract_sha256": "c49c796656a34391b892b4a61973161aafce778a4cfc742e5dfb1f0e2eb27f24",
    "input_manifest_sha256": "f982de2d2daca2247f5f3efa788a64f653bb2d576a4c8516fafc0cd96d34fe74",
    "recipe_sha256": "e6b648f5dfdf350c1f6ac0ccc9636b40453af13a48e18974076e455dc872b75b",
    "controlled_target_profile_resources": [
        {
            "resource": item["resource"],
            "bytes": item["bytes"],
            "sha256": item["sha256"],
        }
        for item in CONTROLLED_TARGET_PROFILE_RESOURCES
    ],
}
EXPECTED_LOCAL_ARTIFACT_PATHS = {
    "source executed WAR": "artifacts/executed-source-spring-mvc-5.3.39.war",
    "download artifact": "artifacts/migrated-spring-boot-3.5.3.zip",
    "executed WAR": "artifacts/executed-spring-boot-3.5.3.war",
}
REQUIRED_LOCAL_RAW_EVIDENCE_PATHS = {
    "evidence/complex-capability-verification.json",
    "evidence/control.log",
    "evidence/framework-contract-model.json",
    "evidence/route-selection.json",
    "evidence/source-build.log",
    "evidence/source-snapshot-manifest.json",
    "evidence/source-startup.log",
    "evidence/source-test-summary.json",
    "evidence/spring-mvc-http-oracle.json",
    "evidence/target-build.log",
    "evidence/target-materialization-receipt.json",
    "evidence/target-materialization-source-map.json",
    "evidence/target-startup.log",
    "evidence/target-test-summary.json",
    "evidence/test-parity.json",
}
LOCAL_FCM_STATUSES = {
    "mvc-dispatch-and-json": "PASSED_LOCAL_EXACT_FIXTURE",
    "bean-validation-and-error-shape": "PASSED_LOCAL_EXACT_FIXTURE",
    "controller-advice-errors": "PASSED_LOCAL_EXACT_FIXTURE",
    "filter-interceptor-order": "PARTIAL_PASSED_LOCAL_EXACT_FIXTURE",
    "view-resolution-and-resources": "PARTIAL_PASSED_LOCAL_EXACT_FIXTURE",
    "servlet-to-boot-lifecycle": "PASSED_LOCAL_EXACT_FIXTURE",
}

MAVEN_NAMESPACE = "http://maven.apache.org/POM/4.0.0"
POM_PROPERTIES = {
    "maven.compiler.release": "11",
    "spring-framework.version": "5.3.39",
    "servlet-api.version": "4.0.1",
    "hamcrest.version": "2.2",
    "json-path.version": "2.7.0",
}
TEST_DEPENDENCIES = {
    ("org.hamcrest", "hamcrest"): "${hamcrest.version}",
    ("com.jayway.jsonpath", "json-path"): "${json-path.version}",
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def validate_controlled_target_profile_resources(pack: Path) -> list[str]:
    errors: list[str] = []
    for binding in CONTROLLED_TARGET_PROFILE_RESOURCES:
        pack_path = pack / binding["pack_path"]
        worker_path = ROOT / binding["worker_path"]
        for label, path in (("pack", pack_path), ("worker", worker_path)):
            if not path.is_file() or path.is_symlink():
                errors.append(
                    f"controlled target profile {label} resource is missing or unsafe: "
                    f"{binding['pack_path'] if label == 'pack' else binding['worker_path']}"
                )
                continue
            if path.stat().st_size != binding["bytes"] or digest(path) != binding["sha256"]:
                errors.append(
                    f"controlled target profile {label} resource drifted: "
                    f"{binding['pack_path'] if label == 'pack' else binding['worker_path']}"
                )
        if pack_path.is_file() and worker_path.is_file() and (
            pack_path.read_bytes() != worker_path.read_bytes()
        ):
            errors.append(
                f"controlled target profile worker mirror is not byte-identical: "
                f"{binding['pack_path']}"
            )
    return errors


def validate_exact_tuple_binding(
    evidence_root: Path,
    receipt: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    binding_path = evidence_root / "exact-tuple-binding.json"
    policy_path = evidence_root / "qualification-policy.json"
    try:
        binding = load(binding_path)
        policy = load(policy_path)
    except (OSError, ValueError) as exc:
        return [f"exact tuple binding or qualification policy is invalid JSON: {exc}"]

    binding_ref = receipt.get("exact_tuple_binding")
    if binding_ref != {
        "path": "exact-tuple-binding.json",
        "sha256": f"sha256:{digest(binding_path)}",
    }:
        errors.append("local qualification receipt does not bind exact tuple bytes")
    policy_ref = receipt.get("policy_snapshot")
    if policy_ref != {
        "path": "qualification-policy.json",
        "sha256": f"sha256:{digest(policy_path)}",
    }:
        errors.append("local qualification receipt does not bind qualification policy bytes")

    source = binding.get("source", {})
    target = binding.get("target", {})
    if binding.get("schema_version") != 1 or binding.get("pack_key") != PACK_KEY:
        errors.append("exact tuple binding schema or pack key is not exact")
    if source.get("commit") != receipt.get("source_commit"):
        errors.append("exact tuple binding source commit does not match the receipt")
    if (
        source.get("git_tree_sha") != receipt.get("source_git_tree_sha")
        or source.get("git_tree_sha") != SOURCE_GIT_TREE_SHA
    ):
        errors.append("exact tuple binding source Git tree does not match the pinned corpus tree")
    if source.get("snapshot_sha256") != f"sha256:{receipt.get('source_snapshot_sha256')}":
        errors.append("exact tuple binding source snapshot does not match the receipt")
    expected_source = {
        "framework": "spring-framework-mvc",
        "framework_version": "5.3.39",
        "java": "11.0.26",
        "maven": "3.9.11",
        "servlet_namespace": "javax.servlet",
        "servlet_api": "4.0.1",
        "packaging": "war",
    }
    for field, expected in expected_source.items():
        if source.get(field) != expected:
            errors.append(f"exact tuple binding source {field} drifted")
    source_artifact = receipt.get("source", {}).get("executed_war", {})
    expected_source_artifact = {
        "artifact_path": source_artifact.get("path"),
        "artifact_sha256": f"sha256:{source_artifact.get('sha256')}",
        "artifact_bytes": source_artifact.get("bytes"),
        "artifact_format": "spring-framework-mvc-war",
    }
    for field, expected in expected_source_artifact.items():
        if source.get(field) != expected:
            errors.append(f"exact tuple binding source {field} drifted")

    receipt_target = receipt.get("target", {})
    executed_war = receipt_target.get("executed_war", {})
    expected_target = {
        "artifact_path": executed_war.get("path"),
        "artifact_sha256": f"sha256:{executed_war.get('sha256')}",
        "artifact_bytes": executed_war.get("bytes"),
        "artifact_format": "spring-boot-executable-war",
        "framework": "spring-boot",
        "framework_version": "3.5.3",
        "spring_framework_version": "6.2.8",
        "java": "21.0.11",
        "maven": "3.9.11",
        "servlet_namespace": "jakarta.servlet",
        "servlet_api": "6.1",
        "embedded_tomcat": "10.1.42",
        "packaging": "executable-war",
    }
    for field, expected in expected_target.items():
        if target.get(field) != expected:
            errors.append(f"exact tuple binding target {field} drifted")
    if target.get("manifest") != executed_war.get("manifest"):
        errors.append("exact tuple binding target manifest does not match the receipt")

    source_receipt = receipt.get("source", {})
    target_receipt = receipt.get("target", {})
    target_tomcat = target_receipt.get("embedded_tomcat_core", {})
    expected_toolchains = {
        "source-java": f"sha256:{source_receipt.get('java_release', {}).get('sha256')}",
        "source-maven": f"sha256:{source_receipt.get('maven_archive', {}).get('sha256')}",
        "source-container": f"sha256:{source_receipt.get('tomcat_archive', {}).get('sha256')}",
        "target-java": f"sha256:{target_receipt.get('java_release', {}).get('sha256')}",
        "target-maven": f"sha256:{source_receipt.get('maven_archive', {}).get('sha256')}",
        "target-container": f"sha256:{target_tomcat.get('sha256')}",
    }
    exact_toolchain = binding.get("toolchain", {})
    expected_exact_toolchain = {
        "maven_archive_sha256": expected_toolchains["source-maven"],
        "maven_archive_sha512": f"sha512:{source_receipt.get('maven_archive', {}).get('sha512')}",
        "source_java_release_sha256": expected_toolchains["source-java"],
        "source_tomcat_archive_sha256": expected_toolchains["source-container"],
        "source_tomcat_archive_sha512": f"sha512:{source_receipt.get('tomcat_archive', {}).get('sha512')}",
        "source_tomcat_version": "9.0.120",
        "target_java_release_sha256": expected_toolchains["target-java"],
        "target_tomcat_core_entry": "WEB-INF/lib-provided/tomcat-embed-core-10.1.42.jar",
        "target_tomcat_core_sha256": expected_toolchains["target-container"],
    }
    if exact_toolchain != expected_exact_toolchain:
        errors.append("exact tuple binding toolchain content identities drifted")

    transformation = binding.get("transformation", {})
    expected_recipe_transformation = {
        "custom_recipe_coordinate": EXPECTED_RECIPE_BINDING["coordinate"],
        "custom_recipe_build_output_timestamp":
            EXPECTED_RECIPE_BINDING["build_output_timestamp"],
        "custom_recipe_artifact_sha256": EXPECTED_RECIPE_BINDING["jar_sha256"],
        "custom_recipe_pom_sha256": EXPECTED_RECIPE_BINDING["recipe_pom_sha256"],
        "custom_recipe_parent_pom_sha256":
            EXPECTED_RECIPE_BINDING["parent_pom_sha256"],
    }
    for field, expected in expected_recipe_transformation.items():
        if transformation.get(field) != expected:
            errors.append(f"exact tuple binding rewrite recipe {field} drifted")

    policy_digest = f"sha256:{digest(policy_path)}"
    if policy.get("schema_version") != 1 or policy.get("scope") != "LOCAL_ENGINEERING_EXACT_FIXTURE_ONLY":
        errors.append("qualification policy schema or scope is not exact")
    if policy.get("source_commit") != receipt.get("source_commit"):
        errors.append("qualification policy source commit does not match the receipt")
    if policy.get("target_artifact", {}).get("sha256") != expected_target["artifact_sha256"]:
        errors.append("qualification policy target artifact does not match the receipt")
    if binding.get("policy", {}).get("sha256") != policy_digest:
        errors.append("exact tuple binding policy digest does not match policy bytes")
    if policy.get("toolchain_bindings") != expected_toolchains:
        errors.append("qualification policy toolchain bindings do not match executed bytes")
    if policy.get("rewrite_recipe_artifact") != EXPECTED_RECIPE_BINDING:
        errors.append("qualification policy rewrite recipe artifact binding drifted")
    policy_evidence = policy.get("evidence_policy", {})
    if policy_evidence.get("external_evidence_status") != "NOT_RUN":
        errors.append("qualification policy external evidence status must remain NOT_RUN")
    if policy_evidence.get("certification_status") != "NOT_CERTIFIED":
        errors.append("qualification policy certification status must remain NOT_CERTIFIED")
    if policy_evidence.get("signature_algorithm") != "Ed25519":
        errors.append("qualification policy signature algorithm must remain Ed25519")
    if policy_evidence.get("required_evidence_types") != [
        "source_build",
        "target_build",
        "source_startup",
        "target_startup",
        "behavioral_equivalence",
        "security",
        "performance",
        "operability",
        "sbom",
        "rollback",
        "independent_review",
        "customer_acceptance",
        "external_certification",
    ]:
        errors.append("qualification policy must enumerate the exact 13 evidence types")
    controls = policy.get("controls", {})
    expected_controls = {
        "application_egress": "DENY",
        "customer_data": False,
        "credential_access": False,
        "dependency_resolution": "DECLARED_MAVEN_REPOSITORIES_ONLY",
        "external_certification_promotion": False,
        "production_deployment": False,
        "source_tree_mutation": "DENY",
        "target_artifact_overwrite": False,
        "workspace": "EPHEMERAL_ISOLATED",
    }
    if controls != expected_controls:
        errors.append("qualification policy controls are not the approved fail-closed set")
    return errors


def validate_supplemental_evidence(
    evidence_root: Path,
    receipt: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    supplemental_root = evidence_root / "supplemental"
    index_path = supplemental_root / "supplemental-index.json"
    evidence_path = supplemental_root / "supplemental-local-evidence.json"
    bom_path = supplemental_root / "sbom-local-inventory.json"
    try:
        index = load(index_path)
        supplemental = load(evidence_path)
        bom = load(bom_path)
    except (OSError, ValueError) as exc:
        return [f"supplemental local evidence is invalid JSON: {exc}"]

    expected_files = {
        "raw/source-build.log",
        "raw/source-rollback.log",
        "raw/target-ab.txt",
        "raw/target-startup.log",
        "sbom-local-inventory.json",
        "source-artifacts/legacy-spring-mvc-5.3.39.war",
        "supplemental-local-evidence.json",
    }
    items = index.get("files")
    indexed = {
        item.get("path"): item
        for item in items
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    } if isinstance(items, list) else {}
    if index.get("schema_version") != 1 or index.get("index_does_not_self_reference") is not True:
        errors.append("supplemental evidence index schema or self-reference guard is invalid")
    if set(indexed) != expected_files:
        errors.append("supplemental evidence index file inventory is incomplete or has extras")
    for relative, item in indexed.items():
        candidate = supplemental_root / relative
        if candidate.is_symlink() or not candidate.is_file():
            errors.append(f"supplemental evidence file is missing or unsafe: {relative}")
            continue
        if item.get("bytes") != candidate.stat().st_size or item.get("sha256") != digest(candidate):
            errors.append(f"supplemental evidence digest or size mismatch: {relative}")

    binding = supplemental.get("binding", {})
    target = receipt.get("target", {}).get("executed_war", {})
    if supplemental.get("evidence_class") != "LOCAL_ENGINEERING_SUPPLEMENTAL":
        errors.append("supplemental evidence class is not local engineering")
    if binding.get("source_commit") != receipt.get("source_commit"):
        errors.append("supplemental evidence source commit does not match the receipt")
    if binding.get("target_artifact_sha256") != f"sha256:{target.get('sha256')}":
        errors.append("supplemental evidence target artifact digest does not match the receipt")
    if binding.get("target_artifact_bytes") != target.get("bytes"):
        errors.append("supplemental evidence target artifact size does not match the receipt")
    if binding.get("policy_sha256") != receipt.get("policy_snapshot", {}).get("sha256"):
        errors.append("supplemental evidence policy digest does not match the receipt")
    source_artifact = supplemental_root / "source-artifacts/legacy-spring-mvc-5.3.39.war"
    source_digest = f"sha256:{digest(source_artifact)}" if source_artifact.is_file() else None
    if binding.get("source_war_sha256") != source_digest:
        errors.append("supplemental evidence source WAR digest is not content-bound")
    if binding.get("source_war_path") != "source-artifacts/legacy-spring-mvc-5.3.39.war":
        errors.append("supplemental evidence source WAR path is not exact")
    if binding.get("source_war_bytes") != source_artifact.stat().st_size:
        errors.append("supplemental evidence source WAR size is not content-bound")

    if supplemental.get("status_boundary") != {
        "external_evidence": "NOT_RUN",
        "local_runner_may_certify": False,
        "local_supplemental": "RECORDED_LOCAL_ONLY",
        "production_certification": "NOT_CERTIFIED",
    }:
        errors.append("supplemental evidence status boundary is unsafe")
    observations = supplemental.get("observations", {})
    security = observations.get("security", {})
    if security.get("status") != "PARTIAL_LOCAL" or security.get("vulnerability_scan") != "NOT_RUN_TOOL_UNAVAILABLE":
        errors.append("supplemental security result must remain partial without a vulnerability scanner")
    performance = observations.get("performance", {})
    if performance.get("status") != "PASSED_LOCAL_BENCHMARK" or performance.get("capacity_validation") != "NOT_RUN_NO_SLO_BOUND":
        errors.append("supplemental performance result must remain a local benchmark without an SLO")
    if performance.get("complete_requests") != 200 or performance.get("concurrency") != 8:
        errors.append("supplemental performance workload is not the fixed 200/8 workload")
    sbom = observations.get("sbom", {})
    if sbom.get("status") != "PARTIAL_LOCAL_INVENTORY_ONLY" or sbom.get("artifact_bound") is not True:
        errors.append("supplemental SBOM result must remain a local artifact-bound inventory")
    if not isinstance(sbom.get("component_count"), int) or sbom.get("component_count", 0) <= 0:
        errors.append("supplemental SBOM must contain at least one component")
    if sbom.get("vulnerability_scan") != "NOT_RUN_TOOL_UNAVAILABLE":
        errors.append("supplemental SBOM vulnerability scan must remain NOT_RUN")
    if bom.get("bomFormat") != "CycloneDX" or bom.get("specVersion") != "1.5":
        errors.append("supplemental SBOM format must be CycloneDX 1.5")
    if len(bom.get("components", [])) != sbom.get("component_count"):
        errors.append("supplemental SBOM component count is not self-consistent")
    bom_hashes = bom.get("metadata", {}).get("component", {}).get("hashes", [])
    if not bom_hashes or bom_hashes[0].get("content") != target.get("sha256"):
        errors.append("supplemental SBOM metadata is not bound to the target artifact")

    operability = observations.get("operability", {})
    if operability.get("status") != "PASSED_LOCAL" or operability.get("loopback_only") is not True:
        errors.append("supplemental operability result is not loopback-only local evidence")
    rollback = observations.get("rollback", {})
    if rollback.get("status") != "PASSED_LOCAL_ISOLATED_ROLLBACK_REHEARSAL" or rollback.get("production_rollback") != "NOT_RUN":
        errors.append("supplemental rollback result must remain isolated local rehearsal")
    if rollback.get("sequence") != [
        "target_startup_readiness",
        "target_stop",
        "source_startup_readiness",
        "source_probe",
        "source_stop",
    ]:
        errors.append("supplemental rollback sequence is not exact")
    if rollback.get("source_build", {}).get("status") != "PASSED_LOCAL":
        errors.append("supplemental rollback source build is not PASSED_LOCAL")
    for name in ("target", "source"):
        shutdown = rollback.get("shutdowns", {}).get(name, {})
        if shutdown.get("bounded") is not True:
            errors.append(f"supplemental rollback {name} shutdown is not bounded")
    for field in ("independent_holdout", "representative_customer_scenario", "external_signatures"):
        if observations.get(field) != "NOT_RUN":
            errors.append(f"supplemental {field} must remain NOT_RUN")

    for relative, needle in (
        ("raw/source-build.log", "BUILD SUCCESS"),
        ("raw/source-rollback.log", "Apache Tomcat/9.0.120"),
        ("raw/target-startup.log", "Spring Boot ::                (v3.5.3)"),
        ("raw/target-startup.log", "Java 21.0.11"),
        ("raw/target-startup.log", "Apache Tomcat/10.1.42"),
        ("raw/target-ab.txt", "Complete requests:      200"),
        ("raw/target-ab.txt", "Failed requests:        0"),
    ):
        if needle not in (supplemental_root / relative).read_text(encoding="utf-8", errors="replace"):
            errors.append(f"supplemental raw evidence is missing expected marker: {relative}: {needle}")
    return errors


def discover_local_evidence(
    evidence: dict[str, Any],
) -> tuple[Path, Path]:
    runs = evidence.get("runs")
    if not isinstance(runs, list) or len(runs) != 1 or not isinstance(runs[0], dict):
        raise ValueError("exact local evidence must declare one run")
    raw_index = runs[0].get("evidence_index")
    if not isinstance(raw_index, str) or not raw_index or "\\" in raw_index:
        raise ValueError("local evidence index path must be a POSIX relative path")
    index_relative = Path(raw_index)
    if index_relative.is_absolute() or ".." in index_relative.parts:
        raise ValueError("local evidence index path is unsafe")
    if (
        len(index_relative.parts) < 4
        or index_relative.parts[:2] != ("certification", "local-execution")
        or index_relative.name != "evidence-index.json"
    ):
        raise ValueError("local evidence index must be below certification/local-execution")
    return index_relative.parent, index_relative


def validate_local_evidence(
    pack: Path,
    evidence_relative: Path,
    index_relative: Path,
) -> tuple[list[str], dict[str, Any] | None]:
    errors: list[str] = []
    evidence_root = pack / evidence_relative
    index_path = pack / index_relative
    if not index_path.is_file() or index_path.is_symlink():
        return [f"local evidence index missing or unsafe: {index_relative}"], None
    try:
        index = load(index_path)
    except (OSError, ValueError) as exc:
        return [f"local evidence index is not valid JSON: {exc}"], None
    if index.get("pack_key") != PACK_KEY:
        errors.append("local evidence index pack_key is not exact")
    if index.get("status") != "PASSED_LOCAL":
        errors.append("local evidence index status must be PASSED_LOCAL")
    if index.get("claim_scope") != "LOCAL_ENGINEERING_EXACT_FIXTURE_ONLY":
        errors.append("local evidence index claim scope is not exact")
    if index.get("certification_eligible") is not False:
        errors.append("local evidence index must remain certification-ineligible")
    if index.get("external_execution_status") != "NOT_RUN":
        errors.append("local evidence index external status must remain NOT_RUN")

    items = index.get("files")
    if not isinstance(items, list) or not items:
        return errors + ["local evidence index must contain files"], None
    indexed: dict[str, dict[str, Any]] = {}
    real_root = evidence_root.resolve()
    for item in items:
        relative = item.get("path") if isinstance(item, dict) else None
        if not isinstance(relative, str) or not relative or "\\" in relative:
            errors.append("local evidence path must be a non-empty POSIX relative path")
            continue
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts or relative in indexed:
            errors.append(f"local evidence path is unsafe or duplicated: {relative}")
            continue
        candidate = evidence_root / relative_path
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            errors.append(f"indexed local evidence file is missing: {relative}")
            continue
        if not resolved.is_relative_to(real_root) or candidate.is_symlink() or not candidate.is_file():
            errors.append(f"indexed local evidence file escapes or is unsafe: {relative}")
            continue
        if item.get("bytes") != candidate.stat().st_size:
            errors.append(f"indexed local evidence byte count mismatch: {relative}")
        actual_sha = digest(candidate)
        if item.get("sha256") != actual_sha:
            errors.append(f"indexed local evidence sha256 mismatch: {relative}")
        indexed[relative] = item

    receipt_item = indexed.get("local-qualification.json")
    if receipt_item is None:
        return errors + ["local qualification receipt is not bound by the outer index"], None
    receipt_path = evidence_root / "local-qualification.json"
    try:
        receipt = load(receipt_path)
    except (OSError, ValueError) as exc:
        return errors + [f"local qualification receipt is not valid JSON: {exc}"], None
    if receipt.get("schema_version") != "1.1":
        errors.append("local qualification receipt schema must be 1.1")
    if receipt.get("status") != "PASSED_LOCAL" or receipt.get("certified") is not False:
        errors.append("local qualification receipt must be PASSED_LOCAL and uncertified")
    if receipt.get("claim_scope") != "LOCAL_ENGINEERING_EXACT_FIXTURE_ONLY":
        errors.append("local qualification receipt claim scope is not exact")
    if receipt.get("external_execution_status") != "NOT_RUN":
        errors.append("local qualification receipt external status must remain NOT_RUN")
    if receipt.get("route_id") != "spring-framework-5.3-mvc-maven-to-boot-3.5.3-java-21":
        errors.append("local qualification receipt route is not exact")
    if receipt.get("pack_key") != PACK_KEY:
        errors.append("local qualification receipt pack key is not exact")
    if receipt.get("source_commit") != SOURCE_COMMIT:
        errors.append("local qualification receipt source commit is not the pinned commit")
    if receipt.get("source_git_tree_sha") != SOURCE_GIT_TREE_SHA:
        errors.append("local qualification receipt source Git tree is not the pinned corpus tree")
    if not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("source_snapshot_sha256", ""))):
        errors.append("local qualification receipt source snapshot is not content-addressed")
    errors.extend(validate_exact_tuple_binding(evidence_root, receipt))
    errors.extend(validate_supplemental_evidence(evidence_root, receipt))

    source = receipt.get("source", {})
    if source.get("spring_framework") != "5.3.39" or source.get("tomcat") != "9.0.120":
        errors.append("local qualification receipt source toolchain tuple drifted")
    for archive_name, expected_sha, expected_sha512, expected_bytes in (
        (
            "maven_archive",
            "0d7125e8c91097b36edb990ea5934e6c68b4440eef4ea96510a0f6815e7eeadb",
            "03e2d65d4483a3396980629f260e25cac0d8b6f7f2791e4dc20bc83f9514db8d0f05b0479e699a5f34679250c49c8e52e961262ded468a20de0be254d8207076",
            9278421,
        ),
        (
            "tomcat_archive",
            "93306f86baafe13186cc3e705c201040d68b0192a50be667a1f576ee4711db0d",
            "fca7cfbe8255b61fac0e474a9a7ac6fbaf2792c72061fda2666b26eb5ba60718adc4fc0cbd013f14a41f101bcd7f5b70b2d3eedc37554ff0db4bdb6e2e2898f6",
            13697062,
        ),
    ):
        archive = source.get(archive_name, {})
        if archive.get("sha256") != expected_sha or archive.get("bytes") != expected_bytes:
            errors.append(f"local qualification receipt {archive_name} identity drifted")
        if archive.get("sha512") != expected_sha512:
            errors.append(f"local qualification receipt {archive_name} SHA-512 drifted")
    if source.get("java_release") != {
        "path": "release",
        "bytes": 1295,
        "sha256": "09d5fffa5ad3de15dcfd603e747df1e6c9ecdb58f25d333e89661910064e884a",
    }:
        errors.append("local qualification receipt source Java release identity drifted")
    catalina = source.get("catalina_jar", {})
    if catalina.get("sha256") != "540f8b3855dc3d963f6872f5fb10a156985ee9bf8ffc78a9f859eda5675309dd":
        errors.append("local qualification receipt Catalina identity drifted")
    if source.get("tomcat_consumed_manifest_sha256") != "bf6e25983335bc1e3ac471195f4f5d09b65c8b57abdce636a087c6fb6c9c0fcd":
        errors.append("local qualification receipt consumed Tomcat manifest drifted")
    if "Apache Maven 3.9.11" not in str(source.get("maven", "")) or 'version "11.0.26"' not in str(source.get("java", "")):
        errors.append("local qualification receipt source Maven/Java version output drifted")
    source_war = source.get("executed_war", {})
    if source_war.get("format") != "spring-framework-mvc-war":
        errors.append("local qualification receipt source WAR format drifted")
    if (
        not re.fullmatch(r"[0-9a-f]{64}", str(source_war.get("sha256", "")))
        or not isinstance(source_war.get("bytes"), int)
        or source_war.get("bytes", 0) <= 0
    ):
        errors.append("local qualification receipt source WAR is not content-addressed")
    if source_war.get("path") != EXPECTED_LOCAL_ARTIFACT_PATHS["source executed WAR"]:
        errors.append("local qualification receipt source WAR path is not exact")
    indexed_source_war = indexed.get(EXPECTED_LOCAL_ARTIFACT_PATHS["source executed WAR"])
    if (
        indexed_source_war is None
        or source_war.get("bytes") != indexed_source_war.get("bytes")
        or source_war.get("sha256") != indexed_source_war.get("sha256")
    ):
        errors.append("local qualification receipt source WAR is not bound by the outer index")

    target = receipt.get("target", {})
    if target.get("spring_boot") != "3.5.3" or target.get("spring_framework") != "6.2.8" or target.get("embedded_tomcat") != "10.1.42":
        errors.append("local qualification receipt target tuple drifted")
    if "Apache Maven 3.9.11" not in str(target.get("maven", "")) or 'version "21.0.11"' not in str(target.get("java", "")):
        errors.append("local qualification receipt target Maven/Java version output drifted")
    if target.get("java_release") != {
        "path": "release",
        "bytes": 1228,
        "sha256": "7befd86565133fbebfa54138e55ec5b03bb59649ea5dda35d9f9b95265226756",
    }:
        errors.append("local qualification receipt target Java release identity drifted")
    if target.get("embedded_tomcat_core") != {
        "entry": "WEB-INF/lib-provided/tomcat-embed-core-10.1.42.jar",
        "bytes": 3631718,
        "sha256": "c0ca6acafe5ad63cd5de16ec8894318a7b53ea11e3db1bc217fd5f2a9746a790",
    }:
        errors.append("local qualification receipt target Tomcat core identity drifted")
    download = target.get("download_artifact", {})
    executed_war = target.get("executed_war", {})
    if download.get("format") != "migrated-repository-zip" or executed_war.get("format") != "spring-boot-executable-war":
        errors.append("download artifact and executed WAR formats are not distinguished")
    if download.get("path") == executed_war.get("path"):
        errors.append("download artifact and executed WAR must be distinct paths")
    for label, artifact in (("download artifact", download), ("executed WAR", executed_war)):
        if not re.fullmatch(r"[0-9a-f]{64}", str(artifact.get("sha256", ""))) or not isinstance(artifact.get("bytes"), int) or artifact.get("bytes", 0) <= 0:
            errors.append(f"local qualification receipt {label} is not content-addressed")
        expected_path = EXPECTED_LOCAL_ARTIFACT_PATHS[label]
        if artifact.get("path") != expected_path:
            errors.append(f"local qualification receipt {label} path is not exact")
        indexed_artifact = indexed.get(expected_path)
        if indexed_artifact is None:
            errors.append(f"local qualification receipt {label} is not preserved by the outer index")
        elif (
            artifact.get("bytes") != indexed_artifact.get("bytes")
            or artifact.get("sha256") != indexed_artifact.get("sha256")
        ):
            errors.append(f"local qualification receipt {label} does not bind its preserved bytes")
    if executed_war.get("bytes", 0) <= download.get("bytes", 0):
        errors.append("executed WAR must not be confused with the small repository ZIP")
    if executed_war.get("manifest") != {
        "Main-Class": "org.springframework.boot.loader.launch.WarLauncher",
        "Start-Class": "io.elmos.legacy.LegacyMvcApplication",
        "Spring-Boot-Version": "3.5.3",
    }:
        errors.append("executed WAR manifest identity drifted")

    harness = receipt.get("harness", {})
    if not re.fullmatch(r"[0-9a-f]{40}", str(harness.get("repository_head", ""))):
        errors.append("local qualification harness repository head is missing")
    if harness.get("worktree_binding") != "repository-head-plus-content-addressed-files":
        errors.append("local qualification harness does not bind dirty worktree files")
    if harness.get("rewrite_recipe_seed") != EXPECTED_RECIPE_BINDING:
        errors.append("local qualification harness rewrite recipe seed drifted")
    harness_items = harness.get("files", [])
    harness_by_path = {
        item.get("path"): item for item in harness_items if isinstance(item, dict)
    }
    if set(harness_by_path) != EXPECTED_HARNESS_FILES:
        errors.append("local qualification harness file inventory is incomplete")
    else:
        for relative, item in harness_by_path.items():
            candidate = ROOT / relative
            if not candidate.is_file() or candidate.is_symlink():
                errors.append(f"local qualification harness source is missing or unsafe: {relative}")
                continue
            if item.get("bytes") != candidate.stat().st_size or item.get("sha256") != digest(candidate):
                errors.append(f"local qualification harness source digest drifted: {relative}")

    execution = receipt.get("execution", {})
    expected_execution = {
        "source_clean_verify": "PASSED",
        "source_tomcat_startup": "PASSED",
        "openrewrite_actual_execution": True,
        "trusted_java_materializer": "PASSED",
        "target_clean_verify": "PASSED",
        "target_warlauncher_startup": "PASSED",
        "target_actuator_health": "PASSED",
        "get_and_jsp_oracle_comparisons": 2,
        "validation_and_error_contract_tests": "PASSED",
        "bounded_shutdown": "PASSED",
    }
    if execution != expected_execution:
        errors.append("local qualification execution summary is incomplete or drifted")

    receipt_evidence = receipt.get("evidence_files", [])
    receipt_paths = {
        item.get("path") for item in receipt_evidence if isinstance(item, dict)
    }
    missing_raw_evidence = REQUIRED_LOCAL_RAW_EVIDENCE_PATHS - receipt_paths
    if missing_raw_evidence:
        errors.append(
            "local qualification raw evidence inventory is incomplete: "
            + ", ".join(sorted(missing_raw_evidence))
        )
    expected_index_paths = receipt_paths | {
        "exact-tuple-binding.json",
        "local-qualification.json",
        "qualification-policy.json",
        *EXPECTED_LOCAL_ARTIFACT_PATHS.values(),
        *{
            f"artifacts/rewrite-recipe-seed/{path}"
            for path in EXPECTED_RECIPE_SEED_FILES
        },
    }
    if set(indexed) != expected_index_paths:
        errors.append("outer evidence index and receipt evidence inventory do not close exactly")
    for item in receipt_evidence:
        if not isinstance(item, dict) or indexed.get(item.get("path")) != item:
            errors.append("receipt evidence entry is not identically bound by the outer index")
            break

    materializer_receipt_relative = "evidence/target-materialization-receipt.json"
    materializer_source_map_relative = "evidence/target-materialization-source-map.json"
    if materializer_receipt_relative not in indexed:
        errors.append("target materialization receipt is not preserved by the evidence index")
    else:
        try:
            materializer_receipt = load(evidence_root / materializer_receipt_relative)
        except (OSError, ValueError) as exc:
            errors.append(f"target materialization receipt is not valid JSON: {exc}")
        else:
            if (
                materializer_receipt.get("pack_key") != PACK_KEY
                or materializer_receipt.get("status")
                != "MATERIALIZED_STATIC_NOT_RUNTIME_VERIFIED"
                or materializer_receipt.get("profile_scope") != "EXACT_FIXTURE_ONLY"
            ):
                errors.append("target materialization receipt identity or scope drifted")
            if (
                materializer_receipt.get("generator_binding")
                != EXPECTED_MATERIALIZER_GENERATOR_BINDING
            ):
                errors.append("target materialization receipt controlled profile binding drifted")
            materializer_execution = materializer_receipt.get("execution", {})
            if not materializer_execution or set(materializer_execution.values()) != {"NOT_RUN"}:
                errors.append("standalone materializer receipt must retain NOT_RUN runtime status")
    if materializer_source_map_relative not in indexed:
        errors.append("target materialization source map is not preserved by the evidence index")
    else:
        try:
            materializer_source_map = load(evidence_root / materializer_source_map_relative)
        except (OSError, ValueError) as exc:
            errors.append(f"target materialization source map is not valid JSON: {exc}")
        else:
            if (
                materializer_source_map.get("schema_version") != 1
                or len(materializer_source_map.get("mappings", [])) != 6
            ):
                errors.append("target materialization source map is incomplete")

    source_summary = load(evidence_root / "evidence/source-test-summary.json") if "evidence/source-test-summary.json" in indexed else {}
    target_summary = load(evidence_root / "evidence/target-test-summary.json") if "evidence/target-test-summary.json" in indexed else {}
    parity = load(evidence_root / "evidence/test-parity.json") if "evidence/test-parity.json" in indexed else {}
    oracle = load(evidence_root / "evidence/spring-mvc-http-oracle.json") if "evidence/spring-mvc-http-oracle.json" in indexed else {}
    route = load(evidence_root / "evidence/route-selection.json") if "evidence/route-selection.json" in indexed else {}
    if (source_summary.get("executed"), source_summary.get("failures"), source_summary.get("errors"), source_summary.get("skipped")) != (6, 0, 0, 0):
        errors.append("local source test summary must prove 6/6")
    if (target_summary.get("executed"), target_summary.get("failures"), target_summary.get("errors"), target_summary.get("skipped")) != (9, 0, 0, 0):
        errors.append("local target test summary must prove 9/9")
    if parity.get("status") != "PASS" or parity.get("preserved_test_identities") != source_summary.get("testIdentities"):
        errors.append("local source/target test identity parity is not exact")
    if oracle.get("status") != "PASS_LOCAL_ENGINEERING" or len(oracle.get("comparisons", [])) != 2:
        errors.append("local HTTP/JSP oracle must contain exactly two passing comparisons")
    if route.get("route_evidence") != "PASSED_LOCAL" or route.get("experimental_opt_in_required") is not False:
        errors.append("local route-selection evidence does not reflect final catalog truth")
    return errors, receipt


def _maven_tag(name: str) -> str:
    return f"{{{MAVEN_NAMESPACE}}}{name}"


def _unique_text(
    parent: ET.Element,
    child_name: str,
    expected: str,
    label: str,
    errors: list[str],
) -> None:
    matches = parent.findall(_maven_tag(child_name))
    if len(matches) != 1:
        errors.append(f"fixture POM {label} must appear exactly once")
        return
    if (matches[0].text or "").strip() != expected:
        errors.append(f"fixture POM {label} must equal {expected}")


def validate_fixture_pom(pom_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        root = ET.parse(pom_path).getroot()
    except (OSError, ET.ParseError) as exc:
        return [f"fixture POM is not valid XML: {exc}"]
    if root.tag != _maven_tag("project"):
        return ["fixture POM root must use the Maven POM namespace"]

    _unique_text(root, "packaging", "war", "packaging", errors)

    property_nodes = root.findall(_maven_tag("properties"))
    if len(property_nodes) != 1:
        errors.append("fixture POM properties must appear exactly once")
    else:
        properties = property_nodes[0]
        for name, expected in POM_PROPERTIES.items():
            _unique_text(properties, name, expected, f"property {name}", errors)

    dependencies_nodes = root.findall(_maven_tag("dependencies"))
    if len(dependencies_nodes) != 1:
        errors.append("fixture POM dependencies must appear exactly once")
        return errors

    dependencies = dependencies_nodes[0].findall(_maven_tag("dependency"))
    for (expected_group, expected_artifact), expected_version in TEST_DEPENDENCIES.items():
        candidates = []
        for dependency in dependencies:
            groups = {
                (item.text or "").strip()
                for item in dependency.findall(_maven_tag("groupId"))
            }
            artifacts = {
                (item.text or "").strip()
                for item in dependency.findall(_maven_tag("artifactId"))
            }
            if expected_group in groups or expected_artifact in artifacts:
                candidates.append(dependency)
        coordinate = f"{expected_group}:{expected_artifact}"
        if len(candidates) != 1:
            errors.append(
                f"fixture POM dependency {coordinate} must appear exactly once"
            )
            continue
        dependency = candidates[0]
        _unique_text(dependency, "groupId", expected_group, f"dependency {coordinate} groupId", errors)
        _unique_text(
            dependency,
            "artifactId",
            expected_artifact,
            f"dependency {coordinate} artifactId",
            errors,
        )
        _unique_text(
            dependency,
            "version",
            expected_version,
            f"dependency {coordinate} version",
            errors,
        )
        _unique_text(dependency, "scope", "test", f"dependency {coordinate} scope", errors)
    return errors


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
    scaffold = load(pack / "target-profile/scaffold/manifest.json")
    recipe = load(pack / "recipes/manifest.json")
    adapter = load(pack / "adapters/runtime-adapter.json")
    campaign = load(pack / "certification/p0-p11-campaign.json")
    local_evidence_relative: Path | None = None
    local_evidence_index: Path | None = None
    try:
        local_evidence_relative, local_evidence_index = discover_local_evidence(evidence)
    except ValueError as exc:
        errors.append(str(exc))
    else:
        for suffix in sorted(LOCAL_EVIDENCE_REQUIRED_SUFFIXES):
            relative = local_evidence_relative / suffix
            candidate = pack / relative
            if candidate.is_symlink() or not candidate.is_file():
                errors.append(f"missing or unsafe local evidence file: {relative}")
    errors.extend(validate_controlled_target_profile_resources(pack))
    try:
        validate_campaign_plan(pack, campaign)
    except (CampaignError, OSError, ValueError) as exc:
        errors.append(f"P0-P11 campaign plan is invalid: {exc}")

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

    expected_source_tuple = "spring-framework-5.3.39-mvc-war-java-11-maven-3.9.11"
    expected_target_tuple = "spring-boot-3.5.3-executable-war-java-21-maven-3.9.11"
    tuples = {item.get("id"): item for item in version_matrix.get("tuples", [])}
    if set(tuples) != {expected_source_tuple, expected_target_tuple}:
        errors.append("version matrix must contain only the exact source and target tuples")
    elif tuples[expected_target_tuple].get("packaging") != "executable-war":
        errors.append("version matrix target must be executable-war")
    edges = version_matrix.get("upgrade_edges", [])
    if len(edges) != 1:
        errors.append("version matrix must contain exactly one directional edge")
    else:
        edge = edges[0]
        if edge.get("from") != expected_source_tuple or edge.get("to") != expected_target_tuple:
            errors.append("version matrix edge does not bind the exact route")
        if edge.get("directional") is not True or edge.get("reverse_supported") is not False:
            errors.append("version matrix edge must remain directional with no reverse support")
        if edge.get("execution_status") != "PASSED_LOCAL":
            errors.append("exact version matrix edge must record PASSED_LOCAL")
        if edge.get("execution_scope") != "LOCAL_ENGINEERING_EXACT_FIXTURE_ONLY":
            errors.append("exact version matrix edge must retain its narrow local scope")
        if edge.get("target_emitter") != "target-profile/scaffold/materialize_target.py":
            errors.append("version matrix edge must bind the controlled target emitter")

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
        expected_status = LOCAL_FCM_STATUSES.get(item.get("id"), "NOT_RUN")
        if item.get("behavior_verification_status") != expected_status:
            errors.append(
                f"FCM behavior status drifted: {item.get('id')} expected {expected_status}"
            )
        if (
            item.get("id") in LOCAL_FCM_STATUSES
            and (
                local_evidence_index is None
                or item.get("evidence_refs") != [str(local_evidence_index)]
            )
        ):
            errors.append(f"locally exercised FCM capability lacks exact evidence: {item.get('id')}")
        if not item.get("obligations"):
            errors.append(f"FCM capability lacks obligations: {item.get('id')}")
        if not item.get("target_strategy"):
            errors.append(f"FCM capability lacks target strategy: {item.get('id')}")
    if fcm.get("extraction_status") != "PASSED_LOCAL_EXACT_FIXTURE":
        errors.append("FCM extraction must record only PASSED_LOCAL_EXACT_FIXTURE")

    if fingerprint.get("exact_tuple", {}).get("framework_version") != "5.3.39":
        errors.append("fingerprint tuple is not exact")
    if fingerprint_evidence.get("execution_status") != "PASSED_LOCAL":
        errors.append("source fingerprint evidence must record PASSED_LOCAL")
    if fingerprint_evidence.get("coverage") is not None:
        errors.append("unexecuted source fingerprint cannot claim coverage")

    if target.get("framework_versions") != ["3.5.3"]:
        errors.append("target profile framework tuple is not exact")
    if target.get("runtime_versions") != ["21"]:
        errors.append("target profile runtime tuple is not exact")
    if target.get("providers", {}).get("views", {}).get("packaging") != "executable-war":
        errors.append("target view profile must use executable-war packaging")
    if target.get("providers", {}).get("views", {}).get("provider_version") != "10.1.42":
        errors.append("target JSP provider must be exact Tomcat Jasper 10.1.42")
    if target.get("providers", {}).get("views", {}).get("dependency_scope") != "provided":
        errors.append("target JSP provider must use provided scope for executable/external WAR isolation")
    if not target.get("startup", {}).get("command", "").split()[2].endswith(".war"):
        errors.append("target startup must execute the verified WAR artifact")
    if target.get("build", {}).get("execution_status") != "PASSED_LOCAL":
        errors.append("target build must record PASSED_LOCAL")
    if target.get("startup", {}).get("execution_status") != "PASSED_LOCAL":
        errors.append("target startup must record PASSED_LOCAL")

    if recipe.get("deterministic") is not True:
        errors.append("recipe must be deterministic")
    if recipe.get("rewrite_spring") != "6.35.0":
        errors.append("rewrite-spring must be pinned to 6.35.0")
    if recipe.get("rewrite_maven_plugin") != "6.44.0":
        errors.append("rewrite Maven plugin must be pinned to 6.44.0")
    if recipe.get("execution_status") != "PASSED_LOCAL":
        errors.append("recipe execution must record PASSED_LOCAL")
    if recipe.get("target_emitter") != "target-profile/scaffold/materialize_target.py":
        errors.append("recipe manifest must bind the controlled target emitter")
    if recipe.get("target_emitter_status") != "IMPLEMENTED_STATIC_NOT_RUNTIME_VERIFIED":
        errors.append("unused Python target emitter must not claim runtime verification")
    if recipe.get("target_emitter_execution_role") != "DOCUMENTATION_SCAFFOLD_NOT_USED_IN_LOCAL_QUALIFICATION":
        errors.append("recipe must distinguish the unused Python scaffold from the Java materializer")
    if recipe.get("production_target_materializer_status") != "PASSED_LOCAL":
        errors.append("trusted Java production target materializer must record PASSED_LOCAL")

    if scaffold.get("target_packaging") != "executable-war":
        errors.append("scaffold target packaging must be executable-war")
    if scaffold.get("source_mutation") is not False:
        errors.append("scaffold must not mutate source")
    if scaffold.get("overwrite_existing_output") is not False:
        errors.append("scaffold must refuse output overwrite")
    if scaffold.get("runtime_evidence_status") != "NOT_RUN":
        errors.append("scaffold runtime evidence must remain NOT_RUN")
    if scaffold.get("bootstrap", {}).get("servlet_initializer") is not True:
        errors.append("scaffold must generate SpringBootServletInitializer")

    if (
        adapter.get("implementation")
        != "ROUTE_SELECTION_AND_TRUSTED_JAVA_EXACT_TARGET_MATERIALIZER_FAIL_CLOSED"
    ):
        errors.append("adapter must describe fail-closed route selection and target emitter wiring")
    if adapter.get("route_catalog_registration") != "PRESENT_EXPERIMENTAL_PASSED_LOCAL_EXACT_FIXTURE":
        errors.append("route catalog registration must record only the exact local fixture")
    if (
        adapter.get("local_execution_port_registration")
        != "PRESENT_EXPERIMENTAL_EXACT_FIXTURE_MATERIALIZER_PASSED_LOCAL"
    ):
        errors.append("local execution port must bind the exact locally executed materializer")
    if adapter.get("production_target_materializer") != "io.elmos.worker.SpringMvcExactTargetMaterializer":
        errors.append("adapter must bind the trusted Java exact target materializer")
    if adapter.get("target_emitter_execution_role") != "DOCUMENTATION_SCAFFOLD_NOT_USED_IN_LOCAL_QUALIFICATION":
        errors.append("adapter must distinguish the unused Python scaffold from the Java materializer")
    if adapter.get("production_target_materializer_scope") != "EXACT_FIXTURE_ONLY":
        errors.append("production target materializer must remain exact-fixture-only")
    if adapter.get("production_wiring_point") != "AFTER_PINNED_OPENREWRITE_BEFORE_TARGET_VERIFY":
        errors.append("production target materializer wiring point must remain exact")
    if adapter.get("repository_python_execution") is not False:
        errors.append("production adapter must not execute repository Python")
    if not re.fullmatch(r"[0-9a-f]{64}", adapter.get("trusted_input_manifest_sha256", "")):
        errors.append("production exact input manifest must be content-addressed")
    if adapter.get("production_target_materializer_execution_status") != "PASSED_LOCAL":
        errors.append("production target materializer execution must record PASSED_LOCAL")
    if adapter.get("execution_status") != "PASSED_LOCAL":
        errors.append("exact local execution adapter must record PASSED_LOCAL")
    if adapter.get("disabled_by_default") is not False:
        errors.append("recorded exact local route must not require experimental opt-in")

    if certification.get("status") != "experimental":
        errors.append("certification status must remain experimental")
    if certification.get("certification_decision") != "NOT_CERTIFIED":
        errors.append("certification decision must remain NOT_CERTIFIED")
    gate_results = certification.get("gate_results", {})
    for field in sorted(LOCAL_RUNTIME_GATE_FIELDS):
        if gate_results.get(field) != "PASSED_LOCAL":
            errors.append(f"exact local runtime gate must be PASSED_LOCAL: {field}")
    for field in sorted(EXTERNAL_RUNTIME_GATE_FIELDS):
        if gate_results.get(field) != "NOT_RUN":
            errors.append(f"external or independent runtime gate must remain NOT_RUN: {field}")
    for value in certification.get("metrics", {}).values():
        if value is not None:
            errors.append("unexecuted certification metrics must remain null")
            break

    if len(evidence.get("runs", [])) != 1 or evidence.get("runs", [{}])[0].get("status") != "PASSED_LOCAL":
        errors.append("exact local evidence must contain one PASSED_LOCAL run")
    if evidence.get("metric_status") != "NOT_EVALUATED_BEYOND_EXACT_FIXTURE":
        errors.append("global metrics must remain not evaluated beyond the exact fixture")
    if evidence.get("external_execution_status") != "NOT_RUN":
        errors.append("external execution must remain NOT_RUN")
    for value in evidence.get("metrics", {}).values():
        if value is not None:
            errors.append("non-generalizable evidence metrics must remain null")
            break

    local_receipt: dict[str, Any] | None = None
    if local_evidence_relative is not None and local_evidence_index is not None:
        local_errors, local_receipt = validate_local_evidence(
            pack,
            local_evidence_relative,
            local_evidence_index,
        )
        errors.extend(local_errors)
    if local_receipt is not None:
        if fingerprint_evidence.get("source_snapshot_sha256") != local_receipt.get("source_snapshot_sha256"):
            errors.append("source fingerprint evidence does not bind the qualification snapshot")
        if fingerprint_evidence.get("source_commit") != local_receipt.get("source_commit"):
            errors.append("source fingerprint evidence does not bind the qualification commit")
        if fcm.get("source_snapshot_sha256") != local_receipt.get("source_snapshot_sha256"):
            errors.append("pack FCM does not bind the qualification snapshot")
        if fcm.get("source_commit") != local_receipt.get("source_commit"):
            errors.append("pack FCM does not bind the qualification commit")

    for corpus in ("holdout", "real-repository", "customer"):
        corpus_manifest = load(pack / f"corpus/{corpus}/reference-inputs.json")
        if corpus_manifest.get("execution_status") != "NOT_RUN":
            errors.append(f"{corpus} execution must remain NOT_RUN")
        if corpus_manifest.get("inputs") != []:
            errors.append(f"{corpus} inputs must remain empty until selected")

    gate_report = (pack / "certification/gate-report.md").read_text(encoding="utf-8")
    campaign_binding = campaign.get("tuple_binding", {})
    for label, expected in (
        ("source commit", campaign_binding.get("source_commit")),
        (
            "target artifact",
            campaign_binding.get("target_artifact", {}).get("digest", "").removeprefix("sha256:"),
        ),
        (
            "target profile",
            campaign_binding.get("target_profile", {}).get("digest", "").removeprefix("sha256:"),
        ),
        (
            "qualification policy",
            campaign_binding.get("policy", {}).get("digest", "").removeprefix("sha256:"),
        ),
    ):
        if not expected or expected not in gate_report:
            errors.append(f"gate report {label} binding is missing or stale")

    errors.extend(
        validate_fixture_pom(pack / "corpus/development/legacy-spring-mvc/pom.xml")
    )

    recipe_text = (
        pack / "recipes/spring-framework-5.3-mvc-to-spring-boot-3.5.3.yml"
    ).read_text(encoding="utf-8")
    for token in (
        "UpgradeToJava21",
        "JavaxMigrationToJakarta",
        "UpgradeSpringFramework_6_2",
        "spring-boot-starter-web",
        "version: 3.5.3",
    ):
        if token not in recipe_text:
            errors.append(f"recipe missing deterministic step: {token}")
    if "latest" in recipe_text.lower():
        errors.append("recipe must not use latest")

    mirrored_recipe = (
        ROOT
        / "apps/java-engine-worker/src/main/resources/rewrite/spring-framework-5.3-mvc-to-spring-boot-3.5.3.yml"
    )
    if not mirrored_recipe.is_file():
        errors.append("worker rewrite mirror is missing")
    elif mirrored_recipe.read_text(encoding="utf-8") != recipe_text:
        errors.append("worker rewrite mirror must be byte-identical to pack recipe")

    emitter_text = (pack / "target-profile/scaffold/materialize_target.py").read_text(
        encoding="utf-8"
    )
    for token in (
        "SpringBootServletInitializer",
        "spring-boot-maven-plugin",
        "<goal>repackage</goal>",
        "<artifactId>tomcat-embed-jasper</artifactId><scope>provided</scope>",
        "spring-boot-starter-actuator",
        "configureDefaultServletHandling",
        "configurer.enable()",
        "server.servlet.register-default-servlet=true",
        "server.shutdown=graceful",
        "management.endpoints.web.exposure.include=health",
        'get(\"/orders\")',
        'get(\"/actuator/env\")',
        'doesNotExist(\"X-Legacy-Audit\")',
        "src/main/webapp/WEB-INF/web.xml",
        "MATERIALIZED_STATIC_NOT_RUNTIME_VERIFIED",
        "BLOCKED_UNSUPPORTED_SOURCE",
    ):
        if token not in emitter_text:
            errors.append(f"controlled target emitter missing contract token: {token}")

    source_test_text = (
        pack
        / "corpus/development/legacy-spring-mvc/src/test/java/io/elmos/legacy/web/LegacyOrderControllerTest.java"
    ).read_text(encoding="utf-8")
    if "addMappedInterceptors" not in source_test_text:
        errors.append("source MVC test must map RequestAuditInterceptor to /api/**")
    if ".addInterceptors(" in source_test_text:
        errors.append("source MVC test must not register RequestAuditInterceptor globally")
    if 'header().doesNotExist("X-Legacy-Audit")' not in source_test_text:
        errors.append("source MVC test must prove /orders is outside the API interceptor")

    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"OK: {pack} status=experimental decision=NOT_CERTIFIED execution=PASSED_LOCAL_EXACT_FIXTURE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
