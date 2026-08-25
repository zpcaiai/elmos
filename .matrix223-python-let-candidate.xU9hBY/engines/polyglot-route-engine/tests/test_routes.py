from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from elmos_polyglot_route.engine import migrate
from elmos_polyglot_route.models import REPOSITORY_SURFACE_LANGUAGES, Language, RouteError
from elmos_polyglot_route.native import analyze
from elmos_polyglot_route.repository import plan_repository

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {
    "java": "java",
    "python": "py",
    "csharp": "cs",
    "typescript": "ts",
    "javascript": "mjs",
    "go": "go",
    "rust": "rs",
    "cpp": "cpp",
    "objc": "m",
    "swift": "swift",
}
FILES = {
    "java": "Pricing",
    "python": "pricing",
    "csharp": "Pricing",
    "typescript": "pricing",
    "javascript": "pricing",
    "go": "pricing",
    "rust": "pricing",
    "cpp": "pricing",
    "objc": "pricing",
    "swift": "pricing",
}


@pytest.mark.parametrize("language", REPOSITORY_SURFACE_LANGUAGES)
def test_native_analyzers_emit_the_same_typed_semantic_slice(language: Language) -> None:
    source = ROOT / "fixtures" / language / f"{FILES[language]}.{EXTENSIONS[language]}"
    semantic = analyze(source, language, "calculate")
    function = semantic.functions[0]
    assert function.name == "calculate"
    assert [parameter.name for parameter in function.parameters] == ["subtotal", "tax"]
    assert [statement.kind for statement in function.body] == ["if", "return"]
    assert semantic.diagnostics == ()


@pytest.mark.parametrize(
    ("source_language", "target_language"),
    [
        (source, target)
        for source in REPOSITORY_SURFACE_LANGUAGES
        for target in REPOSITORY_SURFACE_LANGUAGES
        if source != target and {source, target} != {"javascript", "typescript"}
    ],
)
def test_every_repository_direction_compiles_and_matches_behavior(
    tmp_path: Path,
    source_language: Language,
    target_language: Language,
) -> None:
    source = ROOT / "fixtures" / source_language / f"{FILES[source_language]}.{EXTENSIONS[source_language]}"
    output = tmp_path / f"{source_language}-to-{target_language}"
    report = migrate(
        source,
        source_language,
        target_language,
        "calculate",
        ROOT / "fixtures" / "behavior-cases.json",
        output,
        repository_execution_mode=True,
    )
    assert report["status"] == "PASSED_LOCAL_UNCERTIFIED"
    assert report["behavior_pass_rate"] == 1.0
    assert report["critical_unknown_semantics"] == 1
    behavior = report["behavior_equivalence"]
    assert behavior["status"] == "PASSED"
    assert behavior["case_count"] == behavior["pass_count"] == 3
    artifact = output / behavior["artifact_path"]
    assert behavior["artifact_sha256"] == "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert report["certification_status"] == "EXPERIMENTAL"
    assert report["external_certification_status"] == "NOT_RUN"


@pytest.mark.parametrize(
    ("corpus", "function_name", "file_name"),
    [("holdout", "clamp", "Clamp"), ("representative", "difference", "Difference")],
)
@pytest.mark.parametrize(
    ("source_language", "target_language"),
    [
        (source, target)
        for source in REPOSITORY_SURFACE_LANGUAGES
        for target in REPOSITORY_SURFACE_LANGUAGES
        if source != target and {source, target} != {"javascript", "typescript"}
    ],
)
def test_independent_corpora_compile_and_match_behavior(
    tmp_path: Path,
    corpus: str,
    function_name: str,
    file_name: str,
    source_language: Language,
    target_language: Language,
) -> None:
    source_base = file_name if source_language in {"java", "csharp"} else file_name.lower()
    source = ROOT / "fixtures" / corpus / source_language / f"{source_base}.{EXTENSIONS[source_language]}"
    report = migrate(
        source,
        source_language,
        target_language,
        function_name,
        ROOT / "fixtures" / corpus / "cases.json",
        tmp_path / corpus / f"{source_language}-to-{target_language}",
        repository_execution_mode=True,
    )
    assert report["status"] == "PASSED_LOCAL_UNCERTIFIED"
    assert report["behavior_case_count"] == 3


@pytest.mark.parametrize(
    ("source_language", "target_language"),
    [("javascript", "typescript"), ("typescript", "javascript")],
)
def test_javascript_typescript_repository_route_uses_finite_number_transport_contract(
    tmp_path: Path,
    source_language: Language,
    target_language: Language,
) -> None:
    source = tmp_path / ("identity.mjs" if source_language == "javascript" else "identity.ts")
    source.write_text(
        (
            "/**\n * @param {number} value\n * @returns {number}\n */\n"
            "export function identity(value) { return value; }\n"
            if source_language == "javascript"
            else "export function identity(value: number): number { return value; }\n"
        ),
        encoding="utf-8",
    )
    cases = tmp_path / "cases.json"
    cases.write_text(
        json.dumps(
            [
                {"args": [-0.0], "expected": -0.0},
                {
                    "args": [1.7976931348623157e308],
                    "expected": 1.7976931348623157e308,
                },
                {"args": [5e-324], "expected": 5e-324},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "output"

    report = migrate(
        source,
        source_language,
        target_language,
        "identity",
        cases,
        output,
        repository_execution_mode=True,
    )

    assert report["status"] == "PASSED_LOCAL_UNCERTIFIED"
    assert report["behavior_pass_rate"] == 1.0
    assert report["behavior_equivalence"]["status"] == "PASSED"
    assert [observation["raw"] for observation in report["validation"]["observations"]] == [
        "8000000000000000",
        "7fefffffffffffff",
        "0000000000000001",
    ]


def test_unsupported_python_side_effect_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "unsafe.py"
    source.write_text(
        "def calculate(subtotal: int, tax: int) -> int:\n    print(subtotal)\n    return subtotal + tax\n",
        encoding="utf-8",
    )
    with pytest.raises(RouteError, match="PYTHON_UNSUPPORTED_STATEMENT"):
        analyze(source, "python", "calculate")


def test_repository_inventory_is_content_addressed_and_decomposes_work_units(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "src").mkdir()
    (repository / "src" / "Price.java").write_text(
        "final class Price { static int calculate(int value) { return value; } }\n",
        encoding="utf-8",
    )
    (repository / "src" / "helper.py").write_text(
        "def helper(value: int) -> int:\n    return value\n", encoding="utf-8"
    )
    (repository / "src" / "pricing.go").write_text(
        "package pricing\nfunc Calculate(value int64) int64 { return value }\n",
        encoding="utf-8",
    )
    (repository / "src" / "pricing.rs").write_text(
        "fn calculate(value: i64) -> i64 { return value }\n",
        encoding="utf-8",
    )
    (repository / "src" / "pricing.cpp").write_text(
        "long calculate(long value) { return value; }\n",
        encoding="utf-8",
    )
    (repository / "src" / "pricing.m").write_text(
        "long calculate(long value) { return value; }\n",
        encoding="utf-8",
    )
    (repository / "src" / "pricing.swift").write_text(
        "func calculate(_ value: Int) -> Int { value }\n",
        encoding="utf-8",
    )
    (repository / "node_modules").mkdir()
    (repository / "node_modules" / "ignored.ts").write_text("export const ignored = true;\n", encoding="utf-8")

    plan = plan_repository(repository, "local:inventory-fixture", "java", "python")

    assert plan["status"] == "PLANNED"
    assert plan["route_id"] == "java-to-python"
    assert plan["file_count"] == 7
    assert plan["source_file_count"] == 1
    assert plan["language_counts"]["java"] == 1
    assert plan["language_counts"]["python"] == 1
    assert plan["language_counts"]["go"] == 1
    assert plan["language_counts"]["rust"] == 1
    assert plan["language_counts"]["cpp"] == 1
    assert plan["language_counts"]["objc"] == 1
    assert plan["language_counts"]["swift"] == 1
    assert plan["repository_scale"] == "small"
    assert plan["repository_limits"]["maximum_source_files"] == 5_000
    assert plan["work_units"][0]["source_path"] == "src/Price.java"
    assert plan["work_units"][0]["execution_status"] == "NOT_RUN"
    assert plan["certification_status"] == "NOT_CERTIFIED"
    assert len(plan["snapshot_sha256"]) == 64


def test_repository_inventory_rejects_symlink_root_and_same_language(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "source.py").write_text("def value() -> int:\n    return 1\n", encoding="utf-8")
    alias = tmp_path / "alias"
    alias.symlink_to(repository, target_is_directory=True)

    with pytest.raises(RouteError, match="REPOSITORY_DIRECTORY_INVALID"):
        plan_repository(alias, "local:inventory-fixture", "python", "java")
    with pytest.raises(RouteError, match="SOURCE_AND_TARGET_MUST_DIFFER"):
        plan_repository(repository, "local:inventory-fixture", "python", "python")


def test_repository_inventory_classifies_a_medium_source_estate(tmp_path: Path) -> None:
    repository = tmp_path / "medium-repository"
    repository.mkdir()
    for index in range(501):
        (repository / f"unit_{index:03d}.py").write_text(
            f"def value_{index}(value: int) -> int:\n    return value\n",
            encoding="utf-8",
        )

    plan = plan_repository(repository, "local:medium-repository", "python", "java")

    assert plan["repository_scale"] == "medium"
    assert plan["source_file_count"] == 501
    assert len(plan["work_units"]) == 501
    assert plan["repository_limits"] == {
        "maximum_source_files": 5_000,
        "maximum_source_bytes": 64 * 1024 * 1024,
        "maximum_bytes_per_file": 2 * 1024 * 1024,
    }
