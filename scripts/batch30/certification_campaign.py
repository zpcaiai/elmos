#!/usr/bin/env python3
"""Validate the complete P0-P11 Batch 30 certification campaign.

The campaign layer is deliberately stricter than signature intake alone.  It
re-verifies every signed evidence document, its raw evidence references, the
exact source/target/policy binding, independent corpus separation, zero-
tolerance counters, and the external certificate scope.  It never invents
external evidence and never mutates a framework pack.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.batch30.validate_external_certification_intake import (  # noqa: E402
    REQUIRED_EVIDENCE,
    ExternalIntakeError,
    _approved_roots,
    _verify_reference,
    evaluate_external_intake_file,
)
from scripts.precision_migration.trust import (  # noqa: E402
    canonical_digest,
    read_regular_file_once,
)


CAMPAIGN_SCHEMA_VERSION = "elmos.batch30.certification-campaign.v1"
EVIDENCE_SCHEMA_VERSION = "elmos.batch30.external-evidence.v1"
PHASE_IDS = tuple(f"P{index}" for index in range(12))
CORPUS_ROLES = ("development", "holdout", "representative", "customer")
EXTERNAL_CORPUS_ROLES = ("holdout", "representative", "customer")
PHASE_EVIDENCE = {
    "P0": (),
    "P1": (),
    "P2": ("source_build", "target_build", "source_startup", "target_startup"),
    "P3": ("behavioral_equivalence",),
    "P4": ("security",),
    "P5": ("performance",),
    "P6": ("operability", "sbom"),
    "P7": ("rollback",),
    "P8": ("customer_acceptance",),
    "P9": (),  # populated with every pre-certification class below
    "P10": ("external_certification",),
    "P11": (),
}
LOCAL_PHASE_STATUSES = {
    "PASSED_LOCAL",
    "PASSED_LOCAL_EXACT_FIXTURE",
    "PARTIAL_LOCAL",
    "PREPARED_NOT_RUN",
    "NOT_RUN",
    "PASSED_EXPERIMENTAL_NOT_CERTIFIED",
}
COMMON_EVIDENCE_FIELDS = {
    "schema_version",
    "evidence_type",
    "campaign_digest",
    "binding_digest",
    "execution_id",
    "executed_at",
    "executor_actor_id",
    "executor_organization_id",
    "result",
    "environment",
    "metrics",
    "raw_evidence",
    "unknowns",
    "not_run",
    "waivers",
    "test_integrity",
}
EXPECTED_RESULTS = {
    **{name: "PASS" for name in REQUIRED_EVIDENCE},
    "customer_acceptance": "ACCEPTED",
    "external_certification": "CERTIFIED",
}
TECHNICAL_EVIDENCE = REQUIRED_EVIDENCE[:10]
PRE_CERTIFICATION_EVIDENCE = REQUIRED_EVIDENCE[:-1]
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-]{1,199}$")
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_PACK_CONTENT_BYTES = 512 * 1024 * 1024
MAX_RAW_EVIDENCE_BYTES = 256 * 1024 * 1024
BASE_TOOLCHAINS = {
    "source-java": ("source", "java"),
    "source-maven": ("source", "maven"),
    "source-container": ("source", "container"),
    "target-java": ("target", "java"),
    "target-maven": ("target", "maven"),
    "target-container": ("target", "container"),
}
RECIPE_SEED_PATHS = {
    "io/elmos/elmos-parent/0.1.0-SNAPSHOT/elmos-parent-0.1.0-SNAPSHOT.pom":
        "parent_pom_sha256",
    "io/elmos/elmos-java-recipes/0.1.0-SNAPSHOT/"
    "elmos-java-recipes-0.1.0-SNAPSHOT.pom": "recipe_pom_sha256",
    "io/elmos/elmos-java-recipes/0.1.0-SNAPSHOT/"
    "elmos-java-recipes-0.1.0-SNAPSHOT.jar": "jar_sha256",
}

METRIC_FIELDS = {
    "source_build": {
        "builds_total", "builds_passed", "tests_total", "failures", "errors",
        "skipped", "native", "exact_toolchain",
    },
    "target_build": {
        "builds_total", "builds_passed", "tests_total", "failures", "errors",
        "skipped", "native", "exact_toolchain", "artifact_digest", "rootless",
        "privileged",
    },
    "source_startup": {
        "startup_attempts", "startup_passed", "readiness_probes", "readiness_passed",
        "shutdown_attempts", "shutdown_passed", "startup_seconds", "shutdown_seconds",
        "native",
    },
    "target_startup": {
        "startup_attempts", "startup_passed", "readiness_probes", "readiness_passed",
        "shutdown_attempts", "shutdown_passed", "startup_seconds", "shutdown_seconds",
        "native", "rootless", "privileged", "effective_uid",
    },
    "behavioral_equivalence": {
        "routes_total", "routes_passed", "p0_contracts_total", "p0_contracts_passed",
        "holdout_projects", "representative_projects", "customer_projects",
        "route_coverage", "source_fingerprint_coverage", "framework_contract_coverage",
        "source_map_coverage", "critical_mismatch_count", "silent_framework_drops",
        "critical_transaction_regressions", "critical_data_regressions",
        "duplicate_message_or_job_effects", "test_integrity_violations",
        "rules_frozen_before_holdout", "rules_digest", "corpus_digests",
        "project_outcome_evidence_digests",
    },
    "security": {
        "scanners", "critical_findings", "high_findings", "authentication_regressions",
        "authorization_regressions", "critical_dependency_vulnerabilities",
        "critical_data_exposure_findings",
    },
    "performance": {
        "capacity_validated", "request_count", "error_count", "p95_ms", "slo_p95_ms",
        "throughput_rps", "slo_throughput_rps", "soak_seconds",
    },
    "operability": {
        "endpoints_verified", "failed_probes", "alert_failures", "runbook_failures",
        "trace_correlation_verified",
    },
    "sbom": {
        "artifact_digest", "format", "component_count", "unknown_licenses",
        "critical_vulnerabilities", "artifact_bound",
    },
    "rollback": {
        "rehearsed", "attempts", "passed", "actual_rto_seconds",
        "rto_objective_seconds", "data_loss_records", "orphan_effects",
    },
    "independent_review": {
        "organizationally_independent", "reviewed_evidence_types",
        "reviewed_content_digests", "critical_findings", "unresolved_findings",
    },
    "customer_acceptance": {
        "scenarios_total", "scenarios_passed", "accepted_artifact_digest",
        "accepted_execution_profile_digest", "customer_owned_holdout",
        "unresolved_findings",
    },
    "external_certification": {
        "decision", "scope_bound", "certified_capability_ids", "reviewed_evidence_types",
        "reviewed_content_digests", "certificate_valid_until", "manual_hours",
        "cost_per_verified_workload",
    },
}


class CampaignError(ValueError):
    """Raised when a P0-P11 campaign cannot support certification."""


def support_matrix_subject_digest(
    support_matrix: dict[str, Any], certified_capability_ids: Iterable[str]
) -> str:
    """Bind support semantics while normalizing only the governed promotion edits."""

    certified = set(certified_capability_ids)
    subject = copy.deepcopy(support_matrix)
    capabilities = subject.get("capabilities")
    if not isinstance(capabilities, list):
        raise CampaignError("support matrix capabilities must be an array")
    for capability in capabilities:
        if not isinstance(capability, dict) or capability.get("id") not in certified:
            continue
        capability["status"] = "CERTIFICATION_SUBJECT"
        refs = capability.get("evidence_refs")
        capability["evidence_refs"] = [
            ref
            for ref in (refs if isinstance(refs, list) else [])
            if ref != "certification/external-admission.json"
        ]
    return canonical_digest(subject)


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CampaignError(f"{label} must be an object")
    return value


def _exact_fields(value: dict[str, Any], expected: set[str], label: str) -> None:
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing or extra:
        raise CampaignError(
            f"{label} fields are invalid; missing={missing}, extra={extra}"
        )


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or IDENTITY.fullmatch(value) is None:
        raise CampaignError(f"{label} must be an exact identity")
    if value.upper() in {"UNKNOWN", "NOT_RUN", "INCONCLUSIVE", "BLOCKED"}:
        raise CampaignError(f"{label} must not be a non-success sentinel")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or DIGEST.fullmatch(value) is None:
        raise CampaignError(f"{label} must be sha256:<64 lowercase hex>")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise CampaignError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: Any, label: str, *, minimum: float = 0.0) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or value < minimum:
        raise CampaignError(f"{label} must be a number >= {minimum}")
    return float(value)


def _instant(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise CampaignError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CampaignError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise CampaignError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink():
        raise CampaignError(f"{label} must not be a symlink")
    try:
        raw = read_regular_file_once(path, max_bytes=MAX_JSON_BYTES, label=label)
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CampaignError(f"{label} is not bounded regular UTF-8 JSON: {exc}") from exc
    return _object(value, label), raw


def _content_snapshot(path: Path, label: str) -> tuple[str, int]:
    try:
        raw = read_regular_file_once(
            path,
            max_bytes=MAX_PACK_CONTENT_BYTES,
            label=label,
        )
    except (OSError, ValueError) as exc:
        raise CampaignError(f"{label} is not a bounded regular file: {exc}") from exc
    return "sha256:" + hashlib.sha256(raw).hexdigest(), len(raw)


def _safe_pack_file(pack: Path, relative: Any, label: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise CampaignError(f"{label} path is required")
    candidate_relative = Path(relative)
    if candidate_relative.is_absolute() or ".." in candidate_relative.parts:
        raise CampaignError(f"{label} path is unsafe")
    candidate = pack / candidate_relative
    current = pack
    for part in candidate_relative.parts:
        current /= part
        if current.is_symlink():
            raise CampaignError(f"{label} path must not traverse a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise CampaignError(f"{label} is missing: {relative}") from exc
    if not resolved.is_relative_to(pack.resolve()) or not resolved.is_file():
        raise CampaignError(f"{label} escapes the pack or is not a file")
    return resolved


def _validate_content_binding(
    pack: Path,
    record: Any,
    label: str,
    *,
    require_size: bool,
) -> dict[str, Any]:
    value = _object(record, label)
    expected_fields = {"path", "digest"} | ({"size_bytes"} if require_size else set())
    _exact_fields(value, expected_fields, label)
    path = _safe_pack_file(pack, value["path"], label)
    observed_digest, observed_size = _content_snapshot(path, label)
    if _digest(value["digest"], f"{label}.digest") != observed_digest:
        raise CampaignError(f"{label} digest does not match its bytes")
    if require_size and value["size_bytes"] != observed_size:
        raise CampaignError(f"{label} size does not match its bytes")
    return {**value, "resolved_path": str(path)}


def _version_tuple_from_exact_binding(value: dict[str, Any]) -> dict[str, Any]:
    source = _object(value.get("source"), "exact tuple source")
    target = _object(value.get("target"), "exact tuple target")
    toolchain = _object(value.get("toolchain"), "exact tuple toolchain")
    expected = {
        "source": {
            "framework": source.get("framework"),
            "framework_version": source.get("framework_version"),
            "java": source.get("java"),
            "maven": source.get("maven"),
            "servlet_namespace": source.get("servlet_namespace"),
            "servlet_api": source.get("servlet_api"),
            "container": toolchain.get("source_tomcat_version"),
        },
        "target": {
            "framework": target.get("framework"),
            "framework_version": target.get("framework_version"),
            "spring_framework_version": target.get("spring_framework_version"),
            "java": target.get("java"),
            "maven": target.get("maven"),
            "servlet_namespace": target.get("servlet_namespace"),
            "servlet_api": target.get("servlet_api"),
            "container": target.get("embedded_tomcat"),
        },
    }
    for side, fields in expected.items():
        for field, observed in fields.items():
            _identity(observed, f"exact tuple {side}.{field}")
            if "latest" in str(observed).lower():
                raise CampaignError(f"exact tuple {side}.{field} must not float")
    return expected


def _validate_exact_tuple_contract(
    pack: Path,
    campaign: dict[str, Any],
    binding: dict[str, Any],
) -> None:
    exact_record = _validate_content_binding(
        pack, binding["exact_tuple"], "campaign exact tuple", require_size=False
    )
    exact, _ = _read_json(Path(exact_record["resolved_path"]), "campaign exact tuple")
    if exact.get("pack_key") != campaign["pack_key"]:
        raise CampaignError("campaign exact tuple pack_key drifted")
    source = _object(exact.get("source"), "campaign exact tuple source")
    target = _object(exact.get("target"), "campaign exact tuple target")
    if source.get("commit") != binding["source_commit"]:
        raise CampaignError("campaign source commit does not match the exact tuple")
    if source.get("snapshot_sha256") != binding["source_snapshot_digest"]:
        raise CampaignError("campaign source snapshot does not match the exact tuple")
    artifact = binding["target_artifact"]
    if (
        target.get("artifact_sha256") != artifact.get("digest")
        or target.get("artifact_bytes") != artifact.get("size_bytes")
    ):
        raise CampaignError("campaign target artifact does not match the exact tuple")
    transformation = _object(exact.get("transformation"), "campaign exact tuple transformation")
    if transformation.get("target_profile_sha256") != binding["target_profile"].get("digest"):
        raise CampaignError("campaign target profile does not match the exact tuple")
    if exact.get("policy", {}).get("sha256") != binding["policy"].get("digest"):
        raise CampaignError("campaign policy does not match the exact tuple")
    if binding["version_tuple"] != _version_tuple_from_exact_binding(exact):
        raise CampaignError("campaign version tuple does not match the exact tuple bytes")
    boundary = exact.get("status_boundary")
    if not isinstance(boundary, dict) or (
        boundary.get("external_evidence") != "NOT_RUN"
        or boundary.get("production_certification") != "NOT_CERTIFIED"
        or boundary.get("local_runner_may_certify") is not False
    ):
        raise CampaignError("campaign exact tuple status boundary is not fail-closed")


def _validate_policy_contract(pack: Path, campaign: dict[str, Any]) -> None:
    binding = campaign["tuple_binding"]
    policy_path = _safe_pack_file(pack, binding["policy"]["path"], "campaign policy")
    policy, _ = _read_json(policy_path, "campaign policy")
    if policy.get("source_commit") != binding["source_commit"]:
        raise CampaignError("campaign policy source commit drifted")
    if policy.get("target_artifact", {}).get("sha256") != binding["target_artifact"]["digest"]:
        raise CampaignError("campaign policy target artifact drifted")
    evidence_policy = _object(policy.get("evidence_policy"), "campaign policy evidence_policy")
    if evidence_policy.get("required_evidence_types") != list(REQUIRED_EVIDENCE):
        raise CampaignError("campaign policy must require the exact 13 evidence classes")
    if (
        evidence_policy.get("external_evidence_status") != "NOT_RUN"
        or evidence_policy.get("certification_status") != "NOT_CERTIFIED"
        or evidence_policy.get("signature_algorithm") != "Ed25519"
    ):
        raise CampaignError("campaign policy evidence boundary is not fail-closed")
    toolchain_bindings = _object(
        policy.get("toolchain_bindings"), "campaign policy toolchain_bindings"
    )
    _exact_fields(
        toolchain_bindings,
        set(BASE_TOOLCHAINS),
        "campaign policy toolchain_bindings",
    )
    for name, value in toolchain_bindings.items():
        _digest(value, f"campaign policy toolchain_bindings.{name}")
    if toolchain_bindings["source-maven"] != toolchain_bindings["target-maven"]:
        raise CampaignError("campaign policy must bind one exact Maven distribution")

    recipe = _object(
        policy.get("rewrite_recipe_artifact"),
        "campaign policy rewrite_recipe_artifact",
    )
    _exact_fields(
        recipe,
        {
            "coordinate",
            "build_output_timestamp",
            "jar_sha256",
            "recipe_pom_sha256",
            "parent_pom_sha256",
            "files",
        },
        "campaign policy rewrite_recipe_artifact",
    )
    if recipe["coordinate"] != "io.elmos:elmos-java-recipes:0.1.0-SNAPSHOT":
        raise CampaignError("campaign policy rewrite recipe coordinate drifted")
    _instant(
        recipe["build_output_timestamp"],
        "campaign policy rewrite recipe build_output_timestamp",
    )
    for field in ("jar_sha256", "recipe_pom_sha256", "parent_pom_sha256"):
        _digest(recipe[field], f"campaign policy rewrite_recipe_artifact.{field}")
    files = recipe["files"]
    if not isinstance(files, list) or len(files) != len(RECIPE_SEED_PATHS):
        raise CampaignError("campaign policy rewrite recipe seed must contain three files")
    observed_files: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(files):
        value = _object(item, f"campaign policy rewrite recipe file {index}")
        _exact_fields(
            value,
            {"path", "bytes", "sha256"},
            f"campaign policy rewrite recipe file {index}",
        )
        path = value["path"]
        if path in observed_files or path not in RECIPE_SEED_PATHS:
            raise CampaignError("campaign policy rewrite recipe seed paths are invalid")
        if not isinstance(value["bytes"], int) or isinstance(value["bytes"], bool) or value["bytes"] <= 0:
            raise CampaignError("campaign policy rewrite recipe seed byte count is invalid")
        _digest(
            "sha256:" + str(value["sha256"]),
            f"campaign policy rewrite recipe file {path}",
        )
        expected_digest = recipe[RECIPE_SEED_PATHS[path]].removeprefix("sha256:")
        if value["sha256"] != expected_digest:
            raise CampaignError("campaign policy rewrite recipe seed digest drifted")
        observed_files[path] = value
    if set(observed_files) != set(RECIPE_SEED_PATHS):
        raise CampaignError("campaign policy rewrite recipe seed is incomplete")

    exact_path = _safe_pack_file(
        pack, binding["exact_tuple"]["path"], "campaign exact tuple"
    )
    exact, _ = _read_json(exact_path, "campaign exact tuple")
    transformation = _object(
        exact.get("transformation"), "campaign exact tuple transformation"
    )
    expected_recipe_binding = {
        "custom_recipe_coordinate": recipe["coordinate"],
        "custom_recipe_build_output_timestamp": recipe["build_output_timestamp"],
        "custom_recipe_artifact_sha256": recipe["jar_sha256"],
        "custom_recipe_pom_sha256": recipe["recipe_pom_sha256"],
        "custom_recipe_parent_pom_sha256": recipe["parent_pom_sha256"],
    }
    for field, expected in expected_recipe_binding.items():
        if transformation.get(field) != expected:
            raise CampaignError(
                f"campaign exact tuple rewrite recipe binding drifted: {field}"
            )


def validate_campaign_plan(pack_dir: Path, value: Any) -> dict[str, Any]:
    """Validate a checked-in P0-P11 plan without advancing evidence state."""

    if pack_dir.is_symlink():
        raise CampaignError("pack_dir must be a non-symlink directory")
    pack = pack_dir.resolve(strict=True)
    if not pack.is_dir():
        raise CampaignError("pack_dir must be a non-symlink directory")
    campaign = _object(value, "campaign")
    _exact_fields(
        campaign,
        {
            "schema_version",
            "campaign_id",
            "pack_key",
            "tuple_binding",
            "scope",
            "corpora",
            "rule_freeze",
            "phases",
            "required_external_evidence_types",
            "thresholds",
            "status_boundary",
        },
        "campaign",
    )
    if campaign["schema_version"] != CAMPAIGN_SCHEMA_VERSION:
        raise CampaignError("campaign schema_version is invalid")
    _identity(campaign["campaign_id"], "campaign.campaign_id")
    manifest, _ = _read_json(pack / "pack.json", "pack manifest")
    if campaign["pack_key"] != manifest.get("pack_key"):
        raise CampaignError("campaign pack_key does not match pack.json")

    binding = _object(campaign["tuple_binding"], "campaign.tuple_binding")
    _exact_fields(
        binding,
        {
            "source_commit",
            "source_snapshot_digest",
            "exact_tuple",
            "target_artifact",
            "target_profile",
            "policy",
            "version_tuple",
        },
        "campaign.tuple_binding",
    )
    if not isinstance(binding["source_commit"], str) or COMMIT.fullmatch(binding["source_commit"]) is None:
        raise CampaignError("campaign source_commit must be a full immutable Git SHA")
    _digest(binding["source_snapshot_digest"], "campaign.source_snapshot_digest")
    _validate_content_binding(
        pack, binding["target_artifact"], "campaign target artifact", require_size=True
    )
    _validate_content_binding(
        pack, binding["target_profile"], "campaign target profile", require_size=False
    )
    _validate_content_binding(
        pack, binding["policy"], "campaign policy", require_size=False
    )
    _validate_exact_tuple_contract(pack, campaign, binding)
    _validate_policy_contract(pack, campaign)

    fingerprint_evidence_path = pack / "source-fingerprint" / "evidence.json"
    fcm_path = pack / "contracts" / "framework-contract-model.json"
    for path, label in (
        (fingerprint_evidence_path, "source fingerprint evidence"),
        (fcm_path, "framework contract model"),
    ):
        observed, _ = _read_json(path, label)
        if observed.get("source_commit") != binding["source_commit"]:
            raise CampaignError(f"campaign source commit does not match {label}")
        if observed.get("source_snapshot_sha256") != binding["source_snapshot_digest"].removeprefix("sha256:"):
            raise CampaignError(f"campaign source snapshot does not match {label}")

    scope = _object(campaign["scope"], "campaign.scope")
    _exact_fields(
        scope,
        {
            "exact_tuple_only",
            "certified_capability_ids",
            "excluded_capability_ids",
            "support_matrix_subject_digest",
        },
        "campaign.scope",
    )
    if scope["exact_tuple_only"] is not True:
        raise CampaignError("campaign scope must be exact_tuple_only")
    certified = scope["certified_capability_ids"]
    excluded = scope["excluded_capability_ids"]
    if (
        not isinstance(certified, list)
        or not certified
        or not isinstance(excluded, list)
        or set(certified) & set(excluded)
    ):
        raise CampaignError("campaign capability scope is empty, overlapping, or invalid")
    support, _ = _read_json(pack / "support-matrix.json", "support matrix")
    capability_ids = {
        item.get("id")
        for item in support.get("capabilities", [])
        if isinstance(item, dict)
    }
    if set(certified) | set(excluded) != capability_ids:
        raise CampaignError("campaign capability scope must partition the support matrix")
    if scope["support_matrix_subject_digest"] != support_matrix_subject_digest(
        support, certified
    ):
        raise CampaignError("campaign support matrix certification subject drifted")

    corpora = _object(campaign["corpora"], "campaign.corpora")
    _exact_fields(corpora, set(CORPUS_ROLES), "campaign.corpora")
    resolved_corpora: dict[str, Path] = {}
    for role in CORPUS_ROLES:
        corpus = _object(corpora[role], f"campaign.corpora.{role}")
        _exact_fields(
            corpus,
            {"path", "independent", "execution_status", "authoring_allowed"},
            f"campaign.corpora.{role}",
        )
        relative = corpus["path"]
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise CampaignError(f"campaign corpus {role} path is unsafe")
        lexical_candidate = pack / relative
        current = pack
        for part in Path(relative).parts:
            current /= part
            if current.is_symlink():
                raise CampaignError(
                    f"campaign corpus {role} path must not traverse a symlink"
                )
        candidate = lexical_candidate.resolve(strict=True)
        if (
            lexical_candidate.is_symlink()
            or not candidate.is_dir()
            or not candidate.is_relative_to(pack)
        ):
            raise CampaignError(f"campaign corpus {role} path is not a pack directory")
        resolved_corpora[role] = candidate
        if role == "development":
            if corpus["independent"] is not False or corpus["authoring_allowed"] is not True:
                raise CampaignError("development corpus independence contract is invalid")
        elif corpus["independent"] is not True or corpus["authoring_allowed"] is not False:
            raise CampaignError(f"campaign corpus {role} must be independent and authoring-denied")
        if corpus["execution_status"] not in LOCAL_PHASE_STATUSES:
            raise CampaignError(f"campaign corpus {role} execution_status is invalid")
    for left_index, left in enumerate(CORPUS_ROLES):
        for right in CORPUS_ROLES[left_index + 1 :]:
            left_path = resolved_corpora[left]
            right_path = resolved_corpora[right]
            if left_path == right_path or left_path in right_path.parents or right_path in left_path.parents:
                raise CampaignError(f"campaign corpora overlap physically: {left}, {right}")

    rule_freeze = _object(campaign["rule_freeze"], "campaign.rule_freeze")
    _exact_fields(
        rule_freeze,
        {"rules", "recipe_manifest_digest", "frozen_at", "holdout_authoring_forbidden"},
        "campaign.rule_freeze",
    )
    rules = _validate_content_binding(
        pack, rule_freeze["rules"], "campaign frozen rules", require_size=False
    )
    recipe_digest, _ = _content_snapshot(
        pack / "recipes/manifest.json", "recipe manifest"
    )
    if rule_freeze["recipe_manifest_digest"] != recipe_digest:
        raise CampaignError("campaign rule freeze does not bind the recipe manifest")
    recipe_manifest, _ = _read_json(pack / "recipes/manifest.json", "recipe manifest")
    if recipe_manifest.get("recipe_config") != rule_freeze["rules"]["path"]:
        raise CampaignError("campaign frozen rules are not the recipe-manifest rule asset")
    if rules["digest"] != rule_freeze["rules"]["digest"]:
        raise CampaignError("campaign frozen rules digest drifted")
    _instant(rule_freeze["frozen_at"], "campaign.rule_freeze.frozen_at")
    if rule_freeze["holdout_authoring_forbidden"] is not True:
        raise CampaignError("campaign must forbid rule authoring from holdout cases")

    phases = campaign["phases"]
    if not isinstance(phases, list) or [item.get("id") for item in phases if isinstance(item, dict)] != list(PHASE_IDS):
        raise CampaignError("campaign phases must be exactly P0 through P11 in order")
    for phase in phases:
        _exact_fields(
            phase,
            {"id", "title", "owner_role", "required_evidence_types", "pass_criteria", "execution_status"},
            f"campaign phase {phase.get('id')}",
        )
        _identity(phase["owner_role"], f"campaign phase {phase['id']}.owner_role")
        required = phase["required_evidence_types"]
        if not isinstance(required, list) or any(name not in REQUIRED_EVIDENCE for name in required):
            raise CampaignError(f"campaign phase {phase['id']} evidence types are invalid")
        expected_phase_evidence = (
            PRE_CERTIFICATION_EVIDENCE
            if phase["id"] == "P9"
            else PHASE_EVIDENCE[phase["id"]]
        )
        if required != list(expected_phase_evidence):
            raise CampaignError(
                f"campaign phase {phase['id']} must bind its exact evidence classes"
            )
        if not isinstance(phase["pass_criteria"], list) or not phase["pass_criteria"]:
            raise CampaignError(f"campaign phase {phase['id']} pass criteria are empty")
        if phase["execution_status"] not in LOCAL_PHASE_STATUSES:
            raise CampaignError(f"campaign phase {phase['id']} execution_status is invalid")

    if campaign["required_external_evidence_types"] != list(REQUIRED_EVIDENCE):
        raise CampaignError("campaign must require the exact 13 evidence classes")
    thresholds = _object(campaign["thresholds"], "campaign.thresholds")
    expected_thresholds = {
        "source_fingerprint_coverage": 1.0,
        "framework_contract_coverage": 1.0,
        "build_green_rate": 1.0,
        "startup_pass_rate": 1.0,
        "p0_contract_pass_rate": 1.0,
        "source_map_coverage": 1.0,
        "route_coverage": 1.0,
        "critical_unknowns": 0,
        "silent_framework_drops": 0,
        "critical_security_regressions": 0,
        "critical_transaction_regressions": 0,
        "critical_data_regressions": 0,
        "duplicate_message_or_job_effects": 0,
        "test_integrity_violations": 0,
        "skipped_tests": 0,
        "flaky_tests": 0,
        "waivers": 0,
        "minimum_source_builds": 2,
        "minimum_target_builds": 2,
        "minimum_startup_attempts": 2,
        "minimum_security_scanners": 3,
        "minimum_performance_requests": 10000,
        "minimum_performance_soak_seconds": 3600,
        "performance_slo_p95_ms": 100.0,
        "performance_slo_throughput_rps": 400.0,
        "minimum_rollback_attempts": 3,
        "rollback_rto_objective_seconds": 60.0,
    }
    if thresholds != expected_thresholds:
        raise CampaignError("campaign thresholds must encode the exact 100%/zero-tolerance policy")
    boundary = _object(campaign["status_boundary"], "campaign.status_boundary")
    if boundary != {
        "external_evidence": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "local_runner_may_certify": False,
        "promotion_requires_reverification": True,
    }:
        raise CampaignError("campaign status boundary is not fail-closed")
    return campaign


def _validate_environment(
    value: Any,
    *,
    campaign: dict[str, Any],
    intake_result: dict[str, Any],
    expected_toolchain_digests: dict[str, str],
    label: str,
) -> dict[str, Any]:
    environment = _object(value, label)
    _exact_fields(
        environment,
        {
            "environment_id",
            "isolation",
            "source_commit",
            "source_snapshot_digest",
            "target_artifact_digest",
            "target_profile_digest",
            "policy_digest",
            "version_tuple",
            "toolchains",
        },
        label,
    )
    _identity(environment["environment_id"], f"{label}.environment_id")
    if environment["isolation"] != "AUTHORIZED_ISOLATED":
        raise CampaignError(f"{label}.isolation must be AUTHORIZED_ISOLATED")
    binding = campaign["tuple_binding"]
    expected = {
        "source_commit": binding["source_commit"],
        "source_snapshot_digest": binding["source_snapshot_digest"],
        "target_artifact_digest": intake_result["verified_content_digests"]["artifact"],
        "target_profile_digest": binding["target_profile"]["digest"],
        "policy_digest": binding["policy"]["digest"],
    }
    for field, expected_value in expected.items():
        if environment[field] != expected_value:
            raise CampaignError(f"{label}.{field} does not match the exact campaign binding")
    if environment["version_tuple"] != binding["version_tuple"]:
        raise CampaignError(f"{label}.version_tuple does not match the exact campaign tuple")
    toolchains = environment["toolchains"]
    if not isinstance(toolchains, list) or len(toolchains) != len(BASE_TOOLCHAINS):
        raise CampaignError(f"{label}.toolchains must contain the exact source/target toolchain set")
    names: set[str] = set()
    observed_tools: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(toolchains):
        tool = _object(item, f"{label}.toolchains[{index}]")
        _exact_fields(tool, {"name", "version", "digest"}, f"{label}.toolchains[{index}]")
        name = _identity(tool["name"], f"{label}.toolchains[{index}].name")
        if name in names or "latest" in str(tool["version"]).lower():
            raise CampaignError(f"{label}.toolchains must use unique exact versions")
        names.add(name)
        _identity(tool["version"], f"{label}.toolchains[{index}].version")
        _digest(tool["digest"], f"{label}.toolchains[{index}].digest")
        observed_tools[name] = tool
    if set(observed_tools) != set(BASE_TOOLCHAINS):
        raise CampaignError(f"{label}.toolchains names do not match the exact required set")
    for name, (side, field) in BASE_TOOLCHAINS.items():
        if observed_tools[name]["version"] != binding["version_tuple"][side][field]:
            raise CampaignError(f"{label}.toolchains version drifted: {name}")
        if observed_tools[name]["digest"] != expected_toolchain_digests[name]:
            raise CampaignError(f"{label}.toolchains digest drifted: {name}")
    return environment


def _require_all_zero(metrics: dict[str, Any], names: Iterable[str], label: str) -> None:
    for name in names:
        if metrics.get(name) != 0:
            raise CampaignError(f"{label}.{name} must be zero")


def _validate_type_metrics(
    evidence_type: str,
    metrics: dict[str, Any],
    *,
    campaign: dict[str, Any],
    intake: dict[str, Any],
    intake_result: dict[str, Any],
    now: datetime,
) -> None:
    label = f"evidence.{evidence_type}.metrics"
    _exact_fields(metrics, METRIC_FIELDS[evidence_type], label)
    if evidence_type in {"source_build", "target_build"}:
        for name in ("builds_total", "builds_passed", "tests_total"):
            _integer(metrics.get(name), f"{label}.{name}", minimum=1)
        if metrics["builds_passed"] != metrics["builds_total"]:
            raise CampaignError(f"{label} build pass rate must be 100%")
        minimum_builds = campaign["thresholds"][
            "minimum_source_builds"
            if evidence_type == "source_build"
            else "minimum_target_builds"
        ]
        if metrics["builds_total"] < minimum_builds:
            raise CampaignError(f"{label} does not meet the minimum repeat count")
        _require_all_zero(metrics, ("failures", "errors", "skipped"), label)
        if metrics.get("native") is not True or metrics.get("exact_toolchain") is not True:
            raise CampaignError(f"{label} must record native exact-toolchain execution")
        if evidence_type == "target_build":
            if metrics.get("artifact_digest") != intake_result["verified_content_digests"]["artifact"]:
                raise CampaignError(f"{label}.artifact_digest is not the certified target")
            if metrics.get("rootless") is not True or metrics.get("privileged") is not False:
                raise CampaignError(f"{label} target build must be rootless and unprivileged")
    elif evidence_type in {"source_startup", "target_startup"}:
        for name in ("startup_attempts", "startup_passed", "readiness_probes", "readiness_passed", "shutdown_attempts", "shutdown_passed"):
            _integer(metrics.get(name), f"{label}.{name}", minimum=1)
        if any(
            metrics[passed] != metrics[total]
            for total, passed in (
                ("startup_attempts", "startup_passed"),
                ("readiness_probes", "readiness_passed"),
                ("shutdown_attempts", "shutdown_passed"),
            )
        ):
            raise CampaignError(f"{label} startup/readiness/shutdown must pass 100%")
        if metrics["startup_attempts"] < campaign["thresholds"]["minimum_startup_attempts"]:
            raise CampaignError(f"{label} does not meet the minimum startup repeat count")
        _number(metrics.get("startup_seconds"), f"{label}.startup_seconds")
        _number(metrics.get("shutdown_seconds"), f"{label}.shutdown_seconds")
        if metrics.get("native") is not True:
            raise CampaignError(f"{label}.native must be true")
        if evidence_type == "target_startup" and (
            metrics.get("rootless") is not True
            or metrics.get("privileged") is not False
            or _integer(metrics.get("effective_uid"), f"{label}.effective_uid") == 0
        ):
            raise CampaignError(f"{label} target startup must be rootless with non-zero UID")
    elif evidence_type == "behavioral_equivalence":
        for name in (
            "routes_total",
            "routes_passed",
            "p0_contracts_total",
            "p0_contracts_passed",
            "holdout_projects",
            "representative_projects",
            "customer_projects",
        ):
            _integer(metrics.get(name), f"{label}.{name}", minimum=1)
        if metrics["routes_passed"] != metrics["routes_total"] or metrics["p0_contracts_passed"] != metrics["p0_contracts_total"]:
            raise CampaignError(f"{label} route and P0 pass rates must be 100%")
        for name in (
            "route_coverage",
            "source_fingerprint_coverage",
            "framework_contract_coverage",
            "source_map_coverage",
        ):
            if _number(metrics.get(name), f"{label}.{name}") != 1.0:
                raise CampaignError(f"{label}.{name} must be 1.0")
        _require_all_zero(
            metrics,
            (
                "critical_mismatch_count",
                "silent_framework_drops",
                "critical_transaction_regressions",
                "critical_data_regressions",
                "duplicate_message_or_job_effects",
                "test_integrity_violations",
            ),
            label,
        )
        if metrics.get("rules_frozen_before_holdout") is not True:
            raise CampaignError(f"{label} must prove rule freeze before holdout execution")
        if metrics.get("rules_digest") != campaign["rule_freeze"]["rules"]["digest"]:
            raise CampaignError(f"{label}.rules_digest does not match the frozen rules")
        corpus_digests = _object(metrics.get("corpus_digests"), f"{label}.corpus_digests")
        _exact_fields(corpus_digests, set(CORPUS_ROLES), f"{label}.corpus_digests")
        values = [_digest(corpus_digests[role], f"{label}.corpus_digests.{role}") for role in CORPUS_ROLES]
        if len(set(values)) != len(values):
            raise CampaignError(f"{label} corpora must bind distinct bytes")
        project_outcomes = _object(
            metrics.get("project_outcome_evidence_digests"),
            f"{label}.project_outcome_evidence_digests",
        )
        _exact_fields(
            project_outcomes,
            set(EXTERNAL_CORPUS_ROLES),
            f"{label}.project_outcome_evidence_digests",
        )
        outcome_digests = [
            _digest(
                project_outcomes[role],
                f"{label}.project_outcome_evidence_digests.{role}",
            )
            for role in EXTERNAL_CORPUS_ROLES
        ]
        if len(set(outcome_digests)) != len(outcome_digests):
            raise CampaignError(f"{label} project outcome evidence must be content-distinct")
    elif evidence_type == "security":
        scanners = metrics.get("scanners")
        if (
            not isinstance(scanners, list)
            or len(scanners) < campaign["thresholds"]["minimum_security_scanners"]
            or len(scanners) != len(set(scanners))
            or any(not isinstance(scanner, str) or not scanner for scanner in scanners)
        ):
            raise CampaignError(f"{label}.scanners do not meet the fixed scanner threshold")
        _require_all_zero(
            metrics,
            (
                "critical_findings",
                "high_findings",
                "authentication_regressions",
                "authorization_regressions",
                "critical_dependency_vulnerabilities",
                "critical_data_exposure_findings",
            ),
            label,
        )
    elif evidence_type == "performance":
        if metrics.get("capacity_validated") is not True:
            raise CampaignError(f"{label}.capacity_validated must be true")
        requests = _integer(metrics.get("request_count"), f"{label}.request_count", minimum=1)
        if requests < campaign["thresholds"]["minimum_performance_requests"]:
            raise CampaignError(f"{label}.request_count is below the campaign minimum")
        _require_all_zero(metrics, ("error_count",), label)
        p95 = _number(metrics.get("p95_ms"), f"{label}.p95_ms")
        slo_p95 = _number(metrics.get("slo_p95_ms"), f"{label}.slo_p95_ms", minimum=0.001)
        throughput = _number(metrics.get("throughput_rps"), f"{label}.throughput_rps", minimum=0.001)
        slo_throughput = _number(metrics.get("slo_throughput_rps"), f"{label}.slo_throughput_rps", minimum=0.001)
        soak_seconds = _integer(metrics.get("soak_seconds"), f"{label}.soak_seconds", minimum=1)
        if (
            slo_p95 != campaign["thresholds"]["performance_slo_p95_ms"]
            or slo_throughput
            != campaign["thresholds"]["performance_slo_throughput_rps"]
        ):
            raise CampaignError(f"{label} performance SLO drifted from the campaign")
        if soak_seconds < campaign["thresholds"]["minimum_performance_soak_seconds"]:
            raise CampaignError(f"{label}.soak_seconds is below the campaign minimum")
        if p95 > slo_p95 or throughput < slo_throughput:
            raise CampaignError(f"{label} does not satisfy the bound performance SLO")
    elif evidence_type == "operability":
        if metrics.get("endpoints_verified") != ["/livez", "/readyz", "/metrics", "/version"]:
            raise CampaignError(f"{label}.endpoints_verified is incomplete")
        _require_all_zero(metrics, ("failed_probes", "alert_failures", "runbook_failures"), label)
        if metrics.get("trace_correlation_verified") is not True:
            raise CampaignError(f"{label}.trace_correlation_verified must be true")
    elif evidence_type == "sbom":
        if metrics.get("artifact_digest") != intake_result["verified_content_digests"]["artifact"]:
            raise CampaignError(f"{label}.artifact_digest is not the certified target")
        if metrics.get("format") not in {"CycloneDX-1.5", "SPDX-2.3"}:
            raise CampaignError(f"{label}.format is unsupported")
        _integer(metrics.get("component_count"), f"{label}.component_count", minimum=1)
        _require_all_zero(metrics, ("unknown_licenses", "critical_vulnerabilities"), label)
        if metrics.get("artifact_bound") is not True:
            raise CampaignError(f"{label}.artifact_bound must be true")
    elif evidence_type == "rollback":
        if metrics.get("rehearsed") is not True:
            raise CampaignError(f"{label}.rehearsed must be true")
        attempts = _integer(metrics.get("attempts"), f"{label}.attempts", minimum=1)
        passed = _integer(metrics.get("passed"), f"{label}.passed", minimum=1)
        if attempts != passed:
            raise CampaignError(f"{label} rollback pass rate must be 100%")
        if attempts < campaign["thresholds"]["minimum_rollback_attempts"]:
            raise CampaignError(f"{label} does not meet the minimum rollback repeat count")
        actual_rto = _number(metrics.get("actual_rto_seconds"), f"{label}.actual_rto_seconds")
        objective = _number(metrics.get("rto_objective_seconds"), f"{label}.rto_objective_seconds", minimum=0.001)
        if objective != campaign["thresholds"]["rollback_rto_objective_seconds"]:
            raise CampaignError(f"{label} rollback RTO objective drifted from the campaign")
        _require_all_zero(metrics, ("data_loss_records", "orphan_effects"), label)
        if actual_rto > objective:
            raise CampaignError(f"{label} exceeds the rollback RTO objective")
    elif evidence_type == "independent_review":
        if metrics.get("organizationally_independent") is not True:
            raise CampaignError(f"{label}.organizationally_independent must be true")
        if metrics.get("reviewed_evidence_types") != list(TECHNICAL_EVIDENCE):
            raise CampaignError(f"{label}.reviewed_evidence_types is incomplete")
        reviewed = _object(metrics.get("reviewed_content_digests"), f"{label}.reviewed_content_digests")
        _exact_fields(reviewed, set(TECHNICAL_EVIDENCE), f"{label}.reviewed_content_digests")
        for name in TECHNICAL_EVIDENCE:
            if reviewed[name] != intake_result["verified_content_digests"][name]:
                raise CampaignError(f"{label} reviewed digest mismatch: {name}")
        _require_all_zero(metrics, ("critical_findings", "unresolved_findings"), label)
    elif evidence_type == "customer_acceptance":
        total = _integer(metrics.get("scenarios_total"), f"{label}.scenarios_total", minimum=1)
        passed = _integer(metrics.get("scenarios_passed"), f"{label}.scenarios_passed", minimum=1)
        if total != passed:
            raise CampaignError(f"{label} customer scenario pass rate must be 100%")
        if (
            metrics.get("accepted_artifact_digest") != intake_result["verified_content_digests"]["artifact"]
            or metrics.get("accepted_execution_profile_digest") != intake_result["verified_content_digests"]["execution_profile"]
            or metrics.get("customer_owned_holdout") is not True
        ):
            raise CampaignError(f"{label} acceptance subject binding is invalid")
        _require_all_zero(metrics, ("unresolved_findings",), label)
    elif evidence_type == "external_certification":
        if metrics.get("decision") != "CERTIFIED" or metrics.get("scope_bound") is not True:
            raise CampaignError(f"{label} decision or scope binding is invalid")
        if metrics.get("certified_capability_ids") != campaign["scope"]["certified_capability_ids"]:
            raise CampaignError(f"{label} certified capability scope drifted")
        if metrics.get("reviewed_evidence_types") != list(PRE_CERTIFICATION_EVIDENCE):
            raise CampaignError(f"{label}.reviewed_evidence_types is incomplete")
        reviewed = _object(metrics.get("reviewed_content_digests"), f"{label}.reviewed_content_digests")
        _exact_fields(reviewed, set(PRE_CERTIFICATION_EVIDENCE), f"{label}.reviewed_content_digests")
        for name in PRE_CERTIFICATION_EVIDENCE:
            if reviewed[name] != intake_result["verified_content_digests"][name]:
                raise CampaignError(f"{label} reviewed digest mismatch: {name}")
        if _instant(metrics.get("certificate_valid_until"), f"{label}.certificate_valid_until") <= now:
            raise CampaignError(f"{label} certificate is expired")
        _number(metrics.get("manual_hours"), f"{label}.manual_hours")
        _number(metrics.get("cost_per_verified_workload"), f"{label}.cost_per_verified_workload")


def _validate_evidence_document(
    evidence_type: str,
    value: Any,
    *,
    campaign: dict[str, Any],
    campaign_digest: str,
    intake: dict[str, Any],
    intake_result: dict[str, Any],
    expected_toolchain_digests: dict[str, str],
    roots: tuple[Path, ...],
    raw_digests: set[str],
    now: datetime,
) -> dict[str, Any]:
    document = _object(value, f"evidence.{evidence_type}.document")
    _exact_fields(document, COMMON_EVIDENCE_FIELDS, f"evidence.{evidence_type}.document")
    if document["schema_version"] != EVIDENCE_SCHEMA_VERSION or document["evidence_type"] != evidence_type:
        raise CampaignError(f"evidence.{evidence_type} document identity is invalid")
    if document["campaign_digest"] != campaign_digest:
        raise CampaignError(f"evidence.{evidence_type} document campaign digest drifted")
    if document["binding_digest"] != intake_result["binding_digest"]:
        raise CampaignError(f"evidence.{evidence_type} document binding digest drifted")
    _identity(document["execution_id"], f"evidence.{evidence_type}.execution_id")
    executed_at = _instant(document["executed_at"], f"evidence.{evidence_type}.executed_at")
    if executed_at > now:
        raise CampaignError(f"evidence.{evidence_type}.executed_at is in the future")
    expected_executor = intake["evidence_executors"][evidence_type]
    if document["executor_actor_id"] != expected_executor["actor_id"] or document["executor_organization_id"] != expected_executor["organization_id"]:
        raise CampaignError(f"evidence.{evidence_type} document executor binding drifted")
    if document["result"] != EXPECTED_RESULTS[evidence_type]:
        raise CampaignError(f"evidence.{evidence_type} document result is not admissible")
    authorization = intake["customer_authorization"]["payload"]
    attestation = intake["evidence"][evidence_type]["attestation"]["payload"]
    authorization_issued = _instant(
        authorization["issued_at"], "customer authorization issued_at"
    )
    authorization_expires = _instant(
        authorization["expires_at"], "customer authorization expires_at"
    )
    attestation_issued = _instant(
        attestation["issued_at"], f"evidence.{evidence_type} attestation issued_at"
    )
    if not (authorization_issued <= executed_at <= authorization_expires):
        raise CampaignError(f"evidence.{evidence_type} execution is outside customer authorization")
    if attestation_issued < executed_at:
        raise CampaignError(f"evidence.{evidence_type} was signed before it was executed")
    _validate_environment(
        document["environment"],
        campaign=campaign,
        intake_result=intake_result,
        expected_toolchain_digests=expected_toolchain_digests,
        label=f"evidence.{evidence_type}.environment",
    )
    if document["unknowns"] != [] or document["not_run"] != [] or document["waivers"] != []:
        raise CampaignError(f"evidence.{evidence_type} contains unknown, not-run, or waived work")
    integrity = _object(document["test_integrity"], f"evidence.{evidence_type}.test_integrity")
    if integrity != {"skipped": 0, "flaky": 0, "weakened": 0, "synthetic": False}:
        raise CampaignError(f"evidence.{evidence_type} test integrity is not zero-tolerance")
    raw = document["raw_evidence"]
    if not isinstance(raw, list) or not raw:
        raise CampaignError(f"evidence.{evidence_type}.raw_evidence must be non-empty")
    observed_raw_digests: set[str] = set()
    for index, reference in enumerate(raw):
        try:
            observed = _verify_reference(reference, roots, f"evidence.{evidence_type}.raw_evidence[{index}]")
        except ExternalIntakeError as exc:
            raise CampaignError(str(exc)) from exc
        if observed["digest"] in raw_digests:
            raise CampaignError("raw evidence objects must be content-distinct across all 13 classes")
        raw_digests.add(observed["digest"])
        observed_raw_digests.add(observed["digest"])
        path = Path(observed["resolved_path"])
        if path.stat().st_size > MAX_RAW_EVIDENCE_BYTES:
            raise CampaignError(f"evidence.{evidence_type} raw evidence exceeds the byte budget")
    metrics = _object(document["metrics"], f"evidence.{evidence_type}.metrics")
    _validate_type_metrics(
        evidence_type,
        metrics,
        campaign=campaign,
        intake=intake,
        intake_result=intake_result,
        now=now,
    )
    if evidence_type == "behavioral_equivalence":
        required_behavior_digests = {
            *metrics["corpus_digests"].values(),
            *metrics["project_outcome_evidence_digests"].values(),
        }
        if not required_behavior_digests <= observed_raw_digests:
            raise CampaignError(
                "behavioral equivalence corpus and project outcome digests must reference raw evidence bytes"
            )
    return document


def evaluate_certification_campaign(
    *,
    pack_dir: Path,
    campaign_path: Path,
    intake_path: Path | None = None,
    trust_store: Path | None = None,
    evidence_roots: Iterable[Path] = (),
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate P0-P11 and return a non-mutating certification-gate input."""

    campaign_raw, campaign_bytes = _read_json(campaign_path, "certification campaign")
    campaign = validate_campaign_plan(pack_dir, campaign_raw)
    campaign_digest = "sha256:" + hashlib.sha256(campaign_bytes).hexdigest()
    if intake_path is None:
        return {
            "schema_version": CAMPAIGN_SCHEMA_VERSION,
            "campaign_id": campaign["campaign_id"],
            "pack_key": campaign["pack_key"],
            "campaign_digest": campaign_digest,
            "support_matrix_subject_digest": campaign["scope"]["support_matrix_subject_digest"],
            "decision": "BLOCKED_EXTERNAL_EVIDENCE_REQUIRED",
            "external_evidence_status": "NOT_RUN",
            "production_certification": "NOT_CERTIFIED",
            "required_evidence_types": list(REQUIRED_EVIDENCE),
            "verified_evidence_types": [],
            "phase_results": {
                phase["id"]: phase["execution_status"] for phase in campaign["phases"]
            },
        }
    if trust_store is None:
        raise CampaignError("a submitted intake requires an explicit trust store")
    policy_path = _safe_pack_file(
        pack_dir.resolve(strict=True),
        campaign["tuple_binding"]["policy"]["path"],
        "campaign policy",
    )
    policy, _ = _read_json(policy_path, "campaign policy")
    expected_toolchain_digests = _object(
        policy.get("toolchain_bindings"), "campaign policy toolchain_bindings"
    )
    roots = _approved_roots(evidence_roots)
    observed_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        intake_result = evaluate_external_intake_file(
            intake_path,
            pack_dir=pack_dir,
            trust_store=trust_store,
            evidence_roots=roots,
            now=observed_now,
        )
    except (ExternalIntakeError, OSError, ValueError) as exc:
        raise CampaignError(f"external intake verification failed: {exc}") from exc
    if intake_result.get("verified_evidence_types") != list(REQUIRED_EVIDENCE):
        raise CampaignError("external intake did not verify all 13 evidence classes")
    intake, intake_bytes = _read_json(intake_path, "external intake")
    if "sha256:" + hashlib.sha256(intake_bytes).hexdigest() != intake_result["intake_content_digest"]:
        raise CampaignError("external intake changed after signature verification")
    intake_binding = _object(intake.get("binding"), "external intake binding")
    tuple_binding = campaign["tuple_binding"]
    expected_intake_bindings = {
        "pack_key": campaign["pack_key"],
        "artifact_digest": tuple_binding["target_artifact"]["digest"],
        "artifact_size_bytes": tuple_binding["target_artifact"]["size_bytes"],
        "target_profile_digest": tuple_binding["target_profile"]["digest"],
        "recipe_manifest_digest": campaign["rule_freeze"]["recipe_manifest_digest"],
    }
    for field, expected in expected_intake_bindings.items():
        if intake_binding.get(field) != expected:
            raise CampaignError(f"external intake binding drifted from campaign: {field}")

    documents: dict[str, dict[str, Any]] = {}
    raw_digests = set(intake_result["verified_content_digests"].values())
    for evidence_type in REQUIRED_EVIDENCE:
        reference = intake["evidence"][evidence_type]["content"]
        try:
            observation = _verify_reference(reference, roots, f"evidence.{evidence_type}.content")
        except ExternalIntakeError as exc:
            raise CampaignError(str(exc)) from exc
        raw = read_regular_file_once(
            Path(observation["resolved_path"]),
            max_bytes=MAX_JSON_BYTES,
            label=f"evidence.{evidence_type}.content",
        )
        if (
            "sha256:" + hashlib.sha256(raw).hexdigest() != observation["digest"]
            or len(raw) != observation["size_bytes"]
        ):
            raise CampaignError(f"evidence.{evidence_type} content changed after verification")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CampaignError(f"evidence.{evidence_type} content must be UTF-8 JSON") from exc
        documents[evidence_type] = _validate_evidence_document(
            evidence_type,
            value,
            campaign=campaign,
            campaign_digest=campaign_digest,
            intake=intake,
            intake_result=intake_result,
            expected_toolchain_digests=expected_toolchain_digests,
            roots=roots,
            raw_digests=raw_digests,
            now=observed_now,
        )

    execution_ids = [documents[name]["execution_id"] for name in REQUIRED_EVIDENCE]
    if len(execution_ids) != len(set(execution_ids)):
        raise CampaignError("all 13 evidence classes require distinct execution identities")
    expected_toolchains = {
        item["name"]: {"version": item["version"], "digest": item["digest"]}
        for item in documents["source_build"]["environment"]["toolchains"]
    }
    for evidence_type in REQUIRED_EVIDENCE[1:]:
        observed_toolchains = {
            item["name"]: {"version": item["version"], "digest": item["digest"]}
            for item in documents[evidence_type]["environment"]["toolchains"]
        }
        if observed_toolchains != expected_toolchains:
            raise CampaignError(
                f"evidence.{evidence_type}.environment.toolchains drifted across the campaign"
            )
    executed = {
        name: _instant(documents[name]["executed_at"], f"evidence.{name}.executed_at")
        for name in REQUIRED_EVIDENCE
    }
    if executed["source_startup"] < executed["source_build"]:
        raise CampaignError("source startup predates source build completion")
    if executed["target_startup"] < executed["target_build"]:
        raise CampaignError("target startup predates target build completion")
    if executed["behavioral_equivalence"] < max(
        executed[name]
        for name in ("source_build", "target_build", "source_startup", "target_startup")
    ):
        raise CampaignError("behavioral equivalence predates build and runtime completion")
    if _instant(
        campaign["rule_freeze"]["frozen_at"], "campaign.rule_freeze.frozen_at"
    ) >= executed["behavioral_equivalence"]:
        raise CampaignError("behavioral equivalence did not execute after the rule freeze")
    for evidence_type in ("security", "performance", "operability", "sbom", "rollback"):
        if executed[evidence_type] < executed["target_startup"]:
            raise CampaignError(
                f"{evidence_type} qualification predates target runtime completion"
            )
    if executed["independent_review"] < max(executed[name] for name in TECHNICAL_EVIDENCE):
        raise CampaignError("independent review predates technical evidence completion")
    if executed["customer_acceptance"] < executed["behavioral_equivalence"]:
        raise CampaignError("customer acceptance predates behavioral equivalence")
    if executed["external_certification"] < max(
        executed[name] for name in PRE_CERTIFICATION_EVIDENCE
    ):
        raise CampaignError("external certification predates required evidence completion")

    behavior = documents["behavioral_equivalence"]["metrics"]
    external_certificate = documents["external_certification"]["metrics"]
    normalized_metrics = {
        "source_fingerprint_coverage": behavior["source_fingerprint_coverage"],
        "framework_contract_coverage": behavior["framework_contract_coverage"],
        "build_green_rate": 1.0,
        "startup_pass_rate": 1.0,
        "p0_contract_pass_rate": 1.0,
        "source_map_coverage": behavior["source_map_coverage"],
        "manual_hours": external_certificate["manual_hours"],
        "cost_per_verified_workload": external_certificate["cost_per_verified_workload"],
    }
    zero_tolerance = {
        "critical_unknowns": 0,
        "silent_framework_drops": 0,
        "critical_security_regressions": 0,
        "critical_transaction_regressions": 0,
        "critical_data_regressions": 0,
        "duplicate_message_or_job_effects": 0,
        "test_integrity_violations": 0,
    }
    gate_results = {
        "negative_corpus": "PASSED",
        "holdout": "PASSED",
        "representative_repository": "PASSED",
        **intake_result["certification_gate_results"],
    }
    return {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "campaign_id": campaign["campaign_id"],
        "pack_key": campaign["pack_key"],
        "campaign_digest": campaign_digest,
        "support_matrix_subject_digest": campaign["scope"]["support_matrix_subject_digest"],
        "intake_id": intake_result["intake_id"],
        "intake_content_digest": intake_result["intake_content_digest"],
        "binding_digest": intake_result["binding_digest"],
        "trust_store_digest": intake_result["trust_store_digest"],
        "verified_evidence_types": list(REQUIRED_EVIDENCE),
        "verified_content_digests": intake_result["verified_content_digests"],
        "certified_capability_ids": campaign["scope"]["certified_capability_ids"],
        "metrics": normalized_metrics,
        "zero_tolerance": zero_tolerance,
        "gate_results": gate_results,
        "phase_results": {phase: "PASSED" for phase in PHASE_IDS},
        "decision": "READY_FOR_BATCH30_CERTIFICATION_GATE",
        "external_evidence_status": "PASSED",
        "production_certification": "PENDING_BATCH30_GATE",
        "pack_status_mutated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack_dir", type=Path)
    parser.add_argument(
        "--campaign",
        type=Path,
        help="Defaults to <pack>/certification/p0-p11-campaign.json",
    )
    parser.add_argument("--intake", type=Path)
    parser.add_argument("--trust-store", type=Path)
    parser.add_argument("--evidence-root", action="append", type=Path, default=[])
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    campaign = args.campaign or args.pack_dir / "certification/p0-p11-campaign.json"
    try:
        result = evaluate_certification_campaign(
            pack_dir=args.pack_dir,
            campaign_path=campaign,
            intake_path=None if args.plan_only else args.intake,
            trust_store=args.trust_store,
            evidence_roots=args.evidence_root,
        )
    except (CampaignError, ExternalIntakeError, OSError, ValueError) as exc:
        print(f"CAMPAIGN FAIL: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.plan_only:
        return 0
    return 0 if result["decision"] == "READY_FOR_BATCH30_CERTIFICATION_GATE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
