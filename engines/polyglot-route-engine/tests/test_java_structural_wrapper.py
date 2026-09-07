from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from elmos_polyglot_route.discovery import Verdict, discover_repository
from elmos_polyglot_route.native import inventory_module
from elmos_polyglot_route.pipeline import run_repository_pipeline
from elmos_polyglot_route.project_graph import (
    ProjectGraphError,
    build_project_graph,
    verified_java_structural_wrapper,
)
from elmos_polyglot_route.repository import plan_repository


def _write_cases(cases: Path, count: int) -> None:
    cases.mkdir()
    payload = json.dumps(
        [
            {"args": [2, 3], "expected": 5},
            {"args": [-4, 1], "expected": -3},
        ]
    )
    for index in range(1, count + 1):
        (cases / f"WU-{index:05d}.json").write_text(payload + "\n", encoding="utf-8")


def _java_file(class_name: str, function_name: str, comment: str) -> str:
    return (
        f"/* {comment}\n"
        " * Comments are bytes, not Java declarations.\n"
        " */\n"
        f"public final class {class_name} {{\n"
        f"  public static long {function_name}(long left, long right) {{\n"
        "    return left + right;\n"
        "  }\n"
        "}\n"
    )


@pytest.mark.parametrize("file_count", [1, 5], ids=["small-comment", "medium-comment"])
def test_exact_java_structural_wrappers_allow_complete_pipeline(
    tmp_path: Path,
    file_count: int,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    for index in range(1, file_count + 1):
        class_name = f"Calculator{index}"
        (repository / f"{class_name}.java").write_text(
            _java_file(class_name, f"add{index}", f"fixture {index}: {{ stable prefix }}"),
            encoding="utf-8",
        )
    cases = tmp_path / "cases"
    _write_cases(cases, file_count)

    report = run_repository_pipeline(
        repository,
        f"local:java-structural-wrapper-{file_count}",
        "java",
        "python",
        cases,
        tmp_path / "output",
    )

    assert report["status"] == "COMPLETE"
    assert report["repository_complete"] is True
    assert report["repository_execution_status"] == "PASSED_LOCAL"
    assert report["conversion_coverage"]["complete"] is True
    assert report["conversion_coverage"]["subject_count"] == file_count
    discovery = json.loads(
        (tmp_path / "output" / "repository-discovery-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert discovery["ready_count"] == file_count
    assert discovery["coverage_blocker_count"] == 0
    blocker_keys = {
        result.get("coverage_key")
        for result in discovery["results"]
        if result["verdict"] != Verdict.READY
    }
    wrappers = [
        subject
        for inventory in discovery["module_inventories"]
        for subject in inventory["subjects"]
        if subject["subject_kind"] == "structural-wrapper"
    ]
    assert len(wrappers) == file_count
    assert all(wrapper["semantic_status"] == "PASSED" for wrapper in wrappers)
    assert all(wrapper["blocking_reasons"] == [] for wrapper in wrappers)
    assert all(wrapper["coverage_key"] not in blocker_keys for wrapper in wrappers)


@pytest.mark.parametrize(
    "declaration",
    [
        "@Deprecated\npublic final class Evil { METHODS }\n",
        "public final class Evil implements java.io.Serializable { METHODS }\n",
        "public final class Evil<T> { METHODS }\n",
        "public final class Evil { private static long seed = 1; METHODS }\n",
        "public final class Evil { static { } METHODS }\n",
        "public final class Evil { private Evil() { } METHODS }\n",
        "public final class Evil { static final class Nested { } METHODS }\n",
        "class Base { } public final class Evil extends Base { METHODS }\n",
    ],
    ids=[
        "annotation",
        "interface",
        "type-parameter",
        "field",
        "initializer",
        "constructor",
        "nested-type",
        "base-class",
    ],
)
def test_java_wrapper_requires_exact_compiler_indexed_closure(
    tmp_path: Path,
    declaration: str,
) -> None:
    source = tmp_path / "Evil.java"
    source.write_text(
        declaration.replace(
            "METHODS",
            "public static long clean(long left, long right) { return left + right; }",
        ),
        encoding="utf-8",
    )

    inventory = inventory_module(source, "java")

    assert verified_java_structural_wrapper(inventory["subjects"], "Evil.java") is None


def test_malicious_java_wrapper_keeps_local_output_but_blocks_repository(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "Evil.java").write_text(
        "public final class Evil {\n"
        "  private static long seed = 1;\n"
        "  public static long clean(long left, long right) { return left + right; }\n"
        "}\n",
        encoding="utf-8",
    )
    cases = tmp_path / "cases"
    _write_cases(cases, 1)

    report = run_repository_pipeline(
        repository,
        "local:java-malicious-wrapper",
        "java",
        "python",
        cases,
        tmp_path / "output",
    )

    assert report["status"] == "PARTIAL"
    assert report["repository_complete"] is False
    assert report["repository_execution_status"] == "LIMITED"
    assert report["status_counts"]["PASSED"] == 1
    discovery = json.loads(
        (tmp_path / "output" / "repository-discovery-report.json").read_text(
            encoding="utf-8"
        )
    )
    wrapper = next(
        subject
        for subject in discovery["module_inventories"][0]["subjects"]
        if subject["declaration_kind"] == "top-level-class-wrapper"
    )
    assert wrapper["subject_kind"] == "module-obligation"
    assert wrapper["semantic_status"] == "BLOCKED"
    assert any(
        result.get("coverage_key") == wrapper["coverage_key"]
        and result["verdict"] == Verdict.UNSUPPORTED
        for result in discovery["results"]
    )


def test_project_graph_recomputes_java_structural_wrapper_closure(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "Exact.java").write_text(
        _java_file("Exact", "clean", "project graph independent closure"),
        encoding="utf-8",
    )
    repository_ref = "local:java-wrapper-graph-recheck"
    discovery = discover_repository(
        plan_repository(repository, repository_ref, "java", "python"),
        repository,
    )
    tampered = copy.deepcopy(discovery)
    wrapper = next(
        subject
        for subject in tampered["module_inventories"][0]["subjects"]
        if subject["subject_kind"] == "structural-wrapper"
    )
    wrapper["structural_wrapper_verification"]["member_span_status"] = "CLAIMED"

    with pytest.raises(
        ProjectGraphError,
        match="SEMANTIC_DISCOVERY_STRUCTURAL_WRAPPER_INVALID",
    ):
        build_project_graph(repository, repository_ref, tampered)
