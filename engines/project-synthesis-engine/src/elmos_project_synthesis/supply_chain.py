from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Never
from xml.etree import ElementTree

from .models import (
    SynthesisRequest,
    p0_request_blockers,
    p0_scope_payload,
)
from .project_graphs import validate_workspace_graphs

SBOM_PATH = "requirements/dependency-sbom.cdx.json"
MAVEN_TREE_PATH = ".elmos/dependencies/java-dependency-tree.json"
ARTIFACT_HASH_EVIDENCE_PATH = ".elmos/dependencies/artifact-hashes.json"
PROVIDER_OBSERVATION_PATH = "docs/project-synthesis/provider-observation-2026-09-04.json"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_OBJECT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
ALLOWED_SOURCE_ORIGINS = frozenset(
    {
        "https://github.com/zpcaiai/elmos.git",
        "git@github.com:zpcaiai/elmos.git",
    }
)
REQUIRED_SOURCE_PATHS = (
    "AGENTS.md",
    "Makefile",
    "engines/project-synthesis-engine/pyproject.toml",
    "docs/project-synthesis/p0-launch-scope-v1.json",
)
_EXACT_PYTHON_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^\s;]+)$")
_GRADLE_COORDINATE = re.compile(r"^([^:#=]+):([^:#=]+):([^=]+)=")
_GO_REQUIREMENT = re.compile(r"^([^\s]+)\s+(v[^\s]+)(?:\s+//\s+indirect)?$")
_PNPM_PACKAGE = re.compile(r"^\s{2}(['\"]?)(.+?)\1:\s*$")
_PNPM_INTEGRITY = re.compile(r"integrity:\s*sha512-([A-Za-z0-9+/]+={0,2})")


class SupplyChainFailure(RuntimeError):
    """A stable, fail-closed supply-chain contract failure."""


def canonical_json(document: Any) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def json_artifact_bytes(document: Any) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _scope_sha256() -> str:
    return sha256_bytes(canonical_json(p0_scope_payload()))


def _component(
    ecosystem: str,
    name: str,
    version: str,
    *,
    source: str,
    resolved: bool,
    hashes: tuple[str, ...] = (),
) -> dict[str, Any]:
    normalized_name = name.strip()
    normalized_version = version.strip() or "UNRESOLVED"
    reference = f"pkg:{ecosystem}/{normalized_name}@{normalized_version}"
    result: dict[str, Any] = {
        "type": "library",
        "bom-ref": reference,
        "name": normalized_name,
        "version": normalized_version,
        "properties": [
            {"name": "elmos:ecosystem", "value": ecosystem},
            {"name": "elmos:evidence-source", "value": source},
            {
                "name": "elmos:resolution-status",
                "value": "RESOLVED_FROM_LOCK" if resolved else "DECLARED_ONLY",
            },
        ],
    }
    normalized_hashes: set[tuple[str, str]] = set()
    for value in hashes:
        if value.startswith("sha256:"):
            digest = value.removeprefix("sha256:")
            if SHA256_PATTERN.fullmatch(digest):
                normalized_hashes.add(("SHA-256", digest))
        elif value.startswith("sha512:"):
            encoded = value.removeprefix("sha512:")
            if _valid_base64_digest(encoded, 64):
                normalized_hashes.add(("SHA-512", base64.b64decode(encoded, validate=True).hex()))
        elif value.startswith("h1:"):
            encoded = value.removeprefix("h1:")
            if _valid_base64_digest(encoded, 32):
                normalized_hashes.add(("SHA-256", base64.b64decode(encoded, validate=True).hex()))
        elif SHA256_PATTERN.fullmatch(value):
            normalized_hashes.add(("SHA-256", value))
    if normalized_hashes:
        result["hashes"] = [
            {"alg": algorithm, "content": digest}
            for algorithm, digest in sorted(normalized_hashes)
        ]
    return result


def _add_component(components: dict[str, dict[str, Any]], item: dict[str, Any]) -> str:
    reference = str(item["bom-ref"])
    previous = components.get(reference)
    if previous is None:
        components[reference] = item
    elif previous != item:
        identity_keys = ("type", "bom-ref", "name", "version")
        if any(previous.get(key) != item.get(key) for key in identity_keys):
            raise SupplyChainFailure(f"SBOM_COMPONENT_COLLISION:{reference}")
        merged = {key: previous[key] for key in identity_keys}
        properties = {
            (str(property_value["name"]), str(property_value["value"]))
            for candidate in (previous, item)
            for property_value in candidate.get("properties", [])
            if isinstance(property_value, dict)
            and isinstance(property_value.get("name"), str)
            and isinstance(property_value.get("value"), str)
            and property_value.get("name") != "elmos:resolution-status"
        }
        resolution_values = {
            str(property_value["value"])
            for candidate in (previous, item)
            for property_value in candidate.get("properties", [])
            if isinstance(property_value, dict)
            and property_value.get("name") == "elmos:resolution-status"
            and isinstance(property_value.get("value"), str)
        }
        properties.add(
            (
                "elmos:resolution-status",
                "RESOLVED_FROM_LOCK" if "RESOLVED_FROM_LOCK" in resolution_values else "DECLARED_ONLY",
            )
        )
        merged["properties"] = [
            {"name": name, "value": value} for name, value in sorted(properties)
        ]
        hashes = {
            (str(hash_value["alg"]), str(hash_value["content"]))
            for candidate in (previous, item)
            for hash_value in candidate.get("hashes", [])
            if isinstance(hash_value, dict)
            and isinstance(hash_value.get("alg"), str)
            and isinstance(hash_value.get("content"), str)
        }
        if hashes:
            merged["hashes"] = [
                {"alg": algorithm, "content": content} for algorithm, content in sorted(hashes)
            ]
        components[reference] = merged
    return reference


def _has_strong_integrity(component: Mapping[str, Any]) -> bool:
    hashes = component.get("hashes")
    return isinstance(hashes, list) and any(
        isinstance(item, dict)
        and item.get("alg") in {"SHA-256", "SHA-512"}
        and isinstance(item.get("content"), str)
        and re.fullmatch(r"[0-9a-f]+", item["content"]) is not None
        and len(item["content"]) == (64 if item["alg"] == "SHA-256" else 128)
        for item in hashes
    )


def _valid_base64_digest(value: str, expected_bytes: int) -> bool:
    try:
        return len(base64.b64decode(value, validate=True)) == expected_bytes
    except (binascii.Error, ValueError):
        return False


def _artifact_hash_evidence(
    files: Mapping[str, str],
    *,
    request_sha256: str,
) -> dict[str, dict[str, Any]]:
    content = files.get(ARTIFACT_HASH_EVIDENCE_PATH)
    if content is None:
        return {}
    try:
        document = json.loads(content)
    except json.JSONDecodeError as error:
        raise SupplyChainFailure("ARTIFACT_HASH_EVIDENCE_INVALID") from error
    records = document.get("artifacts") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or set(document)
        != {"schema_version", "kind", "request_sha256", "collector", "artifacts", "evidence_boundary"}
        or document.get("schema_version") != "1.0.0"
        or document.get("kind") != "elmos.project-synthesis.native-artifact-hashes"
        or document.get("request_sha256") != request_sha256
        or document.get("collector") != "repository-owned-local-cache-sha256-v1"
        or document.get("evidence_boundary") != "LOCAL_ENGINEERING_SELF_ATTESTED"
        or not isinstance(records, list)
    ):
        raise SupplyChainFailure("ARTIFACT_HASH_EVIDENCE_INVALID")
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if (
            not isinstance(record, dict)
            or set(record)
            != {"bom_ref", "sha256", "byte_count", "cache_kind", "cache_relative_path"}
            or not isinstance(record.get("bom_ref"), str)
            or not record["bom_ref"].startswith("pkg:maven/")
            or not isinstance(record.get("sha256"), str)
            or SHA256_PATTERN.fullmatch(record["sha256"]) is None
            or not isinstance(record.get("byte_count"), int)
            or record["byte_count"] <= 0
            or record.get("cache_kind") not in {"maven-local-repository", "gradle-module-cache"}
            or not isinstance(record.get("cache_relative_path"), str)
            or not _safe_evidence_relative_path(record["cache_relative_path"])
            or record["bom_ref"] in result
        ):
            raise SupplyChainFailure("ARTIFACT_HASH_EVIDENCE_INVALID")
        result[record["bom_ref"]] = record
    return result


def _safe_evidence_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts and "\\" not in value


def _uv_packages(content: str, *, source: str, project_name: str) -> list[dict[str, Any]]:
    try:
        document = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise SupplyChainFailure("PYTHON_UV_LOCK_INVALID") from error
    packages = document.get("package")
    if document.get("version") != 1 or not isinstance(packages, list):
        raise SupplyChainFailure("PYTHON_UV_LOCK_INVALID")
    result: list[dict[str, Any]] = []
    for package in packages:
        if (
            not isinstance(package, dict)
            or not isinstance(package.get("name"), str)
            or not isinstance(package.get("version"), str)
        ):
            raise SupplyChainFailure("PYTHON_UV_LOCK_PACKAGE_INVALID")
        package_source = package.get("source")
        if package["name"] == project_name and isinstance(package_source, dict) and "editable" in package_source:
            continue
        hashes: list[str] = []
        sdist = package.get("sdist")
        if isinstance(sdist, dict) and isinstance(sdist.get("hash"), str):
            hashes.append(sdist["hash"])
        wheels = package.get("wheels", [])
        if isinstance(wheels, list):
            hashes.extend(
                wheel["hash"]
                for wheel in wheels
                if isinstance(wheel, dict) and isinstance(wheel.get("hash"), str)
            )
        result.append(
            _component(
                "pypi",
                package["name"],
                package["version"],
                source=source,
                resolved=True,
                hashes=tuple(hashes),
            )
        )
    return result


def _python_declarations(content: str, *, source: str) -> list[dict[str, Any]]:
    try:
        document = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise SupplyChainFailure("PYTHON_PROJECT_MANIFEST_INVALID") from error
    project = document.get("project")
    requirements: list[str] = []
    if isinstance(project, dict) and isinstance(project.get("dependencies"), list):
        requirements.extend(value for value in project["dependencies"] if isinstance(value, str))
    groups = document.get("dependency-groups")
    if isinstance(groups, dict):
        for values in groups.values():
            if isinstance(values, list):
                requirements.extend(value for value in values if isinstance(value, str))
    result: list[dict[str, Any]] = []
    for requirement in requirements:
        match = _EXACT_PYTHON_REQUIREMENT.fullmatch(requirement)
        if match is not None:
            result.append(_component("pypi", match[1], match[2], source=source, resolved=False))
    return result


def _requirements_snapshot(content: str, *, source: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _EXACT_PYTHON_REQUIREMENT.fullmatch(line)
        if match is None:
            raise SupplyChainFailure("PYTHON_REQUIREMENTS_LOCK_INVALID")
        result.append(_component("pypi", match[1], match[2], source=source, resolved=False))
    return result


def _maven_declarations(content: str, *, source: str) -> list[dict[str, Any]]:
    if "<!DOCTYPE" in content.upper() or "<!ENTITY" in content.upper():
        raise SupplyChainFailure("MAVEN_PROJECT_MANIFEST_UNSAFE_XML")
    try:
        root = ElementTree.fromstring(content)  # noqa: S314 -- declarations rejected above
    except ElementTree.ParseError as error:
        raise SupplyChainFailure("MAVEN_PROJECT_MANIFEST_INVALID") from error
    namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
    result: list[dict[str, Any]] = []
    for dependency in root.findall("./m:dependencies/m:dependency", namespace):
        group = dependency.findtext("m:groupId", default="", namespaces=namespace).strip()
        artifact = dependency.findtext("m:artifactId", default="", namespaces=namespace).strip()
        version = dependency.findtext("m:version", default="UNRESOLVED", namespaces=namespace).strip()
        if group and artifact:
            result.append(_component("maven", f"{group}/{artifact}", version, source=source, resolved=False))
    return result


def _maven_tree(content: str, *, source: str) -> list[dict[str, Any]]:
    try:
        document = json.loads(content)
    except json.JSONDecodeError as error:
        raise SupplyChainFailure("MAVEN_DEPENDENCY_TREE_INVALID") from error
    if not isinstance(document, dict):
        raise SupplyChainFailure("MAVEN_DEPENDENCY_TREE_INVALID")
    result: list[dict[str, Any]] = []

    def visit(node: object, *, root: bool = False) -> None:
        if not isinstance(node, dict):
            raise SupplyChainFailure("MAVEN_DEPENDENCY_TREE_INVALID")
        group = node.get("groupId")
        artifact = node.get("artifactId")
        version = node.get("version")
        if not root:
            if not all(isinstance(value, str) and value for value in (group, artifact, version)):
                raise SupplyChainFailure("MAVEN_DEPENDENCY_TREE_INVALID")
            result.append(
                _component("maven", f"{group}/{artifact}", str(version), source=source, resolved=True)
            )
        children = node.get("children", [])
        if not isinstance(children, list):
            raise SupplyChainFailure("MAVEN_DEPENDENCY_TREE_INVALID")
        for child in children:
            visit(child)

    visit(document, root=True)
    return result


def _dotnet_declarations(content: str, *, source: str) -> list[dict[str, Any]]:
    if "<!DOCTYPE" in content.upper() or "<!ENTITY" in content.upper():
        raise SupplyChainFailure("DOTNET_PACKAGE_MANIFEST_UNSAFE_XML")
    try:
        root = ElementTree.fromstring(content)  # noqa: S314 -- declarations rejected above
    except ElementTree.ParseError as error:
        raise SupplyChainFailure("DOTNET_PACKAGE_MANIFEST_INVALID") from error
    return [
        _component(
            "nuget",
            str(item.attrib["Include"]),
            str(item.attrib["Version"]),
            source=source,
            resolved=False,
        )
        for item in root.findall(".//PackageVersion")
        if item.attrib.get("Include") and item.attrib.get("Version")
    ]


def _dotnet_locks(files: Mapping[str, str]) -> tuple[list[dict[str, Any]], bool]:
    result: list[dict[str, Any]] = []
    integrity_complete = True
    for path, content in sorted(files.items()):
        if not path.startswith("dotnet/") or not path.endswith("packages.lock.json"):
            continue
        try:
            document = json.loads(content)
        except json.JSONDecodeError as error:
            raise SupplyChainFailure("DOTNET_PACKAGES_LOCK_INVALID") from error
        frameworks = document.get("dependencies") if isinstance(document, dict) else None
        if not isinstance(frameworks, dict) or not frameworks:
            raise SupplyChainFailure("DOTNET_PACKAGES_LOCK_INVALID")
        for packages in frameworks.values():
            if not isinstance(packages, dict):
                raise SupplyChainFailure("DOTNET_PACKAGES_LOCK_INVALID")
            for name, details in packages.items():
                if (
                    isinstance(name, str)
                    and isinstance(details, dict)
                    and details.get("type") == "Project"
                    and "resolved" not in details
                    and "contentHash" not in details
                ):
                    continue
                if (
                    not isinstance(name, str)
                    or not isinstance(details, dict)
                    or not isinstance(details.get("resolved"), str)
                ):
                    raise SupplyChainFailure("DOTNET_PACKAGES_LOCK_INVALID")
                content_hash = details.get("contentHash")
                if not isinstance(content_hash, str) or not _valid_base64_digest(content_hash, 64):
                    integrity_complete = False
                    hashes: tuple[str, ...] = ()
                else:
                    hashes = (f"sha512:{content_hash}",)
                result.append(
                    _component(
                        "nuget",
                        name,
                        details["resolved"],
                        source=path,
                        resolved=True,
                        hashes=hashes,
                    )
                )
    return result, bool(result) and integrity_complete


def _npm_declarations(content: str, *, source: str) -> list[dict[str, Any]]:
    try:
        document = json.loads(content)
    except json.JSONDecodeError as error:
        raise SupplyChainFailure("NPM_PACKAGE_MANIFEST_INVALID") from error
    result: list[dict[str, Any]] = []
    for field in ("dependencies", "devDependencies"):
        dependencies = document.get(field) if isinstance(document, dict) else None
        if not isinstance(dependencies, dict):
            continue
        for name, version in dependencies.items():
            if isinstance(name, str) and isinstance(version, str):
                result.append(_component("npm", name, version, source=source, resolved=False))
    return result


def _pnpm_lock(content: str, *, source: str) -> tuple[list[dict[str, Any]], bool]:
    result: list[dict[str, Any]] = []
    integrity: list[bool] = []
    section: str | None = None
    current_index: int | None = None
    for line in content.splitlines():
        if line and not line.startswith(" "):
            section = line.removesuffix(":")
            continue
        if section != "packages":
            continue
        match = _PNPM_PACKAGE.fullmatch(line)
        if match is None:
            if current_index is not None:
                integrity_match = _PNPM_INTEGRITY.search(line)
                if integrity_match is not None:
                    encoded = integrity_match[1]
                    integrity[current_index] = _valid_base64_digest(encoded, 64)
                    if integrity[current_index]:
                        result[current_index]["hashes"] = [
                            {
                                "alg": "SHA-512",
                                "content": base64.b64decode(encoded, validate=True).hex(),
                            }
                        ]
            continue
        coordinate = match[2].lstrip("/").split("(", 1)[0]
        if "@" not in coordinate:
            continue
        name, version = coordinate.rsplit("@", 1)
        if name and version:
            result.append(_component("npm", name, version, source=source, resolved=True))
            integrity.append(False)
            current_index = len(integrity) - 1
    if not result:
        raise SupplyChainFailure("PNPM_LOCK_INVALID_OR_EMPTY")
    return result, all(integrity)


def _go_modules(content: str, *, source: str, resolved: bool) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    in_require = False
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line == "require (":
            in_require = True
            continue
        if in_require and line == ")":
            in_require = False
            continue
        candidate = line.removeprefix("require ") if line.startswith("require ") else line if in_require else ""
        match = _GO_REQUIREMENT.fullmatch(candidate)
        if match is not None:
            result.append(_component("golang", match[1], match[2], source=source, resolved=resolved))
    return result


def _gradle_lock(content: str, *, source: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for line in content.splitlines():
        match = _GRADLE_COORDINATE.match(line.strip())
        if match is not None:
            result.append(
                _component(
                    "maven",
                    f"{match[1]}/{match[2]}",
                    match[3],
                    source=source,
                    resolved=True,
                )
            )
    if not result:
        raise SupplyChainFailure("GRADLE_LOCK_INVALID_OR_EMPTY")
    return result


def _composer_inventory(content: str, *, source: str) -> list[dict[str, Any]]:
    try:
        document = json.loads(content)
    except json.JSONDecodeError as error:
        raise SupplyChainFailure("COMPOSER_LOCK_INVALID") from error
    result: list[dict[str, Any]] = []
    for field in ("packages", "packages-dev"):
        packages = document.get(field) if isinstance(document, dict) else None
        if not isinstance(packages, list):
            raise SupplyChainFailure("COMPOSER_LOCK_INVALID")
        for package in packages:
            if (
                not isinstance(package, dict)
                or not isinstance(package.get("name"), str)
                or not isinstance(package.get("version"), str)
            ):
                raise SupplyChainFailure("COMPOSER_LOCK_INVALID")
            result.append(_component("composer", package["name"], package["version"], source=source, resolved=True))
    return result


def _composer_platform_only(content: str) -> bool:
    try:
        document = json.loads(content)
    except json.JSONDecodeError as error:
        raise SupplyChainFailure("COMPOSER_PROJECT_MANIFEST_INVALID") from error
    requirements = document.get("require") if isinstance(document, dict) else None
    return isinstance(requirements, dict) and all(name == "php" or name.startswith("ext-") for name in requirements)


def _cargo_lock(content: str, *, source: str, project_name: str) -> list[dict[str, Any]]:
    try:
        document = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise SupplyChainFailure("CARGO_LOCK_INVALID") from error
    packages = document.get("package")
    if document.get("version") != 4 or not isinstance(packages, list):
        raise SupplyChainFailure("CARGO_LOCK_INVALID")
    result: list[dict[str, Any]] = []
    for package in packages:
        if (
            not isinstance(package, dict)
            or not isinstance(package.get("name"), str)
            or not isinstance(package.get("version"), str)
        ):
            raise SupplyChainFailure("CARGO_LOCK_PACKAGE_INVALID")
        if package["name"] == project_name and "source" not in package:
            continue
        hashes = (package["checksum"],) if isinstance(package.get("checksum"), str) else ()
        result.append(
            _component(
                "cargo",
                package["name"],
                package["version"],
                source=source,
                resolved=True,
                hashes=hashes,
            )
        )
    return result


def _target_inventory(
    language: str,
    directory: str,
    files: Mapping[str, str],
    *,
    project_name: str,
) -> tuple[list[dict[str, Any]], str, list[str], str, list[str]]:
    missing: list[str] = []
    integrity_issues: list[str] = []
    components: list[dict[str, Any]]
    if language == "java":
        if MAVEN_TREE_PATH in files:
            components = _maven_tree(files[MAVEN_TREE_PATH], source=MAVEN_TREE_PATH)
            integrity_issues.append("MAVEN_ARTIFACT_HASH_EVIDENCE_MISSING")
            return components, "COMPLETE", [], "INCOMPLETE", integrity_issues
        path = f"{directory}/pom.xml"
        components = _maven_declarations(files[path], source=path)
        missing.append(MAVEN_TREE_PATH)
    elif language == "python":
        lock = f"{directory}/uv.lock"
        if lock in files:
            components = _uv_packages(files[lock], source=lock, project_name=project_name)
            if not components or all(_has_strong_integrity(item) for item in components):
                return components, "COMPLETE", [], "COMPLETE", []
            return components, "COMPLETE", [], "INCOMPLETE", ["PYTHON_LOCK_ARTIFACT_HASH_MISSING"]
        manifest = f"{directory}/pyproject.toml"
        components = _python_declarations(files[manifest], source=manifest)
        snapshot = f"{directory}/requirements.lock"
        if snapshot in files:
            components.extend(_requirements_snapshot(files[snapshot], source=snapshot))
        missing.append(lock)
    elif language == "csharp":
        locked, integrity_complete = _dotnet_locks(files)
        if locked:
            return (
                locked,
                "COMPLETE",
                [],
                "COMPLETE" if integrity_complete else "INCOMPLETE",
                [] if integrity_complete else ["NUGET_CONTENT_HASH_MISSING_OR_INVALID"],
            )
        path = f"{directory}/Directory.Packages.props"
        components = _dotnet_declarations(files[path], source=path)
        missing.append(f"{directory}/**/packages.lock.json")
    elif language == "typescript":
        lock = f"{directory}/pnpm-lock.yaml"
        if lock in files:
            locked, integrity_complete = _pnpm_lock(files[lock], source=lock)
            return (
                locked,
                "COMPLETE",
                [],
                "COMPLETE" if integrity_complete else "INCOMPLETE",
                [] if integrity_complete else ["PNPM_PACKAGE_INTEGRITY_MISSING_OR_INVALID"],
            )
        path = f"{directory}/package.json"
        components = _npm_declarations(files[path], source=path)
        missing.append(lock)
    elif language == "go":
        path = f"{directory}/go.mod"
        sum_path = f"{directory}/go.sum"
        complete = sum_path in files
        components = _go_modules(files[path], source=path, resolved=complete)
        if complete or not components:
            if not components:
                return components, "COMPLETE", [], "NOT_APPLICABLE", []
            sum_entries = {
                (parts[0], parts[1]): parts[2]
                for line in files[sum_path].splitlines()
                if len(parts := line.split()) == 3
                and not parts[1].endswith("/go.mod")
                and parts[2].startswith("h1:")
                and _valid_base64_digest(parts[2].removeprefix("h1:"), 32)
            }
            expected = {(item["name"], item["version"]) for item in components}
            integrity_complete = expected <= set(sum_entries)
            for item in components:
                coordinate = (item["name"], item["version"])
                if coordinate in sum_entries:
                    digest = sum_entries[coordinate].removeprefix("h1:")
                    item["hashes"] = [
                        {
                            "alg": "SHA-256",
                            "content": base64.b64decode(digest, validate=True).hex(),
                        }
                    ]
            return (
                components,
                "COMPLETE",
                [],
                "COMPLETE" if integrity_complete else "INCOMPLETE",
                [] if integrity_complete else ["GO_MODULE_SUM_MISSING_OR_INVALID"],
            )
        missing.append(sum_path)
    elif language == "kotlin":
        path = f"{directory}/gradle.lockfile"
        if path in files:
            return (
                _gradle_lock(files[path], source=path),
                "COMPLETE",
                [],
                "INCOMPLETE",
                ["GRADLE_ARTIFACT_HASH_EVIDENCE_MISSING"],
            )
        components = []
        missing.append(path)
    elif language == "php":
        lock = f"{directory}/composer.lock"
        manifest = f"{directory}/composer.json"
        if lock in files:
            components = _composer_inventory(files[lock], source=lock)
            return components, "COMPLETE", [], "INCOMPLETE", ["COMPOSER_ARTIFACT_HASH_EVIDENCE_MISSING"]
        if _composer_platform_only(files[manifest]):
            return [], "COMPLETE", [], "NOT_APPLICABLE", []
        components = []
        missing.append(lock)
    elif language == "rust":
        path = f"{directory}/Cargo.lock"
        if path in files:
            components = _cargo_lock(files[path], source=path, project_name=project_name)
            integrity_complete = all(_has_strong_integrity(item) for item in components)
            return (
                components,
                "COMPLETE",
                [],
                "COMPLETE" if integrity_complete else "INCOMPLETE",
                [] if integrity_complete else ["CARGO_PACKAGE_CHECKSUM_MISSING_OR_INVALID"],
            )
        components = []
        missing.append(path)
    else:
        raise SupplyChainFailure(f"SBOM_LANGUAGE_UNSUPPORTED:{language}")
    return components, "INCOMPLETE", missing, "INCOMPLETE", integrity_issues


def build_dependency_sbom(
    request: SynthesisRequest,
    files: Mapping[str, str],
) -> dict[str, Any]:
    artifact_hashes = _artifact_hash_evidence(files, request_sha256=request.request_hash)
    used_artifact_hashes: set[str] = set()
    components: dict[str, dict[str, Any]] = {}
    target_components: list[str] = []
    dependencies: list[dict[str, Any]] = []
    resolution: dict[str, dict[str, Any]] = {}
    for target in request.targets:
        directory = str(target.language if target.language != "csharp" else "dotnet")
        target_ref = f"application:{target.language}:{request.project_name}"
        target_components.append(target_ref)
        components[target_ref] = {
            "type": "application",
            "bom-ref": target_ref,
            "name": request.project_name,
            "version": "1.0.0",
            "properties": [
                {"name": "elmos:language", "value": target.language},
                {"name": "elmos:framework", "value": target.framework},
                {"name": "elmos:runtime", "value": target.runtime},
            ],
        }
        inventory, inventory_status, missing, integrity_status, integrity_issues = _target_inventory(
            target.language,
            directory,
            files,
            project_name=request.project_name,
        )
        for item in inventory:
            reference = str(item["bom-ref"])
            record = artifact_hashes.get(reference)
            if record is None:
                continue
            used_artifact_hashes.add(reference)
            hashes = {
                (str(hash_value["alg"]), str(hash_value["content"]))
                for hash_value in item.get("hashes", [])
                if isinstance(hash_value, dict)
                and isinstance(hash_value.get("alg"), str)
                and isinstance(hash_value.get("content"), str)
            }
            hashes.add(("SHA-256", str(record["sha256"])))
            item["hashes"] = [
                {"alg": algorithm, "content": digest} for algorithm, digest in sorted(hashes)
            ]
        if inventory_status == "COMPLETE" and (not inventory or all(_has_strong_integrity(item) for item in inventory)):
            integrity_status = "COMPLETE" if inventory else "NOT_APPLICABLE"
            integrity_issues = []
        refs = sorted({_add_component(components, item) for item in inventory})
        dependencies.append({"ref": target_ref, "dependsOn": refs})
        resolution[target.language] = {
            "inventory_status": inventory_status,
            "integrity_status": integrity_status,
            "dependency_graph_status": "INCOMPLETE_FLATTENED",
            "component_count": len(refs),
            "missing_evidence": missing,
            "integrity_issues": integrity_issues,
        }
    if used_artifact_hashes != set(artifact_hashes):
        raise SupplyChainFailure("ARTIFACT_HASH_EVIDENCE_COMPONENT_MISMATCH")
    inventory_complete = bool(resolution) and all(
        value["inventory_status"] == "COMPLETE" for value in resolution.values()
    )
    integrity_complete = bool(resolution) and all(
        value["integrity_status"] in {"COMPLETE", "NOT_APPLICABLE"} for value in resolution.values()
    )
    root_ref = f"project:{request.project_name}"
    components[root_ref] = {
        "type": "application",
        "bom-ref": root_ref,
        "name": request.project_name,
        "version": "1.0.0",
    }
    dependencies.append({"ref": root_ref, "dependsOn": sorted(target_components)})
    component_list = [components[key] for key in sorted(components)]
    dependencies.sort(key=lambda item: str(item["ref"]))
    serial_seed = {
        "request_sha256": request.request_hash,
        "components": [item["bom-ref"] for item in component_list],
        "resolution": resolution,
    }
    properties = [
        {"name": "elmos:request-sha256", "value": request.request_hash},
        {"name": "elmos:approved-payload-sha256", "value": str(request.raw["approval"]["approved_payload_sha256"])},
        {"name": "elmos:p0-scope-id", "value": str(p0_scope_payload()["scope_id"])},
        {"name": "elmos:p0-scope-sha256", "value": _scope_sha256()},
        {
            "name": "elmos:transitive-inventory-status",
            "value": "COMPLETE" if inventory_complete else "INCOMPLETE",
        },
        {
            "name": "elmos:artifact-integrity-status",
            "value": "COMPLETE" if integrity_complete else "INCOMPLETE",
        },
        {"name": "elmos:dependency-graph-status", "value": "INCOMPLETE_FLATTENED"},
        {"name": "elmos:external-evidence-status", "value": "NOT_RUN"},
        {"name": "elmos:certification-status", "value": "NOT_CERTIFIED"},
    ]
    for language, detail in resolution.items():
        properties.extend(
            [
                {
                    "name": f"elmos:target:{language}:inventory-status",
                    "value": str(detail["inventory_status"]),
                },
                {
                    "name": f"elmos:target:{language}:integrity-status",
                    "value": str(detail["integrity_status"]),
                },
                {
                    "name": f"elmos:target:{language}:missing-evidence",
                    "value": json.dumps(detail["missing_evidence"], separators=(",", ":")),
                },
                {
                    "name": f"elmos:target:{language}:integrity-issues",
                    "value": json.dumps(detail["integrity_issues"], separators=(",", ":")),
                },
            ]
        )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, sha256_bytes(canonical_json(serial_seed)))}",
        "version": 1,
        "metadata": {
            "component": components[root_ref],
            "properties": properties,
        },
        "components": [item for item in component_list if item["bom-ref"] != root_ref],
        "dependencies": dependencies,
        "compositions": [
            {
                "aggregate": "incomplete",
                "assemblies": sorted(target_components),
            }
        ],
    }


def sbom_status(sbom: Mapping[str, Any], name: str) -> str:
    """Return one unambiguous ELMOS SBOM property or ``UNKNOWN``."""

    metadata = sbom.get("metadata")
    properties = metadata.get("properties") if isinstance(metadata, dict) else None
    if not isinstance(properties, list):
        return "UNKNOWN"
    values = {
        item["name"]: item["value"]
        for item in properties
        if isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("value"), str)
    }
    return str(values.get(name, "UNKNOWN"))


def sbom_is_complete(sbom: Mapping[str, Any]) -> bool:
    """Whether inventory and native artifact integrity can feed release.

    The dependency relationship set remains explicitly flattened and is not
    represented as a complete dependency graph.
    """

    return (
        sbom_status(sbom, "elmos:transitive-inventory-status") == "COMPLETE"
        and sbom_status(sbom, "elmos:artifact-integrity-status") == "COMPLETE"
        and sbom_status(sbom, "elmos:dependency-graph-status") == "INCOMPLETE_FLATTENED"
    )


def _safe_derived_file(root: Path, path: Path) -> tuple[str, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise SupplyChainFailure(f"DERIVED_DEPENDENCY_EVIDENCE_UNSAFE:{path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or resolved != path:
        raise SupplyChainFailure(f"DERIVED_DEPENDENCY_EVIDENCE_UNSAFE:{path}")
    return path.relative_to(root).as_posix(), path.read_text(encoding="utf-8")


def build_workspace_sbom(workspace: Path) -> dict[str, Any]:
    root = workspace.expanduser().resolve(strict=True)
    validate_workspace_graphs(root)
    manifest = json.loads((root / ".elmos" / "generation-manifest.json").read_text(encoding="utf-8"))
    files: dict[str, str] = {}
    for entry in manifest["files"]:
        path = root.joinpath(*PurePosixPath(entry["path"]).parts)
        files[entry["path"]] = path.read_text(encoding="utf-8")
    derived = [
        root / MAVEN_TREE_PATH,
        root / ARTIFACT_HASH_EVIDENCE_PATH,
        root / "python" / "uv.lock",
        root / "typescript" / "pnpm-lock.yaml",
        root / "kotlin" / "gradle.lockfile",
        root / "rust" / "Cargo.lock",
        *sorted((root / "dotnet").glob("**/packages.lock.json")),
    ]
    for candidate in derived:
        if candidate.exists() or candidate.is_symlink():
            relative_path, content = _safe_derived_file(root, candidate)
            files[relative_path] = content
    approved = json.loads(files["requirements/approved-request.json"])
    request = SynthesisRequest.from_mapping(approved, require_approval=True)
    return build_dependency_sbom(request, files)


def _artifact_cache_candidate(
    reference: str,
    *,
    maven_repository: Path,
    gradle_cache: Path,
) -> tuple[Path, Path, str]:
    coordinate = reference.removeprefix("pkg:maven/")
    if "@" not in coordinate or "/" not in coordinate:
        raise SupplyChainFailure(f"NATIVE_ARTIFACT_COORDINATE_INVALID:{reference}")
    name, version = coordinate.rsplit("@", 1)
    group, artifact = name.rsplit("/", 1)
    safe_piece = re.compile(r"^[A-Za-z0-9_.+-]+$")
    if not all(safe_piece.fullmatch(value) for value in (group, artifact, version)):
        raise SupplyChainFailure(f"NATIVE_ARTIFACT_COORDINATE_INVALID:{reference}")
    filenames_by_kind = (
        (f"{artifact}-{version}.jar",),
        (f"{artifact}-{version}.pom",),
    )
    maven_directory = maven_repository.joinpath(*group.split("."), artifact, version)
    gradle_directory = gradle_cache.joinpath(group, artifact, version)
    safe_candidates: list[tuple[Path, Path, str]] = []
    for filenames in filenames_by_kind:
        candidates: list[tuple[Path, Path, str]] = []
        candidates.extend(
            (candidate, maven_repository, "maven-local-repository")
            for filename in filenames
            if (candidate := maven_directory / filename).is_file()
        )
        for filename in filenames:
            candidates.extend(
                (candidate, gradle_cache, "gradle-module-cache")
                for candidate in sorted(gradle_directory.glob(f"*/{filename}"))
                if candidate.is_file()
            )
        for candidate, cache_root, cache_kind in candidates:
            if (
                candidate.is_symlink()
                or candidate.stat().st_size <= 0
                or candidate.stat().st_size > 512 * 1024 * 1024
            ):
                continue
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(cache_root) or resolved != candidate:
                continue
            safe_candidates.append((candidate, cache_root, cache_kind))
        if safe_candidates:
            break
    if not safe_candidates:
        raise SupplyChainFailure(f"NATIVE_ARTIFACT_NOT_FOUND:{reference}")
    digests = {sha256_bytes(candidate.read_bytes()) for candidate, _, _ in safe_candidates}
    if len(digests) != 1:
        raise SupplyChainFailure(f"NATIVE_ARTIFACT_CACHE_COLLISION:{reference}")
    return sorted(safe_candidates, key=lambda item: (item[2], str(item[0])))[0]


def collect_native_artifact_hash_evidence(
    workspace: Path,
    *,
    maven_repository: Path | None = None,
    gradle_cache: Path | None = None,
) -> dict[str, Any]:
    """Hash actual Maven/Gradle cache artifacts for a generated workspace.

    The caller writes the returned document to ``ARTIFACT_HASH_EVIDENCE_PATH``.
    No dependency is downloaded and no cache is mutated.
    """

    root = workspace.expanduser().resolve(strict=True)
    validate_workspace_graphs(root)
    generation = json.loads((root / ".elmos" / "generation-manifest.json").read_text(encoding="utf-8"))
    files: dict[str, str] = {}
    for entry in generation["files"]:
        path = root.joinpath(*PurePosixPath(entry["path"]).parts)
        files[entry["path"]] = path.read_text(encoding="utf-8")
    for candidate in (
        root / MAVEN_TREE_PATH,
        root / "python" / "uv.lock",
        root / "typescript" / "pnpm-lock.yaml",
        root / "kotlin" / "gradle.lockfile",
        root / "rust" / "Cargo.lock",
        *sorted((root / "dotnet").glob("**/packages.lock.json")),
    ):
        if candidate.exists() or candidate.is_symlink():
            relative_path, content = _safe_derived_file(root, candidate)
            files[relative_path] = content
    approved = json.loads(files["requirements/approved-request.json"])
    request = SynthesisRequest.from_mapping(approved, require_approval=True)
    sbom = build_dependency_sbom(request, files)
    required = sorted(
        str(component["bom-ref"])
        for component in sbom["components"]
        if isinstance(component, dict)
        and str(component.get("bom-ref", "")).startswith("pkg:maven/")
        and not _has_strong_integrity(component)
    )
    configured_maven = os.environ.get("MAVEN_REPO_LOCAL")
    maven_root = (
        maven_repository
        if maven_repository is not None
        else Path(configured_maven) if configured_maven else Path.home() / ".m2" / "repository"
    ).expanduser().resolve(strict=False)
    gradle_home = (
        Path(os.environ["ELMOS_PROJECT_SYNTHESIS_GRADLE_USER_HOME"])
        if os.environ.get("ELMOS_PROJECT_SYNTHESIS_GRADLE_USER_HOME")
        else Path.home() / ".cache" / "elmos" / "project-synthesis" / "gradle-user-home"
    )
    gradle_root = (gradle_cache or gradle_home / "caches" / "modules-2" / "files-2.1").expanduser().resolve(
        strict=False
    )
    for cache_root in (maven_root, gradle_root):
        if cache_root.exists() and (cache_root.is_symlink() or not cache_root.is_dir()):
            raise SupplyChainFailure("NATIVE_ARTIFACT_CACHE_ROOT_UNSAFE")
    artifacts: list[dict[str, Any]] = []
    for reference in required:
        candidate, cache_root, cache_kind = _artifact_cache_candidate(
            reference,
            maven_repository=maven_root,
            gradle_cache=gradle_root,
        )
        artifacts.append(
            {
                "bom_ref": reference,
                "sha256": sha256_bytes(candidate.read_bytes()),
                "byte_count": candidate.stat().st_size,
                "cache_kind": cache_kind,
                "cache_relative_path": candidate.relative_to(cache_root).as_posix(),
            }
        )
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.project-synthesis.native-artifact-hashes",
        "request_sha256": request.request_hash,
        "collector": "repository-owned-local-cache-sha256-v1",
        "artifacts": artifacts,
        "evidence_boundary": "LOCAL_ENGINEERING_SELF_ATTESTED",
    }


def build_python_lock_sbom(project_directory: Path) -> dict[str, Any]:
    """Build a CycloneDX transitive inventory from one exact uv lock."""

    root = project_directory.expanduser().resolve(strict=True)
    project_path = root / "pyproject.toml"
    lock_path = root / "uv.lock"
    for path, reason in (
        (project_path, "PYTHON_PROJECT_MANIFEST_UNSAFE"),
        (lock_path, "PYTHON_UV_LOCK_UNSAFE"),
    ):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            raise SupplyChainFailure(reason)
    try:
        project_document = tomllib.loads(project_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise SupplyChainFailure("PYTHON_PROJECT_MANIFEST_INVALID") from error
    project = project_document.get("project")
    if (
        not isinstance(project, dict)
        or not isinstance(project.get("name"), str)
        or not isinstance(project.get("version"), str)
    ):
        raise SupplyChainFailure("PYTHON_PROJECT_IDENTITY_INVALID")
    items = _uv_packages(
        lock_path.read_text(encoding="utf-8"),
        source="uv.lock",
        project_name=project["name"],
    )
    components = {str(item["bom-ref"]): item for item in items}
    if len(components) != len(items):
        raise SupplyChainFailure("PYTHON_UV_LOCK_COMPONENT_COLLISION")
    integrity_complete = all(_has_strong_integrity(item) for item in items)
    root_ref = f"application:python:{project['name']}@{project['version']}"
    component_refs = sorted(components)
    serial_seed = {
        "project": root_ref,
        "pyproject_sha256": sha256_bytes(project_path.read_bytes()),
        "uv_lock_sha256": sha256_bytes(lock_path.read_bytes()),
        "components": component_refs,
    }
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, sha256_bytes(canonical_json(serial_seed)))}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "name": project["name"],
                "version": project["version"],
            },
            "properties": [
                {"name": "elmos:p0-scope-id", "value": str(p0_scope_payload()["scope_id"])},
                {"name": "elmos:p0-scope-sha256", "value": _scope_sha256()},
                {"name": "elmos:pyproject-sha256", "value": sha256_bytes(project_path.read_bytes())},
                {"name": "elmos:uv-lock-sha256", "value": sha256_bytes(lock_path.read_bytes())},
                {"name": "elmos:transitive-inventory-status", "value": "COMPLETE"},
                {
                    "name": "elmos:artifact-integrity-status",
                    "value": "COMPLETE" if integrity_complete else "INCOMPLETE",
                },
                {"name": "elmos:dependency-graph-status", "value": "INCOMPLETE_FLATTENED"},
                {"name": "elmos:external-evidence-status", "value": "NOT_RUN"},
                {"name": "elmos:certification-status", "value": "NOT_CERTIFIED"},
            ],
        },
        "components": [components[reference] for reference in component_refs],
        "dependencies": [{"ref": root_ref, "dependsOn": component_refs}],
        "compositions": [{"aggregate": "incomplete", "assemblies": [root_ref]}],
    }


def observe_git_revision(repository: Path) -> dict[str, Any]:
    """Observe an exact local Git revision without accepting caller assertions."""

    git = shutil.which("git")
    if git is None:
        raise SupplyChainFailure("GIT_REQUIRED_FOR_SOURCE_REVISION")
    requested = repository.expanduser().resolve(strict=True)
    if requested.is_symlink() or not requested.is_dir():
        raise SupplyChainFailure("SOURCE_REPOSITORY_UNSAFE")

    def run(*arguments: str) -> str:
        completed = subprocess.run(  # noqa: S603
            [git, "-C", str(requested), *arguments],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            raise SupplyChainFailure(f"SOURCE_GIT_OBSERVATION_FAILED:{arguments[0]}")
        return completed.stdout.strip()

    observed_root = Path(run("rev-parse", "--show-toplevel")).resolve(strict=True)
    if observed_root != requested:
        raise SupplyChainFailure("SOURCE_REPOSITORY_ROOT_MISMATCH")
    commit_sha = run("rev-parse", "HEAD")
    tree_sha = run("rev-parse", "HEAD^{tree}")
    if GIT_OBJECT_PATTERN.fullmatch(commit_sha) is None or GIT_OBJECT_PATTERN.fullmatch(tree_sha) is None:
        raise SupplyChainFailure("SOURCE_GIT_OBJECT_INVALID")
    status = run("status", "--porcelain=v1", "--untracked-files=all")
    origin = run("remote", "get-url", "origin")
    if origin not in ALLOWED_SOURCE_ORIGINS:
        raise SupplyChainFailure("SOURCE_REPOSITORY_ORIGIN_NOT_ALLOWED")
    for relative in REQUIRED_SOURCE_PATHS:
        run("cat-file", "-e", f"HEAD:{relative}")
    engine = requested / "engines" / "project-synthesis-engine" / "pyproject.toml"
    try:
        engine_project = tomllib.loads(engine.read_text(encoding="utf-8")).get("project")
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise SupplyChainFailure("SOURCE_REPOSITORY_ENGINE_IDENTITY_INVALID") from error
    if not isinstance(engine_project, dict) or engine_project.get("name") != "elmos-project-synthesis":
        raise SupplyChainFailure("SOURCE_REPOSITORY_ENGINE_IDENTITY_INVALID")
    return {
        "commit_sha": commit_sha,
        "tree_sha": tree_sha,
        "worktree_clean": not status,
        "origin_url": origin,
    }


def _provider_compatibility(
    request: SynthesisRequest,
    source_repository: Path | None,
) -> tuple[dict[str, Any], list[str]]:
    if request.auth_mode != "oidc":
        return (
            {
                "profile": "jwt-hs256",
                "status": "NOT_APPLICABLE_INDEPENDENT_JWT_PROFILE",
                "observation_path": None,
                "observation_sha256": None,
            },
            [],
        )
    if source_repository is None:
        return (
            {
                "profile": "oidc-rs256",
                "status": "NOT_RUN",
                "observation_path": None,
                "observation_sha256": None,
            },
            ["MANAGED_OIDC_COMPATIBILITY_EVIDENCE_NOT_PROVIDED"],
        )
    observation_path = source_repository / PROVIDER_OBSERVATION_PATH
    relative_path, content = _safe_derived_file(source_repository, observation_path)
    try:
        observation = json.loads(content)
    except json.JSONDecodeError as error:
        raise SupplyChainFailure("MANAGED_PROVIDER_OBSERVATION_INVALID") from error
    expected_keys = {"schema_version", "kind", "scope_id", "observation", "assessment", "boundaries"}
    observed = observation.get("observation") if isinstance(observation, dict) else None
    assessment = observation.get("assessment") if isinstance(observation, dict) else None
    boundaries = observation.get("boundaries") if isinstance(observation, dict) else None
    if (
        not isinstance(observation, dict)
        or set(observation) != expected_keys
        or observation.get("schema_version") != "1.0.0"
        or observation.get("kind") != "elmos.project-synthesis.operator-reported-provider-observation"
        or observation.get("scope_id") != p0_scope_payload()["scope_id"]
        or not isinstance(observed, dict)
        or observed.get("provider") != "neon"
        or observed.get("auth_provider") != "better_auth"
        or observed.get("jwks_key_count") != 1
        or observed.get("jwk_kty") != "OKP"
        or observed.get("jwk_algorithm") != "EdDSA"
        or not isinstance(assessment, dict)
        or assessment.get("required_jwk_kty") != "RSA"
        or assessment.get("required_jwk_algorithm") != "RS256"
        or assessment.get("compatibility") != "ALGORITHM_MISMATCH"
        or assessment.get("launch_gate") != "BLOCKED"
        or not isinstance(boundaries, dict)
        or boundaries.get("evidence_class") != "OPERATOR_REPORTED_READ_ONLY"
        or boundaries.get("raw_provider_receipt_status") != "NOT_PROVIDED"
        or boundaries.get("database_migration_write_status") != "NOT_RUN"
        or boundaries.get("certification_status") != "NOT_CERTIFIED"
    ):
        raise SupplyChainFailure("MANAGED_PROVIDER_OBSERVATION_INVALID")
    return (
        {
            "profile": "oidc-rs256",
            "status": "ALGORITHM_MISMATCH",
            "observation_path": relative_path,
            "observation_sha256": sha256_bytes(observation_path.read_bytes()),
        },
        ["MANAGED_OIDC_ALGORITHM_MISMATCH:required=RS256:observed=EdDSA"],
    )


_EXPECTED_TOOLCHAIN_LABELS: dict[str, tuple[str, ...]] = {
    "java": ("OpenJDK 21.0.11", "Apache Maven 3.9.10"),
    "python": ("uv 0.11.16", "Python 3.12.12"),
    "csharp": (".NET SDK 10.0.301",),
    "typescript": ("Node 26.0.0", "pnpm 10.12.4"),
    "go": ("Go 1.25.0",),
    "kotlin": ("Kotlin Gradle Plugin 2.2.20", "OpenJDK 21.0.11", "Gradle 8.14.3"),
    "php": ("PHP 8.4.12",),
    "rust": ("rustc 1.89.0", "cargo 1.89.0"),
    "postgresql": ("PostgreSQL 17.5",),
}

_REQUIRED_BUILD_COMMANDS: dict[str, tuple[tuple[str, ...], ...]] = {
    "java": (("mvn", "-B", "package"),),
    "python": (
        ("uv", "lock"),
        ("uv", "sync", "--locked"),
        ("python", "--version"),
        ("pytest", "-m", "not integration"),
        ("ruff", "check", "src", "tests"),
        ("mypy", "src"),
    ),
    "csharp": (
        ("dotnet", "restore", "--use-lock-file"),
        ("dotnet", "restore", "--locked-mode"),
        ("dotnet", "test", "--no-restore"),
    ),
    "typescript": (
        ("pnpm", "install", "--lockfile-only"),
        ("pnpm", "install", "--frozen-lockfile"),
        ("pnpm", "check"),
        ("pnpm", "test"),
        ("pnpm", "build"),
    ),
    "go": (("go", "vet"), ("go", "test", "-race"), ("go", "build")),
    "kotlin": (("gradle", "test", "build"),),
    "php": (("php", "-l"), ("php", "tests/run.php")),
    "rust": (
        ("cargo", "fmt", "--check"),
        ("cargo", "clippy", "--locked"),
        ("cargo", "test", "--locked"),
        ("cargo", "build", "--locked", "--release"),
    ),
}


def _command_matches(command: object, required: tuple[str, ...]) -> bool:
    if not isinstance(command, list) or not command or any(not isinstance(item, str) for item in command):
        return False
    if Path(command[0]).name != required[0]:
        return False
    return all(token in command[1:] for token in required[1:])


def _validate_verification_evidence(
    root: Path,
    request: SynthesisRequest,
    generation: Mapping[str, Any],
    generation_bytes: bytes,
    sbom: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> None:
    """Validate the complete self-attested ``verify_workspace`` contract.

    This enforces structural and digest binding and rejects empty result lists.
    It does not establish that the local producer is independent or trustworthy;
    the trusted release signature remains a separate required gate.
    """

    def reject(detail: str) -> Never:
        raise SupplyChainFailure(f"VERIFICATION_EVIDENCE_CONTRACT_INVALID:{detail}")

    if evidence.get("schema_version") != "1.2.0" or evidence.get("status") != "PASSED":
        reject("IDENTITY_OR_STATUS")
    if evidence.get("workspace") != str(root):
        reject("WORKSPACE_BINDING")
    if evidence.get("request_sha256") != request.request_hash:
        reject("REQUEST_BINDING")
    if evidence.get("approved_payload_sha256") != generation.get("approved_payload_sha256"):
        reject("APPROVAL_BINDING")
    if evidence.get("generation_manifest_sha256") != sha256_bytes(generation_bytes):
        reject("GENERATION_BINDING")
    expected_supply_chain = {
        "sbom_format": "CycloneDX",
        "sbom_spec_version": "1.6",
        "sbom_sha256": sha256_bytes(canonical_json(sbom)),
        "transitive_inventory_status": sbom_status(sbom, "elmos:transitive-inventory-status"),
        "artifact_integrity_status": sbom_status(sbom, "elmos:artifact-integrity-status"),
        "dependency_graph_status": sbom_status(sbom, "elmos:dependency-graph-status"),
        "release_signature_status": "NOT_RUN",
        "trusted_root_status": "NOT_RUN",
    }
    if evidence.get("supply_chain") != expected_supply_chain:
        reject("SBOM_BINDING")
    if (
        evidence.get("production_delivery_status") != "NOT_RUN"
        or evidence.get("external_certification_status") != "NOT_RUN"
    ):
        reject("EVIDENCE_BOUNDARY")
    raw_results = evidence.get("results")
    if not isinstance(raw_results, list) or not raw_results:
        reject("RESULTS_EMPTY")
    results: list[object] = raw_results
    normalized: list[dict[str, Any]] = []
    for result in results:
        if (
            not isinstance(result, dict)
            or not all(key in result for key in ("language", "kind", "command", "status", "exit_code", "output"))
            or not isinstance(result.get("language"), str)
            or result.get("kind") not in {"toolchain", "build-analysis", "startup-probe"}
            or not isinstance(result.get("command"), list)
            or not result["command"]
            or any(not isinstance(item, str) for item in result["command"])
            or result.get("status") != "PASSED"
            or result.get("exit_code") != 0
            or not isinstance(result.get("output"), str)
        ):
            reject("RESULT_SHAPE_OR_STATUS")
        normalized.append(result)

    selected = tuple(target.language for target in request.targets)
    environment = evidence.get("environment")
    exact_matches = environment.get("exact_toolchain_match") if isinstance(environment, dict) else None
    if not isinstance(exact_matches, dict) or exact_matches != {language: True for language in selected}:
        reject("EXACT_TOOLCHAIN_SUMMARY")
    for language in (*selected, "postgresql"):
        toolchain = [
            result for result in normalized if result["language"] == language and result["kind"] == "toolchain"
        ]
        observed_labels = {
            line.removeprefix("EXPECTED:")
            for result in toolchain
            for line in str(result["output"]).splitlines()
            if line.startswith("EXPECTED:")
        }
        if observed_labels != set(_EXPECTED_TOOLCHAIN_LABELS[language]):
            reject(f"EXACT_TOOLCHAIN_RESULTS:{language}")
        if any("OBSERVED:" not in str(result["output"]) for result in toolchain):
            reject(f"EXACT_TOOLCHAIN_OBSERVATION:{language}")
    allowed_languages = {*selected, "postgresql"}
    if any(result["language"] not in allowed_languages for result in normalized):
        reject("UNEXPECTED_RESULT_LANGUAGE")
    for language in selected:
        build_results = [
            result for result in normalized if result["language"] == language and result["kind"] == "build-analysis"
        ]
        for required in _REQUIRED_BUILD_COMMANDS[language]:
            if not any(_command_matches(result["command"], required) for result in build_results):
                reject(f"BUILD_RESULT_MISSING:{language}:{':'.join(required)}")
        startup = [
            result for result in normalized if result["language"] == language and result["kind"] == "startup-probe"
        ]
        if len(startup) != 1 or startup[0].get("integration_status") != "PASSED":
            reject(f"STARTUP_OR_INTEGRATION_RESULT:{language}")

    statuses = {result["status"] for result in normalized}
    derived_status = "FAILED" if "FAILED" in statuses else "PARTIAL" if "NOT_RUN" in statuses else "PASSED"
    if derived_status != evidence["status"]:
        reject("STATUS_NOT_DERIVED")


def build_release_manifest(
    workspace: Path,
    *,
    sbom: Mapping[str, Any],
    verification: Path | None = None,
    source_repository: Path | None = None,
) -> dict[str, Any]:
    root = workspace.expanduser().resolve(strict=True)
    validate_workspace_graphs(root)
    generation_path = root / ".elmos" / "generation-manifest.json"
    generation_bytes = generation_path.read_bytes()
    generation = json.loads(generation_bytes)
    approved = json.loads((root / "requirements" / "approved-request.json").read_text(encoding="utf-8"))
    request = SynthesisRequest.from_mapping(approved, require_approval=True)
    blockers = p0_request_blockers(request)

    expected_sbom = build_workspace_sbom(root)
    if dict(sbom) != expected_sbom:
        raise SupplyChainFailure("RELEASE_SBOM_WORKSPACE_BINDING_MISMATCH")
    if not sbom_is_complete(sbom):
        blockers.append("TRANSITIVE_DEPENDENCY_SBOM_INCOMPLETE")
    sbom_bytes = json_artifact_bytes(sbom)
    verification_binding: dict[str, Any]
    if verification is None:
        verification_binding = {"status": "NOT_RUN", "path": None, "sha256": None}
        blockers.append("NATIVE_VERIFICATION_NOT_RUN")
    else:
        evidence_path = verification.expanduser().resolve(strict=True)
        if evidence_path.is_symlink() or not evidence_path.is_file() or evidence_path.stat().st_size > 32 * 1024 * 1024:
            raise SupplyChainFailure("VERIFICATION_EVIDENCE_UNSAFE")
        evidence_bytes = evidence_path.read_bytes()
        try:
            evidence = json.loads(evidence_bytes)
        except json.JSONDecodeError as error:
            raise SupplyChainFailure("VERIFICATION_EVIDENCE_INVALID") from error
        if not isinstance(evidence, dict):
            raise SupplyChainFailure("VERIFICATION_EVIDENCE_INVALID")
        _validate_verification_evidence(root, request, generation, generation_bytes, sbom, evidence)
        verification_binding = {
            "status": "PASSED",
            "path": str(evidence_path),
            "sha256": sha256_bytes(evidence_bytes),
            "contract": "verify_workspace-v1.2",
            "result_count": len(evidence["results"]),
            "target_count": len(request.targets),
            "evidence_class": "LOCAL_ENGINEERING_SELF_ATTESTED",
        }

    revision: dict[str, Any]
    source_root: Path | None = None
    if source_repository is None:
        revision = {
            "commit_sha": None,
            "tree_sha": None,
            "worktree_clean": None,
            "origin_url": None,
        }
        blockers.append("SOURCE_REVISION_NOT_BOUND")
    else:
        source_root = source_repository.expanduser().resolve(strict=True)
        revision = observe_git_revision(source_root)
        if revision["worktree_clean"] is not True:
            blockers.append("SOURCE_WORKTREE_NOT_CLEAN")
    provider_compatibility, provider_blockers = _provider_compatibility(request, source_root)
    blockers.extend(provider_blockers)
    if source_root is not None:
        final_revision = observe_git_revision(source_root)
        if final_revision != revision:
            raise SupplyChainFailure("SOURCE_REVISION_CHANGED_DURING_RELEASE_MANIFEST")

    blockers.append("RELEASE_SIGNATURE_NOT_VERIFIED")
    blockers = sorted(set(blockers))
    only_signature_missing = blockers == ["RELEASE_SIGNATURE_NOT_VERIFIED"]
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.project-synthesis.release-manifest",
        "scope": {
            "id": p0_scope_payload()["scope_id"],
            "sha256": _scope_sha256(),
        },
        "source_revision": revision,
        "generation_manifest": {
            "path": ".elmos/generation-manifest.json",
            "sha256": sha256_bytes(generation_bytes),
            "request_sha256": generation.get("request_sha256"),
            "approved_payload_sha256": generation.get("approved_payload_sha256"),
        },
        "transitive_dependency_sbom": {
            "format": "CycloneDX",
            "spec_version": sbom.get("specVersion"),
            "sha256": sha256_bytes(sbom_bytes),
            "transitive_inventory_status": sbom_status(sbom, "elmos:transitive-inventory-status"),
            "artifact_integrity_status": sbom_status(sbom, "elmos:artifact-integrity-status"),
            "dependency_graph_status": sbom_status(sbom, "elmos:dependency-graph-status"),
            "release_input_status": (
                "INVENTORY_AND_INTEGRITY_COMPLETE" if sbom_is_complete(sbom) else "INCOMPLETE"
            ),
        },
        "verification_evidence": verification_binding,
        "managed_provider_compatibility": provider_compatibility,
        "signature_requirement": {
            "algorithm": "ed25519",
            "trust_root": "REQUIRED",
            "verification_status": "NOT_RUN",
        },
        "decision": "AWAITING_TRUSTED_SIGNATURE" if only_signature_missing else "BLOCKED",
        "blockers": blockers,
        "ready_for_external_gate": False,
        "production_delivery_status": "NOT_RUN",
        "independent_verification_status": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "production_ready": False,
        "certified": False,
    }


def _parse_time(value: object, reason: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SupplyChainFailure(reason)
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise SupplyChainFailure(reason) from error
    if parsed.tzinfo is None:
        raise SupplyChainFailure(reason)
    return parsed.astimezone(UTC)


def _validate_unsigned_release_manifest(manifest: Mapping[str, Any]) -> None:
    expected_keys = {
        "schema_version",
        "kind",
        "scope",
        "source_revision",
        "generation_manifest",
        "transitive_dependency_sbom",
        "verification_evidence",
        "managed_provider_compatibility",
        "signature_requirement",
        "decision",
        "blockers",
        "ready_for_external_gate",
        "production_delivery_status",
        "independent_verification_status",
        "external_evidence_status",
        "certification_status",
        "production_ready",
        "certified",
    }
    if set(manifest) != expected_keys:
        raise SupplyChainFailure("RELEASE_MANIFEST_SHAPE_INVALID")
    if manifest.get("schema_version") != "1.0.0" or manifest.get("kind") != "elmos.project-synthesis.release-manifest":
        raise SupplyChainFailure("RELEASE_MANIFEST_IDENTITY_INVALID")
    scope = manifest.get("scope")
    expected_scope = p0_scope_payload()
    if scope != {"id": expected_scope["scope_id"], "sha256": _scope_sha256()}:
        raise SupplyChainFailure("RELEASE_MANIFEST_SCOPE_INVALID")
    revision = manifest.get("source_revision")
    if (
        not isinstance(revision, dict)
        or set(revision) != {"commit_sha", "tree_sha", "worktree_clean", "origin_url"}
        or not isinstance(revision.get("commit_sha"), str)
        or GIT_OBJECT_PATTERN.fullmatch(revision["commit_sha"]) is None
        or not isinstance(revision.get("tree_sha"), str)
        or GIT_OBJECT_PATTERN.fullmatch(revision["tree_sha"]) is None
        or revision.get("worktree_clean") is not True
        or revision.get("origin_url") not in ALLOWED_SOURCE_ORIGINS
    ):
        raise SupplyChainFailure("RELEASE_MANIFEST_SOURCE_REVISION_INVALID")
    generation = manifest.get("generation_manifest")
    if (
        not isinstance(generation, dict)
        or set(generation) != {"path", "sha256", "request_sha256", "approved_payload_sha256"}
        or generation.get("path") != ".elmos/generation-manifest.json"
        or any(
            not isinstance(generation.get(field), str)
            or SHA256_PATTERN.fullmatch(generation[field]) is None
            for field in ("sha256", "request_sha256", "approved_payload_sha256")
        )
    ):
        raise SupplyChainFailure("RELEASE_MANIFEST_GENERATION_BINDING_INVALID")
    sbom = manifest.get("transitive_dependency_sbom")
    if (
        not isinstance(sbom, dict)
        or set(sbom)
        != {
            "format",
            "spec_version",
            "sha256",
            "transitive_inventory_status",
            "artifact_integrity_status",
            "dependency_graph_status",
            "release_input_status",
        }
        or sbom.get("format") != "CycloneDX"
        or sbom.get("spec_version") != "1.6"
        or sbom.get("transitive_inventory_status") != "COMPLETE"
        or sbom.get("artifact_integrity_status") != "COMPLETE"
        or sbom.get("dependency_graph_status") != "INCOMPLETE_FLATTENED"
        or sbom.get("release_input_status") != "INVENTORY_AND_INTEGRITY_COMPLETE"
        or not isinstance(sbom.get("sha256"), str)
        or SHA256_PATTERN.fullmatch(sbom["sha256"]) is None
    ):
        raise SupplyChainFailure("RELEASE_MANIFEST_SBOM_BINDING_INVALID")
    verification = manifest.get("verification_evidence")
    if (
        not isinstance(verification, dict)
        or set(verification)
        != {
            "status",
            "path",
            "sha256",
            "contract",
            "result_count",
            "target_count",
            "evidence_class",
        }
        or verification.get("status") != "PASSED"
        or not isinstance(verification.get("path"), str)
        or not verification["path"]
        or not isinstance(verification.get("sha256"), str)
        or SHA256_PATTERN.fullmatch(verification["sha256"]) is None
        or verification.get("contract") != "verify_workspace-v1.2"
        or not isinstance(verification.get("result_count"), int)
        or verification["result_count"] <= 0
        or not isinstance(verification.get("target_count"), int)
        or verification["target_count"] <= 0
        or verification.get("evidence_class") != "LOCAL_ENGINEERING_SELF_ATTESTED"
    ):
        raise SupplyChainFailure("RELEASE_MANIFEST_VERIFICATION_BINDING_INVALID")
    if manifest.get("managed_provider_compatibility") != {
        "profile": "jwt-hs256",
        "status": "NOT_APPLICABLE_INDEPENDENT_JWT_PROFILE",
        "observation_path": None,
        "observation_sha256": None,
    }:
        raise SupplyChainFailure("RELEASE_MANIFEST_PROVIDER_COMPATIBILITY_INVALID")
    if manifest.get("signature_requirement") != {
        "algorithm": "ed25519",
        "trust_root": "REQUIRED",
        "verification_status": "NOT_RUN",
    }:
        raise SupplyChainFailure("RELEASE_MANIFEST_SIGNATURE_REQUIREMENT_INVALID")
    if (
        manifest.get("blockers") != ["RELEASE_SIGNATURE_NOT_VERIFIED"]
        or manifest.get("decision") != "AWAITING_TRUSTED_SIGNATURE"
    ):
        raise SupplyChainFailure("RELEASE_PREREQUISITES_NOT_SATISFIED")
    if (
        manifest.get("ready_for_external_gate") is not False
        or manifest.get("production_ready") is not False
        or manifest.get("certified") is not False
        or manifest.get("production_delivery_status") != "NOT_RUN"
        or manifest.get("independent_verification_status") != "NOT_RUN"
        or manifest.get("external_evidence_status") != "NOT_RUN"
        or manifest.get("certification_status") != "NOT_CERTIFIED"
    ):
        raise SupplyChainFailure("RELEASE_MANIFEST_BOUNDARY_INVALID")


def verify_release_signature(
    manifest_path: Path,
    signature_path: Path,
    trust_root_path: Path,
    *,
    workspace: Path,
    sbom_path: Path,
    verification_path: Path,
    source_repository: Path,
    verified_at: datetime | None = None,
) -> dict[str, Any]:
    for path, reason in (
        (manifest_path, "RELEASE_MANIFEST_UNSAFE"),
        (signature_path, "RELEASE_SIGNATURE_UNSAFE"),
        (trust_root_path, "RELEASE_TRUST_ROOT_UNSAFE"),
        (sbom_path, "RELEASE_SBOM_UNSAFE"),
        (verification_path, "VERIFICATION_EVIDENCE_UNSAFE"),
    ):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            raise SupplyChainFailure(reason)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        envelope = json.loads(signature_path.read_text(encoding="utf-8"))
        trust_root = json.loads(trust_root_path.read_text(encoding="utf-8"))
        sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SupplyChainFailure("RELEASE_SIGNATURE_INPUT_INVALID") from error
    if not all(isinstance(value, dict) for value in (manifest, envelope, trust_root, sbom)):
        raise SupplyChainFailure("RELEASE_SIGNATURE_INPUT_INVALID")
    _validate_unsigned_release_manifest(manifest)
    rebuilt = build_release_manifest(
        workspace,
        sbom=sbom,
        verification=verification_path,
        source_repository=source_repository,
    )
    if manifest != rebuilt:
        raise SupplyChainFailure("RELEASE_MANIFEST_LIVE_INPUT_MISMATCH")
    if (
        set(envelope)
        != {
            "schema_version",
            "kind",
            "algorithm",
            "key_id",
            "payload_format",
            "payload_sha256",
            "signature_base64",
            "signed_at",
        }
        or
        envelope.get("schema_version") != "1.0.0"
        or envelope.get("kind") != "elmos.project-synthesis.release-signature"
        or envelope.get("algorithm") != "ed25519"
        or envelope.get("payload_format") != "canonical-json"
        or not isinstance(envelope.get("key_id"), str)
    ):
        raise SupplyChainFailure("RELEASE_SIGNATURE_ENVELOPE_INVALID")
    payload = canonical_json(manifest)
    payload_sha256 = sha256_bytes(payload)
    if envelope.get("payload_sha256") != payload_sha256:
        raise SupplyChainFailure("RELEASE_SIGNATURE_PAYLOAD_MISMATCH")
    signed_at = _parse_time(envelope.get("signed_at"), "RELEASE_SIGNATURE_TIME_INVALID")
    now = (verified_at or datetime.now(UTC)).astimezone(UTC)
    if signed_at > now:
        raise SupplyChainFailure("RELEASE_SIGNATURE_FROM_FUTURE")
    if (
        set(trust_root) != {"schema_version", "kind", "trust_root_id", "status", "keys"}
        or
        trust_root.get("schema_version") != "1.0.0"
        or trust_root.get("kind") != "elmos.project-synthesis.release-trust-root"
        or not isinstance(trust_root.get("trust_root_id"), str)
        or trust_root.get("status") != "ACTIVE"
        or not isinstance(trust_root.get("keys"), list)
    ):
        raise SupplyChainFailure("RELEASE_TRUST_ROOT_INVALID")
    matching = [key for key in trust_root["keys"] if isinstance(key, dict) and key.get("key_id") == envelope["key_id"]]
    if len(matching) != 1:
        raise SupplyChainFailure("RELEASE_SIGNING_KEY_NOT_TRUSTED")
    key = matching[0]
    if set(key) != {
        "key_id",
        "algorithm",
        "status",
        "public_key_path",
        "public_key_sha256",
        "valid_from",
        "valid_until",
    }:
        raise SupplyChainFailure("RELEASE_SIGNING_KEY_INVALID")
    if key.get("algorithm") != "ed25519" or key.get("status") != "ACTIVE":
        raise SupplyChainFailure("RELEASE_SIGNING_KEY_NOT_ACTIVE")
    valid_from = _parse_time(key.get("valid_from"), "RELEASE_SIGNING_KEY_TIME_INVALID")
    valid_until = _parse_time(key.get("valid_until"), "RELEASE_SIGNING_KEY_TIME_INVALID")
    if not valid_from <= signed_at <= valid_until or now > valid_until:
        raise SupplyChainFailure("RELEASE_SIGNING_KEY_OUTSIDE_VALIDITY")
    raw_key_path = key.get("public_key_path")
    if not isinstance(raw_key_path, str):
        raise SupplyChainFailure("RELEASE_SIGNING_KEY_PATH_INVALID")
    relative = PurePosixPath(raw_key_path)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts or "\\" in raw_key_path:
        raise SupplyChainFailure("RELEASE_SIGNING_KEY_PATH_INVALID")
    trust_root_directory = trust_root_path.resolve(strict=True).parent
    public_key = trust_root_directory.joinpath(*relative.parts)
    if public_key.is_symlink() or not public_key.is_file() or public_key.resolve(strict=True) != public_key:
        raise SupplyChainFailure("RELEASE_SIGNING_KEY_UNSAFE")
    if key.get("public_key_sha256") != sha256_bytes(public_key.read_bytes()):
        raise SupplyChainFailure("RELEASE_SIGNING_KEY_DIGEST_MISMATCH")
    try:
        signature = base64.b64decode(envelope.get("signature_base64", ""), validate=True)
    except (binascii.Error, ValueError) as error:
        raise SupplyChainFailure("RELEASE_SIGNATURE_ENCODING_INVALID") from error
    if len(signature) != 64:
        raise SupplyChainFailure("RELEASE_SIGNATURE_LENGTH_INVALID")
    openssl = shutil.which("openssl")
    if openssl is None:
        raise SupplyChainFailure("OPENSSL_REQUIRED_FOR_ED25519_VERIFICATION")
    with tempfile.TemporaryDirectory(prefix="elmos-release-signature-") as temporary:
        payload_path = Path(temporary) / "manifest.canonical.json"
        detached_path = Path(temporary) / "manifest.sig"
        payload_path.write_bytes(payload)
        detached_path.write_bytes(signature)
        completed = subprocess.run(  # noqa: S603
            [
                openssl,
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(public_key),
                "-rawin",
                "-in",
                str(payload_path),
                "-sigfile",
                str(detached_path),
            ],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    if completed.returncode != 0:
        raise SupplyChainFailure("RELEASE_SIGNATURE_INVALID")
    final_revision = observe_git_revision(source_repository)
    if final_revision != manifest["source_revision"]:
        raise SupplyChainFailure("SOURCE_REVISION_CHANGED_DURING_SIGNATURE_VERIFICATION")
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.project-synthesis.release-signature-verification",
        "decision": "READY_FOR_EXTERNAL_GATE",
        "manifest_sha256": payload_sha256,
        "signature_sha256": sha256_bytes(signature),
        "trust_root_id": trust_root["trust_root_id"],
        "trust_root_sha256": sha256_bytes(canonical_json(trust_root)),
        "key_id": envelope["key_id"],
        "algorithm": "ed25519",
        "verification_status": "PASSED",
        "ready_for_external_gate": True,
        "production_delivery_status": "NOT_RUN",
        "independent_verification_status": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "production_ready": False,
        "certified": False,
    }
