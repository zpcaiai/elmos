#!/usr/bin/env python3
"""Fail-closed external qualification and certification gate.

This module verifies real, content-addressed campaign evidence for the 557
non-B16 child Skills.  It never manufactures execution evidence or signs a
certificate.  Native/domain execution, independent holdout, customer workload,
HSM, Canary, rollback, and certification records must be supplied by distinct
authorized external actors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from scripts.precision_migration.trust import (
    TrustStore,
    canonical_digest,
    configured_roots,
    verify_content_reference,
)


ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = ROOT / "docs" / "precision-migration-b01-44" / "external-execution-profiles.json"
INSTALLED_PATH = ROOT / "docs" / "precision-migration-b01-44" / "installed-manifest.json"
STAGES = (
    "native_source_execution",
    "native_target_execution",
    "independent_holdout",
    "representative_customer_workload",
)
STAGE_PARTITIONS = {
    "native_source_execution": "development",
    "native_target_execution": "development",
    "independent_holdout": "holdout",
    "representative_customer_workload": "representative",
}
STAGE_ROLES = {
    "native_source_execution": "native-verifier",
    "native_target_execution": "native-verifier",
    "independent_holdout": "independent-verifier",
    "representative_customer_workload": "customer-workload-verifier",
}
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class ExternalGateError(ValueError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExternalGateError(f"JSON root must be an object: {path}")
    return value


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _require_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or DIGEST.fullmatch(value) is None:
        raise ExternalGateError(f"{field} must be sha256:<64 lowercase hex>")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 1000:
        raise ExternalGateError(f"{field} must be a bounded non-empty string")
    return value


@dataclass(frozen=True)
class ExternalProfileRegistry:
    payload: dict[str, Any]
    by_skill: dict[str, dict[str, Any]]
    digest: str

    @classmethod
    def load(cls, path: Path = PROFILE_PATH) -> "ExternalProfileRegistry":
        payload = _load(path)
        if (
            payload.get("schema_version") != 1
            or payload.get("namespace") != "precision-migration-b01-44"
            or payload.get("profile_count") != 557
            or payload.get("excluded_native_b16_routes") != 30
            or tuple(payload.get("required_stages", [])) != STAGES
        ):
            raise ExternalGateError("external profile registry identity is invalid")
        checked = dict(payload)
        observed_registry_digest = checked.pop("registry_digest", None)
        if observed_registry_digest != canonical_digest(checked):
            raise ExternalGateError("external profile registry digest mismatch")
        profiles = payload.get("profiles")
        if not isinstance(profiles, list) or len(profiles) != 557:
            raise ExternalGateError("external profile registry must contain 557 profiles")
        by_skill: dict[str, dict[str, Any]] = {}
        for profile in profiles:
            if not isinstance(profile, dict):
                raise ExternalGateError("external profile entry must be an object")
            checked_profile = dict(profile)
            profile_digest = checked_profile.pop("profile_digest", None)
            if profile_digest != canonical_digest(checked_profile):
                raise ExternalGateError(f"external profile digest mismatch: {profile.get('skill')}")
            skill = profile.get("skill")
            if not isinstance(skill, str) or skill in by_skill:
                raise ExternalGateError("external profile Skills must be unique")
            if tuple(profile.get("required_stages", [])) != STAGES:
                raise ExternalGateError(f"external profile stages are incomplete: {skill}")
            by_skill[skill] = profile
        return cls(payload=payload, by_skill=by_skill, digest=str(observed_registry_digest))


def _installed_identity() -> dict[str, Any]:
    installed = _load(INSTALLED_PATH)
    return {
        "source_package_manifest_sha256": installed["source_package_manifest_sha256"],
        "source_tree_sha256": installed["source_tree_sha256"],
        "installed_manifest_digest": _file_digest(INSTALLED_PATH),
    }


def _load_reference_json(reference: Any, roots: tuple[Path, ...], label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    observed = verify_content_reference(reference, roots)
    try:
        payload = json.loads(Path(observed["resolved_path"]).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalGateError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExternalGateError(f"{label} JSON root must be an object")
    return payload, observed


def validate_canary_plan(payload: Any, *, environment: str) -> dict[str, Any]:
    """Validate the exact, executable shape of a production Canary plan.

    The campaign gate used to bind only the plan bytes.  That proved integrity,
    but not that the bytes described bounded traffic stages or an executable
    rollback relationship.  Keep the plan provider-neutral while rejecting
    floating percentages, missing observation windows, and non-rollbackable
    stages before production authorization can be considered.
    """
    required = {
        "schema_version", "plan_id", "environment", "stages",
        "canary_adapter_id", "rollback_adapter_id", "approval_required",
    }
    if not isinstance(payload, dict) or set(payload) != required or payload.get("schema_version") != 1:
        raise ExternalGateError("Canary plan fields are invalid")
    plan_id = _require_text(payload.get("plan_id"), "canary.plan_id")
    if payload.get("environment") != environment:
        raise ExternalGateError("Canary plan environment does not match the campaign")
    canary_adapter = _require_text(payload.get("canary_adapter_id"), "canary.canary_adapter_id")
    rollback_adapter = _require_text(payload.get("rollback_adapter_id"), "canary.rollback_adapter_id")
    if canary_adapter == rollback_adapter:
        raise ExternalGateError("Canary and rollback adapters must be distinct")
    if payload.get("approval_required") is not True:
        raise ExternalGateError("Canary plan must require production approval")
    stages = payload.get("stages")
    if not isinstance(stages, list) or not 1 <= len(stages) <= 20:
        raise ExternalGateError("Canary plan must contain between 1 and 20 stages")
    stage_fields = {
        "stage_id", "traffic_percent", "minimum_observation_seconds",
        "required_sli", "rollback_on_failure",
    }
    identifiers: set[str] = set()
    percentages: list[float] = []
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict) or set(stage) != stage_fields:
            raise ExternalGateError(f"Canary stage {index} fields are invalid")
        stage_id = _require_text(stage.get("stage_id"), f"canary.stages[{index}].stage_id")
        if stage_id in identifiers:
            raise ExternalGateError("Canary stage identities must be unique")
        identifiers.add(stage_id)
        percentage = stage.get("traffic_percent")
        if (
            not isinstance(percentage, (int, float))
            or isinstance(percentage, bool)
            or not 0 < float(percentage) <= 100
        ):
            raise ExternalGateError("Canary traffic percentages must be in (0, 100]")
        percentages.append(float(percentage))
        observation = stage.get("minimum_observation_seconds")
        if not isinstance(observation, int) or isinstance(observation, bool) or not 1 <= observation <= 604800:
            raise ExternalGateError("Canary observation windows must be between 1 second and 7 days")
        required_sli = stage.get("required_sli")
        if (
            not isinstance(required_sli, list)
            or not required_sli
            or any(not isinstance(item, str) or not item or len(item) > 200 for item in required_sli)
        ):
            raise ExternalGateError("Canary required_sli must be a unique non-empty string array")
        if len(required_sli) != len(set(required_sli)):
            raise ExternalGateError("Canary required_sli must be a unique non-empty string array")
        if stage.get("rollback_on_failure") is not True:
            raise ExternalGateError("every Canary stage must roll back on gate failure")
    if percentages != sorted(percentages) or len(percentages) != len(set(percentages)):
        raise ExternalGateError("Canary traffic percentages must increase strictly")
    return {
        "plan_id": plan_id,
        "canary_adapter_id": canary_adapter,
        "rollback_adapter_id": rollback_adapter,
        "stage_count": len(stages),
        "maximum_percent": percentages[-1],
    }


def validate_rollback_plan(
    payload: Any,
    *,
    environment: str,
    expected_adapter_id: str,
) -> dict[str, Any]:
    """Validate a bounded rollback exercise/operation plan."""
    required = {
        "schema_version", "plan_id", "environment", "target_digest",
        "rollback_adapter_id", "maximum_rto_seconds", "verification_checks",
        "data_reconciliation_required", "approval_required",
    }
    if not isinstance(payload, dict) or set(payload) != required or payload.get("schema_version") != 1:
        raise ExternalGateError("rollback plan fields are invalid")
    plan_id = _require_text(payload.get("plan_id"), "rollback.plan_id")
    if payload.get("environment") != environment:
        raise ExternalGateError("rollback plan environment does not match the campaign")
    _require_digest(payload.get("target_digest"), "rollback.target_digest")
    adapter_id = _require_text(payload.get("rollback_adapter_id"), "rollback.rollback_adapter_id")
    if adapter_id != expected_adapter_id:
        raise ExternalGateError("Canary and rollback plans name different rollback adapters")
    maximum_rto = payload.get("maximum_rto_seconds")
    if not isinstance(maximum_rto, int) or isinstance(maximum_rto, bool) or not 1 <= maximum_rto <= 86400:
        raise ExternalGateError("rollback maximum_rto_seconds must be between 1 and 86400")
    checks = payload.get("verification_checks")
    if (
        not isinstance(checks, list)
        or not checks
        or any(not isinstance(item, str) or not item or len(item) > 200 for item in checks)
    ):
        raise ExternalGateError("rollback verification_checks must be a unique non-empty string array")
    if len(checks) != len(set(checks)):
        raise ExternalGateError("rollback verification_checks must be a unique non-empty string array")
    if payload.get("data_reconciliation_required") is not True:
        raise ExternalGateError("rollback plan must require data reconciliation")
    if payload.get("approval_required") is not True:
        raise ExternalGateError("rollback plan must require production approval")
    return {
        "plan_id": plan_id,
        "rollback_adapter_id": adapter_id,
        "maximum_rto_seconds": maximum_rto,
        "verification_check_count": len(checks),
    }


def _verify_corpus(
    partition: str,
    reference: Any,
    registry: ExternalProfileRegistry,
    roots: tuple[Path, ...],
) -> tuple[dict[str, str], dict[str, Any]]:
    payload, observed = _load_reference_json(reference, roots, f"{partition} corpus")
    if (
        payload.get("schema_version") != 1
        or payload.get("namespace") != "precision-migration-b01-44"
        or payload.get("partition") != partition
    ):
        raise ExternalGateError(f"{partition} corpus identity is invalid")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 557:
        raise ExternalGateError(f"{partition} corpus must contain 557 cases")
    by_skill: dict[str, str] = {}
    case_digests: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"skill", "profile_digest", "case_digest"}:
            raise ExternalGateError(f"{partition} corpus case fields are invalid")
        skill = case.get("skill")
        profile = registry.by_skill.get(str(skill))
        case_digest = _require_digest(case.get("case_digest"), f"{partition}.case_digest")
        if profile is None or case.get("profile_digest") != profile["profile_digest"]:
            raise ExternalGateError(f"{partition} corpus profile binding is invalid: {skill}")
        if skill in by_skill or case_digest in case_digests:
            raise ExternalGateError(f"{partition} corpus cases and case digests must be unique")
        by_skill[str(skill)] = case_digest
        case_digests.add(case_digest)
    if set(by_skill) != set(registry.by_skill):
        raise ExternalGateError(f"{partition} corpus Skill coverage is incomplete")
    return by_skill, observed


def validate_external_corpus(
    partition: str,
    reference: Any,
    *,
    profile_registry: ExternalProfileRegistry | None = None,
    evidence_roots: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """Validate one exact 557-Skill corpus without executing it.

    This public preflight surface intentionally returns only identity and
    content-addressed observations.  It cannot promote a corpus or any Skill
    maturity state; the independently signed result manifests remain the only
    execution evidence accepted by :func:`evaluate_external_campaign`.
    """
    if partition not in {"development", "holdout", "representative"}:
        raise ExternalGateError("external corpus partition is not supported")
    registry = profile_registry or ExternalProfileRegistry.load()
    cases, observed = _verify_corpus(
        partition,
        reference,
        registry,
        configured_roots(evidence_roots),
    )
    return {
        "state": "VALIDATED_NOT_EXECUTED",
        "partition": partition,
        "case_count": len(cases),
        "profile_registry_digest": registry.digest,
        "content": observed,
        "execution_state": "NOT_RUN",
    }


def validate_external_case_binding(
    partition: str,
    reference: Any,
    *,
    skill: str,
    profile_digest: str,
    case_digest: str,
    profile_registry: ExternalProfileRegistry | None = None,
    evidence_roots: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """Bind one external operation to an exact profile-owned corpus case."""
    if partition not in {"development", "holdout", "representative"}:
        raise ExternalGateError("external corpus partition is not supported")
    registry = profile_registry or ExternalProfileRegistry.load()
    profile = registry.by_skill.get(skill)
    if profile is None or profile.get("profile_digest") != profile_digest:
        raise ExternalGateError("external operation profile binding is invalid")
    cases, observed = _verify_corpus(
        partition,
        reference,
        registry,
        configured_roots(evidence_roots),
    )
    _require_digest(case_digest, "external operation case_digest")
    if cases.get(skill) != case_digest:
        raise ExternalGateError("external operation case binding is invalid")
    return {
        "skill": skill,
        "profile_digest": profile_digest,
        "partition": partition,
        "case_digest": case_digest,
        "corpus_digest": observed["digest"],
    }


def _verify_result_manifest(
    campaign_id: str,
    stage: str,
    reference: Any,
    registry: ExternalProfileRegistry,
    cases: dict[str, str],
    roots: tuple[Path, ...],
) -> tuple[dict[str, Any], dict[str, Any], set[str]]:
    payload, observed = _load_reference_json(reference, roots, f"{stage} result manifest")
    if (
        payload.get("schema_version") != 1
        or payload.get("namespace") != "precision-migration-b01-44"
        or payload.get("campaign_id") != campaign_id
        or payload.get("stage") != stage
    ):
        raise ExternalGateError(f"{stage} result manifest identity is invalid")
    bundle = verify_content_reference(payload.get("evidence_bundle"), roots)
    if bundle["size_bytes"] == 0:
        raise ExternalGateError(f"{stage} evidence bundle must not be empty")
    results = payload.get("results")
    if not isinstance(results, list) or len(results) != 557:
        raise ExternalGateError(f"{stage} result manifest must contain 557 results")
    observed_skills: set[str] = set()
    actors: set[str] = set()
    result_digests: set[str] = set()
    required_fields = {
        "skill", "profile_digest", "case_digest", "state", "exit_code",
        "environment_digest", "executor", "verifier", "replay_command", "result_digest",
    }
    for result in results:
        if not isinstance(result, dict) or set(result) != required_fields:
            raise ExternalGateError(f"{stage} result fields are invalid")
        checked = dict(result)
        result_digest = checked.pop("result_digest", None)
        if result_digest != canonical_digest(checked) or result_digest in result_digests:
            raise ExternalGateError(f"{stage} result digest is invalid or duplicated")
        skill = result.get("skill")
        profile = registry.by_skill.get(str(skill))
        if profile is None or result.get("profile_digest") != profile["profile_digest"]:
            raise ExternalGateError(f"{stage} result profile binding is invalid: {skill}")
        if skill in observed_skills or result.get("case_digest") != cases.get(str(skill)):
            raise ExternalGateError(f"{stage} case/result coverage is invalid: {skill}")
        if result.get("state") != "PASSED" or result.get("exit_code") != 0:
            raise ExternalGateError(f"{stage} contains a non-passing result: {skill}")
        _require_digest(result.get("environment_digest"), f"{stage}.environment_digest")
        executor = _require_text(result.get("executor"), f"{stage}.executor")
        verifier = _require_text(result.get("verifier"), f"{stage}.verifier")
        replay = result.get("replay_command")
        if executor == verifier:
            raise ExternalGateError(f"{stage} executor and verifier must be separate: {skill}")
        if not isinstance(replay, list) or not replay or any(not isinstance(item, str) or not item for item in replay):
            raise ExternalGateError(f"{stage} replay command must be a non-empty argv array")
        observed_skills.add(str(skill))
        result_digests.add(str(result_digest))
        actors.update((executor, verifier))
    if observed_skills != set(registry.by_skill):
        raise ExternalGateError(f"{stage} result Skill coverage is incomplete")
    return payload, {**observed, "evidence_bundle": bundle}, actors


def _campaign_digest(
    campaign: dict[str, Any],
    registry: ExternalProfileRegistry,
    corpus_observations: dict[str, dict[str, Any]],
    plan_observations: dict[str, dict[str, Any]],
) -> str:
    return canonical_digest(
        {
            "schema_version": 1,
            "namespace": "precision-migration-b01-44",
            "campaign_id": campaign.get("campaign_id"),
            "profile_registry_digest": registry.digest,
            "package_identity": campaign.get("package_identity"),
            "environment": campaign.get("environment"),
            "tenant_id": campaign.get("tenant_id"),
            "purpose": campaign.get("purpose"),
            "corpus_digests": {name: item["digest"] for name, item in sorted(corpus_observations.items())},
            "canary_plan_digest": plan_observations["canary"]["digest"],
            "rollback_plan_digest": plan_observations["rollback"]["digest"],
        }
    )


def _verify_envelope(
    trust_store: TrustStore,
    envelope: Any,
    role: str,
    bindings: dict[str, Any],
    now: datetime | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    verified = trust_store.verify_envelope(envelope, required_role=role, bindings=bindings, now=now)
    assert isinstance(envelope, dict) and isinstance(envelope.get("payload"), dict)
    payload = envelope["payload"]
    actor = _require_text(payload.get("actor_id"), f"{role}.actor_id")
    key_id = verified["key_id"]
    return payload, {
        **verified,
        "actor_id": actor,
        "public_key_digest": trust_store.keys[key_id].public_key_digest,
    }


def evaluate_external_campaign(
    campaign: dict[str, Any],
    *,
    evidence_roots: Iterable[Path] | None = None,
    trust_store: TrustStore | Path,
    profile_registry: ExternalProfileRegistry | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    registry = profile_registry or ExternalProfileRegistry.load()
    loaded_trust = TrustStore.load(trust_store) if isinstance(trust_store, Path) else trust_store
    roots = configured_roots(evidence_roots)
    failures: list[str] = []
    states = {
        "native_source_execution": "NOT_RUN",
        "native_target_execution": "NOT_RUN",
        "independent_holdout": "NOT_RUN",
        "representative_customer_workload": "NOT_RUN",
        "production_hsm": "NOT_RUN",
        "authorized_canary": "NOT_RUN",
        "verified_rollback": "NOT_RUN",
        "external_certification": "NOT_RUN",
    }
    result_base = {
        "schema_version": 1,
        "namespace": "precision-migration-b01-44",
        "campaign_id": campaign.get("campaign_id") if isinstance(campaign, dict) else None,
        "profile_registry_digest": registry.digest,
        "profile_count": 557,
    }
    if not isinstance(campaign, dict) or campaign.get("schema_version") != 1 or campaign.get("namespace") != "precision-migration-b01-44":
        failures.append("campaign identity is invalid")
        return _external_result(result_base, states, failures, 0, False, False)
    campaign_id = campaign.get("campaign_id")
    if not isinstance(campaign_id, str) or not campaign_id or len(campaign_id) > 200:
        failures.append("campaign_id is invalid")
    if campaign.get("profile_registry_digest") != registry.digest:
        failures.append("campaign profile registry binding is stale")
    if campaign.get("package_identity") != _installed_identity():
        failures.append("campaign installed package identity is stale")
    for field in ("environment", "tenant_id", "purpose"):
        try:
            _require_text(campaign.get(field), field)
        except ExternalGateError as exc:
            failures.append(str(exc))
    corpus_cases: dict[str, dict[str, str]] = {}
    corpus_observations: dict[str, dict[str, Any]] = {}
    corpora = campaign.get("corpora")
    if not isinstance(corpora, dict) or set(corpora) != {"development", "holdout", "representative"}:
        failures.append("campaign corpora must contain development, holdout, and representative")
    else:
        for partition in ("development", "holdout", "representative"):
            try:
                corpus_cases[partition], corpus_observations[partition] = _verify_corpus(
                    partition, corpora[partition], registry, roots
                )
            except (OSError, ValueError) as exc:
                failures.append(str(exc))
        if len(corpus_cases) == 3:
            for left, right in (("development", "holdout"), ("development", "representative"), ("holdout", "representative")):
                overlap = set(corpus_cases[left].values()) & set(corpus_cases[right].values())
                if overlap:
                    failures.append(f"corpus partitions overlap: {left}/{right}")
    plan_observations: dict[str, dict[str, Any]] = {}
    plan_payloads: dict[str, dict[str, Any]] = {}
    plans = campaign.get("plans")
    if not isinstance(plans, dict) or set(plans) != {"canary", "rollback"}:
        failures.append("campaign plans must contain Canary and rollback")
    else:
        for name in ("canary", "rollback"):
            try:
                plan_payloads[name], plan_observations[name] = _load_reference_json(
                    plans[name], roots, f"{name} plan"
                )
            except (OSError, ValueError) as exc:
                failures.append(f"{name} plan failed verification: {exc}")
        if len(plan_payloads) == 2:
            try:
                canary = validate_canary_plan(plan_payloads["canary"], environment=str(campaign.get("environment")))
                validate_rollback_plan(
                    plan_payloads["rollback"],
                    environment=str(campaign.get("environment")),
                    expected_adapter_id=canary["rollback_adapter_id"],
                )
            except ExternalGateError as exc:
                failures.append(str(exc))
    if failures:
        return _external_result(result_base, states, failures, 0, False, False)
    digest = _campaign_digest(campaign, registry, corpus_observations, plan_observations)
    try:
        campaign_payload, campaign_auth = _verify_envelope(
            loaded_trust,
            campaign.get("campaign_authorization"),
            "external-campaign-authorizer",
            {
                "record_type": "PRECISION_EXTERNAL_CAMPAIGN_AUTHORIZATION",
                "campaign_id": campaign_id,
                "campaign_digest": digest,
                "decision": "APPROVED",
            },
            now,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        failures.append(f"campaign authorization failed: {exc}")
        return _external_result({**result_base, "campaign_digest": digest}, states, failures, 0, False, False)
    stage_receipts = campaign.get("stage_receipts")
    stage_manifest_digests: dict[str, str] = {}
    stage_actors: dict[str, set[str]] = {}
    stage_keys: dict[str, str] = {}
    if not isinstance(stage_receipts, dict):
        stage_receipts = {}
    for stage in STAGES:
        receipt = stage_receipts.get(stage)
        if receipt is None:
            continue
        try:
            if not isinstance(receipt, dict) or set(receipt) != {"manifest", "attestation"}:
                raise ExternalGateError(f"{stage} receipt fields are invalid")
            partition = STAGE_PARTITIONS[stage]
            _, observed_manifest, actors = _verify_result_manifest(
                str(campaign_id), stage, receipt["manifest"], registry, corpus_cases[partition], roots
            )
            payload, attestation = _verify_envelope(
                loaded_trust,
                receipt["attestation"],
                STAGE_ROLES[stage],
                {
                    "record_type": "PRECISION_EXTERNAL_STAGE_ATTESTATION",
                    "campaign_id": campaign_id,
                    "campaign_digest": digest,
                    "stage": stage,
                    "manifest_digest": observed_manifest["digest"],
                    "corpus_digest": corpus_observations[partition]["digest"],
                    "state": "PASSED",
                },
                now,
            )
            executor = _require_text(payload.get("executor"), f"{stage}.attestation.executor")
            verifier = _require_text(payload.get("verifier"), f"{stage}.attestation.verifier")
            if executor == verifier or payload.get("actor_id") != verifier:
                raise ExternalGateError(f"{stage} attestation actor separation is invalid")
            if attestation["actor_id"] == campaign_auth["actor_id"]:
                raise ExternalGateError(f"{stage} verifier cannot be the campaign authorizer")
            stage_actors[stage] = actors | {executor, verifier, attestation["actor_id"]}
            stage_keys[stage] = attestation["public_key_digest"]
            stage_manifest_digests[stage] = observed_manifest["digest"]
            states[stage] = "PASSED"
        except (OSError, ValueError) as exc:
            states[stage] = "FAILED"
            failures.append(str(exc))
    if states["independent_holdout"] == "PASSED":
        native_actors = stage_actors.get("native_source_execution", set()) | stage_actors.get("native_target_execution", set())
        holdout_verifier = stage_receipts["independent_holdout"]["attestation"]["payload"].get("verifier")
        if holdout_verifier in native_actors:
            states["independent_holdout"] = "FAILED"
            failures.append("independent holdout verifier participated in native execution")
        if stage_keys.get("independent_holdout") in {
            stage_keys.get("native_source_execution"), stage_keys.get("native_target_execution")
        }:
            states["independent_holdout"] = "FAILED"
            failures.append("independent holdout verifier reused a native execution verification key")
    customer_authorization_verified = False
    if states["representative_customer_workload"] == "PASSED":
        try:
            _, customer_auth = _verify_envelope(
                loaded_trust,
                campaign.get("customer_authorization"),
                "customer-workload-authorizer",
                {
                    "record_type": "PRECISION_CUSTOMER_WORKLOAD_AUTHORIZATION",
                    "campaign_id": campaign_id,
                    "tenant_id": campaign.get("tenant_id"),
                    "purpose": campaign.get("purpose"),
                    "corpus_digest": corpus_observations["representative"]["digest"],
                    "decision": "APPROVED",
                },
                now,
            )
            representative_verifier = stage_receipts["representative_customer_workload"]["attestation"]["payload"].get("verifier")
            if customer_auth["actor_id"] == representative_verifier:
                raise ExternalGateError("customer authorizer and workload verifier must be separate")
            if customer_auth["public_key_digest"] == stage_keys.get("representative_customer_workload"):
                raise ExternalGateError("customer authorizer and workload verifier must use independent keys")
            customer_authorization_verified = True
        except (OSError, ValueError) as exc:
            states["representative_customer_workload"] = "FAILED"
            failures.append(f"customer authorization failed: {exc}")
    skill_stages_complete = all(states[stage] == "PASSED" for stage in STAGES) and customer_authorization_verified
    verified_skill_count = 557 if skill_stages_complete else 0
    release_digest = canonical_digest(
        {
            "campaign_digest": digest,
            "profile_registry_digest": registry.digest,
            "stage_manifest_digests": dict(sorted(stage_manifest_digests.items())),
            "verified_skill_count": verified_skill_count,
        }
    )
    production_complete = False
    if skill_stages_complete:
        production_complete = _verify_production_chain(
            campaign,
            campaign_id=str(campaign_id),
            release_digest=release_digest,
            plan_observations=plan_observations,
            trust_store=loaded_trust,
            now=now,
            states=states,
            failures=failures,
            forbidden_actors={campaign_auth["actor_id"]} | set().union(*stage_actors.values()),
            forbidden_keys={campaign_auth["public_key_digest"], *stage_keys.values()},
            roots=roots,
        )
    return _external_result(
        {
            **result_base,
            "campaign_digest": digest,
            "release_digest": release_digest,
            "trust_store_digest": loaded_trust.digest,
            "campaign_authorization": campaign_auth,
        },
        states,
        failures,
        verified_skill_count,
        skill_stages_complete,
        production_complete,
    )


def _verify_production_chain(
    campaign: dict[str, Any],
    *,
    campaign_id: str,
    release_digest: str,
    plan_observations: dict[str, dict[str, Any]],
    trust_store: TrustStore,
    now: datetime | None,
    states: dict[str, str],
    failures: list[str],
    forbidden_actors: set[str],
    forbidden_keys: set[str],
    roots: tuple[Path, ...],
) -> bool:
    required = {
        "production_authorization",
        "hsm_receipt",
        "canary_receipt",
        "rollback_receipt",
        "external_certificate",
        "production_artifacts",
    }
    supplied = {name for name in required if campaign.get(name) is not None}
    if not supplied:
        return False
    if supplied != required:
        failures.append(f"production evidence chain is incomplete: missing {sorted(required - supplied)}")
        return False
    production_actors: set[str] = set()
    production_keys: set[str] = set()
    try:
        artifact_refs = campaign["production_artifacts"]
        required_artifacts = {
            "hsm_payload", "hsm_signature", "hsm_public_key",
            "canary_metrics", "rollback_recovery",
        }
        if not isinstance(artifact_refs, dict) or set(artifact_refs) != required_artifacts:
            raise ExternalGateError("production_artifacts fields are invalid")
        artifacts = {
            name: verify_content_reference(reference, roots)
            for name, reference in artifact_refs.items()
        }
        authorization_payload, authorization = _verify_envelope(
            trust_store,
            campaign["production_authorization"],
            "production-change-approver",
            {
                "record_type": "PRECISION_PRODUCTION_CHANGE_AUTHORIZATION",
                "campaign_id": campaign_id,
                "release_digest": release_digest,
                "environment": campaign.get("environment"),
                "canary_plan_digest": plan_observations["canary"]["digest"],
                "rollback_plan_digest": plan_observations["rollback"]["digest"],
                "decision": "APPROVED",
            },
            now,
        )
        production_actors.add(authorization["actor_id"])
        production_keys.add(authorization["public_key_digest"])
        hsm_payload, hsm = _verify_envelope(
            trust_store,
            campaign["hsm_receipt"],
            "production-hsm-attestor",
            {
                "record_type": "PRECISION_HSM_SIGNATURE_RECEIPT",
                "campaign_id": campaign_id,
                "release_digest": release_digest,
                "state": "PASSED",
            },
            now,
        )
        for field in ("key_reference_digest", "signed_payload_digest", "signature_digest", "public_key_digest"):
            _require_digest(hsm_payload.get(field), f"hsm.{field}")
        for field in ("provider", "algorithm"):
            _require_text(hsm_payload.get(field), f"hsm.{field}")
        if hsm_payload.get("algorithm") != "ed25519":
            raise ExternalGateError("only the verified Ed25519 production HSM profile is supported")
        expected_hsm_digests = {
            "signed_payload_digest": artifacts["hsm_payload"]["digest"],
            "signature_digest": artifacts["hsm_signature"]["digest"],
            "public_key_digest": artifacts["hsm_public_key"]["digest"],
        }
        if any(hsm_payload.get(field) != expected for field, expected in expected_hsm_digests.items()):
            raise ExternalGateError("HSM receipt does not bind the supplied payload, signature, and public key bytes")
        signed_payload = json.loads(Path(artifacts["hsm_payload"]["resolved_path"]).read_text(encoding="utf-8"))
        if signed_payload != {"campaign_id": campaign_id, "release_digest": release_digest}:
            raise ExternalGateError("HSM signed payload is not the exact release identity")
        hsm_verification = subprocess.run(
            [
                "openssl", "pkeyutl", "-verify", "-pubin",
                "-inkey", artifacts["hsm_public_key"]["resolved_path"],
                "-rawin", "-in", artifacts["hsm_payload"]["resolved_path"],
                "-sigfile", artifacts["hsm_signature"]["resolved_path"],
            ],
            check=False,
            capture_output=True,
            timeout=10,
        )
        if hsm_verification.returncode != 0:
            raise ExternalGateError("HSM release signature failed cryptographic verification")
        production_actors.add(hsm["actor_id"])
        production_keys.add(hsm["public_key_digest"])
        states["production_hsm"] = "PASSED"
        canary_payload, canary = _verify_envelope(
            trust_store,
            campaign["canary_receipt"],
            "production-controller",
            {
                "record_type": "PRECISION_CANARY_EXECUTION_RECEIPT",
                "campaign_id": campaign_id,
                "release_digest": release_digest,
                "plan_digest": plan_observations["canary"]["digest"],
                "state": "PASSED",
            },
            now,
        )
        percentage = canary_payload.get("maximum_percent_observed")
        if not isinstance(percentage, (int, float)) or isinstance(percentage, bool) or not 0 < percentage <= 100:
            raise ExternalGateError("Canary maximum_percent_observed is invalid")
        if canary_payload.get("rollback_ready") is not True:
            raise ExternalGateError("Canary receipt does not prove rollback readiness")
        _require_digest(canary_payload.get("metrics_evidence_digest"), "canary.metrics_evidence_digest")
        if canary_payload.get("metrics_evidence_digest") != artifacts["canary_metrics"]["digest"]:
            raise ExternalGateError("Canary receipt does not bind the supplied metrics evidence")
        production_actors.add(canary["actor_id"])
        production_keys.add(canary["public_key_digest"])
        states["authorized_canary"] = "PASSED"
        rollback_payload, rollback = _verify_envelope(
            trust_store,
            campaign["rollback_receipt"],
            "rollback-controller",
            {
                "record_type": "PRECISION_ROLLBACK_VALIDATION_RECEIPT",
                "campaign_id": campaign_id,
                "release_digest": release_digest,
                "plan_digest": plan_observations["rollback"]["digest"],
                "state": "PASSED",
            },
            now,
        )
        if rollback_payload.get("mode") not in {"AUTHORIZED_EXERCISE", "ACTUAL_ROLLBACK"}:
            raise ExternalGateError("rollback receipt mode is invalid")
        _require_digest(rollback_payload.get("recovery_evidence_digest"), "rollback.recovery_evidence_digest")
        if rollback_payload.get("recovery_evidence_digest") != artifacts["rollback_recovery"]["digest"]:
            raise ExternalGateError("rollback receipt does not bind the supplied recovery evidence")
        production_actors.add(rollback["actor_id"])
        production_keys.add(rollback["public_key_digest"])
        states["verified_rollback"] = "PASSED"
        if len(production_actors) != 4 or production_actors & forbidden_actors:
            raise ExternalGateError("production authorization, HSM, Canary, rollback, and qualification actors are not separated")
        if len(production_keys) != 4 or production_keys & forbidden_keys:
            raise ExternalGateError("production authorization, HSM, Canary, rollback, and qualification keys are not separated")
        chain_digests = {
            "authorization_digest": canonical_digest(authorization_payload),
            "hsm_receipt_digest": canonical_digest(hsm_payload),
            "canary_receipt_digest": canonical_digest(canary_payload),
            "rollback_receipt_digest": canonical_digest(rollback_payload),
        }
        certificate_payload, certificate = _verify_envelope(
            trust_store,
            campaign["external_certificate"],
            "external-certifier",
            {
                "record_type": "PRECISION_EXTERNAL_CERTIFICATE",
                "campaign_id": campaign_id,
                "release_digest": release_digest,
                "profile_count": 557,
                "authorization_digest": chain_digests["authorization_digest"],
                "hsm_receipt_digest": chain_digests["hsm_receipt_digest"],
                "canary_receipt_digest": chain_digests["canary_receipt_digest"],
                "rollback_receipt_digest": chain_digests["rollback_receipt_digest"],
                "decision": "CERTIFIED",
            },
            now,
        )
        if certificate["actor_id"] in production_actors | forbidden_actors:
            raise ExternalGateError("external certifier is not independent")
        if certificate["public_key_digest"] in production_keys | forbidden_keys:
            raise ExternalGateError("external certifier key is not independent")
        _require_text(certificate_payload.get("certificate_id"), "certificate_id")
        states["external_certification"] = "PASSED"
        return True
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        failures.append(f"production evidence chain failed: {exc}")
        for stage in ("production_hsm", "authorized_canary", "verified_rollback", "external_certification"):
            if states[stage] == "NOT_RUN":
                states[stage] = "FAILED"
        return False


def _external_result(
    base: dict[str, Any],
    states: dict[str, str],
    failures: list[str],
    verified_skill_count: int,
    external_complete: bool,
    production_complete: bool,
) -> dict[str, Any]:
    if failures:
        decision = "REJECTED"
    elif production_complete:
        decision = "CERTIFIED"
    elif external_complete:
        decision = "EXTERNAL_VERIFIED"
    else:
        decision = "NOT_READY"
    body = {
        **base,
        "decision": decision,
        "verified_skill_count": verified_skill_count,
        "external_skill_evidence_complete": external_complete,
        "production_evidence_complete": production_complete,
        "stage_states": states,
        "production_operation_authorized": production_complete,
        "production_certification": "CERTIFIED" if production_complete else "NOT_CERTIFIED",
        "failures": failures,
    }
    return {**body, "result_digest": canonical_digest(body)}


def scaffold() -> dict[str, Any]:
    registry = ExternalProfileRegistry.load()
    body = {
        "schema_version": 1,
        "namespace": "precision-migration-b01-44",
        "profile_registry_digest": registry.digest,
        "profile_count": 557,
        "decision": "NOT_READY",
        "verified_skill_count": 0,
        "external_skill_evidence_complete": False,
        "production_evidence_complete": False,
        "stage_states": {
            stage: "NOT_RUN"
            for stage in (*STAGES, "production_hsm", "authorized_canary", "verified_rollback", "external_certification")
        },
        "production_operation_authorized": False,
        "production_certification": "NOT_CERTIFIED",
        "failures": [],
    }
    return {**body, "result_digest": canonical_digest(body)}


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate_parser = sub.add_parser("validate-profiles")
    validate_parser.add_argument("--registry", type=Path, default=PROFILE_PATH)
    scaffold_parser = sub.add_parser("scaffold")
    scaffold_parser.add_argument("--output", type=Path)
    evaluate_parser = sub.add_parser("evaluate")
    evaluate_parser.add_argument("--campaign", type=Path, required=True)
    evaluate_parser.add_argument("--trust-store", type=Path, required=True)
    evaluate_parser.add_argument("--evidence-root", type=Path, action="append", required=True)
    evaluate_parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "validate-profiles":
            registry = ExternalProfileRegistry.load(args.registry)
            result = {"status": "PASS", "profiles": len(registry.by_skill), "registry_digest": registry.digest}
            exit_code = 0
        elif args.command == "scaffold":
            result = scaffold()
            exit_code = 0
        else:
            result = evaluate_external_campaign(
                _load(args.campaign),
                evidence_roots=args.evidence_root,
                trust_store=args.trust_store,
            )
            exit_code = 0 if result["decision"] in {"EXTERNAL_VERIFIED", "CERTIFIED"} else 2
        rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        output = getattr(args, "output", None)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        return exit_code
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"decision": "REJECTED", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
