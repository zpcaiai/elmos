"""Adversarial closure tests for repository assembly and ZIP handoff."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

import elmos_polyglot_route.pipeline as pipeline_module
from elmos_polyglot_route.assembly import verify_assembled_project
from elmos_polyglot_route.discovery import discover_repository
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.pipeline import (
    ARTIFACT_MANIFEST_NAME,
    ARTIFACT_NAME,
    REPORT_NAME,
    run_repository_pipeline,
)
from elmos_polyglot_route.repository import plan_repository


def _write_repository(repository: Path, *, include_beta: bool = True) -> None:
    repository.mkdir(exist_ok=True)
    (repository / "alpha.py").write_text(
        "def alpha(left: int, right: int) -> int:\n    return left + right\n",
        encoding="utf-8",
    )
    if include_beta:
        (repository / "beta.py").write_text(
            "def beta(left: int, right: int) -> int:\n    return left - right\n",
            encoding="utf-8",
        )


def _write_cases(repository: Path, cases: Path, repository_ref: str) -> None:
    cases.mkdir(exist_ok=True)
    discovery = discover_repository(
        plan_repository(repository, repository_ref, "python", "typescript"),
        repository,
    )
    expected_by_function = {"alpha": 5, "beta": -1}
    for result in discovery["results"]:
        function_name = str(result["function_name"])
        (cases / f"{result['id']}.json").write_text(
            json.dumps(
                [
                    {
                        "args": [2, 3],
                        "expected": expected_by_function[function_name],
                    }
                ]
            ),
            encoding="utf-8",
        )


def _assert_zip_matches_embedded_manifest(output: Path) -> dict[str, object]:
    archive_path = output / ARTIFACT_NAME
    with zipfile.ZipFile(archive_path) as archive:
        manifest_bytes = archive.read(ARTIFACT_MANIFEST_NAME)
        manifest = json.loads(manifest_bytes)
        expected = {str(entry["path"]): (int(entry["bytes"]), str(entry["sha256"])) for entry in manifest["files"]}
        expected[ARTIFACT_MANIFEST_NAME] = (
            len(manifest_bytes),
            hashlib.sha256(manifest_bytes).hexdigest(),
        )
        infos = archive.infolist()
        assert len(infos) == len({info.filename for info in infos})
        assert {info.filename for info in infos} == set(expected)
        for info in infos:
            content = archive.read(info)
            expected_bytes, expected_sha256 = expected[info.filename]
            assert info.file_size == expected_bytes == len(content)
            assert hashlib.sha256(content).hexdigest() == expected_sha256
    return manifest


def _tamper_manifest_owned_input(assembled: Path, input_kind: str) -> None:
    manifest = json.loads((assembled / "assembly-manifest.json").read_text(encoding="utf-8"))
    if input_kind == "source":
        relative = str(manifest["included_units"][0]["assembled_path"])
    else:
        source_paths = {str(unit["assembled_path"]) for unit in manifest["included_units"]}
        relative = next(
            str(binding["path"]) for binding in manifest["build_inputs"] if str(binding["path"]) not in source_paths
        )
    victim = assembled / relative
    content = victim.read_bytes()
    assert content
    replacement = b"X" if content[:1] != b"X" else b"Y"
    victim.write_bytes(replacement + content[1:])


def test_artifact_inventory_excludes_swiftpm_build_cache_symlinks(tmp_path: Path) -> None:
    output = tmp_path / "output"
    assembled = output / "assembled"
    assembled.mkdir(parents=True)
    (assembled / "Package.swift").write_text("// generated package\n", encoding="utf-8")
    build_cache = assembled / ".build"
    build_cache.mkdir()
    release_target = build_cache / "arm64-apple-macosx"
    release_target.mkdir()
    (build_cache / "release").symlink_to(release_target)

    inventory = pipeline_module._artifact_inventory(output)

    assert [entry["path"] for entry in inventory] == ["assembled/Package.swift"]


def test_interrupted_archive_temporary_is_cleaned_and_zip_is_byte_closed(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    cases = tmp_path / "cases"
    output = tmp_path / "output"
    _write_repository(repository, include_beta=False)
    _write_cases(repository, cases, "local:archive-temporary-closure")
    output.mkdir()
    temporary_name = f"{ARTIFACT_NAME}.tmp"
    (output / temporary_name).write_bytes(b"interrupted prior ZIP bytes")

    report = run_repository_pipeline(
        repository,
        "local:archive-temporary-closure",
        "python",
        "typescript",
        cases,
        output,
    )

    assert report["status"] == "COMPLETE"
    assert not (output / temporary_name).exists()
    manifest = _assert_zip_matches_embedded_manifest(output)
    assert temporary_name not in {entry["path"] for entry in manifest["files"]}
    assert ARTIFACT_NAME not in {entry["path"] for entry in manifest["files"]}
    assert ARTIFACT_MANIFEST_NAME not in {entry["path"] for entry in manifest["files"]}


def test_rerun_prunes_units_absent_from_current_discovery_and_handoff(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    cases = tmp_path / "cases"
    output = tmp_path / "output"
    repository_ref = "local:current-discovery-unit-closure"
    _write_repository(repository)
    _write_cases(repository, cases, repository_ref)
    first = run_repository_pipeline(
        repository,
        repository_ref,
        "python",
        "typescript",
        cases,
        output,
    )
    assert first["status_counts"] == {"PASSED": 2}

    (repository / "beta.py").unlink()
    second = run_repository_pipeline(
        repository,
        repository_ref,
        "python",
        "typescript",
        cases,
        output,
    )

    assert second["status"] == "COMPLETE"
    assert second["work_unit_count"] == 1
    assert second["status_counts"] == {"PASSED": 1}
    assert not (output / "batch" / "units" / "WU-00002").exists()
    assert "WU-00002" not in (output / "batch" / "batch-checkpoint.jsonl").read_text(encoding="utf-8")
    manifest = _assert_zip_matches_embedded_manifest(output)
    assert not any("/WU-00002/" in str(entry["path"]) for entry in manifest["files"])


def test_build_verification_rejects_a_missing_manifest_owned_target(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    cases = tmp_path / "cases"
    output = tmp_path / "output"
    repository_ref = "local:assembly-target-closure"
    _write_repository(repository)
    _write_cases(repository, cases, repository_ref)
    run_repository_pipeline(
        repository,
        repository_ref,
        "python",
        "typescript",
        cases,
        output,
    )
    assembled = output / "assembled"
    manifest = json.loads((assembled / "assembly-manifest.json").read_text(encoding="utf-8"))
    victim = assembled / manifest["included_units"][1]["assembled_path"]
    victim.unlink()

    with pytest.raises(RouteError, match="ASSEMBLY_INCLUDED_SOURCE_MISSING_OR_UNSAFE"):
        verify_assembled_project("typescript", assembled)


@pytest.mark.parametrize(
    ("input_kind", "error_code"),
    (
        ("source", "ASSEMBLY_INCLUDED_SOURCE_DRIFTED"),
        ("build", "ASSEMBLY_BUILD_INPUT_DRIFTED"),
    ),
)
def test_pipeline_rejects_manifest_owned_input_tampered_after_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    input_kind: str,
    error_code: str,
) -> None:
    repository = tmp_path / "repository"
    cases = tmp_path / "cases"
    output = tmp_path / "output"
    repository_ref = f"local:post-commit-{input_kind}-drift"
    _write_repository(repository, include_beta=False)
    _write_cases(repository, cases, repository_ref)
    original_commit = pipeline_module._commit_owned_directory

    def commit_then_tamper(output_root: Path, staging_name: str, final_name: str) -> Path:
        assembled = original_commit(output_root, staging_name, final_name)
        _tamper_manifest_owned_input(assembled, input_kind)
        return assembled

    monkeypatch.setattr(pipeline_module, "_commit_owned_directory", commit_then_tamper)

    with pytest.raises(RouteError, match=error_code):
        run_repository_pipeline(
            repository,
            repository_ref,
            "python",
            "typescript",
            cases,
            output,
        )

    assert not (output / REPORT_NAME).exists()
    assert not (output / ARTIFACT_NAME).exists()
    assert not (output / ARTIFACT_MANIFEST_NAME).exists()


@pytest.mark.parametrize(
    ("input_kind", "error_code"),
    (
        ("source", "ASSEMBLY_INCLUDED_SOURCE_DRIFTED"),
        ("build", "ASSEMBLY_BUILD_INPUT_DRIFTED"),
    ),
)
def test_failed_post_commit_rerun_invalidates_prior_complete_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    input_kind: str,
    error_code: str,
) -> None:
    repository = tmp_path / "repository"
    cases = tmp_path / "cases"
    output = tmp_path / "output"
    repository_ref = f"local:failed-rerun-{input_kind}-drift"
    _write_repository(repository, include_beta=False)
    _write_cases(repository, cases, repository_ref)
    first = run_repository_pipeline(
        repository,
        repository_ref,
        "python",
        "typescript",
        cases,
        output,
    )
    assert first["status"] == "COMPLETE"
    assert (output / REPORT_NAME).is_file()
    assert (output / ARTIFACT_NAME).is_file()
    assert (output / ARTIFACT_MANIFEST_NAME).is_file()
    original_commit = pipeline_module._commit_owned_directory

    def commit_then_tamper(output_root: Path, staging_name: str, final_name: str) -> Path:
        assembled = original_commit(output_root, staging_name, final_name)
        _tamper_manifest_owned_input(assembled, input_kind)
        return assembled

    monkeypatch.setattr(pipeline_module, "_commit_owned_directory", commit_then_tamper)

    with pytest.raises(RouteError, match=error_code):
        run_repository_pipeline(
            repository,
            repository_ref,
            "python",
            "typescript",
            cases,
            output,
        )

    assert not (output / REPORT_NAME).exists()
    assert not (output / ARTIFACT_NAME).exists()
    assert not (output / ARTIFACT_MANIFEST_NAME).exists()
    assert not list(output.glob("*.previous-handoff"))


@pytest.mark.parametrize("input_kind", ("source", "build"))
def test_zip_recomputes_manifest_owned_inputs_after_final_directory_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    input_kind: str,
) -> None:
    repository = tmp_path / "repository"
    cases = tmp_path / "cases"
    output = tmp_path / "output"
    repository_ref = f"local:pre-archive-{input_kind}-drift"
    _write_repository(repository, include_beta=False)
    _write_cases(repository, cases, repository_ref)
    original_inventory = pipeline_module._artifact_inventory

    def tamper_then_inventory(output_root: Path) -> list[dict[str, object]]:
        _tamper_manifest_owned_input(output_root / "assembled", input_kind)
        return original_inventory(output_root)

    monkeypatch.setattr(pipeline_module, "_artifact_inventory", tamper_then_inventory)

    with pytest.raises(RouteError, match="ASSEMBLY_ARCHIVE_BUILD_INPUT_DRIFTED"):
        run_repository_pipeline(
            repository,
            repository_ref,
            "python",
            "typescript",
            cases,
            output,
        )

    assert not (output / REPORT_NAME).exists()
    assert not (output / ARTIFACT_NAME).exists()
    assert not (output / ARTIFACT_MANIFEST_NAME).exists()
