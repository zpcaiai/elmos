#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


EXPECTED_BATCHES = list(range(97, 105))
EXPECTED_IDS = [f"B{batch}-S{sequence:02d}" for batch in EXPECTED_BATCHES for sequence in range(1, 17)]
EXPECTED_VERSION = "1.0.1-repository.1"
REQUIRED = {
    "## Objective", "## When to Use", "## Scope", "## Inputs", "## Outputs",
    "## Preconditions", "## Workflow", "## Implementation Requirements",
    "## Required Checks", "## Security and Hard Rules", "## Required Tests",
    "## Verification States", "## Stop and Escalate", "## Evidence Contract",
    "## Definition of Done", "## Completion Report",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_path(root: Path, relative: str) -> Path:
    raw = root / relative
    if raw.is_symlink():
        raise ValueError(f"symlink is not allowed: {relative}")
    path = raw.resolve()
    path.relative_to(root.resolve())
    return path


def package_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


def load_compiler(root: Path) -> ModuleType:
    path = root / "scripts" / "compile_skill_contract.py"
    spec = importlib.util.spec_from_file_location("batch97_104_contract_compiler", path)
    if spec is None or spec.loader is None:
        raise ValueError("contract compiler cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_dag(skills: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    identifiers = {skill.get("id") for skill in skills}
    graph: dict[str, list[str]] = {}
    for skill in skills:
        identifier = skill.get("id")
        dependencies = skill.get("depends_on")
        if not isinstance(identifier, str) or not isinstance(dependencies, list):
            errors.append(f"invalid dependency declaration: {identifier}")
            continue
        if len(dependencies) != len(set(dependencies)):
            errors.append(f"duplicate dependency: {identifier}")
        unknown = [dependency for dependency in dependencies if dependency not in identifiers]
        if unknown:
            errors.append(f"unknown dependency for {identifier}: {unknown}")
        graph[identifier] = dependencies
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> bool:
        if identifier in visiting:
            return True
        if identifier in visited:
            return False
        visiting.add(identifier)
        if any(visit(dependency) for dependency in graph.get(identifier, [])):
            return True
        visiting.remove(identifier)
        visited.add(identifier)
        return False

    if any(visit(identifier) for identifier in sorted(graph)):
        errors.append("blocking dependency graph contains a cycle")
    return errors


def validate(root: Path, expected_batch: int | None = None) -> int:
    errors: list[str] = []
    try:
        import jsonschema
    except ImportError:
        print("ERROR: jsonschema is required; validation may not silently skip schemas", file=sys.stderr)
        return 2

    try:
        manifest = load_json(root / "manifest.json")
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: manifest cannot be loaded: {exc}", file=sys.stderr)
        return 1
    if manifest.get("package") != "elmos-codex-skills-batch97-104-complete":
        errors.append("package identity is invalid")
    if manifest.get("version") != EXPECTED_VERSION:
        errors.append("normalized package version is invalid")
    if manifest.get("skill_count") != 128 or manifest.get("batches") != EXPECTED_BATCHES:
        errors.append("package Skill count or Batch range is invalid")
    if manifest.get("local_id_range") != ["B97-S01", "B104-S16"]:
        errors.append("package local identity range is invalid")
    skills = manifest.get("skills")
    if not isinstance(skills, list):
        skills = []
        errors.append("manifest Skills must be an array")
    if [skill.get("id") for skill in skills] != EXPECTED_IDS:
        errors.append("Skill identities or order differ from B97-S01 through B104-S16")
    names = [skill.get("name") for skill in skills]
    if len(names) != len(set(names)) or any(
        not isinstance(name, str) or re.fullmatch(r"[a-z0-9-]+", name) is None or len(name) > 64
        for name in names
    ):
        errors.append("Skill names are invalid or duplicated")
    if any(skill.get("global_id") is not None for skill in skills):
        errors.append("Batch-local identities were silently mapped to global PG IDs")
    if any(len(skill.get("outputs", [])) != len(set(skill.get("outputs", []))) for skill in skills):
        errors.append("duplicate Skill outputs remain")
    errors.extend(validate_dag(skills))

    inventory = manifest.get("files")
    listed: set[str] = set()
    if not isinstance(inventory, list) or not inventory:
        errors.append("manifest file inventory is missing")
        inventory = []
    for entry in inventory:
        relative = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(relative, str) or relative in listed:
            errors.append(f"invalid or duplicate inventory path: {relative}")
            continue
        listed.add(relative)
        try:
            path = safe_path(root, relative)
        except ValueError:
            errors.append(f"inventory path escapes package: {relative}")
            continue
        if not path.is_file() or path.stat().st_size != entry.get("size_bytes"):
            errors.append(f"file size mismatch: {relative}")
        elif sha256_file(path) != entry.get("sha256"):
            errors.append(f"file digest mismatch: {relative}")
    actual = package_files(root) - {"manifest.json", "SHA256SUMS.txt"}
    if listed != actual:
        errors.append(f"file inventory differs: missing={sorted(actual-listed)}, extra={sorted(listed-actual)}")

    sums: dict[str, str] = {}
    sums_path = root / "SHA256SUMS.txt"
    if not sums_path.is_file():
        errors.append("SHA256SUMS.txt is missing")
    else:
        for line_number, line in enumerate(sums_path.read_text(encoding="utf-8").splitlines(), 1):
            parts = line.split(maxsplit=1)
            if len(parts) != 2 or re.fullmatch(r"[0-9a-f]{64}", parts[0]) is None:
                errors.append(f"invalid SHA256SUMS line {line_number}")
                continue
            relative = parts[1].strip().lstrip("*")
            if relative in sums:
                errors.append(f"duplicate SHA256SUMS path: {relative}")
                continue
            try:
                path = safe_path(root, relative)
            except ValueError:
                errors.append(f"SHA256SUMS path escapes package: {relative}")
                continue
            if not path.is_file() or sha256_file(path) != parts[0]:
                errors.append(f"SHA256SUMS mismatch: {relative}")
            sums[relative] = parts[0]
    if set(sums) != actual | {"manifest.json"}:
        errors.append("SHA256SUMS does not cover the exact canonical package")

    by_id = {skill.get("id"): skill for skill in skills}
    split_entries: list[dict[str, Any]] = []
    for batch in EXPECTED_BATCHES:
        try:
            split = load_json(root / "manifests" / f"batch-{batch}.json")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"Batch {batch} split manifest cannot be loaded: {exc}")
            continue
        entries = split.get("skills")
        if (
            split.get("batch") != batch
            or split.get("version") != EXPECTED_VERSION
            or split.get("skill_count") != 16
            or not isinstance(entries, list)
            or len(entries) != 16
        ):
            errors.append(f"Batch {batch} split manifest is invalid")
            continue
        split_entries.extend(entries)
    if [entry.get("id") for entry in split_entries] != EXPECTED_IDS:
        errors.append("split manifest identities or order differ")
    for split in split_entries:
        canonical = by_id.get(split.get("id"))
        if canonical is None:
            continue
        for key in ("name", "batch", "path", "catalog_path", "depends_on", "outputs", "sha256"):
            if split.get(key) != canonical.get(key):
                errors.append(f"split manifest differs for {split.get('id')}: {key}")

    try:
        index = load_json(root / "index.json")
        if [entry.get("id") for entry in index.get("skills", [])] != EXPECTED_IDS:
            errors.append("index identities or order differ")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"index cannot be loaded: {exc}")

    selected = [skill for skill in skills if expected_batch is None or skill.get("batch") == expected_batch]
    if expected_batch is not None and (expected_batch not in EXPECTED_BATCHES or len(selected) != 16):
        errors.append(f"requested Batch {expected_batch} is not an exact 16-Skill Batch")
    compiler = load_compiler(root)
    contract_schema = load_json(root / "schemas" / "executable-skill-contract-v1.schema.json")
    try:
        jsonschema.Draft202012Validator.check_schema(contract_schema)
    except jsonschema.SchemaError as exc:
        errors.append(f"executable contract schema is invalid: {exc.message}")
    for skill in selected:
        identifier = skill.get("id")
        try:
            runtime = safe_path(root, skill["path"])
            catalog = safe_path(root, skill["catalog_path"])
        except (KeyError, ValueError):
            errors.append(f"Skill path is invalid: {identifier}")
            continue
        if not runtime.is_file() or not catalog.is_file() or runtime.read_bytes() != catalog.read_bytes():
            errors.append(f"Skill catalog/runtime representation differs: {identifier}")
            continue
        if sha256_file(runtime) != skill.get("sha256"):
            errors.append(f"Skill digest mismatch: {identifier}")
        text = runtime.read_text(encoding="utf-8")
        missing = sorted(REQUIRED - set(text.splitlines()))
        if missing:
            errors.append(f"Skill sections are incomplete: {identifier}: {missing}")
        if re.search(rf"^name:\s*{re.escape(str(skill.get('name')))}\s*$", text, re.MULTILINE) is None:
            errors.append(f"Skill frontmatter name mismatch: {identifier}")
        if f"  id: {identifier}" not in text or f"  batch: {skill.get('batch')}" not in text:
            errors.append(f"Skill Batch-local identity is missing: {identifier}")
        interface = runtime.parent / "agents" / "openai.yaml"
        interface_text = interface.read_text(encoding="utf-8") if interface.is_file() else ""
        if not interface_text or f"${skill.get('name')}" not in interface_text:
            errors.append(f"Skill Codex interface is missing or stale: {identifier}")
        try:
            contract = compiler.compile_contract(runtime)
            jsonschema.Draft202012Validator(
                contract_schema,
                format_checker=jsonschema.FormatChecker(),
            ).validate(contract)
        except Exception as exc:
            errors.append(f"Skill contract compilation failed: {identifier}: {exc}")

    schema_map: dict[str, Any] = {}
    for path in sorted((root / "schemas").glob("*.json")):
        try:
            schema = load_json(path)
            jsonschema.Draft202012Validator.check_schema(schema)
            schema_map[path.name] = schema
        except (OSError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
            errors.append(f"invalid JSON Schema {path.name}: {exc}")
    pairs = {
        "capability-graph.example.json": "capability-graph-v1.schema.json",
        "executable-skill-contract.example.json": "executable-skill-contract-v1.schema.json",
        "execution-run.example.json": "execution-run-v1.schema.json",
        "runner-attestation.example.json": "runner-attestation-v1.schema.json",
        "route-pack-result.example.json": "route-pack-result-v1.schema.json",
        "semantic-equivalence-result.example.json": "semantic-equivalence-result-v1.schema.json",
        "evidence-record.example.json": "evidence-record-v1.schema.json",
        "product-certification.example.json": "product-certification-v1.schema.json",
    }
    for template_name, schema_name in pairs.items():
        try:
            jsonschema.Draft202012Validator(
                schema_map[schema_name],
                format_checker=jsonschema.FormatChecker(),
            ).validate(load_json(root / "templates" / template_name))
        except Exception as exc:
            errors.append(f"template validation failed: {template_name}: {exc}")
    fail_closed_templates = {
        "evidence-record.example.json": ("state", "not_run"),
        "product-certification.example.json": ("status", "not_run"),
        "route-pack-result.example.json": ("state", "not_run"),
        "semantic-equivalence-result.example.json": ("state", "not_run"),
    }
    for template_name, (field, expected) in fail_closed_templates.items():
        try:
            if load_json(root / "templates" / template_name).get(field) != expected:
                errors.append(f"template overclaims external state: {template_name}")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"template state cannot be loaded: {template_name}: {exc}")
    try:
        runner_template = load_json(root / "templates" / "runner-attestation.example.json")
        if runner_template.get("posture", {}).get("status") != "not_run":
            errors.append("runner attestation template overclaims trusted posture")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"runner template state cannot be loaded: {exc}")
    try:
        normalization = load_json(root / "NORMALIZATION.json")
        source_digest = normalization.get("source_tree_sha256")
        if normalization.get("external_evidence_status") != "NOT_RUN":
            errors.append("normalization record overclaims external evidence")
        if not isinstance(source_digest, str) or re.fullmatch(r"[0-9a-f]{64}", source_digest) is None:
            errors.append("normalization source digest is invalid")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"normalization record is invalid: {exc}")

    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    batches = [expected_batch] if expected_batch is not None else EXPECTED_BATCHES
    print(f"PASS: {len(selected)} Skills validated across Batches {batches[0]}-{batches[-1]}")
    print("PASS: immutable inventory, DAG, contracts, interfaces, schemas, examples, and NOT_RUN boundary")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--batch", type=int)
    arguments = parser.parse_args()
    raise SystemExit(validate(Path(arguments.root).resolve(), arguments.batch))
