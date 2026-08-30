from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

import elmos_polyglot_route.discovery as discovery_module
import elmos_polyglot_route.pipeline as pipeline_module
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.pipeline import PROJECT_GRAPH_NAME, run_repository_pipeline
from elmos_polyglot_route.project_graph import verify_project_graph


def _repository(root: Path) -> Path:
    repository = root / "repository"
    repository.mkdir()
    (repository / "math.py").write_text(
        "def add(left: int, right: int) -> int:\n    return left + right\n",
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
    first_graph = json.loads((output / PROJECT_GRAPH_NAME).read_text(encoding="utf-8"))
    assert verify_project_graph(first_graph)
    (output / PROJECT_GRAPH_NAME).write_text('{"graph_sha256": "tampered"}\n', encoding="utf-8")
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
    assert second["repository_complete"] is True
    assert second["repository_execution_status"] == "PASSED_LOCAL"
    assert second["project_graph"]["graph_sha256"] == first_graph["graph_sha256"]
    assert second["project_graph"]["obligation_count"] == 0
    assert second["project_graph"]["obligation_status_counts"] == {
        "FAILED": 0,
        "NOT_RUN": 0,
        "PASSED": 0,
        "UNKNOWN": 0,
    }
    assert second["conversion_coverage"]["complete"] is True
    assert second["conversion_coverage"]["status_counts"] == {
        "BLOCKED": 0,
        "FAILED": 0,
        "NOT_RUN": 0,
        "PASSED": 1,
        "UNKNOWN": 0,
    }
    restored_graph = json.loads((output / PROJECT_GRAPH_NAME).read_text(encoding="utf-8"))
    assert restored_graph == first_graph
    assert verify_project_graph(restored_graph)
    assert first["resumed_count"] == 0
    assert second["resumed_count"] == 0
    assert second["status_counts"] == {"PASSED": 1}
    assert len(first["artifact"]["sha256"]) == 64
    assert (
        second["artifact"]["sha256"]
        == hashlib.sha256((output / "repository-migration-artifact.zip").read_bytes()).hexdigest()
    )
    assert second["independent_verification_status"] == "NOT_RUN"
    with zipfile.ZipFile(output / "repository-migration-artifact.zip") as archive:
        names = archive.namelist()
        assert "artifact-manifest.json" in names
        assert PROJECT_GRAPH_NAME in names
        assert "assembled/package.json" in names
        manifest = json.loads(archive.read("artifact-manifest.json"))
        assert manifest["status"] == "COMPLETE"
        assert manifest["repository_complete"] is True
        assert manifest["repository_execution_status"] == "PASSED_LOCAL"
        assert manifest["project_graph"] == second["project_graph"]
        assert manifest["conversion_coverage"] == second["conversion_coverage"]
        assert manifest["certification_status"] == "NOT_CERTIFIED"


def test_repository_pipeline_is_limited_when_project_graph_has_open_obligations(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    (repository / "opaque.blobx").write_bytes(b"unclassified project input")
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"

    report = run_repository_pipeline(
        repository,
        "local:incomplete-project-graph",
        "python",
        "typescript",
        cases,
        output,
    )

    assert report["unit_batch_status"] == "COMPLETE"
    assert report["status_counts"] == {"PASSED": 1}
    assert report["included_unit_count"] == 1
    assert report["build_verification"]["status"] == "PASSED"
    assert report["status"] == "PARTIAL"
    assert report["repository_complete"] is False
    assert report["repository_execution_status"] == "LIMITED"
    assert report["local_execution_evidence"] == "LIMITED"
    assert report["project_graph"]["verification_status"] == "PASSED"
    assert report["project_graph"]["obligation_count"] == 1
    assert report["project_graph"]["obligation_status_counts"]["UNKNOWN"] == 1
    assert (output / "assembled" / "package.json").is_file()
    assert (output / "repository-migration-artifact.zip").is_file()

    manifest = json.loads((output / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PARTIAL"
    assert manifest["unit_batch_status"] == "COMPLETE"
    assert manifest["repository_complete"] is False
    assert manifest["repository_execution_status"] == "LIMITED"
    assert manifest["project_graph"] == report["project_graph"]


def test_repository_pipeline_never_drops_a_rejected_python_symbol(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "mixed.py").write_text(
        "def add(left: int, right: int) -> int:\n"
        "    return left + right\n\n"
        "def persist(name: str) -> str:\n"
        "    with open(name) as handle:\n"
        "        return handle.read()\n",
        encoding="utf-8",
    )
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"

    report = run_repository_pipeline(
        repository,
        "local:partial-symbol-coverage",
        "python",
        "typescript",
        cases,
        output,
    )

    assert report["unit_batch_status"] == "PARTIAL"
    assert report["status"] == "PARTIAL"
    assert report["repository_complete"] is False
    assert report["repository_execution_status"] == "LIMITED"
    assert report["included_unit_count"] == 1
    assert report["project_graph"]["repository_complete"] is True
    assert report["project_graph"]["obligation_count"] == 0
    assert report["conversion_coverage"]["complete"] is False
    assert report["conversion_coverage"]["status_counts"] == {
        "BLOCKED": 1,
        "FAILED": 0,
        "NOT_RUN": 0,
        "PASSED": 1,
        "UNKNOWN": 0,
    }
    assert (output / "assembled" / "package.json").is_file()
    manifest = json.loads((output / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PARTIAL"
    assert manifest["repository_complete"] is False
    assert manifest["conversion_coverage"] == report["conversion_coverage"]


def test_repository_pipeline_limits_unmigrated_descriptors_and_resources(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    (repository / "tests").mkdir()
    (repository / "web").mkdir()
    (repository / "pyproject.toml").write_text(
        '[project]\nname = "sample"\n',
        encoding="utf-8",
    )
    (repository / "settings.yaml").write_text("enabled: true\n", encoding="utf-8")
    (repository / "web" / "index.html").write_text("<main>sample</main>\n", encoding="utf-8")
    (repository / "tests" / "fixture.json").write_text('{"value": 1}\n', encoding="utf-8")
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"

    report = run_repository_pipeline(
        repository,
        "local:unmigrated-repository-artifacts",
        "python",
        "typescript",
        cases,
        output,
    )

    assert report["unit_batch_status"] == "COMPLETE"
    assert report["conversion_coverage"]["complete"] is True
    assert report["status"] == "PARTIAL"
    assert report["repository_complete"] is False
    assert report["repository_execution_status"] == "LIMITED"
    assert report["project_graph"]["obligation_count"] == 4
    assert report["project_graph"]["obligation_status_counts"]["NOT_RUN"] == 4
    assert not (output / "assembled" / "pyproject.toml").exists()
    assert not (output / "assembled" / "settings.yaml").exists()


def test_repository_pipeline_is_limited_when_ignored_directory_scope_is_unverified(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    (repository / "vendor").mkdir()
    (repository / "vendor" / "custom.py").write_text(
        "def hidden() -> int:\n    return 99\n",
        encoding="utf-8",
    )
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"

    report = run_repository_pipeline(
        repository,
        "local:ignored-vendor-source",
        "python",
        "typescript",
        cases,
        output,
    )

    assert report["unit_batch_status"] == "COMPLETE"
    assert report["conversion_coverage"]["complete"] is True
    assert report["status"] == "PARTIAL"
    assert report["repository_complete"] is False
    assert report["repository_execution_status"] == "LIMITED"
    assert report["project_graph"]["obligation_count"] == 1
    assert report["project_graph"]["obligation_status_counts"]["NOT_RUN"] == 1
    graph = json.loads((output / PROJECT_GRAPH_NAME).read_text(encoding="utf-8"))
    assert graph["inventory"]["excluded_entries"] == [
        {
            "path": "vendor",
            "reason": "IGNORED_DIRECTORY_SCOPE_NOT_VERIFIED",
            "verification_status": "NOT_RUN",
        }
    ]


@pytest.mark.parametrize("unsafe_child", ["assembled.staging", "assembled"])
def test_repository_pipeline_rejects_owned_directory_symlinks_without_deleting_target(
    tmp_path: Path,
    unsafe_child: str,
) -> None:
    repository = _repository(tmp_path)
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"
    output.mkdir()
    protected = output / "protected"
    protected.mkdir()
    sentinel = protected / "sentinel.txt"
    sentinel.write_text("retain me\n", encoding="utf-8")
    (output / unsafe_child).symlink_to(protected, target_is_directory=True)

    with pytest.raises(RouteError, match="PIPELINE_OUTPUT_UNSAFE"):
        run_repository_pipeline(
            repository,
            f"local:unsafe-{unsafe_child}",
            "python",
            "typescript",
            cases,
            output,
        )

    assert sentinel.read_text(encoding="utf-8") == "retain me\n"
    assert protected.is_dir()
    assert (output / unsafe_child).is_symlink()


def test_repository_pipeline_rejects_project_graph_drift_during_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"
    original_verify = pipeline_module.verify_assembled_project

    def verify_then_mutate(
        target_language: str,
        destination: Path,
        *,
        cases_directory: Path | None = None,
        cases_manifest: dict[str, object] | None = None,
    ):
        result = original_verify(
            target_language,
            destination,
            cases_directory=cases_directory,
            cases_manifest=cases_manifest,
        )
        (repository / "late-resource.json").write_text('{"changed": true}', encoding="utf-8")
        return result

    monkeypatch.setattr(pipeline_module, "verify_assembled_project", verify_then_mutate)

    with pytest.raises(RouteError, match="PROJECT_GRAPH_CHANGED_DURING_PIPELINE"):
        run_repository_pipeline(
            repository,
            "local:project-graph-drift",
            "python",
            "typescript",
            cases,
            output,
        )

    assert not (output / "assembled").exists()
    assert not (output / "assembled.staging").exists()
    assert not (output / PROJECT_GRAPH_NAME).exists()


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
    previous_graph = (output / PROJECT_GRAPH_NAME).read_bytes()
    (repository / "math.py").write_text(
        "def add(left: int, right: int) -> int:\n    return left - right\n",
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
    assert not (output / "artifact-manifest.json").exists()
    assert not list(output.glob("*.previous-handoff"))
    assert (output / PROJECT_GRAPH_NAME).read_bytes() == previous_graph
    assert (output / "assembled").is_dir()
    assert not (output / "assembled.staging").exists()


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


def test_repository_pipeline_preserves_uniform_module_analyzer_not_run_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "math.swift").write_text(
        "func add(_ left: Int64, _ right: Int64) -> Int64 { left + right }\n",
        encoding="utf-8",
    )
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "WU-00001.json").write_text(
        json.dumps([{"args": [2, 3], "expected": 5}]),
        encoding="utf-8",
    )

    def analyzer_not_run(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_OFFLINE_SEED_NOT_RUN")

    monkeypatch.setattr(discovery_module, "inventory_module", analyzer_not_run)

    with pytest.raises(
        RouteError,
        match="^SWIFT_ANALYZER_DEPENDENCY_OFFLINE_SEED_NOT_RUN$",
    ):
        run_repository_pipeline(
            repository,
            "local:swift-analyzer-not-run",
            "swift",
            "java",
            cases,
            tmp_path / "pipeline",
        )
