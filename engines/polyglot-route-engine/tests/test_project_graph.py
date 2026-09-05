from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from elmos_polyglot_route.project_graph import (
    SUPPORTED_LANGUAGES,
    EdgeKind,
    EvidenceStatus,
    FileRole,
    ProjectGraphError,
    build_project_graph,
    verify_project_graph,
    write_project_graph,
)


def _nodes(graph: dict[str, object]) -> list[dict[str, object]]:
    value = graph["nodes"]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return value


def _edges(graph: dict[str, object]) -> list[dict[str, object]]:
    value = graph["edges"]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return value


def _diagnostics(graph: dict[str, object]) -> list[dict[str, object]]:
    value = graph["diagnostic_obligations"]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return value


def _by_path(graph: dict[str, object], path: str, kind: str) -> dict[str, object]:
    return next(node for node in _nodes(graph) if node["kind"] == kind and node["path"] == path)


def test_python_ast_builds_stable_file_module_symbol_and_import_graph(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    (repository / "src" / "shop").mkdir(parents=True)
    (repository / "src" / "shop" / "prices.py").write_text(
        "import json\nfrom .tax import rate\n\n"
        "class Price:\n"
        "    def total(self, amount: int) -> int:\n"
        "        return amount + rate()\n",
        encoding="utf-8",
    )
    (repository / "src" / "shop" / "tax.py").write_text(
        "def rate() -> int:\n    return 2\n",
        encoding="utf-8",
    )

    first = build_project_graph(repository, "local:shop")
    second = build_project_graph(repository, "local:shop")

    assert first == second
    assert verify_project_graph(first)
    assert first["repository_complete"] is False
    assert first["graph_id"] == f"elmos:project-graph:sha256:{first['graph_sha256']}"
    assert {item["code"] for item in _diagnostics(first)} == {
        "PYTHON_CLASS_SYMBOL_CONVERSION_UNCOVERED",
        "PYTHON_NESTED_SYMBOL_CONVERSION_UNCOVERED",
        "PYTHON_TOP_LEVEL_EFFECT_CONVERSION_UNCOVERED",
    }
    assert len({node["id"] for node in _nodes(first)}) == len(_nodes(first))
    assert len({edge["id"] for edge in _edges(first)}) == len(_edges(first))

    price_file = _by_path(first, "src/shop/prices.py", "file")
    price_module = _by_path(first, "src/shop/prices.py", "module")
    symbols = [node for node in _nodes(first) if node["kind"] == "symbol"]
    assert {node["name"] for node in symbols} == {"Price", "total", "rate"}
    assert all(node["source_location"]["start_line"] is not None for node in symbols)
    coverage_nodes = [node for node in _nodes(first) if node["kind"] in {"symbol", "effect"}]
    coverage_keys = [node["attributes"]["coverage_key"] for node in coverage_nodes]
    assert len(coverage_keys) == len(set(coverage_keys)) == 5
    assert all(
        node["attributes"]["conversion_coverage_requirement"] == "REQUIRED"
        for node in coverage_nodes
    )

    contains = [edge for edge in _edges(first) if edge["kind"] == EdgeKind.CONTAINS]
    assert any(edge["source"] == price_file["id"] and edge["target"] == price_module["id"] for edge in contains)
    imports = [edge for edge in _edges(first) if edge["kind"] == EdgeKind.IMPORTS]
    assert {edge["attributes"]["resolution"] for edge in imports} == {"internal-exact", "stdlib-exact"}
    assert all(edge["source_location"]["start_line"] is not None for edge in imports)


def test_path_based_ids_survive_content_change_while_graph_address_changes(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "pricing.py"
    source.write_text("def total(value: int) -> int:\n    return value\n", encoding="utf-8")
    before = build_project_graph(repository, "local:stable-id")
    before_file = _by_path(before, "pricing.py", "file")
    before_module = _by_path(before, "pricing.py", "module")
    before_symbol = next(node for node in _nodes(before) if node["kind"] == "symbol")

    source.write_text("\n\ndef total(value: int) -> int:\n    return value + 1\n", encoding="utf-8")
    after = build_project_graph(repository, "local:stable-id")

    assert _by_path(after, "pricing.py", "file")["id"] == before_file["id"]
    assert _by_path(after, "pricing.py", "module")["id"] == before_module["id"]
    assert next(node for node in _nodes(after) if node["kind"] == "symbol")["id"] == before_symbol["id"]
    assert after["snapshot_sha256"] != before["snapshot_sha256"]
    assert after["graph_sha256"] != before["graph_sha256"]
    assert verify_project_graph(after)


def test_real_json_toml_and_xml_parsers_emit_typed_build_dependencies(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "package.json").write_text(
        json.dumps({"dependencies": {"react": "18.3.1"}, "devDependencies": {"vitest": "2.0.0"}}),
        encoding="utf-8",
    )
    (repository / "pyproject.toml").write_text(
        '[project]\nname = "sample"\ndependencies = ["requests>=2.32"]\n',
        encoding="utf-8",
    )
    (repository / "pom.xml").write_text(
        "<project><dependencies><dependency><groupId>org.example</groupId>"
        "<artifactId>core</artifactId><version>1.2.3</version>"
        "</dependency></dependencies></project>",
        encoding="utf-8",
    )

    graph = build_project_graph(repository, "local:descriptors")

    assert graph["repository_complete"] is False
    assert {
        item["code"] for item in _diagnostics(graph)
    } == {"BUILD_DESCRIPTOR_MIGRATION_NOT_RUN"}
    descriptor_nodes = [node for node in _nodes(graph) if node["kind"] == "file"]
    assert {node["attributes"]["descriptor_parser"] for node in descriptor_nodes} == {
        "python-json",
        "python-tomllib",
        "python-xml-elementtree-bounded",
    }
    dependency_edges = [edge for edge in _edges(graph) if edge["kind"] == EdgeKind.BUILD_DEPENDENCY]
    dependency_names = {
        next(node["name"] for node in _nodes(graph) if node["id"] == edge["target"]) for edge in dependency_edges
    }
    assert dependency_names == {"react", "vitest", "requests", "org.example:core"}
    assert all(edge["evidence_status"] == EvidenceStatus.PASSED for edge in dependency_edges)


def test_parsed_descriptors_and_resources_remain_blocking_until_target_migration_runs(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    (repository / "web").mkdir(parents=True)
    (repository / "tests").mkdir()
    (repository / "pyproject.toml").write_text(
        '[project]\nname = "sample"\n',
        encoding="utf-8",
    )
    (repository / "settings.yaml").write_text("enabled: true\n", encoding="utf-8")
    (repository / "web" / "index.html").write_text("<main>sample</main>\n", encoding="utf-8")
    (repository / "tests" / "fixture.json").write_text('{"value": 1}\n', encoding="utf-8")

    graph = build_project_graph(repository, "local:unmigrated-artifacts")
    codes = [item["code"] for item in _diagnostics(graph)]

    assert graph["repository_complete"] is False
    assert codes.count("BUILD_DESCRIPTOR_MIGRATION_NOT_RUN") == 1
    assert codes.count("RESOURCE_MIGRATION_NOT_RUN") == 3
    files = [node for node in _nodes(graph) if node["kind"] == "file"]
    assert all(node["attributes"]["migration_status"] == EvidenceStatus.NOT_RUN for node in files)


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("package.json", '{"dependencies":{"one":"1","one":"2"}}'),
        ("package.json", '{"threshold": NaN}'),
        ("pyproject.toml", "[project\nname = 'broken'"),
        ("pom.xml", "<!DOCTYPE project [<!ENTITY x 'unsafe'>]><project>&x;</project>"),
    ],
)
def test_invalid_or_unsafe_structured_descriptors_fail_closed(
    tmp_path: Path,
    filename: str,
    content: str,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / filename).write_text(content, encoding="utf-8")

    graph = build_project_graph(repository, f"local:invalid:{filename}")

    assert graph["repository_complete"] is False
    assert any(item["code"] == "BUILD_DESCRIPTOR_PARSE_FAILED" for item in _diagnostics(graph))
    assert all(item["blocks_repository_complete"] is True for item in _diagnostics(graph))


def test_real_format_parse_does_not_claim_unsupported_build_schema_semantics(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "tsconfig.json").write_text('{"compilerOptions": {"strict": true}}', encoding="utf-8")

    graph = build_project_graph(repository, "local:unsupported-build-schema")
    descriptor = _by_path(graph, "tsconfig.json", "file")

    assert descriptor["attributes"]["descriptor_parser"] == "python-json"
    assert descriptor["attributes"]["descriptor_parse_status"] == EvidenceStatus.PASSED
    assert descriptor["attributes"]["descriptor_semantic_status"] == EvidenceStatus.NOT_RUN
    assert graph["repository_complete"] is False
    assert any(item["code"] == "BUILD_DESCRIPTOR_SEMANTIC_INDEX_NOT_RUN" for item in _diagnostics(graph))


def test_thirteen_non_python_languages_are_classified_but_semantics_stay_not_run(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    sources = {
        "sample.cpp": "int main() { return 0; }",
        "Sample.cs": "class Sample {}",
        "sample.go": "package sample",
        "Sample.java": "class Sample {}",
        "sample.js": "export function sample() {}",
        "sample.kt": "fun sample() {}",
        "sample.m": "int sample(void) { return 0; }",
        "sample.php": "<?php function sample(): void {}",
        "sample.rs": "fn sample() {}",
        "sample.swift": "func sample() {}",
        "sample.ts": "export function sample(): void {}",
        "sample.tsx": "export function sample(): void {}",
        "sample.dart": "void sample() {}",
    }
    for filename, content in sources.items():
        (repository / filename).write_text(content, encoding="utf-8")
    (repository / "package.json").write_text(
        json.dumps({"type": "module"}),
        encoding="utf-8",
    )

    graph = build_project_graph(repository, "local:fourteen-language-boundary")

    assert set(graph["supported_languages"]) == set(SUPPORTED_LANGUAGES)
    assert graph["repository_complete"] is False
    modules = [node for node in _nodes(graph) if node["kind"] == "module"]
    assert len(modules) == 13
    assert {node["language"] for node in modules} == set(SUPPORTED_LANGUAGES) - {"python"}
    assert all(node["attributes"]["semantic_index_status"] == EvidenceStatus.NOT_RUN for node in modules)
    obligations = [item for item in _diagnostics(graph) if item["code"] == "COMPILER_SEMANTIC_INDEX_NOT_RUN"]
    assert len(obligations) == 13
    assert {item["verification_status"] for item in obligations} == {EvidenceStatus.NOT_RUN}
    other_languages = graph["indexers"]["other_languages"]
    assert other_languages["status"] == EvidenceStatus.NOT_RUN
    assert other_languages["module_inventory_count"] == 0
    assert other_languages["required_module_inventory_count"] == 13
    assert other_languages["inventory_coverage_complete"] is False


def test_supplied_non_python_inventory_must_cover_every_matching_source_file(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    first_content = "package sample\n\nfunc First(value int64) int64 { return value }\n"
    second_content = "package sample\n\nfunc Second(value int64) int64 { return value }\n"
    (repository / "first.go").write_text(first_content, encoding="utf-8")
    (repository / "second.go").write_text(second_content, encoding="utf-8")
    discovery = {
        "kind": "elmos.repository-discovery-report",
        "repository_ref": "local:partial-go-inventory",
        "profile": "typed-pure-function-v1",
        "source_language": "go",
        "module_inventories": [
            {
                "path": "first.go",
                "language": "go",
                "source_sha256": hashlib.sha256(first_content.encode("utf-8")).hexdigest(),
                "profile": "typed-pure-module-v1",
                "enumeration_status": "PASSED",
                "analyzer": "go/parser+go/types",
                "subjects": [],
                "diagnostics": [],
            }
        ],
    }

    with pytest.raises(
        ProjectGraphError,
        match=r"^SEMANTIC_DISCOVERY_INVENTORY_COVERAGE_INVALID$",
    ):
        build_project_graph(
            repository,
            "local:partial-go-inventory",
            discovery,
        )


def test_test_resource_and_unknown_files_have_explicit_typed_edges_and_unknown_blocks(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    (repository / "tests").mkdir(parents=True)
    (repository / "tests" / "test_sample.py").write_text("def test_sample() -> None:\n    pass\n", encoding="utf-8")
    (repository / "config.json").write_text('{"enabled": true}', encoding="utf-8")
    (repository / "opaque.blobx").write_bytes(b"opaque")

    graph = build_project_graph(repository, "local:file-roles")

    inventory = graph["inventory"]
    assert inventory["file_count"] == inventory["classified_file_count"] == 3
    assert inventory["role_counts"][FileRole.TEST] == 1
    assert inventory["role_counts"][FileRole.RESOURCE] == 1
    assert inventory["role_counts"][FileRole.UNKNOWN] == 1
    assert any(edge["kind"] == EdgeKind.TEST for edge in _edges(graph))
    assert any(edge["kind"] == EdgeKind.RESOURCE for edge in _edges(graph))
    assert graph["repository_complete"] is False
    assert any(item["code"] == "FILE_CLASSIFICATION_UNKNOWN" for item in _diagnostics(graph))


def test_unresolved_and_dynamic_python_imports_are_diagnostic_obligations(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "plugin.py").write_text(
        "import vendor_sdk\nimport importlib\n\ndef load(name: str):\n    return importlib.import_module(name)\n",
        encoding="utf-8",
    )

    graph = build_project_graph(repository, "local:dynamic-import")
    codes = {item["code"] for item in _diagnostics(graph)}

    assert graph["repository_complete"] is False
    assert "PYTHON_IMPORT_TARGET_UNKNOWN" in codes
    assert "PYTHON_DYNAMIC_IMPORT_REQUIRES_EVIDENCE" in codes
    unresolved = next(node for node in _nodes(graph) if node["kind"] == "unresolved-import")
    assert unresolved["attributes"]["resolution_status"] == EvidenceStatus.UNKNOWN


def test_file_symlink_is_never_followed_and_blocks_completeness(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET = 'must not be read'\n", encoding="utf-8")
    (repository / "linked.py").symlink_to(outside)

    graph = build_project_graph(repository, "local:symlink")
    linked = _by_path(graph, "linked.py", "file")

    assert linked["attributes"]["sha256"] is None
    assert linked["attributes"]["read_status"] == EvidenceStatus.NOT_RUN
    assert linked["attributes"]["role"] == FileRole.UNKNOWN
    assert graph["repository_complete"] is False
    assert {item["code"] for item in _diagnostics(graph)} >= {
        "FILE_NOT_SAFELY_READ",
        "FILE_CLASSIFICATION_UNKNOWN",
        "INVENTORY_ENTRY_NOT_READ",
    }


def test_ignored_directory_scope_is_explicit_and_blocks_repository_completeness(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    (repository / "vendor").mkdir(parents=True)
    (repository / "main.py").write_text(
        "def value() -> int:\n    return 1\n",
        encoding="utf-8",
    )
    (repository / "vendor" / "custom.py").write_text(
        "def hidden() -> int:\n    return 2\n",
        encoding="utf-8",
    )

    graph = build_project_graph(repository, "local:ignored-source-scope")

    assert graph["repository_complete"] is False
    assert graph["inventory"]["excluded_count"] == 1
    assert graph["inventory"]["excluded_entries"] == [
        {
            "path": "vendor",
            "reason": "IGNORED_DIRECTORY_SCOPE_NOT_VERIFIED",
            "verification_status": EvidenceStatus.NOT_RUN,
        }
    ]
    obligation = next(
        item
        for item in _diagnostics(graph)
        if item["source_location"]["path"] == "vendor"
    )
    assert obligation["code"] == "INVENTORY_ENTRY_NOT_READ"
    assert obligation["verification_status"] == EvidenceStatus.NOT_RUN
    assert all(node.get("path") != "vendor/custom.py" for node in _nodes(graph))


def test_graph_digest_detects_tampering_and_writer_refuses_overwrite(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    graph = build_project_graph(repository, "local:writer")
    output = tmp_path / "evidence" / "project-graph.json"

    write_project_graph(graph, output)
    assert json.loads(output.read_text(encoding="utf-8"))["graph_sha256"] == graph["graph_sha256"]
    with pytest.raises(ProjectGraphError, match="OUTPUT_ALREADY_EXISTS"):
        write_project_graph(graph, output)

    graph["repository_complete"] = True
    assert verify_project_graph(graph) is False
    with pytest.raises(ProjectGraphError, match="DIGEST_INVALID"):
        write_project_graph(graph, tmp_path / "tampered.json")


def test_native_scan_project_graph(tmp_path: Path) -> None:
    from elmos_polyglot_route.native_graph_bridge import native_scan_project_graph

    repository = tmp_path / "repository"
    (repository / "src").mkdir(parents=True)
    (repository / "src" / "a.py").write_text("import b\n", encoding="utf-8")
    (repository / "src" / "b.py").write_text("print('b')\n", encoding="utf-8")

    result = native_scan_project_graph(str(repository))
    assert result is not None
    assert result["total_files"] == 2
    assert result["has_cycles"] is False
    assert len(result["topological_order"]) == 2


def test_native_scan_project_graph_rejects_non_object_payload_and_frees_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ctypes

    from elmos_polyglot_route import native_graph_bridge

    payload = ctypes.create_string_buffer(b'["not", "a", "graph"]')

    class FakeLibrary:
        def __init__(self) -> None:
            self.freed: list[int] = []

        def elmos_scan_project_graph(self, _root: bytes, _max_files: int) -> int:
            return ctypes.addressof(payload)

        def elmos_free_string(self, pointer: int) -> None:
            self.freed.append(pointer)

    library = FakeLibrary()
    monkeypatch.setattr(native_graph_bridge, "_get_lib", lambda: library)

    assert native_graph_bridge.native_scan_project_graph("/bounded") is None
    assert library.freed == [ctypes.addressof(payload)]
