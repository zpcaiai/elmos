from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from elmos_polyglot_route.models import Language, RouteError
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

    assert report["status"] in ("PARTIAL", "BLOCKED")
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


def test_php_declarations_outside_the_profile_block_repository_completion(
    tmp_path: Path,
) -> None:
    """PHP enumeration must surface obligations, not silently pass a file.

    The lifted function is fine; the class, its member and the top-level
    constant cannot be carried by `typed-pure-function-v1`. Each has to arrive
    as its own explicit blocker, because a file that reports READY while most
    of it was never looked at is the exact failure this enumeration exists to
    prevent.

    Deliberately no top-level *statement* here -- a file with top-level output
    is covered by its own test below, at the enumeration layer, because the
    behaviour harness has to load the source file and a stray `echo` writes
    into the channel the harness parses.
    """
    _, blockers = _run_partial_pipeline(
        tmp_path,
        "php",
        "sample.php",
        "<?php\n\n"
        "declare(strict_types=1);\n\n"
        "const LIMIT = 10;\n\n"
        "final class Holder\n{\n"
        "    public const SEED = 1;\n\n"
        "    public function scale(int $value): int\n    {\n        return $value;\n    }\n"
        "}\n\n"
        "function clean(int $left, int $right): int\n{\n    return $left + $right;\n}\n",
    )

    blocker_kinds = {
        blocker["source_symbol"]["declaration_kind"] for blocker in blockers
    }
    assert "class" in blocker_kinds
    assert "method" in blocker_kinds
    assert "class-constant" in blocker_kinds
    assert "constant" in blocker_kinds
    assert all(
        blocker["blocker_code"] == "NATIVE_MODULE_DECLARATION_CONVERSION_UNCOVERED"
        for blocker in blockers
    )


def test_php_strict_types_profile_preamble_is_content_bound_not_a_work_unit(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.php"
    source.write_text(
        "<?php\n\ndeclare(strict_types=1);\n\n"
        "function clean(int $left, int $right): int\n"
        "{\n    return $left + $right;\n}\n",
        encoding="utf-8",
    )

    inventory = inventory_module(source, "php")

    assert [subject["name"] for subject in inventory["subjects"]] == ["clean"]
    assert inventory["directives"] == [
        {
            "order": 0,
            "kind": "declare",
            "value": "strict_types=1",
            "source_span": {"file": "sample.php", "start_byte": 7, "end_byte": 31},
            "sha256": "sha256:" + hashlib.sha256(b"declare(strict_types=1);").hexdigest(),
        }
    ]


def test_php_non_profile_declare_remains_an_explicit_module_obligation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.php"
    source.write_text(
        "<?php\n\ndeclare(strict_types=1);\n\ndeclare(ticks=1);\n\n"
        "function clean(int $left, int $right): int\n"
        "{\n    return $left + $right;\n}\n",
        encoding="utf-8",
    )

    inventory = inventory_module(source, "php")

    assert [subject["declaration_kind"] for subject in inventory["subjects"]] == [
        "declare-directive",
        "function",
    ]
    assert inventory["directives"][0]["value"] == "strict_types=1"


def test_a_php_top_level_statement_is_enumerated_as_its_own_obligation(
    tmp_path: Path,
) -> None:
    """Top-level output is enumerated, and is why such a file cannot be piped.

    `echo` at file scope runs on load. The behaviour harness has to load the
    source file to obtain golden values, so the statement writes into the same
    channel the harness parses. Enumeration's job is to name that; keeping the
    assertion here rather than in the pipeline test states the boundary instead
    of hiding it behind a fixture that happens to avoid it.
    """
    from elmos_polyglot_route.native import inventory_module

    source = tmp_path / "sample.php"
    source.write_text(
        "<?php\n\ndeclare(strict_types=1);\n\n"
        "function clean(int $left, int $right): int\n{\n    return $left + $right;\n}\n\n"
        "echo clean(2, 3);\n",
        encoding="utf-8",
    )

    subjects = {
        subject["declaration_kind"]: subject
        for subject in inventory_module(source, "php")["subjects"]
    }

    assert subjects["top-level-statement"]["analyzable"] is False
    assert subjects["function"]["analyzable"] is True


def test_a_php_include_edge_is_enumerated_as_its_own_obligation(tmp_path: Path) -> None:
    """A file that pulls in another file is not closed on its own.

    Asserted through `inventory_module` rather than the repository pipeline:
    the pipeline needs at least one verified unit, and the point here is the
    edge itself, not what surrounds it.
    """
    from elmos_polyglot_route.native import inventory_module

    source = tmp_path / "sample.php"
    source.write_text(
        "<?php\n\ndeclare(strict_types=1);\n\n"
        "require_once __DIR__ . '/bootstrap.php';\n\n"
        "function clean(int $left, int $right): int\n{\n    return $left + $right;\n}\n",
        encoding="utf-8",
    )

    inventory = inventory_module(source, "php")
    subjects = {
        subject["declaration_kind"]: subject for subject in inventory["subjects"]
    }

    assert inventory["enumeration_status"] == "PASSED"
    assert subjects["include-directive"]["analyzable"] is False
    assert subjects["include-directive"]["signature"]["directive"] == "require_once"
    assert subjects["function"]["analyzable"] is True


def test_a_php_function_without_strict_types_is_not_offered_for_lifting(
    tmp_path: Path,
) -> None:
    """Without `declare(strict_types=1)` PHP coerces arguments.

    A `string` would satisfy an `int` parameter, so the profile's entire type
    story collapses. Enumeration refuses to mark anything in such a file
    analyzable rather than letting the named-function frontend decide it later
    on weaker ground.

    This cannot go through `_run_partial_pipeline`: that helper requires at
    least one verified unit, and a file with nothing analyzable is precisely a
    file that has none.
    """
    from elmos_polyglot_route.native import inventory_module

    source = tmp_path / "sample.php"
    source.write_text(
        "<?php\n\nfunction clean(int $left, int $right): int\n{\n"
        "    return $left + $right;\n}\n",
        encoding="utf-8",
    )

    inventory = inventory_module(source, "php")
    functions = [
        subject
        for subject in inventory["subjects"]
        if subject["declaration_kind"] == "function"
    ]

    assert functions
    assert all(subject["analyzable"] is False for subject in functions)


def test_php_lifts_a_named_function_out_of_a_file_that_holds_other_declarations(
    tmp_path: Path,
) -> None:
    """Enumeration and lifting must not contradict each other.

    `lift()` used to require every top-level token to be `function`, so any
    file with a `const`, a class or a trailing statement above the target was
    unliftable -- while `--inventory` was reporting that same target as
    analyzable. Deciding file closure is enumeration's job; the lifter's job is
    one named function.
    """
    from elmos_polyglot_route.native import analyze, inventory_module

    source = tmp_path / "sample.php"
    source.write_text(
        "<?php\n\ndeclare(strict_types=1);\n\n"
        "const LIMIT = 10;\n\n"
        "final class Holder\n{\n    public const SEED = 1;\n}\n\n"
        "function clean(int $left, int $right): int\n{\n    return $left + $right;\n}\n\n"
        "echo clean(2, 3);\n",
        encoding="utf-8",
    )

    analyzable = [
        subject["name"]
        for subject in inventory_module(source, "php")["subjects"]
        if subject["analyzable"]
    ]
    assert analyzable == ["clean"]

    ir = analyze(source, "php", "clean")
    assert ir.functions[0].name == "clean"
    assert [item.name for item in ir.functions[0].parameters] == ["left", "right"]


def test_a_php_body_that_uses_a_skipped_declaration_is_still_rejected(
    tmp_path: Path,
) -> None:
    """Skipping a declaration must not smuggle a dependency on it into the IR.

    The expression parser resolves parameters and nothing else, so a body that
    reaches for a file-level constant fails closed even though the constant
    itself is now stepped over rather than fatal.
    """
    from elmos_polyglot_route.native import analyze

    source = tmp_path / "sample.php"
    source.write_text(
        "<?php\n\ndeclare(strict_types=1);\n\nconst LIMIT = 10;\n\n"
        "function scaled(int $value): int\n{\n    return $value + LIMIT;\n}\n",
        encoding="utf-8",
    )

    with pytest.raises(RouteError, match="PHP_CALL_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "php", "scaled")
