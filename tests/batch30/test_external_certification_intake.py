import base64
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.batch30.validate_external_certification_intake import (
    CUSTOMER_AUTHORIZATION_ROLE,
    EVIDENCE_ROLES,
    NAMESPACE,
    ExternalIntakeError,
    build_expected_binding,
    evaluate_external_intake,
)
from scripts.precision_migration.trust import canonical_bytes, canonical_digest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "batch30" / "validate_external_certification_intake.py"
NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


class ExternalCertificationIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="batch30-external-intake-")
        cls.root = Path(cls.temporary.name)
        cls.key_root = cls.root / "signing-keys"
        cls.key_root.mkdir()
        cls.roles = [CUSTOMER_AUTHORIZATION_ROLE, *EVIDENCE_ROLES.values()]
        cls.private_keys: dict[str, Path] = {}
        cls.public_keys: dict[str, Path] = {}
        for role in cls.roles:
            private_key = cls.key_root / f"{role}.private.pem"
            public_key = cls.key_root / f"{role}.public.pem"
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
            cls.private_keys[role] = private_key
            cls.public_keys[role] = public_key
        cls.pack = cls.root / "framework-pack"
        (cls.pack / "target-profile").mkdir(parents=True)
        (cls.pack / "recipes").mkdir()
        cls.write_class_json(
            cls.pack / "pack.json",
            {
                "schema_version": 1,
                "pack_key": "spring-boot-2-7-18-to-3-5-3",
                "version": "0.3.0",
                "mode": "upgrade",
                "status": "limited",
                "source": {
                    "framework": "spring-boot",
                    "framework_versions": ["2.7.18"],
                    "runtime": "java",
                    "runtime_versions": ["17"],
                    "build_tools": ["maven-3.9.11"],
                    "provider_versions": {"servlet": "4.0"},
                },
                "target": {
                    "framework": "spring-boot",
                    "framework_versions": ["3.5.3"],
                    "runtime": "java",
                    "runtime_versions": ["21"],
                    "build_tools": ["maven-3.9.11"],
                    "provider_versions": {"servlet": "6.1"},
                },
            },
        )
        cls.write_class_json(
            cls.pack / "version-matrix.json",
            {
                "schema_version": 1,
                "pack_key": "spring-boot-2-7-18-to-3-5-3",
                "tuples": [
                    {
                        "id": "source",
                        "spring_boot": "2.7.18",
                        "java": "17",
                        "build": "maven-3.9.11",
                    },
                    {
                        "id": "target",
                        "spring_boot": "3.5.3",
                        "java": "21",
                        "build": "maven-3.9.11",
                    },
                ],
                "upgrade_edges": [
                    {
                        "from": "source",
                        "to": "target",
                        "directional": True,
                        "recipes": ["io.elmos.openrewrite.SpringBoot2_7_18To3_5_3Java21"],
                    }
                ],
            },
        )
        cls.write_class_json(
            cls.pack / "target-profile" / "profile.json",
            {
                "schema_version": 1,
                "profile_key": "spring-boot-2-7-18-to-3-5-3-target",
                "framework": "spring-boot",
                "framework_versions": ["3.5.3"],
                "runtime": "java",
                "runtime_versions": ["21"],
            },
        )
        cls.write_class_json(
            cls.pack / "recipes" / "manifest.json",
            {
                "schema_version": 1,
                "pack_key": "spring-boot-2-7-18-to-3-5-3",
                "recipes": ["io.elmos.openrewrite.SpringBoot2_7_18To3_5_3Java21"],
            },
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    @staticmethod
    def write_class_json(path: Path, value: object) -> None:
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def setUp(self) -> None:
        self.case = Path(tempfile.mkdtemp(prefix="case-", dir=self.root))
        self.evidence_root = self.case / "evidence"
        self.evidence_root.mkdir()
        self.trust_root = self.case / "trust"
        (self.trust_root / "keys").mkdir(parents=True)
        for role, public_key in self.public_keys.items():
            shutil.copy2(public_key, self.trust_root / "keys" / f"{role}.pem")
        self.organizations = {
            "producer_organization_id": "producer-org",
            "customer_organization_id": "customer-org",
            "rootless_organization_id": "rootless-provider-org",
            "independent_organization_id": "independent-review-org",
        }
        self.trust_records = []
        for role in self.roles:
            if role == CUSTOMER_AUTHORIZATION_ROLE or "customer-" in role:
                organization = self.organizations["customer_organization_id"]
            elif "rootless-" in role:
                organization = self.organizations["rootless_organization_id"]
            else:
                organization = self.organizations["independent_organization_id"]
            self.trust_records.append(
                {
                    "key_id": f"key-{role}",
                    "actor_id": f"actor-{role}",
                    "organization_id": organization,
                    "roles": [role],
                    "public_key_path": f"keys/{role}.pem",
                    "not_before": "2020-01-01T00:00:00Z",
                    "not_after": "2100-01-01T00:00:00Z",
                    "revoked": False,
                }
            )
        self.revoked_record_ids: list[str] = []
        self.trust_path = self.trust_root / "trust-store.json"
        self.write_trust()

        artifact = self.evidence_root / "target.jar"
        artifact.write_bytes(b"real-target-artifact-fixture\n")
        execution_profile = self.evidence_root / "rootless-execution-profile.json"
        self.write_json(execution_profile, {"profile": "rootless-exact", "version": "1.0.0"})
        self.artifact_ref = self.content_ref(artifact, "application/java-archive")
        self.execution_profile_ref = self.content_ref(execution_profile)
        self.binding, _ = build_expected_binding(
            self.pack,
            self.artifact_ref,
            self.execution_profile_ref,
            evidence_roots=[self.evidence_root],
        )
        self.binding_digest = canonical_digest(self.binding)
        self.intake_id = "external-intake-one"
        self.scope = {
            "action": "validate-batch30-external-certification-intake",
            "pack_key": self.binding["pack_key"],
            "pack_version": self.binding["pack_version"],
            "binding_digest": self.binding_digest,
            "artifact_digest": self.binding["artifact_digest"],
            "execution_profile_digest": self.binding["execution_profile_digest"],
            **self.organizations,
            "evidence_types": list(EVIDENCE_ROLES),
        }
        evidence = {}
        for index, evidence_type in enumerate(EVIDENCE_ROLES, start=1):
            content_path = self.evidence_root / f"{evidence_type}.json"
            self.write_json(content_path, {"evidence_type": evidence_type, "sequence": index, "result": "PASS"})
            reference = self.content_ref(content_path)
            evidence[evidence_type] = {"content": reference}
        self.scope["evidence_content_digests"] = {
            name: evidence[name]["content"]["digest"] for name in EVIDENCE_ROLES
        }
        authorization_payload = {
            "record_id": "customer-authorization-one",
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
            "actor_id": f"actor-{CUSTOMER_AUTHORIZATION_ROLE}",
            "organization_id": self.organizations["customer_organization_id"],
            "role": CUSTOMER_AUTHORIZATION_ROLE,
            "intake_id": self.intake_id,
            "binding_digest": self.binding_digest,
            "scope": self.scope,
            "outcome": "AUTHORIZED",
            "synthetic": False,
            "unknowns": [],
            "not_run": [],
        }
        authorization_payload_digest = canonical_digest(authorization_payload)
        for evidence_type, role in EVIDENCE_ROLES.items():
            reference = evidence[evidence_type]["content"]
            payload = {
                "record_id": f"attestation-{evidence_type}",
                "issued_at": "2026-01-01T00:00:00Z",
                "expires_at": "2027-01-01T00:00:00Z",
                "actor_id": f"actor-{role}",
                "organization_id": self.organization_for(evidence_type),
                "role": role,
                "intake_id": self.intake_id,
                "binding_digest": self.binding_digest,
                "authorization_record_id": authorization_payload["record_id"],
                "authorization_payload_digest": authorization_payload_digest,
                "evidence_type": evidence_type,
                "content_digest": reference["digest"],
                "content_size_bytes": reference["size_bytes"],
                "outcome": "PASS",
                "evidence_class": "EXTERNAL_NON_SYNTHETIC",
                "synthetic": False,
                "unknowns": [],
                "not_run": [],
                "claims": self.claims_for(evidence_type),
            }
            evidence[evidence_type]["attestation"] = self.sign(role, payload)
        self.intake = {
            "schema_version": 1,
            "namespace": NAMESPACE,
            "intake_id": self.intake_id,
            **self.organizations,
            "binding": self.binding,
            "artifact": self.artifact_ref,
            "execution_profile": self.execution_profile_ref,
            "customer_authorization": self.sign(CUSTOMER_AUTHORIZATION_ROLE, authorization_payload),
            "evidence": evidence,
        }

    def tearDown(self) -> None:
        shutil.rmtree(self.case)

    def organization_for(self, evidence_type: str) -> str:
        if evidence_type in {"authorized_customer_repository", "customer_holdout"}:
            return self.organizations["customer_organization_id"]
        if evidence_type.startswith("rootless_"):
            return self.organizations["rootless_organization_id"]
        return self.organizations["independent_organization_id"]

    @staticmethod
    def claims_for(evidence_type: str) -> dict[str, object]:
        if evidence_type == "authorized_customer_repository":
            return {"authorized_repository": True, "fixed_commit": True, "acceptance_subject_bound": True}
        if evidence_type == "customer_holdout":
            return {"independent_from_development": True, "customer_owned_acceptance": True}
        if evidence_type.startswith("rootless_"):
            return {"rootless": True, "privileged": False, "effective_uid_nonzero": True}
        return {"organizationally_independent": True, "separate_executor_and_verifier": True}

    def write_json(self, path: Path, value: object) -> None:
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def content_ref(path: Path, media_type: str = "application/json") -> dict[str, object]:
        content = path.read_bytes()
        return {
            "uri": path.resolve().as_uri(),
            "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "media_type": media_type,
        }

    def write_trust(self) -> None:
        self.write_json(
            self.trust_path,
            {
                "schema_version": 1,
                "namespace": NAMESPACE,
                "keys": self.trust_records,
                "revoked_record_ids": self.revoked_record_ids,
            },
        )

    def trust_record(self, role: str) -> dict[str, object]:
        return next(item for item in self.trust_records if item["roles"] == [role])

    def sign(
        self,
        role: str,
        payload: dict[str, object],
        *,
        signing_role: str | None = None,
    ) -> dict[str, object]:
        payload_path = self.case / f"payload-{role}-{payload['record_id']}.json"
        signature_path = self.case / f"signature-{role}-{payload['record_id']}.bin"
        payload_path.write_bytes(canonical_bytes(payload))
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(self.private_keys[signing_role or role]),
                "-rawin",
                "-in",
                str(payload_path),
                "-out",
                str(signature_path),
            ],
            check=True,
            capture_output=True,
        )
        return {
            "algorithm": "ed25519",
            "key_id": f"key-{role}",
            "payload": payload,
            "signature": base64.b64encode(signature_path.read_bytes()).decode("ascii"),
        }

    def evaluate(self, intake: dict[str, object] | None = None) -> dict[str, object]:
        return evaluate_external_intake(
            intake or self.intake,
            pack_dir=self.pack,
            trust_store=self.trust_path,
            evidence_roots=[self.evidence_root],
            now=NOW,
        )

    def resign_evidence(self, evidence_type: str, *, signing_role: str | None = None) -> None:
        role = EVIDENCE_ROLES[evidence_type]
        payload = self.intake["evidence"][evidence_type]["attestation"]["payload"]
        self.intake["evidence"][evidence_type]["attestation"] = self.sign(
            role,
            payload,
            signing_role=signing_role,
        )

    def test_valid_intake_is_review_ready_but_never_certifies_or_mutates_pack(self) -> None:
        before = {path: path.read_bytes() for path in self.pack.rglob("*.json")}
        result = self.evaluate()
        self.assertEqual("VERIFIED_EXTERNAL_INTAKE", result["evidence_status"])
        self.assertEqual("READY_FOR_EXTERNAL_GATE_REVIEW", result["decision"])
        self.assertEqual("NOT_CERTIFIED", result["certification_decision"])
        self.assertFalse(result["certification_promoted"])
        self.assertFalse(result["pack_status_mutated"])
        self.assertFalse(result["synthetic_evidence_can_promote"])
        self.assertEqual(7, len(result["verified_roles"]))
        self.assertEqual(before, {path: path.read_bytes() for path in self.pack.rglob("*.json")})

    def test_cli_validates_without_promoting_status(self) -> None:
        intake_path = self.case / "intake.json"
        self.write_json(intake_path, self.intake)
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.pack),
                str(intake_path),
                "--trust-store",
                str(self.trust_path),
                "--evidence-root",
                str(self.evidence_root),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual("NOT_CERTIFIED", result["certification_decision"])

    def test_missing_role_and_unknown_outcome_fail_closed(self) -> None:
        missing = copy.deepcopy(self.intake)
        missing["evidence"].pop("customer_holdout")
        with self.assertRaisesRegex(ExternalIntakeError, "fields are invalid"):
            self.evaluate(missing)
        payload = self.intake["evidence"]["customer_holdout"]["attestation"]["payload"]
        payload["outcome"] = "UNKNOWN"
        self.resign_evidence("customer_holdout")
        with self.assertRaisesRegex(ExternalIntakeError, "non-success sentinel UNKNOWN"):
            self.evaluate()

    def test_self_signing_fails_closed(self) -> None:
        independent_role = EVIDENCE_ROLES["independent_review"]
        reused_actor = f"actor-{EVIDENCE_ROLES['rootless_verifier']}"
        self.trust_record(independent_role)["actor_id"] = reused_actor
        payload = self.intake["evidence"]["independent_review"]["attestation"]["payload"]
        payload["actor_id"] = reused_actor
        self.resign_evidence("independent_review")
        self.write_trust()
        with self.assertRaisesRegex(ExternalIntakeError, "must not reuse actor identity"):
            self.evaluate()

    def test_same_organization_fails_closed(self) -> None:
        same_org = copy.deepcopy(self.intake)
        same_org["independent_organization_id"] = same_org["rootless_organization_id"]
        with self.assertRaisesRegex(ExternalIntakeError, "organizations must be distinct"):
            self.evaluate(same_org)

    def test_expired_signature_fails_closed(self) -> None:
        expired = self.intake["customer_authorization"]["payload"]
        expired["issued_at"] = "2024-01-01T00:00:00Z"
        expired["expires_at"] = "2025-01-01T00:00:00Z"
        self.intake["customer_authorization"] = self.sign(CUSTOMER_AUTHORIZATION_ROLE, expired)
        with self.assertRaisesRegex(ExternalIntakeError, "outside its validity window"):
            self.evaluate()

    def test_expired_trust_key_fails_closed(self) -> None:
        self.trust_record(CUSTOMER_AUTHORIZATION_ROLE)["not_after"] = "2025-01-01T00:00:00Z"
        self.write_trust()
        with self.assertRaisesRegex(ExternalIntakeError, "signing key is outside its validity window"):
            self.evaluate()

    def test_revoked_key_fails_closed(self) -> None:
        self.trust_record(EVIDENCE_ROLES["rootless_runner"])["revoked"] = True
        self.write_trust()
        with self.assertRaisesRegex(ExternalIntakeError, "unknown or revoked"):
            self.evaluate()

    def test_revoked_record_fails_closed(self) -> None:
        self.revoked_record_ids.append("customer-authorization-one")
        self.write_trust()
        with self.assertRaisesRegex(ExternalIntakeError, "record is revoked"):
            self.evaluate()

    def test_wrong_role_signature_fails_closed(self) -> None:
        self.intake["evidence"]["independent_review"]["attestation"] = self.intake["evidence"][
            "rootless_verifier"
        ]["attestation"]
        with self.assertRaisesRegex(ExternalIntakeError, "dedicated to exactly that role"):
            self.evaluate()

    def test_path_escape_symlink_and_content_tamper_fail_closed(self) -> None:
        outside = self.case / "outside.jar"
        outside.write_bytes(b"outside\n")
        escaped = copy.deepcopy(self.intake)
        escaped["artifact"] = self.content_ref(outside, "application/java-archive")
        with self.assertRaisesRegex(ExternalIntakeError, "escapes approved evidence roots"):
            self.evaluate(escaped)

        symlink = self.evidence_root / "artifact-link.jar"
        symlink.symlink_to(self.evidence_root / "target.jar")
        linked = copy.deepcopy(self.intake)
        linked["artifact"] = self.content_ref(symlink, "application/java-archive")
        linked["artifact"]["uri"] = (self.evidence_root.resolve() / symlink.name).as_uri()
        with self.assertRaisesRegex(ExternalIntakeError, "contains a symlink"):
            self.evaluate(linked)

        content_uri = self.intake["evidence"]["rootless_runner"]["content"]["uri"]
        Path(content_uri.removeprefix("file://")).write_bytes(b"tampered\n")
        with self.assertRaisesRegex(ExternalIntakeError, "content .* mismatch"):
            self.evaluate()

    def test_exact_pack_tuple_artifact_profile_binding_is_required(self) -> None:
        drifted = copy.deepcopy(self.intake)
        drifted["binding"]["target_tuple"]["framework_version"] = "3.5.4"
        with self.assertRaisesRegex(ExternalIntakeError, "exact pack/tuple/artifact/profile"):
            self.evaluate(drifted)

    def test_primary_and_role_content_cannot_be_reused(self) -> None:
        reused_primary = copy.deepcopy(self.intake)
        reused_primary["execution_profile"] = reused_primary["artifact"]
        with self.assertRaisesRegex(ExternalIntakeError, "must bind distinct content bytes"):
            self.evaluate(reused_primary)

        reused_role = copy.deepcopy(self.intake)
        reused_role["evidence"]["customer_holdout"] = copy.deepcopy(
            reused_role["evidence"]["authorized_customer_repository"]
        )
        with self.assertRaisesRegex(ExternalIntakeError, "distinct content bytes"):
            self.evaluate(reused_role)

    def test_customer_authorization_binds_every_evidence_digest(self) -> None:
        replacement = self.evidence_root / "replacement-customer-holdout.json"
        self.write_json(replacement, {"evidence_type": "customer_holdout", "result": "PASS", "version": 2})
        reference = self.content_ref(replacement)
        self.intake["evidence"]["customer_holdout"]["content"] = reference
        payload = self.intake["evidence"]["customer_holdout"]["attestation"]["payload"]
        payload["content_digest"] = reference["digest"]
        payload["content_size_bytes"] = reference["size_bytes"]
        self.resign_evidence("customer_holdout")
        with self.assertRaisesRegex(ExternalIntakeError, "binding mismatch: scope"):
            self.evaluate()

    def test_attestations_bind_the_exact_customer_authorization_payload(self) -> None:
        replacement = self.evidence_root / "replacement-customer-holdout.json"
        self.write_json(replacement, {"evidence_type": "customer_holdout", "result": "PASS", "version": 3})
        reference = self.content_ref(replacement)
        self.intake["evidence"]["customer_holdout"]["content"] = reference
        evidence_payload = self.intake["evidence"]["customer_holdout"]["attestation"]["payload"]
        evidence_payload["content_digest"] = reference["digest"]
        evidence_payload["content_size_bytes"] = reference["size_bytes"]
        authorization_payload = self.intake["customer_authorization"]["payload"]
        authorization_payload["scope"]["evidence_content_digests"]["customer_holdout"] = reference["digest"]
        self.intake["customer_authorization"] = self.sign(CUSTOMER_AUTHORIZATION_ROLE, authorization_payload)
        self.resign_evidence("customer_holdout")
        with self.assertRaisesRegex(ExternalIntakeError, "binding mismatch: authorization_payload_digest"):
            self.evaluate()
        drifted = copy.deepcopy(self.intake)
        drifted["binding"]["artifact_digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ExternalIntakeError, "exact pack/tuple/artifact/profile"):
            self.evaluate(drifted)
        drifted = copy.deepcopy(self.intake)
        drifted["binding"]["target_profile_digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ExternalIntakeError, "exact pack/tuple/artifact/profile"):
            self.evaluate(drifted)

    def test_synthetic_claim_fails_closed(self) -> None:
        payload = self.intake["evidence"]["rootless_transformer"]["attestation"]["payload"]
        payload["synthetic"] = True
        self.resign_evidence("rootless_transformer")
        with self.assertRaisesRegex(ExternalIntakeError, "binding mismatch: synthetic"):
            self.evaluate()

    def test_tampered_signature_fails_closed(self) -> None:
        self.intake["customer_authorization"]["signature"] = "ZmFrZQ=="
        with self.assertRaisesRegex(ExternalIntakeError, "signature verification failed"):
            self.evaluate()

    def test_missing_signature_fails_closed(self) -> None:
        self.intake["customer_authorization"].pop("signature")
        with self.assertRaisesRegex(ExternalIntakeError, "fields are invalid"):
            self.evaluate()

    def test_missing_evidence_roots_fail_closed(self) -> None:
        with self.assertRaisesRegex(ExternalIntakeError, "explicit evidence root"):
            evaluate_external_intake(
                self.intake,
                pack_dir=self.pack,
                trust_store=self.trust_path,
                evidence_roots=[],
                now=NOW,
            )

    def test_reused_key_material_fails_closed(self) -> None:
        independent_role = EVIDENCE_ROLES["independent_review"]
        reused_role = EVIDENCE_ROLES["rootless_verifier"]
        self.trust_record(independent_role)["public_key_path"] = f"keys/{reused_role}.pem"
        self.resign_evidence("independent_review", signing_role=reused_role)
        self.write_trust()
        with self.assertRaisesRegex(ExternalIntakeError, "must not reuse public-key material"):
            self.evaluate()

    def test_trust_path_escape_fails_closed(self) -> None:
        independent_role = EVIDENCE_ROLES["independent_review"]
        self.trust_record(independent_role)["public_key_path"] = "../outside.pem"
        self.write_trust()
        with self.assertRaisesRegex(ExternalIntakeError, "public_key_path is invalid"):
            self.evaluate()

    def test_unknown_trust_metadata_fails_closed(self) -> None:
        self.trust_record(EVIDENCE_ROLES["independent_review"])["organization_id"] = "UNKNOWN"
        self.write_trust()
        with self.assertRaisesRegex(ExternalIntakeError, "non-success sentinel UNKNOWN"):
            self.evaluate()


if __name__ == "__main__":
    unittest.main()
