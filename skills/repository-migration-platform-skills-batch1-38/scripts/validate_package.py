#!/usr/bin/env python3
"""Conservative structural and executable validation for the Skill package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CHECKSUM_PATH = ROOT / "CHECKSUMS.sha256"
REQUIRED_BATCH_SECTIONS = (
    "## Contract Metadata",
    "## Objective",
    "## Required Inputs",
    "## Required Outputs",
    "## Workflow",
    "## Required Tests",
    "## Verification Gate",
    "## Stop and Escalate",
    "## Executable Runtime",
    "## Definition of Done",
)
REQUIRED_MASTER_SECTIONS = (
    "## Contract Metadata",
    "## Objective",
    "## Workflow",
    "## Executable Runtime",
    "## Definition of Done",
)
EXCLUDED_CHECKSUM_PARTS = {"__pycache__", ".git"}


def validate_instance(value: Any, schema: dict[str, Any], location: str, errors: list[str]) -> None:
    expected_type = schema.get("type")
    type_matches = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }
    if expected_type in type_matches and not type_matches[expected_type]:
        errors.append(f"schema validation failed at {location}: expected {expected_type}")
        return
    if "const" in schema and value != schema["const"]:
        errors.append(f"schema validation failed at {location}: value differs from const")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"schema validation failed at {location}: value is outside enum")
    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"schema validation failed at {location}: missing {key}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"schema validation failed at {location}: unexpected {key}")
        for key, child in value.items():
            if key in properties and isinstance(properties[key], dict):
                validate_instance(child, properties[key], f"{location}.{key}", errors)
    elif isinstance(value, list):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            errors.append(f"schema validation failed at {location}: too few items")
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            errors.append(f"schema validation failed at {location}: too many items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, child in enumerate(value):
                validate_instance(child, item_schema, f"{location}[{index}]", errors)
    elif isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            errors.append(f"schema validation failed at {location}: string is too short")
        if isinstance(schema.get("pattern"), str) and not re.search(schema["pattern"], value):
            errors.append(f"schema validation failed at {location}: pattern mismatch")
    elif isinstance(value, int) and not isinstance(value, bool):
        if isinstance(schema.get("minimum"), int) and value < schema["minimum"]:
            errors.append(f"schema validation failed at {location}: below minimum")
        if isinstance(schema.get("maximum"), int) and value > schema["maximum"]:
            errors.append(f"schema validation failed at {location}: above maximum")


def read_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid JSON {path.relative_to(ROOT)}: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"JSON root must be an object: {path.relative_to(ROOT)}")
        return None
    return value


def frontmatter(text: str, path: Path, errors: list[str]) -> dict[str, str] | None:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        errors.append(f"frontmatter missing: {path.relative_to(ROOT)}")
        return None
    block = match.group(1)
    top_level_keys = re.findall(r"^([a-zA-Z0-9_-]+):", block, re.M)
    if top_level_keys != ["name", "description"]:
        errors.append(f"frontmatter must contain only name and description: {path.relative_to(ROOT)}")
        return None
    name_match = re.search(r"^name:\s*(\S.*?)\s*$", block, re.M)
    description_match = re.search(r"^description:\s*(.*)$", block, re.M)
    if not name_match or not description_match:
        errors.append(f"name or description missing: {path.relative_to(ROOT)}")
        return None
    description = block[description_match.end():].strip() if description_match.group(1).strip() in {">", ">-", "|", "|-"} else description_match.group(1).strip()
    return {"name": name_match.group(1).strip(), "description": description}


def validate_dependency_dag(entries: list[dict[str, Any]], errors: list[str]) -> None:
    by_batch = {entry["batch"]: entry for entry in entries if entry.get("batch") is not None}
    if set(by_batch) != set(range(1, 39)):
        errors.append("manifest must own exactly Batch 1 through Batch 38")
        return
    for batch, entry in by_batch.items():
        dependencies = entry.get("dependencies")
        if not isinstance(dependencies, list) or any(dep not in by_batch for dep in dependencies):
            errors.append(f"Batch {batch} has invalid dependencies")
    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(batch: int, trail: list[int]) -> None:
        if batch in visiting:
            errors.append("dependency cycle: " + " -> ".join(map(str, [*trail, batch])))
            return
        if batch in visited:
            return
        visiting.add(batch)
        for dependency in by_batch[batch].get("dependencies", []):
            visit(dependency, [*trail, batch])
        visiting.remove(batch)
        visited.add(batch)

    for number in range(1, 39):
        visit(number, [])


def validate_agent_interface(directory: Path, name: str, errors: list[str]) -> None:
    path = directory / "agents" / "openai.yaml"
    if not path.is_file():
        errors.append(f"agents/openai.yaml missing: {directory.relative_to(ROOT)}")
        return
    text = path.read_text(encoding="utf-8")
    for field in ("display_name", "short_description", "default_prompt"):
        if not re.search(rf"^\s+{field}:\s+\".+\"\s*$", text, re.M):
            errors.append(f"{field} missing or unquoted: {path.relative_to(ROOT)}")
    if f"${name}" not in text:
        errors.append(f"default_prompt must mention ${name}: {path.relative_to(ROOT)}")
    short = re.search(r'^\s+short_description:\s+"(.*)"\s*$', text, re.M)
    if short and not 25 <= len(short.group(1)) <= 64:
        errors.append(f"short_description must be 25-64 characters: {path.relative_to(ROOT)}")


def validate_skills(manifest: dict[str, Any], errors: list[str]) -> None:
    entries = manifest.get("skills")
    if not isinstance(entries, list) or len(entries) != 39:
        errors.append("manifest must contain 39 installable Skills")
        return
    names: set[str] = set()
    paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("manifest Skill entry must be an object")
            continue
        name = entry.get("name")
        relative = entry.get("path")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9-]{1,64}", name):
            errors.append(f"invalid Skill name: {name!r}")
            continue
        if name in names:
            errors.append(f"duplicate Skill name: {name}")
        names.add(name)
        if not isinstance(relative, str) or relative in paths:
            errors.append(f"invalid or duplicate Skill path: {relative!r}")
            continue
        paths.add(relative)
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"Skill path missing: {relative}")
            continue
        if path.parent.name != name:
            errors.append(f"Skill directory/name mismatch: {relative}")
        text = path.read_text(encoding="utf-8")
        metadata = frontmatter(text, path, errors)
        if metadata:
            if metadata["name"] != name:
                errors.append(f"frontmatter name mismatch: {relative}")
            if "Use when" not in metadata["description"]:
                errors.append(f"description lacks trigger context: {relative}")
        required = REQUIRED_MASTER_SECTIONS if entry.get("batch") is None else REQUIRED_BATCH_SECTIONS
        for heading in required:
            if heading not in text:
                errors.append(f"{heading} missing: {relative}")
        if entry.get("batch") is not None:
            batch = entry["batch"]
            if f"prepare --batch {batch}" not in text or f"gate --workspace \"$EVIDENCE_WORKSPACE\" --batch {batch}" not in text:
                errors.append(f"Batch runtime commands missing: {relative}")
        elif "prepare-all" not in text or "gate-all" not in text:
            errors.append("master runtime commands missing")
        validate_agent_interface(path.parent, name, errors)
    if manifest.get("batch_skill_count") != 38 or manifest.get("installable_skill_count") != 39:
        errors.append("manifest Skill counts are invalid")
    validate_dependency_dag(entries, errors)


def validate_json_assets(errors: list[str]) -> None:
    schemas = sorted((ROOT / "schemas").glob("*.json"))
    templates = sorted((ROOT / "templates").glob("*.json"))
    required_schemas = {
        "batch-completion-report.schema.json", "invocation.schema.json", "evidence-record.schema.json",
        "verification-record.schema.json", "typed-evidence-envelope.schema.json", "execution-plan.schema.json",
        "gate-result.schema.json", "certificate.schema.json", "trust-policy.schema.json",
        "actor-trust-store.schema.json", "oracle-registry.schema.json",
        "domain-execution-result.schema.json",
        "domain-executor-registry.schema.json",
        "real-toolchain-e2e-report.schema.json",
    }
    if required_schemas - {path.name for path in schemas}:
        errors.append(f"schemas missing: {sorted(required_schemas - {path.name for path in schemas})}")
    for path in [*schemas, *templates]:
        payload = read_json(path, errors)
        if payload is None:
            continue
        if path.parent.name == "schemas":
            if payload.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                errors.append(f"schema draft missing: {path.relative_to(ROOT)}")
            if payload.get("type") != "object":
                errors.append(f"schema root type must be object: {path.relative_to(ROOT)}")
    example = read_json(ROOT / "templates" / "completion-report.example.json", errors)
    schema = read_json(ROOT / "schemas" / "batch-completion-report.schema.json", errors)
    if example and schema:
        validate_instance(example, schema, "templates/completion-report.example.json", errors)
    trust_policy = read_json(ROOT / "trust-policy.json", errors)
    trust_schema = read_json(ROOT / "schemas" / "trust-policy.schema.json", errors)
    if trust_policy and trust_schema:
        validate_instance(trust_policy, trust_schema, "trust-policy.json", errors)
        if trust_policy.get("certification_enabled") is not False or trust_policy.get("keys") != []:
            errors.append("distributed trust policy must keep CERTIFIED disabled and contain no local trust keys")


def validate_runtime(errors: list[str]) -> None:
    scripts = [
        ROOT / "scripts" / "migration_platform.py", ROOT / "scripts" / "transaction_store.py",
        ROOT / "scripts" / "sync_skill_interfaces.py", ROOT / "scripts" / "validate_package.py",
        ROOT / "scripts" / "actor_trust.py", ROOT / "scripts" / "oracle_registry.py",
        ROOT / "scripts" / "build_oracle_registry.py",
        ROOT / "scripts" / "domain_executors.py", ROOT / "scripts" / "build_domain_executor_registry.py",
    ]
    for script in scripts:
        if not script.is_file():
            errors.append(f"runtime script missing: {script.relative_to(ROOT)}")
            continue
        try:
            compile(script.read_text(encoding="utf-8"), str(script), "exec")
        except SyntaxError as exc:
            errors.append(f"Python compile failed for {script.relative_to(ROOT)}: {exc}")
    for builder in (ROOT / "scripts" / "build_oracle_registry.py", ROOT / "scripts" / "build_domain_executor_registry.py"):
        if builder.is_file():
            completed = subprocess.run([sys.executable, str(builder), "--check"], check=False, capture_output=True, text=True)
            if completed.returncode:
                errors.append(f"generated registry is stale: {builder.name}: {completed.stdout.strip()} {completed.stderr.strip()}")
    runtime = ROOT / "scripts" / "migration_platform.py"
    if runtime.is_file():
        completed = subprocess.run([sys.executable, str(runtime), "catalog"], check=False, capture_output=True, text=True)
        try:
            catalog = json.loads(completed.stdout)
        except json.JSONDecodeError:
            catalog = {}
        if completed.returncode != 0 or len(catalog.get("batches", [])) != 38:
            errors.append("runtime catalog must expose exactly 38 executable Batch profiles")
        elif catalog.get("runtime_version") != "2.0.0" or any(item.get("maximum_local_decision") != "LOCAL_TOOLKIT_PASS" for item in catalog["batches"]):
            errors.append("runtime catalog version or local decision ceiling is invalid")
    try:
        oracle_module = __import__("oracle_registry")
        oracle_registry = oracle_module.OracleRegistry.load()
        if len(oracle_registry.by_claim) != 347:
            errors.append("Claim Oracle registry coverage is incomplete")
    except (ImportError, OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Claim Oracle registry is invalid: {exc}")
    try:
        domain_module = __import__("domain_executors")
        executor_registry = domain_module.ExecutorRegistry.load()
        if sorted(executor_registry.by_batch) != list(range(1, 39)):
            errors.append("domain-executor registry coverage is incomplete")
    except (ImportError, OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"domain-executor registry is invalid: {exc}")


def validate_secret_hygiene(errors: list[str]) -> None:
    private_key = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
    credential = re.compile(r"(?i)(?:password|api[_-]?key|secret)\s*[:=]\s*[\"']?[A-Za-z0-9+/=_-]{24,}")
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".yaml", ".yml", ".py", ".sh", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if private_key.search(text) or credential.search(text):
            errors.append(f"possible plaintext secret: {path.relative_to(ROOT)}")


def checksum_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path == CHECKSUM_PATH or path.name == ".DS_Store" or path.suffix == ".pyc":
            continue
        if any(part in EXCLUDED_CHECKSUM_PARTS for part in path.relative_to(ROOT).parts):
            continue
        files.append(path)
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def expected_checksums() -> str:
    lines = []
    for path in checksum_files():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(ROOT).as_posix()}")
    return "\n".join(lines) + "\n"


def validate_checksums(errors: list[str], write: bool, skip: bool) -> None:
    expected = expected_checksums()
    if write:
        CHECKSUM_PATH.write_text(expected, encoding="utf-8")
        return
    if skip:
        return
    try:
        current = CHECKSUM_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"checksum manifest missing: {exc}")
        return
    if current != expected:
        errors.append("CHECKSUMS.sha256 is stale; run validate_package.py --write-checksums after review")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-checksums", action="store_true")
    parser.add_argument("--skip-checksums", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []
    manifest = read_json(ROOT / "manifest.json", errors)
    if manifest:
        validate_skills(manifest, errors)
    validate_json_assets(errors)
    validate_runtime(errors)
    validate_secret_hygiene(errors)
    validate_checksums(errors, args.write_checksums, args.skip_checksums)
    if errors:
        print("FAIL")
        for error in errors:
            print("-", error)
        return 1
    print("PASS: 39 Skill interfaces and 38 executable Batch profiles validated")
    print("PASS: dependency DAG, schemas, transactional runtime, disabled certification trust, checksums, and secret hygiene validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
