from __future__ import annotations

import json
from pathlib import Path

import pytest

from elmos_polyglot_route.engine import migrate
from elmos_polyglot_route.models import ANALYZABLE_LANGUAGES, SUPPORTED_LANGUAGES, Language, RouteError
from elmos_polyglot_route.native import analyze
from elmos_polyglot_route.repository import plan_repository
from elmos_polyglot_route.validation import validate_source

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {
    "java": "java",
    "python": "py",
    "csharp": "cs",
    "typescript": "ts",
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
    "go": "pricing",
    "rust": "pricing",
    "cpp": "pricing",
    "objc": "pricing",
    "swift": "pricing",
}


@pytest.mark.parametrize("language", ANALYZABLE_LANGUAGES)
def test_native_analyzers_emit_the_same_typed_semantic_slice(language: Language) -> None:
    source = ROOT / "fixtures" / language / f"{FILES[language]}.{EXTENSIONS[language]}"
    semantic = analyze(source, language, "calculate")
    function = semantic.functions[0]
    assert function.name == "calculate"
    assert [parameter.name for parameter in function.parameters] == ["subtotal", "tax"]
    assert [statement.kind for statement in function.body] == ["if", "return"]
    assert semantic.diagnostics == ()


@pytest.mark.parametrize("language", ANALYZABLE_LANGUAGES)
def test_original_source_function_passes_the_same_declared_behavior_cases(
    tmp_path: Path,
    language: Language,
) -> None:
    source = ROOT / "fixtures" / language / f"{FILES[language]}.{EXTENSIONS[language]}"
    function = analyze(source, language, "calculate").functions[0]
    cases = json.loads((ROOT / "fixtures" / "behavior-cases.json").read_text(encoding="utf-8"))
    evidence = validate_source(source, language, function, cases, tmp_path / language)
    assert evidence["status"] == "PASSED"
    assert evidence["subject"] == "SOURCE_DECLARATION_EXTRACT"
    assert evidence["case_count"] == 3


@pytest.mark.parametrize(
    ("source_language", "target_language"),
    [(source, target) for source in ANALYZABLE_LANGUAGES for target in SUPPORTED_LANGUAGES if source != target],
)
def test_every_directed_route_compiles_and_matches_behavior(
    tmp_path: Path,
    source_language: Language,
    target_language: Language,
) -> None:
    source = ROOT / "fixtures" / source_language / f"{FILES[source_language]}.{EXTENSIONS[source_language]}"
    report = migrate(
        source,
        source_language,
        target_language,
        "calculate",
        ROOT / "fixtures" / "behavior-cases.json",
        tmp_path / f"{source_language}-to-{target_language}",
    )
    assert report["status"] == "PASSED"
    assert report["behavior_pass_rate"] == 1.0
    assert report["critical_unknown_semantics"] == 0
    assert report["certification_status"] == "EXPERIMENTAL"
    assert report["external_certification_status"] == "NOT_RUN"


@pytest.mark.parametrize(
    ("corpus", "function_name", "file_name"),
    [("holdout", "clamp", "Clamp"), ("representative", "difference", "Difference")],
)
@pytest.mark.parametrize(
    ("source_language", "target_language"),
    [(source, target) for source in ANALYZABLE_LANGUAGES for target in SUPPORTED_LANGUAGES if source != target],
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
    )
    assert report["status"] == "PASSED"
    assert report["behavior_case_count"] == 3


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
        "long long calculate(long long value) { return value; }\n",
        encoding="utf-8",
    )
    (repository / "src" / "pricing.swift").write_text(
        "func calculate(_ value: Int64) -> Int64 { return value }\n",
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
