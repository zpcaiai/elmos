from __future__ import annotations

import inspect
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any, cast

import pytest

from elmos_build_cache.canonical import digest_of, sha256_bytes
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.errors import (
    ContractViolation,
    CorruptObject,
    IdempotencyConflict,
    NotFound,
)
from elmos_build_cache.parity import (
    MANDATORY_SCENARIOS,
    EvidenceBinding,
    ParityThresholds,
    ScenarioStatus,
)
from elmos_build_cache.parity_harness import (
    EvidenceClass,
    MeasurementBundle,
    RawEvidence,
    ReplayMetadata,
    ScenarioCase,
    ScenarioCorpus,
    ScenarioExecution,
    ScenarioRequest,
)
from elmos_build_cache.parity_harness_service import (
    PARITY_HARNESS_REF_SOURCE_KIND,
    ParityHarnessRunRequest,
    TrustedParityHarnessService,
    TrustedParityRunnerRegistration,
    TrustedParityRunnerRegistry,
    TrustedScenarioExecutor,
    parity_harness_ref_kind,
)
from elmos_build_cache.parity_store import ParityMetadataRepository
from elmos_build_cache.security import Ed25519ProvenanceSigner, HmacProvenanceSigner

TENANT = "tenant-test"
PROJECT = "project-test"


def d(label: str) -> str:
    return sha256_bytes(label.encode())


def exact_corpus() -> ScenarioCorpus:
    return ScenarioCorpus.from_cases(
        tuple(
            ScenarioCase(
                scenario_id=scenario_id,
                input_digest=d(f"input:{scenario_id}"),
                timeout_seconds=2.0,
                parameters={"fixture_id": f"fixture:{scenario_id}"},
            )
            for scenario_id in MANDATORY_SCENARIOS
        )
    )


def exact_binding(
    corpus: ScenarioCorpus,
    *,
    tenant_id: str = TENANT,
    project_id: str = PROJECT,
) -> EvidenceBinding:
    return EvidenceBinding(
        source_digest=d("source"),
        configuration_digest=d("configuration"),
        provider_profiles_digest=d("providers"),
        corpus_digest=corpus.digest,
        platform_digest=d("platform"),
        generated_at="2026-08-24T00:00:00Z",
        executor_identity="trusted-executor",
        verifier_identity="independent-verifier",
        tenant_scope_digest=digest_of({"tenant_id": tenant_id, "project_id": project_id}),
        authorization_digest=d(f"authorization:{tenant_id}:{project_id}"),
    )


def measurements() -> MeasurementBundle:
    metrics = dict(asdict(ParityThresholds()))
    return MeasurementBundle(
        measurement_id="local-measurement-1",
        producer_identity="trusted-executor",
        evidence_class=EvidenceClass.SYNTHETIC_ENGINEERING,
        global_metrics=metrics,
        cohorts={"python-small": metrics},
        raw_evidence=(
            RawEvidence(
                "metrics-json",
                "application/json",
                b'{"evidence":"synthetic-local"}',
            ),
        ),
        replay=ReplayMetadata(
            replay_id="measurement-replay-1",
            runner="trusted-measurement-adapter",
            runner_version="1.0.0",
            request_digest=d("measurement-plan"),
        ),
    )


@dataclass(frozen=True)
class FileCountingExecutor:
    marker_path: Path
    identity: str = "trusted-executor"
    evidence_class: EvidenceClass = EvidenceClass.SYNTHETIC_ENGINEERING

    def __call__(self, request: ScenarioRequest) -> ScenarioExecution:
        with self.marker_path.open("a", encoding="utf-8") as marker:
            marker.write(f"{request.case.scenario_id}\n")
        return ScenarioExecution(
            ScenarioStatus.PASS,
            raw_evidence=(
                RawEvidence(
                    "scenario-observation",
                    "application/json",
                    (f'{{"evidence":"synthetic-local","scenario":"{request.case.scenario_id}"}}').encode(),
                ),
            ),
            replay=ReplayMetadata(
                replay_id=f"replay:{request.case.scenario_id}",
                runner="trusted-scenario-adapter",
                runner_version="1.0.0",
                request_digest=request.request_digest,
            ),
            detail={"fixture": "trusted-local"},
        )


def registration(
    marker_path: Path,
    signer: Ed25519ProvenanceSigner,
    *,
    runner_id: str = "runner-1",
    tenant_id: str = TENANT,
    project_id: str = PROJECT,
) -> TrustedParityRunnerRegistration:
    corpus = exact_corpus()
    executor = FileCountingExecutor(marker_path)
    trusted = TrustedScenarioExecutor(
        identity=executor.identity,
        evidence_class=executor.evidence_class,
        implementation_digest=d("trusted-executor-implementation-v1"),
        executor=executor,
    )
    return TrustedParityRunnerRegistration(
        tenant_id=tenant_id,
        project_id=project_id,
        principal_id="principal-1",
        runner_id=runner_id,
        corpus=corpus,
        binding=exact_binding(corpus, tenant_id=tenant_id, project_id=project_id),
        measurements=measurements(),
        executors={scenario_id: trusted for scenario_id in MANDATORY_SCENARIOS},
        signer=signer,
    )


def service_for(
    tmp_path: Path,
    store: SqliteMetadataStore,
    registrations: list[TrustedParityRunnerRegistration],
) -> tuple[TrustedParityHarnessService, ContentAddressableStore]:
    cas = ContentAddressableStore(tmp_path / "parity-cas")
    return (
        TrustedParityHarnessService(
            cas=cas,
            repository=ParityMetadataRepository(store),
            registry=TrustedParityRunnerRegistry(registrations),
        ),
        cas,
    )


def marker_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0


def mutation_counts(store: SqliteMetadataStore) -> tuple[int, int, int, int]:
    def table_count(table: str) -> int:
        row = store.query_one(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
        assert row is not None
        return int(row[0])

    return (
        table_count("idempotency_records"),
        table_count("artifacts"),
        table_count("artifact_refs"),
        table_count("cache_parity_reports_v12"),
    )


def test_trusted_service_registers_exact_graph_persists_and_replays_idempotently(
    tmp_path: Path,
    store: SqliteMetadataStore,
) -> None:
    marker = tmp_path / "executor-invocations.txt"
    signer = Ed25519ProvenanceSigner.generate("parity-service-key")
    first = registration(marker, signer)
    alternate = registration(marker, signer, runner_id="runner-2")
    service, cas = service_for(tmp_path, store, [first, alternate])
    request = ParityHarnessRunRequest(TENANT, PROJECT, "runner-1", "report-1")

    result = service.execute(request, authenticated_principal_id="principal-1")

    assert result.report["decision"] == "READY_FOR_EXTERNAL_GATE"
    assert result.external_evidence_state == "NOT_RUN"
    assert result.certification_state == "NOT_CERTIFIED"
    assert result.to_dict()["maximum_local_decision"] == "READY_FOR_EXTERNAL_GATE"
    assert result.to_dict()["idempotent_replay"] is False
    assert result.evidence_class is EvidenceClass.SYNTHETIC_ENGINEERING
    assert marker_count(marker) == len(MANDATORY_SCENARIOS)
    assert len(result.artifacts) == 44
    assert len(list(cas.objects_root.rglob("*.blob"))) == len(result.artifacts)

    persisted = ParityMetadataRepository(store).get_parity_report(
        TENANT,
        PROJECT,
        "report-1",
    )
    assert persisted == result.report
    expected_ref = (
        PARITY_HARNESS_REF_SOURCE_KIND,
        "report-1",
        parity_harness_ref_kind(PROJECT),
    )
    for artifact in result.artifacts:
        owned = store.get_artifact(TENANT, artifact.digest)
        assert owned is not None
        assert owned.size_bytes == artifact.size_bytes
        assert owned.media_type == artifact.media_type
        assert owned.metadata["project_id"] == PROJECT
        assert owned.metadata["external_evidence_state"] == "NOT_RUN"
        assert owned.metadata["certification_state"] == "NOT_CERTIFIED"
        assert expected_ref in store.artifact_referrers(TENANT, artifact.digest)
        assert store.artifact_tenants(artifact.digest) == [TENANT]
    assert set(
        store.artifact_targets(
            TENANT,
            PARITY_HARNESS_REF_SOURCE_KIND,
            "report-1",
        )
    ) == {artifact.digest for artifact in result.artifacts}

    restarted = TrustedParityHarnessService(
        cas=cas,
        repository=ParityMetadataRepository(store),
        registry=TrustedParityRunnerRegistry([first, alternate]),
    )
    replay = restarted.execute(request, authenticated_principal_id="principal-1")
    assert replay.replayed is True
    assert replay.receipt() == result.receipt()
    assert marker_count(marker) == len(MANDATORY_SCENARIOS)

    with pytest.raises(IdempotencyConflict):
        restarted.execute(
            ParityHarnessRunRequest(TENANT, PROJECT, "runner-2", "report-1"),
            authenticated_principal_id="principal-1",
        )
    assert marker_count(marker) == len(MANDATORY_SCENARIOS)

    drifted_measurements = measurements()
    cast(dict[str, float | int], drifted_measurements.global_metrics)["false_hits"] = 1
    drifted_registration = replace(first, measurements=drifted_measurements)
    drifted_service = TrustedParityHarnessService(
        cas=cas,
        repository=ParityMetadataRepository(store),
        registry=TrustedParityRunnerRegistry([drifted_registration]),
    )
    with pytest.raises(IdempotencyConflict):
        drifted_service.execute(request, authenticated_principal_id="principal-1")
    assert marker_count(marker) == len(MANDATORY_SCENARIOS)

    missing_ref = result.artifacts[0].digest
    with store.transaction():
        store.execute(
            "DELETE FROM artifact_refs WHERE tenant_id=? AND source_kind=?"
            " AND source_id=? AND target_digest=? AND ref_kind=?",
            (
                TENANT,
                PARITY_HARNESS_REF_SOURCE_KIND,
                "report-1",
                missing_ref,
                parity_harness_ref_kind(PROJECT),
            ),
        )
    with pytest.raises(CorruptObject):
        restarted.execute(request, authenticated_principal_id="principal-1")
    assert marker_count(marker) == len(MANDATORY_SCENARIOS)


def test_foreign_missing_and_unpersisted_scope_denials_have_zero_side_effects(
    tmp_path: Path,
    store: SqliteMetadataStore,
) -> None:
    marker = tmp_path / "denied-executor-invocations.txt"
    signer = Ed25519ProvenanceSigner.generate("parity-service-key")
    allowed = registration(marker, signer)
    missing_project = registration(
        marker,
        signer,
        runner_id="runner-missing-project",
        project_id="project-not-persisted",
    )
    service, cas = service_for(tmp_path, store, [allowed, missing_project])
    before = mutation_counts(store)
    denied = (
        (
            ParityHarnessRunRequest("tenant-foreign", PROJECT, "runner-1", "denied-1"),
            "principal-1",
        ),
        (
            ParityHarnessRunRequest(TENANT, "project-foreign", "runner-1", "denied-2"),
            "principal-1",
        ),
        (
            ParityHarnessRunRequest(TENANT, PROJECT, "runner-1", "denied-3"),
            "principal-foreign",
        ),
        (
            ParityHarnessRunRequest(TENANT, PROJECT, "runner-missing", "denied-4"),
            "principal-1",
        ),
        (
            ParityHarnessRunRequest(
                TENANT,
                "project-not-persisted",
                "runner-missing-project",
                "denied-5",
            ),
            "principal-1",
        ),
    )

    for request, principal_id in denied:
        with pytest.raises(NotFound, match="trusted parity runner is unavailable"):
            service.execute(request, authenticated_principal_id=principal_id)

    assert mutation_counts(store) == before
    assert not marker.exists()
    assert not list(cas.objects_root.rglob("*.blob"))


def test_request_surface_is_closed_and_registration_rejects_untrusted_inputs(
    tmp_path: Path,
) -> None:
    assert [item.name for item in fields(ParityHarnessRunRequest)] == [
        "tenant_id",
        "project_id",
        "runner_id",
        "report_id",
    ]
    assert tuple(inspect.signature(TrustedParityHarnessService.execute).parameters) == (
        "self",
        "request",
        "authenticated_principal_id",
    )
    with pytest.raises(TypeError):
        ParityHarnessRunRequest(  # type: ignore[call-arg]
            tenant_id=TENANT,
            project_id=PROJECT,
            runner_id="runner-1",
            report_id="report-1",
            command="echo unsafe",
        )
    with pytest.raises(TypeError):
        ParityHarnessRunRequest(  # type: ignore[call-arg]
            tenant_id=TENANT,
            project_id=PROJECT,
            runner_id="runner-1",
            report_id="report-1",
            metrics={"fabricated": 1},
        )

    marker = tmp_path / "untrusted-executor.txt"
    corpus = exact_corpus()
    executor = FileCountingExecutor(marker)
    common: dict[str, Any] = {
        "tenant_id": TENANT,
        "project_id": PROJECT,
        "principal_id": "principal-1",
        "runner_id": "runner-1",
        "corpus": corpus,
        "binding": exact_binding(corpus),
        "measurements": measurements(),
        "signer": Ed25519ProvenanceSigner.generate("parity-service-key"),
    }
    with pytest.raises(ContractViolation, match="only bound executor registrations"):
        TrustedParityRunnerRegistration(
            **common,
            executors=cast(
                dict[str, TrustedScenarioExecutor],
                {scenario_id: executor for scenario_id in MANDATORY_SCENARIOS},
            ),
        )
    trusted = TrustedScenarioExecutor(
        executor.identity,
        executor.evidence_class,
        d("trusted-executor-implementation-v1"),
        executor,
    )
    with pytest.raises(ContractViolation, match="exact mandatory executor set"):
        TrustedParityRunnerRegistration(
            **common,
            executors={MANDATORY_SCENARIOS[0]: trusted},
        )
    with pytest.raises(ContractViolation, match="Ed25519 signer"):
        TrustedParityRunnerRegistration(
            **{**common, "signer": HmacProvenanceSigner({"key": b"secret"}, "key")},
            executors={scenario_id: trusted for scenario_id in MANDATORY_SCENARIOS},
        )


def test_registration_scope_is_exact_and_registry_drift_fails_closed(tmp_path: Path) -> None:
    marker = tmp_path / "drift-executor.txt"
    signer = Ed25519ProvenanceSigner.generate("parity-service-key")
    corpus = exact_corpus()
    executor = FileCountingExecutor(marker)
    trusted = TrustedScenarioExecutor(
        executor.identity,
        executor.evidence_class,
        d("trusted-executor-implementation-v1"),
        executor,
    )
    with pytest.raises(ContractViolation, match="authenticated tenant scope"):
        TrustedParityRunnerRegistration(
            tenant_id=TENANT,
            project_id=PROJECT,
            principal_id="principal-1",
            runner_id="runner-1",
            corpus=corpus,
            binding=exact_binding(corpus, tenant_id=TENANT, project_id="wrong-project"),
            measurements=measurements(),
            executors={scenario_id: trusted for scenario_id in MANDATORY_SCENARIOS},
            signer=signer,
        )

    installed = registration(marker, signer)
    registry = TrustedParityRunnerRegistry([installed])
    cast(dict[str, float | int], installed.measurements.global_metrics)["false_hits"] = 1
    with pytest.raises(ContractViolation, match="registration drifted"):
        registry.resolve(
            ParityHarnessRunRequest(TENANT, PROJECT, "runner-1", "report-1"),
            authenticated_principal_id="principal-1",
        )
    assert not marker.exists()
