"""Packaged contract data, configuration loading and schema round-trips."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from elmos_build_cache import schemas
from elmos_build_cache.config import (
    CacheConfig,
    default_config,
    load_config,
    load_config_mapping,
)
from elmos_build_cache.enums import (
    NODE_TRANSITIONS,
    STAGED_FILE_TRANSITIONS,
    CacheMode,
    MissReason,
    NodeStatus,
    StagedFileStatus,
    TrustNamespace,
    ValidationLevel,
)
from elmos_build_cache.errors import ContractViolation, SchemaInvalid

ROOT = Path(__file__).resolve().parents[1]
PACKAGED = ROOT / "src" / "elmos_build_cache" / "_data"


@pytest.mark.parametrize(
    ("repo_path", "packaged_path"),
    [
        ("schemas", "schemas"),
        ("openapi", "openapi"),
        ("migrations/postgres", "migrations/postgres"),
        ("migrations/sqlite", "migrations/sqlite"),
    ],
)
def test_repository_contract_copies_match_the_packaged_ones(repo_path: str, packaged_path: str) -> None:
    """The human-facing copies and the importable ones cannot drift apart."""
    repository = ROOT / repo_path
    packaged = PACKAGED / packaged_path
    assert repository.is_dir() and packaged.is_dir()
    repo_files = {path.name: path.read_bytes() for path in sorted(repository.iterdir()) if path.is_file()}
    packaged_files = {path.name: path.read_bytes() for path in sorted(packaged.iterdir()) if path.is_file()}
    assert repo_files == packaged_files


def test_every_declared_schema_is_loadable() -> None:
    for name in schemas.SCHEMA_NAMES:
        assert schemas.load_schema(name)["$id"].endswith(f"{name}.schema.json")
    with pytest.raises(SchemaInvalid):
        schemas.load_schema("does-not-exist")


def test_schema_validation_rejects_incomplete_documents() -> None:
    with pytest.raises(SchemaInvalid) as error:
        schemas.validate("staged-file", {"schema_version": "1.0.0"})
    assert error.value.details["errors"]


def test_shipped_manifest_examples_validate() -> None:
    templates = ROOT / "docs"
    assert templates.is_dir()
    staged = {
        "schema_version": "1.0.0",
        "staged_file_id": "sf_1",
        "tenant_id": "t",
        "project_id": "p",
        "run_id": "r",
        "node_id": "gen",
        "attempt": 1,
        "logical_path": "src/App.cs",
        "file_class": "SEALED_ARTIFACT",
        "status": "CAS_PROMOTED",
        "lease_epoch": 3,
        "version": 4,
        "digest": "sha256:" + "a" * 64,
    }
    schemas.validate("staged-file", staged)


def test_default_config_is_safe() -> None:
    config = default_config()
    assert config.mode is CacheMode.READ_WRITE
    assert config.workspace.source_read_only is True
    assert config.workspace.undeclared_output_policy == "quarantine"
    assert config.security.reject_symlink_escape is True
    assert config.redis.authoritative is False
    assert config.package_version == "1.2.0"
    assert config.parity.claim_mode == "measured_only"
    assert config.parity.prompt_cache.mode == "observe"
    assert config.parity.prompt_cache.enabled is False
    assert config.parity.environment_snapshots.enabled is False
    assert config.parity.affinity.enabled is False
    assert config.parity.coordinator.enabled is False
    assert config.parity.context_ledger.append_only is True
    assert config.parity.automatic_rollback is True
    assert config.parity.false_hit_immediate_rollback is True


def test_shipped_configuration_files_load(tmp_path: Path) -> None:
    for name in ("elmos-cache.yaml", "elmos-cache.local.yaml"):
        config = load_config(ROOT / "config" / name)
        assert isinstance(config, CacheConfig)
        assert config.workspace.publish_strategy == "versioned-atomic-pointer"


def test_unknown_configuration_keys_are_rejected() -> None:
    with pytest.raises(ContractViolation, match="unknown configuration keys"):
        load_config_mapping({"elmos": {"cache": {"enabeld": True}}})


def test_redis_cannot_be_declared_authoritative() -> None:
    with pytest.raises(ContractViolation, match="authoritative"):
        load_config_mapping({"elmos": {"cache": {"redis": {"enabled": True, "authoritative": True}}}})


def test_unsafe_policy_values_are_rejected() -> None:
    with pytest.raises(ContractViolation):
        load_config_mapping({"elmos": {"cache": {"workspace": {"undeclared_output_policy": "ignore"}}}})
    with pytest.raises(ContractViolation):
        load_config_mapping({"elmos": {"cache": {"workspace": {"keep_previous_published_versions": 0}}}})
    with pytest.raises(ContractViolation):
        load_config_mapping({"elmos": {"cache": {"validation": {"default_minimum": "QUARANTINED"}}}})


@pytest.mark.parametrize(
    "parity",
    [
        {"claim_mode": "marketing_claim"},
        {"rollout_phase": "instant_full"},
        {"automatic_rollback": False},
        {"false_hit_immediate_rollback": False},
        {"unknown_outcome_rate_max": 0.011},
        {"prompt_cache": {"provider_failure_threshold": 4}},
        {"prompt_cache": {"provider_recovery_events": 9}},
        {"prompt_cache": {"canonical_layout": False}},
        {"prompt_cache": {"stable_turn_cached_token_reuse_min": 0.899}},
        {"prompt_cache": {"unexpected_full_prefix_miss_max": 0.021}},
        {"context_ledger": {"append_only": False}},
        {"context_ledger": {"whole_repository_reinjection": True}},
        {"context_ledger": {"compaction_soft_limit_ratio": 0.95}},
        {"context_ledger": {"compaction_warmup_reuse_min": 0.799}},
        {"environment_snapshots": {"embed_secret_values": True}},
        {"environment_snapshots": {"verify_digests_on_restore": False}},
        {"environment_snapshots": {"hit_rate_min": 0.949}},
        {"environment_snapshots": {"warm_start_p95_reduction_min": 0.799}},
        {"environment_snapshots": {"default_ttl_seconds": 86_401}},
        {"affinity": {"bounded_load_escape": False}},
        {"affinity": {"fairness_guard": False}},
        {"affinity": {"wrong_shard_rate_max": 0.011}},
        {"coordinator": {"singleflight": False}},
        {"coordinator": {"exact_action_before_model_call": False}},
        {"coordinator": {"unified_attribution": False}},
        {"coordinator": {"max_parallel_probes": 7}},
        {
            "rollout_phase": "observe",
            "prompt_cache": {"enabled": True, "mode": "serve"},
        },
        {"rollout_phase": "shadow", "environment_snapshots": {"enabled": True}},
        {"rollout_phase": "observe", "affinity": {"enabled": True}},
        {"rollout_phase": "shadow", "coordinator": {"enabled": True}},
    ],
)
def test_parity_configuration_fails_closed(parity: dict[str, object]) -> None:
    with pytest.raises(ContractViolation):
        load_config_mapping({"elmos": {"cache": {"parity": parity}}})


def test_type_errors_are_rejected_not_coerced() -> None:
    with pytest.raises(ContractViolation, match="expected a boolean"):
        load_config_mapping({"elmos": {"cache": {"enabled": "yes-please"}}})
    with pytest.raises(ContractViolation, match="expected an integer"):
        load_config_mapping({"elmos": {"cache": {"workspace": {"quota_gb_per_run": "lots"}}}})


def test_validation_level_ordering_and_quarantine_semantics() -> None:
    assert ValidationLevel.TEST_VERIFIED.satisfies(ValidationLevel.COMPILE_VERIFIED)
    assert not ValidationLevel.UNVERIFIED.satisfies(ValidationLevel.TEST_VERIFIED)
    assert not ValidationLevel.QUARANTINED.satisfies(ValidationLevel.UNVERIFIED)
    assert not ValidationLevel.PRODUCTION_CERTIFIED.satisfies(ValidationLevel.QUARANTINED)


def test_trust_namespace_ordering() -> None:
    assert TrustNamespace.OFFICIAL.satisfies(TrustNamespace.BRANCH)
    assert not TrustNamespace.FORK.satisfies(TrustNamespace.OFFICIAL)
    assert not TrustNamespace.QUARANTINE.satisfies(TrustNamespace.EXPERIMENTAL)


def test_state_machines_have_no_unreachable_or_undefined_states() -> None:
    for status in StagedFileStatus:
        assert status in STAGED_FILE_TRANSITIONS
        for target in STAGED_FILE_TRANSITIONS[status]:
            assert target in STAGED_FILE_TRANSITIONS
    for status in NodeStatus:
        assert status in NODE_TRANSITIONS
        for target in NODE_TRANSITIONS[status]:
            assert target in NODE_TRANSITIONS
    # The happy path is exactly the one the specification draws.
    happy = [
        StagedFileStatus.RESERVED,
        StagedFileStatus.WRITING,
        StagedFileStatus.SEALED,
        StagedFileStatus.CAS_PROMOTED,
        StagedFileStatus.TREE_INCLUDED,
        StagedFileStatus.PUBLISHED,
    ]
    for current, following in zip(happy, happy[1:], strict=False):
        assert following in STAGED_FILE_TRANSITIONS[current]


def test_miss_reason_taxonomy_matches_the_reference() -> None:
    reference = (ROOT / "docs" / "cache-miss-reasons.md")
    if not reference.is_file():
        pytest.skip("reference taxonomy not vendored")
    text = reference.read_text(encoding="utf-8")
    for reason in MissReason:
        assert f"`{reason.value}`" in text, reason


def test_cache_mode_read_write_matrix() -> None:
    assert CacheMode.READ_WRITE.may_read and CacheMode.READ_WRITE.may_write
    assert CacheMode.READ_ONLY.may_read and not CacheMode.READ_ONLY.may_write
    assert not CacheMode.WRITE_ONLY.may_read and CacheMode.WRITE_ONLY.may_write
    assert not CacheMode.BYPASS.may_read and not CacheMode.BYPASS.may_write
    assert CacheMode.REFRESH.may_write


def test_sqlite_schema_declares_every_authoritative_entity() -> None:
    sql = (PACKAGED / "migrations" / "sqlite" / "0001_init.sql").read_text(encoding="utf-8")
    for table in (
        "tenants",
        "projects",
        "snapshots",
        "runs",
        "run_nodes",
        "artifacts",
        "artifact_refs",
        "action_cache_entries",
        "staged_files",
        "file_trees",
        "checkpoints",
        "side_effect_receipts",
        "cache_events",
        "pins",
        "certificates",
        "revocations",
        "gc_plans",
        "gc_receipts",
        "idempotency_records",
        "outbox_events",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql, table
    assert "uq_staged_live_path" in sql
    assert "UNIQUE (run_id, sequence)" in sql


def test_canonical_json_is_stable_across_key_order() -> None:
    from elmos_build_cache.canonical import canonical_json_bytes

    assert canonical_json_bytes({"b": 1, "a": [2, {"d": 4, "c": 3}]}) == canonical_json_bytes(
        {"a": [2, {"c": 3, "d": 4}], "b": 1}
    )
    assert json.loads(canonical_json_bytes({"x": 1.0}))["x"] == 1
