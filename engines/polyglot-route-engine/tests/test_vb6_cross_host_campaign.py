from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

from elmos_polyglot_route.models import RouteError

REPO = Path(__file__).resolve().parents[3]
PREPARED = REPO / "verification-packs" / "vb6-cross-host-prepared-v1"


def _campaign_module() -> ModuleType:
    script = REPO / "scripts" / "batch29" / "run_vb6_cross_host_campaign.py"
    spec = importlib.util.spec_from_file_location("vb6_cross_host_campaign", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CAMPAIGN = _campaign_module()


def _copy_request(tmp_path: Path, route_key: str) -> Path:
    destination = tmp_path / "requests" / route_key
    shutil.copytree(PREPARED / route_key, destination)
    return destination


def _windows_receipt(request_root: Path, windows_root: Path) -> dict[str, object]:
    request = CAMPAIGN._load_request(request_root)
    windows_root.mkdir(parents=True)
    runs: list[dict[str, object]] = []
    for corpus in request["corpora"]:
        roles = CAMPAIGN._artifact_roles(
            request_root,
            corpus,
            request["source_language"],
            request["target_language"],
        )
        local_report = json.loads(
            CAMPAIGN._read_bound(request_root, roles["local_report"])
        )
        report_path = windows_root / corpus["corpus"] / "vb6-side-report.json"
        CAMPAIGN._write_json(
            report_path,
            {
                "status": "PASSED",
                "language": "vb6",
                "observations": local_report["observations"],
            },
        )
        binding = CAMPAIGN._binding(report_path, windows_root)
        runs.append(
            {
                "corpus": corpus["corpus"],
                "status": "PASSED_LOCAL",
                "report": binding,
                "artifact_count": 1,
                "artifacts": [binding],
            }
        )
    receipt = {
        "schema_version": 1,
        "kind": "elmos.vb6-cross-host-windows-receipt",
        "route_key": request["route_key"],
        "request_sha256": CAMPAIGN._request_sha256(request_root),
        "runs": runs,
        "windows_vb6_side_status": "PASSED_LOCAL",
        "evidence_class": "GOVERNED_EXTERNAL_SELF_ATTESTED",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    CAMPAIGN._write_json(windows_root / "windows-receipt.json", receipt)
    return receipt


def _prepare_set(root: Path, route_keys: tuple[str, ...]) -> None:
    records = [
        {
            "route_key": route_key,
            **CAMPAIGN._binding(root / route_key / "campaign-request.json", root),
        }
        for route_key in route_keys
    ]
    CAMPAIGN._write_json(
        root / "prepare-set-result.json",
        {
            "schema_version": 1,
            "kind": "elmos.vb6-cross-host-prepare-set-result",
            "route_count": len(route_keys),
            "prepared": list(route_keys),
            "reused": [],
            "requests": records,
            "windows_vb6_side_status": "NOT_RUN",
            "independent_verification_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        },
    )


def test_checked_in_prepare_set_is_digest_complete() -> None:
    result = CAMPAIGN._load_prepare_set(PREPARED)
    assert result["route_count"] == 26
    assert len(result["requests"]) == 26
    assert result["certification_status"] == "NOT_CERTIFIED"


def test_checked_in_requests_match_cross_host_schema() -> None:
    schema = json.loads(
        (REPO / "schemas" / "batch29" / "vb6-cross-host-campaign.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(json.loads((PREPARED / "prepare-set-result.json").read_text()))
    for route_key in CAMPAIGN.VB6_EXACT_ROUTE_KEYS:
        validator.validate(
            json.loads((PREPARED / route_key / "campaign-request.json").read_text())
        )


def test_request_rejects_duplicate_artifact_role(tmp_path: Path) -> None:
    request_root = _copy_request(tmp_path, "java-to-vb6")
    request_path = request_root / "campaign-request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["corpora"][0]["artifacts"][-1] = copy.deepcopy(
        request["corpora"][0]["artifacts"][0]
    )
    CAMPAIGN._write_json(request_path, request)

    with pytest.raises(RouteError, match="VB6_CAMPAIGN_REQUEST_ARTIFACT_SET_INVALID"):
        CAMPAIGN._load_request(request_root)


def test_request_rejects_duplicate_corpus(tmp_path: Path) -> None:
    request_root = _copy_request(tmp_path, "java-to-vb6")
    request_path = request_root / "campaign-request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["corpora"].append(copy.deepcopy(request["corpora"][0]))
    CAMPAIGN._write_json(request_path, request)

    with pytest.raises(RouteError, match="VB6_CAMPAIGN_REQUEST_CORPUS_SET_INVALID"):
        CAMPAIGN._load_request(request_root)


def test_request_rejects_unbound_identifier_plan(tmp_path: Path) -> None:
    request_root = _copy_request(tmp_path, "java-to-vb6")
    plan_path = request_root / "development" / "inputs" / "identifier-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["source_ir_sha256"] = "sha256:" + "0" * 64
    CAMPAIGN._write_json(plan_path, plan)
    request_path = request_root / "campaign-request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    binding = CAMPAIGN._binding(plan_path, request_root)
    request["corpora"][0]["artifacts"] = [
        binding if item["path"] == binding["path"] else item
        for item in request["corpora"][0]["artifacts"]
    ]
    CAMPAIGN._write_json(request_path, request)

    with pytest.raises(RouteError, match="IDENTIFIER_PLAN_SOURCE_BINDING_MISMATCH"):
        CAMPAIGN._load_request(request_root)


def test_request_rejects_hard_linked_artifact(tmp_path: Path) -> None:
    request_root = _copy_request(tmp_path, "java-to-vb6")
    source = request_root / "development" / "inputs" / "Pricing.java"
    alias = request_root / "hard-link-alias"
    os.link(source, alias)

    with pytest.raises(RouteError, match="VB6_CAMPAIGN_ARTIFACT_UNSAFE"):
        CAMPAIGN._load_request(request_root)


def test_windows_output_is_not_published_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "windows-output"

    def fail_after_write(_request: Path, staging: Path) -> None:
        (staging / "partial.txt").write_text("partial", encoding="utf-8")
        raise RouteError("EXPECTED_TEST_FAILURE")

    monkeypatch.setattr(CAMPAIGN, "_execute_windows_unpublished", fail_after_write)
    with pytest.raises(RouteError, match="EXPECTED_TEST_FAILURE"):
        CAMPAIGN.execute_windows(tmp_path / "unused", output)

    assert not output.exists()
    assert not list(tmp_path.glob(".windows-output.staging-*"))


def test_prepare_output_is_not_published_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "prepared-output"

    def fail_after_write(_repo: Path, _route: str, staging: Path) -> None:
        (staging / "partial.txt").write_text("partial", encoding="utf-8")
        raise RouteError("EXPECTED_PREPARE_FAILURE")

    monkeypatch.setattr(CAMPAIGN, "_prepare_unpublished", fail_after_write)
    with pytest.raises(RouteError, match="EXPECTED_PREPARE_FAILURE"):
        CAMPAIGN.prepare(tmp_path / "unused", "java-to-vb6", output)

    assert not output.exists()
    assert not list(tmp_path.glob(".prepared-output.staging-*"))


def test_route_partition_rejects_non_string_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(CAMPAIGN, "VB6_EXACT_ROUTE_KEYS", ("java-to-vb6",))
    assert not CAMPAIGN._valid_route_partition(
        {"prepared": [["java-to-vb6"]], "reused": []}, "prepared", "reused"
    )


def test_verifier_accepts_exact_receipt_and_rejects_duplicate_run(
    tmp_path: Path,
) -> None:
    request_root = _copy_request(tmp_path, "java-to-vb6")
    windows_root = tmp_path / "windows"
    receipt = _windows_receipt(request_root, windows_root)
    result = CAMPAIGN.verify(
        request_root, windows_root, tmp_path / "verification.json"
    )
    schema = json.loads(
        (REPO / "schemas" / "batch29" / "vb6-cross-host-campaign.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema)
    validator.validate(receipt)
    validator.validate(result)
    assert result["status"] == "PASSED_LOCAL_CROSS_HOST"
    assert result["certification_status"] == "NOT_CERTIFIED"

    duplicate = copy.deepcopy(receipt)
    duplicate["runs"][-1] = copy.deepcopy(duplicate["runs"][0])
    CAMPAIGN._write_json(windows_root / "windows-receipt.json", duplicate)
    with pytest.raises(RouteError, match="VB6_CAMPAIGN_WINDOWS_RUN_SET_INVALID"):
        CAMPAIGN._load_windows_receipt(
            request_root, windows_root, CAMPAIGN._load_request(request_root)
        )


def test_set_execution_and_verification_are_resumable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    route_keys = ("java-to-vb6", "vb6-to-java")
    request_root = tmp_path / "request-set"
    for route_key in route_keys:
        shutil.copytree(PREPARED / route_key, request_root / route_key)
    monkeypatch.setattr(CAMPAIGN, "VB6_EXACT_ROUTE_KEYS", route_keys)
    _prepare_set(request_root, route_keys)

    def execute(request: Path, output: Path) -> dict[str, object]:
        return _windows_receipt(request, output)

    monkeypatch.setattr(CAMPAIGN, "execute_windows", execute)
    windows_root = tmp_path / "windows-set"
    first = CAMPAIGN.execute_windows_set(request_root, windows_root)
    second = CAMPAIGN.execute_windows_set(request_root, windows_root)
    assert first == second
    assert first["completed"] == list(route_keys)

    verified_root = tmp_path / "verified-set"
    verified = CAMPAIGN.verify_set(request_root, windows_root, verified_root)
    replayed = CAMPAIGN.verify_set(request_root, windows_root, verified_root)
    assert verified == replayed
    assert verified["route_count"] == 2
    assert verified["status"] == "PASSED_LOCAL_CROSS_HOST"
    assert verified["certification_status"] == "NOT_CERTIFIED"
