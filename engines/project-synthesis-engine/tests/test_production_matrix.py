from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def load_matrix_module() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "run_production_matrix.py"
    spec = importlib.util.spec_from_file_location("run_production_matrix", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def passed_case(language: str, auth_mode: str) -> dict[str, object]:
    return {
        "status": "PASSED",
        "language": language,
        "auth_mode": auth_mode,
        "cleanup_status": "PASSED",
        "startup_probes": [{"status": "PASSED", "integration_status": "PASSED"}],
    }


def test_default_matrix_covers_every_language_and_auth_mode() -> None:
    module = load_matrix_module()
    cases = module.matrix_cases()

    assert len(cases) == 16
    assert {language for language, _ in cases} == {
        "java",
        "python",
        "csharp",
        "typescript",
        "go",
        "kotlin",
        "php",
        "rust",
    }
    assert {auth_mode for _, auth_mode in cases} == {"jwt", "oidc"}


def test_matrix_requires_native_integration_and_cleanup() -> None:
    module = load_matrix_module()

    def executor(language: str, auth_mode: str) -> dict[str, object]:
        result = passed_case(language, auth_mode)
        if language == "go":
            result["startup_probes"] = [
                {"status": "PASSED", "integration_status": "NOT_RUN"}
            ]
        return result

    result = module.run_matrix(["python", "go"], ["jwt"], executor=executor)

    assert result["status"] == "FAILED"
    assert result["case_count"] == 2
    assert result["passed_count"] == 1
    assert len(result["failures"]) == 1


def test_matrix_rejects_missing_or_extra_startup_probes() -> None:
    module = load_matrix_module()

    missing = module.run_matrix(
        ["python"],
        ["jwt"],
        executor=lambda language, auth_mode: {
            **passed_case(language, auth_mode),
            "startup_probes": [],
        },
    )
    extra = module.run_matrix(
        ["python"],
        ["jwt"],
        executor=lambda language, auth_mode: {
            **passed_case(language, auth_mode),
            "startup_probes": [
                {"status": "PASSED", "integration_status": "PASSED"},
                {"status": "PASSED", "integration_status": "PASSED"},
            ],
        },
    )

    assert missing["status"] == "FAILED"
    assert extra["status"] == "FAILED"


def test_matrix_rejects_duplicate_or_closed_dimensions() -> None:
    module = load_matrix_module()

    with pytest.raises(ValueError, match="DUPLICATE_LANGUAGE"):
        module.matrix_cases(["python", "python"], ["jwt"])
    with pytest.raises(ValueError, match="UNSUPPORTED_AUTH_MODE"):
        module.matrix_cases(["python"], ["none"])


def test_evidence_writer_is_atomic_and_requires_json(tmp_path: Path) -> None:
    module = load_matrix_module()
    output = tmp_path / "matrix.json"

    module.write_evidence(output, {"status": "PASSED"})

    assert output.read_text(encoding="utf-8") == '{\n  "status": "PASSED"\n}\n'
    with pytest.raises(ValueError, match="PRODUCTION_MATRIX_OUTPUT_MUST_BE_JSON"):
        module.write_evidence(tmp_path / "matrix.txt", {"status": "PASSED"})
