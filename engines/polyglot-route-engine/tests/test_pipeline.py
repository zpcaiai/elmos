from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.pipeline import run_repository_pipeline


def _repository(root: Path) -> Path:
    repository = root / "repository"
    repository.mkdir()
    (repository / "math.py").write_text(
        "def add(left: int, right: int) -> int:\n"
        "    return left + right\n",
        encoding="utf-8",
    )
    return repository


def _cases(root: Path) -> Path:
    cases = root / "cases"
    cases.mkdir()
    (cases / "WU-00001.json").write_text(
        json.dumps(
            [
                {"args": [2, 3], "expected": 5},
                {"args": [-1, 1], "expected": 0},
            ]
        ),
        encoding="utf-8",
    )
    return cases


def test_repository_pipeline_is_complete_content_addressed_and_resumable(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"

    first = run_repository_pipeline(
        repository,
        "local:test-repository",
        "python",
        "typescript",
        cases,
        output,
    )
    second = run_repository_pipeline(
        repository,
        "local:test-repository",
        "python",
        "typescript",
        cases,
        output,
    )

    assert first["status"] == "COMPLETE"
    assert second["status"] == "COMPLETE"
    assert first["resumed_count"] == 0
    assert second["resumed_count"] == 1
    assert second["status_counts"] == {"PASSED": 1}
    assert len(first["artifact"]["sha256"]) == 64
    assert second["artifact"]["sha256"] == hashlib.sha256(
        (output / "repository-migration-artifact.zip").read_bytes()
    ).hexdigest()
    assert second["independent_verification_status"] == "NOT_RUN"
    with zipfile.ZipFile(output / "repository-migration-artifact.zip") as archive:
        names = archive.namelist()
        assert "artifact-manifest.json" in names
        assert "assembled/package.json" in names
        manifest = json.loads(archive.read("artifact-manifest.json"))
        assert manifest["status"] == "COMPLETE"
        assert manifest["certification_status"] == "NOT_CERTIFIED"


def test_repository_pipeline_invalidates_checkpoint_when_source_drifts(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"
    run_repository_pipeline(
        repository,
        "local:test-repository",
        "python",
        "typescript",
        cases,
        output,
    )
    (repository / "math.py").write_text(
        "def add(left: int, right: int) -> int:\n"
        "    return left - right\n",
        encoding="utf-8",
    )

    with pytest.raises(RouteError, match="PIPELINE_NO_VERIFIED_UNITS"):
        run_repository_pipeline(
            repository,
            "local:test-repository",
            "python",
            "typescript",
            cases,
            output,
        )
    assert not (output / "repository-migration-artifact.zip").exists()
    assert not (output / "repository-pipeline-report.json").exists()


def test_repository_pipeline_invalidates_checkpoint_when_cases_drift(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"
    run_repository_pipeline(
        repository,
        "local:test-repository",
        "python",
        "typescript",
        cases,
        output,
    )
    (cases / "WU-00001.json").write_text(
        json.dumps(
            [
                {"args": [2, 3], "expected": 5},
                {"args": [20, 30], "expected": 50},
            ]
        ),
        encoding="utf-8",
    )

    rerun = run_repository_pipeline(
        repository,
        "local:test-repository",
        "python",
        "typescript",
        cases,
        output,
    )
    assert rerun["status"] == "COMPLETE"
    assert rerun["resumed_count"] == 0


def test_repository_pipeline_refuses_to_package_without_behavior_evidence(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    cases = tmp_path / "cases"
    cases.mkdir()

    with pytest.raises(RouteError, match="PIPELINE_NO_VERIFIED_UNITS"):
        run_repository_pipeline(
            repository,
            "local:test-repository",
            "python",
            "typescript",
            cases,
            tmp_path / "pipeline",
        )
