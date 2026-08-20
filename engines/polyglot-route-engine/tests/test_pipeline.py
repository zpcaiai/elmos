from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

import elmos_polyglot_route.pipeline as pipeline_module
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.pipeline import run_repository_pipeline


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


def test_pipeline_atomic_json_does_not_follow_a_dangling_temp_symlink(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    destination = output / "receipt.json"
    victim = tmp_path / "victim"
    legacy_temp = output / "receipt.json.tmp"
    legacy_temp.symlink_to(victim)

    pipeline_module._write_json(destination, {"status": "SAFE"})

    assert destination.is_file()
    assert not destination.is_symlink()
    assert legacy_temp.is_symlink()
    assert not victim.exists()


def test_pipeline_digest_rejects_an_oversized_file_before_buffering(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.bin"
    with oversized.open("wb") as handle:
        handle.truncate(1_025)
    with pytest.raises(RouteError, match="TEST_LIMIT"):
        pipeline_module._stable_file(
            oversized,
            "TEST_FILE",
            max_bytes=1_024,
            limit_error="TEST_LIMIT",
        )


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
    assert (
        second["artifact"]["sha256"]
        == hashlib.sha256((output / "repository-migration-artifact.zip").read_bytes()).hexdigest()
    )
    assert second["independent_verification_status"] == "NOT_RUN"
    with zipfile.ZipFile(output / "repository-migration-artifact.zip") as archive:
        names = archive.namelist()
        assert "artifact-manifest.json" in names
        assert "assembled/package.json" in names
        assert "functional-conversion-report.json" in names
        assert "FUNCTION_CONVERSION_REPORT.md" in names
        manifest = json.loads(archive.read("artifact-manifest.json"))
        assert manifest["status"] == "COMPLETE"
        assert manifest["certification_status"] == "NOT_CERTIFIED"
        assert manifest["functional_conversion"]["numerator"] == 1
        assert manifest["functional_conversion"]["denominator"] == 1
    assert second["functional_conversion"]["exact_fraction"] == "1/1"
    assert second["functional_conversion"]["display_percent"] == "100.00%"
    assert second["functional_conversion"]["code_artifact_ready"] is True
    assert second["artifact_packaging"]["status"] == "PASSED"
    assert second["artifact_packaging"]["max_compressed_bytes"] == 256 * 1024 * 1024


@pytest.mark.parametrize(
    "incident",
    [
        "EXACT_TOOLCHAIN_UNAVAILABLE:typescript",
        "NATIVE_ANALYZER_FAILED:helper:panic",
        "NATIVE_ANALYZER_CONTRACT_INVALID:INVALID_FUNCTION_SIGNATURE",
    ],
)
def test_repository_pipeline_publishes_a_blocked_report_for_trusted_analysis_incidents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    incident: str,
) -> None:
    repository = _repository(tmp_path)
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"

    def blocked_discovery(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RouteError(incident)

    def batch_must_not_run(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("incident handoff must not enter migration")

    monkeypatch.setattr(pipeline_module, "discover_repository", blocked_discovery)
    monkeypatch.setattr(pipeline_module, "run_batch", batch_must_not_run)
    report = run_repository_pipeline(
        repository,
        "local:test-repository",
        "python",
        "typescript",
        cases,
        output,
    )

    assert report["status"] == "BLOCKED"
    assert report["artifact"] is None
    assert report["functional_conversion"]["denominator_complete"] is True
    assert report["functional_conversion"]["measurement_status"] == "MEASURED"
    assert report["functional_conversion"]["exact_fraction"] == "0/1"
    assert report["functional_conversion"]["code_artifact_ready"] is False
    full_report = json.loads((output / "functional-conversion-report.json").read_text(encoding="utf-8"))
    assert full_report["status_counts"] == {"NOT_RUN": 1}
    assert full_report["functions"][0]["failure"]["reason_code"] == incident.split(":", 1)[0]
    assert full_report["functions"][0]["failure"]["stage"] == "ANALYSIS"
    assert full_report["functions"][0]["improvement_actions"]
    assert full_report["evidence_boundary"]["target_behavior_oracle"] == "NOT_RUN"
    assert (output / "repository-pipeline-report.json").is_file()


def test_repository_pipeline_keeps_reports_when_artifact_capacity_is_exceeded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"
    monkeypatch.setattr(pipeline_module, "MAX_ARTIFACT_UNCOMPRESSED_BYTES", 1)

    report = run_repository_pipeline(
        repository,
        "local:test-repository",
        "python",
        "typescript",
        cases,
        output,
    )

    assert report["status"] == "BLOCKED"
    assert report["artifact"] is None
    assert report["artifact_packaging"]["status"] == "FAILED"
    assert report["artifact_packaging"]["reason_code"] == "PIPELINE_ARTIFACT_UNCOMPRESSED_LIMIT_EXCEEDED"
    assert report["functional_conversion"]["code_artifact_ready"] is False
    full_report = json.loads((output / "functional-conversion-report.json").read_text(encoding="utf-8"))
    assert full_report["status"] == "COMPLETE"
    assert full_report["code_artifact_ready"] is False
    assert full_report["report_id"] == report["functional_conversion"]["report_id"]
    assert (output / "FUNCTION_CONVERSION_REPORT.md").is_file()
    assert not (output / "artifact-manifest.json").exists()
    assert not (output / "repository-migration-artifact.zip").exists()


@pytest.mark.parametrize("mutation", ["bytes", "symlink", "extra"])
def test_repository_pipeline_rejects_artifact_inventory_drift_before_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    repository = _repository(tmp_path)
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"
    real_write = pipeline_module._write_deterministic_zip

    def mutate_after_inventory(
        artifact_output: Path,
        entries: list[dict[str, object]],
    ) -> tuple[Path, int, str]:
        victim_entry = next(entry for entry in entries if str(entry["path"]).startswith("assembled/"))
        victim = artifact_output / str(victim_entry["path"])
        if mutation == "bytes":
            victim.write_bytes(victim.read_bytes() + b"\n// drift\n")
        elif mutation == "symlink":
            outside = tmp_path / "outside-secret.txt"
            outside.write_text("must never enter the archive", encoding="utf-8")
            victim.unlink()
            victim.symlink_to(outside)
        else:
            (artifact_output / "unexpected-after-inventory.txt").write_text("drift", encoding="utf-8")
        return real_write(artifact_output, entries)

    monkeypatch.setattr(pipeline_module, "_write_deterministic_zip", mutate_after_inventory)
    expected = {
        "bytes": "PIPELINE_ARTIFACT_DESCRIPTOR_MISMATCH",
        "symlink": "PIPELINE_ARTIFACT_SOURCE_UNSAFE",
        "extra": "PIPELINE_ARTIFACT_INVENTORY_CHANGED_DURING_ARCHIVE",
    }[mutation]
    with pytest.raises(RouteError, match=expected):
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


def test_repository_pipeline_counts_a_class_method_as_an_unsuccessful_function(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    with (repository / "math.py").open("a", encoding="utf-8") as source:
        source.write(
            "\nclass Hidden:\n    def multiply(self, left: int, right: int) -> int:\n        return left * right\n"
        )
    report = run_repository_pipeline(
        repository,
        "local:test-repository",
        "python",
        "typescript",
        _cases(tmp_path),
        tmp_path / "pipeline",
    )

    assert report["status"] == "PARTIAL"
    assert report["functional_conversion"]["exact_fraction"] == "1/2"
    assert report["functional_conversion"]["denominator_complete"] is True
    full_report = json.loads((tmp_path / "pipeline" / "functional-conversion-report.json").read_text())
    failed = next(item for item in full_report["functions"] if item["status"] != "VERIFIED")
    assert failed["functional_description"]["text"] == (
        "Callable signature in math.py: Hidden.multiply(self, left: int, right: int) -> int"
    )
    assert failed["functional_description"]["source"] == "AST_SIGNATURE_DERIVED"
    assert failed["source_blocks"][0]["extraction_method"] == "PYTHON_AST_FUNCTION"
    assert failed["source_blocks"][0]["snippet"].lstrip().startswith("def multiply")
    assert "def add" not in failed["source_blocks"][0]["snippet"]
    assert failed["failure"]["reason_code"] == "PYTHON_NON_TOP_LEVEL_FUNCTION_OUTSIDE_PROFILE"


def test_repository_pipeline_reports_every_python_function_beyond_the_analysis_cap(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "many.py").write_text(
        "\n".join(f"def function_{index}(value: int) -> int:\n    return value" for index in range(41)) + "\n",
        encoding="utf-8",
    )
    cases = tmp_path / "cases"
    cases.mkdir()
    output = tmp_path / "pipeline"

    report = run_repository_pipeline(
        repository,
        "local:many-functions",
        "python",
        "typescript",
        cases,
        output,
    )

    assert report["status"] == "BLOCKED"
    assert report["functional_conversion"]["exact_fraction"] == "0/41"
    assert report["functional_conversion"]["reported_obligation_count"] == 41
    assert report["functional_conversion"]["denominator_complete"] is True
    full = json.loads((output / "functional-conversion-report.json").read_text(encoding="utf-8"))
    assert len(full["functions"]) == 41
    assert full["functions"][-1]["failure"]["reason_code"] == "CANDIDATE_ANALYSIS_LIMIT_EXCEEDED"


def test_repository_pipeline_recomputes_a_zero_percent_report_when_source_drifts(tmp_path: Path) -> None:
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
    (repository / "math.py").write_text(
        "def add(left: int, right: int) -> int:\n    return left - right\n",
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
    assert rerun["status"] == "BLOCKED"
    assert rerun["resumed_count"] == 0
    assert rerun["functional_conversion"]["exact_fraction"] == "0/1"
    assert rerun["functional_conversion"]["code_artifact_ready"] is False
    assert rerun["functional_conversion"]["report_id"] != first["functional_conversion"]["report_id"]
    assert not (output / "repository-migration-artifact.zip").exists()
    assert (output / "repository-pipeline-report.json").is_file()
    assert (output / "functional-conversion-report.json").is_file()
    assert (output / "FUNCTION_CONVERSION_REPORT.md").is_file()


def test_repository_pipeline_invalidates_checkpoint_when_cases_drift(tmp_path: Path) -> None:
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
    assert rerun["functional_conversion"]["report_id"] != first["functional_conversion"]["report_id"]


@pytest.mark.parametrize("operation", ["add", "delete", "rename", "bytes"])
def test_repository_pipeline_rejects_source_snapshot_changes_during_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    repository = _repository(tmp_path)
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"
    real_build = pipeline_module.build_conversion_report

    def mutate_after_report(*args: object, **kwargs: object) -> dict[str, object]:
        report = real_build(*args, **kwargs)
        source = repository / "math.py"
        if operation == "add":
            (repository / "extra.py").write_text("def extra(value: int) -> int:\n    return value\n", encoding="utf-8")
        elif operation == "delete":
            source.unlink()
        elif operation == "rename":
            source.rename(repository / "renamed.py")
        else:
            source.write_text("def add(left: int, right: int) -> int:\n    return left - right\n", encoding="utf-8")
        return report

    monkeypatch.setattr(pipeline_module, "build_conversion_report", mutate_after_report)
    with pytest.raises(RouteError, match="PIPELINE_SOURCE_SNAPSHOT_CHANGED_DURING_RUN"):
        run_repository_pipeline(
            repository,
            "local:test-repository",
            "python",
            "typescript",
            cases,
            output,
        )
    assert not (output / "repository-pipeline-report.json").exists()
    assert not (output / "repository-migration-artifact.zip").exists()


def test_repository_pipeline_rejects_case_inventory_changes_during_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"
    real_build = pipeline_module.build_conversion_report

    def add_case_after_report(*args: object, **kwargs: object) -> dict[str, object]:
        report = real_build(*args, **kwargs)
        (cases / "unexpected.json").write_text("[]\n", encoding="utf-8")
        return report

    monkeypatch.setattr(pipeline_module, "build_conversion_report", add_case_after_report)
    with pytest.raises(RouteError, match="PIPELINE_BEHAVIOR_CASES_CHANGED_DURING_RUN"):
        run_repository_pipeline(
            repository,
            "local:test-repository",
            "python",
            "typescript",
            cases,
            output,
        )
    assert not (output / "repository-pipeline-report.json").exists()
    assert not (output / "repository-migration-artifact.zip").exists()


def test_repository_pipeline_removes_stale_sharded_reports_before_an_early_failure(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "README.md").write_text("no source\n", encoding="utf-8")
    cases = tmp_path / "cases"
    cases.mkdir()
    output = tmp_path / "pipeline"
    shards = output / "functional-conversion-report-shards"
    shards.mkdir(parents=True)
    for path in (
        output / "functional-conversion-report.json",
        output / "FUNCTION_CONVERSION_REPORT.md",
        output / "FUNCTION_CONVERSION_REPORT_BUNDLE.zip",
        output / "FUNCTION_CONVERSION_REPORT_BUNDLE_MANIFEST.json",
        shards / "report-00001.json",
        shards / "report-00001.md",
    ):
        path.write_text("stale\n", encoding="utf-8")

    with pytest.raises(RouteError, match="NO_SOURCE_FILES"):
        run_repository_pipeline(
            repository,
            "local:no-source",
            "python",
            "typescript",
            cases,
            output,
        )
    assert not (output / "functional-conversion-report.json").exists()
    assert not (output / "FUNCTION_CONVERSION_REPORT.md").exists()
    assert not (output / "FUNCTION_CONVERSION_REPORT_BUNDLE.zip").exists()
    assert not (output / "FUNCTION_CONVERSION_REPORT_BUNDLE_MANIFEST.json").exists()
    assert not shards.exists()


def test_repository_pipeline_reports_zero_percent_without_behavior_evidence(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    cases = tmp_path / "cases"
    cases.mkdir()

    output = tmp_path / "pipeline"
    report = run_repository_pipeline(
        repository,
        "local:test-repository",
        "python",
        "typescript",
        cases,
        output,
    )

    assert report["status"] == "BLOCKED"
    assert report["artifact"] is None
    assert report["functional_conversion"]["exact_fraction"] == "0/1"
    assert report["functional_conversion"]["display_percent"] == "0.00%"
    assert report["functional_conversion"]["failure_summaries"][0]["failure_code"] == "SKIPPED_NO_CASES"
    assert not (output / "repository-migration-artifact.zip").exists()
    assert "补充独立行为用例" in (output / "FUNCTION_CONVERSION_REPORT.md").read_text(encoding="utf-8")


def test_repository_pipeline_source_behavior_failure_never_enters_the_numerator(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "WU-00001.json").write_text(
        json.dumps([{"args": [2, 3], "expected": 999}]),
        encoding="utf-8",
    )
    output = tmp_path / "pipeline"
    report = run_repository_pipeline(
        repository,
        "local:test-repository",
        "python",
        "typescript",
        cases,
        output,
    )

    assert report["status"] == "BLOCKED"
    assert report["functional_conversion"]["numerator"] == 0
    assert report["functional_conversion"]["failure_summaries"][0]["failure_code"] == "SOURCE_VALIDATION_FAILED"
    full_report = json.loads((output / "functional-conversion-report.json").read_text(encoding="utf-8"))
    assert full_report["functions"][0]["failure"]["stage"] == "SOURCE_BEHAVIOR_REPLAY"
    assert report["artifact"] is None
    assert not (output / "repository-migration-artifact.zip").exists()


@pytest.mark.parametrize(
    ("failure", "expected_build_status"),
    [
        ("ASSEMBLY_BUILD_VERIFICATION_FAILED:node:synthetic", "FAILED"),
        ("ASSEMBLY_BUILD_TIMEOUT:node", "FAILED"),
        ("EXACT_TOOLCHAIN_UNAVAILABLE:typescript", "NOT_RUN"),
    ],
)
def test_repository_pipeline_reports_a_target_build_failure_without_a_code_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    expected_build_status: str,
) -> None:
    repository = _repository(tmp_path)
    output = tmp_path / "pipeline"

    def failed_build(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RouteError(failure)

    monkeypatch.setattr(pipeline_module, "verify_assembled_project", failed_build)
    report = run_repository_pipeline(
        repository,
        "local:test-repository",
        "python",
        "typescript",
        _cases(tmp_path),
        output,
    )

    assert report["status"] == "BLOCKED"
    assert report["build_verification"]["status"] == expected_build_status
    assert report["functional_conversion"]["exact_fraction"] == "0/1"
    assert report["artifact"] is None
    assert (output / "functional-conversion-report.json").is_file()
    assert (output / "FUNCTION_CONVERSION_REPORT.md").is_file()
    full_report = json.loads((output / "functional-conversion-report.json").read_text(encoding="utf-8"))
    assert full_report["functions"][0]["failure"]["stage"] == "ASSEMBLY"
    assert full_report["functions"][0]["failure"]["reason_code"] == failure.split(":", 1)[0]
    assert full_report["functions"][0]["target_blocks"]
    assert not (output / "repository-migration-artifact.zip").exists()


def test_repository_pipeline_prunes_units_removed_from_a_new_snapshot(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    (repository / "subtract.py").write_text(
        "def subtract(left: int, right: int) -> int:\n    return left - right\n",
        encoding="utf-8",
    )
    cases = _cases(tmp_path)
    (cases / "WU-00002.json").write_text(
        json.dumps([{"args": [5, 3], "expected": 2}]),
        encoding="utf-8",
    )
    output = tmp_path / "pipeline"
    first = run_repository_pipeline(
        repository,
        "local:test-repository",
        "python",
        "typescript",
        cases,
        output,
    )
    assert first["functional_conversion"]["exact_fraction"] == "2/2"
    assert (output / "batch" / "units" / "WU-00002").is_dir()

    (repository / "subtract.py").unlink()
    (cases / "WU-00002.json").unlink()
    second = run_repository_pipeline(
        repository,
        "local:test-repository",
        "python",
        "typescript",
        cases,
        output,
    )

    assert second["functional_conversion"]["exact_fraction"] == "1/1"
    assert not (output / "batch" / "units" / "WU-00002").exists()
    checkpoint = (output / "batch" / "batch-checkpoint.jsonl").read_text(encoding="utf-8")
    assert "WU-00002" not in checkpoint
    with zipfile.ZipFile(output / "repository-migration-artifact.zip") as archive:
        assert not any(name.startswith("batch/units/WU-00002/") for name in archive.namelist())


def test_repository_pipeline_rejects_a_symlinked_unit_directory(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"
    units = output / "batch" / "units"
    units.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    (units / "WU-00001").symlink_to(external, target_is_directory=True)

    with pytest.raises(RouteError, match="WORK_UNIT_OUTPUT_UNSAFE"):
        run_repository_pipeline(
            repository,
            "local:test-repository",
            "python",
            "typescript",
            cases,
            output,
        )

    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert not (output / "functional-conversion-report.json").exists()


def test_repository_pipeline_rejects_a_symlinked_batch_directory(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    cases = _cases(tmp_path)
    output = tmp_path / "pipeline"
    output.mkdir()
    external = tmp_path / "external-batch"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    (output / "batch").symlink_to(external, target_is_directory=True)

    with pytest.raises(RouteError, match="PIPELINE_PATH_CONFINEMENT_FAILED"):
        run_repository_pipeline(
            repository,
            "local:test-repository",
            "python",
            "typescript",
            cases,
            output,
        )

    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert not (output / "functional-conversion-report.json").exists()
