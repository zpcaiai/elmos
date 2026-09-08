from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "batch29"
ENGINE_SRC = ROOT / "engines" / "polyglot-route-engine" / "src"
for path in (SCRIPTS, ENGINE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_vcpp6_cross_host_campaign as campaign  # noqa: E402
from elmos_polyglot_route.models import RouteError  # noqa: E402


def _passing_report(_emitted, language, _function, cases, _output):
    return {
        "status": "PASSED",
        "language": language,
        "observations": [{"case": index} for index, _ in enumerate(cases)],
    }


def test_prepare_binds_every_input_and_fails_on_transferred_byte_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(campaign, "validate", _passing_report)
    output = tmp_path / "prepared"

    manifest = campaign.prepare(ROOT, "vcpp6-to-python", output)

    assert manifest["prepared_side_status"] == "PASSED_LOCAL"
    assert manifest["windows_vcpp6_side_status"] == "NOT_RUN"
    assert manifest["independent_verification_status"] == "NOT_RUN"
    assert manifest["certification_status"] == "NOT_CERTIFIED"
    assert {item["corpus"] for item in manifest["corpora"]} == set(campaign.CORPORA)
    assert all(len(item["artifacts"]) == 6 for item in manifest["corpora"])
    assert campaign._load_request(output)["route_key"] == "vcpp6-to-python"

    cases = output / "development" / "inputs" / "cases.json"
    cases.write_bytes(cases.read_bytes() + b" ")
    with pytest.raises(RouteError, match="VCPP6_CAMPAIGN_ARTIFACT_DIGEST_MISMATCH"):
        campaign._load_request(output)


def test_vcpp6_vb6_routes_have_an_exact_source_fixture_contract() -> None:
    assert "vb6-to-vcpp6" in campaign.VCPP6_EXACT_ROUTE_KEYS
    assert "vcpp6-to-vb6" in campaign.VCPP6_EXACT_ROUTE_KEYS
    source, cases, function = campaign._fixture(
        ROOT / "engines" / "polyglot-route-engine" / "fixtures",
        "development",
        "vb6",
    )
    assert source.name == "pricing.bas"
    assert cases.name == "behavior-cases.json"
    assert function == "calculate"


def test_campaign_rejects_non_vcpp6_route_before_writing(tmp_path: Path) -> None:
    output = tmp_path / "forbidden"
    with pytest.raises(RouteError, match="VCPP6_CAMPAIGN_ROUTE_NOT_ALLOWED"):
        campaign.prepare(ROOT, "java-to-python", output)
    assert not output.exists()
