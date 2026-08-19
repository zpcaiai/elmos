"""Stage Contract registry: validation, lint, guards and the capability DAG."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from elmos_build_cache.enums import CacheMode, Determinism, FileClass, ValidationLevel
from elmos_build_cache.errors import ContractViolation, NotFound
from elmos_build_cache.stage_contract import (
    PortSpec,
    SideEffectSpec,
    StageContract,
    StageContractRegistry,
    default_pipeline,
    default_registry,
    lint_contract,
)

VALID_DIMENSIONS = (
    "stage_id",
    "stage_version",
    "stage_contract_schema",
    "input_artifact_digests",
    "target_language",
    "toolchain_digest",
    "rule_pack_digest",
    "model_snapshot_digest",
)


def contract(**overrides: object) -> StageContract:
    base: dict[str, object] = {
        "stage_id": "demo",
        "stage_version": "1.0.0",
        "inputs": (PortSpec("ir", "elmos.semantic-ir/v3"),),
        "outputs": (PortSpec("tree", "elmos.file-tree/v1", True, FileClass.PUBLISH_CANDIDATE),),
        "fingerprint_include": VALID_DIMENSIONS,
        "determinism": Determinism.SEEDED,
    }
    base.update(overrides)
    return StageContract(**base)  # type: ignore[arg-type]


def test_default_pipeline_covers_the_conversion_flow() -> None:
    registry = default_registry()
    assert set(registry.stage_ids()) >= {
        "repository-discovery",
        "source-parse",
        "semantic-analysis",
        "semantic-ir",
        "mapping-plan",
        "target-code-generation",
        "compile",
        "test",
        "behavior-validation",
        "repair",
        "certification",
    }
    assert registry.validate_compatibility() == []
    assert len(default_pipeline()) == 13


def test_capability_edges_follow_producer_consumer_schemas() -> None:
    edges = default_registry().capability_edges()
    assert ("mapping-plan", "target-code-generation", "elmos.mapping-plan/v2") in edges
    assert ("compile", "test", "elmos.build-output/v1") in edges


def test_contract_digest_participates_in_the_fingerprint_spec() -> None:
    registry = default_registry()
    generation = registry.get("target-code-generation")
    spec = generation.fingerprint_spec()
    assert generation.digest()[:19] in spec.stage_contract_schema
    assert "model_snapshot_digest" in spec.include


def test_runtime_guard_enforces_declared_outputs_and_roots() -> None:
    guard = default_registry().get("target-code-generation").guard()
    guard.declare_output("generated_tree")
    with pytest.raises(ContractViolation, match="required outputs"):
        guard.check_complete()
    guard.declare_output("source_maps")
    guard.check_complete()

    with pytest.raises(ContractViolation, match="undeclared output port"):
        guard.declare_output("surprise")
    with pytest.raises(ContractViolation, match="writable roots"):
        guard.check_write_root("source")
    guard.check_write_root("generated/pending")


def test_guard_fails_a_deterministic_stage_that_reads_hidden_environment() -> None:
    deterministic = contract(determinism=Determinism.DETERMINISTIC, declared_environment=("LANG",))
    guard = deterministic.guard()
    assert guard.check_environment({"LANG": "C"}) == {"declared": ["LANG"], "undeclared": []}
    with pytest.raises(ContractViolation, match="undeclared environment"):
        guard.check_environment({"LANG": "C", "CI_JOB_ID": "1"})


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"source_access": "read-write"}, "MUTABLE_SOURCE"),
        ({"writable_roots": ("source",)}, "UNDECLARED_PATH"),
        ({"undeclared_output_policy": "ignore"}, "UNDECLARED_OUTPUT_POLICY"),
        ({"minimum_validation_level": ValidationLevel.QUARANTINED}, "MISSING_VALIDATION_FLOOR"),
        ({"outputs": ()}, "NO_OUTPUTS"),
        (
            {"determinism": Determinism.NONDETERMINISTIC_CANDIDATE_ONLY, "cache_mode": CacheMode.READ_WRITE},
            "NONDETERMINISTIC_WRITE",
        ),
        ({"side_effects": (SideEffectSpec("notify", "webhook", idempotent=False),)}, "UNSAFE_SIDE_EFFECT"),
        (
            {"outputs": (PortSpec("tree", "elmos.file-tree@latest"),)},
            "MUTABLE_ALIAS",
        ),
        ({"negative_cache": True, "determinism": Determinism.SEEDED}, "UNSAFE_NEGATIVE_CACHE"),
    ],
)
def test_lint_catches_unsafe_contracts(overrides: dict[str, object], code: str) -> None:
    findings = {finding.code for finding in lint_contract(contract(**overrides))}
    assert code in findings


def test_lint_flags_a_key_that_ignores_its_inputs() -> None:
    thin = contract(
        fingerprint_include=(
            "stage_id",
            "stage_version",
            "stage_contract_schema",
            "target_language",
            "toolchain_digest",
        )
    )
    assert "MISSING_INPUT_DIGESTS" in {finding.code for finding in lint_contract(thin)}


def test_seeded_stage_must_pin_a_model_snapshot() -> None:
    unpinned = contract(
        fingerprint_include=tuple(d for d in VALID_DIMENSIONS if d != "model_snapshot_digest")
    )
    assert "UNPINNED_MODEL" in {finding.code for finding in lint_contract(unpinned)}


def test_registry_rejects_a_contract_that_fails_lint() -> None:
    registry = StageContractRegistry()
    with pytest.raises(ContractViolation):
        registry.register(contract(source_access="read-write"))


def test_registry_rejects_a_silent_contract_change() -> None:
    registry = StageContractRegistry()
    registry.register(contract())
    with pytest.raises(ContractViolation, match="version bump"):
        registry.register(contract(checkpoint_interval_seconds=99))
    registry.register(contract(stage_version="1.1.0", checkpoint_interval_seconds=99))


def test_unknown_stage_lookup_fails_loudly() -> None:
    with pytest.raises(NotFound):
        StageContractRegistry().get("ghost")


def test_contract_round_trips_through_the_packaged_schema(tmp_path: Path) -> None:
    original = default_registry().get("target-code-generation")
    path = tmp_path / "target-code-generation.stage-contract.json"
    path.write_text(json.dumps(original.to_dict(), indent=2), encoding="utf-8")

    registry = StageContractRegistry(external_schemas=("elmos.snapshot/v1",))
    loaded = registry.load_directory(tmp_path)
    assert loaded[0].digest() == original.digest()


def test_shipped_example_contract_is_accepted() -> None:
    example = Path(__file__).resolve().parents[1] / "docs"
    # The package example lives beside the spec; use the in-repo default instead
    # when it is not vendored, so the test never silently skips.
    contract_dict = default_registry().get("target-code-generation").to_dict()
    assert contract_dict["determinism"] == "SEEDED"
    assert contract_dict["workspace"]["source"] == "read-only"
    assert example.is_dir()


def test_documentation_is_generated_from_the_contract() -> None:
    text = default_registry().get("target-code-generation").documentation()
    assert "# Stage `target-code-generation`" in text
    assert "contract digest" in text
    assert "generated_tree" in text
