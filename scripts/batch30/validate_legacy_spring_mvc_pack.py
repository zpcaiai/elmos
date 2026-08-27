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
    "certification/evidence.json",
    "certification/certification.json",
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

LOCAL_EVIDENCE_RELATIVE = Path("certification/local-execution/2026-08-27")
LOCAL_EVIDENCE_INDEX = LOCAL_EVIDENCE_RELATIVE / "evidence-index.json"
EXPECTED_HARNESS_FILES = {
    "apps/java-engine-worker/src/main/java/io/elmos/worker/LocalSpringUpgradeExecutionPort.java",
    "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringDeploymentGuidance.java",
    "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringMvcExactTargetMaterializer.java",
    "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringMvcWarRuntime.java",
    "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringRouteCatalog.java",
    "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringUpgradeModels.java",
    "apps/java-engine-worker/src/main/resources/rewrite/spring-framework-5.3-mvc-to-spring-boot-3.5.3.yml",
    "apps/java-engine-worker/src/main/resources/spring-mvc/exact-5.3.39-fixture-manifest.json",
    "apps/java-engine-worker/src/main/resources/spring-mvc/target-profile/profile.json",
    "apps/java-engine-worker/src/main/resources/spring-mvc/target-profile/scaffold-manifest.json",
    "apps/java-engine-worker/src/test/java/io/elmos/worker/SpringMvcExactLocalQualificationIT.java",
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
    "download artifact": "artifacts/migrated-spring-boot-3.5.3.zip",
    "executed WAR": "artifacts/executed-spring-boot-3.5.3.war",
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


def validate_local_evidence(pack: Path) -> tuple[list[str], dict[str, Any] | None]:
    errors: list[str] = []
    evidence_root = pack / LOCAL_EVIDENCE_RELATIVE
    index_path = pack / LOCAL_EVIDENCE_INDEX
    if not index_path.is_file() or index_path.is_symlink():
        return [f"local evidence index missing or unsafe: {LOCAL_EVIDENCE_INDEX}"], None
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
    if not re.fullmatch(r"[0-9a-f]{40}", str(receipt.get("source_commit", ""))):
        errors.append("local qualification receipt source commit is not exact")
    if not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("source_snapshot_sha256", ""))):
        errors.append("local qualification receipt source snapshot is not content-addressed")

    source = receipt.get("source", {})
    if source.get("spring_framework") != "5.3.39" or source.get("tomcat") != "9.0.120":
        errors.append("local qualification receipt source toolchain tuple drifted")
    for archive_name, expected_sha, expected_bytes in (
        ("maven_archive", "0d7125e8c91097b36edb990ea5934e6c68b4440eef4ea96510a0f6815e7eeadb", 9278421),
        ("tomcat_archive", "93306f86baafe13186cc3e705c201040d68b0192a50be667a1f576ee4711db0d", 13697062),
    ):
        archive = source.get(archive_name, {})
        if archive.get("sha256") != expected_sha or archive.get("bytes") != expected_bytes:
            errors.append(f"local qualification receipt {archive_name} identity drifted")
        if not re.fullmatch(r"[0-9a-f]{128}", str(archive.get("sha512", ""))):
            errors.append(f"local qualification receipt {archive_name} lacks SHA-512")
    catalina = source.get("catalina_jar", {})
    if catalina.get("sha256") != "540f8b3855dc3d963f6872f5fb10a156985ee9bf8ffc78a9f859eda5675309dd":
        errors.append("local qualification receipt Catalina identity drifted")
    if source.get("tomcat_consumed_manifest_sha256") != "bf6e25983335bc1e3ac471195f4f5d09b65c8b57abdce636a087c6fb6c9c0fcd":
        errors.append("local qualification receipt consumed Tomcat manifest drifted")
    if "Apache Maven 3.9.11" not in str(source.get("maven", "")) or 'version "11.0.26"' not in str(source.get("java", "")):
        errors.append("local qualification receipt source Maven/Java version output drifted")

    target = receipt.get("target", {})
    if target.get("spring_boot") != "3.5.3" or target.get("spring_framework") != "6.2.8" or target.get("embedded_tomcat") != "10.1.42":
        errors.append("local qualification receipt target tuple drifted")
    if "Apache Maven 3.9.11" not in str(target.get("maven", "")) or 'version "21.0.11"' not in str(target.get("java", "")):
        errors.append("local qualification receipt target Maven/Java version output drifted")
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
    expected_index_paths = receipt_paths | {
        "local-qualification.json",
        *EXPECTED_LOCAL_ARTIFACT_PATHS.values(),
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
    errors.extend(validate_controlled_target_profile_resources(pack))

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
        if item.get("id") in LOCAL_FCM_STATUSES and item.get("evidence_refs") != [
            str(LOCAL_EVIDENCE_INDEX)
        ]:
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

    local_errors, local_receipt = validate_local_evidence(pack)
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

    for corpus in ("holdout", "real-repository"):
        corpus_manifest = load(pack / f"corpus/{corpus}/reference-inputs.json")
        if corpus_manifest.get("execution_status") != "NOT_RUN":
            errors.append(f"{corpus} execution must remain NOT_RUN")
        if corpus_manifest.get("inputs") != []:
            errors.append(f"{corpus} inputs must remain empty until selected")

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
