#!/usr/bin/env python3
"""Integrate the immutable FRT G01-G30 frontend transformation Skill pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "FRT_G01_G30_Complete_Skills_Pack"
PACKAGE_ROOT = ROOT / "skills" / PACKAGE_NAME
RUNTIME_ROOT = ROOT / "agent-skills" / "runtime"
INSTALL_MANIFEST = ROOT / "docs" / "frt-g01-g30" / "installed-manifest.json"
ENGINE_CATALOG = (
    ROOT
    / "engines"
    / "frontend-client-engine"
    / "src"
    / "frt-catalog.generated.ts"
)
ENGINE_HANDLER_REGISTRY = (
    ROOT
    / "engines"
    / "frontend-client-engine"
    / "src"
    / "frt-handler-registry.generated.ts"
)
COMPILED_CONTRACTS = ROOT / "docs" / "frt-g01-g30" / "compiled-skill-contracts.json"
WEB_CATALOG = (
    ROOT / "apps" / "web-console" / "app" / "lib" / "frtCatalog.generated.ts"
)
EXPECTED_BATCHES = 30
EXPECTED_SKILLS = 472
REQUIRED_SECTIONS = (
    "## Objective",
    "## Workflow",
    "## Verification",
    "## Stop and Escalate When",
    "## Definition of Done",
)
CONTRACT_SECTIONS = (
    "Objective",
    "Inputs",
    "Outputs",
    "Required Implementation Surfaces",
    "Workflow",
    "Hard Rules",
    "API Contract",
    "Verification",
    "Stop and Escalate When",
    "Definition of Done",
)
STACK_NAMES = {
    "vue-2": "Vue 2",
    "vue-3": "Vue 3",
    "react": "React",
    "mini-program": "WeChat Mini Program",
    "arkui": "ArkUI",
    "flutter": "Flutter",
}
ROUTE_PATTERN = re.compile(
    r"^frt-\d{4}-(vue-2|vue-3|react|mini-program|arkui|flutter)"
    r"-to-(vue-2|vue-3|react|mini-program|arkui|flutter)-route-pack$"
)
SURFACE_ROOTS = {
    "contract": "packages/contracts",
    "runtime": "packages/runtime",
    "control_plane": "services/control-plane",
    "web_console": "apps/web-console/src/features",
    "admin_console": "apps/admin-console/src/features",
    "tests": "tests",
}
SURFACE_IMPLEMENTATIONS = {
    "contract": [
        "schemas/frt-g01-g30/skill-run-request.schema.json",
        "schemas/frt-g01-g30/skill-run-result.schema.json",
        "schemas/frt-g01-g30/skill-execution-contract.schema.json",
        "schemas/frt-g01-g30/gate-result.schema.json",
        "schemas/frt-g01-g30/external-qualification-plan.schema.json",
        "schemas/frt-g01-g30/external-qualification-preflight.schema.json",
        "schemas/frt-g01-g30/external-qualification-local-execution.schema.json",
        "engines/frontend-client-engine/src/frt-types.ts",
        "engines/frontend-client-engine/src/frt-production-contract.ts",
    ],
    "runtime": [
        "engines/frontend-client-engine/src/frt-runtime.ts",
        "engines/frontend-client-engine/src/frt-runnable-target.ts",
        "engines/frontend-client-engine/src/frt-semantic-handlers.ts",
        "engines/frontend-client-engine/src/frt-production-contract.ts",
        "engines/frontend-client-engine/src/frt-handler-registry.generated.ts",
    ],
    "control_plane": ["engines/frontend-client-engine/src/server.ts"],
    "web_console": [
        "apps/web-console/app/frontend/FrontendTransformationStudio.tsx",
        "apps/web-console/app/api/frt/catalog/route.ts",
    ],
    "admin_console": [
        "apps/web-console/app/frontend/FrontendTransformationStudio.tsx",
        "apps/web-console/app/api/frt/catalog/route.ts",
    ],
    "tests": [
        "engines/frontend-client-engine/test/frt-artifact-lifecycle.test.ts",
        "engines/frontend-client-engine/test/frt-production-contract.test.ts",
        "engines/frontend-client-engine/test/frt-runtime.test.ts",
        "engines/frontend-client-engine/test/frt-semantic-handlers.test.ts",
        "engines/frontend-client-engine/test/server.test.ts",
        "apps/web-console/e2e/frt-frontend-transformation.spec.ts",
        "scripts/frt/external_qualification.py",
        "scripts/frt/external_campaign_parameters.py",
        "scripts/frt/test_external_qualification.py",
        "scripts/frt/test_external_campaign_parameters.py",
        "scripts/frt/record_frt_ios_device_evidence.mjs",
        "scripts/frt/test_record_frt_ios_device_evidence.py",
        "scripts/frt/materialize_frt_route.mjs",
        "scripts/frt/test_frt_route_smoke.py",
        "scripts/batch46/detect_project_profile.py",
        "scripts/batch46/run_smoke.py",
        "tests/batch46/test_smoke_pack.py",
    ],
}

HANDLER_INPUT_CONTRACTS: dict[str, dict[str, list[str]]] = {
    "governance": {
        "required": ["invariants"],
        "optional": ["dependencies", "allowedDependencies", "artifacts"],
    },
    "estate_discovery": {"required": ["files"], "optional": []},
    "semantic_ir": {"required": ["files"], "optional": []},
    "typed_contract": {"required": ["files"], "optional": []},
    "migration_planning": {
        "required": ["inventory", "target"],
        "optional": ["currentVersions"],
    },
    "source_generation": {
        "required": ["targetProfile", "uiIr"],
        "optional": [],
    },
    "build_toolchain": {
        "required": ["astNodes"],
        "optional": ["imports", "diagnostics", "unsupportedSemantics", "repairPasses"],
    },
    "test_automation": {"required": ["components"], "optional": []},
    "delivery_pipeline": {
        "required": ["states"],
        "optional": ["effects", "asyncOperations"],
    },
    "design_system": {
        "required": ["routes"],
        "optional": ["forms", "apiCalls", "storage", "permissions"],
    },
    "mobile_client": {
        "required": ["uiNodes"],
        "optional": ["designTokens", "locales", "rtlLocales", "animations"],
    },
    "cross_platform": {
        "required": ["requiredCapabilities", "platformCapabilities"],
        "optional": ["bridges"],
    },
    "directional_route": {"required": ["files"], "optional": []},
    "route_orchestration": {
        "required": ["corpus"],
        "optional": ["routeIds"],
    },
    "compatibility": {"required": ["packs"], "optional": []},
    "advanced_verification": {
        "required": ["properties"],
        "optional": ["toolchains", "counterexamples"],
    },
    "runtime_operations": {
        "required": ["resources"],
        "optional": ["roles", "jobs", "quotas"],
    },
    "product_workflow": {
        "required": ["requirements", "states", "transitions"],
        "optional": ["initialState", "journeys", "artifacts"],
    },
    "administration": {
        "required": ["capabilities", "roles", "operations"],
        "optional": [],
    },
    "performance_capacity": {
        "required": ["workload", "budgets"],
        "optional": ["samples", "throughputPerSecond"],
    },
    "resilience_dr": {
        "required": ["scenarios", "recoveryObjectives"],
        "optional": ["observations"],
    },
    "security_privacy": {
        "required": ["assets", "findings"],
        "optional": ["dataFlows", "sbomComponents"],
    },
    "production_readiness": {
        "required": ["slos", "runbooks"],
        "optional": ["alerts", "releases"],
    },
}


def required_evidence_roles(batch: str) -> list[str]:
    number = int(batch[1:])
    base = ["CONTRACT_VALIDATION", "SOURCE_LINEAGE", "INDEPENDENT_VERIFICATION"]
    if number <= 3:
        return base + ["SCHEMA_VALIDATION", "NEGATIVE_TEST"]
    if number <= 7:
        return base + ["SOURCE_BUILD", "TARGET_BUILD", "TYPECHECK", "NEGATIVE_TEST"]
    if number <= 12:
        return base + ["SOURCE_RUNTIME", "TARGET_RUNTIME", "JOURNEY", "ACCESSIBILITY"]
    if number <= 17:
        return base + ["SOURCE_BUILD", "TARGET_BUILD", "BROWSER_OR_DEVICE_JOURNEY", "HOLDOUT_CORPUS"]
    if number == 18:
        return base + ["PACK_SIGNATURE", "PACK_CONFORMANCE", "CONFLICT_RESOLUTION"]
    if number == 19:
        return base + ["PROOF_KERNEL", "COUNTEREXAMPLE_REPLAY", "HOLDOUT_CORPUS"]
    if number == 20:
        return base + ["DURABLE_RUNTIME", "TENANT_ISOLATION", "SECURITY_TEST", "OPERATOR_JOURNEY"]
    if number <= 26:
        return base + ["USER_JOURNEY", "ADMIN_JOURNEY", "HOLDOUT_CORPUS", "REPRESENTATIVE_JOURNEY"]
    if number == 27:
        return base + ["PERFORMANCE_RUN", "CONCURRENCY_RUN", "CAPACITY_RUN", "DEGRADATION_TEST"]
    if number == 28:
        return base + ["CHAOS_RUN", "FAILOVER_RUN", "RESTORE_RUN", "DR_EXERCISE"]
    if number == 29:
        return base + ["PENETRATION_TEST", "PRIVACY_REVIEW", "SUPPLY_CHAIN_ATTESTATION", "INCIDENT_DRILL"]
    return base + ["PRODUCTION_OBSERVATION", "CANARY_OBSERVATION", "ROLLBACK_DRILL", "ON_CALL_REVIEW", "CUSTOMER_OUTCOME"]


def skill_obligations(skill: dict[str, Any]) -> list[str]:
    obligations = [
        "PRESERVE_SOURCE_READ_ONLY",
        "ENFORCE_EXACT_TENANT_AND_RESOURCE_SCOPE",
        "BIND_INPUT_OUTPUT_AND_EVIDENCE_DIGESTS",
        "KEEP_UNKNOWN_AND_UNSUPPORTED_SEMANTICS_EXPLICIT",
        "REQUIRE_INDEPENDENT_GATE_FOR_CERTIFICATION",
    ]
    batch = int(skill["batch"][1:])
    if 3 <= batch <= 19:
        obligations.append("TRANSFORM_THROUGH_TYPED_SEMANTIC_IR")
    if 4 <= batch <= 17:
        obligations.append("USE_EXACT_DIRECTIONAL_SOURCE_AND_TARGET_PROFILES")
    if skill.get("route") is not None:
        source = skill["route"]["source"].upper().replace(" ", "_")
        target = skill["route"]["target"].upper().replace(" ", "_")
        obligations.extend([f"ROUTE_{source}_TO_{target}", "RUN_REAL_SOURCE_AND_TARGET_APPLICATIONS"])
    if batch >= 19:
        obligations.append("MODELS_MAY_PROPOSE_BUT_MAY_NOT_CERTIFY")
    if batch >= 21:
        obligations.append("REQUIRE_REPRESENTATIVE_BUSINESS_AND_ADMIN_JOURNEYS")
    if batch >= 27:
        obligations.append("REQUIRE_AUTHORIZED_EXTERNAL_OR_PRODUCTION_EQUIVALENT_EXECUTION")
    if batch >= 29:
        obligations.append("ZERO_TOLERANCE_FOR_CRITICAL_SECURITY_OR_PRIVACY_FINDINGS")
    if batch == 30:
        obligations.append("PRODUCTION_AUTHORITY_REMAINS_EXTERNAL")
    return obligations


def execution_class(skill: dict[str, Any]) -> str:
    batch = int(skill["batch"][1:])
    if skill.get("route") is not None or 6 <= batch <= 18:
        return "SANDBOX_RUNNER"
    if batch <= 5:
        return "CONTROL_PLANE_ANALYSIS"
    if batch <= 26:
        return "GOVERNED_EXTERNAL_RUNNER"
    if batch <= 29:
        return "AUTHORIZED_EXTERNAL_ASSURANCE"
    return "EXTERNAL_PRODUCTION_AUTHORITY"


def handler_kind(skill: dict[str, Any]) -> str:
    if skill.get("route") is not None:
        return "directional_route"
    return {
        "G01": "governance",
        "G02": "estate_discovery",
        "G03": "semantic_ir",
        "G04": "typed_contract",
        "G05": "migration_planning",
        "G06": "source_generation",
        "G07": "build_toolchain",
        "G08": "test_automation",
        "G09": "delivery_pipeline",
        "G10": "design_system",
        "G11": "mobile_client",
        "G12": "cross_platform",
        "G13": "route_orchestration",
        "G14": "route_orchestration",
        "G15": "route_orchestration",
        "G16": "route_orchestration",
        "G17": "route_orchestration",
        "G18": "compatibility",
        "G19": "advanced_verification",
        "G20": "runtime_operations",
        "G21": "product_workflow",
        "G22": "product_workflow",
        "G23": "product_workflow",
        "G24": "administration",
        "G25": "product_workflow",
        "G26": "product_workflow",
        "G27": "performance_capacity",
        "G28": "resilience_dr",
        "G29": "security_privacy",
        "G30": "production_readiness",
    }[skill["batch"]]


def surface_manifest_path(skill: dict[str, Any], surface: str) -> Path:
    return (
        ROOT
        / SURFACE_ROOTS[surface]
        / skill["batch"].lower()
        / skill["name"]
        / "surface-manifest.json"
    )


def surface_manifest(skill: dict[str, Any], surface: str) -> dict[str, Any]:
    logical_path = (
        f"{SURFACE_ROOTS[surface]}/{skill['batch'].lower()}/{skill['name']}/"
    )
    return {
        "schema_version": "1.0",
        "generated_by": "tooling/integrate_frt_g01_g30.py",
        "skill_id": skill["id"],
        "skill_name": skill["name"],
        "batch": skill["batch"],
        "surface": surface,
        "logical_path": logical_path,
        "status": "shared_implementation",
        "handler_kind": handler_kind(skill),
        "capability_key": skill["executionContract"]["capabilityKey"],
        "execution_contract_sha256": skill["executionContract"]["contractDigest"],
        "execution_class": skill["executionContract"]["executionClass"],
        "input_contract": skill["executionContract"]["inputContract"],
        "contract_version": skill["version"],
        "source_sha256": skill["sourceSha256"],
        "implementation_paths": SURFACE_IMPLEMENTATIONS[surface],
        "not_applicable": False,
        "approval_evidence": [],
        "certification": "NOT_CERTIFIED",
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_frontmatter(text: str, source: Path) -> tuple[dict[str, str], str]:
    match = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if match is None:
        raise SystemExit(f"Source Skill frontmatter is invalid: {source}")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise SystemExit(f"Source Skill frontmatter line is invalid: {source}: {line}")
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"')
    return fields, text[match.end() :].lstrip("\n")


def markdown_section(body: str, heading: str, source: Path) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^##\s|\Z)",
        body,
        re.MULTILINE | re.DOTALL,
    )
    if match is None or not match.group(1).strip():
        raise SystemExit(f"FRT Skill contract section is missing or empty: {source}: {heading}")
    return match.group(1).strip()


def markdown_bullets(section: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in re.finditer(r"^-\s+(.+)$", section, re.MULTILINE)
    ]


def compiled_execution_contract(
    skill: dict[str, Any],
    body: str,
    source: Path,
) -> dict[str, Any]:
    sections = {heading: markdown_section(body, heading, source) for heading in CONTRACT_SECTIONS}
    inputs = markdown_bullets(sections["Inputs"])
    outputs = markdown_bullets(sections["Outputs"])
    verification = markdown_bullets(sections["Verification"])
    stop_conditions = markdown_bullets(sections["Stop and Escalate When"])
    done = markdown_bullets(sections["Definition of Done"])
    workflow_steps = re.findall(r"^\d+\.\s+(.+)$", sections["Workflow"], re.MULTILINE)
    hard_rules = markdown_bullets(sections["Hard Rules"])
    api_operations = re.findall(
        r"^(GET|POST|PUT|PATCH|DELETE)\s+([^\s]+)$",
        sections["API Contract"],
        re.MULTILINE,
    )
    surface_block = re.search(
        r"```(?:text)?\s*\n(.*?)```",
        sections["Required Implementation Surfaces"],
        re.DOTALL,
    )
    surfaces = [
        line.strip()
        for line in (surface_block.group(1).splitlines() if surface_block else [])
        if line.strip()
    ]
    counts = {
        "inputCount": len(inputs),
        "outputCount": len(outputs),
        "workflowStepCount": len(workflow_steps),
        "hardRuleCount": len(hard_rules),
        "verificationCount": len(verification),
        "stopConditionCount": len(stop_conditions),
        "definitionOfDoneCount": len(done),
        "apiOperationCount": len(api_operations),
        "surfaceCount": len(surfaces),
    }
    if any(value == 0 for value in counts.values()):
        raise SystemExit(f"FRT Skill compiled contract is incomplete: {skill['id']}: {counts}")
    handler_input = HANDLER_INPUT_CONTRACTS[skill["handlerKind"]]
    capability_name = skill["name"].removeprefix(f"frt-{skill['id'][4:]}-")
    capability_key = f"frt.{skill['batch'].lower()}.{capability_name}"
    compiled = {
        "schemaVersion": "1.0",
        "skillId": skill["id"],
        "skillName": skill["name"],
        "batch": skill["batch"],
        "capabilityKey": capability_key,
        "handlerKind": skill["handlerKind"],
        "risk": skill["risk"],
        "executionClass": execution_class(skill),
        "inputContract": {
            "required": handler_input["required"],
            "optional": handler_input["optional"],
            "additionalProperties": False,
        },
        "outputContracts": [
            match.group(1) if (match := re.search(r"`([^`]+)`", output)) else output
            for output in outputs
        ],
        "requiredEvidenceRoles": required_evidence_roles(skill["batch"]),
        "obligations": skill_obligations(skill),
        "apiOperations": [
            {"method": method, "path": path}
            for method, path in api_operations
        ],
        "requiredSurfaces": surfaces,
        "assuranceCounts": counts,
        "sourcePath": skill["sourcePath"],
        "sourceSha256": skill["sourceSha256"],
        "productionOperationAuthority": "EXTERNAL_ONLY",
        "certification": "NOT_CERTIFIED",
    }
    return {
        **compiled,
        "contractDigest": "sha256:" + canonical_digest(compiled),
    }


def validate_source() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    package_manifest_path = PACKAGE_ROOT / "PACKAGE_MANIFEST.json"
    if not package_manifest_path.is_file():
        raise SystemExit(f"FRT package manifest is missing: {package_manifest_path}")
    package_manifest = json.loads(package_manifest_path.read_text(encoding="utf-8"))
    if package_manifest.get("name") != PACKAGE_NAME:
        raise SystemExit("FRT package identity is invalid")
    listed_entries = package_manifest.get("files")
    if not isinstance(listed_entries, list) or not listed_entries:
        raise SystemExit("FRT package file manifest is empty")
    listed_paths: set[str] = set()
    for entry in listed_entries:
        relative = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(relative, str) or relative in listed_paths:
            raise SystemExit(f"FRT package has an invalid or duplicate path: {relative}")
        path = (PACKAGE_ROOT / relative).resolve()
        try:
            path.relative_to(PACKAGE_ROOT.resolve())
        except ValueError as exc:
            raise SystemExit(f"FRT package path escapes its root: {relative}") from exc
        if (
            not path.is_file()
            or path.stat().st_size != entry.get("size")
            or sha256_file(path) != entry.get("sha256")
        ):
            raise SystemExit(f"FRT package file integrity failed: {relative}")
        listed_paths.add(relative)
    actual_paths = {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in PACKAGE_ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }
    expected_paths = listed_paths | {"PACKAGE_MANIFEST.json"}
    if actual_paths != expected_paths:
        raise SystemExit(
            "FRT package inventory differs from PACKAGE_MANIFEST.json: "
            f"missing={sorted(expected_paths - actual_paths)}, "
            f"extra={sorted(actual_paths - expected_paths)}"
        )

    manifest = json.loads((PACKAGE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    spec = manifest.get("spec", {})
    if (
        manifest.get("kind") != "FRTSkillPack"
        or spec.get("batchCount") != EXPECTED_BATCHES
        or spec.get("skillCount") != EXPECTED_SKILLS
        or spec.get("directedRouteCount") != 30
    ):
        raise SystemExit("FRT root manifest counts or identity are invalid")
    batch_entries = spec.get("batches")
    if not isinstance(batch_entries, list) or len(batch_entries) != EXPECTED_BATCHES:
        raise SystemExit("FRT root manifest must declare exactly 30 batches")
    batches: list[dict[str, Any]] = []
    for index, batch in enumerate(batch_entries, 1):
        expected_id = f"G{index:02d}"
        if not isinstance(batch, dict) or batch.get("id") != expected_id:
            raise SystemExit(f"FRT batch order must be contiguous at {expected_id}")
        batch_path = PACKAGE_ROOT / str(batch.get("path", ""))
        batch_manifest_path = batch_path.parent / "manifest.yaml"
        if not batch_path.is_file() or not batch_manifest_path.is_file():
            raise SystemExit(f"FRT batch files are missing: {expected_id}")
        batch_fields, _ = parse_frontmatter(batch_path.read_text(encoding="utf-8"), batch_path)
        if batch_fields.get("batch") != expected_id:
            raise SystemExit(f"FRT batch frontmatter mismatch: {expected_id}")
        batches.append(
            {
                "id": expected_id,
                "number": index,
                "title": batch["title"],
                "path": batch["path"],
                "certificateFamily": batch_fields.get("certificate", "").split("0", 1)[0],
                "dependsOn": None if index == 1 else f"G{index - 1:02d}",
                "sourceSha256": "sha256:" + sha256_file(batch_path),
            }
        )

    skill_files = sorted((PACKAGE_ROOT / "skills").glob("*/SKILL.md"))
    if len(skill_files) != EXPECTED_SKILLS:
        raise SystemExit(
            f"FRT package must contain {EXPECTED_SKILLS} Skills, found {len(skill_files)}"
        )
    skills: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for skill_path in skill_files:
        text = skill_path.read_text(encoding="utf-8")
        fields, body = parse_frontmatter(text, skill_path)
        required_fields = {
            "name",
            "description",
            "version",
            "skill_id",
            "batch",
            "risk",
            "requires_certificate",
            "produces_certificate_family",
        }
        if set(fields) != required_fields:
            raise SystemExit(
                f"FRT Skill frontmatter fields are invalid: {skill_path}: {sorted(fields)}"
            )
        name = fields["name"]
        skill_id = fields["skill_id"]
        batch = fields["batch"]
        if name != skill_path.parent.name or len(name) > 64:
            raise SystemExit(f"FRT Skill name/path is invalid: {name}")
        if not re.fullmatch(r"FRT-\d{4}", skill_id) or skill_id in seen_ids:
            raise SystemExit(f"FRT Skill ID is invalid or duplicated: {skill_id}")
        if name in seen_names or not re.fullmatch(r"frt-[a-z0-9-]+", name):
            raise SystemExit(f"FRT Skill name is invalid or duplicated: {name}")
        if batch not in {item["id"] for item in batches}:
            raise SystemExit(f"FRT Skill batch is invalid: {skill_id}: {batch}")
        for section in REQUIRED_SECTIONS:
            if section not in body:
                raise SystemExit(f"FRT Skill is missing {section}: {skill_id}")
        expected_requirement = (
            "System charter inputs"
            if batch == "G01"
            else f"G{int(batch[1:]) - 1:02d}"
        )
        if fields["requires_certificate"] != expected_requirement:
            raise SystemExit(
                f"FRT Skill prerequisite is invalid: {skill_id}: "
                f"{fields['requires_certificate']} != {expected_requirement}"
            )
        title_match = re.search(rf"^# {re.escape(skill_id)}\s+[—-]\s+(.+)$", body, re.MULTILINE)
        if title_match is None:
            raise SystemExit(f"FRT Skill title is missing: {skill_id}")
        route_match = ROUTE_PATTERN.match(name)
        skill = {
                "id": skill_id,
                "name": name,
                "title": title_match.group(1).strip(),
                "description": fields["description"],
                "version": fields["version"],
                "batch": batch,
                "risk": fields["risk"],
                "requiresCertificate": None if batch == "G01" else fields["requires_certificate"],
                "foundationRequirement": fields["requires_certificate"] if batch == "G01" else None,
                "certificateFamily": fields["produces_certificate_family"],
                "sourcePath": skill_path.relative_to(ROOT).as_posix(),
                "sourceSha256": "sha256:" + sha256_file(skill_path),
                "route": (
                    {
                        "source": STACK_NAMES[route_match.group(1)],
                        "target": STACK_NAMES[route_match.group(2)],
                    }
                    if route_match
                    else None
                ),
            }
        skill["handlerKind"] = handler_kind(skill)
        skill["executionContract"] = compiled_execution_contract(skill, body, skill_path)
        skills.append(skill)
        seen_ids.add(skill_id)
        seen_names.add(name)
    skill_ids = [int(skill["id"].split("-")[1]) for skill in skills]
    if skill_ids != sorted(skill_ids):
        raise SystemExit("FRT Skill inventory must be ordered by numeric ID")
    route_count = sum(skill["route"] is not None for skill in skills)
    if route_count != 30:
        raise SystemExit(f"FRT package must contain 30 directed routes, found {route_count}")
    for batch in batches:
        batch["skillCount"] = sum(skill["batch"] == batch["id"] for skill in skills)
    for skill in skills:
        skill["surfaceManifestPaths"] = {
            surface: surface_manifest_path(skill, surface).relative_to(ROOT).as_posix()
            for surface in SURFACE_ROOTS
        }
    return package_manifest, batches, skills


def normalized_skill(skill: dict[str, Any]) -> str:
    source = ROOT / skill["sourcePath"]
    _, body = parse_frontmatter(source.read_text(encoding="utf-8"), source)
    description = (
        f"Run {skill['id']} {skill['title']} for FRT {skill['batch']} with typed frontend "
        "contracts, tenant scope, immutable evidence, and fail-closed certification boundaries."
    )
    metadata = {
        "source_package": PACKAGE_NAME,
        "source_skill_id": skill["id"],
        "source_name": skill["name"],
        "source_sha256": skill["sourceSha256"],
        "batch": skill["batch"],
        "source_version": skill["version"],
        "source_risk": skill["risk"],
        "source_certificate_family": skill["certificateFamily"],
        "runtime_namespace": "frt-g01-g30",
        "implementation_authority": "engines/frontend-client-engine",
        "certification_state": "NOT_CERTIFIED",
    }
    frontmatter = [
        "---",
        f"name: {skill['name']}",
        f"description: {json.dumps(description, ensure_ascii=False)}",
        "metadata:",
        *[
            f"  {key}: {json.dumps(value, ensure_ascii=False)}"
            for key, value in metadata.items()
        ],
        "---",
        "",
    ]
    integration = [
        "## ELMOS Runtime Integration",
        "",
        f"- Runtime catalog key: `{skill['id']}` / `{skill['name']}`.",
        "- Invoke through the typed FRT engine API or CLI; the Markdown Skill does not execute customer code by itself.",
        "- Static analysis, planning, external runner execution, independent verification, and certification remain distinct states.",
        "- Missing scope, prerequisite certificate, real toolchain, browser/device, provider, or independent evidence fails closed.",
        "",
    ]
    return "\n".join(frontmatter + integration) + body.rstrip() + "\n"


def interface_text(skill: dict[str, Any]) -> str:
    prompt = (
        f"Use ${skill['name']} to run {skill['id']} through the governed FRT runtime with "
        "exact scope and fail-closed evidence."
    )
    return "\n".join(
        [
            "interface:",
            f"  display_name: {json.dumps(skill['title'], ensure_ascii=False)}",
            '  short_description: "Run this FRT frontend Skill with evidence controls"',
            f"  default_prompt: {json.dumps(prompt, ensure_ascii=False)}",
            "",
        ]
    )


def write_managed(path: Path, content: str, *, marker: str | None = None) -> None:
    if path.exists() and marker is not None and marker not in path.read_text(encoding="utf-8"):
        raise SystemExit(f"Refusing to overwrite an unmanaged file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def generated_catalog(
    package_manifest: dict[str, Any],
    batches: list[dict[str, Any]],
    skills: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest_digest = "sha256:" + sha256_file(PACKAGE_ROOT / "PACKAGE_MANIFEST.json")
    source_tree_digest = "sha256:" + canonical_digest(
        [(entry["path"], entry["sha256"]) for entry in package_manifest["files"]]
    )
    routes = [
        {
            "routeId": f"{skill['route']['source']} -> {skill['route']['target']}",
            "skillId": skill["id"],
            "skillName": skill["name"],
            "batch": skill["batch"],
            "source": skill["route"]["source"],
            "target": skill["route"]["target"],
            "staticRuntime": "READY",
            "sourceBuild": "NOT_RUN",
            "targetBuild": "NOT_RUN",
            "browserOrDeviceEvidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
        for skill in skills
        if skill["route"] is not None
    ]
    return {
        "schemaVersion": "1.0",
        "package": PACKAGE_NAME,
        "packageVersion": "1.0.0",
        "packageManifestSha256": manifest_digest,
        "sourceTreeSha256": source_tree_digest,
        "batchCount": len(batches),
        "skillCount": len(skills),
        "directedRouteCount": len(routes),
        "technologyStacks": list(STACK_NAMES.values()),
        "batches": batches,
        "skills": skills,
        "routes": routes,
        "evidenceBoundary": {
            "staticPackageValidation": "READY",
            "runtimeExecution": "RUNNER_REQUIRED",
            "formalProof": "NOT_RUN",
            "deviceMatrix": "NOT_RUN",
            "performance": "NOT_RUN",
            "chaosAndDr": "NOT_RUN",
            "penetrationTest": "NOT_RUN",
            "production": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
    }


def typescript_catalog(catalog: dict[str, Any], export_name: str) -> str:
    rendered = json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=False)
    return (
        "// Generated by tooling/integrate_frt_g01_g30.py. Do not edit manually.\n"
        "export interface FrtGeneratedInputContract {\n"
        "  readonly required: readonly string[];\n"
        "  readonly optional: readonly string[];\n"
        "  readonly additionalProperties: false;\n"
        "}\n"
        "export interface FrtGeneratedExecutionContract {\n"
        "  readonly schemaVersion: \"1.0\";\n"
        "  readonly skillId: string; readonly skillName: string; readonly batch: string;\n"
        "  readonly capabilityKey: string; readonly handlerKind: string; readonly risk: string;\n"
        "  readonly executionClass: string; readonly inputContract: FrtGeneratedInputContract;\n"
        "  readonly outputContracts: readonly string[]; readonly requiredEvidenceRoles: readonly string[];\n"
        "  readonly obligations: readonly string[];\n"
        "  readonly apiOperations: readonly { readonly method: string; readonly path: string }[];\n"
        "  readonly requiredSurfaces: readonly string[]; readonly assuranceCounts: Readonly<Record<string, number>>;\n"
        "  readonly sourcePath: string; readonly sourceSha256: string; readonly contractDigest: string;\n"
        "  readonly productionOperationAuthority: \"EXTERNAL_ONLY\"; readonly certification: \"NOT_CERTIFIED\";\n"
        "}\n"
        "export interface FrtGeneratedBatch {\n"
        "  readonly id: string; readonly number: number; readonly title: string; readonly path: string;\n"
        "  readonly certificateFamily: string; readonly dependsOn: string | null;\n"
        "  readonly sourceSha256: string; readonly skillCount: number;\n"
        "}\n"
        "export interface FrtGeneratedSkill {\n"
        "  readonly id: string; readonly name: string; readonly title: string; readonly description: string;\n"
        "  readonly version: string; readonly batch: string; readonly risk: string;\n"
        "  readonly requiresCertificate: string | null; readonly foundationRequirement: string | null;\n"
        "  readonly certificateFamily: string; readonly sourcePath: string; readonly sourceSha256: string;\n"
        "  readonly route: { readonly source: string; readonly target: string } | null;\n"
        "  readonly handlerKind: string; readonly executionContract: FrtGeneratedExecutionContract;\n"
        "  readonly surfaceManifestPaths: Readonly<Record<string, string>>;\n"
        "}\n"
        "export interface FrtGeneratedRoute {\n"
        "  readonly routeId: string; readonly skillId: string; readonly skillName: string; readonly batch: string;\n"
        "  readonly source: string; readonly target: string; readonly staticRuntime: string;\n"
        "  readonly sourceBuild: string; readonly targetBuild: string; readonly browserOrDeviceEvidence: string;\n"
        "  readonly certification: \"NOT_CERTIFIED\";\n"
        "}\n"
        "export interface FrtGeneratedCatalog {\n"
        "  readonly schemaVersion: \"1.0\"; readonly package: string; readonly packageVersion: string;\n"
        "  readonly packageManifestSha256: string; readonly sourceTreeSha256: string;\n"
        "  readonly batchCount: number; readonly skillCount: number; readonly directedRouteCount: number;\n"
        "  readonly technologyStacks: readonly string[]; readonly batches: readonly FrtGeneratedBatch[];\n"
        "  readonly skills: readonly FrtGeneratedSkill[]; readonly routes: readonly FrtGeneratedRoute[];\n"
        "  readonly evidenceBoundary: Readonly<Record<string, string>>;\n"
        "}\n"
        f"export const {export_name}: FrtGeneratedCatalog = {rendered};\n"
    )


def typescript_handler_registry(skills: list[dict[str, Any]]) -> str:
    descriptors = [
        {
            "skillId": skill["id"],
            "skillName": skill["name"],
            "batch": skill["batch"],
            "handlerKind": skill["handlerKind"],
            "capabilityKey": skill["executionContract"]["capabilityKey"],
            "executionClass": skill["executionContract"]["executionClass"],
            "contractDigest": skill["executionContract"]["contractDigest"],
            "inputContract": skill["executionContract"]["inputContract"],
            "actions": ["PLAN", "ANALYZE", "EXECUTE", "VERIFY"],
            "surfaceManifestPaths": skill["surfaceManifestPaths"],
            "sourceSha256": skill["sourceSha256"],
            "contractVersion": skill["version"],
            "certification": "NOT_CERTIFIED",
        }
        for skill in skills
    ]
    rendered = json.dumps(descriptors, ensure_ascii=False, indent=2)
    return (
        "// Generated by tooling/integrate_frt_g01_g30.py. Do not edit manually.\n"
        f"export const frtHandlerRegistry = {rendered} as const;\n"
    )


def install(
    package_manifest: dict[str, Any],
    batches: list[dict[str, Any]],
    skills: list[dict[str, Any]],
) -> None:
    for skill in skills:
        destination = RUNTIME_ROOT / skill["name"]
        skill_file = destination / "SKILL.md"
        interface_file = destination / "agents" / "openai.yaml"
        expected_skill = normalized_skill(skill)
        if skill_file.exists() and f'source_package: "{PACKAGE_NAME}"' not in skill_file.read_text(
            encoding="utf-8"
        ):
            raise SystemExit(f"Refusing to overwrite unmanaged Runtime Skill: {destination}")
        destination.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(expected_skill, encoding="utf-8")
        interface_file.parent.mkdir(parents=True, exist_ok=True)
        interface_file.write_text(interface_text(skill), encoding="utf-8")
        for surface in SURFACE_ROOTS:
            manifest_path = surface_manifest_path(skill, surface)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(
                    surface_manifest(skill, surface),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

    catalog = generated_catalog(package_manifest, batches, skills)
    compiled_contracts = {
        "schemaVersion": "1.0",
        "package": PACKAGE_NAME,
        "skillCount": len(skills),
        "productionOperationAuthorized": False,
        "productionCertification": "NOT_CERTIFIED",
        "contracts": [skill["executionContract"] for skill in skills],
    }
    write_managed(
        ENGINE_CATALOG,
        typescript_catalog(catalog, "frtCatalog"),
        marker="Generated by tooling/integrate_frt_g01_g30.py",
    )
    write_managed(
        WEB_CATALOG,
        typescript_catalog(catalog, "frtCatalog"),
        marker="Generated by tooling/integrate_frt_g01_g30.py",
    )
    write_managed(
        ENGINE_HANDLER_REGISTRY,
        typescript_handler_registry(skills),
        marker="Generated by tooling/integrate_frt_g01_g30.py",
    )
    write_managed(
        COMPILED_CONTRACTS,
        json.dumps(compiled_contracts, ensure_ascii=False, indent=2) + "\n",
    )
    installed_entries = []
    for skill in skills:
        installed = RUNTIME_ROOT / skill["name"] / "SKILL.md"
        interface = installed.parent / "agents" / "openai.yaml"
        installed_entries.append(
            {
                "skill_id": skill["id"],
                "batch": skill["batch"],
                "source_name": skill["name"],
                "source_path": skill["sourcePath"],
                "source_sha256": skill["sourceSha256"],
                "installed_name": skill["name"],
                "installed_path": installed.relative_to(ROOT).as_posix(),
                "installed_sha256": "sha256:" + sha256_file(installed),
                "interface_path": interface.relative_to(ROOT).as_posix(),
                "interface_sha256": "sha256:" + sha256_file(interface),
                "handler_kind": skill["handlerKind"],
                "capability_key": skill["executionContract"]["capabilityKey"],
                "execution_class": skill["executionContract"]["executionClass"],
                "execution_contract_sha256": skill["executionContract"]["contractDigest"],
                "surface_manifests": {
                    surface: {
                        "path": surface_manifest_path(skill, surface)
                        .relative_to(ROOT)
                        .as_posix(),
                        "sha256": "sha256:"
                        + sha256_file(surface_manifest_path(skill, surface)),
                    }
                    for surface in SURFACE_ROOTS
                },
            }
        )
    install_manifest = {
        "schema_version": "1.0",
        "source_package": PACKAGE_NAME,
        "source_namespace": "frt-g01-g30",
        "source_package_manifest_sha256": catalog["packageManifestSha256"],
        "source_tree_sha256": catalog["sourceTreeSha256"],
        "batch_count": len(batches),
        "skill_count": len(skills),
        "directed_route_count": len(catalog["routes"]),
        "runtime_authority": "engines/frontend-client-engine",
        "production_operation_authorized": False,
        "production_certification": "NOT_CERTIFIED",
        "skills": installed_entries,
    }
    INSTALL_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    INSTALL_MANIFEST.write_text(
        json.dumps(install_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify(
    package_manifest: dict[str, Any],
    batches: list[dict[str, Any]],
    skills: list[dict[str, Any]],
) -> None:
    catalog = generated_catalog(package_manifest, batches, skills)
    expected_engine = typescript_catalog(catalog, "frtCatalog")
    expected_web = typescript_catalog(catalog, "frtCatalog")
    expected_handlers = typescript_handler_registry(skills)
    expected_contracts = json.dumps(
        {
            "schemaVersion": "1.0",
            "package": PACKAGE_NAME,
            "skillCount": len(skills),
            "productionOperationAuthorized": False,
            "productionCertification": "NOT_CERTIFIED",
            "contracts": [skill["executionContract"] for skill in skills],
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    if not ENGINE_CATALOG.is_file() or ENGINE_CATALOG.read_text(encoding="utf-8") != expected_engine:
        raise SystemExit("FRT engine catalog is missing or stale")
    if not WEB_CATALOG.is_file() or WEB_CATALOG.read_text(encoding="utf-8") != expected_web:
        raise SystemExit("FRT Web Console catalog is missing or stale")
    if (
        not ENGINE_HANDLER_REGISTRY.is_file()
        or ENGINE_HANDLER_REGISTRY.read_text(encoding="utf-8") != expected_handlers
    ):
        raise SystemExit("FRT handler registry is missing or stale")
    if not COMPILED_CONTRACTS.is_file() or COMPILED_CONTRACTS.read_text(encoding="utf-8") != expected_contracts:
        raise SystemExit("FRT compiled Skill contracts are missing or stale")
    for skill in skills:
        destination = RUNTIME_ROOT / skill["name"]
        skill_file = destination / "SKILL.md"
        interface_file = destination / "agents" / "openai.yaml"
        if not skill_file.is_file() or skill_file.read_text(encoding="utf-8") != normalized_skill(skill):
            raise SystemExit(f"Installed FRT Runtime Skill is missing or stale: {skill['name']}")
        if not interface_file.is_file() or interface_file.read_text(encoding="utf-8") != interface_text(skill):
            raise SystemExit(f"Installed FRT Runtime Skill interface is missing or stale: {skill['name']}")
        for surface in SURFACE_ROOTS:
            manifest_path = surface_manifest_path(skill, surface)
            expected_manifest = (
                json.dumps(
                    surface_manifest(skill, surface),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
            if (
                not manifest_path.is_file()
                or manifest_path.read_text(encoding="utf-8") != expected_manifest
            ):
                raise SystemExit(
                    f"FRT {surface} surface manifest is missing or stale: {skill['id']}"
                )
    if not INSTALL_MANIFEST.is_file():
        raise SystemExit("FRT installed manifest is missing")
    installed_manifest = json.loads(INSTALL_MANIFEST.read_text(encoding="utf-8"))
    if (
        installed_manifest.get("source_tree_sha256") != catalog["sourceTreeSha256"]
        or installed_manifest.get("skill_count") != EXPECTED_SKILLS
        or installed_manifest.get("batch_count") != EXPECTED_BATCHES
        or installed_manifest.get("directed_route_count") != 30
        or installed_manifest.get("production_operation_authorized") is not False
        or installed_manifest.get("production_certification") != "NOT_CERTIFIED"
        or len(installed_manifest.get("skills", [])) != EXPECTED_SKILLS
    ):
        raise SystemExit("FRT installed manifest counts or source identity are stale")
    for entry, skill in zip(installed_manifest["skills"], skills, strict=True):
        installed = ROOT / entry["installed_path"]
        interface = ROOT / entry["interface_path"]
        surfaces = entry.get("surface_manifests", {})
        if (
            entry.get("skill_id") != skill["id"]
            or entry.get("source_sha256") != skill["sourceSha256"]
            or entry.get("installed_sha256") != "sha256:" + sha256_file(installed)
            or entry.get("interface_sha256") != "sha256:" + sha256_file(interface)
            or entry.get("handler_kind") != skill["handlerKind"]
            or entry.get("capability_key") != skill["executionContract"]["capabilityKey"]
            or entry.get("execution_class") != skill["executionContract"]["executionClass"]
            or entry.get("execution_contract_sha256") != skill["executionContract"]["contractDigest"]
            or set(surfaces) != set(SURFACE_ROOTS)
        ):
            raise SystemExit(f"FRT installed manifest entry is stale: {skill['id']}")
        for surface in SURFACE_ROOTS:
            manifest_path = surface_manifest_path(skill, surface)
            surface_entry = surfaces[surface]
            if (
                surface_entry.get("path")
                != manifest_path.relative_to(ROOT).as_posix()
                or surface_entry.get("sha256")
                != "sha256:" + sha256_file(manifest_path)
            ):
                raise SystemExit(
                    f"FRT installed surface digest is stale: {skill['id']}: {surface}"
                )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args()
    package_manifest, batches, skills = validate_source()
    if not args.check:
        install(package_manifest, batches, skills)
    verify(package_manifest, batches, skills)
    print(
        json.dumps(
            {
                "package": PACKAGE_NAME,
                "batches": len(batches),
                "skills": len(skills),
                "directed_routes": sum(skill["route"] is not None for skill in skills),
                "runtime_interfaces": len(skills),
                "status": "verified" if args.check else "integrated-and-verified",
                "production_operation_authorized": False,
                "production_certification": "NOT_CERTIFIED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
