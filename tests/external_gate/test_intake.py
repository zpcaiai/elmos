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
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts import external_gate_intake as external_intake
from scripts.external_gate_intake import (
    NAMESPACE,
    STAGE_PROFILES,
    ExternalGateError,
    binding_digest,
    content_reference,
    evaluate_intake,
)
from scripts.precision_migration import trust as trust_module
from scripts.precision_migration.trust import TrustStore, canonical_bytes

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/external_gate_intake.py"
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


class ExternalGateIntakeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="elmos-external-intake-")
        self.root = Path(self.temporary.name)
        self.keys: dict[str, Path] = {}
        self.identities = {
            "external-executor": ("executor-one", "external-lab-a"),
            "independent-verifier": ("verifier-one", "external-lab-b"),
            "customer-workload-authorizer": ("customer-owner", "customer-org"),
        }
        self.subject_roots: dict[int, Path] = {}
        self.trust_path = self.write_trust_store()
        self.trust_digest = TrustStore.load(self.trust_path).digest

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_trust_store(
        self,
        *,
        identity_overrides: dict[str, tuple[str, str]] | None = None,
        revoked_record_ids: list[str] | None = None,
    ) -> Path:
        records = []
        identities = dict(self.identities)
        identities.update(identity_overrides or {})
        for role, (actor, organization) in identities.items():
            private = self.keys.get(role) or self.root / f"{role}.private.pem"
            public = self.root / f"{role}.public.pem"
            if role not in self.keys:
                subprocess.run(
                    [
                        "openssl",
                        "genpkey",
                        "-algorithm",
                        "ed25519",
                        "-out",
                        str(private),
                    ],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    [
                        "openssl",
                        "pkey",
                        "-in",
                        str(private),
                        "-pubout",
                        "-out",
                        str(public),
                    ],
                    check=True,
                    capture_output=True,
                )
                self.keys[role] = private
            records.append(
                {
                    "key_id": f"key-{role}",
                    "roles": [role],
                    "actor_id": actor,
                    "organization_id": organization,
                    "public_key_path": public.name,
                    "not_before": "2025-01-01T00:00:00Z",
                    "not_after": "2030-01-01T00:00:00Z",
                    "revoked": False,
                }
            )
        path = self.root / (
            "trust-store.json"
            if not identity_overrides and not revoked_record_ids
            else "alternate-trust-store.json"
        )
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "keys": records,
                    "revoked_record_ids": revoked_record_ids or [],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def write_artifact(self, name: str, payload: object) -> dict[str, object]:
        path = self.root / name
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        content = path.read_bytes()
        return {
            "uri": path.resolve().as_uri(),
            "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "media_type": "application/json",
        }

    def envelope(
        self,
        role: str,
        intake: dict[str, object],
        stage_name: str,
        stage_digest: str,
        *,
        identity_overrides: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, object]:
        identities = dict(self.identities)
        identities.update(identity_overrides or {})
        actor, organization = identities[role]
        subject = intake["subject"]
        payload = {
            "record_id": f"record-{intake['batch']}-{stage_name}-{role}",
            "namespace": NAMESPACE,
            "intake_id": intake["intake_id"],
            "batch": intake["batch"],
            "subject_digest": subject["snapshot"]["digest"],
            "subject_key": subject["key"],
            "subject_version": subject["version"],
            "producer_actor_id": subject["producer"]["actor_id"],
            "producer_organization_id": subject["producer"]["organization_id"],
            "stage": stage_name,
            "stage_binding_digest": stage_digest,
            "actor_id": actor,
            "organization_id": organization,
            "issued_at": "2025-01-02T00:00:00Z",
            "expires_at": "2029-01-01T00:00:00Z",
        }
        payload_path = self.root / f"payload-{role}-{stage_name}.json"
        signature_path = self.root / f"signature-{role}-{stage_name}.bin"
        payload_path.write_bytes(canonical_bytes(payload))
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(self.keys[role]),
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

    def resign_envelope(self, role: str, envelope: dict[str, object]) -> None:
        payload_path = self.root / f"resigned-{role}-payload.json"
        signature_path = self.root / f"resigned-{role}-signature.bin"
        payload_path.write_bytes(canonical_bytes(envelope["payload"]))
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(self.keys[role]),
                "-rawin",
                "-in",
                str(payload_path),
                "-out",
                str(signature_path),
            ],
            check=True,
            capture_output=True,
        )
        envelope["signature"] = base64.b64encode(signature_path.read_bytes()).decode(
            "ascii"
        )

    def build_intake(
        self,
        batch: int,
        *,
        identity_overrides: dict[str, tuple[str, str]] | None = None,
        producer_actor: str = "release-owner",
        producer_organization: str = "elmos-org",
    ) -> dict[str, object]:
        snapshot_path = self.root / f"batch-{batch}-subject-snapshot.json"
        subject_kind = "batch29-route" if batch == 29 else "batch35-verification-pack"
        subject_key = "python-to-typescript" if batch == 29 else "source-ingestion-pack"
        subject_root = self.root / f"batch-{batch}-subject-root"
        subject_file = subject_root / "subject/manifest.json"
        subject_file.parent.mkdir(parents=True, exist_ok=True)
        subject_content = canonical_bytes(
            {
                "batch": batch,
                "kind": subject_kind,
                "key": subject_key,
                "version": "1.0.0",
            }
        )
        subject_file.write_bytes(subject_content)
        self.subject_roots[batch] = subject_root
        snapshot_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": subject_kind,
                    "key": subject_key,
                    "version": "1.0.0",
                    "repository_revision": "git:" + "a" * 40,
                    "file_set_policy": "exact",
                    "files": [
                        {
                            "path": "subject/manifest.json",
                            "role": "subject-manifest",
                            "sha256": "sha256:"
                            + hashlib.sha256(subject_content).hexdigest(),
                            "byte_size": len(subject_content),
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        intake: dict[str, object] = {
            "schema_version": 1,
            "namespace": NAMESPACE,
            "intake_id": f"INTAKE-B{batch}-001",
            "batch": batch,
            "subject": {
                "kind": subject_kind,
                "key": subject_key,
                "version": "1.0.0",
                "producer": {
                    "actor_id": producer_actor,
                    "organization_id": producer_organization,
                },
                "snapshot": content_reference(snapshot_path),
            },
            "stages": [],
            "policy": {
                "repository_status_update": False,
                "production_operation_authorized": False,
                "maximum_local_decision": "ACCEPTED_FOR_REPOSITORY_GATE",
            },
        }
        for stage_name, roles in STAGE_PROFILES[batch].items():
            metrics = (
                {
                    "tests_total": 3,
                    "tests_passed": 3,
                    "tests_failed": 0,
                    "critical_unknowns": 0,
                    "critical_behavior_regressions": 0,
                    "test_integrity_violations": 0,
                }
                if batch == 29
                else {
                    "cases_total": 3,
                    "cases_passed": 3,
                    "cases_failed": 0,
                    "p0_unknowns": 0,
                    "critical_failures": 0,
                    "test_integrity_violations": 0,
                }
            )
            stage: dict[str, object] = {
                "stage": stage_name,
                "status": "PASSED",
                "metrics": metrics,
                "evidence": [
                    {
                        "role": role,
                        "artifact": self.write_artifact(
                            f"{batch}-{stage_name}-{role}.json",
                            {
                                "batch": batch,
                                "stage": stage_name,
                                "role": role,
                                "status": "PASSED",
                            },
                        ),
                    }
                    for role in sorted(roles)
                ],
            }
            if batch == 35 and stage_name == "representative_production_workload":
                stage["context"] = {
                    "provenance": "production-derived",
                    "authorized_use": "verification-only",
                    "data_handling": "deidentified",
                    "production_mutation": False,
                }
            stage_digest = binding_digest(intake, stage, stage["evidence"])
            stage["execution"] = self.envelope(
                "external-executor",
                intake,
                stage_name,
                stage_digest,
                identity_overrides=identity_overrides,
            )
            stage["verification"] = self.envelope(
                "independent-verifier",
                intake,
                stage_name,
                stage_digest,
                identity_overrides=identity_overrides,
            )
            if batch == 35 and stage_name == "representative_production_workload":
                stage["authorization"] = self.envelope(
                    "customer-workload-authorizer",
                    intake,
                    stage_name,
                    stage_digest,
                    identity_overrides=identity_overrides,
                )
            intake["stages"].append(stage)
        return intake

    def evaluate(
        self,
        intake: dict[str, object],
        trust_path: Path | None = None,
        *,
        expected_digest: str | None = None,
        subject_root: Path | None = None,
    ) -> dict[str, object]:
        selected_trust_path = trust_path or self.trust_path
        selected_trust_digest = (
            expected_digest or TrustStore.load(selected_trust_path).digest
        )
        return evaluate_intake(
            intake,
            trust_store_path=selected_trust_path,
            expected_trust_store_digest=selected_trust_digest,
            evidence_roots=(self.root.resolve(),),
            subject_root=subject_root or self.subject_roots[int(intake["batch"])],
            now=NOW,
        )

    def test_batch29_signed_external_intake_is_accepted_without_certification(
        self,
    ) -> None:
        result = self.evaluate(self.build_intake(29))
        self.assertEqual("ACCEPTED_FOR_REPOSITORY_GATE", result["decision"])
        self.assertEqual("NOT_CERTIFIED", result["certification_decision"])
        self.assertEqual(3, len(result["accepted_stages"]))

    def test_batch35_requires_independent_holdout_and_authorized_production_workload(
        self,
    ) -> None:
        result = self.evaluate(self.build_intake(35))
        self.assertEqual("ACCEPTED_FOR_REPOSITORY_GATE", result["decision"])
        self.assertEqual("NOT_CERTIFIED", result["certification_decision"])
        self.assertEqual(2, len(result["accepted_stages"]))

    def test_tampered_evidence_bytes_are_rejected(self) -> None:
        intake = self.build_intake(29)
        path = Path(
            intake["stages"][0]["evidence"][0]["artifact"]["uri"].removeprefix(
                "file://"
            )
        )
        path.write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(
            ValueError, "content byte count mismatch|content digest mismatch"
        ):
            self.evaluate(intake)

    def test_subject_snapshot_identity_mismatch_is_rejected(self) -> None:
        intake = self.build_intake(29)
        snapshot_path = Path(
            intake["subject"]["snapshot"]["uri"].removeprefix("file://")
        )
        snapshot = json.loads(snapshot_path.read_text())
        snapshot["key"] = "different-route"
        snapshot_path.write_text(
            json.dumps(snapshot, sort_keys=True) + "\n", encoding="utf-8"
        )
        intake["subject"]["snapshot"] = content_reference(snapshot_path)
        with self.assertRaisesRegex(ExternalGateError, "snapshot key does not match"):
            self.evaluate(intake)

    def test_one_artifact_cannot_fill_multiple_evidence_roles(self) -> None:
        intake = self.build_intake(29)
        evidence = intake["stages"][0]["evidence"]
        evidence[1]["artifact"] = copy.deepcopy(evidence[0]["artifact"])
        with self.assertRaisesRegex(ExternalGateError, "reuse one artifact"):
            self.evaluate(intake)

    def test_forged_signature_is_rejected(self) -> None:
        intake = self.build_intake(29)
        intake["stages"][0]["verification"]["signature"] = base64.b64encode(
            b"x" * 64
        ).decode("ascii")
        with self.assertRaisesRegex(ValueError, "signature verification failed"):
            self.evaluate(intake)

    def test_signed_envelope_window_must_fit_key_authorization(self) -> None:
        original = self.build_intake(29)
        cases = (
            ("issued_at", "2024-12-31T23:59:59Z", "issued_at is outside"),
            ("expires_at", "2030-01-01T00:00:01Z", "expires_at exceeds"),
        )
        for field, value, expected_error in cases:
            with self.subTest(field=field):
                intake = copy.deepcopy(original)
                envelope = intake["stages"][0]["execution"]
                envelope["payload"][field] = value
                self.resign_envelope("external-executor", envelope)
                with self.assertRaisesRegex(ValueError, expected_error):
                    self.evaluate(intake)

    def test_stage_metrics_changed_after_signing_are_rejected(self) -> None:
        intake = self.build_intake(29)
        intake["stages"][0]["metrics"]["tests_total"] = 4
        intake["stages"][0]["metrics"]["tests_passed"] = 4
        with self.assertRaisesRegex(
            ValueError, "binding mismatch: stage_binding_digest"
        ):
            self.evaluate(intake)

    def test_producer_identity_changed_after_signing_is_rejected(self) -> None:
        original = self.build_intake(29)
        mutations = (
            ("actor_id", "replacement-release-owner", "producer_actor_id"),
            (
                "organization_id",
                "replacement-producer-org",
                "producer_organization_id",
            ),
        )
        for field, value, expected_binding in mutations:
            with self.subTest(field=field):
                intake = copy.deepcopy(original)
                intake["subject"]["producer"][field] = value
                with self.assertRaisesRegex(
                    ValueError, f"binding mismatch: {expected_binding}"
                ):
                    self.evaluate(intake)

    def test_producer_actor_cannot_claim_a_different_trusted_organization(self) -> None:
        intake = self.build_intake(
            29,
            producer_actor="executor-one",
            producer_organization="different-producer-org",
        )
        with self.assertRaisesRegex(
            ExternalGateError, "producer actor organization conflicts"
        ):
            self.evaluate(intake)

    def test_producer_actor_cannot_execute_verify_or_authorize(self) -> None:
        cases = (
            (29, "executor-one", "external-lab-a", "cannot execute"),
            (29, "verifier-one", "external-lab-b", "cannot execute"),
            (35, "customer-owner", "customer-org", "cannot authorize"),
        )
        for batch, actor, organization, expected_error in cases:
            with self.subTest(actor=actor):
                intake = self.build_intake(
                    batch,
                    producer_actor=actor,
                    producer_organization=organization,
                )
                with self.assertRaisesRegex(ExternalGateError, expected_error):
                    self.evaluate(intake)

    def test_wrong_trust_store_pin_is_rejected(self) -> None:
        intake = self.build_intake(29)
        with self.assertRaisesRegex(
            ExternalGateError, "does not match the repository-owner pin"
        ):
            self.evaluate(intake, expected_digest="sha256:" + "f" * 64)

    def test_subject_file_tamper_is_rejected(self) -> None:
        intake = self.build_intake(29)
        subject_file = self.subject_roots[29] / "subject/manifest.json"
        subject_file.write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(
            ExternalGateError, "subject file .* (byte count|digest) mismatch"
        ):
            self.evaluate(intake)

    def test_subject_files_are_streamed_and_not_loaded_as_whole_bytes(self) -> None:
        intake = self.build_intake(29)
        original_reader = external_intake._read_path_snapshot

        def reject_subject_whole_file_reads(
            path: Path, *, max_bytes: int, label: str
        ) -> tuple[Path, bytes]:
            if label.startswith("subject file"):
                raise AssertionError("subject file used whole-file reader")
            return original_reader(path, max_bytes=max_bytes, label=label)

        with mock.patch.object(
            external_intake,
            "_read_path_snapshot",
            side_effect=reject_subject_whole_file_reads,
        ):
            result = self.evaluate(intake)
        self.assertEqual("ACCEPTED_FOR_REPOSITORY_GATE", result["decision"])

    def test_subject_final_stream_detects_same_size_restored_mtime_drift(self) -> None:
        intake = self.build_intake(29)
        subject_file = self.subject_roots[29] / "subject/manifest.json"
        original_content = subject_file.read_bytes()
        original_stat = subject_file.stat()
        original_scan = external_intake._subject_root_files
        scans = 0

        def mutate_between_streaming_passes(root: Path) -> dict[str, Path]:
            nonlocal scans
            scans += 1
            if scans == 2:
                subject_file.write_bytes(b"x" * len(original_content))
                subject_file.write_bytes(original_content)
                os.utime(
                    subject_file,
                    ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
                )
            return original_scan(root)

        with mock.patch.object(
            external_intake,
            "_subject_root_files",
            side_effect=mutate_between_streaming_passes,
        ):
            with self.assertRaisesRegex(
                ExternalGateError, "changed between verification passes"
            ):
                self.evaluate(intake)

    def test_subject_resource_limits_fail_closed(self) -> None:
        intake = self.build_intake(29)
        cases = (
            ("MAX_SUBJECT_FILES", 0, "MAX_SUBJECT_FILES"),
            ("MAX_SINGLE_SUBJECT_BYTES", 1, "MAX_SINGLE_SUBJECT_BYTES"),
            ("MAX_TOTAL_SUBJECT_BYTES", 1, "MAX_TOTAL_SUBJECT_BYTES"),
            ("MAX_SUBJECT_SCAN_DEPTH", 0, "MAX_SUBJECT_SCAN_DEPTH"),
            ("MAX_SUBJECT_SCAN_ENTRIES", 1, "MAX_SUBJECT_SCAN_ENTRIES"),
        )
        for constant, limit, expected_error in cases:
            with self.subTest(constant=constant):
                with mock.patch.object(external_intake, constant, limit):
                    with self.assertRaisesRegex(ExternalGateError, expected_error):
                        self.evaluate(intake)

    def test_subject_schema_publishes_matching_resource_limits(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/external-gates/subject-snapshot.schema.json").read_text()
        )
        limits = schema["x-elmos-resource-limits"]
        self.assertEqual(external_intake.MAX_SUBJECT_FILES, limits["max_subject_files"])
        self.assertEqual(
            external_intake.MAX_SINGLE_SUBJECT_BYTES,
            limits["max_single_subject_bytes"],
        )
        self.assertEqual(
            external_intake.MAX_TOTAL_SUBJECT_BYTES,
            limits["max_total_subject_bytes"],
        )
        self.assertEqual(
            external_intake.MAX_SUBJECT_SCAN_DEPTH,
            limits["max_subject_scan_depth"],
        )
        self.assertEqual(
            external_intake.MAX_SUBJECT_SCAN_ENTRIES,
            limits["max_subject_scan_entries"],
        )

    def test_missing_subject_file_is_rejected(self) -> None:
        intake = self.build_intake(29)
        (self.subject_roots[29] / "subject/manifest.json").unlink()
        with self.assertRaisesRegex(ExternalGateError, "missing declared files"):
            self.evaluate(intake)

    def test_extra_subject_file_is_rejected(self) -> None:
        intake = self.build_intake(29)
        (self.subject_roots[29] / "undeclared.txt").write_text(
            "not in the exact manifest\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ExternalGateError, "undeclared extra files"):
            self.evaluate(intake)

    def test_subject_symlink_is_rejected(self) -> None:
        intake = self.build_intake(29)
        subject_file = self.subject_roots[29] / "subject/manifest.json"
        outside = self.root / "outside-subject.json"
        outside.write_bytes(subject_file.read_bytes())
        subject_file.unlink()
        os.symlink(outside, subject_file)
        with self.assertRaisesRegex(ExternalGateError, "contains a symlink"):
            self.evaluate(intake)

    def test_subject_snapshot_path_escape_is_rejected(self) -> None:
        intake = self.build_intake(29)
        snapshot_path = Path(
            intake["subject"]["snapshot"]["uri"].removeprefix("file://")
        )
        snapshot = json.loads(snapshot_path.read_text())
        snapshot["files"][0]["path"] = "../outside-subject.json"
        snapshot_path.write_text(
            json.dumps(snapshot, sort_keys=True) + "\n", encoding="utf-8"
        )
        intake["subject"]["snapshot"] = content_reference(snapshot_path)
        with self.assertRaisesRegex(ExternalGateError, "file path is unsafe"):
            self.evaluate(intake)

    def test_subject_snapshot_path_swap_is_rejected(self) -> None:
        intake = self.build_intake(29)
        snapshot_path = Path(
            intake["subject"]["snapshot"]["uri"].removeprefix("file://")
        )
        replacement = self.root / "replacement-snapshot.json"
        replacement.write_bytes(snapshot_path.read_bytes())
        reference = content_reference(snapshot_path)
        original_read = os.read
        swapped = False

        def swap_after_first_read(descriptor: int, count: int) -> bytes:
            nonlocal swapped
            content = original_read(descriptor, count)
            if content and not swapped:
                os.replace(replacement, snapshot_path)
                swapped = True
            return content

        with mock.patch.object(
            external_intake.os, "read", side_effect=swap_after_first_read
        ):
            with self.assertRaisesRegex(
                ExternalGateError, "path changed while being read"
            ):
                external_intake.read_verified_reference_bytes(
                    reference,
                    (self.root.resolve(),),
                    max_bytes=4 * 1024 * 1024,
                    label="subject snapshot",
                )

    def test_trust_store_path_swap_is_rejected(self) -> None:
        replacement = self.root / "replacement-trust-store.json"
        replacement.write_bytes(self.trust_path.read_bytes())
        original_reader = trust_module.read_regular_file_once
        swapped = False

        def swap_after_store_read(path: Path, *, max_bytes: int, label: str) -> bytes:
            nonlocal swapped
            content = original_reader(path, max_bytes=max_bytes, label=label)
            if label == "trust store" and not swapped:
                os.replace(replacement, self.trust_path)
                swapped = True
            return content

        with mock.patch.object(
            trust_module, "read_regular_file_once", side_effect=swap_after_store_read
        ):
            with self.assertRaisesRegex(ValueError, "trust store changed"):
                TrustStore.load_with_document(self.trust_path)

    def test_trust_store_public_key_path_swap_is_rejected(self) -> None:
        public_key = self.root / "external-executor.public.pem"
        replacement = self.root / "replacement-public-key.pem"
        replacement.write_bytes(public_key.read_bytes())
        original_reader = trust_module.read_regular_file_once
        swapped = False

        def swap_after_key_read(path: Path, *, max_bytes: int, label: str) -> bytes:
            nonlocal swapped
            content = original_reader(path, max_bytes=max_bytes, label=label)
            if label == "trust store key key-external-executor" and not swapped:
                os.replace(replacement, public_key)
                swapped = True
            return content

        with mock.patch.object(
            trust_module, "read_regular_file_once", side_effect=swap_after_key_read
        ):
            with self.assertRaisesRegex(ValueError, "public key changed"):
                TrustStore.load_with_document(self.trust_path)

    def test_not_run_stage_remains_blocked(self) -> None:
        intake = self.build_intake(35)
        intake["stages"][0]["status"] = "NOT_RUN"
        with self.assertRaisesRegex(ExternalGateError, "remains NOT_RUN"):
            self.evaluate(intake)

    def test_missing_production_authorization_is_rejected(self) -> None:
        intake = self.build_intake(35)
        production = next(
            stage
            for stage in intake["stages"]
            if stage["stage"] == "representative_production_workload"
        )
        del production["authorization"]
        with self.assertRaisesRegex(
            ExternalGateError, "authorization envelope is required"
        ):
            self.evaluate(intake)

    def test_executor_and_verifier_organizations_must_differ(self) -> None:
        overrides = {"independent-verifier": ("verifier-one", "external-lab-a")}
        trust_path = self.write_trust_store(identity_overrides=overrides)
        intake = self.build_intake(29, identity_overrides=overrides)
        with self.assertRaisesRegex(ExternalGateError, "organizations must differ"):
            self.evaluate(intake, trust_path)

    def test_revoked_signed_record_is_rejected(self) -> None:
        intake = self.build_intake(29)
        revoked = intake["stages"][0]["verification"]["payload"]["record_id"]
        trust_path = self.write_trust_store(revoked_record_ids=[revoked])
        with self.assertRaisesRegex(ValueError, "record is revoked"):
            self.evaluate(intake, trust_path)

    def test_distinct_roles_cannot_share_the_same_public_key(self) -> None:
        intake = self.build_intake(29)
        trust = json.loads(self.trust_path.read_text())
        executor_path = next(
            item["public_key_path"]
            for item in trust["keys"]
            if item["roles"] == ["external-executor"]
        )
        verifier = next(
            item for item in trust["keys"] if item["roles"] == ["independent-verifier"]
        )
        verifier["public_key_path"] = executor_path
        alternate = self.root / "duplicate-key-trust-store.json"
        alternate.write_text(json.dumps(trust, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ExternalGateError, "distinct public keys"):
            self.evaluate(intake, alternate)

    def test_revoked_record_cannot_shadow_an_active_duplicate_key_id(self) -> None:
        trust = json.loads(self.trust_path.read_text())
        revoked_duplicate = copy.deepcopy(trust["keys"][0])
        revoked_duplicate["revoked"] = True
        trust["keys"].insert(0, revoked_duplicate)
        alternate = self.root / "revoked-duplicate-key-id-trust-store.json"
        alternate.write_text(json.dumps(trust, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid identity"):
            TrustStore.load(alternate)

    def test_cli_writes_a_non_certifying_result(self) -> None:
        intake_path = self.root / "intake.json"
        output_path = self.root / "validated.json"
        intake = self.build_intake(29)
        intake_path.write_text(json.dumps(intake, indent=2) + "\n", encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "validate",
                "--intake",
                str(intake_path),
                "--trust-store",
                str(self.trust_path),
                "--expected-trust-store-digest",
                self.trust_digest,
                "--evidence-root",
                str(self.root),
                "--subject-root",
                str(self.subject_roots[29]),
                "--output",
                str(output_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("certification=NOT_CERTIFIED", completed.stdout)
        self.assertEqual(
            "NOT_CERTIFIED",
            json.loads(output_path.read_text())["certification_decision"],
        )

    def test_cli_requires_out_of_band_trust_store_pin(self) -> None:
        intake_path = self.root / "missing-pin-intake.json"
        intake = self.build_intake(29)
        intake_path.write_text(json.dumps(intake, indent=2) + "\n", encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "validate",
                "--intake",
                str(intake_path),
                "--trust-store",
                str(self.trust_path),
                "--evidence-root",
                str(self.root),
                "--subject-root",
                str(self.subject_roots[29]),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("--expected-trust-store-digest", completed.stderr)

    def test_scaffold_is_valid_but_honestly_not_run(self) -> None:
        snapshot = self.root / "scaffold-snapshot.json"
        subject_root = self.root / "scaffold-subject-root"
        subject_file = (
            subject_root / "verification-packs/source-ingestion-pack/pack.json"
        )
        subject_file.parent.mkdir(parents=True)
        subject_content = canonical_bytes(
            {"key": "source-ingestion-pack", "version": "1.0.0"}
        )
        subject_file.write_bytes(subject_content)
        snapshot.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "batch35-verification-pack",
                    "key": "source-ingestion-pack",
                    "version": "1.0.0",
                    "repository_revision": "git:" + "c" * 40,
                    "file_set_policy": "exact",
                    "files": [
                        {
                            "path": "verification-packs/source-ingestion-pack/pack.json",
                            "role": "pack-manifest",
                            "sha256": "sha256:"
                            + hashlib.sha256(subject_content).hexdigest(),
                            "byte_size": len(subject_content),
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        output = self.root / "scaffold.json"
        scaffolded = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "scaffold",
                "--batch",
                "35",
                "--intake-id",
                "INTAKE-B35-SCAFFOLD",
                "--subject-key",
                "source-ingestion-pack",
                "--subject-version",
                "1.0.0",
                "--subject-snapshot",
                str(snapshot),
                "--subject-root",
                str(subject_root),
                "--producer-actor",
                "release-owner",
                "--producer-organization",
                "elmos-org",
                "--output",
                str(output),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            0, scaffolded.returncode, scaffolded.stdout + scaffolded.stderr
        )
        intake = json.loads(output.read_text())
        self.assertEqual({"NOT_RUN"}, {stage["status"] for stage in intake["stages"]})
        blocked = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "validate",
                "--intake",
                str(output),
                "--trust-store",
                str(self.trust_path),
                "--expected-trust-store-digest",
                self.trust_digest,
                "--evidence-root",
                str(self.root),
                "--subject-root",
                str(subject_root),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, blocked.returncode)
        self.assertIn("remains NOT_RUN", blocked.stderr)

    def test_scaffold_rejects_an_inexact_subject_root(self) -> None:
        subject_root = self.root / "inexact-scaffold-subject"
        subject_file = subject_root / "subject/manifest.json"
        subject_file.parent.mkdir(parents=True)
        subject_content = b"{}\n"
        subject_file.write_bytes(subject_content)
        (subject_root / "extra.txt").write_text("undeclared\n", encoding="utf-8")
        snapshot = self.root / "inexact-scaffold-snapshot.json"
        snapshot.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "batch29-route",
                    "key": "python-to-typescript",
                    "version": "1.0.0",
                    "repository_revision": "git:" + "e" * 40,
                    "file_set_policy": "exact",
                    "files": [
                        {
                            "path": "subject/manifest.json",
                            "role": "subject-manifest",
                            "sha256": "sha256:"
                            + hashlib.sha256(subject_content).hexdigest(),
                            "byte_size": len(subject_content),
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        args = SimpleNamespace(
            batch=29,
            intake_id="INTAKE-B29-INEXACT-SCAFFOLD",
            subject_key="python-to-typescript",
            subject_version="1.0.0",
            subject_snapshot=snapshot,
            subject_root=subject_root,
            producer_actor="release-owner",
            producer_organization="elmos-org",
        )
        with self.assertRaisesRegex(ExternalGateError, "undeclared extra files"):
            external_intake.scaffold(args)


if __name__ == "__main__":
    unittest.main()
