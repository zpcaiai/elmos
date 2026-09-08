from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from elmos_repository_orchestrator.contracts import ContractError
from elmos_repository_orchestrator.cli import main
from elmos_repository_orchestrator.production_runtime import (
    probe_production_runtime,
    runtime_preflight,
)


PLAN_PATH = Path(__file__).parents[1] / "config" / "ai-runtime-plan.json"
PLAN = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
NOW = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)
DIGEST = "a" * 64


def environment() -> dict[str, str]:
    return {
        "ELMOS_CONTROL_PLANE_BASE_URL": "https://control.elmos.example",
        "ELMOS_OPERATIONS_API_KEY": "short-lived-secret",
        "ELMOS_OPERATIONS_TENANT_ID": "tenant-1",
        "ELMOS_OPERATIONS_ACTOR_ID": "operator-1",
        "ELMOS_RUNNER_NODE_ID": "runner-1",
        "ELMOS_RUNNER_POOL_ID": "pool-1",
        "ELMOS_RUNNER_CAPABILITIES": "generation:multi,translation:java-python",
        "ELMOS_RUNNER_AGENT_VERSION": "1.2.3",
        "ELMOS_RUNNER_AGENT_IMAGE": f"registry.example/elmos/runner-agent@sha256:{DIGEST}",
        "ELMOS_RUNNER_IMAGE_GENERATION": f"registry.example/elmos/generation@sha256:{DIGEST}",
        "ELMOS_RUNNER_IMAGE_ALLOWLIST_VERSION": "allowlist-v1",
        "ELMOS_RUNTIME_PROBE_ACK": PLAN["gate_id"],
    }


class FakeResponse:
    def __init__(self, body: dict, *, fail: bool = False) -> None:
        self.body = body
        self.fail = fail

    def raise_for_status(self) -> None:
        if self.fail:
            raise RuntimeError("provider details must not escape")

    def json(self) -> dict:
        return self.body


class FakeRuntimeClient:
    def __init__(self, node: dict | None = None, *, fail_path: str | None = None) -> None:
        self.node = node or {
            "runnerNodeId": "runner-1",
            "runnerPoolId": "pool-1",
            "agentVersion": "1.2.3",
            "fleetStatus": "READY",
            "capabilities": ["generation:multi", "translation:java-python"],
            "maxConcurrency": 2,
            "attestationVerified": True,
            "attestationVerifiedAt": (NOW - timedelta(minutes=5)).isoformat(),
            "imageAllowlistVersion": "allowlist-v1",
            "lastHeartbeatAt": (NOW - timedelta(seconds=15)).isoformat(),
        }
        self.fail_path = fail_path
        self.requests: list[tuple[str, dict]] = []

    def get(self, path: str, **kwargs):
        self.requests.append((path, kwargs))
        if path == "/actuator/health/readiness" or path == "/actuator/health/liveness":
            body = {"status": "UP"}
        elif path == "/runner/v1/reaper/last-run":
            body = {"checkedAt": (NOW - timedelta(seconds=2)).isoformat()}
        else:
            body = {"schemaVersion": "1.0.0", "items": [self.node], "returned": 1}
        return FakeResponse(body, fail=path == self.fail_path)


def test_preflight_lists_missing_bindings_and_accepts_exact_configuration() -> None:
    blocked = runtime_preflight(PLAN, environment={})
    assert blocked["status"] == "BLOCKED"
    assert "missing_environment:ELMOS_CONTROL_PLANE_BASE_URL" in blocked["blockers"]
    assert blocked["production_certification"] == "NOT_CERTIFIED"
    assert runtime_preflight(PLAN, environment=environment())["status"] == "READY"


def test_probe_validates_real_api_shape_scope_freshness_and_hides_credentials() -> None:
    client = FakeRuntimeClient()
    result = probe_production_runtime(PLAN, environment=environment(), client=client, now=NOW)
    assert result["status"] == "EXECUTED_UNVERIFIED"
    assert result["control_plane"]["status"] == "UP"
    assert result["runner"]["status"] == "READY"
    assert result["runner"]["inventory"]["runnerNodeId"] == "runner-1"
    assert result["runner"]["heartbeat_age_seconds"] == 15.0
    assert result["independent_verification"] == "NOT_RUN"
    assert result["production_certification"] == "NOT_CERTIFIED"
    assert "short-lived-secret" not in str(result)
    inventory_request = client.requests[-1]
    assert inventory_request[1]["headers"]["X-ELMOS-Operations-Key"] == "short-lived-secret"


def test_probe_fails_closed_for_ack_attestation_staleness_and_unknown_http() -> None:
    values = environment()
    values["ELMOS_RUNTIME_PROBE_ACK"] = "wrong"
    with pytest.raises(ContractError, match="acknowledgment"):
        probe_production_runtime(PLAN, environment=values, client=FakeRuntimeClient(), now=NOW)

    unattested = deepcopy(FakeRuntimeClient().node)
    unattested["attestationVerified"] = False
    with pytest.raises(ContractError, match="attestation"):
        probe_production_runtime(PLAN, environment=environment(), client=FakeRuntimeClient(unattested), now=NOW)

    stale = deepcopy(FakeRuntimeClient().node)
    stale["lastHeartbeatAt"] = (NOW - timedelta(minutes=10)).isoformat()
    with pytest.raises(ContractError, match="stale"):
        probe_production_runtime(PLAN, environment=environment(), client=FakeRuntimeClient(stale), now=NOW)

    with pytest.raises(ContractError, match="unknown result") as failure:
        probe_production_runtime(
            PLAN,
            environment=environment(),
            client=FakeRuntimeClient(fail_path="/actuator/health/readiness"),
            now=NOW,
        )
    assert "provider details" not in str(failure.value)


def test_runtime_plan_cannot_weaken_attestation_or_use_mutable_images() -> None:
    weakened = deepcopy(PLAN)
    weakened["runner"]["attestation_required"] = False
    with pytest.raises(ContractError, match="verified attestation"):
        runtime_preflight(weakened, environment=environment())

    mutable = environment()
    mutable["ELMOS_RUNNER_AGENT_IMAGE"] = "registry.example/elmos/runner-agent:latest"
    result = runtime_preflight(PLAN, environment=mutable)
    assert result["status"] == "BLOCKED"
    assert result["blockers"][0].startswith("runner_image:")


def test_runtime_cli_preflight_and_probe_are_explicit(capsys) -> None:
    assert main(["runtime-preflight", "--plan", str(PLAN_PATH), "--expect-blocked"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"
    assert main(["runtime-probe", "--plan", str(PLAN_PATH)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "BLOCKED"
    assert result["reasons"] == ["execution_flag_required:runtime-probe requires --execute"]
