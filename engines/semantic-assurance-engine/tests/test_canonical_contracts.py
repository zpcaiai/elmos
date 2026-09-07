"""Fail-closed request, identity and canonicalization tests."""

from __future__ import annotations

import pytest

from elmos_semantic_assurance.canonical import (
    CanonicalizationError,
    canonical_json,
    digest_value,
    require_bounded_json,
)
from elmos_semantic_assurance.contracts import SkillRequest, TrustedIdentity


def test_canonical_json_is_order_independent_and_digest_bound() -> None:
    left = {"z": [3, 2, 1], "a": {"enabled": True, "value": 4}}
    right = {"a": {"value": 4, "enabled": True}, "z": [3, 2, 1]}

    assert canonical_json(left) == canonical_json(right)
    assert digest_value(left) == digest_value(right)


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_rejected(number: float) -> None:
    with pytest.raises(CanonicalizationError, match="non-finite"):
        canonical_json({"value": number})


def test_request_size_is_bounded() -> None:
    with pytest.raises(CanonicalizationError, match="exceeds 64 bytes"):
        require_bounded_json({"payload": "x" * 128}, max_bytes=64)


def test_request_depth_is_bounded() -> None:
    value: dict[str, object] = {}
    cursor = value
    for index in range(35):
        child: dict[str, object] = {}
        cursor[f"level{index}"] = child
        cursor = child

    with pytest.raises(CanonicalizationError, match="nesting exceeds 32"):
        canonical_json(value)


@pytest.mark.parametrize("field", ["password", "api_key", "private_key", "access_token"])
def test_inline_secret_material_is_rejected(
    identity: TrustedIdentity,
    request_copy,
    field: str,
) -> None:
    document = request_copy()
    document["payload"][field] = "do-not-store-this"

    with pytest.raises(CanonicalizationError, match="inline secret material"):
        SkillRequest.parse(document, identity)


def test_opaque_secret_reference_is_allowed(
    identity: TrustedIdentity,
    request_document,
) -> None:
    parsed = SkillRequest.parse(request_document, identity)

    assert parsed.payload["credential_ref"] == "credential-001"


@pytest.mark.parametrize(
    ("scope_field", "value"),
    [("tenantId", "tenant-b"), ("projectId", "project-b")],
)
def test_scope_must_match_trusted_identity(
    identity: TrustedIdentity,
    request_copy,
    scope_field: str,
    value: str,
) -> None:
    document = request_copy()
    document["scope"][scope_field] = value

    with pytest.raises(PermissionError, match="trusted identity"):
        SkillRequest.parse(document, identity)


def test_actor_cannot_be_supplied_by_untrusted_request(
    identity: TrustedIdentity,
    request_copy,
) -> None:
    document = request_copy()
    document["scope"]["actorId"] = "actor-attacker"

    with pytest.raises(ValueError, match="scope fields invalid"):
        SkillRequest.parse(document, identity)


@pytest.mark.parametrize(
    "effect",
    ["shell", "network", "provider-write", "repository-write", "certification"],
)
def test_untrusted_effect_authority_is_rejected(
    identity: TrustedIdentity,
    request_copy,
    effect: str,
) -> None:
    document = request_copy()
    document["allowedEffects"] = [effect]

    with pytest.raises(PermissionError, match="cannot authorize effects"):
        SkillRequest.parse(document, identity)


def test_unknown_request_fields_fail_closed(
    identity: TrustedIdentity,
    request_copy,
) -> None:
    document = request_copy()
    document["certificationStatus"] = "CERTIFIED"

    with pytest.raises(ValueError, match="unsupported fields"):
        SkillRequest.parse(document, identity)


def test_digest_changes_for_scope_or_payload_change(
    identity: TrustedIdentity,
    request_copy,
) -> None:
    first = SkillRequest.parse(request_copy(), identity)
    changed_document = request_copy()
    changed_document["payload"]["model"]["nodes"].append("decimal128")
    changed = SkillRequest.parse(changed_document, identity)

    assert digest_value(first.to_digest_document("elmos-type-algebra")) != digest_value(
        changed.to_digest_document("elmos-type-algebra")
    )


def test_identity_fields_are_validated() -> None:
    with pytest.raises(CanonicalizationError, match="actorId"):
        TrustedIdentity("tenant-a", "project-a", "actor with spaces")

    with pytest.raises(CanonicalizationError, match=r"roles\[0\]"):
        TrustedIdentity(
            "tenant-a",
            "project-a",
            "actor-a",
            roles=("role with spaces",),
        )

    with pytest.raises(ValueError, match="must not contain duplicates"):
        TrustedIdentity(
            "tenant-a",
            "project-a",
            "actor-a",
            roles=("semantic-assurance:execute", "semantic-assurance:execute"),
        )


def test_effect_authority_cannot_be_duplicated(
    identity: TrustedIdentity,
    request_copy,
) -> None:
    document = request_copy()
    document["allowedEffects"] = ["artifact-write", "artifact-write"]

    with pytest.raises(ValueError, match="must not contain duplicates"):
        SkillRequest.parse(document, identity)
