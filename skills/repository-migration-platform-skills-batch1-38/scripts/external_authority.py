#!/usr/bin/env python3
"""Authorize a digest-pinned external evidence authority without trusting repository input."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from actor_trust import ActorTrustStore, canonical_digest, parse_time, read_regular


class ExternalAuthorityError(ValueError):
    pass


def confined(path: Path, roots: tuple[Path, ...], label: str) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise ExternalAuthorityError(f"{label} escapes approved roots")
    return resolved


def authorize(policy_path: Path, approval: dict[str, Any], internal_trust_path: Path,
              external_trust_path: Path, tenant_id: str, purpose: str,
              roots: tuple[Path, ...]) -> tuple[ActorTrustStore, dict[str, Any]]:
    try:
        raw = read_regular(confined(policy_path, roots, "external authority policy"),
                           1024 * 1024, "external authority policy")
        policy = json.loads(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ExternalAuthorityError(f"external authority policy is invalid: {exc}") from exc
    required = {"schema_version", "policy_id", "tenant_id", "external_store_id",
                "external_store_sha256", "authority_organization_id", "authority_class",
                "purposes", "issued_at", "expires_at", "revoked"}
    if (not isinstance(policy, dict) or set(policy) != required or policy.get("schema_version") != "1.0" or
            policy.get("tenant_id") != tenant_id or policy.get("revoked") is not False):
        raise ExternalAuthorityError("external authority policy fields, tenant, or revocation state are invalid")
    if purpose not in {"independent-certification", "source-provenance"}:
        raise ExternalAuthorityError("external authority purpose is invalid")
    purposes = policy.get("purposes")
    if (not isinstance(purposes, list) or purpose not in purposes or len(purposes) != len(set(purposes)) or
            any(item not in {"independent-certification", "source-provenance"} for item in purposes)):
        raise ExternalAuthorityError("external authority policy does not allow the requested purpose")
    observed = datetime.now(timezone.utc)
    issued = parse_time(policy.get("issued_at"), "policy.issued_at")
    expires = parse_time(policy.get("expires_at"), "policy.expires_at")
    if not issued <= observed < expires:
        raise ExternalAuthorityError("external authority policy is outside its validity window")
    external = ActorTrustStore.load(external_trust_path)
    expected_store_purpose = ("external-certification" if purpose == "independent-certification"
                              else "source-provenance")
    expected_class = "certification-body" if purpose == "independent-certification" else "source-archive"
    if (external.schema_version != "2.0" or external.purpose != expected_store_purpose or
            external.store_id != policy.get("external_store_id") or external.digest != policy.get("external_store_sha256") or
            policy.get("authority_class") != expected_class):
        raise ExternalAuthorityError("external Trust Store differs from the approved exact authority tuple")
    organization = policy.get("authority_organization_id")
    if (not isinstance(organization, str) or not organization or not external.actors or
            any(actor.organization_id != organization or actor.authority_class != expected_class
                for actor in external.actors.values())):
        raise ExternalAuthorityError("external Trust Store actors do not belong to the approved authority organization")
    policy_sha = canonical_digest(policy)
    internal = ActorTrustStore.load(internal_trust_path)
    if internal.schema_version != "2.0" or internal.purpose != "workspace-actors":
        raise ExternalAuthorityError("external authority approval requires a version 2 workspace Trust Store")
    approver = internal.verify(approval, "external-trust-approver", {
        "policy_id": policy["policy_id"], "tenant_id": tenant_id, "policy_sha256": policy_sha,
        "external_store_sha256": external.digest, "purpose": purpose,
    })
    if not approver.get("organization_id") or approver["organization_id"] == organization:
        raise ExternalAuthorityError("external Trust Store approver must be organization-independent")
    return external, {
        "policy_id": policy["policy_id"], "policy_sha256": policy_sha,
        "purpose": purpose, "external_store_id": external.store_id,
        "external_store_sha256": external.digest, "authority_organization_id": organization,
        "authority_class": expected_class, "expires_at": policy["expires_at"],
        "approved_by": approver, "revoked": False,
    }

