#!/usr/bin/env python3
"""Run the exact Spring enterprise contract against pinned local containers.

The local execution class is useful engineering evidence.  The staging class
additionally requires a protected, dedicated, rootless GitHub Actions runner,
but remains self-attested and cannot produce a Batch 30 certification decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "framework-packs/spring-boot-2-7-18-to-3-5-3"
FIXTURES = {
    "source": {
        "directory": PACK / "corpus/development/enterprise-source",
        "java": "17.0.11",
        "spring_boot": "2.7.18",
    },
    "target": {
        "directory": PACK / "corpus/development/enterprise-target",
        "java": "21.0.11",
        "spring_boot": "3.5.3",
    },
}
IMAGES = {
    "postgres": "postgres@sha256:6567bca8d7bc8c82c5922425a0baee57be8402df92bae5eacad5f01ae9544daa",
    "rabbitmq": "rabbitmq@sha256:5cbd7145b0306399ad68422c3350b6cbd1bb95704b39f5896480e5b6d4238a04",
}
EXPECTED_MAVEN = "3.9.11"
EXPECTED_TESTS = 4
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
MAVEN_NAMESPACE = {"m": "http://maven.apache.org/POM/4.0.0"}


class EnterpriseGateError(RuntimeError):
    """The enterprise execution contract was not satisfied."""


def _run(
    command: Sequence[str],
    *,
    cwd: Path = ROOT,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        env=None if environment is None else dict(environment),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        tail = "\n".join(result.stdout.splitlines()[-80:])
        raise EnterpriseGateError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{tail}"
        )
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fixture_manifest() -> dict[str, Any]:
    files: dict[str, str] = {}
    for fixture in FIXTURES.values():
        directory = Path(fixture["directory"])
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or "target" in path.parts:
                continue
            relative = path.relative_to(ROOT).as_posix()
            files[relative] = _sha256(path)
    encoded = json.dumps(files, separators=(",", ":"), sort_keys=True).encode()
    return {
        "algorithm": "sha256",
        "digest": hashlib.sha256(encoded).hexdigest(),
        "file_count": len(files),
        "files": files,
    }


def _verify_fixture_metadata() -> None:
    for name, fixture in FIXTURES.items():
        pom = Path(fixture["directory"]) / "pom.xml"
        root = ET.parse(pom).getroot()
        boot = root.findtext("m:parent/m:version", namespaces=MAVEN_NAMESPACE)
        java = root.findtext("m:properties/m:java.version", namespaces=MAVEN_NAMESPACE)
        if boot != fixture["spring_boot"] or java != fixture["java"].split(".", 1)[0]:
            raise EnterpriseGateError(
                f"{name} POM tuple drift: Spring Boot {boot}, Java {java}"
            )
    target_pom = Path(FIXTURES["target"]["directory"]) / "pom.xml"
    target_root = ET.parse(target_pom).getroot()
    test_source = target_root.findtext(
        "m:build/m:testSourceDirectory", namespaces=MAVEN_NAMESPACE
    )
    if test_source != "../enterprise-source/src/test/java":
        raise EnterpriseGateError("target must execute the exact source enterprise contract")


def _java_version(java_home: Path) -> str:
    java = java_home / "bin/java"
    if not java.is_file():
        raise EnterpriseGateError(f"Java executable not found: {java}")
    output = _run([str(java), "-version"]).stdout
    match = re.search(r'version "([0-9]+(?:\.[0-9]+){1,3})', output)
    if match is None:
        raise EnterpriseGateError(f"could not parse Java version from {java}")
    return match.group(1)


def _maven_version(maven: Path) -> str:
    if not maven.is_file():
        raise EnterpriseGateError(f"Maven executable not found: {maven}")
    output = _run([str(maven), "--version"]).stdout
    match = re.search(r"Apache Maven ([0-9.]+)", output)
    if match is None:
        raise EnterpriseGateError("could not parse Maven version")
    return match.group(1)


def _docker_state() -> dict[str, Any]:
    version = json.loads(
        _run(["docker", "version", "--format", "{{json .}}"]).stdout
    )
    security_options = json.loads(
        _run(["docker", "info", "--format", "{{json .SecurityOptions}}"]).stdout
    )
    server = version.get("Server")
    if not isinstance(server, dict) or server.get("Os") != "linux":
        raise EnterpriseGateError("a reachable Linux Docker server is required")
    if server.get("Arch") not in {"amd64", "arm64"}:
        raise EnterpriseGateError("Docker server architecture must be amd64 or arm64")
    minimum_api = str(server.get("MinAPIVersion", ""))
    if re.fullmatch(r"[0-9]+\.[0-9]+", minimum_api) is None:
        raise EnterpriseGateError("Docker minimum API version is unavailable")
    return {
        "server_version": server.get("Version"),
        "server_api_version": server.get("ApiVersion"),
        "minimum_api_version": minimum_api,
        "operating_system": server.get("Platform", {}).get("Name") or server.get("Os"),
        "architecture": server.get("Arch"),
        "security_options": security_options,
        "rootless": any("rootless" in str(option).lower() for option in security_options),
    }


def _verify_images() -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for name, reference in IMAGES.items():
        _run(["docker", "pull", reference])
        inspect = json.loads(
            _run(
                ["docker", "image", "inspect", reference, "--format", "{{json .}}"]
            ).stdout
        )
        repository_digests = inspect.get("RepoDigests", [])
        if reference not in repository_digests:
            raise EnterpriseGateError(
                f"Docker image {name} does not expose the required digest {reference}"
            )
        results[name] = {
            "reference": reference,
            "image_id": inspect.get("Id"),
            "os": inspect.get("Os"),
            "architecture": inspect.get("Architecture"),
        }
    return results


def _require_staging_context(
    environment: Mapping[str, str], docker: Mapping[str, Any], revision: str, output: Path
) -> dict[str, str]:
    required = {
        "CI": "true",
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": "refs/heads/main",
        "ELMOS_SPRING_RUNNER_CLASS": "DEDICATED_ROOTLESS",
    }
    for name, expected in required.items():
        if environment.get(name) != expected:
            raise EnterpriseGateError(f"staging requires exact {name}={expected}")
    fields = {
        "runner_id": environment.get("ELMOS_SPRING_RUNNER_ID", ""),
        "runner_attestation_digest": environment.get(
            "ELMOS_SPRING_RUNNER_ATTESTATION_DIGEST", ""
        ),
        "environment_id": environment.get("ELMOS_SPRING_ENVIRONMENT_ID", ""),
        "deployment_id": environment.get("ELMOS_SPRING_DEPLOYMENT_ID", ""),
        "expected_revision": environment.get("ELMOS_SPRING_EXPECTED_REVISION", ""),
    }
    if not fields["runner_id"] or not fields["environment_id"] or not fields["deployment_id"]:
        raise EnterpriseGateError("staging runner/environment/deployment identities are required")
    if SHA256.fullmatch(fields["runner_attestation_digest"]) is None:
        raise EnterpriseGateError("staging runner attestation must be one sha256 digest")
    if fields["expected_revision"] != revision:
        raise EnterpriseGateError("staging expected revision does not match checked-out HEAD")
    if not docker.get("rootless"):
        raise EnterpriseGateError("staging requires a rootless Docker daemon")
    if output.resolve().is_relative_to(ROOT.resolve()):
        raise EnterpriseGateError("staging evidence output must be outside the repository")
    return fields


def _parse_report(report: Path) -> dict[str, int]:
    if not report.is_file():
        raise EnterpriseGateError(f"Surefire report missing: {report}")
    root = ET.parse(report).getroot()
    result = {
        key: int(root.attrib.get(key, "0"))
        for key in ("tests", "failures", "errors", "skipped")
    }
    if result != {
        "tests": EXPECTED_TESTS,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }:
        raise EnterpriseGateError(f"unexpected enterprise test result: {result}")
    return result


def _run_fixture(
    name: str,
    fixture: Mapping[str, Any],
    java_home: Path,
    maven: Path,
    docker_api: str,
    log_directory: Path,
) -> dict[str, Any]:
    actual_java = _java_version(java_home)
    if actual_java != fixture["java"]:
        raise EnterpriseGateError(
            f"{name} requires Java {fixture['java']}, found {actual_java}"
        )
    environment = dict(os.environ)
    environment["JAVA_HOME"] = str(java_home)
    environment["DOCKER_API_VERSION"] = docker_api
    result = _run(
        [
            str(maven),
            "-B",
            "-q",
            f"-Dapi.version={docker_api}",
            "-Dtest=EnterpriseContractIT",
            "clean",
            "test",
        ],
        cwd=Path(fixture["directory"]),
        environment=environment,
    )
    log = log_directory / f"{name}.log"
    log.write_text(result.stdout, encoding="utf-8")
    report = (
        Path(fixture["directory"])
        / "target/surefire-reports/TEST-io.elmos.enterprise.EnterpriseContractIT.xml"
    )
    return {
        "spring_boot": fixture["spring_boot"],
        "java": actual_java,
        "tests": _parse_report(report),
        "log_sha256": _sha256(log),
    }


def run_gate(arguments: argparse.Namespace, environment: Mapping[str, str]) -> dict[str, Any]:
    revision = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    if COMMIT.fullmatch(revision) is None:
        raise EnterpriseGateError("repository revision is not one exact commit")
    maven = Path(arguments.maven).expanduser().resolve()
    maven_version = _maven_version(maven)
    if maven_version != EXPECTED_MAVEN:
        raise EnterpriseGateError(
            f"enterprise gate requires Maven {EXPECTED_MAVEN}, found {maven_version}"
        )
    docker = _docker_state()
    output = Path(arguments.output).expanduser().resolve()
    staging: dict[str, str] | None = None
    if arguments.execution_class == "staging":
        staging = _require_staging_context(environment, docker, revision, output)
        workspace_status = _run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"]
        ).stdout
        if workspace_status:
            raise EnterpriseGateError("staging checkout must be clean before execution")

    _verify_fixture_metadata()
    fixture_manifest = _fixture_manifest()
    images = _verify_images()
    with tempfile.TemporaryDirectory(prefix="elmos-spring-enterprise-") as directory:
        log_directory = Path(directory)
        executions = {
            "source": _run_fixture(
                "source",
                FIXTURES["source"],
                Path(arguments.java17_home).expanduser().resolve(),
                maven,
                docker["minimum_api_version"],
                log_directory,
            ),
            "target": _run_fixture(
                "target",
                FIXTURES["target"],
                Path(arguments.java21_home).expanduser().resolve(),
                maven,
                docker["minimum_api_version"],
                log_directory,
            ),
        }
    if _fixture_manifest() != fixture_manifest:
        raise EnterpriseGateError("enterprise fixture bytes changed during execution")

    evidence = {
        "schema_version": "elmos.batch30.spring-enterprise-container-evidence.v1",
        "pack_key": PACK.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "revision": revision,
        "execution_class": arguments.execution_class,
        "execution_status": (
            "STAGING_RUNNER_EXECUTED_SELF_ATTESTED"
            if arguments.execution_class == "staging"
            else "PASSED_LOCAL"
        ),
        "runner_sha256": _sha256(Path(__file__)),
        "fixture_manifest": fixture_manifest,
        "scope": [
            "role-based HTTP security and fail-closed configuration",
            "PostgreSQL schema and JPA persistence",
            "atomic transaction rollback and durable outbox",
            "pessimistic locking and oversell prevention",
            "RabbitMQ publisher confirms and idempotent consumption",
            "bounded actuator exposure",
        ],
        "maven": maven_version,
        "docker": docker,
        "images": images,
        "executions": executions,
        "staging_identity": staging,
        "evidence_boundaries": {
            "customer_acceptance": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "external_certification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-class", choices=("local", "staging"), default="local")
    parser.add_argument("--output", required=True)
    parser.add_argument("--maven", default=os.environ.get("ELMOS_MAVEN_EXECUTABLE", "mvn"))
    parser.add_argument("--java17-home", default=os.environ.get("ELMOS_JAVA17_HOME", ""))
    parser.add_argument("--java21-home", default=os.environ.get("ELMOS_JAVA21_HOME", ""))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if not arguments.java17_home or not arguments.java21_home:
        print("ERROR: exact Java 17 and Java 21 homes are required", file=sys.stderr)
        return 2
    try:
        evidence = run_gate(arguments, os.environ)
    except (EnterpriseGateError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps({
        "execution_status": evidence["execution_status"],
        "certification": evidence["evidence_boundaries"]["certification"],
        "output": str(Path(arguments.output).expanduser().resolve()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
