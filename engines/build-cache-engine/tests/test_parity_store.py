"""Durable v1.2 parity metadata contracts."""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest

from elmos_build_cache.canonical import canonical_json_text, digest_of
from elmos_build_cache.db.store import MetadataStore
from elmos_build_cache.errors import (
    ConflictError,
    ContractViolation,
    CorruptObject,
    IdempotencyConflict,
    TenantMismatch,
)
from elmos_build_cache.parity import EvidenceBinding, evaluate_parity
from elmos_build_cache.parity_store import ParityMetadataRepository
from elmos_build_cache.prompt_cache import NormalizedTokenUsage, PromptProvider, UsageAccounting

TENANT = "tenant-test"
PROJECT = "project-test"
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64
DIGEST_E = "sha256:" + "e" * 64


@pytest.fixture
def repository(store: MetadataStore) -> ParityMetadataRepository:
    return ParityMetadataRepository(store)


def prompt_manifest(manifest_id: str = "manifest-1") -> dict[str, object]:
    return {
        "schema_version": "1.2.0",
        "manifest_id": manifest_id,
        "provider_namespace": "openai/project-digest-1",
        "compatibility_group": "provider-model-effort-tools-v1",
        "provider": "openai",
        "model": "gpt-5.6",
        "effort": "high",
        "tool_schema_digest": DIGEST_A,
        "segments": [
            {
                "segment_id": "system-policy",
                "stability_class": "GLOBAL_STABLE",
                "digest": DIGEST_B,
                "byte_length": 120,
                "sensitivity": "INTERNAL",
            }
        ],
        "stable_prefix_digest": DIGEST_C,
    }


def environment_snapshot(
    snapshot_id: str = "snapshot-1",
    snapshot_key: str = DIGEST_D,
) -> dict[str, object]:
    return {
        "schema_version": "1.2.0",
        "snapshot_id": snapshot_id,
        "snapshot_key": snapshot_key,
        "platform": {"os": "linux", "arch": "arm64", "libc": "glibc"},
        "base_image_digest": DIGEST_A,
        "lockfile_digests": [DIGEST_B],
        "toolchain_digests": [DIGEST_C],
        "layers": [{"layer_type": "DEPENDENCIES", "digest": DIGEST_E, "size_bytes": 10}],
        "trust_namespace": "tenant/project/toolchain",
        "status": "AVAILABLE",
    }


def outcome(event_id: str = "event-1", request_id: str = "request-1") -> dict[str, object]:
    return {
        "schema_version": "1.2.0",
        "event_id": event_id,
        "request_id": request_id,
        "layer": "ACTION",
        "outcome": "HIT",
        "reason_code": "EXACT_ACTION_RESULT",
        "eligible": True,
        "identity_digest": DIGEST_A,
        "occurred_at": "2026-08-20T00:00:00Z",
    }


def affinity_decision() -> dict[str, object]:
    return {
        "schema_version": "1.2.0",
        "decision_id": "decision-1",
        "affinity_key": DIGEST_B,
        "request_id": "request-1",
        "selected_target": "worker-1",
        "candidates": [
            {
                "target_id": "worker-1",
                "compatible": True,
                "score": 19.0,
                "prompt_value_ms": 20.0,
                "queue_penalty_ms": 1.0,
            }
        ],
        "reason_codes": ["PREFIX_LOCAL"],
        "decided_at": "2026-08-20T00:00:00Z",
    }


def external_parity_report(report_id: str = "report-external") -> dict[str, object]:
    return {
        "schema_version": "1.2.0",
        "report_id": report_id,
        "subject": {
            "source_digest": DIGEST_A,
            "config_digest": DIGEST_B,
            "corpus_digest": DIGEST_C,
            "provider_profile_digests": [DIGEST_D],
            "platform_digest": DIGEST_E,
        },
        "thresholds": {},
        "metrics": {},
        "scenario_results": [
            {"scenario_id": "exact-rerun", "passed": False, "metrics": {}}
        ],
        "mandatory_pass": False,
        "false_hits": 0,
        "cross_tenant_hits": 0,
        "corrupt_executions": 0,
        "generated_at": "2026-08-20T00:00:00Z",
        "limitations": ["External execution remains NOT_RUN."],
    }


def internal_not_run_report(report_id: str = "report-internal") -> dict[str, object]:
    report = evaluate_parity(
        report_id=report_id,
        metrics={},
        cohorts={},
        scenarios=(),
        binding=EvidenceBinding(
            source_digest=DIGEST_A,
            configuration_digest=DIGEST_B,
            provider_profiles_digest=DIGEST_C,
            corpus_digest=DIGEST_D,
            platform_digest=DIGEST_E,
            generated_at="2026-08-20T00:00:00Z",
            executor_identity="executor-a",
            verifier_identity="verifier-b",
        ),
    )
    return report.to_dict()


def test_parity_migrations_are_applied_and_packaged_byte_identical(
    store: MetadataStore,
) -> None:
    root = Path(__file__).resolve().parents[1]
    for dialect, filename in (
        ("sqlite", "0004_cache_parity.sql"),
        ("postgres", "0006_cache_parity.sql"),
    ):
        assert (root / "migrations" / dialect / filename).read_bytes() == (
            root / "src/elmos_build_cache/_data/migrations" / dialect / filename
        ).read_bytes()

    assert store.query_one(
        "SELECT name FROM schema_migrations WHERE name=?", ("0004_cache_parity.sql",)
    ) == ("0004_cache_parity.sql",)
    tables = {str(row[0]) for row in store.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "prompt_prefix_manifests",
        "provider_cache_usage",
        "environment_snapshot_manifests",
        "environment_snapshot_status_events",
        "cache_outcome_events_v12",
        "cache_affinity_decisions_v12",
        "cache_parity_reports_v12",
    } <= tables


def test_prompt_manifest_is_schema_valid_content_free_idempotent_and_scoped(
    repository: ParityMetadataRepository,
    store: MetadataStore,
) -> None:
    document = prompt_manifest()
    assert repository.put_prompt_manifest(TENANT, PROJECT, "manifest-1", document) == document
    assert repository.put_prompt_manifest(TENANT, PROJECT, "manifest-1", document) == document
    assert repository.get_prompt_manifest(TENANT, PROJECT, "manifest-1") == document
    assert repository.get_prompt_manifest("tenant-other", PROJECT, "manifest-1") is None
    row = store.query_one(
        "SELECT manifest_digest FROM prompt_prefix_manifests "
        "WHERE tenant_id=? AND project_id=? AND manifest_id=?",
        (TENANT, PROJECT, "manifest-1"),
    )
    assert row == (digest_of(document),)

    drift = copy.deepcopy(document)
    drift["stable_prefix_digest"] = DIGEST_D
    with pytest.raises(IdempotencyConflict):
        repository.put_prompt_manifest(TENANT, PROJECT, "manifest-1", drift)
    with pytest.raises(TenantMismatch):
        repository.put_prompt_manifest("tenant-other", PROJECT, "manifest-1", document)


@pytest.mark.parametrize("tamper", ["digest", "column", "schema"])
def test_prompt_get_fails_closed_on_database_tamper(
    repository: ParityMetadataRepository,
    store: MetadataStore,
    tamper: str,
) -> None:
    document = prompt_manifest()
    repository.put_prompt_manifest(TENANT, PROJECT, "manifest-1", document)
    with store.transaction():
        if tamper == "digest":
            store.execute(
                "UPDATE prompt_prefix_manifests SET manifest_digest=? "
                "WHERE tenant_id=? AND project_id=? AND manifest_id=?",
                (DIGEST_B, TENANT, PROJECT, "manifest-1"),
            )
        elif tamper == "column":
            store.execute(
                "UPDATE prompt_prefix_manifests SET provider=? "
                "WHERE tenant_id=? AND project_id=? AND manifest_id=?",
                ("anthropic", TENANT, PROJECT, "manifest-1"),
            )
        else:
            malformed = dict(document)
            del malformed["segments"]
            store.execute(
                "UPDATE prompt_prefix_manifests SET manifest_digest=?, document=? "
                "WHERE tenant_id=? AND project_id=? AND manifest_id=?",
                (
                    digest_of(malformed),
                    canonical_json_text(malformed),
                    TENANT,
                    PROJECT,
                    "manifest-1",
                ),
            )

    with pytest.raises(CorruptObject):
        repository.get_prompt_manifest(TENANT, PROJECT, "manifest-1")


def test_normalized_provider_usage_binds_existing_manifest_and_reconciles(
    repository: ParityMetadataRepository,
) -> None:
    manifest = prompt_manifest()
    repository.put_prompt_manifest(TENANT, PROJECT, "manifest-1", manifest)
    manifest_digest = digest_of(manifest)
    usage = NormalizedTokenUsage(
        provider=PromptProvider.OPENAI,
        total_input_tokens=100,
        processed_input_tokens=40,
        output_tokens=12,
        cache_read_tokens=60,
        cache_write_tokens=None,
        accounting=UsageAccounting.INCLUSIVE,
        observed_fields=("usage.input_tokens",),
    )
    stored = repository.put_provider_usage(
        TENANT, PROJECT, "usage-1", manifest_digest, usage
    )
    assert stored["prompt_manifest_digest"] == manifest_digest
    assert stored["cache_read_tokens"] == 60
    assert "observed_fields" not in stored
    assert repository.put_provider_usage(
        TENANT, PROJECT, "usage-1", manifest_digest, usage
    ) == stored

    drift = dict(usage.telemetry())
    drift.update(total_input_tokens=101, processed_input_tokens=41)
    with pytest.raises(IdempotencyConflict):
        repository.put_provider_usage(TENANT, PROJECT, "usage-1", manifest_digest, drift)
    with pytest.raises(ContractViolation, match="only normalized counter fields"):
        repository.put_provider_usage(
            TENANT,
            PROJECT,
            "usage-2",
            manifest_digest,
            {**usage.telemetry(), "raw_prompt": "do not persist"},
        )


def test_environment_manifest_is_immutable_and_terminal_status_is_append_only(
    repository: ParityMetadataRepository,
    store: MetadataStore,
) -> None:
    document = environment_snapshot()
    repository.put_environment_snapshot(TENANT, PROJECT, DIGEST_D, document)
    assert repository.get_environment_snapshot(TENANT, PROJECT, DIGEST_D) == document
    with pytest.raises(IdempotencyConflict):
        repository.put_environment_snapshot(
            TENANT,
            PROJECT,
            DIGEST_D,
            environment_snapshot("snapshot-same-key", DIGEST_D),
        )
    state = repository.get_environment_snapshot_state(TENANT, PROJECT, DIGEST_D)
    assert state is not None and state["effective_status"] == "AVAILABLE"

    status_event = repository.append_environment_snapshot_status(
        TENANT, PROJECT, DIGEST_D, "status-1", "AVAILABLE", "QUARANTINED", DIGEST_A
    )
    assert status_event["new_status"] == "QUARANTINED"
    assert repository.append_environment_snapshot_status(
        TENANT, PROJECT, DIGEST_D, "status-1", "AVAILABLE", "QUARANTINED", DIGEST_A
    ) == status_event
    state = repository.get_environment_snapshot_state(TENANT, PROJECT, DIGEST_D)
    assert state is not None and state["effective_status"] == "QUARANTINED"
    assert state["manifest"] == document

    with pytest.raises(ConflictError):
        repository.append_environment_snapshot_status(
            TENANT, PROJECT, DIGEST_D, "status-2", "AVAILABLE", "REVOKED", DIGEST_B
        )
    with pytest.raises(sqlite3.IntegrityError, match="APPEND_ONLY"):
        with store.transaction():
            store.execute(
                "DELETE FROM environment_snapshot_status_events "
                "WHERE tenant_id=? AND project_id=? AND snapshot_key=?",
                (TENANT, PROJECT, DIGEST_D),
            )


def test_environment_get_and_state_reject_tampered_manifest_digest(
    repository: ParityMetadataRepository,
    store: MetadataStore,
) -> None:
    repository.put_environment_snapshot(
        TENANT,
        PROJECT,
        DIGEST_D,
        environment_snapshot(),
    )
    with store.transaction():
        store.execute(
            "UPDATE environment_snapshot_manifests SET manifest_digest=? "
            "WHERE tenant_id=? AND project_id=? AND snapshot_key=?",
            (DIGEST_B, TENANT, PROJECT, DIGEST_D),
        )

    with pytest.raises(CorruptObject):
        repository.get_environment_snapshot(TENANT, PROJECT, DIGEST_D)
    with pytest.raises(CorruptObject):
        repository.get_environment_snapshot_state(TENANT, PROJECT, DIGEST_D)


@pytest.mark.parametrize(
    "tamper",
    ["sequence", "previous_event_digest", "event_digest", "manifest_binding"],
)
def test_environment_state_validates_the_complete_append_only_chain(
    repository: ParityMetadataRepository,
    store: MetadataStore,
    tamper: str,
) -> None:
    repository.put_environment_snapshot(
        TENANT,
        PROJECT,
        DIGEST_D,
        environment_snapshot(),
    )
    repository.append_environment_snapshot_status(
        TENANT,
        PROJECT,
        DIGEST_D,
        "status-1",
        "AVAILABLE",
        "QUARANTINED",
        DIGEST_A,
    )

    with store.transaction():
        store.execute("DROP TRIGGER environment_snapshot_status_events_no_update")
        if tamper == "sequence":
            store.execute(
                "UPDATE environment_snapshot_status_events SET sequence=2 "
                "WHERE tenant_id=? AND project_id=? AND snapshot_key=?",
                (TENANT, PROJECT, DIGEST_D),
            )
        elif tamper == "previous_event_digest":
            store.execute(
                "UPDATE environment_snapshot_status_events SET previous_event_digest=? "
                "WHERE tenant_id=? AND project_id=? AND snapshot_key=?",
                (DIGEST_B, TENANT, PROJECT, DIGEST_D),
            )
        elif tamper == "event_digest":
            store.execute(
                "UPDATE environment_snapshot_status_events SET event_digest=? "
                "WHERE tenant_id=? AND project_id=? AND snapshot_key=?",
                (DIGEST_B, TENANT, PROJECT, DIGEST_D),
            )
        else:
            row = store.query_one(
                "SELECT document FROM environment_snapshot_status_events "
                "WHERE tenant_id=? AND project_id=? AND snapshot_key=?",
                (TENANT, PROJECT, DIGEST_D),
            )
            assert row is not None
            event = json.loads(str(row[0]))
            event["manifest_digest"] = DIGEST_B
            body = {key: value for key, value in event.items() if key != "event_digest"}
            event["event_digest"] = digest_of(body)
            store.execute(
                "UPDATE environment_snapshot_status_events "
                "SET event_digest=?, document=? "
                "WHERE tenant_id=? AND project_id=? AND snapshot_key=?",
                (
                    event["event_digest"],
                    canonical_json_text(event),
                    TENANT,
                    PROJECT,
                    DIGEST_D,
                ),
            )

    with pytest.raises(CorruptObject):
        repository.get_environment_snapshot_state(TENANT, PROJECT, DIGEST_D)


@pytest.mark.parametrize("location", ["platform", "layer"])
def test_environment_manifest_runtime_overlay_rejects_unknown_nested_fields(
    repository: ParityMetadataRepository,
    location: str,
) -> None:
    document = environment_snapshot()
    platform = document["platform"]
    layers = document["layers"]
    assert isinstance(platform, dict)
    assert isinstance(layers, list) and isinstance(layers[0], dict)
    target = platform if location == "platform" else layers[0]
    target["note"] = "secret-under-innocuous-key"

    with pytest.raises(ContractViolation, match="closed shape"):
        repository.put_environment_snapshot(TENANT, PROJECT, DIGEST_D, document)


def test_outcomes_are_append_only_idempotent_and_explain_one_request(
    repository: ParityMetadataRepository,
    store: MetadataStore,
) -> None:
    first = outcome()
    second = outcome("event-2")
    second["layer"] = "ENVIRONMENT"
    second["outcome"] = "NECESSARY_MISS"
    second["reason_code"] = "LOCKFILE_CHANGED"
    repository.put_cache_outcome(TENANT, PROJECT, "request-1", "event-1", first)
    repository.put_cache_outcome(TENANT, PROJECT, "request-1", "event-2", second)
    assert repository.put_cache_outcome(
        TENANT, PROJECT, "request-1", "event-1", first
    ) == first
    assert repository.list_cache_outcomes(TENANT, PROJECT, "request-1") == (first, second)
    assert repository.list_cache_outcomes("tenant-other", PROJECT, "request-1") == ()

    drift = copy.deepcopy(first)
    drift["outcome"] = "UNEXPECTED_MISS"
    with pytest.raises(IdempotencyConflict):
        repository.put_cache_outcome(TENANT, PROJECT, "request-1", "event-1", drift)
    with pytest.raises(sqlite3.IntegrityError, match="APPEND_ONLY"):
        with store.transaction():
            store.execute(
                "UPDATE cache_outcome_events_v12 SET reason_code=? "
                "WHERE tenant_id=? AND project_id=? AND event_id=?",
                ("DRIFT", TENANT, PROJECT, "event-1"),
            )


def test_outcome_list_rejects_document_to_index_binding_tamper(
    repository: ParityMetadataRepository,
    store: MetadataStore,
) -> None:
    document = outcome()
    repository.put_cache_outcome(
        TENANT,
        PROJECT,
        "request-1",
        "event-1",
        document,
    )
    tampered = dict(document)
    tampered["request_id"] = "request-other"
    with store.transaction():
        store.execute("DROP TRIGGER cache_outcome_events_v12_no_update")
        store.execute(
            "UPDATE cache_outcome_events_v12 SET event_digest=?, document=? "
            "WHERE tenant_id=? AND project_id=? AND event_id=?",
            (
                digest_of(tampered),
                canonical_json_text(tampered),
                TENANT,
                PROJECT,
                "event-1",
            ),
        )

    with pytest.raises(CorruptObject):
        repository.list_cache_outcomes(TENANT, PROJECT, "request-1")


def test_affinity_and_both_parity_report_contracts_are_durable(
    repository: ParityMetadataRepository,
) -> None:
    affinity = affinity_decision()
    assert repository.put_affinity_decision(
        TENANT, PROJECT, "request-1", "decision-1", affinity
    ) == affinity

    external = external_parity_report()
    repository.put_parity_report(TENANT, PROJECT, "report-external", external)
    assert repository.get_parity_report(TENANT, PROJECT, "report-external") == external

    internal = internal_not_run_report()
    assert internal["decision"] == "NOT_RUN"
    repository.put_parity_report(TENANT, PROJECT, "report-internal", internal)
    assert repository.get_parity_report(TENANT, PROJECT, "report-internal") == internal

    tampered = copy.deepcopy(internal)
    tampered["missing"] = []
    with pytest.raises(ContractViolation, match="mandatory scenario|decision"):
        repository.put_parity_report(TENANT, PROJECT, "report-tampered", tampered)


def test_parity_report_get_revalidates_internal_report_semantics(
    repository: ParityMetadataRepository,
    store: MetadataStore,
) -> None:
    report = internal_not_run_report()
    repository.put_parity_report(TENANT, PROJECT, "report-internal", report)
    tampered = copy.deepcopy(report)
    tampered["missing"] = []
    with store.transaction():
        store.execute(
            "UPDATE cache_parity_reports_v12 SET report_digest=?, document=? "
            "WHERE tenant_id=? AND project_id=? AND report_id=?",
            (
                digest_of(tampered),
                canonical_json_text(tampered),
                TENANT,
                PROJECT,
                "report-internal",
            ),
        )

    with pytest.raises(CorruptObject):
        repository.get_parity_report(TENANT, PROJECT, "report-internal")


@pytest.mark.parametrize(
    ("document", "put"),
    [
        (
            {**prompt_manifest("manifest-raw"), "raw_prompt": "customer prompt"},
            lambda repository, document: repository.put_prompt_manifest(
                TENANT, PROJECT, "manifest-raw", document
            ),
        ),
        (
            {
                **environment_snapshot("snapshot-raw", DIGEST_E),
                "platform": {"os": "linux", "arch": "arm64", "raw_secret": "value"},
            },
            lambda repository, document: repository.put_environment_snapshot(
                TENANT, PROJECT, DIGEST_E, document
            ),
        ),
        (
            {**internal_not_run_report("report-raw"), "metrics": {"raw_source": "code"}},
            lambda repository, document: repository.put_parity_report(
                TENANT, PROJECT, "report-raw", document
            ),
        ),
    ],
)
def test_raw_prompt_source_and_secret_keys_are_rejected(
    repository: ParityMetadataRepository,
    document: dict[str, object],
    put: object,
) -> None:
    assert callable(put)
    with pytest.raises(ContractViolation, match="must not contain raw"):
        put(repository, document)
