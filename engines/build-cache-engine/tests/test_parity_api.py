"""Production control-plane tests for all seven cache-parity operations."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from conftest import PROJECT, TENANT, digest
from elmos_build_cache.affinity import (
    AffinityAuthorizationContext,
    AffinityCandidate,
    AttestedAffinityCandidate,
    AttestedAffinityRegistry,
    StaticAffinityAuthorizationResolver,
    TargetHealth,
)
from elmos_build_cache.api import CacheControlPlane, Request
from elmos_build_cache.canonical import digest_of
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.config import (
    AffinityConfig,
    CacheParityConfig,
    EnvironmentSnapshotConfig,
)
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.environment_cache import EnvironmentKeyInputs, PlatformIdentity
from elmos_build_cache.environment_service import (
    EnvironmentLayerPayload,
    EnvironmentLayerType,
    EnvironmentSnapshotService,
)
from elmos_build_cache.parity import MANDATORY_SCENARIOS, ParityThresholds
from elmos_build_cache.parity_api import (
    decide_cache_affinity_payload,
    tenant_project_scope_digest,
)
from elmos_build_cache.parity_evidence import (
    EVIDENCE_ATTESTATION_KIND,
    EVIDENCE_REF_SOURCE_KIND,
    AsymmetricParityEvidenceTrustVerifier,
    CasParityEvidenceVerifier,
    parity_evidence_ref_kind,
)
from elmos_build_cache.parity_runtime import (
    SERVING_GATE_KIND,
    ParityRuntime,
    serving_gate_statement,
)
from elmos_build_cache.parity_store import ParityMetadataRepository
from elmos_build_cache.prompt_cache import PromptProvider
from elmos_build_cache.security import (
    Ed25519ProvenanceSigner,
    HmacProvenanceSigner,
    ProvenanceSigner,
    SignedStatement,
)


class ServingControl:
    def __init__(self) -> None:
        self.enabled = True
        self.rollback_reasons: list[str] = []

    def is_serving(self) -> bool:
        return self.enabled

    def latch_rollback(self, reason_code: str) -> None:
        self.rollback_reasons.append(reason_code)
        self.enabled = False


class AcceptingTestTrustVerifier:
    """Deliberately permissive injection used to prove the CAS verifier rejects HMAC."""

    def verify(
        self,
        signed: SignedStatement,
        *,
        expected_verifier_identity: str,
    ) -> None:
        del signed, expected_verifier_identity


@pytest.fixture
def parity_repository(store: SqliteMetadataStore) -> ParityMetadataRepository:
    return ParityMetadataRepository(store)


@pytest.fixture
def parity_plane(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    parity_repository: ParityMetadataRepository,
) -> CacheControlPlane:
    scope = tenant_project_scope_digest(TENANT, PROJECT)
    affinity_candidate = AffinityCandidate(
        target_id="worker-compatible",
        tenant_scope_digest=scope,
        authorization_scope_digest=digest("5"),
        authorized=True,
        trust_namespace="branch-main",
        provider=PromptProvider.OPENAI,
        model="gpt-5.6",
        effort_profile="high",
        tool_schema_digest=digest("6"),
        prefix_compatibility_digest=digest("7"),
        platform_digest=digest("8"),
        available_capacity=2,
        health=TargetHealth.HEALTHY,
        prompt_cache_value_ms=500,
        queue_delay_ms=10,
    )
    runner_signer = Ed25519ProvenanceSigner.generate("runner-attestation-verifier")
    runner_statement = {
        "schema_version": "1.2.0",
        "tenant_id": TENANT,
        "project_id": PROJECT,
        "candidate": affinity_candidate.attestation_document(),
        "attested_at": 0,
        "expires_at": 10**12,
    }
    signed_runner = runner_signer.sign_statement(
        "elmos.cache-affinity-runner-attestation/v1.2",
        runner_statement,
    )
    registry = AttestedAffinityRegistry(
        (
            AttestedAffinityCandidate(
                tenant_id=TENANT,
                project_id=PROJECT,
                candidate=affinity_candidate,
                attestation_digest=digest_of(signed_runner.to_dict()),
                verifier_identity=signed_runner.key_id,
                attested_at=0,
                expires_at=10**12,
                signed_attestation=signed_runner,
            ),
        ),
        trust_verifier=Ed25519ProvenanceSigner.verifier(
            runner_signer.public_keyset()
        ),
    )
    affinity_authorizer = StaticAffinityAuthorizationResolver(
        {
            (digest("9"), TENANT, PROJECT): AffinityAuthorizationContext(
                tenant_id=TENANT,
                project_id=PROJECT,
                principal_digest=digest("9"),
                authorization_scope_digest=digest("5"),
                allowed=True,
            )
        }
    )
    parity_config = replace(
        CacheParityConfig(),
        rollout_phase="internal",
        environment_snapshots=replace(EnvironmentSnapshotConfig(), enabled=True),
        affinity=replace(AffinityConfig(), enabled=True),
    )
    signer = Ed25519ProvenanceSigner.generate("http-serving-gate")
    statement = serving_gate_statement(
        parity_config,
        TENANT,
        PROJECT,
        ("environment_snapshot", "affinity"),
        issued_at=clock.now(),
        expires_at=clock.now() + 3_600,
    )
    receipt = signer.sign_statement(SERVING_GATE_KIND, statement)
    serving_authorizer = ParityRuntime(
        parity_config,
        TENANT,
        PROJECT,
        sink=parity_repository,
        clock=clock,
        serving_controls={
            "environment_snapshot": ServingControl(),
            "affinity": ServingControl(),
        },
        serving_gate_receipt=receipt,
        serving_gate_verifier=Ed25519ProvenanceSigner.verifier(signer.public_keyset()),
    )
    return CacheControlPlane(
        store,
        cas,
        TENANT,
        clock=clock,
        parity_repository=parity_repository,
        affinity_registry=registry,
        affinity_authorizer=affinity_authorizer,
        serving_authorizer=serving_authorizer,
    )


def prompt_payload(content: str = "Stable system policy") -> dict[str, object]:
    return {
        "project_id": PROJECT,
        "identity": {
            "provider": "openai",
            "provider_namespace_digest": digest("2"),
            "model": "gpt-5.6",
            "effort_profile": "high",
            "tool_schema_digest": digest("3"),
            "compatibility_digest": digest("4"),
        },
        "segments": [
            {
                "segment_id": "system-policy",
                "stability": "stable",
                "ordinal": 0,
                "content": content,
            },
            {
                "segment_id": "turn-request",
                "stability": "volatile",
                "ordinal": 0,
                "content": "Implement the cache",
            },
        ],
    }


def affinity_payload() -> dict[str, object]:
    request = {
        "authorization_scope_digest": digest("5"),
        "trust_namespace": "branch-main",
        "provider": "openai",
        "model": "gpt-5.6",
        "effort_profile": "high",
        "tool_schema_digest": digest("6"),
        "prefix_compatibility_digest": digest("7"),
        "platform_digest": digest("8"),
        "required_capacity": 1,
    }
    return {
        "project_id": PROJECT,
        "request_id": "affinity-request-1",
        "request": request,
    }


def binding(
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    authorization_digest: str | None = None,
) -> dict[str, str]:
    result = {
        "source_digest": digest("a"),
        "configuration_digest": digest("b"),
        "provider_profiles_digest": digest("c"),
        "corpus_digest": digest("d"),
        "platform_digest": digest("e"),
        "generated_at": "2026-08-20T00:00:00Z",
        "executor_identity": "executor-1",
        "verifier_identity": "verifier-2",
    }
    if tenant_id is not None and project_id is not None and authorization_digest is not None:
        result.update(
            {
                "tenant_scope_digest": tenant_project_scope_digest(tenant_id, project_id),
                "authorization_digest": authorization_digest,
            }
        )
    return result


def verified_scenarios(
    cas: ContentAddressableStore,
    metrics: dict[str, float | int],
    cohorts: dict[str, dict[str, float | int]],
) -> list[dict[str, object]]:
    bound = binding()
    measurement_raw = b'{"kind":"measured-parity-counters"}'
    measurement_raw_digest = cas.put_bytes(measurement_raw)
    measurement = {
        "schema_version": "1.2.0",
        "kind": "elmos.cache-parity-measurement-bundle/v1.2",
        "measurement_id": "api-measurement-1",
        "producer_identity": "executor-1",
        "evidence_class": "RUNTIME_ENGINEERING",
        "external_evidence_state": "NOT_RUN",
        "binding": bound,
        "global_metrics": metrics,
        "cohorts": cohorts,
        "raw_evidence": [
            {
                "role": "normalized-counters",
                "media_type": "application/json",
                "digest": measurement_raw_digest,
                "size": len(measurement_raw),
            }
        ],
        "replay": {
            "protocol": "elmos.cache-parity-replay/v1.2",
            "replay_id": "measurement-replay-1",
            "runner": "api-test-measurer",
            "runner_version": "1",
            "request_digest": digest("1"),
            "attempt": 1,
        },
    }
    measurement_digest = cas.put_document(measurement)

    scenarios: list[dict[str, object]] = []
    for scenario_id in MANDATORY_SCENARIOS:
        raw = json.dumps({"scenario_id": scenario_id, "measured": True}).encode()
        raw_digest = cas.put_bytes(raw)
        request = {
            "schema_version": "1.2.0",
            "kind": "elmos.cache-parity-scenario-request/v1.2",
            "run_id": "parity-ready-typed",
            "case": {
                "schema_version": "1.2.0",
                "scenario_id": scenario_id,
                "input_digest": digest("2"),
                "timeout_seconds": 30.0,
                "parameters": {},
            },
            "binding": bound,
            "measurement_bundle_digest": measurement_digest,
        }
        request_digest = digest_of(request)
        manifest = {
            "schema_version": "1.2.0",
            "kind": "elmos.cache-parity-scenario-execution/v1.2",
            "scenario_id": scenario_id,
            "request": request,
            "request_digest": request_digest,
            "executor_identity": "executor-1",
            "evidence_class": "RUNTIME_ENGINEERING",
            "external_evidence_state": "NOT_RUN",
            "status": "PASS",
            "reason": "measured test execution",
            "detail": {},
            "raw_evidence": [
                {
                    "role": "scenario-observation",
                    "media_type": "application/json",
                    "digest": raw_digest,
                    "size": len(raw),
                }
            ],
            "replay": {
                "protocol": "elmos.cache-parity-replay/v1.2",
                "replay_id": f"replay:{scenario_id}",
                "runner": "api-test-scenario-runner",
                "runner_version": "1",
                "request_digest": request_digest,
                "attempt": 1,
            },
        }
        manifest_digest = cas.put_document(manifest)
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "status": "PASS",
                "evidence_digests": [raw_digest, manifest_digest],
            }
        )
    return scenarios


def externally_verified_scenarios(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    signer: ProvenanceSigner,
    metrics: dict[str, float | int],
    cohorts: dict[str, dict[str, float | int]],
    *,
    tenant_id: str = TENANT,
    project_id: str = PROJECT,
    report_id: str = "parity-ready-external",
    register_artifacts: bool = True,
) -> tuple[dict[str, str], list[dict[str, object]]]:
    authorization = b'{"kind":"parity-evidence-authorization","decision":"ALLOW"}'
    authorization_digest = cas.put_bytes(authorization)
    bound = binding(
        tenant_id=tenant_id,
        project_id=project_id,
        authorization_digest=authorization_digest,
    )
    measurement_raw = b'{"kind":"externally-verified-parity-counters"}'
    measurement_raw_digest = cas.put_bytes(measurement_raw)
    measurement = {
        "schema_version": "1.2.0",
        "kind": "elmos.cache-parity-measurement-bundle/v1.2",
        "measurement_id": "api-external-measurement-1",
        "producer_identity": "executor-1",
        "evidence_class": "EXTERNAL_RUNTIME",
        "external_evidence_state": "EXTERNAL_VERIFIED",
        "binding": bound,
        "global_metrics": metrics,
        "cohorts": cohorts,
        "raw_evidence": [
            {
                "role": "normalized-counters",
                "media_type": "application/json",
                "digest": measurement_raw_digest,
                "size": len(measurement_raw),
            }
        ],
        "replay": {
            "protocol": "elmos.cache-parity-replay/v1.2",
            "replay_id": "external-measurement-replay-1",
            "runner": "independent-external-measurer",
            "runner_version": "1",
            "request_digest": digest("1"),
            "attempt": 1,
        },
    }
    measurement_digest = cas.put_document(measurement)
    all_digests = {
        authorization_digest,
        measurement_raw_digest,
        measurement_digest,
    }
    scenarios: list[dict[str, object]] = []
    for scenario_id in MANDATORY_SCENARIOS:
        raw = json.dumps(
            {"scenario_id": scenario_id, "externally_verified": True},
            sort_keys=True,
        ).encode()
        raw_digest = cas.put_bytes(raw)
        request = {
            "schema_version": "1.2.0",
            "kind": "elmos.cache-parity-scenario-request/v1.2",
            "run_id": report_id,
            "case": {
                "schema_version": "1.2.0",
                "scenario_id": scenario_id,
                "input_digest": digest("2"),
                "timeout_seconds": 30.0,
                "parameters": {},
            },
            "binding": bound,
            "measurement_bundle_digest": measurement_digest,
        }
        request_digest = digest_of(request)
        manifest = {
            "schema_version": "1.2.0",
            "kind": "elmos.cache-parity-scenario-execution/v1.2",
            "scenario_id": scenario_id,
            "request": request,
            "request_digest": request_digest,
            "executor_identity": "executor-1",
            "evidence_class": "EXTERNAL_RUNTIME",
            "external_evidence_state": "EXTERNAL_VERIFIED",
            "status": "PASS",
            "reason": "independently measured external execution",
            "detail": {},
            "raw_evidence": [
                {
                    "role": "scenario-observation",
                    "media_type": "application/json",
                    "digest": raw_digest,
                    "size": len(raw),
                }
            ],
            "replay": {
                "protocol": "elmos.cache-parity-replay/v1.2",
                "replay_id": f"external-replay:{scenario_id}",
                "runner": "independent-external-scenario-runner",
                "runner_version": "1",
                "request_digest": request_digest,
                "attempt": 1,
            },
        }
        manifest_digest = cas.put_document(manifest)
        authorized_digests = {
            authorization_digest,
            measurement_raw_digest,
            measurement_digest,
            raw_digest,
            manifest_digest,
        }
        statement = {
            "schema_version": "1.2.0",
            "report_id": report_id,
            "scenario_id": scenario_id,
            "tenant_scope_digest": bound["tenant_scope_digest"],
            "authorization_digest": authorization_digest,
            "evidence_binding_digest": digest_of(bound),
            "request_digest": request_digest,
            "execution_manifest_digest": manifest_digest,
            "measurement_bundle_digest": measurement_digest,
            "evidence_digests": sorted(authorized_digests),
            "executor_identity": "executor-1",
            "verifier_identity": "verifier-2",
            "issued_at": clock.now() - 1,
            "expires_at": clock.now() + 3_600,
        }
        attestation_digest = cas.put_document(
            signer.sign_statement(EVIDENCE_ATTESTATION_KIND, statement).to_dict()
        )
        scenario_digests = authorized_digests | {attestation_digest}
        all_digests.update(scenario_digests)
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "status": "PASS",
                "evidence_digests": sorted(scenario_digests),
            }
        )
    if register_artifacts:
        for evidence_digest in sorted(all_digests):
            evidence_bytes = cas.get_bytes(evidence_digest, verify=True)
            store.register_artifact(
                tenant_id,
                evidence_digest,
                len(evidence_bytes),
                "application/octet-stream",
                "parity-evidence",
            )
            store.add_artifact_ref(
                tenant_id,
                EVIDENCE_REF_SOURCE_KIND,
                authorization_digest,
                evidence_digest,
                parity_evidence_ref_kind(project_id),
            )
    return bound, scenarios


def install_evidence_trust(
    plane: CacheControlPlane,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    signer: Ed25519ProvenanceSigner,
) -> None:
    plane.parity_api.evidence_verifier = CasParityEvidenceVerifier(
        cas,
        ownership=store,
        trust_verifier=AsymmetricParityEvidenceTrustVerifier(
            Ed25519ProvenanceSigner.verifier(signer.public_keyset()),
            {signer.active_key_id: "verifier-2"},
        ),
        clock=clock,
    )


def test_compile_prompt_prefix_persists_only_content_free_manifest(
    parity_plane: CacheControlPlane,
    parity_repository: ParityMetadataRepository,
    store: SqliteMetadataStore,
) -> None:
    secret_source = "Stable system policy customer-source-marker"
    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/prompt-prefixes/compile",
            prompt_payload(secret_source),
            {"Idempotency-Key": "compile-prefix-1"},
        )
    )

    assert response.status == 200
    body = response.json()
    serialized = json.dumps(body, sort_keys=True)
    assert secret_source not in serialized
    manifest = body["manifest"]
    stored = parity_repository.get_prompt_manifest(TENANT, PROJECT, manifest["manifest_id"])
    assert stored == manifest
    assert secret_source not in json.dumps(stored, sort_keys=True)
    idempotency = store.query_one(
        "SELECT response FROM idempotency_records WHERE tenant_id=? AND idempotency_key=?",
        (TENANT, "compile-prefix-1"),
    )
    assert idempotency is not None and secret_source not in str(idempotency[0])


def test_compile_rejects_unapproved_volatile_stable_prefix(
    parity_plane: CacheControlPlane,
) -> None:
    payload = prompt_payload("generated at 2026-08-20T12:34:56Z")
    rejected = parity_plane.handle(
        Request(
            "POST",
            "/cache/prompt-prefixes/compile",
            payload,
            {"Idempotency-Key": "volatile-prefix-1"},
        )
    )
    assert rejected.status == 422
    assert rejected.json()["code"] == "CONTRACT_VIOLATION"

    payload["volatility_approvals"] = [
        {"segment_id": "system-policy", "code": "TIMESTAMP"}
    ]
    approved = parity_plane.handle(
        Request(
            "POST",
            "/cache/prompt-prefixes/compile",
            payload,
            {"Idempotency-Key": "volatile-prefix-2"},
        )
    )
    assert approved.status == 200
    assert approved.json()["volatility_approvals"] == [
        {"segment_id": "system-policy", "code": "TIMESTAMP"}
    ]


def test_prompt_compilation_rejects_unbounded_segment_count(
    parity_plane: CacheControlPlane,
) -> None:
    payload = prompt_payload()
    payload["segments"] = [
        {
            "segment_id": f"stable-{index}",
            "stability": "stable",
            "ordinal": index,
            "content": "x",
        }
        for index in range(257)
    ]
    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/prompt-prefixes/compile",
            payload,
            {"Idempotency-Key": "too-many-segments"},
        )
    )
    assert response.status == 422


def test_append_context_event_is_scoped_hash_linked_and_content_free(
    parity_plane: CacheControlPlane,
) -> None:
    payload = {
        "project_id": PROJECT,
        "branch_lineage": "refs/heads/main@abc123",
        "repository_snapshot_digest": digest("1"),
        "event_type": "FILE_READ",
        "payload": {"logical_path": "src/main.py", "content_digest": digest("2")},
        "expected_sequence": 0,
    }
    created = parity_plane.handle(
        Request(
            "POST",
            "/cache/context-ledgers/context-stream-api/events",
            payload,
            {"Idempotency-Key": "context-event-1"},
        )
    )
    assert created.status == 201
    assert created.json()["sequence"] == 1
    assert created.json()["tenant_scope"] == tenant_project_scope_digest(TENANT, PROJECT)
    assert "payload" not in created.json()

    raw = {**payload, "payload": {"source_code": "print('secret')"}}
    rejected = parity_plane.handle(
        Request(
            "POST",
            "/cache/context-ledgers/context-stream-api/events",
            raw,
            {"Idempotency-Key": "context-event-raw"},
        )
    )
    assert rejected.status == 422
    assert rejected.json()["code"] in {"CONTRACT_VIOLATION", "SECRET_DETECTED"}


def test_environment_lookup_verifies_manifest_layers_and_only_returns_a_decision(
    parity_plane: CacheControlPlane,
    parity_repository: ParityMetadataRepository,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    service = EnvironmentSnapshotService(store, cas, parity_repository, clock)
    inputs = EnvironmentKeyInputs(
        base_image_digest=digest("1"),
        setup_script_digests=(),
        maintenance_script_digests=(),
        lockfile_digests=(),
        package_manager_digest=digest("2"),
        toolchain_digests=(("python", digest("3")),),
        platform=PlatformIdentity("linux", "arm64", "glibc", digest("4")),
        approved_environment_digests=(),
        secret_reference_versions=(),
    )
    sealed = service.seal(
        TENANT,
        PROJECT,
        "branch-main",
        inputs,
        (EnvironmentLayerPayload(EnvironmentLayerType.BASE, b"verified-base-layer"),),
    )
    snapshot_key = sealed.key.digest
    layer_digest = sealed.layers[0].digest
    query = {
        "projectId": PROJECT,
        "trustNamespace": "branch-main",
        "transferMs": "10",
        "decompressionMs": "5",
        "verificationMs": "2",
        "rebuildMs": "100",
    }
    response = parity_plane.handle(
        Request("GET", f"/cache/environments/{snapshot_key}", query=query)
    )
    assert response.status == 200
    assert response.json()["verified"] is True
    assert response.json()["verified_layer_digests"] == [layer_digest]
    assert response.json()["restore_decision"]["action"] == "RESTORE"
    assert response.json()["execution_performed"] is False

    caller_proof = parity_plane.handle(
        Request(
            "GET",
            f"/cache/environments/{snapshot_key}",
            query={
                **query,
                "observedManifestDigest": sealed.manifest_digest,
                "verifiedLayerDigests": layer_digest,
            },
        )
    )
    assert caller_proof.status == 422
    assert caller_proof.json()["code"] == "CONTRACT_VIOLATION"

    layer_path = cas.path_for(layer_digest)
    os.chmod(layer_path, 0o644)
    layer_path.write_bytes(b"tampered-base-layer")
    corrupt = parity_plane.handle(
        Request("GET", f"/cache/environments/{snapshot_key}", query=query)
    )
    assert corrupt.status == 422
    assert corrupt.json()["code"] == "CORRUPT_OBJECT"
    state = parity_repository.get_environment_snapshot_state(TENANT, PROJECT, snapshot_key)
    assert state is not None
    assert state["effective_status"] == "QUARANTINED"
    assert state["latest_status_event"]["new_status"] == "QUARANTINED"
    parity_status = parity_plane.handle(Request("GET", "/status")).json()["cache_parity"]
    assert parity_status["rollback"]["latched"] is True
    assert parity_status["rollback"]["reason_code"] == "SERVING_PATH_INTEGRITY_FAILED"
    assert not any(parity_status["serving"].values())


def test_affinity_uses_only_server_attested_scoped_candidates(
    parity_plane: CacheControlPlane,
) -> None:
    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/affinity/decide",
            affinity_payload(),
            {"Idempotency-Key": "affinity-1"},
            authenticated_principal_digest=digest("9"),
        )
    )
    assert response.status == 200
    body = response.json()
    assert body["selected_target"] == "worker-compatible"
    assert [item["target_id"] for item in body["candidates"]] == [
        "worker-compatible"
    ]


def test_http_status_reports_only_verified_and_wired_serving(
    parity_plane: CacheControlPlane,
) -> None:
    status = parity_plane.handle(Request("GET", "/status")).json()["cache_parity"]

    assert status["serving_gate_receipt"]["status"] == "VERIFIED"
    assert status["serving"]["environment_snapshot"] is True
    assert status["serving"]["affinity"] is True
    assert status["serving"]["provider_prompt"] is False
    assert status["external_provider_evidence"] == "NOT_RUN"
    assert status["certification"] == "NOT_CERTIFIED"


def test_http_serving_pep_rejects_project_outside_signed_receipt(
    parity_plane: CacheControlPlane,
) -> None:
    response = parity_plane.handle(
        Request(
            "GET",
            f"/cache/environments/{digest('a')}",
            query={"projectId": "project-outside-receipt"},
        )
    )

    assert response.status == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
    assert response.json()["details"]["state"] == "SERVING_NOT_AUTHORIZED"


def test_affinity_rejects_caller_supplied_authorization_and_candidates(
    parity_plane: CacheControlPlane,
) -> None:
    payload = affinity_payload()
    payload["candidates"] = [
        {
            "target_id": "attacker-worker",
            "authorized": True,
            "tenant_scope_digest": tenant_project_scope_digest(TENANT, PROJECT),
        }
    ]
    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/affinity/decide",
            payload,
            {"Idempotency-Key": "affinity-caller-injection"},
            authenticated_principal_digest=digest("9"),
        )
    )
    assert response.status == 422


def test_affinity_cannot_select_another_valid_authorization_scope(
    parity_plane: CacheControlPlane,
) -> None:
    payload = affinity_payload()
    request = payload["request"]
    assert isinstance(request, dict)
    request["authorization_scope_digest"] = digest("a")

    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/affinity/decide",
            payload,
            {"Idempotency-Key": "affinity-self-selected-scope"},
            authenticated_principal_digest=digest("9"),
        )
    )

    assert response.status == 422
    assert response.json()["code"] == "CONTRACT_VIOLATION"


def test_affinity_uses_server_scope_when_the_claim_is_omitted(
    parity_plane: CacheControlPlane,
) -> None:
    payload = affinity_payload()
    request = payload["request"]
    assert isinstance(request, dict)
    del request["authorization_scope_digest"]

    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/affinity/decide",
            payload,
            {"Idempotency-Key": "affinity-server-scope"},
            authenticated_principal_digest=digest("9"),
        )
    )

    assert response.status == 200
    assert response.json()["selected_target"] == "worker-compatible"


def test_affinity_rejects_another_principal_in_the_same_project(
    parity_plane: CacheControlPlane,
) -> None:
    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/affinity/decide",
            affinity_payload(),
            {"Idempotency-Key": "affinity-other-principal"},
            authenticated_principal_digest=digest("a"),
        )
    )

    assert response.status == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_affinity_balanced_score_does_not_claim_a_prefix_hit_reason() -> None:
    scope = tenant_project_scope_digest(TENANT, PROJECT)
    neutral = AffinityCandidate(
        target_id="worker-neutral",
        tenant_scope_digest=scope,
        authorization_scope_digest=digest("5"),
        authorized=True,
        trust_namespace="branch-main",
        provider=PromptProvider.OPENAI,
        model="gpt-5.6",
        effort_profile="high",
        tool_schema_digest=digest("6"),
        prefix_compatibility_digest=digest("7"),
        platform_digest=digest("8"),
        available_capacity=2,
        health=TargetHealth.HEALTHY,
    )

    evaluation = decide_cache_affinity_payload(
        TENANT,
        affinity_payload(),
        trusted_candidates=(neutral,),
        trusted_authorization_scope_digest=digest("5"),
    )

    assert evaluation.decision.reason.value == "BALANCED_SCORE"
    assert evaluation.document["reason_codes"] == []


def test_explain_cache_outcome_returns_closed_diagnostics_not_raw_telemetry(
    parity_plane: CacheControlPlane,
    parity_repository: ParityMetadataRepository,
) -> None:
    outcome = {
        "schema_version": "1.2.0",
        "event_id": "outcome-event-1",
        "request_id": "cache-request-1",
        "layer": "ACTION",
        "outcome": "HIT",
        "reason_code": "EXACT_RESULT_REUSED",
        "eligible": True,
        "occurred_at": "2026-08-20T00:00:00Z",
    }
    parity_repository.put_cache_outcome(
        TENANT, PROJECT, "cache-request-1", "outcome-event-1", outcome
    )
    response = parity_plane.handle(
        Request("GET", "/cache/explain/cache-request-1", query={"projectId": PROJECT})
    )
    assert response.status == 200
    body = response.json()
    assert body["outcomes"][0]["reason"] == "EXACT_RESULT_REUSED"
    assert body["remediation_codes"] == ["NONE"]
    assert body["causal_invalidation_graph"]["claim"] == "OBSERVED_ONLY"


def test_parity_run_persists_honest_not_run_and_report_is_project_scoped(
    parity_plane: CacheControlPlane,
) -> None:
    payload = {
        "project_id": PROJECT,
        "report_id": "parity-not-run-1",
        "metrics": {},
        "cohorts": {},
        "scenarios": [],
        "binding": binding(),
    }
    started = parity_plane.handle(
        Request(
            "POST",
            "/cache/parity/runs",
            payload,
            {"Idempotency-Key": "parity-not-run-key"},
        )
    )
    assert started.status == 202
    assert started.json()["decision"] == "NOT_RUN"
    assert started.json()["provider_execution_performed"] is False
    assert started.json()["certified"] is False
    assert started.json()["report"]["missing"]

    fetched = parity_plane.handle(
        Request(
            "GET",
            "/cache/parity/reports/parity-not-run-1",
            query={"projectId": PROJECT},
        )
    )
    assert fetched.status == 200
    assert fetched.json()["decision"] == "NOT_RUN"

    other_project = parity_plane.handle(
        Request(
            "GET",
            "/cache/parity/reports/parity-not-run-1",
            query={"projectId": "project-other"},
        )
    )
    assert other_project.status == 404


def test_arbitrary_reused_blob_cannot_prepare_the_external_gate(
    parity_plane: CacheControlPlane,
    cas: ContentAddressableStore,
) -> None:
    evidence = cas.put_bytes(b"independent measured cache evidence")
    metrics = asdict(ParityThresholds())
    payload = {
        "project_id": PROJECT,
        "report_id": "parity-ready-1",
        "metrics": metrics,
        "cohorts": {"interactive": metrics},
        "scenarios": [
            {
                "scenario_id": scenario_id,
                "status": "PASS",
                "evidence_digests": [evidence],
            }
            for scenario_id in MANDATORY_SCENARIOS
        ],
        "binding": binding(),
    }
    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/parity/runs",
            payload,
            {"Idempotency-Key": "parity-ready-key"},
        )
    )
    assert response.status == 202
    assert response.json()["decision"] == "NOT_RUN"
    assert response.json()["report"]["mandatory_pass"] is False
    assert response.json()["certified"] is False


def test_local_engineering_evidence_cannot_prepare_the_external_gate(
    parity_plane: CacheControlPlane,
    cas: ContentAddressableStore,
) -> None:
    metrics = asdict(ParityThresholds())
    cohorts = {"interactive": metrics}
    payload = {
        "project_id": PROJECT,
        "report_id": "parity-ready-typed",
        "metrics": metrics,
        "cohorts": cohorts,
        "scenarios": verified_scenarios(cas, metrics, cohorts),
        "binding": binding(),
    }
    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/parity/runs",
            payload,
            {"Idempotency-Key": "parity-ready-typed-key"},
        )
    )
    assert response.status == 202
    assert response.json()["decision"] == "NOT_RUN"
    assert response.json()["report"]["mandatory_pass"] is False
    assert response.json()["certified"] is False


def test_only_scoped_owned_authorized_asymmetrically_verified_evidence_is_ready(
    parity_plane: CacheControlPlane,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    signer = Ed25519ProvenanceSigner.generate("parity-evidence-key")
    metrics = asdict(ParityThresholds())
    cohorts = {"interactive": metrics}
    bound, scenarios = externally_verified_scenarios(
        store,
        cas,
        clock,
        signer,
        metrics,
        cohorts,
    )
    install_evidence_trust(parity_plane, store, cas, clock, signer)
    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/parity/runs",
            {
                "project_id": PROJECT,
                "report_id": "parity-ready-external",
                "metrics": metrics,
                "cohorts": cohorts,
                "scenarios": scenarios,
                "binding": bound,
            },
            {"Idempotency-Key": "parity-ready-external-key"},
        )
    )
    assert response.status == 202
    assert response.json()["decision"] == "READY_FOR_EXTERNAL_GATE"
    assert response.json()["report"]["mandatory_pass"] is True
    assert response.json()["certified"] is False


def test_scoped_signed_evidence_without_injected_trust_is_not_run(
    parity_plane: CacheControlPlane,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    signer = Ed25519ProvenanceSigner.generate("parity-no-trust-key")
    metrics = asdict(ParityThresholds())
    cohorts = {"interactive": metrics}
    bound, scenarios = externally_verified_scenarios(
        store,
        cas,
        clock,
        signer,
        metrics,
        cohorts,
        report_id="parity-no-trust",
    )
    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/parity/runs",
            {
                "project_id": PROJECT,
                "report_id": "parity-no-trust",
                "metrics": metrics,
                "cohorts": cohorts,
                "scenarios": scenarios,
                "binding": bound,
            },
            {"Idempotency-Key": "parity-no-trust-key"},
        )
    )
    assert response.status == 202
    assert response.json()["decision"] == "NOT_RUN"
    assert all(
        scenario["detail"]["evidence_failure_code"]
        == "EVIDENCE_TRUST_VERIFIER_UNAVAILABLE"
        for scenario in response.json()["report"]["scenarios"]
    )


def test_symmetric_evidence_signature_is_rejected_even_by_permissive_injection(
    parity_plane: CacheControlPlane,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    signer = HmacProvenanceSigner({"dev-hmac": b"shared-secret"}, "dev-hmac")
    metrics = asdict(ParityThresholds())
    cohorts = {"interactive": metrics}
    bound, scenarios = externally_verified_scenarios(
        store,
        cas,
        clock,
        signer,
        metrics,
        cohorts,
        report_id="parity-hmac-evidence",
    )
    parity_plane.parity_api.evidence_verifier = CasParityEvidenceVerifier(
        cas,
        ownership=store,
        trust_verifier=AcceptingTestTrustVerifier(),
        clock=clock,
    )
    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/parity/runs",
            {
                "project_id": PROJECT,
                "report_id": "parity-hmac-evidence",
                "metrics": metrics,
                "cohorts": cohorts,
                "scenarios": scenarios,
                "binding": bound,
            },
            {"Idempotency-Key": "parity-hmac-evidence-key"},
        )
    )
    assert response.status == 202
    assert response.json()["decision"] == "NOT_RUN"
    assert all(
        scenario["detail"]["evidence_failure_code"]
        == "EVIDENCE_ATTESTATION_NOT_ASYMMETRIC"
        for scenario in response.json()["report"]["scenarios"]
    )


def test_parity_metrics_must_match_the_verified_measurement_bundle(
    parity_plane: CacheControlPlane,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    signer = Ed25519ProvenanceSigner.generate("parity-metric-evidence-key")
    measured = asdict(ParityThresholds())
    cohorts = {"interactive": measured}
    bound, scenarios = externally_verified_scenarios(
        store,
        cas,
        clock,
        signer,
        measured,
        cohorts,
        report_id="parity-metric-drift",
    )
    install_evidence_trust(parity_plane, store, cas, clock, signer)
    claimed = {**measured, "stable_turn_cached_token_reuse": 1.0}
    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/parity/runs",
            {
                "project_id": PROJECT,
                "report_id": "parity-metric-drift",
                "metrics": claimed,
                "cohorts": cohorts,
                "scenarios": scenarios,
                "binding": bound,
            },
            {"Idempotency-Key": "parity-metric-drift-key"},
        )
    )
    assert response.status == 202
    assert response.json()["decision"] == "NOT_RUN"


def test_scoped_evidence_cannot_replay_into_another_project(
    parity_plane: CacheControlPlane,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    signer = Ed25519ProvenanceSigner.generate("parity-project-replay-key")
    metrics = asdict(ParityThresholds())
    cohorts = {"interactive": metrics}
    bound, scenarios = externally_verified_scenarios(
        store,
        cas,
        clock,
        signer,
        metrics,
        cohorts,
        report_id="parity-project-replay",
    )
    install_evidence_trust(parity_plane, store, cas, clock, signer)
    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/parity/runs",
            {
                "project_id": "project-other",
                "report_id": "parity-project-replay",
                "metrics": metrics,
                "cohorts": cohorts,
                "scenarios": scenarios,
                "binding": bound,
            },
            {"Idempotency-Key": "parity-project-replay-key"},
        )
    )
    assert response.status == 422
    assert response.json()["code"] == "CONTRACT_VIOLATION"
    assert "authenticated scope" in response.json()["message"]


def test_same_global_cas_evidence_cannot_replay_into_another_tenant(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    parity_repository: ParityMetadataRepository,
) -> None:
    signer = Ed25519ProvenanceSigner.generate("parity-tenant-replay-key")
    trust = AsymmetricParityEvidenceTrustVerifier(
        Ed25519ProvenanceSigner.verifier(signer.public_keyset()),
        {signer.active_key_id: "verifier-2"},
    )
    metrics = asdict(ParityThresholds())
    cohorts = {"interactive": metrics}
    bound, scenarios = externally_verified_scenarios(
        store,
        cas,
        clock,
        signer,
        metrics,
        cohorts,
        report_id="parity-tenant-replay",
    )
    other_plane = CacheControlPlane(
        store,
        cas,
        "tenant-other",
        clock=clock,
        parity_repository=parity_repository,
        parity_evidence_trust_verifier=trust,
    )
    response = other_plane.handle(
        Request(
            "POST",
            "/cache/parity/runs",
            {
                "project_id": "other-tenant-project",
                "report_id": "parity-tenant-replay",
                "metrics": metrics,
                "cohorts": cohorts,
                "scenarios": scenarios,
                "binding": bound,
            },
            {"Idempotency-Key": "parity-tenant-replay-key"},
        )
    )
    assert response.status == 422
    assert response.json()["code"] == "CONTRACT_VIOLATION"
    assert "authenticated scope" in response.json()["message"]


def test_signed_evidence_without_tenant_artifact_registration_is_not_run(
    parity_plane: CacheControlPlane,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    signer = Ed25519ProvenanceSigner.generate("parity-unowned-key")
    metrics = asdict(ParityThresholds())
    cohorts = {"interactive": metrics}
    bound, scenarios = externally_verified_scenarios(
        store,
        cas,
        clock,
        signer,
        metrics,
        cohorts,
        report_id="parity-unowned",
        register_artifacts=False,
    )
    install_evidence_trust(parity_plane, store, cas, clock, signer)
    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/parity/runs",
            {
                "project_id": PROJECT,
                "report_id": "parity-unowned",
                "metrics": metrics,
                "cohorts": cohorts,
                "scenarios": scenarios,
                "binding": bound,
            },
            {"Idempotency-Key": "parity-unowned-key"},
        )
    )
    assert response.status == 202
    assert response.json()["decision"] == "NOT_RUN"
    assert all(
        scenario["detail"]["evidence_failure_code"]
        == "EVIDENCE_OBJECT_UNOWNED_OR_INVALID"
        for scenario in response.json()["report"]["scenarios"]
    )


@pytest.mark.parametrize(
    "thresholds",
    [
        {"stable_turn_cached_token_reuse": 0.0},
        {"unexpected_full_prefix_miss": 1.0},
        {"false_hits": 1},
    ],
)
def test_caller_cannot_weaken_parity_thresholds(
    parity_plane: CacheControlPlane,
    thresholds: dict[str, float | int],
) -> None:
    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/parity/runs",
            {
                "project_id": PROJECT,
                "report_id": "parity-weakened-threshold",
                "metrics": {},
                "cohorts": {},
                "scenarios": [],
                "binding": binding(),
                "thresholds": thresholds,
            },
            {"Idempotency-Key": "parity-weakened-threshold-key"},
        )
    )
    assert response.status == 422


def test_pass_claim_with_missing_evidence_is_downgraded_to_not_run(
    parity_plane: CacheControlPlane,
) -> None:
    metrics = asdict(ParityThresholds())
    payload = {
        "project_id": PROJECT,
        "report_id": "parity-missing-evidence",
        "metrics": metrics,
        "cohorts": {"interactive": metrics},
        "scenarios": [
            {
                "scenario_id": scenario_id,
                "status": "PASS",
                "evidence_digests": [digest("f")],
            }
            for scenario_id in MANDATORY_SCENARIOS
        ],
        "binding": binding(),
    }
    response = parity_plane.handle(
        Request(
            "POST",
            "/cache/parity/runs",
            payload,
            {"Idempotency-Key": "parity-missing-evidence-key"},
        )
    )
    assert response.status == 202
    assert response.json()["decision"] == "NOT_RUN"
    assert response.json()["report"]["mandatory_pass"] is False


def test_all_mutating_parity_operations_require_global_idempotency(
    parity_plane: CacheControlPlane,
) -> None:
    for path, payload in (
        ("/cache/prompt-prefixes/compile", prompt_payload()),
        ("/cache/affinity/decide", affinity_payload()),
        (
            "/cache/parity/runs",
            {
                "project_id": PROJECT,
                "report_id": "missing-key",
                "metrics": {},
                "cohorts": {},
                "scenarios": [],
                "binding": binding(),
            },
        ),
    ):
        response = parity_plane.handle(Request("POST", path, payload))
        assert response.status == 400
        assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_openapi_supplement_declares_all_operations_and_matches_packaged_copy() -> None:
    from elmos_build_cache.schemas import SCHEMA_DIR

    source = (
        Path(__file__).resolve().parents[1]
        / "openapi"
        / "cache-parity-control-plane.openapi.yaml"
    )
    packaged = SCHEMA_DIR.parent / "openapi" / "cache-parity-control-plane.openapi.yaml"
    assert source.read_bytes() == packaged.read_bytes()
    text = source.read_text(encoding="utf-8")
    for operation in (
        "compilePromptPrefix",
        "appendContextLedgerEvent",
        "lookupEnvironmentSnapshot",
        "decideCacheAffinity",
        "explainCacheOutcome",
        "startCacheParityRun",
        "getCacheParityReport",
    ):
        assert f"operationId: {operation}" in text
    assert "ContextAppendRequest" in text
    assert text.count("IdempotencyKey") >= 5
