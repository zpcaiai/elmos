"""Fail-closed request, identity and canonicalization tests."""

from __future__ import annotations

import unittest

from elmos_semantic_assurance.canonical import (
    CanonicalizationError,
    canonical_json,
    digest_value,
    require_bounded_json,
)
from elmos_semantic_assurance.contracts import SkillRequest, TrustedIdentity

import sys
from pathlib import Path

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from fixtures import make_identity, make_request_copy, make_request_document


class TestCanonicalContracts(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = make_identity()
        self.request_doc = make_request_document()

    def test_canonical_json_is_order_independent_and_digest_bound(self) -> None:
        left = {"z": [3, 2, 1], "a": {"enabled": True, "value": 4}}
        right = {"a": {"value": 4, "enabled": True}, "z": [3, 2, 1]}

        self.assertEqual(canonical_json(left), canonical_json(right))
        self.assertEqual(digest_value(left), digest_value(right))

    def test_non_finite_numbers_are_rejected(self) -> None:
        for number in [float("nan"), float("inf"), float("-inf")]:
            with self.subTest(number=number):
                with self.assertRaisesRegex(CanonicalizationError, "non-finite"):
                    canonical_json({"value": number})

    def test_request_size_is_bounded(self) -> None:
        with self.assertRaisesRegex(CanonicalizationError, "exceeds 64 bytes"):
            require_bounded_json({"payload": "x" * 128}, max_bytes=64)

    def test_request_depth_is_bounded(self) -> None:
        value: dict[str, object] = {}
        cursor = value
        for index in range(35):
            child: dict[str, object] = {}
            cursor[f"level{index}"] = child
            cursor = child

        with self.assertRaisesRegex(CanonicalizationError, "nesting exceeds 32"):
            canonical_json(value)

    def test_inline_secret_material_is_rejected(self) -> None:
        for field in ["password", "api_key", "private_key", "access_token"]:
            with self.subTest(field=field):
                document = make_request_copy()
                document["payload"][field] = "do-not-store-this"
                with self.assertRaisesRegex(CanonicalizationError, "inline secret material"):
                    SkillRequest.parse(document, self.identity)

    def test_opaque_secret_reference_is_allowed(self) -> None:
        parsed = SkillRequest.parse(self.request_doc, self.identity)
        self.assertEqual(parsed.payload["credential_ref"], "credential-001")

    def test_scope_must_match_trusted_identity(self) -> None:
        for scope_field, value in [("tenantId", "tenant-b"), ("projectId", "project-b")]:
            with self.subTest(scope_field=scope_field, value=value):
                document = make_request_copy()
                document["scope"][scope_field] = value
                with self.assertRaisesRegex(PermissionError, "trusted identity"):
                    SkillRequest.parse(document, self.identity)

    def test_actor_cannot_be_supplied_by_untrusted_request(self) -> None:
        document = make_request_copy()
        document["scope"]["actorId"] = "actor-attacker"

        with self.assertRaisesRegex(ValueError, "scope fields invalid"):
            SkillRequest.parse(document, self.identity)

    def test_untrusted_effect_authority_is_rejected(self) -> None:
        for effect in ["shell", "network", "provider-write", "repository-write", "certification"]:
            with self.subTest(effect=effect):
                document = make_request_copy()
                document["allowedEffects"] = [effect]
                with self.assertRaisesRegex(PermissionError, "cannot authorize effects"):
                    SkillRequest.parse(document, self.identity)

    def test_unknown_request_fields_fail_closed(self) -> None:
        document = make_request_copy()
        document["certificationStatus"] = "CERTIFIED"

        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            SkillRequest.parse(document, self.identity)

    def test_digest_changes_for_scope_or_payload_change(self) -> None:
        first = SkillRequest.parse(make_request_copy(), self.identity)
        changed_document = make_request_copy()
        changed_document["payload"]["model"]["nodes"].append("decimal128")
        changed = SkillRequest.parse(changed_document, self.identity)

        self.assertNotEqual(
            digest_value(first.to_digest_document("elmos-type-algebra")),
            digest_value(changed.to_digest_document("elmos-type-algebra")),
        )

    def test_identity_fields_are_validated(self) -> None:
        with self.assertRaisesRegex(CanonicalizationError, "actorId"):
            TrustedIdentity("tenant-a", "project-a", "actor with spaces")

        with self.assertRaisesRegex(CanonicalizationError, r"roles\[0\]"):
            TrustedIdentity(
                "tenant-a",
                "project-a",
                "actor-a",
                roles=("role with spaces",),
            )

        with self.assertRaisesRegex(ValueError, "must not contain duplicates"):
            TrustedIdentity(
                "tenant-a",
                "project-a",
                "actor-a",
                roles=("semantic-assurance:execute", "semantic-assurance:execute"),
            )

    def test_effect_authority_cannot_be_duplicated(self) -> None:
        document = make_request_copy()
        document["allowedEffects"] = ["artifact-write", "artifact-write"]

        with self.assertRaisesRegex(ValueError, "must not contain duplicates"):
            SkillRequest.parse(document, self.identity)


if __name__ == "__main__":
    unittest.main()
