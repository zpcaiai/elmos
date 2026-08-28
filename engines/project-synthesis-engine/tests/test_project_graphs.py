from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from elmos_project_synthesis.deployment_guidance import render_deployment_guidance
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SUPPORTED_LANGUAGES, TARGET_PROFILES, SynthesisRequest
from elmos_project_synthesis.production_profile import render_production_assets
from elmos_project_synthesis.project_graphs import (
    DEPENDENCY_GRAPH_PATH,
    DEPENDENCY_GRAPH_SCHEMA_ID,
    PROJECT_INSIGHTS_PATH,
    PROJECT_STRUCTURE_PATH,
    PROJECT_STRUCTURE_SCHEMA_ID,
    render_declared_dependency_graph,
    render_project_structure,
    validate_workspace_graphs,
)
from elmos_project_synthesis.workspace import generate_workspace

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = ROOT / "contracts" / "project-synthesis-schema"

TARGET_MANIFEST_PATHS = {
    "java": "java/pom.xml",
    "python": "python/pyproject.toml",
    "csharp": "dotnet/src/GraphService.Api/GraphService.Api.csproj",
    "typescript": "typescript/package.json",
    "go": "go/go.mod",
    "kotlin": "kotlin/build.gradle.kts",
    "php": "php/composer.json",
    "rust": "rust/Cargo.toml",
}


def _approved_request(*, production: bool = False) -> SynthesisRequest:
    permissions: tuple[dict[str, str], ...] = ()
    if production:
        permissions = tuple(
            {
                "actor": "api_user",
                "action": action,
                "resource": "record",
                "effect": "allow",
            }
            for action in ("create", "read", "update", "delete")
        )
    draft = create_draft(
        name="graph-service",
        description="Generate one governed API in all eight bundled targets.",
        entity="record",
        languages=SUPPORTED_LANGUAGES,
        persistence="postgresql" if production else "in-memory",
        auth_mode="jwt" if production else "none",
        permissions=permissions,
    )
    approved = approve_request(
        draft,
        actor="user:graph-reviewer",
        approved_at="2026-08-10T00:00:00+00:00",
    )
    return SynthesisRequest.from_mapping(approved)


def _managed_paths(request: SynthesisRequest, *, production: bool = False) -> list[str]:
    paths = [
        "README.md",
        "docker-compose.yml",
        "requirements/approved-request.json",
        "requirements/project-blueprint.json",
        PROJECT_STRUCTURE_PATH,
        DEPENDENCY_GRAPH_PATH,
        PROJECT_INSIGHTS_PATH,
        "docs/ARCHITECTURE.md",
        *TARGET_MANIFEST_PATHS.values(),
    ]
    if production:
        paths.extend(render_production_assets(request))
        paths.extend(render_deployment_guidance(request))
        paths.append("database/migrations/001_initial.sql")
    return sorted(set(paths))


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_text(root: Path, relative: str, content: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _blueprint(request: SynthesisRequest) -> dict[str, Any]:
    return {
        "schema_version": "1.1.0",
        "project": {
            "id": request.raw["project"]["id"],
            "name": request.project_name,
        },
        "applications": [
            {
                "id": f"APP-{target.language.upper()}",
                "language": target.language,
                "profile": f"{target.framework}-{target.runtime}",
                "port": target.port,
                "storage": request.persistence,
                "auth_mode": request.auth_mode,
                "toolchain": TARGET_PROFILES[target.language]["toolchain"],
            }
            for target in request.targets
        ],
        "runtime": {target.language: target.runtime for target in request.targets},
    }


def _write_workspace(
    tmp_path: Path,
    request: SynthesisRequest,
    *,
    production: bool = False,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    workspace = tmp_path / "workspace"
    managed_paths = _managed_paths(request, production=production)
    structure = render_project_structure(request, managed_paths)
    dependencies = render_declared_dependency_graph(request)
    special_content = {
        "requirements/approved-request.json": _json_text(request.raw),
        "requirements/project-blueprint.json": _json_text(_blueprint(request)),
        PROJECT_STRUCTURE_PATH: _json_text(structure),
        DEPENDENCY_GRAPH_PATH: _json_text(dependencies),
        PROJECT_INSIGHTS_PATH: _json_text(
            {
                "project_structure": structure,
                "declared_dependencies": dependencies,
            }
        ),
    }
    for relative in managed_paths:
        _write_text(workspace, relative, special_content.get(relative, f"fixture:{relative}\n"))

    entries = []
    for relative in managed_paths:
        digest = hashlib.sha256((workspace / relative).read_bytes()).hexdigest()
        entries.append(
            {
                "path": relative,
                "sha256": digest,
                "ownership": "managed",
                "source_refs": ["approved-request"],
            }
        )
    digest_by_path = {entry["path"]: entry["sha256"] for entry in entries}
    manifest = {
        "schema_version": "1.1.0",
        "engine": "elmos.project-synthesis",
        "engine_version": "1.4.0",
        "status": "GENERATED",
        "files": entries,
        "graphs": [
            {
                "kind": "project-structure",
                "path": PROJECT_STRUCTURE_PATH,
                "schema_id": PROJECT_STRUCTURE_SCHEMA_ID,
                "sha256": digest_by_path[PROJECT_STRUCTURE_PATH],
            },
            {
                "kind": "declared-dependency",
                "path": DEPENDENCY_GRAPH_PATH,
                "schema_id": DEPENDENCY_GRAPH_SCHEMA_ID,
                "sha256": digest_by_path[DEPENDENCY_GRAPH_PATH],
            },
        ],
    }
    _write_text(workspace, ".elmos/generation-manifest.json", _json_text(manifest))
    return workspace, structure, dependencies


def _load_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _rebind_graph_digest(workspace: Path, relative: str) -> None:
    digest = hashlib.sha256((workspace / relative).read_bytes()).hexdigest()
    manifest_path = workspace / ".elmos/generation-manifest.json"
    manifest = _load_json(manifest_path)
    for entry in manifest["files"]:
        if entry["path"] == relative:
            entry["sha256"] = digest
    for entry in manifest["graphs"]:
        if entry["path"] == relative:
            entry["sha256"] = digest
    manifest_path.write_text(_json_text(manifest), encoding="utf-8")


def _application_languages(nodes: Iterable[dict[str, Any]]) -> set[str]:
    return {str(node["language"]) for node in nodes if node.get("kind") == "application" and "language" in node}


def test_all_eight_targets_are_complete_and_resolution_remains_not_run(tmp_path: Path) -> None:
    request = _approved_request()
    workspace, structure, dependencies = _write_workspace(tmp_path, request)

    assert _application_languages(structure["nodes"]) == set(SUPPORTED_LANGUAGES)
    assert {
        str(node["id"]).removeprefix("app:") for node in dependencies["nodes"] if node["kind"] == "application"
    } == set(SUPPORTED_LANGUAGES)
    assert structure["coverage"]["declared_application_count"] == 8
    assert structure["coverage"]["represented_application_count"] == 8
    assert structure["coverage"]["managed_file_count"] == len(_managed_paths(request))
    assert dependencies["complete"] is False
    assert dependencies["resolution"] == {"status": "NOT_RUN", "resolved_graph_refs": []}
    assert dependencies["issues"] == ["NATIVE_TRANSITIVE_RESOLUTION_NOT_RUN"]
    assert all("@" not in node["coordinate"] for node in dependencies["nodes"] if node["kind"] == "framework")

    validate_workspace_graphs(workspace)


def test_graph_rendering_is_deterministic_for_path_order_and_duplicates() -> None:
    request = _approved_request()
    paths = _managed_paths(request)

    first_structure = render_project_structure(request, paths)
    second_structure = render_project_structure(request, [*reversed(paths), paths[0], paths[-1]])

    assert first_structure == second_structure
    assert render_declared_dependency_graph(request) == render_declared_dependency_graph(request)
    assert first_structure["nodes"] == sorted(first_structure["nodes"], key=lambda node: node["id"])
    assert first_structure["edges"] == sorted(
        first_structure["edges"],
        key=lambda edge: (edge["from"], edge["to"], edge["type"]),
    )


def test_production_shared_roots_are_explicitly_classified(tmp_path: Path) -> None:
    request = _approved_request(production=True)
    paths = _managed_paths(request, production=True)

    structure = render_project_structure(request, paths)
    group_kinds = {
        str(node["path"]): str(node["kind"]) for node in structure["nodes"] if str(node["id"]).startswith("group:")
    }

    assert group_kinds["database"] == "database"
    assert group_kinds["observability"] == "observability"
    assert group_kinds["operations"] == "operations"
    assert group_kinds["security"] == "security"
    assert structure["coverage"]["status"] == "PASSED"
    assert structure["coverage"]["unclassified_paths"] == []
    assert _application_languages(structure["nodes"]) == set(SUPPORTED_LANGUAGES)

    workspace, _, _ = _write_workspace(tmp_path, request, production=True)
    validate_workspace_graphs(workspace)

    rendered_workspace = tmp_path / "production-workspace"
    generate_workspace(request.raw, rendered_workspace)
    validate_workspace_graphs(rendered_workspace)


def test_unknown_shared_root_still_fails_closed() -> None:
    request = _approved_request()

    with pytest.raises(ValueError, match="PROJECT_STRUCTURE_UNCLASSIFIED_ROOT:unknown-root"):
        render_project_structure(request, [*_managed_paths(request), "unknown-root/file.txt"])


def test_validation_rejects_a_dangling_edge_even_with_rebound_digest(tmp_path: Path) -> None:
    request = _approved_request()
    workspace, _, _ = _write_workspace(tmp_path, request)
    path = workspace / PROJECT_STRUCTURE_PATH
    structure = _load_json(path)
    structure["edges"].append({"from": "repository", "to": "missing", "type": "contains"})
    path.write_text(_json_text(structure), encoding="utf-8")
    _rebind_graph_digest(workspace, PROJECT_STRUCTURE_PATH)

    with pytest.raises(RuntimeError, match="PROJECT_GRAPH_EDGE_INVALID"):
        validate_workspace_graphs(workspace)


def test_validation_rejects_graph_digest_tampering(tmp_path: Path) -> None:
    request = _approved_request()
    workspace, _, _ = _write_workspace(tmp_path, request)
    path = workspace / PROJECT_STRUCTURE_PATH
    structure = _load_json(path)
    repository = next(node for node in structure["nodes"] if node["id"] == "repository")
    repository["label"] = "tampered-but-schema-valid"
    path.write_text(_json_text(structure), encoding="utf-8")

    with pytest.raises(RuntimeError, match="GENERATION_MANIFEST_GRAPH_DIGEST_INVALID"):
        validate_workspace_graphs(workspace)


def test_validation_rejects_path_escape_even_with_rebound_digest(tmp_path: Path) -> None:
    request = _approved_request()
    workspace, _, _ = _write_workspace(tmp_path, request)
    path = workspace / PROJECT_STRUCTURE_PATH
    structure = _load_json(path)
    application = next(node for node in structure["nodes"] if node["kind"] == "application")
    application["path"] = "../outside"
    path.write_text(_json_text(structure), encoding="utf-8")
    _rebind_graph_digest(workspace, PROJECT_STRUCTURE_PATH)

    with pytest.raises(RuntimeError, match="PROJECT_GRAPH_PATH_INVALID"):
        validate_workspace_graphs(workspace)


def test_validation_rejects_resolution_claim_even_with_rebound_digest(tmp_path: Path) -> None:
    request = _approved_request()
    workspace, _, _ = _write_workspace(tmp_path, request)
    path = workspace / DEPENDENCY_GRAPH_PATH
    dependencies = _load_json(path)
    dependencies["complete"] = True
    dependencies["resolution"] = {
        "status": "PASSED",
        "resolved_graph_refs": [".elmos/verification/resolved-dependencies.json"],
    }
    dependencies["issues"] = []
    path.write_text(_json_text(dependencies), encoding="utf-8")
    _rebind_graph_digest(workspace, DEPENDENCY_GRAPH_PATH)

    with pytest.raises(RuntimeError, match="DEPENDENCY_GRAPH_RESOLUTION_CLAIM_INVALID"):
        validate_workspace_graphs(workspace)


def test_validation_rejects_tampered_managed_source_before_native_execution(tmp_path: Path) -> None:
    request = _approved_request()
    workspace, _, _ = _write_workspace(tmp_path, request)
    (workspace / "java/pom.xml").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="GENERATION_MANIFEST_FILE_DIGEST_INVALID"):
        validate_workspace_graphs(workspace)


def test_validation_rejects_missing_managed_file_before_native_execution(tmp_path: Path) -> None:
    request = _approved_request()
    workspace, _, _ = _write_workspace(tmp_path, request)
    (workspace / "java/pom.xml").unlink()

    with pytest.raises(RuntimeError, match="GENERATION_MANIFEST_FILE_INVALID"):
        validate_workspace_graphs(workspace)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("path", "../outside.txt"),
        ("path", "java/"),
        ("ownership", "user-owned"),
    ),
)
def test_validation_rejects_unsafe_or_unmanaged_manifest_entry(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    request = _approved_request()
    workspace, _, _ = _write_workspace(tmp_path, request)
    manifest_path = workspace / ".elmos/generation-manifest.json"
    manifest = _load_json(manifest_path)
    manifest["files"][0][field] = value
    manifest_path.write_text(_json_text(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="GENERATION_MANIFEST_ENTRY_INVALID"):
        validate_workspace_graphs(workspace)


def test_validation_rejects_duplicate_manifest_path(tmp_path: Path) -> None:
    request = _approved_request()
    workspace, _, _ = _write_workspace(tmp_path, request)
    manifest_path = workspace / ".elmos/generation-manifest.json"
    manifest = _load_json(manifest_path)
    manifest["files"].append(dict(manifest["files"][0]))
    manifest_path.write_text(_json_text(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="GENERATION_MANIFEST_ENTRY_INVALID"):
        validate_workspace_graphs(workspace)


def test_validation_rejects_missing_required_manifest_entry(tmp_path: Path) -> None:
    request = _approved_request()
    workspace, _, _ = _write_workspace(tmp_path, request)
    manifest_path = workspace / ".elmos/generation-manifest.json"
    manifest = _load_json(manifest_path)
    manifest["files"] = [entry for entry in manifest["files"] if entry["path"] != PROJECT_INSIGHTS_PATH]
    manifest_path.write_text(_json_text(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="GENERATION_MANIFEST_REQUIRED_FILE_MISSING"):
        validate_workspace_graphs(workspace)


def test_validation_rejects_symlinked_manifest_file(tmp_path: Path) -> None:
    request = _approved_request()
    workspace, _, _ = _write_workspace(tmp_path, request)
    target = workspace / "java/pom.xml"
    target.unlink()
    target.symlink_to(workspace / "README.md")

    with pytest.raises(RuntimeError, match="GENERATION_MANIFEST_FILE_INVALID"):
        validate_workspace_graphs(workspace)


def test_validation_rejects_extra_or_rebound_graph_index(tmp_path: Path) -> None:
    request = _approved_request()
    workspace, _, _ = _write_workspace(tmp_path, request)
    manifest_path = workspace / ".elmos/generation-manifest.json"
    manifest = _load_json(manifest_path)
    manifest["graphs"].append(dict(manifest["graphs"][0]))
    manifest_path.write_text(_json_text(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="GENERATION_MANIFEST_GRAPH_INDEX_INVALID"):
        validate_workspace_graphs(workspace)

    manifest["graphs"] = manifest["graphs"][:-1]
    manifest["graphs"][0]["sha256"] = "0" * 64
    manifest_path.write_text(_json_text(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="GENERATION_MANIFEST_GRAPH_DIGEST_INVALID"):
        validate_workspace_graphs(workspace)


def test_validation_rejects_project_insights_graph_drift(tmp_path: Path) -> None:
    request = _approved_request()
    workspace, _, _ = _write_workspace(tmp_path, request)
    path = workspace / PROJECT_INSIGHTS_PATH
    insights = _load_json(path)
    insights["project_structure"]["coverage"]["status"] = "FAILED"
    path.write_text(_json_text(insights), encoding="utf-8")
    manifest_path = workspace / ".elmos/generation-manifest.json"
    manifest = _load_json(manifest_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    for entry in manifest["files"]:
        if entry["path"] == PROJECT_INSIGHTS_PATH:
            entry["sha256"] = digest
    manifest_path.write_text(_json_text(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="PROJECT_INSIGHTS_GRAPH_DRIFT"):
        validate_workspace_graphs(workspace)


@pytest.mark.parametrize(
    ("schema_name", "schema_id"),
    (
        ("project-structure-v1.schema.json", PROJECT_STRUCTURE_SCHEMA_ID),
        ("declared-dependency-graph-v1.schema.json", DEPENDENCY_GRAPH_SCHEMA_ID),
    ),
)
def test_graph_contract_schemas_are_strict(schema_name: str, schema_id: str) -> None:
    schema = _load_json(SCHEMA_ROOT / schema_name)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == schema_id
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["$defs"]["node"]["additionalProperties"] is False
    assert schema["$defs"]["edge"]["additionalProperties"] is False
