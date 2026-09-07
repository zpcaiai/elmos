from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from elmos_build_cache.canonical import sha256_bytes
from elmos_build_cache.parity_jobs import (
    ParityHarnessJobRequest,
    ParityJobService,
)
from elmos_build_cache.security import Ed25519ProvenanceSigner
from elmos_build_cache.slo_service import CacheSloRuntimeRegistry
from test_parity_harness_service import (
    PROJECT,
    TENANT,
    marker_count,
    registration,
    service_for,
)


def test_replaying_a_local_harness_job_does_not_run_the_runner_again(
    tmp_path: Path, store
) -> None:
    marker = tmp_path / "runner-invocations.txt"
    signer = Ed25519ProvenanceSigner.generate("parity-job-key")
    principal = sha256_bytes(b"principal-1")
    installed = replace(registration(marker, signer), principal_id=principal)
    harness_service, _ = service_for(tmp_path, store, [installed])
    jobs = ParityJobService(
        harness_service=harness_service,
        runner_registry=harness_service.registry,
        slo_runtime_registry=CacheSloRuntimeRegistry(),
    )
    request = ParityHarnessJobRequest(TENANT, PROJECT, "job-1", "runner-1", "report-1")

    first = jobs.run_harness_once(
        request, authenticated_principal_digest=principal
    )
    first_invocations = marker_count(marker)
    replay = jobs.run_harness_once(
        request, authenticated_principal_digest=principal
    )

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.to_dict() == {**first.to_dict(), "idempotent_replay": True}
    assert marker_count(marker) == first_invocations
