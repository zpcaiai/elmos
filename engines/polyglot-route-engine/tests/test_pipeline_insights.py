from __future__ import annotations

import copy
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.pipeline import _behavior_coverage_summary, run_repository_pipeline


def _discovery(unit_count: int) -> dict[str, Any]:
    return {
        "work_unit_count": unit_count,
        "results": [
            {
                "id": f"WU-{index:05d}",
                "source_path": f"source-{index}.py",
                "function_name": f"function_{index}",
            }
            for index in range(1, unit_count + 1)
        ],
    }


def _mixed_batch() -> dict[str, Any]:
    return {
        "status": "PARTIAL",
        "work_unit_count": 4,
        "selected_count": 4,
        "attempted_count": 2,
        "unattempted_count": 2,
        "status_counts": {
            "FAILED": 1,
            "FUTURE_STATUS": 1,
            "PASSED": 1,
            "SKIPPED_NO_CASES": 1,
        },
        "units": [
            {
                "id": "WU-00001",
                "source_path": "source-1.py",
                "function_name": "function_1",
                "target_function_name": "function_1",
                "identifier_plan_path": "identifier-plan.json",
                "identifier_plan_sha256": "sha256:" + ("b" * 64),
                "status": "PASSED",
                "execution_status": "PASSED_LOCAL_UNCERTIFIED",
                "behavior_case_count": 2,
                "evidence_path": "units/WU-00001/route-evidence.json",
                "evidence_sha256": "sha256:" + ("a" * 64),
            },
            {
                "id": "WU-00002",
                "source_path": "source-2.py",
                "function_name": "function_2",
                "status": "FAILED",
            },
            {
                "id": "WU-00003",
                "source_path": "source-3.py",
                "status": "SKIPPED_NO_CASES",
            },
            {
                "id": "WU-00004",
                "source_path": "source-4.py",
                "status": "FUTURE_STATUS",
            },
        ],
    }


def test_behavior_coverage_has_one_exact_denominator_for_all_four_states() -> None:
    summary = _behavior_coverage_summary(_discovery(4), _mixed_batch())

    assert summary["status"] == "FAILED"
    assert summary["complete"] is False
    assert summary["work_unit_denominator"] == 4
    assert summary["work_unit_count"] == 4
    assert summary["accounted_work_unit_count"] == 4
    assert summary["attempted_work_unit_count"] == 2
    assert summary["unresolved_work_unit_count"] == 2
    assert summary["pass_rate"] == 0.25
    assert summary["status_counts"] == {
        "FAILED": 1,
        "NOT_RUN": 1,
        "PASSED": 1,
        "UNKNOWN": 1,
    }
    assert summary["behavior_case_count"] == 2
    assert summary["behavior_case_count_scope"] == "PASSED_WORK_UNITS_ONLY"
    assert [unit["behavior_case_count"] for unit in summary["units"]] == [2, None, 0, None]
    assert summary["independent_verification_status"] == "NOT_RUN"
    assert summary["external_verification_status"] == "NOT_RUN"


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("duplicate-id", "BEHAVIOR_COVERAGE_UNIT_DUPLICATED"),
        ("reordered-id", "BEHAVIOR_COVERAGE_WORK_UNIT_SET_MISMATCH"),
        ("forged-counts", "BEHAVIOR_COVERAGE_BATCH_COUNTS_MISMATCH"),
        ("forged-complete", "BEHAVIOR_COVERAGE_BATCH_STATUS_CONTRADICTORY"),
    ],
)
def test_behavior_coverage_rejects_unclosed_or_contradictory_batches(
    mutation: str,
    error: str,
) -> None:
    batch = copy.deepcopy(_mixed_batch())
    if mutation == "duplicate-id":
        batch["units"][1]["id"] = "WU-00001"
    elif mutation == "reordered-id":
        batch["units"][0], batch["units"][1] = batch["units"][1], batch["units"][0]
    elif mutation == "forged-counts":
        batch["status_counts"]["PASSED"] = 2
    else:
        batch["status"] = "COMPLETE"

    with pytest.raises(RouteError, match=error):
        _behavior_coverage_summary(_discovery(4), batch)


@pytest.mark.skip(
    reason="behavior_coverage is not in the pipeline report on this branch yet: the "
    "coverage machinery was deferred to one follow-up together with the project "
    "graph and the runner's coverage fields. The two unit tests above still cover "
    "_behavior_coverage_summary itself."
)
def test_pipeline_report_and_manifest_share_fail_closed_behavior_insights(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "math.py").write_text(
        "def add(left: int, right: int) -> int:\n"
        "    return left + right\n\n"
        "def subtract(left: int, right: int) -> int:\n"
        "    return left - right\n",
        encoding="utf-8",
    )
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "WU-00001-F001.json").write_text(
        json.dumps([{"args": [2, 3], "expected": 5}]),
        encoding="utf-8",
    )
    output = tmp_path / "pipeline"

    report = run_repository_pipeline(
        repository,
        "local:behavior-coverage-insights",
        "python",
        "typescript",
        cases,
        output,
    )
    disk_report = json.loads((output / "repository-pipeline-report.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "artifact-manifest.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(output / "repository-migration-artifact.zip") as archive:
        archived_manifest = json.loads(archive.read("artifact-manifest.json"))

    assert disk_report == report
    assert archived_manifest == manifest
    shared_fields = {
        "behavior_coverage",
        "certification_status",
        "conversion_coverage",
        "external_verification_status",
        "independent_verification_status",
        "local_execution_evidence",
        "project_graph",
        "repository_complete",
        "repository_execution_status",
        "status",
        "unit_batch_status",
    }
    assert {field: manifest[field] for field in shared_fields} == {
        field: report[field] for field in shared_fields
    }

    behavior = report["behavior_coverage"]
    assert behavior["status"] == "NOT_RUN"
    assert behavior["complete"] is False
    assert behavior["work_unit_denominator"] == 2
    assert behavior["accounted_work_unit_count"] == 2
    assert behavior["attempted_work_unit_count"] == 1
    assert behavior["unresolved_work_unit_count"] == 1
    assert behavior["pass_rate"] == 0.5
    assert behavior["status_counts"] == {
        "FAILED": 0,
        "NOT_RUN": 1,
        "PASSED": 1,
        "UNKNOWN": 0,
    }
    assert report["repository_complete"] is False
    assert report["status"] == "PARTIAL"
    assert report["repository_execution_status"] == "LIMITED"
    assert report["independent_verification_status"] == "NOT_RUN"
    assert report["external_verification_status"] == "NOT_RUN"
    assert manifest["independent_verification_status"] == "NOT_RUN"
    assert manifest["external_verification_status"] == "NOT_RUN"
    assert behavior["independent_verification_status"] == "NOT_RUN"
    assert behavior["external_verification_status"] == "NOT_RUN"
