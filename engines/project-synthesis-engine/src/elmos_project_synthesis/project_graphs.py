from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .models import TARGET_PROFILES, SynthesisRequest

PROJECT_STRUCTURE_PATH = "requirements/project-structure.json"
DEPENDENCY_GRAPH_PATH = "requirements/declared-dependency-graph.json"
PROJECT_INSIGHTS_PATH = "requirements/project-insights.json"
PROJECT_STRUCTURE_SCHEMA_ID = "elmos.project-synthesis.project-structure.v1"
DEPENDENCY_GRAPH_SCHEMA_ID = "elmos.project-synthesis.declared-dependency-graph.v1"

_GRAPH_CONTRACTS = {
    PROJECT_STRUCTURE_PATH: ("project-structure", PROJECT_STRUCTURE_SCHEMA_ID),
    DEPENDENCY_GRAPH_PATH: ("declared-dependency", DEPENDENCY_GRAPH_SCHEMA_ID),
}
_GRAPH_PATHS = frozenset(_GRAPH_CONTRACTS)
_REQUIRED_MANAGED_PATHS = frozenset(
    {
        PROJECT_STRUCTURE_PATH,
        DEPENDENCY_GRAPH_PATH,
        PROJECT_INSIGHTS_PATH,
        "requirements/approved-request.json",
        "requirements/project-blueprint.json",
    }
)
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9:._-]{0,199}$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_SHARED_ROOT_KINDS = {
    ".github": "continuous-integration",
    "database": "database",
    "deploy": "deployment",
    "docs": "documentation",
    "observability": "observability",
    "operations": "operations",
    "requirements": "requirements",
    # scripts/projectctl.py is emitted for every request and is one of the
    # four files cli.py requires an archive to contain; scripts/ was simply
    # never classified, which failed every render_workspace closed.
    "scripts": "operations",
    "security": "security",
}
_BUILD_MANIFESTS = {
    "Cargo.lock",
    "Cargo.toml",
    "Directory.Build.props",
    "Directory.Packages.props",
    "build.gradle.kts",
    "composer.json",
    "composer.lock",
    "go.mod",
    "go.sum",
    "gradle.lockfile",
    "package.json",
    "pnpm-lock.yaml",
    "pom.xml",
    "pyproject.toml",
    "requirements.lock",
    "settings.gradle.kts",
}
_STRUCTURE_KINDS = frozenset(
    {
        *_SHARED_ROOT_KINDS.values(),
        "api-contract",
        "application",
        "application-support",
        "build-manifest",
        "configuration",
        "container",
        "repository",
        "repository-metadata",
        "source-root",
        "test-root",
    }
)
_DEPENDENCY_KINDS = frozenset({"application", "build-tool", "framework", "provider", "runtime"})
_DEPENDENCY_EDGE_TYPES = frozenset({"builds-with", "persists-to", "requires", "uses"})
_DEPENDENCY_VERSION_SOURCES = frozenset({"emitter-build-manifest", "project-blueprint", "runtime-manifest"})


def _safe_relative_path(value: str) -> bool:
    if value == ".":
        return True
    if (
        not value
        or len(value) > 1024
        or value.startswith("/")
        or "\\" in value
        or any(ord(character) < 32 for character in value)
    ):
        return False
    parts = value.split("/")
    return all(part not in {"", ".", ".."} for part in parts) and PurePosixPath(value).as_posix() == value


def _target_category(relative: str) -> str:
    parts = PurePosixPath(relative).parts
    name = parts[-1]
    lowered = tuple(part.lower() for part in parts)
    lower_name = name.lower()
    if name in _BUILD_MANIFESTS or name.endswith((".csproj", ".sln", ".slnx")):
        return "build-manifest"
    if lower_name in {"openapi.json", "openapi.yaml", "openapi.yml"}:
        return "api-contract"
    if lower_name == "dockerfile":
        return "container"
    if ".github" in lowered or "workflows" in lowered:
        return "continuous-integration"
    if any(part in {"test", "tests"} or part.endswith(".tests") for part in lowered) or (
        lower_name.startswith("test_")
        or lower_name.endswith(("_test.go", ".spec.ts", ".test.ts", "test.java", "tests.cs"))
    ):
        return "test-root"
    if any(part in {"app", "cmd", "source", "sources", "src"} for part in lowered) or lower_name.endswith(
        (".go", ".java", ".kt", ".php", ".py", ".rs", ".ts")
    ):
        return "source-root"
    if lower_name.startswith(".") or lower_name.endswith((".json", ".properties", ".toml", ".yaml", ".yml")):
        return "configuration"
    return "application-support"


def _group_paths(paths: Iterable[str], prefix: str) -> list[str]:
    return sorted(path for path in paths if path == prefix or path.startswith(f"{prefix}/"))


def render_project_structure(
    request: SynthesisRequest,
    managed_paths: Iterable[str],
) -> dict[str, Any]:
    supplied_paths = list(managed_paths)
    if not supplied_paths or any(not isinstance(path, str) or not _safe_relative_path(path) for path in supplied_paths):
        raise ValueError("PROJECT_STRUCTURE_PATHS_INVALID")
    paths = sorted(set(supplied_paths))
    target_directories = {str(TARGET_PROFILES[target.language]["directory"]): target for target in request.targets}
    shared_directory_roots = {
        PurePosixPath(path).parts[0]
        for path in paths
        if "/" in path and PurePosixPath(path).parts[0] not in target_directories
    }
    unclassified_roots = sorted(shared_directory_roots - set(_SHARED_ROOT_KINDS))
    if unclassified_roots:
        raise ValueError(f"PROJECT_STRUCTURE_UNCLASSIFIED_ROOT:{','.join(unclassified_roots)}")

    nodes: list[dict[str, Any]] = [
        {
            "id": "repository",
            "kind": "repository",
            "path": ".",
            "label": request.project_name,
            "ownership": "managed",
            "file_count": len(paths),
            "status": "REPRESENTED",
        }
    ]
    edges: list[dict[str, str]] = []
    classified_paths: set[str] = set()

    for root, kind in sorted(_SHARED_ROOT_KINDS.items()):
        matched = _group_paths(paths, root)
        if not matched:
            continue
        classified_paths.update(matched)
        node_id = f"group:{root}"
        nodes.append(
            {
                "id": node_id,
                "kind": kind,
                "path": root,
                "label": root,
                "ownership": "managed",
                "file_count": len(matched),
                "status": "REPRESENTED",
            }
        )
        edges.append({"from": "repository", "to": node_id, "type": "contains"})

    root_files = sorted(path for path in paths if "/" not in path)
    if root_files:
        classified_paths.update(root_files)
        nodes.append(
            {
                "id": "group:root-files",
                "kind": "repository-metadata",
                "path": ".",
                "label": "root files",
                "ownership": "managed",
                "file_count": len(root_files),
                "status": "REPRESENTED",
            }
        )
        edges.append({"from": "repository", "to": "group:root-files", "type": "contains"})

    for directory, target in sorted(target_directories.items()):
        target_paths = _group_paths(paths, directory)
        if not target_paths:
            raise ValueError(f"PROJECT_STRUCTURE_TARGET_EMPTY:{target.language}")
        classified_paths.update(target_paths)
        app_id = f"app:{target.language}"
        nodes.append(
            {
                "id": app_id,
                "kind": "application",
                "path": directory,
                "label": target.language,
                "language": target.language,
                "framework": target.framework,
                "runtime": target.runtime,
                "ownership": "managed",
                "file_count": len(target_paths),
                "status": "REPRESENTED",
            }
        )
        edges.append({"from": "repository", "to": app_id, "type": "contains"})
        categories: dict[str, list[str]] = {}
        for path in target_paths:
            relative = path.removeprefix(f"{directory}/")
            categories.setdefault(_target_category(relative), []).append(path)
        for category, category_paths in sorted(categories.items()):
            node_id = f"{app_id}:{category}"
            nodes.append(
                {
                    "id": node_id,
                    "kind": category,
                    "path": directory,
                    "label": category,
                    "language": target.language,
                    "ownership": "managed",
                    "file_count": len(category_paths),
                    "status": "REPRESENTED",
                }
            )
            edges.append({"from": app_id, "to": node_id, "type": "contains"})

    unclassified_paths = sorted(set(paths) - classified_paths)
    if unclassified_paths:
        raise ValueError(f"PROJECT_STRUCTURE_UNCLASSIFIED_PATH:{','.join(unclassified_paths)}")
    nodes.sort(key=lambda item: str(item["id"]))
    edges.sort(key=lambda item: (item["from"], item["to"], item["type"]))
    represented_applications = sum(node["kind"] == "application" for node in nodes)
    return {
        "schema_version": "1.0.0",
        "graph_kind": "elmos.project-structure",
        "project": {
            "id": request.raw["project"]["id"],
            "name": request.project_name,
            "repository_mode": "polyglot-monorepo",
            "approved_payload_sha256": request.raw["approval"]["approved_payload_sha256"],
        },
        "nodes": nodes,
        "edges": edges,
        "coverage": {
            "scope": "managed-generated-artifacts",
            "managed_file_count": len(paths),
            "classified_file_count": len(classified_paths),
            "declared_application_count": len(request.targets),
            "represented_application_count": represented_applications,
            "unclassified_paths": [],
            "status": "PASSED",
        },
    }


def _build_tool(language: str) -> tuple[str, str]:
    return {
        "csharp": ("dotnet-sdk", "10.0.301"),
        "go": ("go", "1.25.0"),
        "java": ("maven", "3.9.10"),
        "kotlin": ("gradle", "8.14.3"),
        "php": ("php", "8.4.12"),
        "python": ("uv", "0.11.16"),
        "rust": ("cargo", "1.89.0"),
        "typescript": ("pnpm", "10.12.4"),
    }[language]


def render_declared_dependency_graph(request: SynthesisRequest) -> dict[str, Any]:
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    for target in sorted(request.targets, key=lambda item: item.language):
        app_id = f"app:{target.language}"
        runtime_id = f"runtime:{target.language}:{target.runtime}"
        framework_id = f"framework:{target.language}:{target.framework}"
        tool, version = _build_tool(target.language)
        tool_id = f"build-tool:{target.language}:{tool}"
        nodes.extend(
            [
                {
                    "id": app_id,
                    "kind": "application",
                    "coordinate": target.language,
                    "version_source": "project-blueprint",
                },
                {
                    "id": runtime_id,
                    "kind": "runtime",
                    "coordinate": f"{target.language}@{target.runtime}",
                    "version_source": "project-blueprint",
                },
                {
                    "id": framework_id,
                    "kind": "framework",
                    "coordinate": target.framework,
                    "version_source": "emitter-build-manifest",
                },
                {
                    "id": tool_id,
                    "kind": "build-tool",
                    "coordinate": f"{tool}@{version}",
                    "version_source": "runtime-manifest",
                },
            ]
        )
        edges.extend(
            [
                {
                    "from": app_id,
                    "to": runtime_id,
                    "type": "requires",
                    "scope": "runtime",
                    "evidence_status": "DECLARED",
                },
                {
                    "from": app_id,
                    "to": framework_id,
                    "type": "uses",
                    "scope": "application",
                    "evidence_status": "DECLARED",
                },
                {
                    "from": app_id,
                    "to": tool_id,
                    "type": "builds-with",
                    "scope": "build",
                    "evidence_status": "DECLARED",
                },
            ]
        )
    if request.requires_database:
        nodes.append(
            {
                "id": "provider:postgresql:17.5",
                "kind": "provider",
                "coordinate": "postgresql@17.5",
                "version_source": "runtime-manifest",
            }
        )
        for target in sorted(request.targets, key=lambda item: item.language):
            edges.append(
                {
                    "from": f"app:{target.language}",
                    "to": "provider:postgresql:17.5",
                    "type": "persists-to",
                    "scope": "runtime",
                    "evidence_status": "DECLARED",
                }
            )
    return {
        "schema_version": "1.0.0",
        "graph_kind": "elmos.declared-dependency-graph",
        "project_id": request.raw["project"]["id"],
        "nodes": sorted(nodes, key=lambda item: item["id"]),
        "edges": sorted(edges, key=lambda item: (item["from"], item["to"], item["type"])),
        "resolution": {"status": "NOT_RUN", "resolved_graph_refs": []},
        "complete": False,
        "issues": ["NATIVE_TRANSITIVE_RESOLUTION_NOT_RUN"],
    }


def _read_json_object(path: Path, code: str) -> dict[str, Any]:
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 4_000_000:
            raise RuntimeError(code)
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(code) from error
    if not isinstance(loaded, dict):
        raise RuntimeError(code)
    return loaded


def _require_keys(
    value: Mapping[str, Any],
    *,
    required: frozenset[str],
    allowed: frozenset[str],
    code: str,
) -> None:
    keys = set(value)
    if not required <= keys or not keys <= allowed:
        raise RuntimeError(code)


def _validate_graph_core(graph: dict[str, Any], *, kind: str) -> None:
    if graph.get("schema_version") != "1.0.0" or graph.get("graph_kind") != kind:
        raise RuntimeError("PROJECT_GRAPH_IDENTITY_INVALID")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list) or not nodes:
        raise RuntimeError("PROJECT_GRAPH_SHAPE_INVALID")
    node_ids: set[str] = set()
    for node in nodes:
        if (
            not isinstance(node, dict)
            or not isinstance(node.get("id"), str)
            or _ID_PATTERN.fullmatch(node["id"]) is None
        ):
            raise RuntimeError("PROJECT_GRAPH_NODE_INVALID")
        if node["id"] in node_ids:
            raise RuntimeError("PROJECT_GRAPH_NODE_DUPLICATED")
        node_ids.add(node["id"])
        if isinstance(node.get("path"), str) and not _safe_relative_path(node["path"]):
            raise RuntimeError("PROJECT_GRAPH_PATH_INVALID")
    seen_edges: set[tuple[str, str, str]] = set()
    for edge in edges:
        if (
            not isinstance(edge, dict)
            or not isinstance(edge.get("from"), str)
            or not isinstance(edge.get("to"), str)
            or not isinstance(edge.get("type"), str)
            or edge["from"] not in node_ids
            or edge["to"] not in node_ids
            or edge["from"] == edge["to"]
        ):
            raise RuntimeError("PROJECT_GRAPH_EDGE_INVALID")
        edge_key = (edge["from"], edge["to"], edge["type"])
        if edge_key in seen_edges:
            raise RuntimeError("PROJECT_GRAPH_EDGE_DUPLICATED")
        seen_edges.add(edge_key)


def _validate_structure_graph(graph: dict[str, Any]) -> None:
    _require_keys(
        graph,
        required=frozenset({"schema_version", "graph_kind", "project", "nodes", "edges", "coverage"}),
        allowed=frozenset({"schema_version", "graph_kind", "project", "nodes", "edges", "coverage"}),
        code="PROJECT_STRUCTURE_SHAPE_INVALID",
    )
    _validate_graph_core(graph, kind="elmos.project-structure")
    project = graph["project"]
    if not isinstance(project, dict):
        raise RuntimeError("PROJECT_STRUCTURE_PROJECT_INVALID")
    _require_keys(
        project,
        required=frozenset({"id", "name", "repository_mode", "approved_payload_sha256"}),
        allowed=frozenset({"id", "name", "repository_mode", "approved_payload_sha256"}),
        code="PROJECT_STRUCTURE_PROJECT_INVALID",
    )
    if (
        not isinstance(project["id"], str)
        or not project["id"]
        or not isinstance(project["name"], str)
        or not project["name"]
        or project["repository_mode"] != "polyglot-monorepo"
        or not isinstance(project["approved_payload_sha256"], str)
        or _DIGEST_PATTERN.fullmatch(project["approved_payload_sha256"]) is None
    ):
        raise RuntimeError("PROJECT_STRUCTURE_PROJECT_INVALID")

    nodes = graph["nodes"]
    assert isinstance(nodes, list)
    common_keys = frozenset({"id", "kind", "path", "label", "ownership", "file_count", "status"})
    allowed_keys = common_keys | {"language", "framework", "runtime"}
    repository_count = 0
    application_count = 0
    for node in nodes:
        assert isinstance(node, dict)
        _require_keys(
            node,
            required=common_keys,
            allowed=allowed_keys,
            code="PROJECT_STRUCTURE_NODE_INVALID",
        )
        file_count = node["file_count"]
        if (
            node["kind"] not in _STRUCTURE_KINDS
            or not isinstance(node["path"], str)
            or not _safe_relative_path(node["path"])
            or not isinstance(node["label"], str)
            or not node["label"]
            or node["ownership"] != "managed"
            or node["status"] != "REPRESENTED"
            or isinstance(file_count, bool)
            or not isinstance(file_count, int)
            or file_count < 0
        ):
            raise RuntimeError("PROJECT_STRUCTURE_NODE_INVALID")
        if node["kind"] == "repository":
            repository_count += 1
            if node["id"] != "repository" or node["path"] != "." or file_count < 1:
                raise RuntimeError("PROJECT_STRUCTURE_NODE_INVALID")
        if node["kind"] == "application":
            application_count += 1
            if (
                not {"language", "framework", "runtime"} <= set(node)
                or node["language"] not in TARGET_PROFILES
                or not isinstance(node["framework"], str)
                or not isinstance(node["runtime"], str)
                or file_count < 1
            ):
                raise RuntimeError("PROJECT_STRUCTURE_NODE_INVALID")
        elif "framework" in node or "runtime" in node:
            raise RuntimeError("PROJECT_STRUCTURE_NODE_INVALID")
        if "language" in node and node["language"] not in TARGET_PROFILES:
            raise RuntimeError("PROJECT_STRUCTURE_NODE_INVALID")
    if repository_count != 1 or application_count < 1:
        raise RuntimeError("PROJECT_STRUCTURE_NODE_INVALID")
    if nodes != sorted(nodes, key=lambda item: str(item["id"])):
        raise RuntimeError("PROJECT_GRAPH_ORDER_INVALID")

    edges = graph["edges"]
    assert isinstance(edges, list)
    for edge in edges:
        assert isinstance(edge, dict)
        _require_keys(
            edge,
            required=frozenset({"from", "to", "type"}),
            allowed=frozenset({"from", "to", "type"}),
            code="PROJECT_STRUCTURE_EDGE_INVALID",
        )
        if edge["type"] != "contains":
            raise RuntimeError("PROJECT_STRUCTURE_EDGE_INVALID")
    if edges != sorted(edges, key=lambda item: (item["from"], item["to"], item["type"])):
        raise RuntimeError("PROJECT_GRAPH_ORDER_INVALID")

    coverage = graph["coverage"]
    if not isinstance(coverage, dict):
        raise RuntimeError("PROJECT_STRUCTURE_COVERAGE_INVALID")
    coverage_keys = frozenset(
        {
            "scope",
            "managed_file_count",
            "classified_file_count",
            "declared_application_count",
            "represented_application_count",
            "unclassified_paths",
            "status",
        }
    )
    _require_keys(
        coverage,
        required=coverage_keys,
        allowed=coverage_keys,
        code="PROJECT_STRUCTURE_COVERAGE_INVALID",
    )
    count_fields = (
        "managed_file_count",
        "classified_file_count",
        "declared_application_count",
        "represented_application_count",
    )
    if (
        coverage["scope"] != "managed-generated-artifacts"
        or coverage["status"] != "PASSED"
        or coverage["unclassified_paths"] != []
        or any(
            isinstance(coverage[field], bool) or not isinstance(coverage[field], int) or coverage[field] < 0
            for field in count_fields
        )
        or coverage["managed_file_count"] != coverage["classified_file_count"]
        or coverage["declared_application_count"] != application_count
        or coverage["represented_application_count"] != application_count
    ):
        raise RuntimeError("PROJECT_STRUCTURE_COVERAGE_INVALID")


def _validate_dependency_graph(graph: dict[str, Any]) -> None:
    top_keys = frozenset(
        {"schema_version", "graph_kind", "project_id", "nodes", "edges", "resolution", "complete", "issues"}
    )
    _require_keys(
        graph,
        required=top_keys,
        allowed=top_keys,
        code="DEPENDENCY_GRAPH_SHAPE_INVALID",
    )
    _validate_graph_core(graph, kind="elmos.declared-dependency-graph")
    if not isinstance(graph["project_id"], str) or not graph["project_id"]:
        raise RuntimeError("DEPENDENCY_GRAPH_PROJECT_INVALID")
    nodes = graph["nodes"]
    assert isinstance(nodes, list)
    node_keys = frozenset({"id", "kind", "coordinate", "version_source"})
    for node in nodes:
        assert isinstance(node, dict)
        _require_keys(
            node,
            required=node_keys,
            allowed=node_keys,
            code="DEPENDENCY_GRAPH_NODE_INVALID",
        )
        if (
            node["kind"] not in _DEPENDENCY_KINDS
            or not isinstance(node["coordinate"], str)
            or not node["coordinate"]
            or node["version_source"] not in _DEPENDENCY_VERSION_SOURCES
        ):
            raise RuntimeError("DEPENDENCY_GRAPH_NODE_INVALID")
    if nodes != sorted(nodes, key=lambda item: str(item["id"])):
        raise RuntimeError("PROJECT_GRAPH_ORDER_INVALID")

    edges = graph["edges"]
    assert isinstance(edges, list)
    edge_keys = frozenset({"from", "to", "type", "scope", "evidence_status"})
    for edge in edges:
        assert isinstance(edge, dict)
        _require_keys(
            edge,
            required=edge_keys,
            allowed=edge_keys,
            code="DEPENDENCY_GRAPH_EDGE_INVALID",
        )
        if (
            edge["type"] not in _DEPENDENCY_EDGE_TYPES
            or not isinstance(edge["scope"], str)
            or not edge["scope"]
            or edge["evidence_status"] != "DECLARED"
        ):
            raise RuntimeError("DEPENDENCY_GRAPH_EDGE_INVALID")
    if edges != sorted(edges, key=lambda item: (item["from"], item["to"], item["type"])):
        raise RuntimeError("PROJECT_GRAPH_ORDER_INVALID")
    if (
        graph["complete"] is not False
        or graph["resolution"] != {"status": "NOT_RUN", "resolved_graph_refs": []}
        or graph["issues"] != ["NATIVE_TRANSITIVE_RESOLUTION_NOT_RUN"]
    ):
        raise RuntimeError("DEPENDENCY_GRAPH_RESOLUTION_CLAIM_INVALID")


def _confined_existing_path(root: Path, relative: str, *, require_file: bool) -> Path:
    if not _safe_relative_path(relative):
        raise RuntimeError("PROJECT_GRAPH_PATH_INVALID")
    candidate = root
    if relative != ".":
        for part in PurePosixPath(relative).parts:
            candidate /= part
            if candidate.is_symlink():
                raise RuntimeError("PROJECT_GRAPH_PATH_INVALID")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise RuntimeError("PROJECT_GRAPH_PATH_INVALID") from error
    if resolved != root and not resolved.is_relative_to(root):
        raise RuntimeError("PROJECT_GRAPH_PATH_INVALID")
    if require_file and not candidate.is_file():
        raise RuntimeError("PROJECT_GRAPH_PATH_INVALID")
    return candidate


def _manifest_files(root: Path, manifest: dict[str, Any]) -> dict[str, str]:
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("GENERATION_MANIFEST_FILES_INVALID")
    files: dict[str, str] = {}
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"path", "sha256", "ownership", "source_refs"}
            or not isinstance(entry.get("path"), str)
            or not _safe_relative_path(entry["path"])
            or not isinstance(entry.get("sha256"), str)
            or _DIGEST_PATTERN.fullmatch(entry["sha256"]) is None
            or entry.get("ownership") != "managed"
            or not isinstance(entry.get("source_refs"), list)
            or not entry["source_refs"]
            or any(not isinstance(ref, str) or not ref for ref in entry["source_refs"])
            or entry["path"] in files
        ):
            raise RuntimeError("GENERATION_MANIFEST_ENTRY_INVALID")
        relative = entry["path"]
        try:
            path = _confined_existing_path(root, relative, require_file=True)
        except RuntimeError as error:
            raise RuntimeError("GENERATION_MANIFEST_FILE_INVALID") from error
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_digest != entry["sha256"]:
            if relative in _GRAPH_PATHS:
                raise RuntimeError("GENERATION_MANIFEST_GRAPH_DIGEST_INVALID")
            raise RuntimeError("GENERATION_MANIFEST_FILE_DIGEST_INVALID")
        files[relative] = actual_digest
    if list(files) != sorted(files):
        raise RuntimeError("GENERATION_MANIFEST_FILES_ORDER_INVALID")
    if not _REQUIRED_MANAGED_PATHS <= set(files):
        raise RuntimeError("GENERATION_MANIFEST_REQUIRED_FILE_MISSING")
    return files


def _validate_graph_index(manifest: dict[str, Any], files: Mapping[str, str]) -> None:
    graph_entries = manifest.get("graphs")
    if not isinstance(graph_entries, list) or len(graph_entries) != len(_GRAPH_CONTRACTS):
        raise RuntimeError("GENERATION_MANIFEST_GRAPH_INDEX_INVALID")
    indexed: dict[str, dict[str, Any]] = {}
    for entry in graph_entries:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"kind", "path", "schema_id", "sha256"}
            or not isinstance(entry.get("path"), str)
            or entry["path"] in indexed
        ):
            raise RuntimeError("GENERATION_MANIFEST_GRAPH_INDEX_INVALID")
        indexed[entry["path"]] = entry
    if set(indexed) != set(_GRAPH_CONTRACTS):
        raise RuntimeError("GENERATION_MANIFEST_GRAPH_INDEX_INVALID")
    for path, (kind, schema_id) in _GRAPH_CONTRACTS.items():
        entry = indexed[path]
        if entry["kind"] != kind or entry["schema_id"] != schema_id or entry["sha256"] != files.get(path):
            raise RuntimeError("GENERATION_MANIFEST_GRAPH_DIGEST_INVALID")


def _blueprint_languages(blueprint: dict[str, Any]) -> tuple[str, ...]:
    applications = blueprint.get("applications")
    if not isinstance(applications, list) or not applications:
        raise RuntimeError("PROJECT_BLUEPRINT_APPLICATIONS_INVALID")
    languages: list[str] = []
    for application in applications:
        if (
            not isinstance(application, dict)
            or not isinstance(application.get("language"), str)
            or application["language"] not in TARGET_PROFILES
            or application["language"] in languages
        ):
            raise RuntimeError("PROJECT_BLUEPRINT_APPLICATIONS_INVALID")
        languages.append(application["language"])
    return tuple(languages)


def validate_workspace_graphs(workspace: Path) -> None:
    root = workspace.resolve(strict=True)
    manifest_path = _confined_existing_path(
        root,
        ".elmos/generation-manifest.json",
        require_file=True,
    )
    manifest = _read_json_object(manifest_path, "GENERATION_MANIFEST_INVALID")
    files = _manifest_files(root, manifest)
    _validate_graph_index(manifest, files)

    structure = _read_json_object(root / PROJECT_STRUCTURE_PATH, "PROJECT_STRUCTURE_INVALID")
    dependencies = _read_json_object(root / DEPENDENCY_GRAPH_PATH, "DEPENDENCY_GRAPH_INVALID")
    insights = _read_json_object(root / PROJECT_INSIGHTS_PATH, "PROJECT_INSIGHTS_INVALID")
    blueprint = _read_json_object(
        root / "requirements" / "project-blueprint.json",
        "PROJECT_BLUEPRINT_INVALID",
    )
    approved = _read_json_object(
        root / "requirements" / "approved-request.json",
        "APPROVED_REQUEST_INVALID",
    )
    _validate_structure_graph(structure)
    _validate_dependency_graph(dependencies)
    if insights.get("project_structure") != structure or insights.get("declared_dependencies") != dependencies:
        raise RuntimeError("PROJECT_INSIGHTS_GRAPH_DRIFT")

    coverage = structure["coverage"]
    assert isinstance(coverage, dict)
    if coverage["managed_file_count"] != len(files):
        raise RuntimeError("PROJECT_STRUCTURE_MANIFEST_COVERAGE_INVALID")

    for node in structure["nodes"]:
        assert isinstance(node, dict)
        _confined_existing_path(root, node["path"], require_file=False)

    try:
        request = SynthesisRequest.from_mapping(approved)
    except ValueError as error:
        raise RuntimeError("APPROVED_REQUEST_INVALID") from error
    blueprint_languages = _blueprint_languages(blueprint)
    request_languages = tuple(target.language for target in request.targets)
    if blueprint_languages != request_languages:
        raise RuntimeError("PROJECT_GRAPH_APPLICATION_COVERAGE_INVALID")
    project = blueprint.get("project")
    if (
        not isinstance(project, dict)
        or project.get("id") != request.raw["project"]["id"]
        or project.get("name") != request.project_name
    ):
        raise RuntimeError("PROJECT_BLUEPRINT_PROJECT_INVALID")

    try:
        expected_structure = render_project_structure(request, files)
    except ValueError as error:
        raise RuntimeError("PROJECT_STRUCTURE_MANIFEST_CONTENT_INVALID") from error
    expected_dependencies = render_declared_dependency_graph(request)
    if structure != expected_structure:
        raise RuntimeError("PROJECT_STRUCTURE_CONTENT_INVALID")
    if dependencies != expected_dependencies:
        raise RuntimeError("DEPENDENCY_GRAPH_CONTENT_INVALID")

    manifest_schema = manifest.get("schema_version")
    if manifest_schema not in {"1.1.0", "1.2.0"}:
        raise RuntimeError("GENERATION_MANIFEST_SCHEMA_INVALID")
    if manifest_schema == "1.2.0":
        # Local import avoids making the graph primitives depend on the
        # higher-level supply-chain collector during module initialization.
        from .models import p0_request_blockers, p0_scope_payload
        from .supply_chain import SBOM_PATH, build_dependency_sbom, canonical_json, sbom_status, sha256_bytes

        if SBOM_PATH not in files:
            raise RuntimeError("GENERATION_MANIFEST_SBOM_MISSING")
        sbom = _read_json_object(root / SBOM_PATH, "GENERATION_SBOM_INVALID")
        managed_content = {
            path: (root / path).read_text(encoding="utf-8")
            for path in files
            if path != SBOM_PATH
        }
        if sbom != build_dependency_sbom(request, managed_content):
            raise RuntimeError("GENERATION_SBOM_CONTENT_INVALID")
        supply_chain = manifest.get("supply_chain")
        p0_scope = manifest.get("p0_launch_scope")
        expected_scope = p0_scope_payload()
        expected_scope_sha256 = sha256_bytes(canonical_json(expected_scope))
        if p0_scope != {
            "id": expected_scope["scope_id"],
            "sha256": expected_scope_sha256,
            "request_status": "IN_SCOPE" if not p0_request_blockers(request) else "OUT_OF_SCOPE",
            "blockers": p0_request_blockers(request),
        }:
            raise RuntimeError("GENERATION_MANIFEST_P0_SCOPE_INVALID")
        if supply_chain != {
            "sbom": {
                "path": SBOM_PATH,
                "format": "CycloneDX",
                "spec_version": "1.6",
                "sha256": files[SBOM_PATH],
                "transitive_inventory_status": sbom_status(sbom, "elmos:transitive-inventory-status"),
                "artifact_integrity_status": sbom_status(sbom, "elmos:artifact-integrity-status"),
                "dependency_graph_status": sbom_status(sbom, "elmos:dependency-graph-status"),
            },
            "release_manifest_status": "NOT_CREATED",
            "release_signature_status": "NOT_RUN",
            "trusted_root_status": "NOT_RUN",
        }:
            raise RuntimeError("GENERATION_MANIFEST_SUPPLY_CHAIN_INVALID")
