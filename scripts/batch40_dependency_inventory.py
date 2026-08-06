#!/usr/bin/env python3
"""Batch 40 dependency inventory: a static SBOM of the declared component surface.

This reads the dependency declarations that are actually checked into the
repository — the Maven reactor and any npm lockfiles — and enumerates every
component identity it finds.

What it deliberately does NOT do is guess versions. A Maven dependency whose
version comes from an imported BOM cannot be resolved without running Maven, so
it is recorded as `managed-by-bom` rather than given a plausible-looking number.
`sbomCoverage` counts only components whose version was actually determined, so
an inventory full of unresolved entries scores low — which is the honest signal.

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


def maven_components(repo: Path, poms: list[Path], properties: dict[str, str]) -> list[dict]:
    components: dict[tuple[str, str, str | None], dict] = {}
    for pom in poms:
        try:
            root = ElementTree.parse(pom).getroot()
        except ElementTree.ParseError:
            continue
        relative = pom.relative_to(repo).as_posix()
        for dependency in root.iter(f"{MAVEN_NAMESPACE}dependency"):
            group = text_of(dependency.find(f"{MAVEN_NAMESPACE}groupId"))
            artifact = text_of(dependency.find(f"{MAVEN_NAMESPACE}artifactId"))
            if not group or not artifact:
                continue
            raw_version = text_of(dependency.find(f"{MAVEN_NAMESPACE}version"))
            version, resolution = resolve(raw_version, properties)
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
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    if not repo.is_dir():
        print(f"ERROR: {repo} is not a directory", file=sys.stderr)
        return 2
    started = datetime.now(timezone.utc)

    poms = walk(repo, "pom.xml")
    locks = walk(repo, "package-lock.json")
    properties = collect_properties(poms)
    components = maven_components(repo, poms, properties) + npm_components(repo, locks)

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
        "replayCommand": "python3 scripts/batch40_dependency_inventory.py",
        "toolDigest": sha256_bytes(Path(__file__).read_bytes()),
        "pythonVersion": platform.python_version(),
        "sources": {
            "mavenPomCount": len(poms),
            "npmLockCount": len(locks),
            "sharedPropertyCount": len(properties),
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
            "Versions supplied by an imported BOM are recorded as managed-by-bom, not resolved; running Maven is required to pin them.",
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
