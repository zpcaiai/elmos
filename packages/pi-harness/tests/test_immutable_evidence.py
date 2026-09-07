from __future__ import annotations

import base64
import copy
import hashlib
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from elmos_pi_harness.canonical import digest, digest_bytes
from elmos_pi_harness.external_gates import (
    ExternalGateLedger,
    GateExecution,
    ReleaseCandidate,
)
from elmos_pi_harness.immutable_evidence import (
    S3ImmutableEvidenceArchive,
    S3ImmutableEvidenceConfig,
)
from elmos_pi_harness.models import ConflictError, PolicyDeniedError
from elmos_pi_harness.production import ExactTarget
from elmos_pi_harness.provider import ProviderOutcomeUnknown


def uid() -> str:
    return str(uuid.uuid4())


class FakeProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeSTS:
    def get_caller_identity(self):
        return {"Account": "123456789012"}


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, list[dict]] = {}
        self.fail_after_write = False
        self.fail_without_write = False
        self.lock_mode = "COMPLIANCE"

    def get_bucket_location(self, **_kwargs):
        return {"LocationConstraint": "ap-southeast-1"}

    def get_public_access_block(self, **_kwargs):
        return {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            }
        }

    def get_bucket_ownership_controls(self, **_kwargs):
        return {
            "OwnershipControls": {
                "Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]
            }
        }

    def get_bucket_encryption(self, **_kwargs):
        return {
            "ServerSideEncryptionConfiguration": {
                "Rules": [
                    {
                        "ApplyServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "aws:kms",
                            "KMSMasterKeyID": "arn:aws:kms:ap-southeast-1:123456789012:key/evidence",
                        }
                    }
                ]
            }
        }

    def get_bucket_versioning(self, **_kwargs):
        return {"Status": "Enabled"}

    def get_object_lock_configuration(self, **_kwargs):
        return {
            "ObjectLockConfiguration": {
                "ObjectLockEnabled": "Enabled",
                "Rule": {"DefaultRetention": {"Mode": self.lock_mode, "Days": 365}},
            }
        }

    def head_object(self, **request):
        versions = self.objects.get(request["Key"], [])
        if request.get("VersionId"):
            versions = [
                item for item in versions if item["VersionId"] == request["VersionId"]
            ]
        if not versions:
            raise FakeProviderError("NotFound")
        return copy.deepcopy(versions[-1])

    def put_object(self, **request):
        if self.fail_without_write:
            raise FakeProviderError("RequestTimeout")
        if request.get("IfNoneMatch") == "*" and request["Key"] in self.objects:
            raise FakeProviderError("PreconditionFailed")
        body = request["Body"]
        content = body if isinstance(body, bytes) else body.read()
        actual_checksum = base64.b64encode(hashlib.sha256(content).digest()).decode(
            "ascii"
        )
        if actual_checksum != request["ChecksumSHA256"]:
            raise FakeProviderError("BadDigest")
        version_id = f"version-{sum(len(value) for value in self.objects.values()) + 1}"
        head = {
            "ContentLength": len(content),
            "LastModified": datetime.now(timezone.utc),
            "Metadata": request["Metadata"],
            "ServerSideEncryption": request["ServerSideEncryption"],
            "SSEKMSKeyId": request["SSEKMSKeyId"],
            "ObjectLockMode": request["ObjectLockMode"],
            "ObjectLockRetainUntilDate": request["ObjectLockRetainUntilDate"],
            "ChecksumSHA256": request["ChecksumSHA256"],
            "VersionId": version_id,
            "ETag": '"fixture"',
        }
        self.objects.setdefault(request["Key"], []).append(head)
        if self.fail_after_write:
            self.fail_after_write = False
            raise FakeProviderError("RequestTimeout")
        return {"VersionId": version_id}


def config() -> S3ImmutableEvidenceConfig:
    return S3ImmutableEvidenceConfig(
        bucket="pi-harness-evidence",
        region="ap-southeast-1",
        account_id="123456789012",
        kms_key_arn="arn:aws:kms:ap-southeast-1:123456789012:key/evidence",
        retention_days=365,
    )


class ImmutableEvidenceTests(unittest.TestCase):
    def archive(
        self, s3: FakeS3 | None = None
    ) -> tuple[S3ImmutableEvidenceArchive, FakeS3]:
        client = s3 or FakeS3()
        return (
            S3ImmutableEvidenceArchive(
                config(), s3_client=client, sts_client=FakeSTS()
            ),
            client,
        )

    def test_create_only_object_lock_write_replay_and_receipt_verification(
        self,
    ) -> None:
        archive, _client = self.archive()
        content = b"immutable evidence"
        expected = digest_bytes(content)
        first = archive.put_bytes(
            "release/evidence.json",
            content,
            expected,
            authorization_id="AUTH-1",
            actor_id="archive-runner",
        )
        second = archive.put_bytes(
            "release/evidence.json",
            content,
            expected,
            authorization_id="AUTH-1",
            actor_id="archive-runner",
        )
        self.assertEqual(first["status"], "ARCHIVED")
        self.assertFalse(first["certified"])
        self.assertFalse(first["archive"]["replayed"])
        self.assertTrue(second["archive"]["replayed"])
        self.assertEqual(archive.verify_receipt(first)["status"], "VERIFIED")

        with self.assertRaises(ConflictError):
            archive.put_bytes(
                "release/evidence.json",
                content,
                expected,
                authorization_id="AUTH-DIFFERENT",
                actor_id="archive-runner",
            )

        tampered = copy.deepcopy(first)
        tampered["archive"]["content_length"] += 1
        with self.assertRaises(PolicyDeniedError):
            archive.verify_receipt(tampered)

        wrong_target = copy.deepcopy(first)
        wrong_target["archive"]["target"]["account_id"] = "999999999999"
        wrong_target["archive_receipt_digest"] = digest(wrong_target["archive"])
        with self.assertRaises(PolicyDeniedError):
            archive.verify_receipt(wrong_target)

        wrong_actor = copy.deepcopy(first)
        wrong_actor["archive"]["actor_id"] = "different-runner"
        wrong_actor["archive_receipt_digest"] = digest(wrong_actor["archive"])
        with self.assertRaises(ConflictError):
            archive.verify_receipt(wrong_actor)

        _key, versions = next(iter(_client.objects.items()))
        versions[-1]["ChecksumSHA256"] = None
        with self.assertRaises(ConflictError):
            archive.verify_receipt(first)

    def test_unknown_write_is_reconciled_or_remains_unknown_without_observation(
        self,
    ) -> None:
        client = FakeS3()
        archive, _ = self.archive(client)
        client.fail_after_write = True
        content = b"provider accepted before timeout"
        reconciled = archive.put_bytes(
            "release/reconciled.json",
            content,
            digest_bytes(content),
            authorization_id="AUTH-2",
            actor_id="archive-runner",
        )
        self.assertTrue(reconciled["archive"]["reconciled_after_unknown"])

        client.fail_without_write = True
        missing = b"never observed"
        with self.assertRaises(ProviderOutcomeUnknown):
            archive.put_bytes(
                "release/unknown.json",
                missing,
                digest_bytes(missing),
                authorization_id="AUTH-3",
                actor_id="archive-runner",
            )

    def test_short_object_retention_is_rejected(self) -> None:
        archive, client = self.archive()
        content = b"retention-bound evidence"
        receipt = archive.put_bytes(
            "release/retention.json",
            content,
            digest_bytes(content),
            authorization_id="AUTH-RETENTION",
            actor_id="archive-runner",
        )
        _key, versions = next(iter(client.objects.items()))
        versions[-1]["ObjectLockRetainUntilDate"] = versions[-1][
            "LastModified"
        ] + timedelta(days=30)
        with self.assertRaises(PolicyDeniedError):
            archive.verify_receipt(receipt)

    def test_wrong_object_lock_policy_is_rejected_before_any_write(self) -> None:
        client = FakeS3()
        client.lock_mode = "GOVERNANCE"
        with self.assertRaises(PolicyDeniedError):
            self.archive(client)

    def test_ledger_snapshot_archives_release_events_raw_objects_and_manifest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-worm-") as temporary:
            root = Path(temporary).resolve()
            release = ReleaseCandidate(
                release_id=uid(),
                source_git_sha="a" * 40,
                package_version="5.1.0",
                source_archive_digest="sha256:" + "b" * 64,
                artifact_digests={"wheel": "sha256:" + "c" * 64},
                implementation_trust_domain="engineering.example",
                created_at="2026-08-28T03:00:00Z",
                frozen_by="release-manager",
            )
            ledger = ExternalGateLedger.initialize(root / "ledger", release)
            raw = root / "raw.log"
            raw.write_bytes(b"native provider output")
            execution = GateExecution(
                result_id=uid(),
                gap_id="P0-G03",
                release_digest=release.release_digest,
                target=ExactTarget(
                    "aws",
                    "cloudformation",
                    "2010-05-15",
                    "ap-southeast-1",
                    "123456789012",
                    "staging",
                ),
                authorization_id="AUTH-CLOUD",
                executor_id="cloud-runner",
                producer_trust_domain="engineering.example",
                environment_digest="sha256:" + "d" * 64,
                started_at=(datetime.now(timezone.utc) - timedelta(minutes=2))
                .isoformat()
                .replace("+00:00", "Z"),
                completed_at=(datetime.now(timezone.utc) - timedelta(minutes=1))
                .isoformat()
                .replace("+00:00", "Z"),
                raw_evidence_digests=(digest_bytes(raw.read_bytes()),),
                replay_reference="runbook://P0-G03",
                status="EXECUTED",
            )
            ledger.record_execution(execution, [raw])
            archive, client = self.archive()
            result = ledger.archive(
                archive,
                authorization_id="AUTH-ARCHIVE",
                actor_id="archive-runner",
            )
            self.assertEqual(result["status"], "ARCHIVED")
            self.assertEqual(result["record_count"], 3)
            self.assertEqual(len(client.objects), 4)
            self.assertEqual(result["certification"], "NOT_CERTIFIED")
            self.assertFalse(result["certified"])


if __name__ == "__main__":
    unittest.main()
