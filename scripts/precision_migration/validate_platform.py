#!/usr/bin/env python3
"""Validate package identity, 632 installed Skills, schemas, and runtime surfaces."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE = ROOT / "skills" / "precision-migration-skills-batch-01-44"
MANIFEST_PATH = ROOT / "docs" / "precision-migration-b01-44" / "installed-manifest.json"
RUNTIME_ROOT = ROOT / "agent-skills" / "runtime"
WORKSPACE_ROOT = ROOT / ".agents" / "skills"
SCHEMA_ROOT = ROOT / "schemas" / "precision-migration-b01-44"
WEB_CATALOG = ROOT / "apps" / "web-console" / "app" / "lib" / "precisionMigrationCatalog.generated.ts"
ADAPTER_REGISTRY = ROOT / "docs" / "precision-migration-b01-44" / "adapter-registry.json"
EXECUTABLE_CONTRACTS = ROOT / "docs" / "precision-migration-b01-44" / "executable-contracts.json"
TRUST_STORE_EXAMPLE = ROOT / "config" / "precision-migration" / "trust-store.example.json"
TEMPLATE_ROOT = ROOT / "templates" / "precision-migration-b01-44"
VERIFICATION_PACK = ROOT / "verification-packs" / "precision-migration-b01-44-runtime"
OFFICIAL_VALIDATOR = Path(
    "/Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py"
)
EXPECTED_SCHEMAS = {
    "adapter-registry.schema.json",
    "catalog.schema.json",
    "gate-request.schema.json",
    "gate-result.schema.json",
    "job.schema.json",
    "skill-run-request.schema.json",
    "skill-run-result.schema.json",
    "trust-store.schema.json",
}


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_validator() -> Callable[[Path], tuple[bool, str]]:
    if not OFFICIAL_VALIDATOR.is_file():
        sys.path.insert(0, str(ROOT / "tooling"))
        from skill_creator_tools import validate_skill

        return validate_skill
    spec = importlib.util.spec_from_file_location(
        "elmos_precision_migration_validator", OFFICIAL_VALIDATOR
    )
    if spec is None or spec.loader is None:
        fail("cannot load official skill-creator validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_skill


def validate_interface(skill_dir: Path, name: str) -> None:
    interface_path = skill_dir / "agents" / "openai.yaml"
    if not interface_path.is_file():
        fail(f"missing Runtime Skill interface: {name}")
    payload = yaml.safe_load(interface_path.read_text(encoding="utf-8"))
    interface = payload.get("interface") if isinstance(payload, dict) else None
    if not isinstance(interface, dict):
        fail(f"invalid Runtime Skill interface: {name}")
    for key in ("display_name", "short_description", "default_prompt"):
        if not isinstance(interface.get(key), str) or not interface[key].strip():
            fail(f"Runtime Skill interface lacks {key}: {name}")
    if not 25 <= len(interface["short_description"]) <= 64:
        fail(f"Runtime Skill short_description length is invalid: {name}")
    if f"${name}" not in interface["default_prompt"]:
        fail(f"Runtime Skill default_prompt does not invoke its alias: {name}")


def main() -> int:
    subprocess.run([sys.executable, str(SOURCE / "verify_package.py")], cwd=ROOT, check=True)
    subprocess.run(
        [sys.executable, str(ROOT / "tooling" / "integrate_precision_migration_batch1_44.py"), "--check"],
        cwd=ROOT,
        check=True,
    )
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    catalog_schema = json.loads((SCHEMA_ROOT / "catalog.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(catalog_schema).validate(manifest)
    if manifest.get("workspace_skill_count") != 632 or manifest.get("workspace_installation") != "ALL_RUNTIME_SKILLS":
        fail("all 632 Precision Migration Skills must be installed in the Codex workspace discovery root")
    installed_digest = "sha256:" + digest(MANIFEST_PATH)
    source_manifest_digest = "sha256:" + digest(SOURCE / "manifest.json")
    pack = json.loads((VERIFICATION_PACK / "pack.json").read_text(encoding="utf-8"))
    certification = json.loads(
        (VERIFICATION_PACK / "certification" / "certification.json").read_text(encoding="utf-8")
    )
    for label, exact_scope in (
        ("pack", pack.get("scope")),
        ("certification", certification.get("exact_scope")),
    ):
        if not isinstance(exact_scope, dict):
            fail(f"verification {label} exact scope is invalid")
        if exact_scope.get("source_artifact_digest") != source_manifest_digest:
            fail(f"verification {label} source digest drifted")
        if exact_scope.get("target_artifact_digest") != installed_digest:
            fail(f"verification {label} target digest drifted")
    if {path.name for path in SCHEMA_ROOT.glob("*.json")} != EXPECTED_SCHEMAS:
        fail("Precision Migration schema inventory drifted")
    for schema_path in sorted(SCHEMA_ROOT.glob("*.json")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
    skill_request = json.loads(
        (TEMPLATE_ROOT / "skill-run-request.example.json").read_text(encoding="utf-8")
    )
    gate_request = json.loads(
        (TEMPLATE_ROOT / "gate-request.example.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(
        json.loads((SCHEMA_ROOT / "skill-run-request.schema.json").read_text(encoding="utf-8"))
    ).validate(skill_request)
    jsonschema.Draft202012Validator(
        json.loads((SCHEMA_ROOT / "gate-request.schema.json").read_text(encoding="utf-8"))
    ).validate(gate_request)

    validate_skill = load_validator()
    names: set[str] = set()
    sources: set[str] = set()
    kinds: Counter[str] = Counter()
    batches: Counter[int] = Counter()
    invalid_maturity: list[str] = []
    for record in manifest["skills"]:
        name = record["name"]
        source_name = record["source_name"]
        if name in names or source_name in sources:
            fail(f"duplicate installed identity: {name}")
        names.add(name)
        sources.add(source_name)
        kinds[record["kind"]] += 1
        if record["kind"] == "skill":
            batches[int(record["batch"])] += 1
        skill_dir = RUNTIME_ROOT / name
        skill_path = skill_dir / "SKILL.md"
        source_path = SOURCE / record["source_path"]
        if not skill_path.is_file() or not source_path.is_file():
            fail(f"installed or source Skill is missing: {name}")
        if digest(skill_path) != record["installed_sha256"]:
            fail(f"installed Skill digest mismatch: {name}")
        if digest(source_path) != record["source_sha256"]:
            fail(f"source Skill digest mismatch: {name}")
        valid, message = validate_skill(skill_dir)
        if not valid:
            fail(f"skill-creator validation failed for {name}: {message}")
        text = skill_path.read_text(encoding="utf-8")
        front_name = re.search(r"(?m)^name:\s*([^\n]+)$", text)
        if front_name is None or front_name.group(1).strip() != name:
            fail(f"Runtime Skill frontmatter/directory mismatch: {name}")
        validate_interface(skill_dir, name)
        if digest(skill_dir / "agents" / "openai.yaml") != record["interface_sha256"]:
            fail(f"Runtime Skill interface digest mismatch: {name}")
        workspace_dir = WORKSPACE_ROOT / name
        workspace_skill = workspace_dir / "SKILL.md"
        workspace_interface = workspace_dir / "agents" / "openai.yaml"
        if not workspace_skill.is_file() or not workspace_interface.is_file():
            fail(f"workspace-discoverable Skill is missing: {name}")
        if digest(workspace_skill) != record["workspace_sha256"] or workspace_skill.read_bytes() != skill_path.read_bytes():
            fail(f"workspace Skill digest mismatch: {name}")
        if workspace_interface.read_bytes() != (skill_dir / "agents" / "openai.yaml").read_bytes():
            fail(f"workspace Skill interface mismatch: {name}")
        maturity = record.get("maturity")
        state = record["binding"].get("binding_state")
        declared_maturities = {
            "ADAPTER_DECLARED", "ADAPTER_CONTRACT_PASSED", "LOCAL_EXECUTED",
            "HOLDOUT_PASSED", "EXTERNAL_VERIFIED", "CERTIFIED",
        }
        if (state == "DECLARED" and maturity not in declared_maturities) or (
            state != "DECLARED" and maturity in declared_maturities
        ):
            invalid_maturity.append(name)

    if kinds != {"skill": 587, "batch-orchestrator": 44, "global-orchestrator": 1}:
        fail(f"installed kind counts drifted: {dict(kinds)}")
    if set(batches) != set(range(1, 45)) or sum(batches.values()) != 587:
        fail("installed Batch coverage is incomplete")
    if invalid_maturity:
        fail(f"adapter maturity/binding state diverged: {invalid_maturity[:10]}")
    entrypoint = manifest["workspace_entrypoint"]
    workspace_skill = WORKSPACE_ROOT / entrypoint / "SKILL.md"
    runtime_skill = RUNTIME_ROOT / entrypoint / "SKILL.md"
    if not workspace_skill.is_file() or workspace_skill.read_bytes() != runtime_skill.read_bytes():
        fail("workspace orchestrator does not match the installed Runtime Skill")
    if not WEB_CATALOG.is_file():
        fail("Precision Migration web catalog is missing")
    web_text = WEB_CATALOG.read_text(encoding="utf-8")
    if (
        '"runtimeSkillCount": 632' not in web_text
        or '"workspaceSkillCount": 632' not in web_text
        or '"childSkillCount": 587' not in web_text
    ):
        fail("Precision Migration web catalog counts drifted")
    adapter_registry = json.loads(ADAPTER_REGISTRY.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(
        json.loads((SCHEMA_ROOT / "adapter-registry.schema.json").read_text(encoding="utf-8"))
    ).validate(adapter_registry)
    if len(adapter_registry["entries"]) != 632:
        fail("adapter registry coverage is incomplete")
    jsonschema.Draft202012Validator(
        json.loads((SCHEMA_ROOT / "trust-store.schema.json").read_text(encoding="utf-8"))
    ).validate(json.loads(TRUST_STORE_EXAMPLE.read_text(encoding="utf-8")))
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "precision_migration" / "adapters.py"), "validate-registry"],
        cwd=ROOT,
        check=True,
    )

    from scripts.precision_migration.contracts import ContractRegistry
    from scripts.precision_migration.exact import ExactImplementationRegistry
    from scripts.precision_migration.orchestration import OrchestratorRegistry
    from scripts.precision_migration.runtime import Registry, evaluate

    registry = Registry.load()
    contracts = ContractRegistry.load(EXECUTABLE_CONTRACTS)
    if len(contracts.by_skill) != 587 or len(contracts.by_handler) != 587:
        fail("executable contract coverage is incomplete")
    exact_implementations = ExactImplementationRegistry.load()
    orchestrator_implementations = OrchestratorRegistry.load()
    if len(exact_implementations.by_handler) != 536:
        fail("exact per-Skill implementation coverage is incomplete")
    if len(orchestrator_implementations.by_handler) != 45:
        fail("executable orchestrator DAG coverage is incomplete")
    for record in manifest["skills"]:
        if registry.resolve(record["name"])["source_name"] != record["source_name"]:
            fail(f"runtime alias resolution failed: {record['name']}")
        if registry.resolve(record["source_name"])["name"] != record["name"]:
            fail(f"runtime source resolution failed: {record['source_name']}")
    example_result = evaluate(skill_request, registry)
    jsonschema.Draft202012Validator(
        json.loads((SCHEMA_ROOT / "skill-run-result.schema.json").read_text(encoding="utf-8"))
    ).validate(example_result)
    if example_result["status"] not in {"CONDITIONALLY_VERIFIED", "REQUIRES_ADAPTER"}:
        fail("checked-in NOT_RUN example must remain fail-closed")
    print(
        json.dumps(
            {
                "status": "PASS",
                "batches": 44,
                "child_skills": 587,
                "orchestrators": 45,
                "runtime_skills": 632,
                "workspace_skills": 632,
                "schemas": len(EXPECTED_SCHEMAS),
                "adapter_contracts": sum(
                    1 for item in adapter_registry["entries"]
                    if item.get("binding_state") == "DECLARED"
                ),
                "installed_without_adapter": manifest["maturity_counts"].get("INSTALLED", 0),
                "external_evidence": "NOT_RUN",
                "production_certification": "NOT_CERTIFIED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
