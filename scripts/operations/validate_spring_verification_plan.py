#!/usr/bin/env python3
"""Validate the evidence-preparation contract for the Spring Boot 4.1.1 Pack.

The plan is deliberately not an execution receipt. It binds every required
runtime/holdout/provider track to the exact target tuple while requiring all
execution, authorization, and independent-verifier states to remain NOT_RUN
until real evidence is supplied through the appropriate workflow.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PACK_KEY = "spring-to-boot-4-1-1"
PLAN_RELATIVE = Path("verification/validation-plan.json")
TRACK_CONTRACT_RELATIVE = Path("verification/track-contract.json")
FEATURE_MATRIX_RELATIVE = Path("target-profile/feature-matrix.json")
PROFILE_RELATIVE = Path("target-profile/profile.json")
VERSION_MATRIX_RELATIVE = Path("version-matrix.json")
EVIDENCE_RELATIVE = Path("certification/evidence.json")
CERTIFICATION_RELATIVE = Path("certification/certification.json")
ROUTE_CATALOG = ROOT / "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringRouteCatalog.java"

TRACK_IDS = (
    "source-build",
    "target-build",
    "source-startup",
    "target-startup",
    "component-contracts",
    "provider-behavior",
    "holdout",
    "representative-repository",
    "independent-verification",
)

TRACK_EVIDENCE_FIELDS = {
    "source-build": ("source_build",),
    "target-build": ("target_build",),
    "source-startup": ("source_startup",),
    "target-startup": ("target_startup",),
    "component-contracts": ("development_contracts", "component_contracts"),
    "provider-behavior": ("provider_behavior",),
    "holdout": ("independent_holdout",),
    "representative-repository": ("representative_repository",),
    "independent-verification": ("independent_verification",),
}

REQUIRED_PROVIDER_FEATURES = {
    "boot-grpc",
    "boot-actuator",
    "boot-observability",
    "web-graphql",
    "web-hateoas",
    "data-jpa",
    "data-jdbc",
    "data-r2dbc",
    "data-redis",
    "data-document",
    "transactions",
    "messaging-kafka",
    "messaging-amqp",
    "messaging-jms",
    "messaging-integration",
    "messaging-batch",
    "integration-ldap-session",
    "cache",
    "scheduler",
    "security-web",
    "security-method-oauth2",
}

DECLARATIVE_PROTOCOL = "DECLARATIVE_PROTOCOL_NOT_EXECUTABLE"
FAILURE_POLICY = "FAIL_CLOSED"
PLACEHOLDER = re.compile(r"<[^>]*>|\$\{[^}]+\}")
EXPECTED_PROVIDER_DOMAINS = {
    "security": {
        "feature_ids": ["security-web", "security-method-oauth2"],
        "target_profile_keys": ["spring_security"],
        "unresolved_provider_profiles": [],
        "required_evidence_roles": [
            "source-security-profile",
            "target-security-profile",
            "security-oracle",
            "negative-path-results",
        ],
    },
    "database": {
        "feature_ids": ["data-jpa", "data-jdbc", "data-r2dbc", "data-redis", "data-document"],
        "target_profile_keys": ["persistence"],
        "unresolved_provider_profiles": [
            "spring-jdbc",
            "spring-r2dbc",
            "spring-data-redis",
            "spring-data-document",
        ],
        "required_evidence_roles": [
            "source-database-profile",
            "target-database-profile",
            "data-reconciliation",
            "query-oracle",
        ],
    },
    "transaction": {
        "feature_ids": ["transactions"],
        "target_profile_keys": ["persistence"],
        "unresolved_provider_profiles": [],
        "required_evidence_roles": [
            "transaction-schedule",
            "isolation-lock-oracle",
            "rollback-results",
            "duplicate-side-effect-results",
        ],
    },
    "messaging": {
        "feature_ids": [
            "messaging-kafka",
            "messaging-amqp",
            "messaging-jms",
            "messaging-integration",
            "messaging-batch",
        ],
        "target_profile_keys": ["spring_kafka", "spring_amqp", "spring_integration"],
        "unresolved_provider_profiles": ["spring-jms", "spring-batch"],
        "required_evidence_roles": [
            "source-message-profile",
            "target-message-profile",
            "delivery-oracle",
            "duplicate-loss-results",
        ],
    },
    "provider": {
        "feature_ids": [
            "boot-grpc",
            "boot-actuator",
            "boot-observability",
            "web-graphql",
            "web-hateoas",
            "integration-ldap-session",
            "cache",
            "scheduler",
        ],
        "target_profile_keys": [
            "grpc",
            "observability",
            "spring_graphql",
            "spring_hateoas",
            "spring_ldap",
            "spring_session",
        ],
        "unresolved_provider_profiles": [],
        "required_evidence_roles": [
            "provider-version-lock",
            "provider-runtime-log",
            "provider-oracle",
            "negative-path-results",
        ],
    },
}

EXPECTED_TRACK_ROUTE_BINDINGS = {
    "source-build": "version-matrix.json#tuples[*]",
    "target-build": "version-matrix.json#tuples[*]",
    "source-startup": "version-matrix.json#tuples[*]",
    "target-startup": "version-matrix.json#tuples[*]",
    "component-contracts": "version-matrix.json#tuples[*]",
    "provider-behavior": "version-matrix.json#tuples[*]",
    "holdout": "version-matrix.json#tuples[*]",
    "representative-repository": "version-matrix.json#tuples[*]",
    "independent-verification": "track-contract.tracks[0..7]",
}
EXPECTED_PROTOCOL_MARKERS = {
    "source-build": (
        "source_fingerprint=source-fingerprint/manifest.json",
        "exact_source_version=required",
        "build_tool=tuple.build",
    ),
    "target-build": (
        "recipe=tuple.recipe",
        "target_profile=target-profile/profile.json",
        "target_spring_boot=4.1.1",
        "target_java=21",
        "build_tool=tuple.build",
    ),
    "source-startup": (
        "artifact_role=source-build-artifact",
        "source_fingerprint=source-fingerprint/manifest.json",
        "bind=exact_source_tuple",
        "probes=health,shutdown",
    ),
    "target-startup": (
        "artifact_role=target-build-artifact",
        "target_profile=target-profile/profile.json#startup",
        "probes=health,shutdown",
    ),
    "component-contracts": (
        "fcm=contracts/framework-contract-model.json",
        "feature_matrix=target-profile/feature-matrix.json",
        "compare=source,target",
    ),
    "provider-behavior": (
        "target_profile=target-profile/profile.json#providers",
        "provider_lock=target-profile/dependency-locks/spring-boot-4.1.1.properties",
        "domains=security,database,transaction,messaging,provider",
        "isolation=required",
    ),
    "holdout": (
        "corpus=corpus/holdout",
        "source_target=required",
        "mapping_authoring=false",
        "isolation=required",
    ),
    "representative-repository": (
        "corpus=corpus/real-repository",
        "authorization=required",
        "source_target_build_startup=required",
        "isolation=required",
    ),
    "independent-verification": (
        "input=content-addressed-evidence",
        "verifier=separate",
        "output=certification/independent-verification",
    ),
}


def has_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return PLACEHOLDER.search(value) is not None
    if isinstance(value, list):
        return any(has_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(has_placeholder(item) for item in value.values())
    return False


def load_object(path: Path, errors: list[str], label: str) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label} is not valid JSON: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{label} must be a JSON object")
        return None
    return value


def exact_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def validate(pack: Path) -> list[str]:
    errors: list[str] = []
    manifest = load_object(pack / "pack.json", errors, "pack.json")
    plan = load_object(pack / PLAN_RELATIVE, errors, "verification plan")
    track_contract = load_object(
        pack / TRACK_CONTRACT_RELATIVE, errors, "verification track contract"
    )
    if manifest is None or plan is None or track_contract is None:
        return errors

    if manifest.get("pack_key") != PACK_KEY:
        errors.append(f"pack_key must be {PACK_KEY}")
    paths = manifest.get("paths")
    if not isinstance(paths, dict):
        errors.append("pack.json paths must be an object")
    else:
        if paths.get("verification_plan") != PLAN_RELATIVE.as_posix():
            errors.append("pack.json paths.verification_plan must bind the validation plan")
        if paths.get("verification_track_contract") != TRACK_CONTRACT_RELATIVE.as_posix():
            errors.append("pack.json paths.verification_track_contract must bind the track contract")
        elif not (pack / TRACK_CONTRACT_RELATIVE).is_file():
            errors.append("verification track contract is missing")
        if paths.get("gate_report") != "certification/gate-report.md" or not (
            pack / "certification/gate-report.md"
        ).is_file():
            errors.append("pack.json paths.gate_report must bind the gate boundary report")

    if plan.get("schema_version") != 1:
        errors.append("verification plan schema_version must be 1")
    if plan.get("plan_key") != f"{PACK_KEY}-verification-plan":
        errors.append("verification plan plan_key drift")
    if plan.get("pack_key") != PACK_KEY:
        errors.append("verification plan pack_key drift")
    if plan.get("plan_status") != "PREPARED_NOT_RUN":
        errors.append("verification plan must remain PREPARED_NOT_RUN")

    execution_protocol = plan.get("execution_protocol")
    if not isinstance(execution_protocol, dict):
        errors.append("verification plan execution_protocol is required")
    else:
        expected_protocol = {
            "kind": DECLARATIVE_PROTOCOL,
            "route_selector": "version-matrix.json#tuples[*]",
            "target_profile_selector": "target-profile/profile.json",
            "provider_lock_selector": "target-profile/dependency-locks/spring-boot-4.1.1.properties",
            "required_failure_policy": FAILURE_POLICY,
        }
        for field, expected in expected_protocol.items():
            if execution_protocol.get(field) != expected:
                errors.append(f"verification execution_protocol {field} drift")
        if has_placeholder(execution_protocol):
            errors.append("verification execution_protocol contains a placeholder")

    contract_target = track_contract.get("target")
    if track_contract.get("schema_version") != 1:
        errors.append("verification track contract schema_version must be 1")
    if track_contract.get("contract_key") != f"{PACK_KEY}-track-contract":
        errors.append("verification track contract key drift")
    if track_contract.get("pack_key") != PACK_KEY:
        errors.append("verification track contract pack_key drift")
    if track_contract.get("status") != "PREPARED_NOT_RUN":
        errors.append("verification track contract must remain PREPARED_NOT_RUN")
    if track_contract.get("failure_policy") != FAILURE_POLICY:
        errors.append("verification track contract failure_policy must be FAIL_CLOSED")
    if has_placeholder(track_contract):
        errors.append("verification track contract contains a placeholder")
    if not isinstance(contract_target, dict):
        errors.append("verification track contract target is required")
    else:
        expected_contract_target = {
            "profile_key": "spring-to-boot-4-1-1-java-21",
            "target_spring_boot": "4.1.1",
            "target_java": "21",
            "route_source": "version-matrix.json#tuples[*]",
            "target_profile": "target-profile/profile.json",
            "provider_lock": "target-profile/dependency-locks/spring-boot-4.1.1.properties",
            "feature_matrix": "target-profile/feature-matrix.json",
            "fcm": "contracts/framework-contract-model.json",
        }
        for field, expected in expected_contract_target.items():
            if contract_target.get(field) != expected:
                errors.append(f"verification track contract target {field} drift")
        provider_lock = contract_target.get("provider_lock")
        if isinstance(provider_lock, str) and not (pack / provider_lock).is_file():
            errors.append("verification track contract provider lock is missing")

    target = plan.get("target")
    manifest_target = manifest.get("target")
    if not isinstance(target, dict) or not isinstance(manifest_target, dict):
        errors.append("verification plan and pack target objects are required")
    else:
        expected_target = {
            "framework": "spring-boot",
            "version": "4.1.1",
            "runtime": "java",
            "runtime_version": "21",
            "build_tools": ["maven-3.9.11", "gradle-8.14.3"],
        }
        for field, expected in expected_target.items():
            if target.get(field) != expected:
                errors.append(f"verification target {field} drift")
        if target.get("profile_key") != "spring-to-boot-4-1-1-java-21":
            errors.append("verification target profile_key drift")
        if target.get("provider_versions") != manifest_target.get("provider_versions"):
            errors.append("verification target provider_versions drift")

    profile = load_object(pack / PROFILE_RELATIVE, errors, "target profile")
    if profile is not None:
        if profile.get("profile_key") != "spring-to-boot-4-1-1-java-21":
            errors.append("target profile key drift")
        if profile.get("framework") != "spring-boot" or profile.get("framework_versions") != ["4.1.1"]:
            errors.append("target profile Spring Boot tuple drift")
        if profile.get("runtime") != "java" or profile.get("runtime_versions") != ["21"]:
            errors.append("target profile Java tuple drift")

    domain_section = track_contract.get("provider_domains")
    expected_domain_ids = list(EXPECTED_PROVIDER_DOMAINS)
    if not isinstance(domain_section, list) or [
        item.get("id") for item in domain_section if isinstance(item, dict)
    ] != expected_domain_ids:
        errors.append("provider domains must exactly match security/database/transaction/messaging/provider")
    else:
        provider_keys = set()
        if profile is not None and isinstance(profile.get("providers"), dict):
            provider_keys = set(profile["providers"])
        observed_provider_features: list[str] = []
        for domain in domain_section:
            domain_id = domain.get("id")
            expected_domain = EXPECTED_PROVIDER_DOMAINS[domain_id]
            for field in (
                "feature_ids",
                "target_profile_keys",
                "unresolved_provider_profiles",
                "required_evidence_roles",
            ):
                if domain.get(field) != expected_domain[field]:
                    errors.append(f"provider domain {domain_id} {field} drift")
            if domain.get("source_profile_required") is not True:
                errors.append(f"provider domain {domain_id} source_profile_required must be true")
            if domain.get("status") != "NOT_RUN":
                errors.append(f"provider domain {domain_id} status must remain NOT_RUN")
            observed_provider_features.extend(domain.get("feature_ids", []))
            for profile_key in domain.get("target_profile_keys", []):
                if profile_key not in provider_keys:
                    errors.append(
                        f"provider domain {domain_id} target profile key is missing: {profile_key}"
                    )
        if len(observed_provider_features) != len(set(observed_provider_features)):
            errors.append("provider domain feature coverage must be duplicate-free")
        if set(observed_provider_features) != REQUIRED_PROVIDER_FEATURES:
            errors.append("provider domains must exactly cover provider feature set")
        policy = track_contract.get("provider_domain_policy")
        if not isinstance(policy, dict):
            errors.append("provider_domain_policy is required")
        else:
            expected_policy = {
                "source_profile_required": True,
                "target_provider_version_lock_required": True,
                "unsupported_or_unresolved_semantics": "NOT_RUN",
                "domain_overlap": FAILURE_POLICY,
                "static_mapping_is_not_runtime_evidence": True,
            }
            for field, expected in expected_policy.items():
                if policy.get(field) != expected:
                    errors.append(f"provider_domain_policy {field} drift")

    version_matrix = load_object(pack / VERSION_MATRIX_RELATIVE, errors, "version matrix")
    route_section = plan.get("routes")
    route_ids = route_section.get("ids") if isinstance(route_section, dict) else None
    if not isinstance(route_section, dict) or route_section.get("source_of_truth") != VERSION_MATRIX_RELATIVE.as_posix():
        errors.append("verification routes must be bound to version-matrix.json")
    if not exact_string_list(route_ids) or len(set(route_ids)) != len(route_ids):
        errors.append("verification routes.ids must be a non-empty duplicate-free string list")
    if version_matrix is not None and isinstance(route_ids, list):
        if version_matrix.get("schema_version") != 1:
            errors.append("version matrix schema_version drift")
        if version_matrix.get("pack_key") != PACK_KEY:
            errors.append("version matrix pack_key drift")
        if version_matrix.get("target") != {"spring_boot": "4.1.1", "java": "21"}:
            errors.append("version matrix target tuple drift")
        rows = version_matrix.get("tuples")
        expected_ids = [row.get("id") for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        if route_ids != expected_ids:
            errors.append("verification route ids must exactly match version-matrix tuple order")
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                errors.append("version matrix tuple must be an object")
                continue
            if row.get("target_spring_boot", "4.1.1") != "4.1.1":
                errors.append(f"version matrix target drift: {row.get('id')}")
            if row.get("target_java", "21") != "21":
                errors.append(f"version matrix Java target drift: {row.get('id')}")
            if row.get("execution_status") != "NOT_RUN":
                errors.append(f"version matrix execution must remain NOT_RUN: {row.get('id')}")
    if ROUTE_CATALOG.is_file():
        catalog_text = ROUTE_CATALOG.read_text(encoding="utf-8")
        for route_id in route_ids if isinstance(route_ids, list) else []:
            if f'"{route_id}"' not in catalog_text:
                errors.append(f"route is absent from Java catalog: {route_id}")
        if 'static final String TARGET_BOOT = "3.5.3"' not in catalog_text:
            errors.append("legacy default target 3.5.3 is not bound in the Java catalog")
        if 'static final String TARGET_BOOT_4_1_1 = "4.1.1"' not in catalog_text:
            errors.append("Boot 4.1.1 target is not bound in the Java catalog")
    else:
        errors.append("Java Spring route catalog is missing")

    boundary = plan.get("compatibility_boundary")
    if not isinstance(boundary, dict):
        errors.append("compatibility_boundary is required")
    else:
        if boundary.get("legacy_default_target") != {"spring_boot": "3.5.3", "java": "21"}:
            errors.append("legacy default target boundary drift")
        if boundary.get("new_target_requires_request_field") != "targetSpringBoot":
            errors.append("new target request field boundary drift")
        if boundary.get("new_target_request_value") != "4.1.1":
            errors.append("new target request value boundary drift")
        if boundary.get("legacy_default_must_remain_unchanged") is not True:
            errors.append("legacy default preservation must be true")
        if boundary.get("target_selection_must_be_explicit") is not True:
            errors.append("target selection explicitness must be true")

    corpora = plan.get("corpora")
    expected_corpus_paths = {
        "development": "corpus/development",
        "holdout": "corpus/holdout",
        "representative_repository": "corpus/real-repository",
    }
    if not isinstance(corpora, dict) or set(corpora) != set(expected_corpus_paths):
        errors.append("verification corpora must declare development, holdout and representative_repository")
    else:
        observed_paths = []
        for role, expected_path in expected_corpus_paths.items():
            entry = corpora.get(role)
            if not isinstance(entry, dict) or entry.get("path") != expected_path:
                errors.append(f"verification corpus path drift: {role}")
            else:
                observed_paths.append(expected_path)
        if len(observed_paths) != len(set(observed_paths)):
            errors.append("development, holdout and representative corpora must be distinct")

    feature_matrix = load_object(pack / FEATURE_MATRIX_RELATIVE, errors, "feature matrix")
    feature_section = plan.get("feature_verification")
    if not isinstance(feature_section, dict):
        errors.append("feature_verification is required")
    elif feature_matrix is not None:
        source_language_ids = {
            f"language-{item.get('id')}"
            for item in feature_matrix.get("source_languages", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        component_feature_ids = {
            feature_id
            for component in feature_matrix.get("components", [])
            if isinstance(component, dict)
            for feature_id in component.get("features", [])
            if isinstance(feature_id, str)
        }
        expected_features = source_language_ids | component_feature_ids
        groups = {
            key: feature_section.get(key)
            for key in ("static_conversion", "runtime_contract", "provider_behavior", "test_behavior", "unsupported")
        }
        flattened: list[str] = []
        for group, values in groups.items():
            if not exact_string_list(values):
                errors.append(f"feature verification group must be a string list: {group}")
                continue
            flattened.extend(values)
            status = feature_section.get("status_policy", {}).get(group) if isinstance(feature_section.get("status_policy"), dict) else None
            expected_status = "STATIC_COVERED_NOT_RUNTIME_CERTIFIED" if group == "static_conversion" else "NOT_RUN"
            if status != expected_status:
                errors.append(f"feature verification status policy drift: {group}")
        if len(flattened) != len(set(flattened)):
            errors.append("feature verification groups must not overlap")
        if set(flattened) != expected_features:
            errors.append("feature verification groups must exactly cover the feature matrix")
        provider_values = set(groups.get("provider_behavior") or [])
        if not REQUIRED_PROVIDER_FEATURES.issubset(provider_values):
            errors.append("security/data/transaction/messaging/provider features must use provider_behavior")
        if feature_section.get("source_of_truth") != FEATURE_MATRIX_RELATIVE.as_posix():
            errors.append("feature verification source_of_truth drift")

    tracks = plan.get("tracks")
    if not isinstance(tracks, list) or [item.get("id") for item in tracks if isinstance(item, dict)] != list(TRACK_IDS):
        errors.append("verification tracks must exactly match the required ordered track list")
    else:
        corpus_roles = set(expected_corpus_paths)
        for track in tracks:
            track_id = track.get("id")
            if track.get("required") is not True:
                errors.append(f"verification track is not required: {track_id}")
            for field in ("status", "authorization_status", "independent_verifier_status"):
                if track.get(field) != "NOT_RUN":
                    errors.append(f"verification track {track_id} {field} must remain NOT_RUN")
            if track.get("execution_mode") != DECLARATIVE_PROTOCOL:
                errors.append(f"verification track {track_id} execution_mode must be declarative")
            if not isinstance(track.get("replay_command"), str) or not track["replay_command"].strip():
                errors.append(f"verification track replay_command is missing: {track_id}")
            elif has_placeholder(track["replay_command"]):
                errors.append(f"verification track replay_command contains a placeholder: {track_id}")
            elif not track["replay_command"].startswith("DECLARATIVE_ONLY batch30."):
                errors.append(f"verification track replay_command must be declarative: {track_id}")
            elif any(
                marker not in track["replay_command"]
                for marker in EXPECTED_PROTOCOL_MARKERS.get(track_id, ())
            ):
                errors.append(f"verification track replay_command binding is incomplete: {track_id}")
            role = track.get("corpus_role", track.get("input_corpus_role"))
            if role not in corpus_roles:
                errors.append(f"verification track corpus role is invalid: {track_id}")
            required_roles = track.get("required_evidence_roles")
            slots = track.get("evidence_slots")
            if not exact_string_list(required_roles) or len(set(required_roles)) != len(required_roles):
                errors.append(f"verification track evidence roles are invalid: {track_id}")
                continue
            if not isinstance(slots, list):
                errors.append(f"verification track evidence_slots are missing: {track_id}")
                continue
            slot_roles = []
            for slot in slots:
                if not isinstance(slot, dict):
                    errors.append(f"verification track evidence slot is invalid: {track_id}")
                    continue
                slot_roles.append(slot.get("role"))
                if slot.get("status") != "NOT_RUN":
                    errors.append(f"verification evidence slot must remain NOT_RUN: {track_id}")
                if slot.get("path") is not None or slot.get("sha256") is not None:
                    errors.append(f"unmaterialized verification evidence slot must have null binding: {track_id}")
            if slot_roles != required_roles:
                errors.append(f"verification track evidence slots do not match required roles: {track_id}")
        independent = tracks[-1]
        if independent.get("evidence_destination") != "certification/independent-verification":
            errors.append("independent verifier evidence destination drift")

    contract_tracks = track_contract.get("tracks")
    if not isinstance(contract_tracks, list) or [
        item.get("id") for item in contract_tracks if isinstance(item, dict)
    ] != list(TRACK_IDS):
        errors.append("verification track contract must exactly match the required ordered track list")
    elif isinstance(tracks, list) and len(tracks) == len(contract_tracks):
        for plan_track, contract_track in zip(tracks, contract_tracks):
            track_id = plan_track.get("id")
            if contract_track.get("id") != track_id:
                errors.append(f"verification track contract id drift: {track_id}")
                continue
            for field in (
                "required",
                "execution_mode",
                "status",
                "authorization_status",
                "independent_verifier_status",
                "failure_policy",
            ):
                expected = plan_track.get(field)
                if contract_track.get(field) != expected:
                    errors.append(f"verification track contract {track_id} {field} drift")
            if contract_track.get("execution_mode") != DECLARATIVE_PROTOCOL:
                errors.append(f"verification track contract {track_id} execution_mode must be declarative")
            protocol = contract_track.get("protocol")
            if protocol != plan_track.get("replay_command"):
                errors.append(f"verification track contract {track_id} protocol drift")
            elif not isinstance(protocol, str) or has_placeholder(protocol):
                errors.append(f"verification track contract {track_id} protocol contains a placeholder")
            elif not protocol.startswith("DECLARATIVE_ONLY batch30."):
                errors.append(f"verification track contract {track_id} protocol must be declarative")
            elif any(
                marker not in protocol
                for marker in EXPECTED_PROTOCOL_MARKERS.get(track_id, ())
            ):
                errors.append(f"verification track contract {track_id} protocol binding is incomplete")
            expected_route = EXPECTED_TRACK_ROUTE_BINDINGS[track_id]
            if contract_track.get("route_binding") != expected_route:
                errors.append(f"verification track contract {track_id} route_binding drift")
            contract_role = contract_track.get("corpus_role", contract_track.get("input_corpus_role"))
            plan_role = plan_track.get("corpus_role", plan_track.get("input_corpus_role"))
            if contract_role != plan_role:
                errors.append(f"verification track contract {track_id} corpus role drift")
            if contract_track.get("required_evidence_roles") != plan_track.get("required_evidence_roles"):
                errors.append(f"verification track contract {track_id} evidence roles drift")
            if contract_track.get("failure_policy") != FAILURE_POLICY:
                errors.append(f"verification track contract {track_id} failure_policy must be FAIL_CLOSED")
            if contract_track.get("status") != "NOT_RUN":
                errors.append(f"verification track contract {track_id} status must remain NOT_RUN")
            if contract_track.get("authorization_status") != "NOT_RUN":
                errors.append(f"verification track contract {track_id} authorization must remain NOT_RUN")
            if contract_track.get("independent_verifier_status") != "NOT_RUN":
                errors.append(f"verification track contract {track_id} verifier status must remain NOT_RUN")
        if contract_tracks[-1].get("evidence_destination") != "certification/independent-verification":
            errors.append("verification track contract independent verifier evidence destination drift")

    evidence = load_object(pack / EVIDENCE_RELATIVE, errors, "certification evidence")
    if evidence is not None:
        if evidence.get("execution_status") != "NOT_RUN":
            errors.append("certification evidence execution_status must remain NOT_RUN")
        required_fields = {
            field
            for fields in TRACK_EVIDENCE_FIELDS.values()
            for field in fields
        }
        for field in required_fields:
            if evidence.get(field) != "NOT_RUN":
                errors.append(f"certification evidence {field} must remain NOT_RUN")
        required_before = evidence.get("required_before_promotion")
        if not exact_string_list(required_before):
            errors.append("certification evidence required_before_promotion must be a string list")
        else:
            required_names = {
                "real-source-build",
                "real-target-build",
                "source-startup",
                "target-startup",
                "component-contracts",
                "provider-behavior",
                "independent-holdout",
                "representative-repository",
                "independent-verification",
            }
            if not required_names.issubset(set(required_before)):
                errors.append("certification evidence promotion prerequisites are incomplete")

    certification = load_object(pack / CERTIFICATION_RELATIVE, errors, "certification record")
    if certification is not None:
        if certification.get("pack_key") != PACK_KEY:
            errors.append("certification pack_key drift")
        if certification.get("decision") != "NOT_CERTIFIED":
            errors.append("certification decision must remain NOT_CERTIFIED")
        if certification.get("certification_eligible") is not False:
            errors.append("certification_eligible must remain false")
        if certification.get("external_evidence_status") != "NOT_RUN":
            errors.append("external_evidence_status must remain NOT_RUN")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack_dir", type=Path)
    args = parser.parse_args()
    errors = validate(args.pack_dir)
    if errors:
        for error in errors:
            print(f"PLAN FAIL: {error}")
        return 1
    print(
        json.dumps(
            {
                "status": "PASSED",
                "pack_key": PACK_KEY,
                "plan_status": "PREPARED_NOT_RUN",
                "tracks": list(TRACK_IDS),
                "external_evidence_status": "NOT_RUN",
                "certification_decision": "NOT_CERTIFIED",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
