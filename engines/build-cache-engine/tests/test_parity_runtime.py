from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from elmos_build_cache.clock import ManualClock
from elmos_build_cache.config import CacheParityConfig, PromptCacheConfig
from elmos_build_cache.enums import MissReason
from elmos_build_cache.parity_runtime import (
    SERVING_GATE_KIND,
    ParityRuntime,
    serving_gate_statement,
)
from elmos_build_cache.security import (
    Ed25519ProvenanceSigner,
    HmacProvenanceSigner,
    SignedStatement,
)


class Sink:
    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []

    def put_cache_outcome(
        self,
        tenant_id: str,
        project_id: str,
        request_id: str,
        event_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]:
        assert tenant_id == "tenant-a"
        assert project_id == "project-a"
        assert request_id == document["request_id"]
        assert event_id == document["event_id"]
        stored = dict(document)
        self.documents.append(stored)
        return stored


class BrokenSink(Sink):
    def put_cache_outcome(
        self,
        tenant_id: str,
        project_id: str,
        request_id: str,
        event_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]:
        raise RuntimeError("connection details must not appear in the report")


class ServingControl:
    def __init__(self) -> None:
        self.enabled = True
        self.rollback_reasons: list[str] = []

    def is_serving(self) -> bool:
        return self.enabled

    def latch_rollback(self, reason_code: str) -> None:
        self.rollback_reasons.append(reason_code)
        self.enabled = False


def prompt_serving_config() -> CacheParityConfig:
    return replace(
        CacheParityConfig(),
        rollout_phase="internal",
        prompt_cache=replace(PromptCacheConfig(), enabled=True, mode="serve"),
    )


def signed_gate(
    config: CacheParityConfig,
    clock: ManualClock,
    *,
    tenant_id: str = "tenant-a",
    project_id: str = "project-a",
) -> tuple[SignedStatement, Ed25519ProvenanceSigner]:
    signer = Ed25519ProvenanceSigner.generate("serving-gate")
    claims = serving_gate_statement(
        config,
        tenant_id,
        project_id,
        ("provider_prompt",),
        issued_at=clock.now(),
        expires_at=clock.now() + 3_600,
    )
    return signer.sign_statement(SERVING_GATE_KIND, claims), signer


def test_real_action_outcomes_are_content_free_and_budgeted() -> None:
    sink = Sink()
    runtime = ParityRuntime(CacheParityConfig(), "tenant-a", "project-a", sink=sink)

    hit = runtime.observe_action(node_id="node-a", action_key="sha256:" + "a" * 64, hit=True)
    corrupt = runtime.observe_action(
        node_id="node-b",
        action_key="sha256:" + "b" * 64,
        hit=False,
        miss_reasons=(MissReason.ARTIFACT_CORRUPT,),
    )

    assert hit["outcome"] == "HIT"
    assert corrupt["outcome"] == "UNEXPECTED_MISS"
    assert corrupt["reason_code"] == "CORRUPT_OBJECT"
    assert len(sink.documents) == 2
    assert "node-a" not in repr(sink.documents)
    assert "sha256:" not in repr(sink.documents)
    report = runtime.report()
    assert report is not None
    assert report["observations"]["unexpected_budget"]["consumed"] == 1


def test_expected_identity_change_is_a_necessary_miss() -> None:
    runtime = ParityRuntime(CacheParityConfig(), "tenant-a", "project-a")

    event = runtime.observe_action(
        node_id="node-a",
        action_key=None,
        hit=False,
        miss_reasons=(MissReason.PUBLIC_INTERFACE_CHANGED,),
    )

    assert event["outcome"] == "NECESSARY_MISS"
    assert event["reason_code"] == "PUBLIC_INTERFACE_CHANGED"
    report = runtime.report()
    assert report is not None
    assert report["observations"]["unexpected_budget"]["consumed"] == 0


def test_serving_flags_are_independent_and_safe_by_default() -> None:
    default = ParityRuntime(CacheParityConfig(), "tenant-a", "project-a").report()
    assert default is not None
    assert default["serving"] == {
        "provider_prompt": False,
        "environment_snapshot": False,
        "affinity": False,
        "multi_layer_coordinator": False,
    }
    assert default["external_provider_evidence"] == "NOT_RUN"
    assert default["certification"] == "NOT_CERTIFIED"
    assert set(default["wiring"]["layers"].values()) == {"NOT_WIRED"}

    serve = prompt_serving_config()
    report = ParityRuntime(serve, "tenant-a", "project-a").report()
    assert report is not None
    assert report["serving_requested"]["provider_prompt"] is True
    assert report["serving"]["provider_prompt"] is False
    assert report["wiring"]["layers"]["provider_prompt"] == "NOT_WIRED"
    assert report["serving_gate_receipt"]["status"] == "MISSING"
    assert report["rollback"]["latched"] is True
    assert report["serving"]["environment_snapshot"] is False


def test_serving_requires_valid_asymmetric_receipt_and_executable_wiring(
    clock: ManualClock,
) -> None:
    config = prompt_serving_config()
    receipt, signer = signed_gate(config, clock)
    verifier = Ed25519ProvenanceSigner.verifier(signer.public_keyset())

    unwired = ParityRuntime(
        config,
        "tenant-a",
        "project-a",
        sink=Sink(),
        clock=clock,
        serving_gate_receipt=receipt,
        serving_gate_verifier=verifier,
    ).report()
    assert unwired is not None
    assert unwired["serving_gate_receipt"]["status"] == "VERIFIED"
    assert unwired["serving"]["provider_prompt"] is False
    assert unwired["wiring"]["layers"]["provider_prompt"] == "NOT_WIRED"

    control = ServingControl()
    wired = ParityRuntime(
        config,
        "tenant-a",
        "project-a",
        sink=Sink(),
        clock=clock,
        serving_controls={"provider_prompt": control},
        serving_gate_receipt=receipt,
        serving_gate_verifier=verifier,
    ).report()
    assert wired is not None
    assert wired["serving_gate_receipt"]["status"] == "VERIFIED"
    assert wired["wiring"]["layers"]["provider_prompt"] == "WIRED"
    assert wired["serving"]["provider_prompt"] is True
    assert wired["external_provider_evidence"] == "NOT_RUN"
    assert wired["certification"] == "NOT_CERTIFIED"


def test_receipt_is_bound_to_project_and_asymmetric_trust(
    clock: ManualClock,
) -> None:
    config = prompt_serving_config()
    wrong_project_receipt, signer = signed_gate(config, clock, project_id="project-b")
    control = ServingControl()
    wrong_project = ParityRuntime(
        config,
        "tenant-a",
        "project-a",
        sink=Sink(),
        clock=clock,
        serving_controls={"provider_prompt": control},
        serving_gate_receipt=wrong_project_receipt,
        serving_gate_verifier=Ed25519ProvenanceSigner.verifier(signer.public_keyset()),
    ).report()
    assert wrong_project is not None
    assert wrong_project["serving_gate_receipt"]["reason_code"] == "SERVING_GATE_BINDING_INVALID"
    assert wrong_project["serving"]["provider_prompt"] is False

    symmetric = HmacProvenanceSigner(
        {"development-only": b"development-only-secret"}, "development-only"
    )
    claims = serving_gate_statement(
        config,
        "tenant-a",
        "project-a",
        ("provider_prompt",),
        issued_at=clock.now(),
        expires_at=clock.now() + 3_600,
    )
    symmetric_receipt = symmetric.sign_statement(SERVING_GATE_KIND, claims)
    rejected = ParityRuntime(
        config,
        "tenant-a",
        "project-a",
        sink=Sink(),
        clock=clock,
        serving_controls={"provider_prompt": ServingControl()},
        serving_gate_receipt=symmetric_receipt,
        serving_gate_verifier=symmetric,
    ).report()
    assert rejected is not None
    assert rejected["serving_gate_receipt"]["reason_code"] == "SERVING_GATE_SIGNATURE_INVALID"
    assert rejected["serving"]["provider_prompt"] is False


def test_disabled_plane_emits_no_report_but_does_not_change_outcome_semantics() -> None:
    runtime = ParityRuntime(replace(CacheParityConfig(), enabled=False), "tenant-a", "project-a")

    document = runtime.observe_action(
        node_id="node-a",
        action_key=None,
        hit=False,
        miss_reasons=(MissReason.NO_ENTRY,),
    )

    assert document["outcome"] == "NECESSARY_MISS"
    assert runtime.report() is None


def test_observation_store_outage_degrades_without_breaking_correct_execution() -> None:
    runtime = ParityRuntime(CacheParityConfig(), "tenant-a", "project-a", sink=BrokenSink())

    document = runtime.observe_action(
        node_id="node-a",
        action_key=None,
        hit=False,
        miss_reasons=(MissReason.NO_ENTRY,),
    )

    assert document["outcome"] == "NECESSARY_MISS"
    report = runtime.report()
    assert report is not None
    assert report["degraded"] is True
    assert report["observations"]["persistence_errors"] == 1
    assert report["observations"]["last_persistence_error"] == "RuntimeError"
    assert report["rollback"] == {
        "latched": True,
        "reason_code": "OBSERVATION_PERSISTENCE_FAILED",
        "delivery_errors": [],
    }
    assert "connection details" not in repr(report)


def test_persistence_failure_stops_serving_and_rollback_stays_latched(
    clock: ManualClock,
) -> None:
    config = prompt_serving_config()
    receipt, signer = signed_gate(config, clock)
    control = ServingControl()
    runtime = ParityRuntime(
        config,
        "tenant-a",
        "project-a",
        sink=BrokenSink(),
        clock=clock,
        serving_controls={"provider_prompt": control},
        serving_gate_receipt=receipt,
        serving_gate_verifier=Ed25519ProvenanceSigner.verifier(signer.public_keyset()),
    )
    before = runtime.report()
    assert before is not None and before["serving"]["provider_prompt"] is True

    runtime.observe_action(
        node_id="node-a",
        action_key=None,
        hit=False,
        miss_reasons=(MissReason.NO_ENTRY,),
    )
    runtime.sink = Sink()
    after = runtime.report()

    assert after is not None
    assert after["serving"]["provider_prompt"] is False
    assert after["rollback"]["latched"] is True
    assert after["rollback"]["reason_code"] == "OBSERVATION_PERSISTENCE_FAILED"
    assert control.enabled is False
    assert control.rollback_reasons == ["OBSERVATION_PERSISTENCE_FAILED"]
