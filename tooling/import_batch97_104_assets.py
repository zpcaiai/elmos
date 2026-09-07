#!/usr/bin/env python3
"""Import, normalize, install, and verify the Batch 97-104 Skill package."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "elmos-codex-skills-batch97-104-complete"
PACKAGE_ROOT = ROOT / PACKAGE_NAME
RUNTIME_ROOT = ROOT / "agent-skills" / "runtime"
INSTALL_MANIFEST = ROOT / "docs" / "batch97-104" / "installed-manifest.json"
SKILL_GENERATOR = (
    Path.home() / ".codex" / "skills" / ".system" / "skill-creator" / "scripts"
    / "generate_openai_yaml.py"
)
EXPECTED_BATCHES = list(range(97, 105))
EXPECTED_SKILLS = 128
EXPECTED_IDS = [f"B{batch}-S{sequence:02d}" for batch in EXPECTED_BATCHES for sequence in range(1, 17)]
PACKAGE_VERSION = "1.0.1-repository.1"
DEPENDENCY_REPAIRS = {
    "B101-S16": ["B101-S15"],
    "B102-S15": ["B102-S14"],
}
REQUIRED_HEADINGS = {
    "## Objective",
    "## When to Use",
    "## Scope",
    "## Inputs",
    "## Outputs",
    "## Preconditions",
    "## Workflow",
    "## Implementation Requirements",
    "## Required Checks",
    "## Security and Hard Rules",
    "## Required Tests",
    "## Verification States",
    "## Stop and Escalate",
    "## Evidence Contract",
    "## Definition of Done",
    "## Completion Report",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def included_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in included_files(root):
        relative = path.relative_to(root).as_posix().encode()
        digest.update(relative)
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        fail(f"Path escapes package root: {relative}")
        raise AssertionError from exc
    return candidate


def dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def normalize_outputs_section(text: str) -> str:
    match = re.search(r"(?ms)^## Outputs\n(.*?)(?=^## )", text)
    if match is None:
        fail("Skill is missing an Outputs section")
    seen: set[str] = set()
    normalized: list[str] = []
    for line in match.group(1).splitlines():
        if line.startswith("- `"):
            if line in seen:
                continue
            seen.add(line)
        normalized.append(line)
    replacement = "\n".join(normalized).rstrip() + "\n\n"
    return text[: match.start(1)] + replacement + text[match.end(1) :].lstrip("\n")


def replace_dependency_line(text: str, dependencies: list[str]) -> str:
    rendered = "None inside this package; use the installed Batch 1–96 capability graph as upstream authority."
    if dependencies:
        rendered = ", ".join(f"`{dependency}`" for dependency in dependencies)
    updated, count = re.subn(
        r"^Package dependencies:.*$",
        f"Package dependencies: {rendered}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        fail("Skill dependency declaration is missing or duplicated")
    return updated


def load_generator() -> ModuleType:
    if not SKILL_GENERATOR.is_file():
        fail(f"Skill interface generator is missing: {SKILL_GENERATOR}")
    spec = importlib.util.spec_from_file_location("elmos_skill_interface_generator", SKILL_GENERATOR)
    if spec is None or spec.loader is None:
        fail(f"Cannot load Skill interface generator: {SKILL_GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_interface(name: str, generator: ModuleType | None = None) -> str:
    if generator is None:
        acronyms = {"API", "CI", "CLI", "PR", "SQL", "UI"}
        small = {"and", "or", "to", "up", "with"}
        words: list[str] = []
        for index, word in enumerate(name.split("-")):
            if word.upper() in acronyms:
                words.append(word.upper())
            elif index > 0 and word in small:
                words.append(word)
            else:
                words.append(word.capitalize())
        display = " ".join(words)

        def quote(value: str) -> str:
            return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    else:
        display = generator.format_display_name(name)
        quote = generator.yaml_quote
    short = "Run this ELMOS product-closure Skill safely"
    prompt = f"Use ${name} to execute this ELMOS product-closure Skill with fail-closed evidence."
    return "\n".join(
        [
            "interface:",
            f"  display_name: {quote(display)}",
            f"  short_description: {quote(short)}",
            f"  default_prompt: {quote(prompt)}",
            "",
        ]
    )


def generate_interfaces(package: Path) -> None:
    generator = load_generator()
    for skill_dir in sorted((package / "agent-skills" / "runtime").iterdir()):
        if not skill_dir.is_dir():
            continue
        name = skill_dir.name
        result = generator.write_openai_yaml(
            skill_dir,
            name,
            [
                "short_description=Run this ELMOS product-closure Skill safely",
                f"default_prompt=Use ${name} to execute this ELMOS product-closure Skill with fail-closed evidence.",
            ],
        )
        interface = skill_dir / "agents" / "openai.yaml"
        if result is None or interface.read_text(encoding="utf-8") != expected_interface(name, generator):
            fail(f"Skill interface generation failed: {name}")


def validate_raw_source(source: Path) -> dict[str, Any]:
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        fail(f"Source package manifest is missing: {manifest_path}")
    manifest = load_json(manifest_path)
    if manifest.get("package") != PACKAGE_NAME:
        fail("Source package identity is invalid")
    if manifest.get("skill_count") != EXPECTED_SKILLS:
        fail("Source package must declare exactly 128 Skills")
    if manifest.get("batches") != EXPECTED_BATCHES:
        fail("Source package batches must be exactly 97-104")
    if manifest.get("local_id_range") != ["B97-S01", "B104-S16"]:
        fail("Source package local identity range is invalid")
    skills = manifest.get("skills")
    if not isinstance(skills, list) or [entry.get("id") for entry in skills] != EXPECTED_IDS:
        fail("Source Skill identities must be exactly B97-S01 through B104-S16")
    names = [entry.get("name") for entry in skills]
    if len(set(names)) != EXPECTED_SKILLS or any(
        not isinstance(name, str) or not re.fullmatch(r"[a-z0-9-]+", name) or len(name) > 64
        for name in names
    ):
        fail("Source Skill names are invalid or duplicated")
    for entry in manifest.get("files", []):
        relative = entry.get("path")
        if not isinstance(relative, str):
            fail("Source package file inventory contains an invalid path")
        path = safe_path(source, relative)
        if not path.is_file() or path.stat().st_size != entry.get("size_bytes"):
            fail(f"Source package file size mismatch: {relative}")
        if sha256_file(path) != entry.get("sha256"):
            fail(f"Source package file digest mismatch: {relative}")
    return manifest


def copy_source(source: Path) -> None:
    if PACKAGE_ROOT.exists():
        fail(f"Destination already exists: {PACKAGE_ROOT}")
    shutil.copytree(
        source,
        PACKAGE_ROOT,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def assert_dependency_dag(skills: list[dict[str, Any]]) -> None:
    identifiers = {entry["id"] for entry in skills}
    graph = {entry["id"]: entry.get("depends_on", []) for entry in skills}
    for identifier, dependencies in graph.items():
        if not isinstance(dependencies, list) or any(value not in identifiers for value in dependencies):
            fail(f"Skill dependency is invalid: {identifier}")
        if len(dependencies) != len(set(dependencies)):
            fail(f"Skill dependency is duplicated: {identifier}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            fail(f"Blocking Skill dependency cycle detected at {identifier}")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in graph[identifier]:
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in graph:
        visit(identifier)


def normalize_package(source_digest: str | None = None) -> dict[str, Any]:
    manifest = load_json(PACKAGE_ROOT / "manifest.json")
    skills = manifest["skills"]
    by_id = {entry["id"]: entry for entry in skills}
    for identifier, dependencies in DEPENDENCY_REPAIRS.items():
        by_id[identifier]["depends_on"] = dependencies
    for entry in skills:
        entry["outputs"] = dedupe(entry.get("outputs", []))
        for key in ("path", "catalog_path"):
            path = safe_path(PACKAGE_ROOT, entry[key])
            text = normalize_outputs_section(path.read_text(encoding="utf-8"))
            text = replace_dependency_line(text, entry.get("depends_on", []))
            path.write_text(text, encoding="utf-8")
        runtime = safe_path(PACKAGE_ROOT, entry["path"])
        catalog = safe_path(PACKAGE_ROOT, entry["catalog_path"])
        if runtime.read_bytes() != catalog.read_bytes():
            fail(f"Canonical and runtime Skill differ after normalization: {entry['id']}")
        entry["sha256"] = sha256_file(runtime)

    for batch in EXPECTED_BATCHES:
        batch_path = PACKAGE_ROOT / "manifests" / f"batch-{batch}.json"
        batch_manifest = load_json(batch_path)
        for entry in batch_manifest["skills"]:
            canonical = by_id[entry["id"]]
            entry["depends_on"] = canonical["depends_on"]
            entry["outputs"] = canonical["outputs"]
            entry["sha256"] = canonical["sha256"]
        batch_manifest["version"] = PACKAGE_VERSION
        write_json(batch_path, batch_manifest)

    generate_interfaces(PACKAGE_ROOT)
    normalization_path = PACKAGE_ROOT / "NORMALIZATION.json"
    previous = load_json(normalization_path) if normalization_path.is_file() else {}
    normalization = {
        "schema_version": "elmos.batch97-104-normalization.v1",
        "source_package": PACKAGE_NAME,
        "source_version": "1.0.0",
        "normalized_version": PACKAGE_VERSION,
        "source_tree_sha256": source_digest or previous.get("source_tree_sha256"),
        "repairs": [
            {"code": "DUPLICATE_OUTPUTS", "affected_skills": 32, "status": "repaired"},
            {
                "code": "BLOCKING_DEPENDENCY_CYCLES",
                "affected_skills": sorted(DEPENDENCY_REPAIRS),
                "status": "repaired",
            },
            {"code": "MISSING_CODEX_INTERFACES", "affected_skills": 128, "status": "repaired"},
            {"code": "INCOMPLETE_FILE_INVENTORY", "status": "repaired"},
        ],
        "identity_policy": "batch-local-product-closure; global PG IDs remain unassigned",
        "external_evidence_status": "NOT_RUN",
    }
    if not normalization["source_tree_sha256"]:
        fail("Normalization source tree digest is missing")
    write_json(normalization_path, normalization)

    manifest["version"] = PACKAGE_VERSION
    manifest["global_id_policy"] = (
        "unassigned; preserve batch-local product-closure identity until a separately approved "
        "global namespace allocation exists"
    )
    manifest["repository_normalization"] = "NORMALIZATION.json"
    manifest["skills"] = skills
    manifest["files"] = []
    payload = [
        path
        for path in included_files(PACKAGE_ROOT)
        if path.name not in {"manifest.json", "SHA256SUMS.txt"}
    ]
    manifest["files"] = [
        {
            "path": path.relative_to(PACKAGE_ROOT).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in payload
    ]
    write_json(PACKAGE_ROOT / "manifest.json", manifest)
    checksummed = [
        path for path in included_files(PACKAGE_ROOT) if path.name != "SHA256SUMS.txt"
    ]
    (PACKAGE_ROOT / "SHA256SUMS.txt").write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(PACKAGE_ROOT).as_posix()}\n"
            for path in checksummed
        ),
        encoding="utf-8",
    )
    assert_dependency_dag(skills)
    return manifest


def expected_install_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    entries = []
    for skill in manifest["skills"]:
        name = skill["name"]
        canonical = PACKAGE_ROOT / skill["path"]
        interface = canonical.parent / "agents" / "openai.yaml"
        entries.append(
            {
                "source_key": f"PRODUCT-CLOSURE-{skill['id']}",
                "source_id": skill["id"],
                "global_id": None,
                "batch": skill["batch"],
                "source_name": name,
                "installed_name": name,
                "source_path": canonical.relative_to(ROOT).as_posix(),
                "source_sha256": "sha256:" + sha256_file(canonical),
                "installed_path": f"agent-skills/runtime/{name}/SKILL.md",
                "installed_sha256": "sha256:" + sha256_file(canonical),
                "interface_path": f"agent-skills/runtime/{name}/agents/openai.yaml",
                "interface_sha256": "sha256:" + sha256_file(interface),
            }
        )
    return {
        "schema_version": "elmos.batch97-104-installed-skills.v1",
        "package": PACKAGE_NAME,
        "package_version": manifest["version"],
        "source_id_namespace": "batch-local-product-closure",
        "source_id_range": ["B97-S01", "B104-S16"],
        "global_id_assignment": "UNASSIGNED",
        "skill_count": EXPECTED_SKILLS,
        "external_evidence_status": "NOT_RUN",
        "skills": entries,
    }


def sync_installed(manifest: dict[str, Any]) -> None:
    prior = load_json(INSTALL_MANIFEST) if INSTALL_MANIFEST.is_file() else None
    managed = {
        entry["installed_name"] for entry in prior.get("skills", [])
    } if isinstance(prior, dict) else set()
    for skill in manifest["skills"]:
        name = skill["name"]
        source_dir = (PACKAGE_ROOT / skill["path"]).parent
        destination = RUNTIME_ROOT / name
        if destination.exists() and name not in managed:
            fail(f"Refusing to overwrite unmanaged Runtime Skill: {destination}")
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_dir / "SKILL.md", destination / "SKILL.md")
        (destination / "agents").mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_dir / "agents" / "openai.yaml", destination / "agents" / "openai.yaml")
    write_json(INSTALL_MANIFEST, expected_install_manifest(manifest))


def validate_package() -> dict[str, Any]:
    manifest_path = PACKAGE_ROOT / "manifest.json"
    if not manifest_path.is_file():
        fail(f"Imported package is missing: {manifest_path}")
    manifest = load_json(manifest_path)
    if manifest.get("package") != PACKAGE_NAME or manifest.get("version") != PACKAGE_VERSION:
        fail("Imported package identity or normalized version is invalid")
    if manifest.get("skill_count") != EXPECTED_SKILLS or manifest.get("batches") != EXPECTED_BATCHES:
        fail("Imported package count or Batch range is invalid")
    skills = manifest.get("skills")
    if not isinstance(skills, list) or [entry.get("id") for entry in skills] != EXPECTED_IDS:
        fail("Imported package Skill identities are invalid")
    if any(entry.get("global_id") is not None for entry in skills):
        fail("Batch-local Skill identity was silently assigned a global ID")
    if any(len(entry.get("outputs", [])) != len(set(entry.get("outputs", []))) for entry in skills):
        fail("Duplicate Skill outputs remain")
    assert_dependency_dag(skills)

    inventory = manifest.get("files")
    if not isinstance(inventory, list) or not inventory:
        fail("Imported package file inventory is missing")
    listed: set[str] = set()
    for entry in inventory:
        relative = entry.get("path")
        if not isinstance(relative, str) or relative in listed:
            fail(f"Invalid or duplicate package inventory path: {relative}")
        listed.add(relative)
        path = safe_path(PACKAGE_ROOT, relative)
        if not path.is_file() or path.stat().st_size != entry.get("size_bytes"):
            fail(f"Imported package file size mismatch: {relative}")
        if sha256_file(path) != entry.get("sha256"):
            fail(f"Imported package file digest mismatch: {relative}")
    actual = {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in included_files(PACKAGE_ROOT)
        if path.name not in {"manifest.json", "SHA256SUMS.txt"}
    }
    if listed != actual:
        fail(f"Imported package file inventory differs: missing={sorted(actual-listed)}, extra={sorted(listed-actual)}")

    sums: dict[str, str] = {}
    for line_number, line in enumerate((PACKAGE_ROOT / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            fail(f"Invalid SHA256SUMS line {line_number}")
        relative = parts[1].strip().lstrip("*")
        if relative in sums:
            fail(f"Duplicate SHA256SUMS path: {relative}")
        path = safe_path(PACKAGE_ROOT, relative)
        if not path.is_file() or sha256_file(path) != parts[0]:
            fail(f"SHA256SUMS mismatch: {relative}")
        sums[relative] = parts[0]
    if set(sums) != actual | {"manifest.json"}:
        fail("SHA256SUMS does not cover the exact canonical package")

    by_id = {entry["id"]: entry for entry in skills}
    split_entries: list[dict[str, Any]] = []
    for batch in EXPECTED_BATCHES:
        batch_manifest = load_json(PACKAGE_ROOT / "manifests" / f"batch-{batch}.json")
        entries = batch_manifest.get("skills")
        if (
            batch_manifest.get("batch") != batch
            or batch_manifest.get("version") != PACKAGE_VERSION
            or batch_manifest.get("skill_count") != 16
            or not isinstance(entries, list)
            or len(entries) != 16
        ):
            fail(f"Batch {batch} split manifest is invalid")
        split_entries.extend(entries)
    if [entry.get("id") for entry in split_entries] != EXPECTED_IDS:
        fail("Split manifest ordering or identities differ")
    for split in split_entries:
        canonical = by_id[split["id"]]
        for key in ("name", "batch", "path", "catalog_path", "depends_on", "outputs", "sha256"):
            if split.get(key) != canonical.get(key):
                fail(f"Split manifest differs for {split['id']}: {key}")

    index = load_json(PACKAGE_ROOT / "index.json")
    if [entry.get("id") for entry in index.get("skills", [])] != EXPECTED_IDS:
        fail("Package index identities or order differ")
    for skill in skills:
        name = skill["name"]
        runtime = safe_path(PACKAGE_ROOT, skill["path"])
        catalog = safe_path(PACKAGE_ROOT, skill["catalog_path"])
        if not runtime.is_file() or runtime.read_bytes() != catalog.read_bytes():
            fail(f"Canonical Skill representations differ: {skill['id']}")
        if sha256_file(runtime) != skill["sha256"]:
            fail(f"Canonical Skill digest mismatch: {skill['id']}")
        text = runtime.read_text(encoding="utf-8")
        if not REQUIRED_HEADINGS.issubset(set(text.splitlines())):
            fail(f"Canonical Skill sections are incomplete: {skill['id']}")
        if re.search(rf"^name:\s*{re.escape(name)}\s*$", text, re.MULTILINE) is None:
            fail(f"Canonical Skill name mismatch: {skill['id']}")
        if f"  id: {skill['id']}" not in text or f"  batch: {skill['batch']}" not in text:
            fail(f"Canonical Skill source identity is missing: {skill['id']}")
        interface = runtime.parent / "agents" / "openai.yaml"
        if not interface.is_file() or interface.read_text(encoding="utf-8") != expected_interface(name):
            fail(f"Canonical Skill interface is missing or stale: {name}")
        installed = RUNTIME_ROOT / name / "SKILL.md"
        installed_interface = installed.parent / "agents" / "openai.yaml"
        if not installed.is_file() or installed.read_bytes() != runtime.read_bytes():
            fail(f"Installed Runtime Skill is missing or changed: {name}")
        if not installed_interface.is_file() or installed_interface.read_bytes() != interface.read_bytes():
            fail(f"Installed Runtime Skill interface is missing or changed: {name}")

    expected_install = expected_install_manifest(manifest)
    if not INSTALL_MANIFEST.is_file() or load_json(INSTALL_MANIFEST) != expected_install:
        fail("Installed Runtime Skill manifest is missing or changed")
    normalization = load_json(PACKAGE_ROOT / "NORMALIZATION.json")
    if normalization.get("external_evidence_status") != "NOT_RUN":
        fail("Package normalization overclaims external evidence")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("/Users/stephen/Downloads") / PACKAGE_NAME,
        help="supplied Batch 97-104 distribution",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--import-package", action="store_true", help="import and normalize the supplied package")
    mode.add_argument("--refresh-locks", action="store_true", help="refresh hashes after an intentional package repair")
    mode.add_argument("--check", action="store_true", help="verify the normalized package and installed Skills")
    args = parser.parse_args()
    if args.import_package:
        source = args.source.resolve()
        validate_raw_source(source)
        digest = tree_digest(source)
        copy_source(source)
        manifest = normalize_package(digest)
        sync_installed(manifest)
    elif args.refresh_locks:
        if not PACKAGE_ROOT.is_dir():
            fail("Cannot refresh an absent imported package")
        manifest = normalize_package()
        sync_installed(manifest)
    else:
        manifest = validate_package()
    manifest = validate_package()
    print(
        json.dumps(
            {
                "package": PACKAGE_NAME,
                "version": manifest["version"],
                "skills": EXPECTED_SKILLS,
                "batches": [97, 104],
                "source_namespace": "batch-local-product-closure",
                "interfaces": EXPECTED_SKILLS,
                "external_evidence": "NOT_RUN",
                "status": "verified" if not args.import_package else "imported-normalized-verified",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
