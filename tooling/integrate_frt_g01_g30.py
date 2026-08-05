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
        "engines/frontend-client-engine/src/frt-types.ts",
    ],
    "runtime": [
        "engines/frontend-client-engine/src/frt-runtime.ts",
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
        "engines/frontend-client-engine/test/frt-runtime.test.ts",
        "engines/frontend-client-engine/test/server.test.ts",
        "apps/web-console/e2e/frt-frontend-transformation.spec.ts",
    ],
}


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
        skills.append(
            {
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
        )
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
        skill["handlerKind"] = handler_kind(skill)
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
        f"export const {export_name} = {rendered} as const;\n"
    )


def typescript_handler_registry(skills: list[dict[str, Any]]) -> str:
    descriptors = [
        {
            "skillId": skill["id"],
            "skillName": skill["name"],
            "batch": skill["batch"],
            "handlerKind": skill["handlerKind"],
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
    if not ENGINE_CATALOG.is_file() or ENGINE_CATALOG.read_text(encoding="utf-8") != expected_engine:
        raise SystemExit("FRT engine catalog is missing or stale")
    if not WEB_CATALOG.is_file() or WEB_CATALOG.read_text(encoding="utf-8") != expected_web:
        raise SystemExit("FRT Web Console catalog is missing or stale")
    if (
        not ENGINE_HANDLER_REGISTRY.is_file()
        or ENGINE_HANDLER_REGISTRY.read_text(encoding="utf-8") != expected_handlers
    ):
        raise SystemExit("FRT handler registry is missing or stale")
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
                "production_certification": "NOT_CERTIFIED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
