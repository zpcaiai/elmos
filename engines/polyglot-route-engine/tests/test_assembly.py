"""Tests for `assembly.py`: turning a batch report's PASSED units into one project.

Most tests here construct a batch report and batch output directory by hand,
deliberately bypassing `run_batch`/`migrate`, so they exercise assembly's own
placement, namespacing and fail-closed logic without requiring any of the four
exact language toolchains to be installed. `test_end_to_end_...` is the
exception: it drives the real `plan_repository -> discover_repository ->
run_batch -> assemble_project -> verify_assembled_project` pipeline, mirroring
`test_repository_pipeline.py`'s conventions, and therefore does require the
real Python and TypeScript toolchains pinned by `toolchains.py`.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route.assembly import (
    MANIFEST_NAME,
    assemble_project,
    verify_assembled_project,
    write_assembly_deployment_guidance,
)
from elmos_polyglot_route.batch import run_batch
from elmos_polyglot_route.discovery import Verdict, discover_repository
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.repository import plan_repository


def _digest(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write_unit(batch_output: Path, unit_id: str, target_path: str, content: str) -> None:
    directory = batch_output / "units" / unit_id
    directory.mkdir(parents=True)
    (directory / target_path).write_text(content, encoding="utf-8")


def _passed_unit(unit_id: str, target_path: str, content: str, *, function_name: str = "calculate") -> dict[str, Any]:
    return {
        "id": unit_id,
        "source_path": f"src/{unit_id}.src",
        "status": "PASSED",
        "function_name": function_name,
        "target_path": target_path,
        "target_sha256": _digest(content),
        "evidence_path": f"units/{unit_id}/route-evidence.json",
    }


def _batch_report(target_language: str, units: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.repository-batch-report",
        "status": "PARTIAL",
        "repository_ref": "local:customer-repository",
        "snapshot_sha256": "deadbeef",
        "route_id": f"python-to-{target_language}",
        "source_language": "python",
        "target_language": target_language,
        "units": units,
    }


PYTHON_UNIT_A = "def calculate(a: int, b: int) -> int:\n    return a + b\n"
PYTHON_UNIT_B = "def calculate(a: int, b: int) -> int:\n    return a - b\n"
JAVA_UNIT = (
    "public final class Migrated {\n"
    "    public static long add(long a, long b) {\n"
    "        return (a + b);\n"
    "    }\n"
    "}\n"
)


def test_assemble_places_python_units_under_collision_free_modules(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", "migrated.py", PYTHON_UNIT_A)
    _write_unit(batch_output, "WU-00002", "migrated.py", PYTHON_UNIT_B)
    report = _batch_report(
        "python",
        [
            _passed_unit("WU-00001", "migrated.py", PYTHON_UNIT_A),
            _passed_unit("WU-00002", "migrated.py", PYTHON_UNIT_B),
        ],
    )

    destination = tmp_path / "assembled"
    manifest = assemble_project(report, batch_output, destination)

    assert manifest["kind"] == "elmos.repository-assembly-report"
    assert manifest["included_unit_count"] == 2
    assert manifest["excluded_unit_count"] == 0
    assert manifest["build_verification_status"] == "NOT_RUN"

    first = destination / "src" / "elmos_generated" / "wu00001.py"
    second = destination / "src" / "elmos_generated" / "wu00002.py"
    assert first.read_text(encoding="utf-8") == PYTHON_UNIT_A
    assert second.read_text(encoding="utf-8") == PYTHON_UNIT_B
    # Same function name in both units never collides because each keeps its own module.
    assert first.read_text().count("def calculate") == 1
    assert second.read_text().count("def calculate") == 1
    assert (destination / "src" / "elmos_generated" / "__init__.py").is_file()
    assert (destination / "pyproject.toml").is_file()
    assert (destination / MANIFEST_NAME).is_file()


def test_assemble_wraps_each_java_unit_in_its_own_package(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", "Migrated.java", JAVA_UNIT)
    report = _batch_report("java", [_passed_unit("WU-00001", "Migrated.java", JAVA_UNIT, function_name="add")])

    destination = tmp_path / "assembled"
    manifest = assemble_project(report, batch_output, destination)

    placed = destination / "src" / "main" / "java" / "elmos" / "generated" / "wu00001" / "Migrated.java"
    content = placed.read_text(encoding="utf-8")
    assert content.startswith("package elmos.generated.wu00001;\n\n")
    assert "public final class Migrated" in content
    assert manifest["included_units"][0]["assembled_path"] == "src/main/java/elmos/generated/wu00001/Migrated.java"
    assert (destination / "pom.xml").is_file()


def test_assemble_excludes_non_passed_units_but_records_them(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", "migrated.py", PYTHON_UNIT_A)
    report = _batch_report(
        "python",
        [
            _passed_unit("WU-00001", "migrated.py", PYTHON_UNIT_A),
            {"id": "WU-00002", "status": "FAILED", "reason": "TARGET_VALIDATION_FAILED:javac:boom"},
            {"id": "WU-00003", "status": "SKIPPED_NO_CASES", "reason": "No behavior-case corpus."},
        ],
    )

    manifest = assemble_project(report, batch_output, tmp_path / "assembled")

    assert manifest["included_unit_count"] == 1
    assert manifest["excluded_unit_count"] == 2
    excluded_ids = {unit["id"] for unit in manifest["excluded_units"]}
    assert excluded_ids == {"WU-00002", "WU-00003"}


def test_assemble_rejects_content_that_drifted_from_the_recorded_hash(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", "migrated.py", PYTHON_UNIT_A)
    unit = _passed_unit("WU-00001", "migrated.py", PYTHON_UNIT_A)
    unit["target_sha256"] = _digest("something else entirely")
    report = _batch_report("python", [unit])

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_CONTENT_DRIFTED"):
        assemble_project(report, batch_output, tmp_path / "assembled")


def test_assemble_rejects_a_batch_report_with_no_passed_units(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    batch_output.mkdir()
    report = _batch_report("python", [{"id": "WU-00001", "status": "SKIPPED_NOT_READY", "reason": "UNSUPPORTED"}])

    with pytest.raises(RouteError, match="ASSEMBLY_NO_PASSED_UNITS_TO_ASSEMBLE"):
        assemble_project(report, batch_output, tmp_path / "assembled")


def test_assemble_rejects_a_target_path_that_is_not_a_bare_filename(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", "migrated.py", PYTHON_UNIT_A)
    unit = _passed_unit("WU-00001", "../migrated.py", PYTHON_UNIT_A)
    report = _batch_report("python", [unit])

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_TARGET_PATH_INVALID"):
        assemble_project(report, batch_output, tmp_path / "assembled")


def test_assemble_refuses_to_overwrite_an_existing_destination(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", "migrated.py", PYTHON_UNIT_A)
    report = _batch_report("python", [_passed_unit("WU-00001", "migrated.py", PYTHON_UNIT_A)])
    destination = tmp_path / "assembled"
    destination.mkdir()

    with pytest.raises(RouteError, match="ASSEMBLY_DESTINATION_ALREADY_EXISTS"):
        assemble_project(report, batch_output, destination)


def test_verify_assembled_project_requires_a_manifest(tmp_path: Path) -> None:
    destination = tmp_path / "assembled"
    destination.mkdir()
    with pytest.raises(RouteError, match="ASSEMBLY_MANIFEST_MISSING"):
        verify_assembled_project("python", destination)


def test_end_to_end_pipeline_assembles_and_build_verifies_a_python_project(tmp_path: Path) -> None:
    repository = tmp_path / "customer-repository"
    (repository / "src").mkdir(parents=True)
    (repository / "src" / "pricing.py").write_text(
        "def calculate(subtotal: float, tax: float) -> float:\n"
        "    if tax < 0:\n"
        "        return subtotal\n"
        "    return subtotal + tax\n",
        encoding="utf-8",
    )
    (repository / "src" / "shipping.py").write_text(
        "def calculate(weight: float, rate: float) -> float:\n    return weight * rate\n",
        encoding="utf-8",
    )

    plan = plan_repository(repository, "local:customer-repository", "python", "typescript")
    discovery = discover_repository(plan, repository)
    ready_units = [result for result in discovery["results"] if result["verdict"] == Verdict.READY]
    assert len(ready_units) == 2

    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / f"{ready_units[0]['id']}.json").write_text(
        json.dumps([{"args": [100.0, 5.0], "expected": 105.0}, {"args": [100.0, -1.0], "expected": 100.0}]),
        encoding="utf-8",
    )
    (cases / f"{ready_units[1]['id']}.json").write_text(
        json.dumps([{"args": [2.0, 3.0], "expected": 6.0}]),
        encoding="utf-8",
    )

    batch_report = run_batch(discovery, repository, cases, tmp_path / "batch")
    assert batch_report["status_counts"]["PASSED"] == 2

    destination = tmp_path / "assembled"
    manifest = assemble_project(batch_report, tmp_path / "batch", destination)
    assert manifest["included_unit_count"] == 2
    assert manifest["build_verification_status"] == "NOT_RUN"
    assert not (destination / "docs" / "LOCAL_RUN.md").exists()

    verified = verify_assembled_project("typescript", destination)
    assert verified["build_verification_status"] == "PASSED"
    assert (destination / "dist").is_dir()
    assert (destination / "docs" / "LOCAL_RUN.md").is_file()
    assert (destination / "docs" / "CLOUD_PUBLISHING.md").is_file()
    assert (destination / "deploy" / "deployment-options.json").is_file()

    on_disk_manifest = json.loads((destination / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert on_disk_manifest["build_verification_status"] == "PASSED"


def test_write_assembly_deployment_guidance_is_reusable_independent_of_verify(tmp_path: Path) -> None:
    destination = tmp_path / "assembled"
    destination.mkdir()
    written = write_assembly_deployment_guidance(destination, "csharp", 3)
    assert set(written) == {
        "docs/LOCAL_RUN.md",
        "docs/CLOUD_PUBLISHING.md",
        "deploy/deployment-options.json",
    }
    for relative_path in written:
        assert (destination / relative_path).is_file()
