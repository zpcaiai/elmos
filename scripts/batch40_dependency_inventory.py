#!/usr/bin/env python3
"""Batch 40 dependency inventory: a static SBOM of the declared component surface.

This reads the dependency declarations that are actually checked into the
repository — the Maven reactor and any npm lockfiles — and enumerates every
component identity it finds.

What it deliberately does NOT do is guess versions. Maven dependency-management
and imported BOMs are resolved only from exact POM bytes already present in the
local Maven repository. A missing BOM stays unresolved rather than being filled
from a hard-coded catalogue. `sbomCoverage` counts only components whose version
was actually determined, so an incomplete Maven cache remains visible.

Exit codes: 0 = inventory produced, 2 = usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timezone
from pathlib import Path

MAVEN_NAMESPACE = "{http://maven.apache.org/POM/4.0.0}"
PROPERTY_PATTERN = re.compile(r"\$\{([^}]+)\}")
SKIP_DIRECTORIES = {"node_modules", ".git", "_to_delete", "target", "build", "dist", ".next", "__pycache__"}


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def walk(root: Path, name: str) -> list[Path]:
    """Find files by name, pruning skipped directories as we descend.

    Filtering the results of rglob is not enough: rglob still walks into
    node_modules first, which on a repository this size takes minutes.
    """
    found: list[Path] = []
    for directory, subdirectories, filenames in os.walk(root):
        subdirectories[:] = sorted(item for item in subdirectories if item not in SKIP_DIRECTORIES)
        if name in filenames:
            found.append(Path(directory) / name)
    return sorted(found)


def text_of(node: ElementTree.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value or None


def collect_properties(poms: list[Path]) -> dict[str, str]:
    """Gather <properties> across the reactor.

    Maven resolves properties per-module with inheritance; this flattens them,
    which is why a resolution that depends on a shadowed property is reported as
    unresolved rather than silently taking the wrong value.
    """
    properties: dict[str, str] = {}
    conflicts: set[str] = set()
    for pom in poms:
        try:
            root = ElementTree.parse(pom).getroot()
        except ElementTree.ParseError:
            continue
        block = root.find(f"{MAVEN_NAMESPACE}properties")
        if block is None:
            continue
        for child in block:
            key = child.tag.replace(MAVEN_NAMESPACE, "")
            value = (child.text or "").strip()
            if not value:
                continue
            if key in properties and properties[key] != value:
                conflicts.add(key)
            properties[key] = value
    for key in conflicts:
        properties.pop(key, None)
    return properties


def pom_coordinates(root: ElementTree.Element) -> tuple[str | None, str | None, str | None]:
    parent = root.find(f"{MAVEN_NAMESPACE}parent")
    group = text_of(root.find(f"{MAVEN_NAMESPACE}groupId"))
    version = text_of(root.find(f"{MAVEN_NAMESPACE}version"))
    if parent is not None:
        group = group or text_of(parent.find(f"{MAVEN_NAMESPACE}groupId"))
        version = version or text_of(parent.find(f"{MAVEN_NAMESPACE}version"))
    return group, text_of(root.find(f"{MAVEN_NAMESPACE}artifactId")), version


def pom_properties(root: ElementTree.Element, inherited: dict[str, str]) -> dict[str, str]:
    properties = dict(inherited)
    group, artifact, version = pom_coordinates(root)
    aliases = {
        "project.groupId": group,
        "pom.groupId": group,
        "project.artifactId": artifact,
        "pom.artifactId": artifact,
        "project.version": version,
        "pom.version": version,
    }
    properties.update({key: value for key, value in aliases.items() if value})
    block = root.find(f"{MAVEN_NAMESPACE}properties")
    if block is not None:
        for child in block:
            key = child.tag.replace(MAVEN_NAMESPACE, "")
            value = (child.text or "").strip()
            if value:
                properties[key] = value
    return properties


def expand(value: str | None, properties: dict[str, str]) -> str | None:
    """Resolve a bounded property chain, rejecting cycles and missing values."""
    if value is None:
        return None
    current = value
    seen: set[str] = set()
    for _ in range(32):
        matches = PROPERTY_PATTERN.findall(current)
        if not matches:
            return current
        if any(name in seen or name not in properties for name in matches):
            return None
        seen.update(matches)
        current = PROPERTY_PATTERN.sub(lambda match: properties[match.group(1)], current)
    return None


def local_bom_path(repository: Path, group: str, artifact: str, version: str) -> Path:
    return repository.joinpath(*group.split("."), artifact, version, f"{artifact}-{version}.pom")


def collect_managed_versions(
    root: ElementTree.Element,
    inherited: dict[str, str],
    maven_repository: Path,
    visited: set[Path],
    bom_sources: list[dict],
) -> dict[tuple[str, str], tuple[str, str]]:
    """Return exact managed versions, recursively expanding cached imported BOMs."""
    properties = pom_properties(root, inherited)
    managed: dict[tuple[str, str], tuple[str, str]] = {}
    block = root.find(f"{MAVEN_NAMESPACE}dependencyManagement/{MAVEN_NAMESPACE}dependencies")
    if block is None:
        return managed
    imports: list[tuple[str, str, str]] = []
    for dependency in block.findall(f"{MAVEN_NAMESPACE}dependency"):
        group = expand(text_of(dependency.find(f"{MAVEN_NAMESPACE}groupId")), properties)
        artifact = expand(text_of(dependency.find(f"{MAVEN_NAMESPACE}artifactId")), properties)
        version = expand(text_of(dependency.find(f"{MAVEN_NAMESPACE}version")), properties)
        dep_type = text_of(dependency.find(f"{MAVEN_NAMESPACE}type")) or "jar"
        scope = text_of(dependency.find(f"{MAVEN_NAMESPACE}scope")) or "compile"
        if not group or not artifact or not version:
            continue
        if dep_type == "pom" and scope == "import":
            imports.append((group, artifact, version))
        else:
            managed[(group, artifact)] = (version, "dependency-management")
    for group, artifact, version in imports:
        path = local_bom_path(maven_repository, group, artifact, version).resolve()
        if path in visited or not path.is_file():
            continue
        visited.add(path)
        try:
            bom_root = ElementTree.parse(path).getroot()
        except ElementTree.ParseError:
            continue
        bom_sources.append({
            "coordinate": f"{group}:{artifact}:{version}",
            "path": path.relative_to(maven_repository.resolve()).as_posix(),
            "sha256": sha256_bytes(path.read_bytes()),
        })
        imported = collect_managed_versions(
            bom_root, properties, maven_repository, visited, bom_sources
        )
        for coordinate, resolved in imported.items():
            managed.setdefault(coordinate, resolved)
    return managed


def resolve(value: str | None, properties: dict[str, str]) -> tuple[str | None, str]:
    if value is None:
        return None, "managed-by-bom"
    if value == "${project.version}":
        return None, "project-version"
    match = PROPERTY_PATTERN.fullmatch(value)
    if match:
        resolved = properties.get(match.group(1))
        if resolved is None:
            return None, "unresolved-property"
        if PROPERTY_PATTERN.search(resolved):
            return None, "unresolved-property"
        return resolved, "property"
    if PROPERTY_PATTERN.search(value):
        return None, "unresolved-property"
    return value, "literal"


def maven_components(
    repo: Path,
    poms: list[Path],
    properties: dict[str, str],
    managed: dict[tuple[str, str], tuple[str, str]],
) -> list[dict]:
    components: dict[tuple[str, str, str | None], dict] = {}
    for pom in poms:
        try:
            root = ElementTree.parse(pom).getroot()
        except ElementTree.ParseError:
            continue
        relative = pom.relative_to(repo).as_posix()
        # Repository properties are intentionally flattened conservatively by
        # collect_properties: a name that differs between modules is removed.
        # Re-introducing a module-local value here would silently defeat that
        # conflict check. Only the current Maven project aliases are local.
        local_properties = dict(properties)
        group_id, artifact_id, project_version = pom_coordinates(root)
        local_properties.update({
            key: value
            for key, value in {
                "project.groupId": group_id,
                "pom.groupId": group_id,
                "project.artifactId": artifact_id,
                "pom.artifactId": artifact_id,
                "project.version": project_version,
                "pom.version": project_version,
            }.items()
            if value
        })
        dependency_blocks = list(root.findall(f"{MAVEN_NAMESPACE}dependencies"))
        profiles = root.find(f"{MAVEN_NAMESPACE}profiles")
        if profiles is not None:
            dependency_blocks.extend(
                profile.find(f"{MAVEN_NAMESPACE}dependencies")
                for profile in profiles.findall(f"{MAVEN_NAMESPACE}profile")
                if profile.find(f"{MAVEN_NAMESPACE}dependencies") is not None
            )
        for block in dependency_blocks:
            for dependency in block.findall(f"{MAVEN_NAMESPACE}dependency"):
                group = text_of(dependency.find(f"{MAVEN_NAMESPACE}groupId"))
                artifact = text_of(dependency.find(f"{MAVEN_NAMESPACE}artifactId"))
                if not group or not artifact:
                    continue
                raw_version = text_of(dependency.find(f"{MAVEN_NAMESPACE}version"))
                version, resolution = resolve(raw_version, local_properties)
                if version is None and raw_version == "${project.version}":
                    version = local_properties.get("project.version")
                    resolution = "project-version" if version else resolution
                if version is None and raw_version is None and (group, artifact) in managed:
                    version, source = managed[(group, artifact)]
                    resolution = source
                scope = text_of(dependency.find(f"{MAVEN_NAMESPACE}scope")) or "compile"
                key = (group, artifact, version)
                entry = components.setdefault(key, {
                    "ecosystem": "maven",
                    "group": group,
                    "name": artifact,
                    "version": version,
                    "versionResolution": resolution,
                    "declaredVersion": raw_version,
                    "purl": f"pkg:maven/{group}/{artifact}" + (f"@{version}" if version else ""),
                    "scopes": set(),
                    "internal": group.startswith("io.elmos"),
                    "declaredIn": set(),
                })
                entry["scopes"].add(scope)
                entry["declaredIn"].add(relative)
    ordered = []
    for entry in components.values():
        entry["scopes"] = sorted(entry["scopes"])
        entry["declaredIn"] = sorted(entry["declaredIn"])
        ordered.append(entry)
    return sorted(ordered, key=lambda item: (item["group"], item["name"], item["version"] or ""))


def npm_components(repo: Path, locks: list[Path]) -> list[dict]:
    components: dict[tuple[str, str | None], dict] = {}
    for lock in locks:
        try:
            payload = json.loads(lock.read_text(encoding="utf-8"))
        except (ValueError, json.JSONDecodeError):
            continue
        relative = lock.relative_to(repo).as_posix()
        for path, package in (payload.get("packages") or {}).items():
            if not path or not isinstance(package, dict):
                continue  # the "" entry is the project itself
            name = package.get("name") or path.split("node_modules/")[-1]
            version = package.get("version")
            key = (name, version)
            entry = components.setdefault(key, {
                "ecosystem": "npm",
                "group": None,
                "name": name,
                "version": version,
                "versionResolution": "lockfile" if version else "unresolved-lock-entry",
                "declaredVersion": version,
                "purl": f"pkg:npm/{name}" + (f"@{version}" if version else ""),
                "integrity": package.get("integrity"),
                "license": package.get("license"),
                "scopes": ["dev"] if package.get("dev") else ["runtime"],
                "internal": False,
                "declaredIn": set(),
            })
            entry["declaredIn"].add(relative)
    ordered = []
    for entry in components.values():
        entry["declaredIn"] = sorted(entry["declaredIn"])
        ordered.append(entry)
    return sorted(ordered, key=lambda item: (item["name"], item["version"] or ""))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--maven-repository",
        type=Path,
        default=Path(os.environ.get("MAVEN_REPOSITORY", Path.home() / ".m2" / "repository")),
        help="local Maven repository used only to resolve exact imported BOM POMs",
    )
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    if not repo.is_dir():
        print(f"ERROR: {repo} is not a directory", file=sys.stderr)
        return 2
    started = datetime.now(timezone.utc)

    poms = walk(repo, "pom.xml")
    locks = walk(repo, "package-lock.json")
    properties = collect_properties(poms)
    managed: dict[tuple[str, str], tuple[str, str]] = {}
    bom_sources: list[dict] = []
    visited: set[Path] = set()
    for pom in poms:
        try:
            pom_root = ElementTree.parse(pom).getroot()
        except ElementTree.ParseError:
            continue
        discovered = collect_managed_versions(
            pom_root, properties, arguments.maven_repository.resolve(), visited, bom_sources
        )
        managed.update(discovered)
    components = maven_components(repo, poms, properties, managed) + npm_components(repo, locks)

    external = [item for item in components if not item["internal"]]
    versioned = [item for item in external if item["version"]]
    resolution_counts: dict[str, int] = {}
    for item in components:
        resolution_counts[item["versionResolution"]] = resolution_counts.get(item["versionResolution"], 0) + 1

    finished = datetime.now(timezone.utc)
    report = {
        "check": "batch40-dependency-inventory",
        "batch": 40,
        "startedAt": started.isoformat().replace("+00:00", "Z"),
        "finishedAt": finished.isoformat().replace("+00:00", "Z"),
        "replayCommand": "python3 scripts/batch40_dependency_inventory.py --maven-repository <path>",
        "toolDigest": sha256_bytes(Path(__file__).read_bytes()),
        "pythonVersion": platform.python_version(),
        "sources": {
            "mavenPomCount": len(poms),
            "npmLockCount": len(locks),
            "sharedPropertyCount": len(properties),
            "managedCoordinateCount": len(managed),
            "mavenBomCount": len(bom_sources),
            "mavenBoms": sorted(bom_sources, key=lambda item: item["coordinate"]),
        },
        "totals": {
            "componentCount": len(components),
            "externalComponentCount": len(external),
            "internalComponentCount": len(components) - len(external),
            "versionedExternalCount": len(versioned),
        },
        "versionResolution": dict(sorted(resolution_counts.items())),
        "metrics": {
            # Coverage is the share of external components whose version is
            # actually known. Unresolved entries drag it down on purpose.
            "sbomCoverage": round(len(versioned) / len(external), 4) if external else 0.0,
        },
        "limitations": [
            "Static declaration parse only: transitive Maven dependencies are not expanded, so this is a direct-dependency inventory rather than a full build graph.",
            "Imported BOM versions are resolved only from content-addressed POMs in the selected local Maven repository; missing or invalid BOMs remain unresolved.",
            "Properties are flattened across the reactor; a property redefined with different values in different modules is dropped rather than guessed.",
            "No vulnerability lookup is performed, so this inventory alone does not establish CVE exposure.",
        ],
        "components": [
            {key: value for key, value in item.items() if key != "internal"} | {"internal": item["internal"]}
            for item in components
        ],
    }

    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload, encoding="utf-8")
        print(f"wrote {arguments.output}")
    else:
        print(payload)
    print(
        f"poms={len(poms)} locks={len(locks)} components={len(components)} "
        f"external={len(external)} versioned={len(versioned)} "
        f"coverage={report['metrics']['sbomCoverage']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
