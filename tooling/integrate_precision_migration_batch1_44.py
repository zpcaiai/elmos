#!/usr/bin/env python3
"""Install the Precision Migration B01-B44 contracts into the ELMOS runtime.

The submitted package is immutable source material.  This importer gives every
source Skill a collision-free repository identity, an invocable Codex
interface, and a provenance-bound registry entry.  It deliberately does not
turn static validation into migration, production, or certification evidence.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.precision_migration.contracts import compile_contract

SOURCE = ROOT / "skills" / "precision-migration-skills-batch-01-44"
RUNTIME_ROOT = ROOT / "agent-skills" / "runtime"
WORKSPACE_SKILL_ROOT = ROOT / ".agents" / "skills"
DOC_ROOT = ROOT / "docs" / "precision-migration-b01-44"
INSTALL_MANIFEST = DOC_ROOT / "installed-manifest.json"
ADAPTER_REGISTRY = DOC_ROOT / "adapter-registry.json"
EXECUTABLE_CONTRACTS = DOC_ROOT / "executable-contracts.json"
WEB_CATALOG = (
    ROOT / "apps" / "web-console" / "app" / "lib" / "precisionMigrationCatalog.generated.ts"
)
GENERATOR = Path(
    "/Users/stephen/.codex/skills/.system/skill-creator/scripts/generate_openai_yaml.py"
)

NAMESPACE = "precision-migration-b01-44"
EXPECTED_BATCHES = 44
EXPECTED_CHILD_SKILLS = 587
EXPECTED_ORCHESTRATORS = 45
EXPECTED_RUNTIME_SKILLS = EXPECTED_CHILD_SKILLS + EXPECTED_ORCHESTRATORS
STATUS_VALUES = [
    "PROVED",
    "VERIFIED",
    "CONDITIONALLY_VERIFIED",
    "REQUIRES_ADAPTER",
    "REQUIRES_HUMAN_REVIEW",
    "UNSUPPORTED",
    "FAILED",
]
MATURITY_VALUES = [
    "SPEC_ONLY",
    "INSTALLED",
    "ADAPTER_DECLARED",
    "ADAPTER_CONTRACT_PASSED",
    "LOCAL_EXECUTED",
    "HOLDOUT_PASSED",
    "EXTERNAL_VERIFIED",
    "CERTIFIED",
]


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_digest(root: Path) -> str:
    value = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        value.update(path.relative_to(root).as_posix().encode("utf-8"))
        value.update(b"\0")
        value.update(path.read_bytes())
        value.update(b"\0")
    return value.hexdigest()


def load_generator() -> Callable[..., Any]:
    if not GENERATOR.is_file():
        from skill_creator_tools import write_openai_yaml

        return write_openai_yaml
    spec = importlib.util.spec_from_file_location(
        "elmos_precision_migration_openai_yaml", GENERATOR
    )
    if spec is None or spec.loader is None:
        fail(f"cannot load Skill interface generator: {GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.write_openai_yaml


def frontmatter(text: str, source: Path) -> tuple[dict[str, Any], str]:
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if match is None:
        fail(f"Skill has invalid frontmatter: {source}")
    try:
        metadata = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        fail(f"Skill has invalid YAML frontmatter: {source}: {exc}")
    if not isinstance(metadata, dict):
        fail(f"Skill frontmatter is not an object: {source}")
    name = metadata.get("name")
    description = metadata.get("description")
    if not isinstance(name, str) or not isinstance(description, str):
        fail(f"Skill frontmatter lacks name or description: {source}")
    return metadata, match.group(2)


def runtime_name(source_name: str, batch: int | None, kind: str) -> str:
    if kind == "global-orchestrator":
        candidate = "pm-precision-migration-orchestrator"
    elif kind == "batch-orchestrator":
        if batch is None:
            fail(f"batch orchestrator lacks a Batch: {source_name}")
        slug = re.sub(r"^batch-\d{2}-", "", source_name)
        candidate = f"pm-b{batch:02d}-{slug}"
    else:
        if batch is None:
            fail(f"child Skill lacks a Batch: {source_name}")
        candidate = f"pm-b{batch:02d}-{source_name}"
    if len(candidate) <= 64:
        return candidate
    suffix = sha256(f"{NAMESPACE}:{source_name}".encode())[:8]
    return f"{candidate[:55].rstrip('-')}-{suffix}"


def binding_for_record(batch: int | None, source_name: str, kind: str) -> dict[str, Any]:
    secrets_permission = "deny"
    if batch is None:
        adapter = "precision-migration-orchestrator"
        surfaces = ["scripts/precision_migration/runtime.py", "scripts/precision_migration/adapters.py"]
    elif batch <= 4:
        adapter = "assessment-and-target-planning"
        surfaces = ["engines/project-synthesis-engine", "modules/product-roadmap-governance"]
    elif batch <= 13:
        adapter = "semantic-recovery-and-ir"
        surfaces = ["engines/composite-engine", "engines/polyglot-route-engine"]
    elif batch <= 16:
        adapter = "directed-backend-route"
        surfaces = ["engines/polyglot-route-engine", "scripts/batch29"]
    elif batch <= 18:
        adapter = "frontend-client-route"
        surfaces = ["engines/frontend-client-engine", "scripts/batch32"]
    elif batch <= 27:
        adapter = "database-and-data-route"
        surfaces = [
            "engines/database-data-engine",
            "engines/sql-dialect-engine",
            "scripts/batch31",
        ]
    elif batch <= 32:
        adapter = "differential-test-and-repair"
        surfaces = ["engines/test-quality-engine", "scripts/batch35"]
    elif batch <= 35:
        adapter = "formal-and-advanced-verification"
        surfaces = ["scripts/batch35", "schemas/batch35"]
    elif batch <= 37:
        adapter = "model-routing-and-agent-harness"
        surfaces = ["engines/ai-platform-engine", "modules/secure-execution-plane"]
    elif batch <= 40:
        adapter = "skill-and-project-synthesis"
        surfaces = ["engines/project-synthesis-engine", "apps/control-plane"]
    elif batch == 41:
        adapter = "evidence-release-gate"
        surfaces = ["scripts/precision_migration/runtime.py", "modules/evidence-assurance-fabric"]
    elif batch == 42:
        adapter = "shadow-canary-cutover"
        surfaces = ["engines/infrastructure-engine", "engines/operations-sre-itsm-engine"]
    elif batch == 43:
        adapter = "continuous-modernization-learning"
        surfaces = ["engines/ai-platform-engine", "engines/software-delivery-platform-engine"]
    else:
        adapter = "enterprise-private-commercialization"
        surfaces = ["apps/control-plane", "apps/commercial-api"]
    route_key = source_name.removesuffix("-direction-pack")
    route_path = ROOT / "routes" / route_key / "route.json"
    if kind in {"global-orchestrator", "batch-orchestrator"}:
        handler_id = "orchestrator-plan-v1"
        handler_entrypoint = "scripts.precision_migration.adapters:execute_orchestrator_plan"
        supported_modes = ["assess"]
    elif source_name == "repository-modernization-assessment":
        handler_id = "repository-assessment-v1"
        handler_entrypoint = "scripts.precision_migration.adapters:execute_repository_assessment"
        supported_modes = ["assess"]
        surfaces = [*surfaces, "scripts/precision_migration/adapters.py"]
    elif batch == 16 and route_path.is_file():
        handler_id = f"batch29-route-executor-v1:{route_key}"
        handler_entrypoint = "scripts.precision_migration.adapters:execute_batch29_route"
        supported_modes = ["transform", "validate", "certify"]
        surfaces = [*surfaces, f"routes/{route_key}/route.json"]
    elif batch == 41:
        b41_functions = {
            "evidence-manifest": "execute_evidence_manifest",
            "conversion-provenance": "execute_conversion_provenance",
            "rule-proof-certificate": "execute_rule_proof_certificate",
            "module-equivalence-certificate": "execute_module_equivalence_certificate",
            "runtime-evidence-package": "execute_runtime_evidence_package",
            "semantic-loss-report": "execute_semantic_loss_report",
            "unresolved-obligation-report": "execute_unresolved_obligation_report",
            "release-gate-engine": "execute_release_gate",
            "correctness-level-classifier": "execute_correctness_classifier",
            "certificate-signing": "execute_certificate_signing",
        }
        function = b41_functions[source_name]
        handler_id = f"b41-{source_name}-v1"
        handler_entrypoint = f"scripts.precision_migration.b41:{function}"
        supported_modes = ["validate", "certify"]
        surfaces = [*surfaces, "scripts/precision_migration/trust.py", "scripts/precision_migration/b41.py"]
        if source_name == "certificate-signing":
            secrets_permission = "secret-reference-only"
    elif batch == 42:
        b42_functions = {
            "production-shadow-run": "execute_production_shadow_run",
            "live-event-replay": "execute_live_event_replay",
            "side-effect-suppression": "execute_side_effect_suppression",
            "dual-write-validation": "execute_dual_write_validation",
            "canary-traffic-planner": "execute_canary_traffic_planner",
            "progressive-cutover": "execute_progressive_cutover",
            "automatic-rollback": "execute_automatic_rollback",
            "migration-wave-planner": "execute_migration_wave_planner",
            "strangler-routing": "execute_strangler_routing",
            "post-cutover-monitoring": "execute_post_cutover_monitoring",
        }
        function = b42_functions[source_name]
        handler_id = f"b42-{source_name}-v1"
        handler_entrypoint = f"scripts.precision_migration.b42:{function}"
        supported_modes = ["validate", "repair", "certify"]
        surfaces = [*surfaces, "scripts/precision_migration/b42.py"]
    else:
        handler_id = f"domain-skill-v2:{source_name}"
        handler_entrypoint = "scripts.precision_migration.domain:execute_domain_skill"
        supported_modes = modes_for_batch(batch)
        surfaces = [*surfaces, "scripts/precision_migration/contracts.py", "scripts/precision_migration/domain.py"]
    missing = [path for path in surfaces if not (ROOT / path).exists()]
    declared = not missing
    return {
        "adapter": adapter,
        "binding_state": "DECLARED" if declared else "UNAVAILABLE",
        "handler_id": handler_id,
        "handler_entrypoint": handler_entrypoint,
        "contract_version": "1.0.0",
        "supported_modes": supported_modes,
        "timeout_seconds": 120,
        "permissions": {
            "source": "read-only",
            "output": "dedicated-directory",
            "network": "deny",
            "secrets": secrets_permission,
            "shell": "deny-repository-content",
        },
        "repository_surfaces": surfaces,
        "missing_surfaces": missing,
        "evidence_boundary": (
            "DECLARED means an allowlisted handler contract exists; it is not execution, "
            "holdout, external, customer, production, or certification evidence."
        ),
    }


def modes_for_batch(batch: int | None) -> list[str]:
    if batch is None:
        return ["assess"]
    if batch <= 4:
        return ["assess"]
    if batch <= 10:
        return ["assess", "validate"]
    if batch <= 27:
        return ["transform", "validate", "repair"]
    if batch <= 35:
        return ["validate", "repair", "certify"]
    if batch <= 40:
        return ["assess", "transform", "validate"]
    if batch == 41:
        return ["validate", "certify"]
    if batch == 42:
        return ["validate", "repair", "certify"]
    if batch == 43:
        return ["assess", "validate", "repair"]
    return ["assess", "validate", "certify"]


def source_records() -> list[dict[str, Any]]:
    if not SOURCE.is_dir():
        fail(f"source package is missing: {SOURCE}")
    catalog_path = SOURCE / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(catalog, list) or len(catalog) != EXPECTED_CHILD_SKILLS:
        fail(f"source catalog must contain {EXPECTED_CHILD_SKILLS} child Skills")
    records: list[dict[str, Any]] = []
    seen_source: set[str] = set()
    seen_runtime: set[str] = set()
    for item in catalog:
        if not isinstance(item, dict):
            fail("source catalog contains a non-object entry")
        batch = item.get("batch")
        source_name = item.get("name")
        relative = item.get("path")
        if not isinstance(batch, int) or not 1 <= batch <= EXPECTED_BATCHES:
            fail(f"source catalog contains invalid Batch: {item}")
        if not isinstance(source_name, str) or not isinstance(relative, str):
            fail(f"source catalog contains invalid identity: {item}")
        source_path = SOURCE / relative
        if not source_path.is_file():
            fail(f"source Skill is missing: {source_path}")
        metadata, _ = frontmatter(source_path.read_text(encoding="utf-8"), source_path)
        if metadata["name"] != source_name:
            fail(f"source catalog/frontmatter mismatch: {source_name}")
        batch_slug = str(item.get("batch_slug", ""))
        record = {
            "kind": "skill",
            "batch": batch,
            "batch_slug": batch_slug,
            "batch_title": item.get("batch_title"),
            "phase": item.get("phase"),
            "source_name": source_name,
            "description": metadata["description"],
            "source_path": relative,
        }
        if source_name in seen_source:
            fail(f"duplicate source child Skill identity: {source_name}")
        records.append(record)
        seen_source.add(source_name)

    batch_dirs = sorted((SOURCE / "batches").glob("batch-*"))
    if len(batch_dirs) != EXPECTED_BATCHES:
        fail(f"source package must contain {EXPECTED_BATCHES} Batch directories")
    batch_catalog: dict[int, dict[str, Any]] = {}
    for directory in batch_dirs:
        catalog_yaml = yaml.safe_load((directory / "catalog.yaml").read_text(encoding="utf-8"))
        if not isinstance(catalog_yaml, dict) or not isinstance(catalog_yaml.get("batch"), int):
            fail(f"invalid Batch catalog: {directory / 'catalog.yaml'}")
        batch = int(catalog_yaml["batch"])
        batch_catalog[batch] = catalog_yaml
        source_path = directory / "SKILL.md"
        metadata, _ = frontmatter(source_path.read_text(encoding="utf-8"), source_path)
        records.append(
            {
                "kind": "batch-orchestrator",
                "batch": batch,
                "batch_slug": catalog_yaml.get("slug"),
                "batch_title": catalog_yaml.get("title"),
                "phase": catalog_yaml.get("phase"),
                "source_name": metadata["name"],
                "description": metadata["description"],
                "source_path": source_path.relative_to(SOURCE).as_posix(),
            }
        )

    meta_path = SOURCE / "meta" / "precision-migration-orchestrator" / "SKILL.md"
    metadata, _ = frontmatter(meta_path.read_text(encoding="utf-8"), meta_path)
    records.append(
        {
            "kind": "global-orchestrator",
            "batch": None,
            "batch_slug": None,
            "batch_title": "Precision Migration B01-B44",
            "phase": "Global routing and evidence governance",
            "source_name": metadata["name"],
            "description": metadata["description"],
            "source_path": meta_path.relative_to(SOURCE).as_posix(),
        }
    )

    if len(records) != EXPECTED_RUNTIME_SKILLS:
        fail(f"expected {EXPECTED_RUNTIME_SKILLS} runtime records, found {len(records)}")
    for record in records:
        source_name = str(record["source_name"])
        if source_name in seen_source and record["kind"] != "skill":
            fail(f"source identity collision: {source_name}")
        seen_source.add(source_name)
        name = runtime_name(source_name, record["batch"], str(record["kind"]))
        if not re.fullmatch(r"[a-z0-9-]{1,64}", name):
            fail(f"invalid runtime name: {name}")
        if name in seen_runtime:
            fail(f"runtime name collision: {name}")
        seen_runtime.add(name)
        record["name"] = name
        record["binding"] = binding_for_record(
            record["batch"], str(record["source_name"]), str(record["kind"])
        )

    child_by_batch = Counter(
        int(record["batch"]) for record in records if record["kind"] == "skill"
    )
    if set(child_by_batch) != set(range(1, EXPECTED_BATCHES + 1)):
        fail("one or more Batches have no child Skills")
    for batch, catalog_yaml in batch_catalog.items():
        skills = catalog_yaml.get("skills")
        if not isinstance(skills, list) or len(skills) != child_by_batch[batch]:
            fail(f"Batch {batch:02d} catalog count does not match catalog.json")
    return sorted(
        records,
        key=lambda item: (
            -1 if item["batch"] is None else int(item["batch"]),
            {"global-orchestrator": 0, "batch-orchestrator": 1, "skill": 2}[item["kind"]],
            str(item["source_name"]),
        ),
    )


def normalized_skill(record: dict[str, Any], all_records: list[dict[str, Any]]) -> str:
    source_path = SOURCE / str(record["source_path"])
    metadata, body = frontmatter(source_path.read_text(encoding="utf-8"), source_path)
    description = str(metadata["description"]).replace("<", "[").replace(">", "]")
    trigger = (
        f" Precision Migration B{record['batch']:02d} contract; use for this exact "
        "assessment, transformation, validation, repair, evidence, or cutover scope."
        if record["batch"] is not None
        else " Use to route Precision Migration work across B01-B44 with fail-closed evidence."
    )
    description = (description.rstrip("。. ") + "." + trigger).strip()
    if len(description) > 1024:
        fail(f"normalized description exceeds 1024 characters: {record['name']}")

    alias_by_source = {str(item["source_name"]): str(item["name"]) for item in all_records}
    if record["kind"] == "batch-orchestrator":
        for source_name, alias in alias_by_source.items():
            body = body.replace(
                f"skills/{source_name}/SKILL.md", f"../{alias}/SKILL.md"
            )
    binding = record["binding"]
    batch_label = "global" if record["batch"] is None else f"B{record['batch']:02d}"
    runtime_block = (
        "\n## ELMOS runtime binding\n\n"
        f"- Invoke this repository Skill as `${record['name']}`.\n"
        f"- Immutable source identity: `{record['source_name']}` in `{NAMESPACE}` ({batch_label}).\n"
        f"- Runtime adapter: `{binding['adapter']}`; binding state: "
        f"`{binding.get('binding_state', 'AVAILABLE')}`.\n"
        "- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan "
        f"--skill {record['name']}`.\n"
        "- Static installation and local evidence evaluation never substitute for exact "
        "source/target execution, independent review, customer acceptance, production "
        "operation, or certification; missing evidence stays `NOT_RUN`.\n"
    )
    heading = re.search(r"(?m)^# .+$", body)
    if heading is None:
        body = runtime_block.lstrip() + "\n" + body.lstrip()
    else:
        insert_at = heading.end()
        body = body[:insert_at] + runtime_block + body[insert_at:]
    return (
        "---\n"
        f"name: {record['name']}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n\n"
        + body.lstrip()
    )


def write_interface(
    directory: Path, record: dict[str, Any], write_openai_yaml: Callable[..., Any]
) -> None:
    batch_label = "B01-B44" if record["batch"] is None else f"B{record['batch']:02d}"
    source_title = str(record["source_name"]).replace("-", " ").title()
    display = f"Precision Migration {batch_label}: {source_title}"[:96].rstrip()
    short = f"Run Precision Migration {batch_label} with evidence controls"
    prompt = (
        f"Use ${record['name']} to execute this Precision Migration contract with "
        "fail-closed evidence."
    )
    with contextlib.redirect_stdout(io.StringIO()):
        output = write_openai_yaml(
            directory,
            str(record["name"]),
            [
                f"display_name={display}",
                f"short_description={short}",
                f"default_prompt={prompt}",
            ],
        )
    if output is None:
        fail(f"cannot generate agents/openai.yaml: {record['name']}")


def render_web_catalog(manifest: dict[str, Any]) -> str:
    payload = {
        "namespace": NAMESPACE,
        "batchCount": manifest["batch_count"],
        "childSkillCount": manifest["child_skill_count"],
        "orchestratorCount": manifest["orchestrator_count"],
        "runtimeSkillCount": manifest["runtime_skill_count"],
        "workspaceSkillCount": manifest["workspace_skill_count"],
        "structuralStatus": manifest["structural_status"],
        "runtimeProtocolStatus": manifest["runtime_protocol_status"],
        "maturityCounts": manifest["maturity_counts"],
        "externalEvidenceStatus": manifest["external_evidence_status"],
        "productionCertification": manifest["production_certification"],
    }
    phases: dict[str, dict[str, Any]] = {}
    for record in manifest["skills"]:
        if record["kind"] != "skill":
            continue
        phase = str(record["phase"])
        group = phases.setdefault(
            phase,
            {"phase": phase, "batches": set(), "skillCount": 0, "adapterDeclaredCount": 0},
        )
        group["batches"].add(int(record["batch"]))
        group["skillCount"] += 1
        if record["maturity"] == "ADAPTER_DECLARED":
            group["adapterDeclaredCount"] += 1
    rendered_phases = []
    for value in phases.values():
        batches = sorted(value["batches"])
        rendered_phases.append(
            {
                "phase": value["phase"],
                "batchRange": (
                    f"B{batches[0]:02d}" if len(batches) == 1 else f"B{batches[0]:02d}-B{batches[-1]:02d}"
                ),
                "skillCount": value["skillCount"],
                "adapterDeclaredCount": value["adapterDeclaredCount"],
                "installedOnlyCount": value["skillCount"] - value["adapterDeclaredCount"],
            }
        )
    return (
        "// Generated by tooling/integrate_precision_migration_batch1_44.py.\n"
        "// Do not edit by hand.\n\n"
        f"export const precisionMigrationSummary = {json.dumps(payload, ensure_ascii=False, indent=2)} as const;\n\n"
        f"export const precisionMigrationPhases = {json.dumps(rendered_phases, ensure_ascii=False, indent=2)} as const;\n"
    )


def build_expected(staging_root: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    records = source_records()
    write_openai_yaml = load_generator()
    generated_root = staging_root / "runtime"
    generated_root.mkdir(parents=True)
    installed_records: list[dict[str, Any]] = []
    for record in records:
        destination = generated_root / str(record["name"])
        destination.mkdir()
        skill_text = normalized_skill(record, records)
        (destination / "SKILL.md").write_text(skill_text, encoding="utf-8")
        write_interface(destination, record, write_openai_yaml)
        installed = dict(record)
        installed["source_sha256"] = sha256(
            (SOURCE / str(record["source_path"])).read_bytes()
        )
        installed["installed_path"] = (
            f"agent-skills/runtime/{record['name']}/SKILL.md"
        )
        installed["installed_sha256"] = sha256(
            (destination / "SKILL.md").read_bytes()
        )
        installed["workspace_path"] = f".agents/skills/{record['name']}/SKILL.md"
        installed["workspace_sha256"] = installed["installed_sha256"]
        installed["interface_sha256"] = sha256(
            (destination / "agents" / "openai.yaml").read_bytes()
        )
        if installed["kind"] == "skill" and installed["binding"]["binding_state"] == "DECLARED":
            installed["maturity"] = "LOCAL_EXECUTED"
        else:
            installed["maturity"] = (
                "ADAPTER_DECLARED"
                if installed["binding"]["binding_state"] == "DECLARED"
                else "INSTALLED"
            )
        installed["contract_status"] = "INSTALLED"
        installed["runtime_protocol_status"] = (
            "BOUNDED_LOCAL_EXECUTION" if installed["kind"] == "skill" else "CONTRACT_READY"
        )
        installed["external_evidence_status"] = "NOT_RUN"
        installed_records.append(installed)

    phase_counts: dict[str, int] = defaultdict(int)
    batch_counts: dict[str, int] = defaultdict(int)
    for record in installed_records:
        if record["kind"] == "skill":
            phase_counts[str(record["phase"])] += 1
            batch_counts[f"B{int(record['batch']):02d}"] += 1
    maturity_counts = Counter(str(record["maturity"]) for record in installed_records)
    manifest = {
        "schema_version": 1,
        "namespace": NAMESPACE,
        "source_package": "precision-migration-skills-batch-01-44",
        "source_version": (SOURCE / "VERSION").read_text(encoding="utf-8").strip(),
        "source_package_manifest_sha256": sha256((SOURCE / "manifest.json").read_bytes()),
        "source_tree_sha256": tree_digest(SOURCE),
        "batch_count": EXPECTED_BATCHES,
        "child_skill_count": EXPECTED_CHILD_SKILLS,
        "orchestrator_count": EXPECTED_ORCHESTRATORS,
        "runtime_skill_count": EXPECTED_RUNTIME_SKILLS,
        "workspace_skill_count": EXPECTED_RUNTIME_SKILLS,
        "workspace_installation": "ALL_RUNTIME_SKILLS",
        "workspace_entrypoint": "pm-precision-migration-orchestrator",
        "status_values": STATUS_VALUES,
        "maturity_values": MATURITY_VALUES,
        "maturity_counts": dict(sorted(maturity_counts.items())),
        "batch_counts": dict(sorted(batch_counts.items())),
        "phase_counts": dict(phase_counts),
        "structural_status": "PASS",
        "runtime_protocol_status": "BOUNDED_LOCAL_EXECUTION",
        "external_evidence_status": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "maximum_local_decision": "READY_FOR_EXTERNAL_GATE",
        "completion_boundary": (
            "All source contracts and bounded local handlers are installed and locally executed. "
            "Native toolchain breadth, independent holdout, external review, customer traffic, "
            "and certification require separately verified evidence."
        ),
        "skills": installed_records,
    }
    manifest_path = staging_root / "installed-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    web_path = staging_root / "precisionMigrationCatalog.generated.ts"
    web_path.write_text(render_web_catalog(manifest), encoding="utf-8")
    adapter_registry = {
        "schema_version": 1,
        "namespace": NAMESPACE,
        "source_tree_sha256": manifest["source_tree_sha256"],
        "entries": [
            {
                "skill": record["name"],
                "source_skill": record["source_name"],
                "batch": record["batch"],
                "kind": record["kind"],
                "maturity": record["maturity"],
                **record["binding"],
            }
            for record in installed_records
        ],
    }
    adapter_path = staging_root / "adapter-registry.json"
    adapter_path.write_text(
        json.dumps(adapter_registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    executable_contracts = {
        "schema_version": 1,
        "namespace": NAMESPACE,
        "source_tree_sha256": manifest["source_tree_sha256"],
        "contracts": [
            compile_contract(record, SOURCE / str(record["source_path"]))
            for record in records
            if record["kind"] == "skill"
        ],
    }
    contracts_path = staging_root / "executable-contracts.json"
    contracts_path.write_text(
        json.dumps(executable_contracts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths = {str(record["name"]): generated_root / str(record["name"]) for record in records}
    paths["__manifest__"] = manifest_path
    paths["__web__"] = web_path
    paths["__adapters__"] = adapter_path
    paths["__contracts__"] = contracts_path
    return manifest, paths


def directories_equal(left: Path, right: Path) -> bool:
    left_files = {
        path.relative_to(left).as_posix(): path.read_bytes()
        for path in left.rglob("*")
        if path.is_file()
    }
    right_files = {
        path.relative_to(right).as_posix(): path.read_bytes()
        for path in right.rglob("*")
        if path.is_file()
    }
    return left_files == right_files


def check_install(manifest: dict[str, Any], expected: dict[str, Path]) -> None:
    failures: list[str] = []
    for record in manifest["skills"]:
        name = str(record["name"])
        actual = RUNTIME_ROOT / name
        if not actual.is_dir() or not directories_equal(expected[name], actual):
            failures.append(f"runtime:{name}")
        workspace = WORKSPACE_SKILL_ROOT / name
        if not workspace.is_dir() or not directories_equal(expected[name], workspace):
            failures.append(f"workspace:{name}")
    if not INSTALL_MANIFEST.is_file() or INSTALL_MANIFEST.read_bytes() != expected[
        "__manifest__"
    ].read_bytes():
        failures.append("installed-manifest")
    if not WEB_CATALOG.is_file() or WEB_CATALOG.read_bytes() != expected["__web__"].read_bytes():
        failures.append("web-catalog")
    if not ADAPTER_REGISTRY.is_file() or ADAPTER_REGISTRY.read_bytes() != expected[
        "__adapters__"
    ].read_bytes():
        failures.append("adapter-registry")
    if not EXECUTABLE_CONTRACTS.is_file() or EXECUTABLE_CONTRACTS.read_bytes() != expected[
        "__contracts__"
    ].read_bytes():
        failures.append("executable-contracts")
    if failures:
        fail(f"Precision Migration installation drifted: {failures[:12]} ({len(failures)} total)")
    print(
        json.dumps(
            {
                "status": "PASS",
                "mode": "check",
                "batches": manifest["batch_count"],
                "child_skills": manifest["child_skill_count"],
                "orchestrators": manifest["orchestrator_count"],
                "runtime_skills": manifest["runtime_skill_count"],
                "workspace_skills": manifest["workspace_skill_count"],
                "external_evidence": manifest["external_evidence_status"],
                "production_certification": manifest["production_certification"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def install(manifest: dict[str, Any], expected: dict[str, Path]) -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    WORKSPACE_SKILL_ROOT.mkdir(parents=True, exist_ok=True)
    previous_names: set[str] = set()
    previous_workspace_names: set[str] = set()
    if INSTALL_MANIFEST.is_file():
        previous = json.loads(INSTALL_MANIFEST.read_text(encoding="utf-8"))
        if previous.get("namespace") != NAMESPACE:
            fail(f"refusing to replace foreign installed manifest: {INSTALL_MANIFEST}")
        previous_names = {str(item["name"]) for item in previous.get("skills", [])}
        if previous.get("workspace_installation") == "ALL_RUNTIME_SKILLS":
            previous_workspace_names = set(previous_names)
        elif isinstance(previous.get("workspace_entrypoint"), str):
            previous_workspace_names = {str(previous["workspace_entrypoint"])}
    expected_names = {str(item["name"]) for item in manifest["skills"]}
    for name in sorted(expected_names):
        destination = RUNTIME_ROOT / name
        if destination.exists() and name not in previous_names:
            fail(f"refusing to overwrite unowned Runtime Skill: {destination}")
        workspace = WORKSPACE_SKILL_ROOT / name
        if workspace.exists() and name not in previous_workspace_names:
            fail(f"refusing to overwrite unowned workspace Skill: {workspace}")
    for name in sorted(previous_names - expected_names):
        stale = RUNTIME_ROOT / name
        if stale.exists():
            shutil.rmtree(stale)
    for name in sorted(expected_names):
        destination = RUNTIME_ROOT / name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(expected[name], destination)

    for name in sorted(previous_workspace_names - expected_names):
        stale = WORKSPACE_SKILL_ROOT / name
        if stale.exists():
            shutil.rmtree(stale)
    for name in sorted(expected_names):
        workspace = WORKSPACE_SKILL_ROOT / name
        if workspace.exists():
            shutil.rmtree(workspace)
        shutil.copytree(expected[name], workspace)
    workspace_name = str(manifest["workspace_entrypoint"])
    DOC_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(expected["__manifest__"], INSTALL_MANIFEST)
    shutil.copy2(expected["__adapters__"], ADAPTER_REGISTRY)
    shutil.copy2(expected["__contracts__"], EXECUTABLE_CONTRACTS)
    WEB_CATALOG.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(expected["__web__"], WEB_CATALOG)
    print(
        json.dumps(
            {
                "status": "PASS",
                "mode": "install",
                "runtime_skills": manifest["runtime_skill_count"],
                "workspace_skills": manifest["workspace_skill_count"],
                "workspace_entrypoint": workspace_name,
                "external_evidence": "NOT_RUN",
                "production_certification": "NOT_CERTIFIED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify generated installation")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix=".precision-migration-", dir=ROOT) as temp:
        manifest, expected = build_expected(Path(temp))
        if args.check:
            check_install(manifest, expected)
        else:
            install(manifest, expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
