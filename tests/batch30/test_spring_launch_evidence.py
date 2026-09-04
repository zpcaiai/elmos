from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from scripts.batch30.spring_launch_evidence import (
    APPROVER_ROLE,
    BUSINESS_LINE,
    DESIGN_PARTNER_ROLE,
    EXECUTOR_ROLE,
    GATE_IDS,
    INDEX_AUTHORITY_ROLE,
    NAMESPACE,
    PROFILE,
    REVIEWER_ROLE,
    ROUTE_ID,
    VERIFIER_ROLE,
    SpringLaunchEvidenceError,
    VerifiedEnvelope,
    _immutable_uri,
    _load_trust,
    _register_signer,
    _write_new_owner_only,
    assemble_spring_launch_receipt,
    content_reference,
    receipt_digest,
    verify_spring_launch_receipt,
    verify_spring_launch_receipt_file,
)
from scripts.precision_migration.trust import (
    TrustStore,
    canonical_bytes,
    canonical_digest,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/batch30/spring_launch_evidence.py"


class SpringLaunchEvidenceTests(unittest.TestCase):
    def test_reference_binds_existing_bytes_below_an_explicit_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            evidence_root = Path(temporary).resolve()
            evidence = evidence_root / "staging-report.json"
            payload = b'{"outcome":"PASSED_EXTERNAL"}'
            evidence.write_bytes(payload)

            reference = content_reference(
                evidence,
                evidence_roots=[evidence_root],
                media_type="application/json",
            )

        self.assertEqual("file://" + str(evidence), reference["uri"])
        self.assertEqual("sha256:" + hashlib.sha256(payload).hexdigest(), reference["digest"])
        self.assertEqual(len(payload), reference["size_bytes"])

    def test_reference_rejects_paths_outside_the_approved_root(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            evidence = Path(first).resolve() / "evidence.bin"
            evidence.write_bytes(b"external evidence")
            with self.assertRaisesRegex(SpringLaunchEvidenceError, "approved evidence roots"):
                content_reference(evidence, evidence_roots=[Path(second).resolve()])

    def test_receipt_digest_is_canonical_and_excludes_its_own_field(self) -> None:
        left = {"z": 1, "a": {"b": 2}}
        right = {"a": {"b": 2}, "receipt_digest": "ignored", "z": 1}
        self.assertEqual(receipt_digest(left), receipt_digest(right))
        self.assertRegex(receipt_digest(left), r"^sha256:[0-9a-f]{64}$")

    def test_verify_cli_rejects_unsigned_placeholder_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            receipt = root / "receipt.json"
            trust = root / "trust.json"
            receipt.write_text(json.dumps({"schema_version": 1}) + "\n", encoding="utf-8")
            trust.write_text(json.dumps({"schema_version": 1, "keys": []}) + "\n", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "verify",
                    str(receipt),
                    "--trust-store",
                    str(trust),
                    "--evidence-root",
                    str(root),
                    "--expected-trust-store-digest",
                    "sha256:" + "0" * 64,
                    "--expected-environment-id",
                    "staging-one",
                    "--expected-deployment-id",
                    "deployment-one",
                    "--expected-provider",
                    "private-linux",
                    "--expected-region",
                    "cn-test-one",
                    "--expected-environment-class",
                    "STAGING",
                    "--expected-configuration-digest",
                    "sha256:" + "1" * 64,
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(2, completed.returncode)
        self.assertIn("SPRING LAUNCH EVIDENCE FAIL", completed.stderr)
        self.assertIn("receipt fields are invalid", completed.stderr)


class SignedSpringLaunchReceiptTests(unittest.TestCase):
    NOW = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
    REVISION = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    KEY_SPECS = {
        "executor": (EXECUTOR_ROLE, "executor-actor", "executor-org"),
        "verifier": (VERIFIER_ROLE, "verifier-actor", "verifier-org"),
        "reviewer": (REVIEWER_ROLE, "reviewer-actor", "reviewer-org"),
        "release": (APPROVER_ROLE, "release-actor", "release-org"),
        "risk": (APPROVER_ROLE, "risk-actor", "risk-org"),
        "partner-a": (DESIGN_PARTNER_ROLE, "partner-a-actor", "partner-a-org"),
        "partner-b": (DESIGN_PARTNER_ROLE, "partner-b-actor", "partner-b-org"),
        "index": (INDEX_AUTHORITY_ROLE, "index-actor", "index-org"),
    }
    SIGNATURE_CACHE: dict[tuple[str, bytes], str] = {}

    @classmethod
    def setUpClass(cls) -> None:
        cls.key_directory = tempfile.TemporaryDirectory(prefix="spring-launch-keys-")
        cls.key_root = Path(cls.key_directory.name)
        cls.private_keys = {}
        cls.public_keys = {}
        for name in cls.KEY_SPECS:
            private_key = cls.key_root / f"{name}.private.pem"
            public_key = cls.key_root / f"{name}.public.pem"
            subprocess.run(
                ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
                check=True,
                capture_output=True,
            )
            cls.private_keys[name] = private_key
            cls.public_keys[name] = public_key

    @classmethod
    def tearDownClass(cls) -> None:
        cls.key_directory.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="spring-launch-case-")
        self.case = Path(self.temporary.name).resolve()
        self.evidence_root = self.case / "evidence"
        self.evidence_root.mkdir()
        self.trust_root = self.case / "trust"
        (self.trust_root / "keys").mkdir(parents=True)
        for name, public_key in self.public_keys.items():
            (self.trust_root / "keys" / f"{name}.pem").write_bytes(public_key.read_bytes())
        self.trust_path = self.trust_root / "trust.json"
        self.write_json(
            self.trust_path,
            {
                "schema_version": 1,
                "namespace": NAMESPACE,
                "keys": [
                    {
                        "key_id": f"key-{name}",
                        "actor_id": actor,
                        "organization_id": organization,
                        "roles": [role],
                        "public_key_path": f"keys/{name}.pem",
                        "not_before": "2026-01-01T00:00:00Z",
                        "not_after": "2027-01-01T00:00:00Z",
                        "revoked": False,
                    }
                    for name, (role, actor, organization) in self.KEY_SPECS.items()
                ],
                "revoked_record_ids": [],
            },
        )
        os.chmod(self.trust_path, 0o600)
        self.signature_number = 0

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def write_json(path: Path, value: object, *, canonical: bool = False) -> None:
        if canonical:
            path.write_bytes(canonical_bytes(value))
        else:
            path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")

    def ref(self, path: Path, media_type: str = "application/json") -> dict[str, object]:
        return content_reference(
            path,
            evidence_roots=[self.evidence_root],
            media_type=media_type,
        )

    def sign(self, key_name: str, payload: dict[str, object]) -> dict[str, object]:
        payload_bytes = canonical_bytes(payload)
        cache_key = (key_name, payload_bytes)
        cached_signature = self.SIGNATURE_CACHE.get(cache_key)
        if cached_signature is not None:
            return {
                "algorithm": "ed25519",
                "key_id": f"key-{key_name}",
                "payload": payload,
                "signature": cached_signature,
            }
        self.signature_number += 1
        payload_path = self.case / f"payload-{self.signature_number}.json"
        signature_path = self.case / f"signature-{self.signature_number}.bin"
        payload_path.write_bytes(payload_bytes)
        subprocess.run(
            [
                "openssl", "pkeyutl", "-sign", "-inkey", str(self.private_keys[key_name]),
                "-rawin", "-in", str(payload_path), "-out", str(signature_path),
            ],
            check=True,
            capture_output=True,
        )
        encoded_signature = base64.b64encode(signature_path.read_bytes()).decode("ascii")
        self.SIGNATURE_CACHE[cache_key] = encoded_signature
        return {
            "algorithm": "ed25519",
            "key_id": f"key-{key_name}",
            "payload": payload,
            "signature": encoded_signature,
        }

    @staticmethod
    def fixture_envelope(
        key_name: str, payload: dict[str, object]
    ) -> dict[str, object]:
        """Build a shape-only envelope for tests that fail before crypto intake."""

        return {
            "algorithm": "ed25519",
            "key_id": f"key-{key_name}",
            "payload": payload,
            "signature": base64.b64encode(b"\0" * 64).decode("ascii"),
        }

    def make_receipt(
        self,
        *,
        controlled_index: bool = False,
        real_signatures: bool = False,
        sampled_signatures: bool = False,
    ) -> dict[str, object]:
        if real_signatures and sampled_signatures:
            raise ValueError("fixture cannot request both real and sampled signatures")
        sampled_keys: set[str] = set()

        def sampled_signer(
            key_name: str, payload: dict[str, object]
        ) -> dict[str, object]:
            if key_name not in sampled_keys:
                sampled_keys.add(key_name)
                return self.sign(key_name, payload)
            return self.fixture_envelope(key_name, payload)

        sign_envelope = (
            self.sign
            if real_signatures
            else sampled_signer
            if sampled_signatures
            else self.fixture_envelope
        )
        profile = self.evidence_root / "profile.json"
        profile.write_bytes(PROFILE.read_bytes())
        artifact = self.evidence_root / "artifact.jar"
        artifact.write_bytes(b"exact deployed artifact bytes")
        profile_ref = self.ref(profile)
        artifact_ref = self.ref(artifact, "application/java-archive")
        environment_value = {
            "schema_version": 1,
            "namespace": NAMESPACE,
            "environment_id": "staging-one",
            "deployment_id": "deployment-one",
            "environment_class": "STAGING",
            "provider": "private-linux",
            "region": "cn-test-one",
            "tenant_mode": "MULTI_TENANT",
            "execution_plane": "PRIVATE_ROOTLESS_RUNNER_BROKER",
            "deployed_revision": self.REVISION,
            "launch_profile_digest": profile_ref["digest"],
            "artifact_digest": artifact_ref["digest"],
            "configuration_digest": "sha256:" + "1" * 64,
            "network_policy_digest": "sha256:" + "2" * 64,
            "rootless_policy_digest": "sha256:" + "3" * 64,
            "runtime_image_digests": {
                "proxy": "sha256:" + "4" * 64,
                "transformer": "sha256:" + "5" * 64,
                "runner": "sha256:" + "6" * 64,
            },
            "captured_at": "2026-09-04T08:50:00Z",
            "secrets_embedded": False,
        }
        environment = self.evidence_root / "environment.json"
        self.write_json(environment, environment_value, canonical=True)
        binding = {
            "deployed_revision": self.REVISION,
            "launch_profile": profile_ref,
            "artifact": artifact_ref,
            "environment": self.ref(environment),
        }
        binding_digest = canonical_digest(binding)
        receipt_id = "spring-launch-one"
        gate_refs = []
        for index, gate_id in enumerate(GATE_IDS):
            path = self.evidence_root / f"gate-{index}.json"
            path.write_text(json.dumps({"gate": gate_id, "sequence": index}) + "\n")
            reference = self.ref(path)
            gate_refs.append(
                {
                    **reference,
                    "verification": {"mode": "LOCAL_BYTES", "local_uri": reference["uri"]},
                }
            )

        evidence_index = None
        index_envelope = None
        index_digest = None
        if controlled_index:
            first = gate_refs[0]
            remote_uri = "s3://spring-evidence/staging.json?versionId=one"
            entry = {
                "entry_id": "staging-entry",
                "uri": remote_uri,
                "digest": first["digest"],
                "size_bytes": first["size_bytes"],
                "media_type": first["media_type"],
                "recorded_at": "2026-09-04T08:45:00Z",
            }
            index_value = {
                "schema_version": 1,
                "namespace": NAMESPACE,
                "index_id": "index-one",
                "generated_at": "2026-09-04T08:55:00Z",
                "entries": [entry],
            }
            index_file = self.evidence_root / "index.json"
            self.write_json(index_file, index_value, canonical=True)
            index_ref = self.ref(index_file)
            index_envelope = sign_envelope(
                "index",
                {
                    "record_id": "index-record",
                    "issued_at": "2026-09-04T09:01:00Z",
                    "expires_at": "2026-09-05T10:00:00Z",
                    "actor_id": "index-actor",
                    "organization_id": "index-org",
                    "role": INDEX_AUTHORITY_ROLE,
                    "receipt_id": receipt_id,
                    "binding_digest": binding_digest,
                    "index_id": "index-one",
                    "index_content_digest": index_ref["digest"],
                    "index_content_size_bytes": index_ref["size_bytes"],
                    "outcome": "INDEX_AUTHENTICATED",
                    "synthetic": False,
                    "unknowns": [],
                    "not_run": [],
                },
            )
            evidence_index = {"content": index_ref, "attestation": index_envelope}
            gate_refs[0] = {
                "uri": remote_uri,
                "digest": first["digest"],
                "size_bytes": first["size_bytes"],
                "media_type": first["media_type"],
                "verification": {
                    "mode": "CONTROLLED_INDEX",
                    "entry_id": "staging-entry",
                    "entry_digest": canonical_digest(entry),
                },
            }
            index_digest = index_ref["digest"]

        evidence_set_digest = canonical_digest(
            {
                "receipt_id": receipt_id,
                "binding_digest": binding_digest,
                "observed_at": "2026-09-04T09:00:00Z",
                "controlled_index_content_digest": index_digest,
                "gates": [
                    {"id": gate, "status": "PASSED_EXTERNAL", "evidence": gate_refs[index]}
                    for index, gate in enumerate(GATE_IDS)
                ],
            }
        )
        gates = []
        gate_envelope_digests = []
        for index, gate_id in enumerate(GATE_IDS):
            reference = gate_refs[index]
            common = {
                "receipt_id": receipt_id,
                "binding_digest": binding_digest,
                "evidence_set_digest": evidence_set_digest,
                "gate_id": gate_id,
                "evidence_uri": reference["uri"],
                "evidence_digest": reference["digest"],
                "evidence_size_bytes": reference["size_bytes"],
                "outcome": "PASSED_EXTERNAL",
                "evidence_class": "EXTERNAL_NON_SYNTHETIC",
                "synthetic": False,
                "unknowns": [],
                "not_run": [],
            }
            execution_payload = {
                "record_id": f"execution-{index}",
                "issued_at": "2026-09-04T09:05:00Z",
                "expires_at": "2026-09-05T10:00:00Z",
                "actor_id": "executor-actor",
                "organization_id": "executor-org",
                "role": EXECUTOR_ROLE,
                **common,
            }
            execution = sign_envelope("executor", execution_payload)
            verification = sign_envelope(
                "verifier",
                {
                    "record_id": f"verification-{index}",
                    "issued_at": "2026-09-04T09:10:00Z",
                    "expires_at": "2026-09-05T10:00:00Z",
                    "actor_id": "verifier-actor",
                    "organization_id": "verifier-org",
                    "role": VERIFIER_ROLE,
                    **common,
                    "execution_record_id": execution_payload["record_id"],
                    "execution_payload_digest": canonical_digest(execution_payload),
                },
            )
            gates.append(
                {
                    "id": gate_id,
                    "status": "PASSED_EXTERNAL",
                    "evidence": reference,
                    "execution_attestation": execution,
                    "verification_attestation": verification,
                }
            )
            gate_envelope_digests.append(
                {
                    "gate_id": gate_id,
                    "execution_envelope_digest": canonical_digest(execution),
                    "verification_envelope_digest": canonical_digest(verification),
                }
            )

        approvals = []
        for key_name, scope in (("release", "RELEASE_AUTHORIZATION"), ("risk", "RISK_ACCEPTANCE")):
            _, actor, organization = self.KEY_SPECS[key_name]
            approvals.append(
                sign_envelope(
                    key_name,
                    {
                        "record_id": f"approval-{key_name}",
                        "issued_at": "2026-09-04T09:15:00Z",
                        "expires_at": "2026-09-05T10:00:00Z",
                        "actor_id": actor,
                        "organization_id": organization,
                        "role": APPROVER_ROLE,
                        "receipt_id": receipt_id,
                        "binding_digest": binding_digest,
                        "evidence_set_digest": evidence_set_digest,
                        "approval_scope": scope,
                        "outcome": "APPROVED",
                        "synthetic": False,
                        "unknowns": [],
                        "not_run": [],
                    },
                )
            )
        partners = []
        for key_name in ("partner-a", "partner-b"):
            _, actor, organization = self.KEY_SPECS[key_name]
            partners.append(
                sign_envelope(
                    key_name,
                    {
                        "record_id": f"acceptance-{key_name}",
                        "issued_at": "2026-09-04T09:15:00Z",
                        "expires_at": "2026-09-05T10:00:00Z",
                        "actor_id": actor,
                        "organization_id": organization,
                        "role": DESIGN_PARTNER_ROLE,
                        "receipt_id": receipt_id,
                        "binding_digest": binding_digest,
                        "evidence_set_digest": evidence_set_digest,
                        "partner_organization_id": organization,
                        "outcome": "ACCEPTED",
                        "synthetic": False,
                        "unknowns": [],
                        "not_run": [],
                    },
                )
            )
        review_subject_digest = canonical_digest(
            {
                "receipt_id": receipt_id,
                "binding_digest": binding_digest,
                "evidence_set_digest": evidence_set_digest,
                "controlled_index_attestation_digest": (
                    canonical_digest(index_envelope) if index_envelope else None
                ),
                "gate_attestations": gate_envelope_digests,
                "approval_envelope_digests": sorted(canonical_digest(item) for item in approvals),
                "design_partner_envelope_digests": sorted(canonical_digest(item) for item in partners),
            }
        )
        review = sign_envelope(
            "reviewer",
            {
                "record_id": "review-record",
                "issued_at": "2026-09-04T09:20:00Z",
                "expires_at": "2026-09-05T10:00:00Z",
                "actor_id": "reviewer-actor",
                "organization_id": "reviewer-org",
                "role": REVIEWER_ROLE,
                "receipt_id": receipt_id,
                "binding_digest": binding_digest,
                "evidence_set_digest": evidence_set_digest,
                "review_subject_digest": review_subject_digest,
                "outcome": "REVIEWED",
                "synthetic": False,
                "unknowns": [],
                "not_run": [],
            },
        )
        receipt = {
            "schema_version": 1,
            "namespace": NAMESPACE,
            "receipt_id": receipt_id,
            "business_line": BUSINESS_LINE,
            "route_id": ROUTE_ID,
            "observed_at": "2026-09-04T09:00:00Z",
            "binding": binding,
            "binding_digest": binding_digest,
            "principals": {
                "execution": {"actor_id": "executor-actor", "organization_id": "executor-org"},
                "independent_verifier": {"actor_id": "verifier-actor", "organization_id": "verifier-org"},
                "independent_reviewer": {"actor_id": "reviewer-actor", "organization_id": "reviewer-org"},
            },
            "evidence_index": evidence_index,
            "gates": gates,
            "approvals": approvals,
            "design_partner_acceptances": partners,
            "independent_review": review,
        }
        receipt["receipt_digest"] = receipt_digest(receipt)
        return receipt

    def verify(
        self, receipt: dict[str, object], **options: object
    ) -> dict[str, object]:
        return verify_spring_launch_receipt(
            receipt,
            trust_store=self.trust_path,
            evidence_roots=[self.evidence_root],
            expected_revision=self.REVISION,
            now=self.NOW,
            **options,
        )

    @staticmethod
    def _verify_without_process(
            store: TrustStore,
            envelope: dict[str, object],
            *,
            required_role: str,
            bindings: dict[str, object],
            now: datetime | None = None,
        ) -> dict[str, object]:
        payload = envelope["payload"]
        for field, expected in bindings.items():
            if type(payload.get(field)) is not type(expected) or payload.get(field) != expected:
                raise ValueError(f"signed envelope binding mismatch: {field}")
        return {
            "record_id": payload["record_id"],
            "key_id": envelope["key_id"],
            "role": required_role,
            "payload_digest": canonical_digest(payload),
            "trust_store_digest": store.digest,
        }

    @classmethod
    def fast_signature_verification(cls) -> mock._patch:

        return mock.patch.object(
            TrustStore,
            "verify_envelope",
            autospec=True,
            side_effect=cls._verify_without_process,
        )

    @classmethod
    def sampled_signature_verification(cls) -> mock._patch:
        original_verify = TrustStore.verify_envelope
        verified_keys: set[str] = set()

        def verify_sample(
            store: TrustStore,
            envelope: dict[str, object],
            *,
            required_role: str,
            bindings: dict[str, object],
            now: datetime | None = None,
        ) -> dict[str, object]:
            key_id = str(envelope["key_id"])
            if key_id not in verified_keys:
                verified_keys.add(key_id)
                return original_verify(
                    store,
                    envelope,
                    required_role=required_role,
                    bindings=bindings,
                    now=now,
                )
            return cls._verify_without_process(
                store,
                envelope,
                required_role=required_role,
                bindings=bindings,
                now=now,
            )

        return mock.patch.object(
            TrustStore,
            "verify_envelope",
            autospec=True,
            side_effect=verify_sample,
        )

    def test_complete_receipt_verifies_but_does_not_certify(self) -> None:
        trust_digest = _load_trust(self.trust_path).store.digest
        with self.sampled_signature_verification():
            result = self.verify(
                self.make_receipt(controlled_index=True, sampled_signatures=True),
                expected_trust_store_digest=trust_digest,
                expected_environment_id="staging-one",
                expected_deployment_id="deployment-one",
                expected_provider="private-linux",
                expected_region="cn-test-one",
                expected_environment_class="STAGING",
                expected_configuration_digest="sha256:" + "1" * 64,
            )
        self.assertEqual("VERIFIED_EXTERNAL_RECEIPT", result["evidence_status"])
        self.assertEqual("NOT_CERTIFIED", result["certification"])
        self.assertFalse(result["certification_promoted"])
        self.assertEqual(list(GATE_IDS), result["verified_gate_ids"])
        self.assertEqual("sha256:" + "1" * 64, result["configuration_digest"])
        self.assertEqual("staging-one", result["environment_id"])

        with self.assertRaisesRegex(SpringLaunchEvidenceError, "expected trust store digest"):
            self.verify(
                self.make_receipt(),
                expected_trust_store_digest="sha256:" + "0" * 64,
            )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "expected environment_id"):
            self.verify(
                self.make_receipt(),
                expected_environment_id="different-environment",
            )

    def test_launch_profile_must_match_the_committed_revision(self) -> None:
        receipt = self.make_receipt()
        with mock.patch(
            "scripts.batch30.spring_launch_evidence.read_regular_file_once",
            return_value=b"dirty working-tree profile",
        ):
            with self.assertRaisesRegex(
                SpringLaunchEvidenceError,
                "working-tree bytes do not match the expected revision",
            ):
                self.verify(receipt)

    def test_signed_controlled_index_closes_remote_evidence(self) -> None:
        with self.fast_signature_verification():
            result = self.verify(self.make_receipt(controlled_index=True))
        self.assertEqual("VALIDATED_NOT_CERTIFIED", result["external_evidence_intake"])

    def test_receipt_and_supporting_schemas_accept_fixture(self) -> None:
        from jsonschema import Draft202012Validator

        for name in (
            "spring-launch-external-evidence.schema.json",
            "spring-launch-trust-store.schema.json",
            "spring-launch-evidence-index.schema.json",
            "spring-launch-environment-manifest.schema.json",
        ):
            schema = json.loads((ROOT / "schemas" / "batch30" / name).read_text())
            Draft202012Validator.check_schema(schema)
        receipt = self.make_receipt(controlled_index=True)
        schema = json.loads(
            (ROOT / "schemas/batch30/spring-launch-external-evidence.schema.json").read_text()
        )
        Draft202012Validator(schema).validate(receipt)

    def test_tampered_evidence_bytes_and_signature_fail_closed(self) -> None:
        receipt = self.make_receipt()
        evidence_path = Path(
            receipt["gates"][0]["evidence"]["verification"]["local_uri"].removeprefix("file://")
        )
        evidence_path.write_bytes(evidence_path.read_bytes() + b"tampered")
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "byte count mismatch"):
            self.verify(receipt)

        receipt = self.make_receipt()
        receipt["gates"][0]["execution_attestation"] = self.sign(
            "executor",
            copy.deepcopy(receipt["gates"][0]["execution_attestation"]["payload"]),
        )
        receipt["gates"][0]["verification_attestation"]["signature"] = base64.b64encode(
            b"x" * 64
        ).decode("ascii")
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "signature verification failed"):
            self.verify(receipt)

    def test_revision_freshness_order_and_approval_counts_fail_closed(self) -> None:
        receipt = self.make_receipt()
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "expected repository revision"):
            verify_spring_launch_receipt(
                receipt,
                trust_store=self.trust_path,
                evidence_roots=[self.evidence_root],
                expected_revision="b" * 40,
                now=self.NOW,
            )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "stale"):
            verify_spring_launch_receipt(
                receipt,
                trust_store=self.trust_path,
                evidence_roots=[self.evidence_root],
                expected_revision=self.REVISION,
                now=self.NOW + timedelta(days=5),
            )
        receipt["gates"][0], receipt["gates"][1] = receipt["gates"][1], receipt["gates"][0]
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "must be STAGING_DEPLOYMENT"):
            self.verify(receipt)
        receipt = self.make_receipt()
        receipt["approvals"] = receipt["approvals"][:1]
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "two signed external approvals"):
            with self.fast_signature_verification():
                self.verify(receipt)

    def test_approval_organizations_are_external_and_distinct(self) -> None:
        receipt = self.make_receipt()
        trust = json.loads(self.trust_path.read_text())
        for key in trust["keys"]:
            if key["key_id"] == "key-risk":
                key["organization_id"] = "release-org"
        self.write_json(self.trust_path, trust)
        risk_payload = receipt["approvals"][1]["payload"]
        risk_payload["organization_id"] = "release-org"
        receipt["approvals"][1] = self.fixture_envelope("risk", risk_payload)
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "two distinct organizations"):
            with self.fast_signature_verification():
                self.verify(receipt)

    def test_design_partners_require_distinct_signed_organizations(self) -> None:
        receipt = self.make_receipt()
        trust = json.loads(self.trust_path.read_text())
        for key in trust["keys"]:
            if key["key_id"] == "key-partner-b":
                key["organization_id"] = "partner-a-org"
        self.write_json(self.trust_path, trust)
        partner_payload = receipt["design_partner_acceptances"][1]["payload"]
        partner_payload["organization_id"] = "partner-a-org"
        partner_payload["partner_organization_id"] = "partner-a-org"
        receipt["design_partner_acceptances"][1] = self.fixture_envelope(
            "partner-b", partner_payload
        )
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "two distinct organizations"):
            with self.fast_signature_verification():
                self.verify(receipt)

    def test_strict_json_rejects_duplicate_receipt_and_trust_keys(self) -> None:
        receipt = self.make_receipt()
        receipt_file = self.evidence_root / "duplicate-receipt.json"
        raw_receipt = json.dumps(receipt, sort_keys=True)
        raw_receipt = raw_receipt.replace(
            '"schema_version": 1',
            '"schema_version": 1, "schema_version": 1',
            1,
        )
        receipt_file.write_text(raw_receipt, encoding="utf-8")
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "duplicate object key"):
            verify_spring_launch_receipt_file(
                receipt_file,
                trust_store=self.trust_path,
                evidence_roots=[self.evidence_root],
                expected_revision=self.REVISION,
                now=self.NOW,
            )

        trust_bytes = self.trust_path.read_text(encoding="utf-8")
        namespace_field = f'"namespace": "{NAMESPACE}"'
        trust_bytes = trust_bytes.replace(
            namespace_field,
            f'{namespace_field}, {namespace_field}',
            1,
        )
        self.trust_path.write_text(trust_bytes, encoding="utf-8")
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "duplicate object key"):
            self.verify(receipt)

    def test_crypto_rejects_short_signatures_and_mislabeled_rsa_keys(self) -> None:
        receipt = self.make_receipt()
        receipt["gates"][0]["execution_attestation"]["signature"] = base64.b64encode(
            b"short"
        ).decode("ascii")
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "exactly 64 bytes"):
            self.verify(receipt)

        receipt = self.make_receipt()
        rsa_private = self.case / "rsa-private.pem"
        rsa_public = self.trust_root / "keys" / "executor.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(rsa_private)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(rsa_private), "-pubout", "-out", str(rsa_public)],
            check=True,
            capture_output=True,
        )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "must be an Ed25519"):
            self.verify(receipt)

    def test_canonical_spki_detects_same_key_with_different_pem_encoding(self) -> None:
        receipt = self.make_receipt()
        executor_pem = self.public_keys["executor"].read_text(encoding="ascii")
        body = "".join(
            line
            for line in executor_pem.splitlines()
            if not line.startswith("-----")
        )
        rewrapped = "-----BEGIN PUBLIC KEY-----\n"
        rewrapped += "\n".join(body[index:index + 32] for index in range(0, len(body), 32))
        rewrapped += "\n-----END PUBLIC KEY-----\n"
        (self.trust_root / "keys" / "verifier.pem").write_text(
            rewrapped, encoding="ascii"
        )
        verification = self.fixture_envelope(
            "verifier",
            copy.deepcopy(receipt["gates"][0]["verification_attestation"]["payload"]),
        )
        receipt["gates"][0]["verification_attestation"] = verification
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "public-key material was reused"):
            with self.fast_signature_verification():
                self.verify(receipt)

    def test_environment_and_controlled_index_freshness_fail_closed(self) -> None:
        receipt = self.make_receipt()
        environment_path = Path(
            receipt["binding"]["environment"]["uri"].removeprefix("file://")
        )
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
        environment["captured_at"] = "2026-08-01T00:00:00Z"
        self.write_json(environment_path, environment, canonical=True)
        receipt["binding"]["environment"] = self.ref(environment_path)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "capture is older"):
            self.verify(receipt)

        receipt = self.make_receipt(controlled_index=True)
        index_path = Path(
            receipt["evidence_index"]["content"]["uri"].removeprefix("file://")
        )
        index_value = json.loads(index_path.read_text(encoding="utf-8"))
        index_value["generated_at"] = "2026-08-01T00:00:00Z"
        index_value["entries"][0]["recorded_at"] = "2026-08-01T00:00:00Z"
        self.write_json(index_path, index_value, canonical=True)
        receipt["evidence_index"]["content"] = self.ref(index_path)
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "index is older"):
            self.verify(receipt)

    def test_placeholders_and_bool_integer_confusion_fail_closed(self) -> None:
        receipt = self.make_receipt()
        receipt["principals"]["execution"]["actor_id"] = "CHANGE_ME_ACTOR"
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "placeholder sentinel"):
            self.verify(receipt)

        receipt = self.make_receipt()
        receipt["schema_version"] = True
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "receipt identity"):
            self.verify(receipt)

        receipt = self.make_receipt()
        environment_path = Path(
            receipt["binding"]["environment"]["uri"].removeprefix("file://")
        )
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
        environment["secrets_embedded"] = 0
        self.write_json(environment_path, environment, canonical=True)
        receipt["binding"]["environment"] = self.ref(environment_path)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "exactly false"):
            self.verify(receipt)

        receipt = self.make_receipt()
        execution_payload = copy.deepcopy(
            receipt["gates"][0]["execution_attestation"]["payload"]
        )
        execution_payload["synthetic"] = 0
        receipt["gates"][0]["execution_attestation"]["payload"] = execution_payload
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "synthetic must be false"):
            self.verify(receipt)

    def test_controlled_index_rejects_local_and_mismatched_digest_uris(self) -> None:
        receipt = self.make_receipt(controlled_index=True)
        receipt["gates"][0]["evidence"]["uri"] = (
            self.evidence_root / "gate-0.json"
        ).as_uri()
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "cannot authorize a file URI"):
            with self.fast_signature_verification():
                self.verify(receipt)

        from jsonschema import Draft202012Validator

        schema = json.loads(
            (ROOT / "schemas/batch30/spring-launch-external-evidence.schema.json").read_text()
        )
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(receipt)))

        receipt = self.make_receipt(controlled_index=True)
        receipt["gates"][0]["evidence"]["uri"] += "&sha256=" + "0" * 64
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "digest query pin must equal"):
            with self.fast_signature_verification():
                self.verify(receipt)

        with self.assertRaisesRegex(SpringLaunchEvidenceError, "mutable or placeholder"):
            _immutable_uri(
                "s3://spring-evidence/staging.json?versionId=latest",
                "sha256:" + "1" * 64,
                "test evidence URI",
            )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "mutable or placeholder"):
            _immutable_uri(
                "s3://spring-evidence/staging.json?versionId=CHANGE_ME",
                "sha256:" + "1" * 64,
                "test evidence URI",
            )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "digest query pin must equal"):
            _immutable_uri(
                "https://evidence.example/staging.json?sha256="
                + "1" * 64
                + "&SHA256="
                + "0" * 64,
                "sha256:" + "1" * 64,
                "test evidence URI",
            )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "invalid length"):
            _immutable_uri(
                "s3://spring-evidence/staging.json?versionId=%20",
                "sha256:" + "1" * 64,
                "test evidence URI",
            )

    def test_trust_store_requires_owner_only_out_of_band_file(self) -> None:
        receipt = self.make_receipt()
        os.chmod(self.trust_path, 0o644)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "owner-only mode"):
            self.verify(receipt)

        inside = self.evidence_root / "trust.json"
        inside.write_bytes(self.trust_path.read_bytes())
        os.chmod(inside, 0o600)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "outside all evidence roots"):
            verify_spring_launch_receipt(
                receipt,
                trust_store=inside,
                evidence_roots=[self.evidence_root],
                expected_revision=self.REVISION,
                now=self.NOW,
            )

    def test_openat_reference_and_assemble_output_reject_symlink_or_repo_paths(self) -> None:
        real_directory = self.case / "real-evidence"
        real_directory.mkdir()
        evidence = real_directory / "report.bin"
        evidence.write_bytes(b"evidence")
        linked_directory = self.case / "linked-evidence"
        linked_directory.symlink_to(real_directory, target_is_directory=True)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "canonical"):
            content_reference(
                linked_directory / "report.bin",
                evidence_roots=[self.case],
            )

        with self.assertRaisesRegex(SpringLaunchEvidenceError, "outside the repository"):
            _write_new_owner_only(
                ROOT / "spring-launch-receipt-should-not-exist.json",
                b"{}\n",
            )

        output_parent = self.case / "safe-output"
        output_parent.mkdir(mode=0o700)
        linked_parent = self.case / "linked-output"
        linked_parent.symlink_to(output_parent, target_is_directory=True)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "ancestors"):
            _write_new_owner_only(linked_parent / "receipt.json", b"{}\n")

        failed_output = output_parent / "failed-receipt.json"
        with mock.patch(
            "scripts.batch30.spring_launch_evidence.os.write", return_value=0
        ):
            with self.assertRaisesRegex(SpringLaunchEvidenceError, "no forward progress"):
                _write_new_owner_only(failed_output, b"{}\n")
        self.assertFalse(failed_output.exists())

    def test_global_actor_and_organization_roles_cannot_overlap(self) -> None:
        def verified(
            *, actor: str, organization: str, role: str, record_id: str
        ) -> VerifiedEnvelope:
            return VerifiedEnvelope(
                payload={"record_id": record_id},
                key_id=f"key-{record_id}",
                actor_id=actor,
                organization_id=organization,
                role=role,
                public_key_digest="sha256:" + hashlib.sha256(record_id.encode()).hexdigest(),
                payload_digest="sha256:" + "1" * 64,
                envelope_digest="sha256:" + "2" * 64,
                issued_at=self.NOW,
            )

        controls = {
            "record_ids": set(),
            "key_owners": {},
            "public_key_owners": {},
            "actor_roles": {},
            "organization_roles": {},
        }
        _register_signer(
            verified(
                actor="approval-actor",
                organization="shared-org",
                role=APPROVER_ROLE,
                record_id="approval-record",
            ),
            **controls,
        )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "organization cannot occupy"):
            _register_signer(
                verified(
                    actor="partner-actor",
                    organization="shared-org",
                    role=DESIGN_PARTNER_ROLE,
                    record_id="partner-record",
                ),
                **controls,
            )

        actor_controls = {
            "record_ids": set(),
            "key_owners": {},
            "public_key_owners": {},
            "actor_roles": {},
            "organization_roles": {},
        }
        _register_signer(
            verified(
                actor="shared-actor",
                organization="approval-org",
                role=APPROVER_ROLE,
                record_id="actor-approval-record",
            ),
            **actor_controls,
        )
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "actor identity cannot occupy"):
            _register_signer(
                verified(
                    actor="shared-actor",
                    organization="partner-org",
                    role=DESIGN_PARTNER_ROLE,
                    record_id="actor-partner-record",
                ),
                **actor_controls,
            )

    def test_review_must_follow_controlled_index_attestation(self) -> None:
        receipt = self.make_receipt(controlled_index=True)
        index_payload = copy.deepcopy(receipt["evidence_index"]["attestation"]["payload"])
        index_payload["issued_at"] = "2026-09-04T09:25:00Z"
        receipt["evidence_index"]["attestation"] = self.fixture_envelope(
            "index", index_payload
        )
        review_subject = canonical_digest(
            {
                "receipt_id": receipt["receipt_id"],
                "binding_digest": receipt["binding_digest"],
                "evidence_set_digest": receipt["independent_review"]["payload"]["evidence_set_digest"],
                "controlled_index_attestation_digest": canonical_digest(
                    receipt["evidence_index"]["attestation"]
                ),
                "gate_attestations": [
                    {
                        "gate_id": gate["id"],
                        "execution_envelope_digest": canonical_digest(gate["execution_attestation"]),
                        "verification_envelope_digest": canonical_digest(gate["verification_attestation"]),
                    }
                    for gate in receipt["gates"]
                ],
                "approval_envelope_digests": sorted(
                    canonical_digest(item) for item in receipt["approvals"]
                ),
                "design_partner_envelope_digests": sorted(
                    canonical_digest(item)
                    for item in receipt["design_partner_acceptances"]
                ),
            }
        )
        review_payload = copy.deepcopy(receipt["independent_review"]["payload"])
        review_payload["review_subject_digest"] = review_subject
        receipt["independent_review"] = self.fixture_envelope(
            "reviewer", review_payload
        )
        receipt["receipt_digest"] = receipt_digest(receipt)
        with self.assertRaisesRegex(SpringLaunchEvidenceError, "review predates"):
            with self.fast_signature_verification():
                self.verify(receipt)

    def test_assemble_adds_only_digest_to_complete_signed_draft(self) -> None:
        receipt = self.make_receipt()
        draft = copy.deepcopy(receipt)
        del draft["receipt_digest"]
        with self.fast_signature_verification():
            assembled, result = assemble_spring_launch_receipt(
                draft,
                trust_store=self.trust_path,
                evidence_roots=[self.evidence_root],
                expected_revision=self.REVISION,
                now=self.NOW,
            )
        self.assertEqual(receipt["receipt_digest"], assembled["receipt_digest"])
        self.assertEqual("NOT_CERTIFIED", result["certification"])


if __name__ == "__main__":
    unittest.main()
