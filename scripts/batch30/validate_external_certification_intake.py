#!/usr/bin/env python3
"""Verify signed, content-addressed Batch 30 external evidence intake.

This verifier is intentionally separate from the framework certification gate.  A
successful intake proves that the supplied bytes and attestations are authentic,
current, exactly scoped, and role-separated.  It never changes a framework pack,
never promotes a status, and never returns CERTIFIED.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.precision_migration.trust import (  # noqa: E402
    TrustStore,
    canonical_digest,
    read_regular_file_once,
    verify_content_reference,
)


NAMESPACE = "batch30-framework-external-certification"
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{1,199}$")
NON_SUCCESS = {
    "UNKNOWN",
    "INCONCLUSIVE",
    "NOT_RUN",
    "NOT_EVALUATED",
    "NOT_APPLICABLE",
    "UNSUPPORTED",
    "UNBOUND_REQUIRES_SOURCE_FINGERPRINT",
    "BLOCKED",
}
MAX_JSON_BYTES = 4 * 1024 * 1024

CUSTOMER_AUTHORIZATION_ROLE = "batch30-customer-authorizer"
EVIDENCE_ROLES = {
    "authorized_customer_repository": "batch30-customer-repository-verifier",
    "customer_holdout": "batch30-customer-holdout-verifier",
    "customer_acceptance": "batch30-customer-acceptance-approver",
    "rootless_runner": "batch30-rootless-runner-attestor",
    "rootless_transformer": "batch30-rootless-transformer-attestor",
    "rootless_verifier": "batch30-rootless-verifier-attestor",
    "independent_review": "batch30-independent-verifier",
    "external_certification": "batch30-external-certifier",
}
REQUIRED_EVIDENCE = tuple(EVIDENCE_ROLES)
ALLOWED_ROLES = {CUSTOMER_AUTHORIZATION_ROLE, *EVIDENCE_ROLES.values()}

CUSTOMER_EVIDENCE = {
    "authorized_customer_repository",
    "customer_holdout",
    "customer_acceptance",
}
ROOTLESS_EVIDENCE = {"rootless_runner", "rootless_transformer", "rootless_verifier"}
ORGANIZATIONALLY_INDEPENDENT_EVIDENCE = {"independent_review", "external_certification"}
EVIDENCE_OUTCOMES = {
    **{evidence_type: "PASS" for evidence_type in EVIDENCE_ROLES},
    "customer_acceptance": "ACCEPTED",
    "external_certification": "CERTIFIED",
}

AUTHORIZATION_PAYLOAD_FIELDS = {
    "record_id",
    "issued_at",
    "expires_at",
    "actor_id",
    "organization_id",
    "role",
    "intake_id",
    "binding_digest",
    "scope",
    "outcome",
    "synthetic",
    "unknowns",
    "not_run",
}
ATTESTATION_PAYLOAD_FIELDS = {
    "record_id",
    "issued_at",
    "expires_at",
    "actor_id",
    "organization_id",
    "role",
    "intake_id",
    "binding_digest",
    "authorization_record_id",
    "authorization_payload_digest",
    "evidence_type",
    "content_digest",
    "content_size_bytes",
    "executor_actor_id",
    "executor_organization_id",
    "outcome",
    "evidence_class",
    "synthetic",
    "unknowns",
    "not_run",
    "claims",
}


class ExternalIntakeError(ValueError):
    """Raised when an external evidence intake fails closed."""


@dataclass(frozen=True)
class SignerMetadata:
    key_id: str
    actor_id: str
    organization_id: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class LoadedTrust:
    store: TrustStore
    metadata: dict[str, SignerMetadata]


@dataclass(frozen=True)
class JsonFileSnapshot:
    value: dict[str, Any]
    digest: str
    size_bytes: int


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExternalIntakeError(f"{label} must be an object")
    return value


def _require_exact_fields(value: dict[str, Any], expected: set[str], label: str) -> None:
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing or extra:
        raise ExternalIntakeError(f"{label} fields are invalid; missing={missing}, extra={extra}")


def _require_identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or IDENTITY.fullmatch(value) is None or value.upper() in NON_SUCCESS:
        raise ExternalIntakeError(f"{label} must be an exact, non-placeholder identity")
    return value


def _reject_non_success(value: Any, label: str) -> None:
    if isinstance(value, str) and value.upper() in NON_SUCCESS:
        raise ExternalIntakeError(f"{label} contains non-success sentinel {value}")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_non_success(item, f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_non_success(item, f"{label}[{index}]")


def _load_json_snapshot(
    path: Path, label: str, *, max_bytes: int = MAX_JSON_BYTES
) -> JsonFileSnapshot:
    try:
        raw = read_regular_file_once(path, max_bytes=max_bytes, label=label)
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ExternalIntakeError(f"{label} is not bounded regular UTF-8 JSON: {exc}") from exc
    return JsonFileSnapshot(
        value=_require_object(value, label),
        digest="sha256:" + hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
    )


def _approved_roots(values: Iterable[Path]) -> tuple[Path, ...]:
    supplied = list(values)
    if not supplied:
        raise ExternalIntakeError("at least one explicit evidence root is required")
    roots: list[Path] = []
    for candidate in supplied:
        expanded = candidate.expanduser()
        if expanded.is_symlink():
            raise ExternalIntakeError(f"evidence root must not be a symlink: {candidate}")
        try:
            resolved = expanded.resolve(strict=True)
        except OSError as exc:
            raise ExternalIntakeError(f"evidence root does not exist: {candidate}") from exc
        if not resolved.is_dir():
            raise ExternalIntakeError(f"evidence root is not a directory: {resolved}")
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _lexical_file_path(reference: dict[str, Any], roots: tuple[Path, ...], label: str) -> Path:
    uri = reference.get("uri")
    if not isinstance(uri, str) or not uri:
        raise ExternalIntakeError(f"{label}.uri is required")
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise ExternalIntakeError(f"{label}.uri must be a local file URI")
    raw = Path(unquote(parsed.path))
    lexical = Path(os.path.abspath(raw))
    containing_root: Path | None = None
    for root in roots:
        try:
            lexical.relative_to(root)
        except ValueError:
            continue
        containing_root = root
        break
    if containing_root is None:
        raise ExternalIntakeError(f"{label}.uri escapes approved evidence roots")
    relative = lexical.relative_to(containing_root)
    current = containing_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ExternalIntakeError(f"{label}.uri contains a symlink")
    return lexical


def _verify_reference(reference: Any, roots: tuple[Path, ...], label: str) -> dict[str, Any]:
    item = _require_object(reference, label)
    _require_exact_fields(item, {"uri", "digest", "size_bytes", "media_type"}, label)
    if not isinstance(item.get("media_type"), str) or not item["media_type"]:
        raise ExternalIntakeError(f"{label}.media_type is required")
    if DIGEST.fullmatch(str(item.get("digest"))) is None:
        raise ExternalIntakeError(f"{label}.digest must be sha256:<64 lowercase hex>")
    size = item.get("size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ExternalIntakeError(f"{label}.size_bytes must be a positive integer")
    _lexical_file_path(item, roots, label)
    try:
        return verify_content_reference(item, roots)
    except (OSError, ValueError) as exc:
        raise ExternalIntakeError(f"{label} content verification failed: {exc}") from exc


def _exact_side(manifest: dict[str, Any], side_name: str) -> dict[str, Any]:
    side = _require_object(manifest.get(side_name), f"pack.{side_name}")
    exact: dict[str, str] = {}
    for plural, singular in (
        ("framework_versions", "framework_version"),
        ("runtime_versions", "runtime_version"),
        ("build_tools", "build_tool"),
    ):
        values = side.get(plural)
        if not isinstance(values, list) or len(values) != 1:
            raise ExternalIntakeError(f"pack.{side_name}.{plural} must contain exactly one value")
        exact[singular] = _require_identity(values[0], f"pack.{side_name}.{plural}[0]")
    return {
        "framework": _require_identity(side.get("framework"), f"pack.{side_name}.framework"),
        "framework_version": exact["framework_version"],
        "runtime": _require_identity(side.get("runtime"), f"pack.{side_name}.runtime"),
        "runtime_version": exact["runtime_version"],
        "build_tool": exact["build_tool"],
        "provider_versions": _require_object(side.get("provider_versions", {}), f"pack.{side_name}.provider_versions"),
    }


def _validate_pack_identity(
    pack_dir: Path,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, JsonFileSnapshot],
]:
    if pack_dir.is_symlink():
        raise ExternalIntakeError("pack_dir must not be a symlink")
    pack = pack_dir.resolve(strict=True)
    if not pack.is_dir():
        raise ExternalIntakeError("pack_dir must be a directory")
    snapshots = {
        "pack_manifest": _load_json_snapshot(pack / "pack.json", "pack manifest"),
        "version_matrix": _load_json_snapshot(pack / "version-matrix.json", "version matrix"),
        "target_profile": _load_json_snapshot(
            pack / "target-profile" / "profile.json", "target profile"
        ),
        "recipe_manifest": _load_json_snapshot(
            pack / "recipes" / "manifest.json", "recipe manifest"
        ),
    }
    manifest = snapshots["pack_manifest"].value
    matrix = snapshots["version_matrix"].value
    target_profile = snapshots["target_profile"].value
    recipes = snapshots["recipe_manifest"].value
    pack_key = _require_identity(manifest.get("pack_key"), "pack.pack_key")
    if matrix.get("pack_key") != pack_key or recipes.get("pack_key") != pack_key:
        raise ExternalIntakeError("pack, version matrix, and recipe manifest pack_key must match")
    source = _exact_side(manifest, "source")
    target = _exact_side(manifest, "target")
    if (
        target_profile.get("framework") != target["framework"]
        or target_profile.get("framework_versions") != [target["framework_version"]]
        or target_profile.get("runtime") != target["runtime"]
        or target_profile.get("runtime_versions") != [target["runtime_version"]]
    ):
        raise ExternalIntakeError("target profile does not match the exact target tuple")
    tuples = matrix.get("tuples")
    if not isinstance(tuples, list) or len(tuples) < 2:
        raise ExternalIntakeError("version matrix must contain exact source and target tuples")
    if not isinstance(recipes.get("recipes"), list) or not recipes["recipes"]:
        raise ExternalIntakeError("recipe manifest must contain at least one exact recipe")
    source_candidates = [candidate for candidate in tuples if _tuple_matches(candidate, source)]
    target_candidates = [candidate for candidate in tuples if _tuple_matches(candidate, target)]
    if len(source_candidates) != 1 or len(target_candidates) != 1:
        raise ExternalIntakeError("version matrix must match each exact source and target tuple exactly once")
    source_id = source_candidates[0].get("id")
    target_id = target_candidates[0].get("id")
    edges = matrix.get("upgrade_edges")
    matching_edges = []
    if isinstance(edges, list):
        matching_edges = [
            edge
            for edge in edges
            if isinstance(edge, dict)
            and edge.get("from") == source_id
            and edge.get("to") == target_id
            and edge.get("directional") is True
        ]
    if len(matching_edges) != 1:
        raise ExternalIntakeError("version matrix must contain one directional edge for the exact tuple")
    edge = matching_edges[0]
    edge_recipes = edge.get("recipes")
    if edge_recipes is None and isinstance(edge.get("recipe"), str):
        edge_recipes = [edge["recipe"]]
    if (
        not isinstance(edge_recipes, list)
        or not edge_recipes
        or any(recipe not in recipes["recipes"] for recipe in edge_recipes)
    ):
        raise ExternalIntakeError("version matrix edge and recipe manifest are not exactly aligned")
    return manifest, source, target, snapshots


def _tuple_matches(candidate: Any, exact: dict[str, Any]) -> bool:
    if not isinstance(candidate, dict):
        return False
    candidate_framework = candidate.get("framework", exact["framework"])
    candidate_framework_version = candidate.get("framework_version", candidate.get("spring_boot"))
    runtime_key = "java" if exact["runtime"] == "java" else "runtime_version"
    return (
        candidate_framework == exact["framework"]
        and candidate_framework_version == exact["framework_version"]
        and candidate.get(runtime_key) == exact["runtime_version"]
        and candidate.get("build") == exact["build_tool"]
    )


def build_expected_binding(
    pack_dir: Path,
    artifact_reference: Any,
    execution_profile_reference: Any,
    *,
    evidence_roots: Iterable[Path],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Build and verify the exact immutable binding signers must attest."""
    roots = _approved_roots(evidence_roots)
    pack = pack_dir.resolve(strict=True)
    manifest, source, target, snapshots = _validate_pack_identity(pack)
    artifact = _verify_reference(artifact_reference, roots, "artifact")
    execution_profile = _verify_reference(execution_profile_reference, roots, "execution_profile")
    if artifact["digest"] == execution_profile["digest"]:
        raise ExternalIntakeError("artifact and execution profile must bind distinct content bytes")
    binding = {
        "pack_key": manifest["pack_key"],
        "pack_version": _require_identity(manifest.get("version"), "pack.version"),
        "pack_manifest_digest": snapshots["pack_manifest"].digest,
        "source_tuple": source,
        "target_tuple": target,
        "version_matrix_digest": snapshots["version_matrix"].digest,
        "recipe_manifest_digest": snapshots["recipe_manifest"].digest,
        "target_profile_digest": snapshots["target_profile"].digest,
        "artifact_digest": artifact["digest"],
        "artifact_size_bytes": artifact["size_bytes"],
        "execution_profile_digest": execution_profile["digest"],
        "execution_profile_size_bytes": execution_profile["size_bytes"],
    }
    return binding, {"artifact": artifact, "execution_profile": execution_profile}


def _load_trust(path: Path) -> LoadedTrust:
    supplied = path.expanduser()
    if supplied.is_symlink():
        raise ExternalIntakeError("trust store must not be a symlink")
    try:
        resolved = supplied.resolve(strict=True)
        before = read_regular_file_once(
            supplied, max_bytes=1024 * 1024, label="Batch 30 trust store"
        )
        payload = _require_object(json.loads(before.decode("utf-8")), "Batch 30 trust store")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ExternalIntakeError(f"Batch 30 trust store is invalid: {exc}") from exc
    _require_exact_fields(payload, {"schema_version", "namespace", "keys", "revoked_record_ids"}, "trust store")
    if payload.get("schema_version") != 1 or payload.get("namespace") != NAMESPACE:
        raise ExternalIntakeError("trust store identity is invalid")
    _reject_non_success(payload, "trust store")
    keys = payload.get("keys")
    if not isinstance(keys, list) or not keys:
        raise ExternalIntakeError("trust store keys must be a non-empty array")
    metadata: dict[str, SignerMetadata] = {}
    base = resolved.parent
    key_fields = {
        "key_id", "actor_id", "organization_id", "roles", "public_key_path",
        "not_before", "not_after", "revoked",
    }
    for index, raw in enumerate(keys):
        item = _require_object(raw, f"trust store key {index}")
        _require_exact_fields(item, key_fields, f"trust store key {index}")
        key_id = _require_identity(item.get("key_id"), f"trust store key {index}.key_id")
        if key_id in metadata:
            raise ExternalIntakeError(f"duplicate trust key identity: {key_id}")
        actor = _require_identity(item.get("actor_id"), f"trust store key {key_id}.actor_id")
        organization = _require_identity(item.get("organization_id"), f"trust store key {key_id}.organization_id")
        roles = item.get("roles")
        if not isinstance(roles, list) or len(roles) != 1 or len(set(roles)) != 1:
            raise ExternalIntakeError(f"trust store key {key_id}.roles is invalid")
        role_values = tuple(_require_identity(role, f"trust store key {key_id}.roles") for role in roles)
        if any(role not in ALLOWED_ROLES for role in role_values):
            raise ExternalIntakeError(f"trust store key {key_id}.roles contains an unsupported role")
        relative_key = item.get("public_key_path")
        if not isinstance(relative_key, str) or not relative_key or Path(relative_key).is_absolute() or ".." in Path(relative_key).parts:
            raise ExternalIntakeError(f"trust store key {key_id}.public_key_path is invalid")
        current = base
        for part in Path(relative_key).parts:
            current = current / part
            if current.is_symlink():
                raise ExternalIntakeError(f"trust store key {key_id}.public_key_path contains a symlink")
        if not isinstance(item.get("revoked"), bool):
            raise ExternalIntakeError(f"trust store key {key_id}.revoked must be boolean")
        metadata[key_id] = SignerMetadata(key_id, actor, organization, role_values)
    try:
        store = TrustStore.from_bytes(resolved, before)
    except (OSError, ValueError) as exc:
        raise ExternalIntakeError(f"Batch 30 trust store verification failed: {exc}") from exc
    return LoadedTrust(store=store, metadata=metadata)


def _organization_for(evidence_type: str, intake: dict[str, Any]) -> str:
    if evidence_type in CUSTOMER_EVIDENCE:
        return intake["customer_organization_id"]
    if evidence_type in ROOTLESS_EVIDENCE:
        return intake["rootless_organization_id"]
    if evidence_type == "independent_review":
        return intake["independent_organization_id"]
    return intake["certification_organization_id"]


def _evidence_executors(value: Any) -> dict[str, dict[str, str]]:
    executors = _require_object(value, "intake.evidence_executors")
    _require_exact_fields(executors, set(REQUIRED_EVIDENCE), "intake.evidence_executors")
    normalized: dict[str, dict[str, str]] = {}
    for evidence_type in REQUIRED_EVIDENCE:
        principal = _require_object(
            executors[evidence_type],
            f"intake.evidence_executors.{evidence_type}",
        )
        _require_exact_fields(
            principal,
            {"actor_id", "organization_id"},
            f"intake.evidence_executors.{evidence_type}",
        )
        normalized[evidence_type] = {
            "actor_id": _require_identity(
                principal.get("actor_id"),
                f"intake.evidence_executors.{evidence_type}.actor_id",
            ),
            "organization_id": _require_identity(
                principal.get("organization_id"),
                f"intake.evidence_executors.{evidence_type}.organization_id",
            ),
        }
    return normalized


def _expected_claims(evidence_type: str) -> dict[str, Any]:
    if evidence_type == "authorized_customer_repository":
        return {"authorized_repository": True, "fixed_commit": True, "acceptance_subject_bound": True}
    if evidence_type == "customer_holdout":
        return {"independent_from_development": True, "customer_owned_acceptance": True}
    if evidence_type == "customer_acceptance":
        return {
            "acceptance_subject_bound": True,
            "accepted_exact_artifact_and_profile": True,
            "customer_decision": "ACCEPTED",
        }
    if evidence_type in ROOTLESS_EVIDENCE:
        return {"rootless": True, "privileged": False, "effective_uid_nonzero": True}
    if evidence_type == "independent_review":
        return {"organizationally_independent": True, "separate_executor_and_verifier": True}
    return {
        "certification_scope_bound": True,
        "independent_certification_authority": True,
        "certificate_decision": "CERTIFIED",
    }


def _verify_signed_payload(
    loaded: LoadedTrust,
    envelope: Any,
    *,
    role: str,
    expected_organization: str,
    bindings: dict[str, Any],
    expected_fields: set[str],
    now: datetime | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    item = _require_object(envelope, f"{role} envelope")
    _require_exact_fields(item, {"algorithm", "key_id", "payload", "signature"}, f"{role} envelope")
    key_id = item.get("key_id")
    if not isinstance(key_id, str) or key_id not in loaded.metadata:
        raise ExternalIntakeError(f"{role} signing key is unknown")
    metadata = loaded.metadata[key_id]
    if metadata.roles != (role,):
        raise ExternalIntakeError(f"{role} signing key must be dedicated to exactly that role")
    if metadata.organization_id != expected_organization:
        raise ExternalIntakeError(f"{role} signer organization does not match its trust class")
    payload = _require_object(item.get("payload"), f"{role} payload")
    _require_exact_fields(payload, expected_fields, f"{role} payload")
    _require_identity(payload.get("record_id"), f"{role} payload.record_id")
    if payload.get("actor_id") != metadata.actor_id or payload.get("organization_id") != metadata.organization_id:
        raise ExternalIntakeError(f"{role} signed actor or organization does not match the trust store")
    if payload.get("role") != role:
        raise ExternalIntakeError(f"{role} payload role binding is invalid")
    _reject_non_success(payload, f"{role} payload")
    try:
        receipt = loaded.store.verify_envelope(item, required_role=role, bindings=bindings, now=now)
    except (OSError, ValueError) as exc:
        raise ExternalIntakeError(f"{role} signature verification failed: {exc}") from exc
    trusted_key = loaded.store.keys[receipt["key_id"]]
    return payload, {
        **receipt,
        "actor_id": metadata.actor_id,
        "organization_id": metadata.organization_id,
        "public_key_digest": trusted_key.public_key_digest,
    }


def evaluate_external_intake(
    intake: dict[str, Any],
    *,
    pack_dir: Path,
    trust_store: Path | LoadedTrust,
    evidence_roots: Iterable[Path],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate an intake without mutating certification state."""
    item = _require_object(intake, "intake")
    intake_fields = {
        "schema_version", "namespace", "intake_id", "producer_organization_id",
        "customer_organization_id", "rootless_organization_id", "independent_organization_id",
        "certification_organization_id", "binding", "artifact", "execution_profile",
        "evidence_executors", "customer_authorization", "evidence",
    }
    _require_exact_fields(item, intake_fields, "intake")
    if item.get("schema_version") != 1 or item.get("namespace") != NAMESPACE:
        raise ExternalIntakeError("intake identity is invalid")
    intake_id = _require_identity(item.get("intake_id"), "intake.intake_id")
    organizations = {
        name: _require_identity(item.get(name), f"intake.{name}")
        for name in (
            "producer_organization_id",
            "customer_organization_id",
            "rootless_organization_id",
            "independent_organization_id",
            "certification_organization_id",
        )
    }
    if len(set(organizations.values())) != len(organizations):
        raise ExternalIntakeError(
            "producer, customer, rootless, independent, and certification organizations must be distinct"
        )
    evidence_executors = _evidence_executors(item.get("evidence_executors"))
    executor_actor_ids = {
        principal["actor_id"] for principal in evidence_executors.values()
    }
    executor_organization_ids = {
        principal["organization_id"] for principal in evidence_executors.values()
    }
    _reject_non_success(item, "intake")

    expected_binding, primary_artifacts = build_expected_binding(
        pack_dir,
        item.get("artifact"),
        item.get("execution_profile"),
        evidence_roots=evidence_roots,
    )
    binding = _require_object(item.get("binding"), "intake.binding")
    if binding != expected_binding:
        raise ExternalIntakeError("intake binding does not match the exact pack/tuple/artifact/profile identity")
    binding_digest = canonical_digest(binding)
    loaded = _load_trust(trust_store) if isinstance(trust_store, Path) else trust_store

    evidence = _require_object(item.get("evidence"), "intake.evidence")
    _require_exact_fields(evidence, set(REQUIRED_EVIDENCE), "intake.evidence")
    evidence_items: dict[str, dict[str, Any]] = {}
    content_observations: dict[str, dict[str, Any]] = {}
    content_digests = {
        primary_artifacts["artifact"]["digest"],
        primary_artifacts["execution_profile"]["digest"],
    }
    roots = _approved_roots(evidence_roots)
    for evidence_type in REQUIRED_EVIDENCE:
        evidence_item = _require_object(evidence[evidence_type], f"evidence.{evidence_type}")
        _require_exact_fields(evidence_item, {"content", "attestation"}, f"evidence.{evidence_type}")
        content = _verify_reference(evidence_item["content"], roots, f"evidence.{evidence_type}.content")
        if content["digest"] in content_digests:
            raise ExternalIntakeError("each required evidence role must bind distinct content bytes")
        content_digests.add(content["digest"])
        evidence_items[evidence_type] = evidence_item
        content_observations[evidence_type] = content

    scope = {
        "action": "validate-batch30-external-certification-intake",
        "pack_key": binding["pack_key"],
        "pack_version": binding["pack_version"],
        "binding_digest": binding_digest,
        "artifact_digest": binding["artifact_digest"],
        "execution_profile_digest": binding["execution_profile_digest"],
        "producer_organization_id": organizations["producer_organization_id"],
        "customer_organization_id": organizations["customer_organization_id"],
        "rootless_organization_id": organizations["rootless_organization_id"],
        "independent_organization_id": organizations["independent_organization_id"],
        "certification_organization_id": organizations["certification_organization_id"],
        "evidence_types": list(REQUIRED_EVIDENCE),
        "evidence_executors": evidence_executors,
        "evidence_content_digests": {
            name: content_observations[name]["digest"] for name in REQUIRED_EVIDENCE
        },
    }
    auth_bindings = {
        "role": CUSTOMER_AUTHORIZATION_ROLE,
        "intake_id": intake_id,
        "binding_digest": binding_digest,
        "organization_id": organizations["customer_organization_id"],
        "scope": scope,
        "outcome": "AUTHORIZED",
        "synthetic": False,
        "unknowns": [],
        "not_run": [],
    }
    authorization_payload, authorization_receipt = _verify_signed_payload(
        loaded,
        item.get("customer_authorization"),
        role=CUSTOMER_AUTHORIZATION_ROLE,
        expected_organization=organizations["customer_organization_id"],
        bindings=auth_bindings,
        expected_fields=AUTHORIZATION_PAYLOAD_FIELDS,
        now=now,
    )
    authorization_payload_digest = canonical_digest(authorization_payload)
    if authorization_receipt["actor_id"] in executor_actor_ids:
        raise ExternalIntakeError(
            "customer authorizer must be separate from every evidence executor"
        )

    receipts: dict[str, dict[str, Any]] = {}
    actor_ids = {authorization_receipt["actor_id"]}
    key_ids = {authorization_receipt["key_id"]}
    public_keys = {authorization_receipt["public_key_digest"]}
    record_ids = {authorization_payload["record_id"]}
    for evidence_type in REQUIRED_EVIDENCE:
        evidence_item = evidence_items[evidence_type]
        content = content_observations[evidence_type]
        role = EVIDENCE_ROLES[evidence_type]
        executor = evidence_executors[evidence_type]
        bindings = {
            "role": role,
            "intake_id": intake_id,
            "binding_digest": binding_digest,
            "authorization_record_id": authorization_payload["record_id"],
            "authorization_payload_digest": authorization_payload_digest,
            "evidence_type": evidence_type,
            "content_digest": content["digest"],
            "content_size_bytes": content["size_bytes"],
            "executor_actor_id": executor["actor_id"],
            "executor_organization_id": executor["organization_id"],
            "organization_id": _organization_for(evidence_type, item),
            "outcome": EVIDENCE_OUTCOMES[evidence_type],
            "evidence_class": "EXTERNAL_NON_SYNTHETIC",
            "synthetic": False,
            "unknowns": [],
            "not_run": [],
            "claims": _expected_claims(evidence_type),
        }
        payload, receipt = _verify_signed_payload(
            loaded,
            evidence_item.get("attestation"),
            role=role,
            expected_organization=bindings["organization_id"],
            bindings=bindings,
            expected_fields=ATTESTATION_PAYLOAD_FIELDS,
            now=now,
        )
        if receipt["actor_id"] in executor_actor_ids:
            raise ExternalIntakeError(
                "external evidence signer must be separate from every evidence executor"
            )
        if (
            evidence_type in ORGANIZATIONALLY_INDEPENDENT_EVIDENCE
            and receipt["organization_id"] in executor_organization_ids
        ):
            raise ExternalIntakeError(
                f"{evidence_type} signer organization must be separate from every "
                "evidence executor organization"
            )
        for observed, used, label in (
            (receipt["actor_id"], actor_ids, "actor identity"),
            (receipt["key_id"], key_ids, "key identity"),
            (receipt["public_key_digest"], public_keys, "public-key material"),
            (payload["record_id"], record_ids, "record identity"),
        ):
            if observed in used:
                raise ExternalIntakeError(f"external evidence roles must not reuse {label}")
            used.add(observed)
        receipts[evidence_type] = {
            **receipt,
            "record_id": payload["record_id"],
            "content_digest": content["digest"],
            "content_size_bytes": content["size_bytes"],
        }

    return {
        "schema_version": 1,
        "namespace": NAMESPACE,
        "intake_id": intake_id,
        "pack_key": binding["pack_key"],
        "pack_version": binding["pack_version"],
        "binding_digest": binding_digest,
        "trust_store_digest": loaded.store.digest,
        "evidence_status": "VERIFIED_EXTERNAL_INTAKE",
        "verified_roles": [CUSTOMER_AUTHORIZATION_ROLE, *EVIDENCE_ROLES.values()],
        "verified_executor_principals": evidence_executors,
        "verified_content_digests": {
            "artifact": primary_artifacts["artifact"]["digest"],
            "execution_profile": primary_artifacts["execution_profile"]["digest"],
            **{name: receipt["content_digest"] for name, receipt in receipts.items()},
        },
        "decision": "READY_FOR_EXTERNAL_GATE_REVIEW",
        "customer_acceptance_signature_verified": True,
        "independent_review_signature_verified": True,
        "external_certification_signature_verified": True,
        "certification_decision": "NOT_CERTIFIED",
        "certification_promoted": False,
        "pack_status_mutated": False,
        "synthetic_evidence_can_promote": False,
    }


def evaluate_external_intake_file(
    intake_path: Path,
    *,
    pack_dir: Path,
    trust_store: Path | LoadedTrust,
    evidence_roots: Iterable[Path],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read an intake once and return its byte identity with the review result."""
    supplied = intake_path.expanduser()
    if supplied.is_symlink():
        raise ExternalIntakeError("external intake must not be a symlink")
    try:
        raw = read_regular_file_once(
            supplied, max_bytes=MAX_JSON_BYTES, label="external intake"
        )
        intake = _require_object(json.loads(raw.decode("utf-8")), "external intake")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ExternalIntakeError(f"external intake is invalid: {exc}") from exc
    result = evaluate_external_intake(
        intake,
        pack_dir=pack_dir,
        trust_store=trust_store,
        evidence_roots=evidence_roots,
        now=now,
    )
    return {
        **result,
        "intake_content_digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "intake_size_bytes": len(raw),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack_dir", type=Path)
    parser.add_argument("intake", type=Path)
    parser.add_argument("--trust-store", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, action="append", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = evaluate_external_intake_file(
            args.intake,
            pack_dir=args.pack_dir,
            trust_store=args.trust_store,
            evidence_roots=args.evidence_root,
        )
    except (ExternalIntakeError, OSError, ValueError) as exc:
        print(f"INTAKE FAIL: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
