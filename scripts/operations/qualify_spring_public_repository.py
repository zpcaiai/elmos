#!/usr/bin/env python3
"""Replay a fail-closed Spring public-repository qualification.

This harness is deliberately narrower than the synthetic Spring route runner.
It consumes a repository-owned manifest, verifies an immutable public archive,
audits the complete source-test inventory, and records prerequisites. Untrusted
build, transformation, and test execution is hard-disabled until a protected
rootless-runner receipt verifier is implemented.

The result is local public engineering evidence.  A public repository is not a
customer repository and this process is not an independent verifier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
PACK_KEY = "spring-boot-2-7-18-to-3-5-3"
PACK_ROOT = ROOT / "framework-packs" / PACK_KEY
TARGET_RECIPE_ROOT = (PACK_ROOT / "recipes").resolve()
DEFAULT_MANIFEST = (
    PACK_ROOT
    / "corpus/real-repository"
    / "public-qualification-manifest.json"
)
ALLOWED_ARCHIVE_HOSTS = {"codeload.github.com"}
HEX_40 = re.compile(r"[0-9a-f]{40}")
HEX_64 = re.compile(r"[0-9a-f]{64}")
MAVEN_NS = "http://maven.apache.org/POM/4.0.0"
EXACT_TOOLCHAIN_NAMES = (
    "source_java",
    "source_javac",
    "target_java",
    "target_javac",
    "maven",
    "cmake",
    "cxx",
    "make",
)
TOOLCHAIN_VERSION_ARGUMENTS = {
    "source_java": ["-version"],
    "source_javac": ["-version"],
    "target_java": ["-version"],
    "target_javac": ["-version"],
    "maven": ["-version"],
    "cmake": ["--version"],
    "cxx": ["--version"],
    "make": ["--version"],
}
ROOTLESS_EXECUTION_STATUS = "NOT_RUN_ROOTLESS_ATTESTED_RUNNER_REQUIRED"
PROTECTED_RUNNER_RECEIPT_VERIFIER_IMPLEMENTED = False
EXECUTION_IMPLEMENTATION_REQUIREMENTS = (
    "protected-control-plane runner receipt verification",
    "content-addressed runner image and sandbox-policy binding",
    "rootless runtime and nonzero effective-uid attestation",
    "digest-only service-image injection and runtime verification",
    "separate executor and verifier identities with freshness and revocation checks",
)


class QualificationError(RuntimeError):
    """A fail-closed manifest, provenance, or execution error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise QualificationError(reason)


def protected_execution_gate(operation: str) -> dict[str, Any]:
    """Return the hard execution boundary; caller-supplied claims are not inputs."""

    return {
        "status": ROOTLESS_EXECUTION_STATUS,
        "operation": operation,
        "execution_enabled": False,
        "protected_runner_receipt_verifier": "NOT_IMPLEMENTED",
        "caller_supplied_attestation_accepted": False,
        "implementation_requirements": list(EXECUTION_IMPLEMENTATION_REQUIREMENTS),
        "evidence_scope": "LOCAL_STATIC_AND_PREREQUISITE_AUDIT_ONLY",
    }


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(payload.get("schema_version") == 1, "MANIFEST_SCHEMA_UNSUPPORTED")
    require(
        payload.get("pack_key") == PACK_KEY,
        "MANIFEST_PACK_MISMATCH",
    )
    execution_policy = payload.get("execution_policy")
    require(
        execution_policy
        == {
            "default_mode": "static-prerequisite-audit-only",
            "untrusted_build_execution": ROOTLESS_EXECUTION_STATUS,
            "protected_rootless_runner_receipt_verifier": "NOT_IMPLEMENTED",
            "caller_supplied_attestation_accepted": False,
            "implementation_requirements": list(EXECUTION_IMPLEMENTATION_REQUIREMENTS),
        },
        "EXECUTION_POLICY_NOT_FAIL_CLOSED",
    )
    require(
        PROTECTED_RUNNER_RECEIPT_VERIFIER_IMPLEMENTED is False,
        "PROTECTED_RUNNER_RECEIPT_VERIFIER_STATE_UNEXPECTED",
    )
    repositories = payload.get("repositories")
    require(isinstance(repositories, list) and repositories, "REPOSITORIES_EMPTY")
    ids: set[str] = set()
    for repository in repositories:
        repository_id = repository.get("id")
        require(
            isinstance(repository_id, str)
            and re.fullmatch(r"[a-z0-9][a-z0-9-]+", repository_id) is not None,
            "REPOSITORY_ID_INVALID",
        )
        require(repository_id not in ids, f"REPOSITORY_ID_DUPLICATE:{repository_id}")
        ids.add(repository_id)
        require(repository.get("customer_repository") is False, "PUBLIC_MARKED_CUSTOMER")
        require(
            repository.get("independent_verification") is False,
            "SELF_RUN_MARKED_INDEPENDENT",
        )
        commit = str(repository.get("commit_sha", ""))
        tree = str(repository.get("tree_sha", ""))
        require(HEX_40.fullmatch(commit) is not None, f"COMMIT_NOT_EXACT:{repository_id}")
        require(HEX_40.fullmatch(tree) is not None, f"TREE_NOT_EXACT:{repository_id}")
        archive = repository.get("archive")
        require(isinstance(archive, dict), f"ARCHIVE_MISSING:{repository_id}")
        archive_url = str(archive.get("url", ""))
        parsed = urlparse(archive_url)
        require(parsed.scheme == "https", f"ARCHIVE_URL_NOT_HTTPS:{repository_id}")
        require(parsed.hostname in ALLOWED_ARCHIVE_HOSTS, f"ARCHIVE_HOST_DENIED:{repository_id}")
        require(commit in archive_url, f"ARCHIVE_URL_NOT_COMMIT_BOUND:{repository_id}")
        require(
            HEX_64.fullmatch(str(archive.get("sha256", ""))) is not None,
            f"ARCHIVE_DIGEST_INVALID:{repository_id}",
        )
        require(
            archive.get("root") == f"{repository_id}-{commit}",
            f"ARCHIVE_ROOT_NOT_COMMIT_BOUND:{repository_id}",
        )
        source = repository.get("source_tuple", {})
        require(source.get("spring_boot") == "2.7.18", f"SOURCE_BOOT_MISMATCH:{repository_id}")
        require(source.get("java") == "17", f"SOURCE_JAVA_MISMATCH:{repository_id}")
        require(source.get("maven") == "3.9.11", f"SOURCE_MAVEN_MISMATCH:{repository_id}")
        for item in repository.get("required_files", []):
            require(isinstance(item.get("path"), str), "REQUIRED_FILE_PATH_INVALID")
            require(
                HEX_64.fullmatch(str(item.get("sha256", ""))) is not None,
                f"REQUIRED_FILE_DIGEST_INVALID:{item.get('path')}",
            )
        for image in repository.get("service_images", []):
            digest = str(image.get("platform_digest", ""))
            require(
                re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is not None,
                f"SERVICE_IMAGE_DIGEST_INVALID:{repository_id}:{image.get('role')}",
            )
            require(
                str(image.get("resolved_reference", "")).endswith(digest),
                f"SERVICE_IMAGE_REFERENCE_NOT_PINNED:{repository_id}:{image.get('role')}",
            )
            require(
                image.get("execution_reference") == image.get("resolved_reference")
                and "@sha256:" in str(image.get("execution_reference", "")),
                f"SERVICE_IMAGE_EXECUTION_REFERENCE_NOT_PINNED:{repository_id}:{image.get('role')}",
            )
            require(
                image.get("source_reference") != image.get("execution_reference"),
                f"SERVICE_IMAGE_SOURCE_TAG_USED_AS_EXECUTION_OBJECT:{repository_id}:{image.get('role')}",
            )
        target = repository.get("target", {})
        require(target.get("spring_boot") == "3.5.3", f"TARGET_BOOT_MISMATCH:{repository_id}")
        require(target.get("java") == "21", f"TARGET_JAVA_MISMATCH:{repository_id}")
        require(target.get("maven") == "3.9.11", f"TARGET_MAVEN_MISMATCH:{repository_id}")
        require(
            target.get("recipe_id")
            == "io.elmos.openrewrite.SpringBoot2_7_18To3_5_3Java21",
            f"TARGET_RECIPE_ID_MISMATCH:{repository_id}",
        )
        require(
            target.get("rewrite_maven_plugin") == "6.44.0",
            f"TARGET_REWRITE_PLUGIN_MISMATCH:{repository_id}",
        )
        require(
            target.get("rewrite_spring") == "6.35.0",
            f"TARGET_REWRITE_SPRING_MISMATCH:{repository_id}",
        )
        require(
            repository.get("toolchain_assertions", {}).get(
                "target_java_version_fragment"
            )
            == "21.0.11",
            f"TARGET_JAVA_TOOLCHAIN_MISMATCH:{repository_id}",
        )
        toolchain_contract = repository.get("toolchain_contract")
        require(
            isinstance(toolchain_contract, dict),
            f"TOOLCHAIN_CONTRACT_MISSING:{repository_id}",
        )
        require(
            toolchain_contract.get("platform_system") == "Darwin"
            and toolchain_contract.get("platform_machine") == "arm64",
            f"TOOLCHAIN_PLATFORM_NOT_EXACT:{repository_id}",
        )
        identities = toolchain_contract.get("executables")
        require(
            isinstance(identities, dict),
            f"TOOLCHAIN_EXECUTABLES_MISSING:{repository_id}",
        )
        require(
            set(identities) == set(EXACT_TOOLCHAIN_NAMES),
            f"TOOLCHAIN_EXECUTABLE_SET_MISMATCH:{repository_id}",
        )
        for name in EXACT_TOOLCHAIN_NAMES:
            identity = identities[name]
            require(
                isinstance(identity, dict),
                f"TOOLCHAIN_IDENTITY_INVALID:{repository_id}:{name}",
            )
            require(
                HEX_64.fullmatch(str(identity.get("sha256", ""))) is not None,
                f"TOOLCHAIN_DIGEST_INVALID:{repository_id}:{name}",
            )
            version_line = identity.get("version_line")
            require(
                isinstance(version_line, str)
                and bool(version_line)
                and "\n" not in version_line
                and "\r" not in version_line,
                f"TOOLCHAIN_VERSION_LINE_INVALID:{repository_id}:{name}",
            )
        require(
            toolchain_contract.get("maven_policy")
            == {
                "isolated_user_home": True,
                "isolated_local_repository": True,
                "strict_checksums": True,
                "inherited_maven_options": False,
            },
            f"MAVEN_POLICY_NOT_FAIL_CLOSED:{repository_id}",
        )
        recipe_value = str(target.get("recipe_path", ""))
        require(bool(recipe_value) and not Path(recipe_value).is_absolute(), "TARGET_RECIPE_PATH_INVALID")
        recipe_path = (ROOT / recipe_value).resolve()
        require(
            recipe_path.is_relative_to(TARGET_RECIPE_ROOT),
            f"TARGET_RECIPE_PATH_ESCAPE:{repository_id}",
        )
        require(recipe_path.is_file(), f"TARGET_RECIPE_MISSING:{repository_id}")
    for candidate in payload.get("separate_public_candidates", []):
        candidate_id = str(candidate.get("id", ""))
        require(
            HEX_40.fullmatch(str(candidate.get("commit_sha", ""))) is not None,
            f"CANDIDATE_COMMIT_NOT_EXACT:{candidate_id}",
        )
        require(
            HEX_40.fullmatch(str(candidate.get("tree_sha", ""))) is not None,
            f"CANDIDATE_TREE_NOT_EXACT:{candidate_id}",
        )
        require(
            HEX_64.fullmatch(str(candidate.get("pom_sha256", ""))) is not None,
            f"CANDIDATE_POM_DIGEST_INVALID:{candidate_id}",
        )
        require(candidate.get("source_execution") == "NOT_RUN", "CANDIDATE_SOURCE_OVERCLAIM")
        require(candidate.get("target_execution") == "NOT_RUN", "CANDIDATE_TARGET_OVERCLAIM")
        require(candidate.get("customer_repository") is False, "CANDIDATE_MARKED_CUSTOMER")
        require(
            candidate.get("independent_verification") is False,
            "CANDIDATE_MARKED_INDEPENDENT",
        )
    return payload


def repository_by_id(manifest: dict[str, Any], repository_id: str) -> dict[str, Any]:
    matches = [item for item in manifest["repositories"] if item["id"] == repository_id]
    require(len(matches) == 1, f"REPOSITORY_NOT_DECLARED:{repository_id}")
    return matches[0]


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run_command(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
    timeout_seconds: int,
) -> dict[str, Any]:
    started = utc_now()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )
        output = completed.stdout
        return {
            "command": command,
            "started_at": started,
            "finished_at": utc_now(),
            "exit_code": completed.returncode,
            "timed_out": False,
            "output": output,
            "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
            "output_bytes": len(output.encode("utf-8")),
        }
    except subprocess.TimeoutExpired as exc:
        data = exc.stdout or ""
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        return {
            "command": command,
            "started_at": started,
            "finished_at": utc_now(),
            "exit_code": None,
            "timed_out": True,
            "output": data,
            "output_sha256": hashlib.sha256(data.encode("utf-8")).hexdigest(),
            "output_bytes": len(data.encode("utf-8")),
        }


def fetch_archive(url: str, destination: Path) -> dict[str, Any]:
    command = [
        "curl",
        "--proto",
        "=https",
        "--tlsv1.2",
        "--fail",
        "--location",
        "--silent",
        "--show-error",
        "--connect-timeout",
        "5",
        "--max-time",
        "120",
        "--retry",
        "2",
        "--retry-all-errors",
        "--output",
        str(destination),
        url,
    ]
    record = run_command(command, cwd=destination.parent, timeout_seconds=135)
    require(record["exit_code"] == 0 and not record["timed_out"], "ARCHIVE_FETCH_FAILED")
    return record


def check_workspace(path: Path, minimum_free_bytes: int) -> None:
    resolved = path.resolve()
    forbidden = {Path("/").resolve(), Path.home().resolve(), ROOT.resolve()}
    require(resolved not in forbidden, "WORKSPACE_TARGET_TOO_BROAD")
    if resolved.exists():
        require(resolved.is_dir(), "WORKSPACE_NOT_DIRECTORY")
        require(not any(resolved.iterdir()), "WORKSPACE_NOT_EMPTY")
    else:
        resolved.mkdir(parents=True)
    free = shutil.disk_usage(resolved).free
    require(free >= minimum_free_bytes, f"FREE_SPACE_BELOW_STOP_LINE:{free}")


def validate_tar_members(archive: Path, expected_root: str) -> None:
    with tarfile.open(archive, mode="r:gz") as handle:
        members = handle.getmembers()
        require(bool(members), "ARCHIVE_EMPTY")
        for member in members:
            name = PurePosixPath(member.name)
            require(not name.is_absolute(), f"ARCHIVE_ABSOLUTE_PATH:{member.name}")
            require(".." not in name.parts, f"ARCHIVE_PATH_TRAVERSAL:{member.name}")
            require(name.parts and name.parts[0] == expected_root, "ARCHIVE_ROOT_MISMATCH")
            require(
                member.isfile() or member.isdir(),
                f"ARCHIVE_UNSAFE_MEMBER_TYPE:{member.name}",
            )


def extract_archive(archive: Path, workspace: Path, expected_root: str) -> Path:
    validate_tar_members(archive, expected_root)
    with tarfile.open(archive, mode="r:gz") as handle:
        handle.extractall(workspace, filter="data")
    source = workspace / expected_root
    require(source.is_dir(), "EXTRACTED_SOURCE_MISSING")
    return source


def verify_required_files(source: Path, repository: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for expected in repository.get("required_files", []):
        path = source / expected["path"]
        require(path.is_file(), f"REQUIRED_FILE_MISSING:{expected['path']}")
        actual = sha256_file(path)
        require(actual == expected["sha256"], f"REQUIRED_FILE_DRIFT:{expected['path']}")
        results.append(
            {"path": expected["path"], "sha256": actual, "bytes": path.stat().st_size}
        )
    return results


def pom_audit(source: Path, repository: dict[str, Any]) -> dict[str, Any]:
    pom = source / "pom.xml"
    tree = ET.parse(pom)
    root = tree.getroot()
    parent_version = root.findtext(f"{{{MAVEN_NS}}}parent/{{{MAVEN_NS}}}version")
    java_version = root.findtext(
        f"{{{MAVEN_NS}}}properties/{{{MAVEN_NS}}}java.version"
    )
    dependencies = {
        (
            dependency.findtext(f"{{{MAVEN_NS}}}groupId") or "",
            dependency.findtext(f"{{{MAVEN_NS}}}artifactId") or "",
        )
        for dependency in root.findall(f"{{{MAVEN_NS}}}dependencies/{{{MAVEN_NS}}}dependency")
    }
    expected = repository["source_tuple"]
    require(parent_version == expected["spring_boot"], "POM_BOOT_VERSION_DRIFT")
    require(java_version == expected["java"], "POM_JAVA_VERSION_DRIFT")
    return {
        "pom_sha256": sha256_file(pom),
        "spring_boot_parent": parent_version,
        "java_version": java_version,
        "junit_vintage_declared": (
            "org.junit.vintage",
            "junit-vintage-engine",
        )
        in dependencies,
    }


def test_inventory(source: Path, repository: dict[str, Any]) -> dict[str, Any]:
    jupiter = 0
    junit4 = 0
    files = sorted((source / "src/test/java").rglob("*.java"))
    for path in files:
        text = path.read_text(encoding="utf-8")
        count = len(re.findall(r"(?<![\w.])@Test(?:\s*\(|\b)", text))
        if "import org.junit.jupiter.api.Test;" in text:
            jupiter += count
        if "import org.junit.Test;" in text:
            junit4 += count
    observed = {
        "test_source_files": len(files),
        "junit_jupiter_tests": jupiter,
        "junit4_tests": junit4,
        "total_tests": jupiter + junit4,
    }
    expected = repository["test_inventory"]
    for key, value in expected.items():
        require(observed.get(key) == value, f"TEST_INVENTORY_DRIFT:{key}")
    return observed


def create_vintage_overlay(
    source: Path,
    repository: dict[str, Any],
    *,
    target_profile: bool = False,
) -> dict[str, Any]:
    overlay = repository["test_discovery_overlay"]
    original = source / "pom.xml"
    destination = source / "qualification-pom.xml"
    test_hashes_before = {
        str(path.relative_to(source)): sha256_file(path)
        for path in sorted((source / "src/test").rglob("*"))
        if path.is_file()
    }
    tree = ET.parse(original)
    root = tree.getroot()
    dependencies = root.find(f"{{{MAVEN_NS}}}dependencies")
    require(dependencies is not None, "POM_DEPENDENCIES_MISSING")
    assert dependencies is not None
    dependency = ET.SubElement(dependencies, f"{{{MAVEN_NS}}}dependency")
    ET.SubElement(dependency, f"{{{MAVEN_NS}}}groupId").text = "org.junit.vintage"
    ET.SubElement(dependency, f"{{{MAVEN_NS}}}artifactId").text = "junit-vintage-engine"
    if not target_profile:
        ET.SubElement(dependency, f"{{{MAVEN_NS}}}version").text = overlay["version"]
    ET.SubElement(dependency, f"{{{MAVEN_NS}}}scope").text = "test"
    ET.register_namespace("", MAVEN_NS)
    tree.write(destination, encoding="UTF-8", xml_declaration=True)
    test_hashes = {
        str(path.relative_to(source)): sha256_file(path)
        for path in sorted((source / "src/test").rglob("*"))
        if path.is_file()
    }
    require(test_hashes == test_hashes_before, "TEST_SOURCE_CHANGED_BY_DISCOVERY_OVERLAY")
    return {
        "status": "APPLIED_EXPLICIT_TEST_DISCOVERY_ONLY",
        "reason": "Expose the repository's 20 existing JUnit4 tests to the JUnit Platform; no test source is changed.",
        "version": (
            "MANAGED_BY_SPRING_BOOT_TARGET_BOM"
            if target_profile
            else overlay["version"]
        ),
        "original_pom_sha256": sha256_file(original),
        "overlay_pom_path": "qualification-pom.xml",
        "overlay_pom_sha256": sha256_file(destination),
        "test_source_hashes_before_overlay": test_hashes_before,
        "test_source_hashes_after_overlay": test_hashes,
    }


def exact_executable_audit(
    *,
    name: str,
    executable: Path,
    identity: dict[str, Any],
    cwd: Path,
    environment: dict[str, str] | None = None,
    command_prefix: list[str] | None = None,
    required_root: Path | None = None,
) -> dict[str, Any]:
    """Bind a tool invocation to its exact executable bytes and version line."""

    require(name in TOOLCHAIN_VERSION_ARGUMENTS, f"TOOLCHAIN_NAME_UNKNOWN:{name}")
    requested = executable.absolute()
    result: dict[str, Any] = {
        "name": name,
        "requested_path": str(requested),
        "expected_sha256": identity["sha256"],
        "expected_version_line": identity["version_line"],
        "matched": False,
    }
    try:
        resolved = requested.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        return {**result, "status": "FAILED_EXECUTABLE_MISSING", "error": str(exc)}
    result["resolved_path"] = str(resolved)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        return {**result, "status": "FAILED_NOT_EXECUTABLE"}
    if required_root is not None:
        try:
            resolved.relative_to(required_root.resolve(strict=True))
        except (OSError, RuntimeError, ValueError) as exc:
            return {
                **result,
                "status": "FAILED_EXECUTABLE_OUTSIDE_REQUIRED_ROOT",
                "error": str(exc),
            }

    actual_sha256 = sha256_file(resolved)
    result.update(
        {
            "sha256": actual_sha256,
            "bytes": resolved.stat().st_size,
            "digest_matched": actual_sha256 == identity["sha256"],
        }
    )
    command = [
        str(resolved),
        *(command_prefix or []),
        *TOOLCHAIN_VERSION_ARGUMENTS[name],
    ]
    execution = run_command(
        command,
        cwd=cwd,
        environment=environment,
        timeout_seconds=20,
    )
    post_audit: dict[str, Any]
    identity_stable = False
    try:
        post_resolved = requested.resolve(strict=True)
        post_sha256 = sha256_file(post_resolved)
        post_audit = {
            "resolved_path": str(post_resolved),
            "sha256": post_sha256,
            "bytes": post_resolved.stat().st_size,
        }
        identity_stable = bool(
            post_resolved == resolved
            and post_sha256 == actual_sha256
            and post_audit["bytes"] == result["bytes"]
        )
    except (OSError, RuntimeError) as exc:
        post_audit = {"error": str(exc)}
    observed_line = next(
        (line.strip() for line in execution["output"].splitlines() if line.strip()),
        "",
    )
    version_matched = observed_line == identity["version_line"]
    matched = bool(
        execution["exit_code"] == 0
        and not execution["timed_out"]
        and result["digest_matched"]
        and version_matched
        and identity_stable
    )
    status = "PASSED_EXACT_IDENTITY" if matched else "FAILED_IDENTITY_MISMATCH"
    if not identity_stable:
        status = "FAILED_EXECUTABLE_DRIFT_DURING_AUDIT"
    return {
        **result,
        "status": status,
        "observed_version_line": observed_line,
        "version_matched": version_matched,
        "post_execution_identity": post_audit,
        "identity_stable_during_audit": identity_stable,
        "execution_path": str(resolved) if identity_stable else None,
        "evidence_scope": "LOCAL_TOOLCHAIN_ENGINEERING_AUDIT_NOT_ROOTLESS_ATTESTATION",
        "matched": matched,
        "execution": execution,
    }


def exact_jni_toolchain(java_home: Path) -> dict[str, Path]:
    """Resolve every CMake FindJNI input below one exact JDK home."""

    root = java_home.resolve(strict=True)
    include = (root / "include").resolve(strict=True)
    require((include / "jni.h").is_file(), "EXACT_JDK_JNI_HEADER_MISSING")

    platform_include = next(
        (
            candidate.resolve(strict=True)
            for candidate in (
                include / "darwin",
                include / "linux",
                include / "win32",
            )
            if candidate.is_dir() and (candidate / "jni_md.h").is_file()
        ),
        None,
    )
    jvm_library = next(
        (
            candidate.resolve(strict=True)
            for candidate in (
                root / "lib/server/libjvm.dylib",
                root / "lib/server/libjvm.so",
                root / "bin/server/jvm.dll",
            )
            if candidate.is_file()
        ),
        None,
    )
    awt_library = next(
        (
            candidate.resolve(strict=True)
            for candidate in (
                root / "lib/libjawt.dylib",
                root / "lib/libjawt.so",
                root / "bin/jawt.dll",
            )
            if candidate.is_file()
        ),
        None,
    )
    require(platform_include is not None, "EXACT_JDK_PLATFORM_JNI_HEADER_MISSING")
    require(jvm_library is not None, "EXACT_JDK_JVM_LIBRARY_MISSING")
    require(awt_library is not None, "EXACT_JDK_AWT_LIBRARY_MISSING")
    assert platform_include is not None
    assert jvm_library is not None
    assert awt_library is not None

    selected = {
        "JAVA_HOME": root,
        "Java_JAVA_EXECUTABLE": (root / "bin/java").resolve(strict=True),
        "Java_JAVAC_EXECUTABLE": (root / "bin/javac").resolve(strict=True),
        "JAVA_INCLUDE_PATH": include,
        "JAVA_INCLUDE_PATH2": platform_include,
        "JAVA_AWT_INCLUDE_PATH": include,
        "JAVA_JVM_LIBRARY": jvm_library,
        "JAVA_AWT_LIBRARY": awt_library,
    }
    for name, path in selected.items():
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise QualificationError(f"EXACT_JDK_PATH_ESCAPE:{name}") from exc
    for name in ("Java_JAVA_EXECUTABLE", "Java_JAVAC_EXECUTABLE"):
        require(
            selected[name].is_file() and os.access(selected[name], os.X_OK),
            f"EXACT_JDK_EXECUTABLE_INVALID:{name}",
        )
    return selected


def parse_cmake_cache(cache_path: Path) -> tuple[dict[str, str], list[str]]:
    require(cache_path.is_file(), "CMAKE_CACHE_MISSING")
    entries: dict[str, str] = {}
    duplicates: list[str] = []
    for line in cache_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith(("#", "//")) or "=" not in line:
            continue
        key_with_type, value = line.split("=", 1)
        key = key_with_type.split(":", 1)[0]
        if key in entries:
            duplicates.append(key)
        entries[key] = value
    return entries, sorted(set(duplicates))


def audit_cmake_jni_cache(
    cache_path: Path,
    expected: dict[str, Path],
    expected_build_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Reject required or additional JNI/Java cache paths outside the exact JDK."""

    entries, duplicates = parse_cmake_cache(cache_path)
    root = expected["JAVA_HOME"].resolve(strict=True)
    actual: dict[str, str | None] = {}
    mismatches = [f"DUPLICATE_CACHE_KEY:{key}" for key in duplicates]
    for name, expected_path in {**expected, **(expected_build_paths or {})}.items():
        value = entries.get(name)
        actual[name] = value
        if value is None or value.endswith("-NOTFOUND"):
            mismatches.append(f"{name}:MISSING")
            continue
        try:
            resolved = Path(value).resolve(strict=True)
        except (OSError, RuntimeError):
            mismatches.append(f"{name}:UNRESOLVED:{value}")
            continue
        if resolved != expected_path.resolve(strict=True):
            mismatches.append(
                f"{name}:EXPECTED:{expected_path.resolve(strict=True)}:ACTUAL:{resolved}"
            )

    observed_jni_paths: list[dict[str, Any]] = []
    jni_markers = ("JAVA", "JNI", "JVM", "JDK", "AWT")
    for key, value in sorted(entries.items()):
        if not any(marker in key.upper() for marker in jni_markers):
            continue
        for token in value.split(";"):
            candidate_text = token.strip().strip('"')
            candidate = Path(candidate_text)
            if not candidate.is_absolute():
                continue
            resolved = candidate.resolve(strict=False)
            try:
                resolved.relative_to(root)
                inside_exact_jdk = True
            except ValueError:
                inside_exact_jdk = False
            observed_jni_paths.append(
                {
                    "key": key,
                    "declared": candidate_text,
                    "resolved": str(resolved),
                    "inside_exact_jdk": inside_exact_jdk,
                }
            )
            if not inside_exact_jdk:
                mismatches.append(f"FOREIGN_JNI_PATH:{key}:{resolved}")
            elif not resolved.exists():
                mismatches.append(f"UNRESOLVED_JNI_PATH:{key}:{resolved}")

    return {
        "status": "PASSED_EXACT_JDK" if not mismatches else "FAILED_JDK_PATH_MISMATCH",
        "matched": not mismatches,
        "cache_path": str(cache_path),
        "cache_sha256": sha256_file(cache_path),
        "cache_bytes": cache_path.stat().st_size,
        "expected": {
            name: str(path)
            for name, path in {**expected, **(expected_build_paths or {})}.items()
        },
        "actual": actual,
        "observed_jni_paths": observed_jni_paths,
        "mismatches": sorted(set(mismatches)),
    }


def cmake_configure_command(
    *,
    cmake: Path,
    cxx: Path,
    make: Path,
    source: Path,
    build: Path,
    jni_toolchain: dict[str, Path],
) -> list[str]:
    return [
        str(cmake),
        "-S",
        str(source / "battle-engine"),
        "-B",
        str(build),
        "-G",
        "Unix Makefiles",
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_CXX_COMPILER={cxx}",
        f"-DCMAKE_MAKE_PROGRAM={make}",
        *(f"-D{name}={path}" for name, path in jni_toolchain.items()),
    ]


def native_build(
    source: Path,
    java_home: Path,
    repository: dict[str, Any],
    *,
    cmake: Path,
    cxx: Path,
    make: Path,
) -> dict[str, Any]:
    # Untrusted CMake configure/build is unavailable until a protected receipt
    # verifier exists. This cannot be overridden with caller-supplied JSON.
    return protected_execution_gate("untrusted-cmake-native-build")

    # Retained implementation is unreachable scaffolding for a future protected
    # runner integration; the gate above must only move behind real receipt checks.
    build = source / "qualification-native-build"
    try:
        jni_toolchain = exact_jni_toolchain(java_home)
    except (OSError, QualificationError) as exc:
        return {
            "status": "FAILED_EXACT_JNI_TOOLCHAIN",
            "error": str(exc),
            "configure": None,
            "toolchain_audit": None,
            "build": None,
            "artifact": None,
            "library_directory": str(build),
        }
    environment = os.environ.copy()
    for key in (
        "CMAKE_INCLUDE_PATH",
        "CMAKE_LIBRARY_PATH",
        "CMAKE_PREFIX_PATH",
        "CPATH",
        "CPLUS_INCLUDE_PATH",
        "JAVA_TOOL_OPTIONS",
        "JDK_JAVA_OPTIONS",
        "JDK_HOME",
        "JRE_HOME",
        "_JAVA_OPTIONS",
    ):
        environment.pop(key, None)
    environment["JAVA_HOME"] = str(jni_toolchain["JAVA_HOME"])
    configure = run_command(
        cmake_configure_command(
            cmake=cmake,
            cxx=cxx,
            make=make,
            source=source,
            build=build,
            jni_toolchain=jni_toolchain,
        ),
        cwd=source,
        environment=environment,
        timeout_seconds=repository["timeouts_seconds"]["native_configure"],
    )
    toolchain_audit: dict[str, Any] | None = None
    compile_record: dict[str, Any] | None = None
    artifact: dict[str, Any] | None = None
    if configure["exit_code"] == 0 and not configure["timed_out"]:
        toolchain_audit = audit_cmake_jni_cache(
            build / "CMakeCache.txt",
            jni_toolchain,
            {
                "CMAKE_CXX_COMPILER": cxx.resolve(strict=True),
                "CMAKE_MAKE_PROGRAM": make.resolve(strict=True),
            },
        )
        if toolchain_audit["matched"]:
            compile_record = run_command(
                [str(cmake), "--build", str(build), "--config", "Release"],
                cwd=source,
                environment=environment,
                timeout_seconds=repository["timeouts_seconds"]["native_build"],
            )
            candidates = [build / name for name in repository["native_artifacts"]]
            match = next((candidate for candidate in candidates if candidate.is_file()), None)
            if match is not None:
                artifact = {
                    "path": str(match.relative_to(source)),
                    "sha256": sha256_file(match),
                    "bytes": match.stat().st_size,
                }
    passed = bool(
        configure["exit_code"] == 0
        and toolchain_audit
        and toolchain_audit["matched"]
        and compile_record
        and compile_record["exit_code"] == 0
        and artifact
    )
    return {
        "status": "PASSED_LOCAL" if passed else "FAILED",
        "configure": configure,
        "toolchain_audit": toolchain_audit,
        "build": compile_record,
        "artifact": artifact,
        "library_directory": str(build),
    }


def service_image_audit(repository: dict[str, Any], source: Path) -> list[dict[str, Any]]:
    results = []
    docker = shutil.which("docker")
    for image in repository["service_images"]:
        result: dict[str, Any] = {
            "role": image["role"],
            "source_reference_provenance_only": image["source_reference"],
            "source_reference_used_for_execution": False,
            "resolved_reference": image["resolved_reference"],
            "execution_reference": image["execution_reference"],
            "platform": image["platform"],
            "expected_platform_digest": image["platform_digest"],
            "status": "NOT_AVAILABLE",
        }
        if docker is None:
            result["reason"] = "DOCKER_CLI_NOT_AVAILABLE"
        else:
            inspect = run_command(
                [docker, "image", "inspect", image["execution_reference"]],
                cwd=source,
                timeout_seconds=20,
            )
            result["inspect"] = inspect
            if inspect["exit_code"] == 0:
                try:
                    inspected = json.loads(inspect["output"])[0]
                    pinned_id = inspected["Id"]
                    repo_digests = inspected.get("RepoDigests", [])
                except (IndexError, KeyError, TypeError, json.JSONDecodeError):
                    pinned_id = None
                    repo_digests = []
                result["pinned_image_id"] = pinned_id
                result["repo_digests"] = repo_digests
                if (
                    pinned_id is not None
                    and image["execution_reference"] in repo_digests
                ):
                    result["status"] = "AVAILABLE_RESOLVED_DIGEST_LOCAL"
                else:
                    result["reason"] = "RESOLVED_DIGEST_REFERENCE_NOT_BOUND_LOCALLY"
            else:
                result["reason"] = "PINNED_IMAGE_NOT_PRESENT_NO_PULL_PERFORMED"
        results.append(result)
    return results


def prepare_maven_isolation(workspace: Path) -> dict[str, Path]:
    root = (workspace.resolve(strict=True) / ".elmos-maven-isolation").resolve()
    require(root.is_relative_to(workspace.resolve(strict=True)), "MAVEN_ISOLATION_PATH_ESCAPE")
    user_home = root / "user-home"
    local_repository = root / "repository"
    for path in (user_home, local_repository):
        path.mkdir(parents=True, exist_ok=False)
    return {
        "root": root,
        "user_home": user_home.resolve(strict=True),
        "local_repository": local_repository.resolve(strict=True),
    }


def exact_maven_arguments(isolation: dict[str, Path]) -> list[str]:
    root = isolation["root"].resolve(strict=True)
    user_home = isolation["user_home"].resolve(strict=True)
    local_repository = isolation["local_repository"].resolve(strict=True)
    for name, path in (("USER_HOME", user_home), ("LOCAL_REPOSITORY", local_repository)):
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise QualificationError(f"MAVEN_{name}_PATH_ESCAPE") from exc
    return [
        "--strict-checksums",
        f"-Dmaven.repo.local={local_repository}",
        f"-Duser.home={user_home}",
    ]


def exact_maven_environment(
    java_home: Path, isolation: dict[str, Path]
) -> dict[str, str]:
    environment = os.environ.copy()
    environment["JAVA_HOME"] = str(java_home.resolve(strict=True))
    environment["HOME"] = str(isolation["user_home"].resolve(strict=True))
    for key in (
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "ALL_PROXY",
        "https_proxy",
        "http_proxy",
        "all_proxy",
        "JAVA_TOOL_OPTIONS",
        "JDK_JAVA_OPTIONS",
        "MAVEN_ARGS",
        "MAVEN_CONFIG",
        "MAVEN_OPTS",
        "_JAVA_OPTIONS",
    ):
        environment.pop(key, None)
    environment["NO_PROXY"] = "repo.maven.apache.org,localhost,127.0.0.1"
    environment["no_proxy"] = environment["NO_PROXY"]
    proxy_guards = (
        "-Djava.net.useSystemProxies=false "
        "-Dhttp.proxyHost= -Dhttps.proxyHost= -DsocksProxyHost= "
        "-Dhttp.nonProxyHosts=* -Dhttps.nonProxyHosts=*"
    )
    environment["MAVEN_OPTS"] = proxy_guards
    return environment


def source_test_command(
    source: Path,
    maven: Path,
    java_home: Path,
    native: dict[str, Any],
    repository: dict[str, Any],
    maven_isolation: dict[str, Path],
    timeout_key: str = "source_tests",
) -> dict[str, Any]:
    return protected_execution_gate("untrusted-maven-source-tests")

    # See native_build: retained for a future protected runner only.
    environment = exact_maven_environment(java_home, maven_isolation)
    jdbc = repository["source_test_properties"]
    command = [
        str(maven),
        "-B",
        "-ntp",
        *exact_maven_arguments(maven_isolation),
        "-f",
        str(source / "qualification-pom.xml"),
        f"-DargLine=-Djava.library.path={native['library_directory']}",
        f"-Dspring.datasource.url={jdbc['spring.datasource.url']}",
        f"-Dspring.datasource.driver-class-name={jdbc['spring.datasource.driver-class-name']}",
        "verify",
    ]
    return run_command(
        command,
        cwd=source,
        environment=environment,
        timeout_seconds=repository["timeouts_seconds"][timeout_key],
    )


def surefire_summary(source: Path) -> dict[str, Any]:
    reports = sorted((source / "target/surefire-reports").glob("TEST-*.xml"))
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    entries = []
    test_cases: list[str] = []
    for report in reports:
        root = ET.parse(report).getroot()
        entry = {
            key: int(root.attrib.get(key, "0"))
            for key in ("tests", "failures", "errors", "skipped")
        }
        for key, value in entry.items():
            totals[key] += value
        for case in root.iter("testcase"):
            class_name = case.attrib.get("classname", "")
            name = case.attrib.get("name", "")
            require(bool(class_name and name), f"SUREFIRE_TESTCASE_ID_MISSING:{report.name}")
            test_cases.append(f"{class_name}#{name}")
        entries.append(
            {
                "path": str(report.relative_to(source)),
                "sha256": sha256_file(report),
                "bytes": report.stat().st_size,
                **entry,
            }
        )
    require(len(test_cases) == len(set(test_cases)), "SUREFIRE_TESTCASE_ID_DUPLICATE")
    return {"reports": entries, "test_cases": sorted(test_cases), **totals}


def target_pom_audit(target: Path, repository: dict[str, Any]) -> dict[str, Any]:
    tree = ET.parse(target / "pom.xml")
    root = tree.getroot()
    parent = root.find(f"{{{MAVEN_NS}}}parent")
    require(parent is not None, "TARGET_POM_PARENT_MISSING")
    assert parent is not None
    parent_group = parent.findtext(f"{{{MAVEN_NS}}}groupId", "")
    parent_artifact = parent.findtext(f"{{{MAVEN_NS}}}artifactId", "")
    parent_version = parent.findtext(f"{{{MAVEN_NS}}}version", "")
    properties = root.find(f"{{{MAVEN_NS}}}properties")
    java_version = (
        properties.findtext(f"{{{MAVEN_NS}}}java.version", "")
        if properties is not None
        else ""
    )
    expected = repository["target"]
    return {
        "parent_group": parent_group,
        "parent_artifact": parent_artifact,
        "spring_boot": parent_version,
        "java": java_version,
        "matched": (
            parent_group == "org.springframework.boot"
            and parent_artifact == "spring-boot-starter-parent"
            and parent_version == expected["spring_boot"]
            and java_version == expected["java"]
        ),
        "pom_sha256": sha256_file(target / "pom.xml"),
        "pom_bytes": (target / "pom.xml").stat().st_size,
    }


def transform_target(
    source: Path,
    target: Path,
    repository: dict[str, Any],
    maven: Path,
    target_java_home: Path,
    maven_isolation: dict[str, Path],
) -> dict[str, Any]:
    return protected_execution_gate("untrusted-maven-openrewrite-transform")

    # See native_build: retained for a future protected runner only.
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(
            ".git",
            ".elmos",
            "target",
            "qualification-pom.xml",
            "qualification-native-build",
        ),
    )
    target_profile = repository["target"]
    recipe = ROOT / target_profile["recipe_path"]
    installed_recipe = target / ".elmos/openrewrite.yml"
    installed_recipe.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(recipe, installed_recipe)
    command = [
        str(maven),
        "-B",
        "-ntp",
        *exact_maven_arguments(maven_isolation),
        f"org.openrewrite.maven:rewrite-maven-plugin:{target_profile['rewrite_maven_plugin']}:run",
        "-Drewrite.configLocation=.elmos/openrewrite.yml",
        f"-Drewrite.activeRecipes={target_profile['recipe_id']}",
        "-Drewrite.recipeArtifactCoordinates="
        f"org.openrewrite.recipe:rewrite-spring:{target_profile['rewrite_spring']}",
        "-Drewrite.exportDatatables=true",
    ]
    execution = run_command(
        command,
        cwd=target,
        environment=exact_maven_environment(target_java_home, maven_isolation),
        timeout_seconds=repository["timeouts_seconds"]["target_transform"],
    )
    pom = target_pom_audit(target, repository) if (target / "pom.xml").is_file() else None
    recipe_validation_error = "Recipe validation error" in execution["output"]
    status = (
        "PASSED_LOCAL"
        if execution["exit_code"] == 0
        and not execution["timed_out"]
        and not recipe_validation_error
        and pom is not None
        and pom["matched"]
        else "FAILED"
    )
    return {
        "status": status,
        "execution": execution,
        "recipe": {
            "path": target_profile["recipe_path"],
            "id": target_profile["recipe_id"],
            "sha256": sha256_file(recipe),
            "bytes": recipe.stat().st_size,
            "rewrite_maven_plugin": target_profile["rewrite_maven_plugin"],
            "rewrite_spring": target_profile["rewrite_spring"],
        },
        "recipe_validation_error": recipe_validation_error,
        "pom": pom,
    }


def qualify_target(
    *,
    source: Path,
    workspace: Path,
    repository: dict[str, Any],
    maven: Path,
    cmake: Path,
    cxx: Path,
    make: Path,
    maven_isolation: dict[str, Path],
    target_java_home: Path | None,
    source_reports: dict[str, Any],
    expected_tests: int,
) -> dict[str, Any]:
    return {
        **protected_execution_gate("untrusted-target-build-and-test"),
        "source_green_required": True,
    }

    # See native_build: retained for a future protected runner only.
    if target_java_home is None:
        return {
            "status": "NOT_RUN_TARGET_TOOLCHAIN_NOT_DECLARED",
            "source_green_required": True,
        }
    identities = repository["toolchain_contract"]["executables"]
    target_java = exact_executable_audit(
        name="target_java",
        executable=target_java_home / "bin/java",
        identity=identities["target_java"],
        cwd=source,
        required_root=target_java_home,
    )
    target_javac = exact_executable_audit(
        name="target_javac",
        executable=target_java_home / "bin/javac",
        identity=identities["target_javac"],
        cwd=source,
        required_root=target_java_home,
    )
    target_maven_environment = exact_maven_environment(
        target_java_home, maven_isolation
    )
    target_maven = exact_executable_audit(
        name="maven",
        executable=maven,
        identity=identities["maven"],
        cwd=source,
        environment=target_maven_environment,
        command_prefix=exact_maven_arguments(maven_isolation),
    )
    target_maven["java_home_matched"] = (
        f"runtime: {target_java_home.resolve(strict=True)}"
        in target_maven.get("execution", {}).get("output", "")
    )
    target_maven["matched"] = bool(
        target_maven["matched"] and target_maven["java_home_matched"]
    )
    target_toolchain = {
        "java": target_java,
        "javac": target_javac,
        "maven": target_maven,
    }
    if not all(item["matched"] for item in target_toolchain.values()):
        return {
            "status": "FAILED_TARGET_TOOLCHAIN_IDENTITY",
            "source_green_required": True,
            "toolchain": target_toolchain,
        }
    target = workspace / "migrated"
    transformation = transform_target(
        source,
        target,
        repository,
        maven,
        target_java_home,
        maven_isolation,
    )
    if transformation["status"] != "PASSED_LOCAL":
        return {
            "status": "FAILED_TRANSFORMATION",
            "source_green_required": True,
            "toolchain": target_toolchain,
            "transformation": transformation,
        }
    overlay = create_vintage_overlay(target, repository, target_profile=True)
    native = native_build(
        target,
        target_java_home,
        repository,
        cmake=cmake,
        cxx=cxx,
        make=make,
    )
    if native["status"] != "PASSED_LOCAL":
        return {
            "status": "FAILED_TARGET_NATIVE_PREREQUISITE",
            "source_green_required": True,
            "toolchain": target_toolchain,
            "transformation": transformation,
            "test_discovery_overlay": overlay,
            "native_prerequisite": native,
        }
    execution = source_test_command(
        target,
        maven,
        target_java_home,
        native,
        repository,
        maven_isolation,
        timeout_key="target_tests",
    )
    reports = surefire_summary(target)
    execution["surefire"] = reports
    same_test_oracle = reports["test_cases"] == source_reports["test_cases"]
    passed = (
        execution["exit_code"] == 0
        and not execution["timed_out"]
        and reports["tests"] == expected_tests
        and len(reports["test_cases"]) == expected_tests
        and reports["failures"] == 0
        and reports["errors"] == 0
        and reports["skipped"] == 0
        and same_test_oracle
    )
    return {
        "status": "PASSED_LOCAL" if passed else "FAILED_TARGET_TESTS",
        "source_green_required": True,
        "toolchain": target_toolchain,
        "transformation": transformation,
        "test_discovery_overlay": overlay,
        "native_prerequisite": native,
        "execution": execution,
        "same_complete_test_oracle": same_test_oracle,
    }


def qualification(
    *,
    manifest_path: Path,
    repository_id: str,
    archive_input: Path | None,
    workspace: Path,
    output: Path,
    java_home: Path,
    maven: Path,
    cmake: Path,
    cxx: Path,
    make: Path,
    target_java_home: Path | None = None,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    repository = repository_by_id(manifest, repository_id)
    minimum_free = int(manifest["minimum_free_bytes"])
    check_workspace(workspace, minimum_free)

    archive = workspace / "source.tar.gz"
    fetch: dict[str, Any] | None = None
    if archive_input is None:
        fetch = fetch_archive(repository["archive"]["url"], archive)
    else:
        require(archive_input.is_file(), "LOCAL_ARCHIVE_MISSING")
        shutil.copyfile(archive_input, archive)
    archive_digest = sha256_file(archive)
    require(archive_digest == repository["archive"]["sha256"], "ARCHIVE_DIGEST_MISMATCH")
    require(
        archive.stat().st_size == repository["archive"]["bytes"],
        "ARCHIVE_SIZE_MISMATCH",
    )
    source = extract_archive(archive, workspace, repository["archive"]["root"])

    files = verify_required_files(source, repository)
    pom = pom_audit(source, repository)
    inventory = test_inventory(source, repository)
    overlay = create_vintage_overlay(source, repository)
    maven_isolation = prepare_maven_isolation(workspace)
    contract = repository["toolchain_contract"]
    require(
        platform.system() == contract["platform_system"]
        and platform.machine() == contract["platform_machine"],
        "TOOLCHAIN_PLATFORM_MISMATCH",
    )
    identities = contract["executables"]
    java = exact_executable_audit(
        name="source_java",
        executable=java_home / "bin/java",
        identity=identities["source_java"],
        cwd=workspace,
        required_root=java_home,
    )
    javac = exact_executable_audit(
        name="source_javac",
        executable=java_home / "bin/javac",
        identity=identities["source_javac"],
        cwd=workspace,
        required_root=java_home,
    )
    maven_environment = exact_maven_environment(java_home, maven_isolation)
    maven_record = exact_executable_audit(
        name="maven",
        executable=maven,
        identity=identities["maven"],
        cwd=workspace,
        environment=maven_environment,
        command_prefix=exact_maven_arguments(maven_isolation),
    )
    maven_record["java_home_matched"] = (
        f"runtime: {java_home.resolve(strict=True)}"
        in maven_record.get("execution", {}).get("output", "")
    )
    maven_record["matched"] = bool(
        maven_record["matched"] and maven_record["java_home_matched"]
    )
    if not maven_record["matched"]:
        maven_record["status"] = "FAILED_MAVEN_OR_JAVA_IDENTITY"
    cmake_record = exact_executable_audit(
        name="cmake",
        executable=cmake,
        identity=identities["cmake"],
        cwd=workspace,
    )
    cxx_record = exact_executable_audit(
        name="cxx",
        executable=cxx,
        identity=identities["cxx"],
        cwd=workspace,
    )
    make_record = exact_executable_audit(
        name="make",
        executable=make,
        identity=identities["make"],
        cwd=workspace,
    )
    toolchain_records = {
        "java": java,
        "javac": javac,
        "maven": maven_record,
        "cmake": cmake_record,
        "cxx": cxx_record,
        "make": make_record,
    }
    toolchains_green = all(item["matched"] for item in toolchain_records.values())

    native = protected_execution_gate("untrusted-cmake-native-build")
    services = service_image_audit(repository, source)
    source_tests = None
    source_test_status = ROOTLESS_EXECUTION_STATUS
    target_execution = {
        **protected_execution_gate("untrusted-target-build-and-test"),
        "source_green_required": True,
    }
    target_status = target_execution["status"]
    blocker_codes = [ROOTLESS_EXECUTION_STATUS]
    if not toolchains_green:
        blocker_codes.append("EXACT_TOOLCHAIN_MISMATCH")
    if any(item["status"] != "AVAILABLE_RESOLVED_DIGEST_LOCAL" for item in services):
        blocker_codes.append("PINNED_SERVICE_IMAGES_NOT_AVAILABLE")
    overall_status = ROOTLESS_EXECUTION_STATUS

    evidence = {
        "schema_version": 1,
        "record_type": "PUBLIC_REPOSITORY_LOCAL_QUALIFICATION",
        "evidence_class": "LOCAL_PUBLIC_ENGINEERING",
        "certification_eligible": False,
        "certification_status": "NOT_CERTIFIED",
        "customer_repository": False,
        "customer_outcome_status": "NOT_EVALUATED",
        "independent_verification": False,
        "independent_review_status": "NOT_RUN",
        "external_execution_status": "NOT_RUN",
        "observed_at": utc_now(),
        "pack_key": manifest["pack_key"],
        "repository": {
            "id": repository_id,
            "url": repository["repository_url"],
            "commit_sha": repository["commit_sha"],
            "tree_sha": repository["tree_sha"],
            "archive": {
                "url": repository["archive"]["url"],
                "sha256": archive_digest,
                "bytes": archive.stat().st_size,
                "provided_locally": archive_input is not None,
                "fetch": fetch,
            },
        },
        "separate_public_candidates": manifest.get("separate_public_candidates", []),
        "execution_environment": {
            "os": platform.platform(),
            "architecture": platform.machine(),
            "minimum_free_bytes_stop_line": minimum_free,
            "free_bytes_after_run": shutil.disk_usage(workspace).free,
        },
        "protected_execution_gate": protected_execution_gate(
            "public-repository-source-transform-target"
        ),
        "source_tuple": repository["source_tuple"],
        "verified_files": files,
        "pom_audit": pom,
        "test_inventory": inventory,
        "original_repository_default": {
            "ci_build_command": "mvn -B -DskipTests package",
            "ci_executes_tests": False,
            "junit_vintage_declared": pom["junit_vintage_declared"],
            "junit_platform_tests_statically_discoverable": inventory[
                "junit_jupiter_tests"
            ],
            "junit4_tests_not_discoverable_without_vintage": inventory["junit4_tests"],
            "runtime_execution_in_this_replay": source_test_status,
        },
        "test_discovery_overlay": overlay,
        "toolchains": toolchain_records,
        "maven_isolation": {
            "status": "ENFORCED",
            "strict_checksums": True,
            "inherited_maven_options": False,
            "root": str(maven_isolation["root"]),
            "user_home": str(maven_isolation["user_home"]),
            "local_repository": str(maven_isolation["local_repository"]),
        },
        "native_prerequisite": native,
        "service_prerequisites": services,
        "source_baseline": {
            "status": source_test_status,
            "all_declared_tests_required": True,
            "expected_tests": inventory["total_tests"],
            "execution": source_tests,
        },
        "target_execution": target_execution,
        "overall_status": overall_status,
        "blocker_codes": blocker_codes,
        "claims": {
            "migration_success_rate": "NOT_EVALUATED",
            "behavioral_equivalence": (
                "OBSERVED_COMPLETE_TEST_ORACLE_PARITY"
                if target_status == "PASSED_LOCAL"
                else "NOT_EVALUATED"
            ),
            "customer_acceptance": "NOT_RUN",
            "independent_external_validation": "NOT_RUN",
        },
        "replay": {
            "manifest_path": str(manifest_path.relative_to(ROOT)),
            "command": [
                "python3",
                "scripts/operations/qualify_spring_public_repository.py",
                "--repository-id",
                repository_id,
                "--archive",
                "<verified-source.tar.gz>",
                "--workspace",
                "<empty-workspace>",
                "--output",
                str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output),
                "--java-home",
                str(java_home),
                "--target-java-home",
                str(target_java_home) if target_java_home else "<java-21-home>",
                "--maven-executable",
                str(maven),
                "--cmake-executable",
                str(cmake),
                "--cxx-executable",
                str(cxx),
                "--make-executable",
                str(make),
            ],
        },
    }
    atomic_json(output, evidence)
    return evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--target-java-home", type=Path)
    parser.add_argument("--maven-executable", type=Path, required=True)
    parser.add_argument("--cmake-executable", type=Path, required=True)
    parser.add_argument("--cxx-executable", type=Path, required=True)
    parser.add_argument("--make-executable", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        evidence = qualification(
            manifest_path=args.manifest.resolve(),
            repository_id=args.repository_id,
            archive_input=args.archive.resolve() if args.archive else None,
            workspace=args.workspace.resolve(),
            output=args.output.resolve(),
            java_home=args.java_home.resolve(),
            maven=args.maven_executable.resolve(),
            cmake=args.cmake_executable.resolve(),
            cxx=args.cxx_executable.resolve(),
            make=args.make_executable.resolve(),
            target_java_home=(
                args.target_java_home.resolve() if args.target_java_home else None
            ),
        )
    except (QualificationError, OSError, ValueError, ET.ParseError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"{evidence['overall_status']}: {args.repository_id}")
    return (
        0
        if evidence["overall_status"]
        == "PASSED_LOCAL_SOURCE_AND_TARGET_TEST_ORACLE"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
