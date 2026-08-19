"""KEY-001..003: ActionKey dimensions, exclusions and hermeticity auditing."""

from __future__ import annotations

import dataclasses

import pytest

from elmos_build_cache.enums import MissReason
from elmos_build_cache.errors import ContractViolation
from elmos_build_cache.fingerprint import (
    EXCLUDED_DIMENSIONS,
    FingerprintInputs,
    StageFingerprintSpec,
    build_action_key,
    canonical_flags,
    explain_miss,
    observed_environment,
)

SPEC = StageFingerprintSpec(
    stage_id="target-code-generation",
    stage_version="1.0.0",
    stage_contract_schema="elmos.stage-contract/v1#abc",
    declared_environment=("LANG", "TZ"),
)


def digest(character: str) -> str:
    return "sha256:" + character * 64


BASE = FingerprintInputs(
    input_artifact_digests=(digest("1"),),
    source_semantic_digest=digest("2"),
    dependency_public_interface_digests=(digest("3"),),
    target_language="csharp",
    target_framework="aspnet-core",
    target_runtime="net10.0",
    rule_pack_digest=digest("5"),
    toolchain_digest=digest("4"),
    compiler_flags=("-O2", "--nullable=enable"),
    dependency_lock_digests={"packages.lock.json": digest("6")},
    declared_environment={"LANG": "C.UTF-8", "TZ": "UTC"},
    prompt_template_digest=digest("7"),
    model_snapshot_digest=digest("8"),
    decoding_parameters={"seed": 42, "temperature": 0.0},
    feature_flags={"generated_file_staging": True},
)


def test_key_001_irrelevant_inputs_do_not_move_the_key() -> None:
    """KEY-001: undeclared environment and temp paths cannot change the key."""
    noisy = dataclasses.replace(
        BASE,
        declared_environment={"LANG": "C.UTF-8", "TZ": "UTC", "TMPDIR": "/tmp/run-9182", "HOSTNAME": "b"},
    )
    assert build_action_key(SPEC, BASE).action_key == build_action_key(SPEC, noisy).action_key


def test_key_001_flag_order_and_duplicates_are_canonical() -> None:
    reordered = dataclasses.replace(BASE, compiler_flags=("--nullable=enable", "-O2", "-O2"))
    assert build_action_key(SPEC, reordered).action_key == build_action_key(SPEC, BASE).action_key
    assert canonical_flags(["-O2", "-O2", " --a=b "]) == ["--a=b", "-O2"]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("rule_pack_digest", digest("a"), MissReason.RULE_PACK_CHANGED),
        ("toolchain_digest", digest("b"), MissReason.TOOLCHAIN_CHANGED),
        ("target_runtime", "net11.0", MissReason.TARGET_PROFILE_CHANGED),
        ("prompt_template_digest", digest("c"), MissReason.PROMPT_TEMPLATE_CHANGED),
        ("model_snapshot_digest", digest("d"), MissReason.MODEL_SNAPSHOT_CHANGED),
        ("dependency_public_interface_digests", (digest("e"),), MissReason.PUBLIC_INTERFACE_CHANGED),
        ("dependency_lock_digests", {"packages.lock.json": digest("f")}, MissReason.DEPENDENCY_LOCK_CHANGED),
        ("compiler_flags", ("-O3",), MissReason.COMPILER_FLAGS_CHANGED),
        ("input_artifact_digests", (digest("9"),), MissReason.SOURCE_DIGEST_CHANGED),
    ],
)
def test_key_002_result_affecting_inputs_move_the_key(field: str, value: object, reason: MissReason) -> None:
    """KEY-002: every result-affecting dimension changes the key, with a reason."""
    baseline = build_action_key(SPEC, BASE)
    changed = build_action_key(SPEC, dataclasses.replace(BASE, **{field: value}))
    assert changed.action_key != baseline.action_key
    assert reason in explain_miss(changed, baseline).reasons


def test_key_003_undeclared_environment_is_excluded_and_audited() -> None:
    """KEY-003: the value stays out of the key and the audit records it."""
    audit = SPEC.audit_environment({"LANG": "C.UTF-8", "CI_JOB_ID": "918273"})
    assert audit["declared"] == ["LANG"]
    assert audit["undeclared"] == ["CI_JOB_ID"]
    with_extra = dataclasses.replace(
        BASE, declared_environment={"LANG": "C.UTF-8", "TZ": "UTC", "CI_JOB_ID": "918273"}
    )
    assert build_action_key(SPEC, with_extra).action_key == build_action_key(SPEC, BASE).action_key


def test_excluded_dimensions_cannot_be_declared() -> None:
    for name in ("run_id", "workspace_absolute_path", "wall_clock_time", "host_name"):
        assert name in EXCLUDED_DIMENSIONS
        with pytest.raises(ContractViolation):
            StageFingerprintSpec("s", "1", "c", include=(name,))


def test_secret_environment_cannot_enter_a_key() -> None:
    with pytest.raises(ContractViolation):
        StageFingerprintSpec("s", "1", "c", declared_environment=("GITHUB_TOKEN",))


def test_required_dimensions_must_be_present_and_non_empty() -> None:
    with pytest.raises(ContractViolation):
        build_action_key(SPEC, dataclasses.replace(BASE, toolchain_digest=""))


def test_fingerprint_document_is_explainable_and_schema_valid() -> None:
    from elmos_build_cache import schemas

    fingerprint = build_action_key(SPEC, BASE)
    schemas.validate("action-key", fingerprint.document)
    dimensions = fingerprint.document["explanation"]["dimension_digests"]
    assert "toolchain_digest" in dimensions
    assert fingerprint.document["explanation"]["canonicalization"] == "canonical-json-v1"


def test_first_miss_reports_no_entry() -> None:
    assert explain_miss(build_action_key(SPEC, BASE), None).reasons == (MissReason.NO_ENTRY,)


def test_observed_environment_reads_only_declared_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANG", "C.UTF-8")
    monkeypatch.setenv("SUPER_SECRET", "value")
    assert observed_environment(("LANG", "SUPER_SECRET")) == {
        "LANG": "C.UTF-8",
        "SUPER_SECRET": "value",
    }
    assert build_action_key(
        SPEC, dataclasses.replace(BASE, declared_environment=observed_environment(("LANG", "SUPER_SECRET")))
    ).dimensions["declared_environment"] == {"LANG": "C.UTF-8"}
