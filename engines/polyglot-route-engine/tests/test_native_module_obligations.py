from __future__ import annotations

import json
from pathlib import Path

import pytest

from elmos_polyglot_route.models import Language
from elmos_polyglot_route.native import inventory_module
from elmos_polyglot_route.pipeline import run_repository_pipeline


def _run_partial_pipeline(
    tmp_path: Path,
    language: Language,
    filename: str,
    source: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    repository = tmp_path / "repository"
    cases = tmp_path / "cases"
    output = tmp_path / "output"
    repository.mkdir()
    cases.mkdir()
    (repository / filename).write_text(source, encoding="utf-8")
    (cases / "WU-00001.json").write_text(
        json.dumps(
            [
                {"args": [2, 3], "expected": 5},
                {"args": [-4, 1], "expected": -3},
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = run_repository_pipeline(
        repository,
        f"local:native-obligation/{language}",
        language,
        "python",
        cases,
        output,
    )
    discovery = json.loads(
        (output / "repository-discovery-report.json").read_text(encoding="utf-8")
    )
    blockers = [
        result
        for result in discovery["results"]
        if result["verdict"] != "READY"
    ]

    assert report["status"] == "PARTIAL"
    assert report["repository_complete"] is False
    assert report["repository_execution_status"] == "LIMITED"
    assert report["local_execution_evidence"] == "LIMITED"
    assert report["project_graph"]["repository_complete"] is False
    assert report["conversion_coverage"]["complete"] is False
    assert report["conversion_coverage"]["status_counts"]["BLOCKED"] >= 1
    assert report["status_counts"]["PASSED"] == 1
    assert blockers
    assert all(blocker["blocker_code"] for blocker in blockers)
    assert all(blocker["reason"] for blocker in blockers)
    return report, blockers


def test_go_build_constraints_and_directives_block_repository_completion(
    tmp_path: Path,
) -> None:
    _, blockers = _run_partial_pipeline(
        tmp_path,
        "go",
        "sample.go",
        "//go:build darwin || linux\n"
        "// +build darwin linux\n\n"
        "package sample\n\n"
        "//go:generate echo generated\n"
        "func clean(left int64, right int64) int64 { return left + right }\n",
    )

    blocker_kinds = {
        blocker["source_symbol"]["declaration_kind"] for blocker in blockers
    }
    assert blocker_kinds == {
        "go-build-constraint",
        "plus-build-constraint",
        "go-directive",
    }
    directives = {
        blocker["source_symbol"]["source_signature"]["directive"]
        for blocker in blockers
    }
    assert "//go:generate echo generated" in directives


@pytest.mark.parametrize(
    "declaration",
    [
        (
            "[System.Diagnostics.DebuggerDisplay(\"Container\")]\n"
            "public static class Container {\n"
            "  public static long clean(long left, long right) { return left + right; }\n"
            "}\n"
        ),
        (
            "public class Container : MissingBase {\n"
            "  public static long clean(long left, long right) { return left + right; }\n"
            "}\n"
        ),
        (
            "public class Container<T> {\n"
            "  public static long clean(long left, long right) { return left + right; }\n"
            "}\n"
        ),
        (
            "public class Container(long seed) {\n"
            "  public static long clean(long left, long right) { return left + right; }\n"
            "}\n"
        ),
        (
            "public static class Container {\n"
            "  private static long seed = 1;\n"
            "  public static long clean(long left, long right) { return left + right; }\n"
            "}\n"
        ),
    ],
    ids=["attribute", "base-list", "type-parameter", "primary-constructor", "initializer"],
)
def test_csharp_non_plain_type_wrappers_are_inventory_obligations(
    tmp_path: Path,
    declaration: str,
) -> None:
    source = tmp_path / "Container.cs"
    source.write_text(declaration, encoding="utf-8")

    inventory = inventory_module(source, "csharp")

    container = next(
        subject for subject in inventory["subjects"] if subject["name"] == "Container"
    )
    assert container["declaration_kind"] == "ClassDeclaration"
    assert container["analyzable"] is False


def test_csharp_attributed_wrapper_keeps_local_output_but_blocks_repository(
    tmp_path: Path,
) -> None:
    _, blockers = _run_partial_pipeline(
        tmp_path,
        "csharp",
        "Container.cs",
        "[System.Diagnostics.DebuggerDisplay(\"Container\")]\n"
        "public static class Container {\n"
        "  public static long clean(long left, long right) { return left + right; }\n"
        "}\n",
    )

    assert any(
        blocker["source_symbol"]["name"] == "Container"
        and blocker["source_symbol"]["declaration_kind"] == "ClassDeclaration"
        for blocker in blockers
    )


def test_rust_semantic_attributes_block_repository_completion(tmp_path: Path) -> None:
    _, blockers = _run_partial_pipeline(
        tmp_path,
        "rust",
        "sample.rs",
        "#[no_mangle]\n"
        "pub fn exported(left: i64, right: i64) -> i64 { return left + right; }\n\n"
        "fn clean(left: i64, right: i64) -> i64 { return left + right; }\n",
    )

    attribute_paths = {
        blocker["source_symbol"]["source_signature"].get("attribute_path")
        for blocker in blockers
    }
    assert "no_mangle" in attribute_paths
    assert any(
        blocker["source_symbol"]["declaration_kind"] == "item-attribute"
        for blocker in blockers
    )


def test_rust_module_and_link_attributes_are_explicit_inventory_subjects(
    tmp_path: Path,
) -> None:
    source = tmp_path / "attributes.rs"
    source.write_text(
        "#![no_std]\n"
        "#[link(name = \"c\")]\n"
        "extern \"C\" {}\n"
        "#[export_name = \"exported_name\"]\n"
        "pub extern \"C\" fn exported(value: i64) -> i64 { value }\n",
        encoding="utf-8",
    )

    inventory = inventory_module(source, "rust")

    attributes = {
        subject["signature"].get("attribute_path")
        for subject in inventory["subjects"]
        if subject["declaration_kind"] in {"module-attribute", "item-attribute"}
    }
    assert {"no_std", "link", "export_name"} <= attributes
    assert all(
        subject["analyzable"] is False
        for subject in inventory["subjects"]
        if subject["declaration_kind"] in {"module-attribute", "item-attribute"}
    )


def test_cpp_default_argument_blocks_repository_completion(tmp_path: Path) -> None:
    _, blockers = _run_partial_pipeline(
        tmp_path,
        "cpp",
        "sample.cpp",
        "#include <cstdint>\n\n"
        "std::int64_t clean(std::int64_t left, std::int64_t right) {\n"
        "  return left + right;\n"
        "}\n\n"
        "std::int64_t configured(std::int64_t value = 1) { return value; }\n",
    )

    configured = next(
        blocker["source_symbol"]
        for blocker in blockers
        if blocker["source_symbol"]["name"] == "configured"
    )
    assert "default-argument" in configured["source_signature"]["semantic_markers"]


def test_objc_visibility_attribute_blocks_repository_completion(tmp_path: Path) -> None:
    _, blockers = _run_partial_pipeline(
        tmp_path,
        "objc",
        "sample.m",
        "long long clean(long long left, long long right) { return left + right; }\n"
        "__attribute__((visibility(\"default\")))\n"
        "long long exported(long long value) { return value; }\n",
    )

    exported = next(
        blocker["source_symbol"]
        for blocker in blockers
        if blocker["source_symbol"]["name"] == "exported"
    )
    assert "attribute:VisibilityAttr" in exported["source_signature"]["semantic_markers"]
