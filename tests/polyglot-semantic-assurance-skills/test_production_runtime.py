"""Security, durability, and fail-closed tests for the 300-Skill runtime."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import time

import pytest

from elmos_polyglot_compiler.catalog import load_catalog
from elmos_polyglot_compiler.contracts import (
    ContractError,
    ExecutionAuthority,
    IdempotencyConflict,
    RuntimeRequest,
    digest_json,
)
from elmos_polyglot_compiler.evidence import (
    ArtifactStoreError,
    ContentAddressedArtifactStore,
)
from elmos_polyglot_compiler.runtime import (
    SkillRuntime,
    _validate_operation,
    build_registry,
    validate_registry,
)
from elmos_polyglot_compiler.handlers import _scan_repository
from elmos_polyglot_compiler.store import SqliteExecutionStore, StateStoreError


REVISION = "sha256:" + "a" * 64


def _request(*, inputs: dict | None = None, key: str = "attempt-1", tenant: str = "t1"):
    return {
        "schema_version": "1.0",
        "request_id": f"request-{tenant}-{key}",
        "tenant_id": tenant,
        "project_id": "project-1",
        "actor_id": "actor-1",
        "revision_digest": REVISION,
        "environment_authority_id": "environment-1",
        "idempotency_key": key,
        "inputs": inputs or {},
    }


def _authority(
    skill: str,
    *,
    tenant: str = "t1",
    verified: frozenset[str] = frozenset(),
    repository_root: Path | None = None,
) -> ExecutionAuthority:
    return ExecutionAuthority(
        tenant_id=tenant,
        project_id="project-1",
        actor_id="actor-1",
        revision_digest=REVISION,
        environment_authority_id="environment-1",
        allowed_skills=frozenset({skill}),
        verified_evidence_digests=verified,
        repository_root=repository_root,
    )


@pytest.fixture
def catalog():
    return load_catalog()


@pytest.fixture
def runtime(tmp_path: Path, catalog):
    return SkillRuntime(
        state_store=SqliteExecutionStore((tmp_path / "state.sqlite3").resolve()),
        artifact_store=ContentAddressedArtifactStore((tmp_path / "artifacts").resolve()),
        catalog=catalog,
    )


def test_catalog_binds_exact_source_cardinalities(catalog):
    assert len(catalog.skills) == 300
    assert sum(len(item.dependencies) for item in catalog.skills) == 537
    assert len(catalog.routes) == 784
    assert len(catalog.reference_routes) == 40
    assert all(item.readiness == "not-run" for item in catalog.routes)
    assert all(item.status == "not-run" for item in catalog.reference_routes)
    assert any(
        issue["id"] == "SOURCE-SCHEMA-BATCH-ENUM-A-I"
        for issue in catalog.raw["source_issues"]
    )


def test_registry_has_300_distinct_exact_handlers(catalog):
    registry = build_registry(catalog)
    validate_registry(catalog, registry)
    assert len(registry) == 300
    assert len({binding.handler_id for binding in registry.values()}) == 300
    assert len({id(binding.handler) for binding in registry.values()}) == 300


def test_every_exact_handler_routes_without_fabricated_success(runtime, catalog):
    for definition in catalog.skills:
        result = runtime.execute(
            definition.name,
            _request(key=f"all-{definition.ordinal}"),
            authority=_authority(definition.name),
        )
        assert result["state"] != "FAILED", definition.name
        assert result["external_effects_performed"] is False
        assert result["certification"] != "CERTIFIED"
        assert result["request_artifact"] is not None
        assert result["artifact"] is not None


def test_scope_mismatch_has_no_state_or_artifact_write(tmp_path: Path, catalog):
    artifacts = (tmp_path / "artifacts").resolve()
    runtime = SkillRuntime(
        state_store=SqliteExecutionStore((tmp_path / "state.sqlite3").resolve()),
        artifact_store=ContentAddressedArtifactStore(artifacts),
        catalog=catalog,
    )
    skill = catalog.skills[0].name
    result = runtime.execute(
        skill,
        _request(tenant="attacker"),
        authority=_authority(skill, tenant="victim"),
    )
    assert result["code"] == "REQUEST_CONTRACT_REJECTED"
    assert result["request_artifact"] is None
    assert result["artifact"] is None
    assert not any(path.is_file() for path in artifacts.rglob("*"))


def test_idempotency_replays_and_rejects_changed_input(runtime, catalog):
    skill = catalog.skills[0].name
    authority = _authority(skill)
    first = runtime.execute(skill, _request(key="same"), authority=authority)
    replay = runtime.execute(skill, _request(key="same"), authority=authority)
    assert replay == first
    with pytest.raises(IdempotencyConflict):
        runtime.execute(
            skill,
            _request(inputs={"goal": "different"}, key="same"),
            authority=authority,
        )


def test_same_idempotency_key_is_isolated_by_tenant(runtime, catalog):
    skill = catalog.skills[0].name
    left = runtime.execute(
        skill,
        _request(key="shared", tenant="tenant-a"),
        authority=_authority(skill, tenant="tenant-a"),
    )
    right = runtime.execute(
        skill,
        _request(key="shared", tenant="tenant-b"),
        authority=_authority(skill, tenant="tenant-b"),
    )
    assert left["tenant_id"] == "tenant-a"
    assert right["tenant_id"] == "tenant-b"
    assert left["result_digest"] != right["result_digest"]


def test_state_database_is_private_and_rejects_symlink_target(tmp_path: Path):
    database = (tmp_path / "private-state.sqlite3").resolve()
    SqliteExecutionStore(database)
    assert database.stat().st_mode & 0o777 == 0o600

    outside = (tmp_path / "outside-state.sqlite3").resolve()
    outside.write_bytes(b"outside-sentinel")
    linked = tmp_path / "linked-state.sqlite3"
    linked.symlink_to(outside)
    with pytest.raises(StateStoreError):
        SqliteExecutionStore(linked.absolute())
    assert outside.read_bytes() == b"outside-sentinel"


def test_legacy_idempotency_record_cannot_replay_across_runtime_contract(
    tmp_path: Path, catalog
):
    state_store = SqliteExecutionStore((tmp_path / "state.sqlite3").resolve())
    artifact_store = ContentAddressedArtifactStore((tmp_path / "artifacts").resolve())
    runtime = SkillRuntime(
        state_store=state_store,
        artifact_store=artifact_store,
        catalog=catalog,
    )
    skill = catalog.skills[0].name
    request_value = _request(key="legacy-runtime-contract")
    request = RuntimeRequest.parse(request_value)
    state_store.commit(
        skill_name=skill,
        request=request,
        request_digest="sha256:" + "f" * 64,
        result={"legacy_result": True},
    )
    with pytest.raises(IdempotencyConflict):
        runtime.execute(skill, request_value, authority=_authority(skill))


def test_operation_contract_rejects_incoherent_gate_ready_state():
    with pytest.raises(ContractError, match="independently verified gate-ready"):
        _validate_operation(
            {
                "state": "BLOCKED",
                "code": "BUGGY_HANDLER",
                "implementation_state": "INDEPENDENT_GATE_REQUIRED",
                "outputs": {"verdict": "DIVERGENT"},
                "unavailable": [],
                "warnings": [],
                "external_effects_performed": False,
                "external_evidence": "INDEPENDENTLY_VERIFIED",
                "certification": "READY_FOR_EXTERNAL_GATE",
            }
        )


def test_repository_snapshot_rejects_symlinks(runtime, catalog, tmp_path: Path):
    skill = "elmos-immutable-repository-snapshot"
    assert skill in catalog.skills_by_name
    root = (tmp_path / "repository").resolve()
    root.mkdir()
    (root / "source.txt").write_text("safe", encoding="utf-8")
    (root / "escape").symlink_to(tmp_path / "outside")
    result = runtime.execute(
        skill,
        _request(key="symlink"),
        authority=_authority(skill, repository_root=root),
    )
    assert result["state"] == "BLOCKED"
    assert result["code"] == "REQUEST_CONTRACT_REJECTED"


def test_repository_snapshot_rejects_file_change_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = (tmp_path / "repository-race").resolve()
    root.mkdir()
    changing = root / "changing.bin"
    changing.write_bytes(b"a" * (2 * 1024 * 1024))
    original_read = os.read
    mutated = False

    def racing_read(descriptor: int, amount: int) -> bytes:
        nonlocal mutated
        chunk = original_read(descriptor, amount)
        if chunk and not mutated:
            mutated = True
            with changing.open("ab") as handle:
                handle.write(b"changed")
        return chunk

    monkeypatch.setattr("elmos_polyglot_compiler.handlers.os.read", racing_read)
    with pytest.raises(ContractError, match="changed during read"):
        _scan_repository(root, REVISION)


def _receipt(
    *, subject_digest: str, evidence_type: str = "native-route-test", evidence_id: str = "evidence-1"
) -> dict:
    now = int(time.time())
    return {
        "schema_version": "1.0",
        "evidence_id": evidence_id,
        "evidence_type": evidence_type,
        "producer_id": "runner-1",
        "verifier_id": "verifier-2",
        "tenant_id": "t1",
        "project_id": "project-1",
        "revision_digest": REVISION,
        "environment_authority_id": "environment-1",
        "subject_digest": subject_digest,
        "artifact_digest": "sha256:" + "b" * 64,
        "status": "PASSED",
        "independent": True,
        "executed_at_epoch_seconds": now,
        "expires_at_epoch_seconds": now + 3600,
    }


def test_gate_requires_host_verified_subject_bound_evidence(runtime, catalog):
    definition = next(
        item for item in catalog.skills if item.operation_family == "quality-gate"
    )
    route_id = catalog.routes[0].route_id
    probe = runtime.execute(
        definition.name,
        _request(
            inputs={"route_id": route_id, "evidence_receipts": []},
            key="gate-policy-probe",
        ),
        authority=_authority(definition.name),
    )
    server_required = probe["outputs"]["required_evidence_types"]
    required = sorted(set(server_required) | {"native-route-test"})
    subject_digest = digest_json(
        {"route_id": route_id, "required_evidence_types": required}
    )
    receipts = [
        _receipt(
            subject_digest=subject_digest,
            evidence_type=evidence_type,
            evidence_id=f"evidence-{index}",
        )
        for index, evidence_type in enumerate(required, start=1)
    ]
    receipt_digests = frozenset(digest_json(receipt) for receipt in receipts)
    inputs = {
        "route_id": route_id,
        "required_evidence_types": ["native-route-test"],
        "evidence_receipts": receipts,
    }
    unverified = runtime.execute(
        definition.name,
        _request(inputs=inputs, key="unverified"),
        authority=_authority(definition.name),
    )
    assert unverified["state"] == "BLOCKED"
    assert unverified["certification"] == "NOT_CERTIFIED"

    verified = runtime.execute(
        definition.name,
        _request(inputs=inputs, key="verified"),
        authority=_authority(definition.name, verified=receipt_digests),
    )
    assert verified["state"] == "READY_FOR_EXTERNAL_GATE"
    assert verified["certification"] == "READY_FOR_EXTERNAL_GATE"
    assert verified["external_effects_performed"] is False


def test_host_verified_receipt_for_another_subject_still_blocks(runtime, catalog):
    definition = next(
        item for item in catalog.skills if item.operation_family == "quality-gate"
    )
    receipt = _receipt(subject_digest="sha256:" + "c" * 64)
    receipt_digest = digest_json(receipt)
    result = runtime.execute(
        definition.name,
        _request(
            inputs={
                "route_id": catalog.routes[0].route_id,
                "required_evidence_types": ["native-route-test"],
                "evidence_receipts": [receipt],
            },
            key="wrong-subject",
        ),
        authority=_authority(definition.name, verified=frozenset({receipt_digest})),
    )
    assert result["state"] == "BLOCKED"
    assert result["outputs"]["evidence_evaluation"]["receipts"][0]["code"] == (
        "EVIDENCE_SUBJECT_MISMATCH"
    )


def test_gate_caller_cannot_reduce_repository_owned_evidence_policy(runtime, catalog):
    definition = next(
        item for item in catalog.skills if item.operation_family == "quality-gate"
    )
    route_id = catalog.routes[0].route_id
    probe = runtime.execute(
        definition.name,
        _request(
            inputs={"route_id": route_id, "evidence_receipts": []},
            key="minimum-policy-probe",
        ),
        authority=_authority(definition.name),
    )
    required = probe["outputs"]["required_evidence_types"]
    subject_digest = digest_json(
        {"route_id": route_id, "required_evidence_types": required}
    )
    receipt = _receipt(
        subject_digest=subject_digest,
        evidence_type=required[0],
        evidence_id="single-caller-selected-evidence",
    )
    result = runtime.execute(
        definition.name,
        _request(
            inputs={
                "route_id": route_id,
                "required_evidence_types": [required[0]],
                "evidence_receipts": [receipt],
            },
            key="cannot-reduce-policy",
        ),
        authority=_authority(
            definition.name, verified=frozenset({digest_json(receipt)})
        ),
    )
    assert result["state"] == "BLOCKED"
    assert result["certification"] == "NOT_CERTIFIED"
    assert result["outputs"]["missing_evidence_types"]


def test_verified_fuzz_divergence_never_becomes_gate_ready(runtime, catalog):
    definition = next(
        item for item in catalog.skills if item.operation_family == "semantic-fuzzing"
    )
    route_id = catalog.routes[0].route_id
    campaign = {"id": "campaign-1", "corpus_digest": "sha256:" + "d" * 64}
    results = [
        {
            "case_id": "case-1",
            "source_digest": "sha256:" + "1" * 64,
            "target_digest": "sha256:" + "2" * 64,
            "verdict": "DIVERGENT",
        }
    ]
    required = [
        "counterexample-replay",
        "differential-fuzz-results",
        "independent-verification",
    ]
    subject_digest = digest_json(
        {
            "route_id": route_id,
            "campaign": campaign,
            "results_digest": digest_json(results),
            "required_evidence_types": required,
        }
    )
    receipts = [
        _receipt(
            subject_digest=subject_digest,
            evidence_type=evidence_type,
            evidence_id=f"fuzz-evidence-{index}",
        )
        for index, evidence_type in enumerate(required, start=1)
    ]
    result = runtime.execute(
        definition.name,
        _request(
            inputs={
                "route_id": route_id,
                "campaign": campaign,
                "results": results,
                "evidence_receipts": receipts,
            },
            key="verified-divergence",
        ),
        authority=_authority(
            definition.name,
            verified=frozenset(digest_json(receipt) for receipt in receipts),
        ),
    )
    assert result["state"] == "BLOCKED"
    assert result["code"] == "FUZZ_DIVERGENCE_OR_INCONCLUSIVE_VERIFIED"
    assert result["outputs"]["verdict"] == "DIVERGENT"
    assert result["external_evidence"] == "INDEPENDENTLY_VERIFIED"
    assert result["certification"] == "NOT_CERTIFIED"


def test_content_addressed_artifact_tampering_is_detected(tmp_path: Path):
    store = ContentAddressedArtifactStore((tmp_path / "artifacts").resolve())
    assert store.root.stat().st_mode & 0o777 == 0o700
    artifact = store.put_bytes(b"trusted", media_type="application/octet-stream")
    digest = artifact["digest"]
    hexdigest = digest.removeprefix("sha256:")
    path = store.root / "sha256" / hexdigest[:2] / hexdigest[2:4] / hexdigest
    path.write_bytes(b"tampered")
    with pytest.raises(ArtifactStoreError):
        store.get(digest)
    assert hashlib.sha256(b"trusted").hexdigest() == hexdigest


def test_artifact_store_rejects_symlink_ancestor_without_external_write(tmp_path: Path):
    root = (tmp_path / "artifact-symlink-root").resolve()
    outside = (tmp_path / "outside").resolve()
    outside.mkdir()
    store = ContentAddressedArtifactStore(root)
    value = b"cannot-escape"
    hexdigest = hashlib.sha256(value).hexdigest()
    (root / "sha256").mkdir()
    (root / "sha256" / hexdigest[:2]).symlink_to(outside, target_is_directory=True)
    with pytest.raises(ArtifactStoreError):
        store.put_bytes(value, media_type="application/octet-stream")
    assert list(outside.iterdir()) == []
