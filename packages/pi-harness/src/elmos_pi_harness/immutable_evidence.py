"""Independently retained immutable evidence archives.

The local external-gate ledger detects application-visible tampering.  This
module adds an exact-target S3 Object Lock boundary for production retention.
Archive writes are create-only, KMS encrypted, checksum verified, version
bound, and fail with an UNKNOWN outcome when the provider result cannot be
reconciled safely.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Literal

from .canonical import digest, digest_bytes, require_nonempty, utc_now
from .models import ConflictError, PolicyDeniedError
from .provider import ProviderOutcomeUnknown
from .production import ExactTarget


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_ACCOUNT = re.compile(r"^[0-9]{12}$")
_BUCKET = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{1,61}[a-z0-9])$")
_REGION = re.compile(r"^[a-z]{2}(?:-[a-z0-9]+)+-[0-9]+$")
_KMS_ARN = re.compile(
    r"^arn:(?:aws|aws-us-gov|aws-cn):kms:(?P<region>[^:]+):"
    r"(?P<account>[0-9]{12}):key/(?P<key>[A-Za-z0-9-]+)$"
)


@dataclass(frozen=True)
class S3ImmutableEvidenceConfig:
    bucket: str
    region: str
    account_id: str
    kms_key_arn: str
    retention_days: int
    retention_mode: Literal["COMPLIANCE", "GOVERNANCE"] = "COMPLIANCE"
    prefix: str = "pi-harness/external-evidence"

    def __post_init__(self) -> None:
        for name in ("bucket", "region", "account_id", "kms_key_arn", "prefix"):
            require_nonempty(getattr(self, name), name, 512)
        if (
            not _BUCKET.fullmatch(self.bucket)
            or ".." in self.bucket
            or re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", self.bucket)
        ):
            raise ValueError("bucket is not a valid general-purpose S3 bucket name")
        if not _REGION.fullmatch(self.region):
            raise ValueError("region must be an explicit AWS region")
        if not _ACCOUNT.fullmatch(self.account_id):
            raise ValueError("account_id must contain exactly 12 digits")
        kms_match = _KMS_ARN.fullmatch(self.kms_key_arn)
        if (
            kms_match is None
            or kms_match.group("region") != self.region
            or kms_match.group("account") != self.account_id
        ):
            raise ValueError("KMS key ARN must bind the exact region and account")
        if self.retention_mode not in {"COMPLIANCE", "GOVERNANCE"}:
            raise ValueError("retention_mode must be COMPLIANCE or GOVERNANCE")
        if self.retention_days < 90 or self.retention_days > 3650:
            raise ValueError("retention_days must be between 90 and 3650")
        path = PurePosixPath(self.prefix)
        if (
            path.is_absolute()
            or ".." in path.parts
            or not path.parts
            or self.prefix != "/".join(path.parts)
        ):
            raise ValueError("evidence archive prefix is unsafe")

    @property
    def target(self) -> ExactTarget:
        return ExactTarget(
            provider="aws",
            service="s3-object-lock",
            version="2006-03-01",
            region=self.region,
            account_id=self.account_id,
            environment="evidence-retention",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "region": self.region,
            "account_id": self.account_id,
            "kms_key_arn": self.kms_key_arn,
            "retention_days": self.retention_days,
            "retention_mode": self.retention_mode,
            "prefix": self.prefix,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "S3ImmutableEvidenceConfig":
        fields = {
            "bucket",
            "region",
            "account_id",
            "kms_key_arn",
            "retention_days",
            "retention_mode",
            "prefix",
        }
        if set(value) != fields:
            raise ValueError("immutable evidence configuration fields mismatch")
        if not isinstance(value["retention_days"], int) or isinstance(
            value["retention_days"], bool
        ):
            raise ValueError("retention_days must be an integer")
        return cls(**{name: value[name] for name in fields})


class S3ImmutableEvidenceArchive:
    """Create-only Object Lock archive with provider-result reconciliation."""

    def __init__(
        self,
        config: S3ImmutableEvidenceConfig,
        *,
        s3_client: Any | None = None,
        sts_client: Any | None = None,
    ) -> None:
        self.config = config
        if s3_client is None or sts_client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - optional production extra
                raise RuntimeError(
                    "boto3 is required; install elmos-pi-harness[cloud]"
                ) from exc
            session = boto3.Session(region_name=config.region)
            s3_client = session.client("s3")
            sts_client = session.client("sts")
        if str(sts_client.get_caller_identity().get("Account")) != config.account_id:
            raise PolicyDeniedError(
                "evidence archive credentials do not match the configured account"
            )
        expected_owner = {"ExpectedBucketOwner": config.account_id}
        location = (
            s3_client.get_bucket_location(
                Bucket=config.bucket, **expected_owner
            ).get(
                "LocationConstraint"
            )
            or "us-east-1"
        )
        if location != config.region:
            raise PolicyDeniedError(
                "evidence archive bucket region does not match the exact target"
            )
        public = s3_client.get_public_access_block(
            Bucket=config.bucket, **expected_owner
        )[
            "PublicAccessBlockConfiguration"
        ]
        if not all(
            public.get(name) is True
            for name in (
                "BlockPublicAcls",
                "IgnorePublicAcls",
                "BlockPublicPolicy",
                "RestrictPublicBuckets",
            )
        ):
            raise PolicyDeniedError(
                "evidence archive public access block is incomplete"
            )
        ownership = s3_client.get_bucket_ownership_controls(
            Bucket=config.bucket, **expected_owner
        )["OwnershipControls"]["Rules"]
        if not any(
            rule.get("ObjectOwnership") == "BucketOwnerEnforced"
            for rule in ownership
        ):
            raise PolicyDeniedError(
                "evidence archive must enforce bucket-owner object ownership"
            )
        encryption = s3_client.get_bucket_encryption(
            Bucket=config.bucket, **expected_owner
        )[
            "ServerSideEncryptionConfiguration"
        ]["Rules"]
        if not any(
            rule.get("ApplyServerSideEncryptionByDefault", {}).get("SSEAlgorithm")
            == "aws:kms"
            and rule.get("ApplyServerSideEncryptionByDefault", {}).get("KMSMasterKeyID")
            == config.kms_key_arn
            for rule in encryption
        ):
            raise PolicyDeniedError(
                "evidence archive default KMS key does not match the configured key"
            )
        versioning = s3_client.get_bucket_versioning(
            Bucket=config.bucket, **expected_owner
        )
        if versioning.get("Status") != "Enabled":
            raise PolicyDeniedError("evidence archive versioning is not enabled")
        lock = s3_client.get_object_lock_configuration(
            Bucket=config.bucket, **expected_owner
        )
        if (
            lock.get("ObjectLockConfiguration", {}).get("ObjectLockEnabled")
            != "Enabled"
        ):
            raise PolicyDeniedError("S3 Object Lock is not enabled")
        default_retention = (
            lock.get("ObjectLockConfiguration", {})
            .get("Rule", {})
            .get("DefaultRetention", {})
        )
        if default_retention.get("Mode") != config.retention_mode:
            raise PolicyDeniedError("S3 Object Lock mode does not match policy")
        configured_days = (
            int(default_retention.get("Days", 0))
            + int(default_retention.get("Years", 0)) * 365
        )
        if configured_days < config.retention_days:
            raise PolicyDeniedError("S3 Object Lock retention is shorter than required")
        self.client = s3_client

    @staticmethod
    def _error_code(exc: Exception) -> str | None:
        response = getattr(exc, "response", {}) or {}
        if not isinstance(response, Mapping):
            return None
        error = response.get("Error")
        if not isinstance(error, Mapping):
            return None
        code = error.get("Code")
        return code if isinstance(code, str) else None

    @staticmethod
    def _logical_key(value: str) -> str:
        text = require_nonempty(value, "logical_key", 2048)
        path = PurePosixPath(text)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("archive logical key is unsafe")
        return "/".join(path.parts)

    def _key(self, logical_key: str) -> str:
        return f"{self.config.prefix}/{self._logical_key(logical_key)}"

    def _head(
        self, key: str, *, version_id: str | None = None
    ) -> Mapping[str, Any] | None:
        request: dict[str, Any] = {
            "Bucket": self.config.bucket,
            "Key": key,
            "ChecksumMode": "ENABLED",
            "ExpectedBucketOwner": self.config.account_id,
        }
        if version_id:
            request["VersionId"] = version_id
        try:
            return self.client.head_object(**request)
        except Exception as exc:
            if self._error_code(exc) in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise

    def _verify_head(
        self,
        head: Mapping[str, Any],
        *,
        expected_digest: str,
        expected_size: int,
        expected_authorization_id: str,
        expected_actor_id: str,
    ) -> None:
        if int(head.get("ContentLength", -1)) != expected_size:
            raise ConflictError("immutable evidence object length mismatch")
        metadata = head.get("Metadata", {})
        if metadata.get("sha256") != expected_digest:
            raise ConflictError("immutable evidence object digest metadata mismatch")
        if metadata.get("authorization-id") != expected_authorization_id:
            raise ConflictError(
                "immutable evidence object authorization metadata mismatch"
            )
        if metadata.get("actor-id") != expected_actor_id:
            raise ConflictError("immutable evidence object actor metadata mismatch")
        if head.get("ServerSideEncryption") != "aws:kms":
            raise PolicyDeniedError("immutable evidence object is not KMS encrypted")
        if head.get("SSEKMSKeyId") != self.config.kms_key_arn:
            raise PolicyDeniedError("immutable evidence object used the wrong KMS key")
        if head.get("ObjectLockMode") != self.config.retention_mode:
            raise PolicyDeniedError("immutable evidence object lock mode mismatch")
        retain_until = head.get("ObjectLockRetainUntilDate")
        if not isinstance(retain_until, datetime) or retain_until.tzinfo is None:
            raise PolicyDeniedError("immutable evidence object lacks a retention time")
        last_modified = head.get("LastModified")
        if not isinstance(last_modified, datetime) or last_modified.tzinfo is None:
            raise PolicyDeniedError(
                "immutable evidence object lacks an authoritative creation time"
            )
        minimum_retain_until = last_modified.astimezone(timezone.utc) + timedelta(
            days=self.config.retention_days
        )
        if retain_until.astimezone(timezone.utc) < minimum_retain_until:
            raise PolicyDeniedError(
                "immutable evidence object retention is shorter than policy"
            )
        if retain_until.astimezone(timezone.utc) <= datetime.now(timezone.utc):
            raise PolicyDeniedError("immutable evidence object retention has expired")
        expected_checksum = base64.b64encode(
            bytes.fromhex(expected_digest.removeprefix("sha256:"))
        ).decode("ascii")
        checksum = head.get("ChecksumSHA256")
        if checksum != expected_checksum:
            raise ConflictError("immutable evidence native checksum mismatch")

    def _receipt(
        self,
        *,
        key: str,
        expected_digest: str,
        head: Mapping[str, Any],
        authorization_id: str,
        actor_id: str,
        replayed: bool,
        reconciled_after_unknown: bool,
    ) -> dict[str, Any]:
        version_id = require_nonempty(head.get("VersionId"), "VersionId", 1024)
        normalized = {
            "target": self.config.target.to_dict(),
            "bucket": self.config.bucket,
            "key": key,
            "version_id": version_id,
            "content_digest": expected_digest,
            "content_length": int(head["ContentLength"]),
            "authorization_id": authorization_id,
            "actor_id": actor_id,
            "retention_mode": head["ObjectLockMode"],
            "object_last_modified": head["LastModified"]
            .astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "retain_until": head["ObjectLockRetainUntilDate"]
            .astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "kms_key_arn": head["SSEKMSKeyId"],
            "native_checksum": head.get("ChecksumSHA256"),
            "etag": head.get("ETag"),
            "replayed": replayed,
            "reconciled_after_unknown": reconciled_after_unknown,
            "observed_at": utc_now(),
        }
        return {
            "status": "ARCHIVED",
            "certified": False,
            "archive": normalized,
            "archive_receipt_digest": digest(normalized),
        }

    def _put(
        self,
        *,
        logical_key: str,
        body: bytes | BinaryIO,
        expected_digest: str,
        size: int,
        authorization_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        if not _DIGEST.fullmatch(expected_digest):
            raise ValueError("expected_digest must be a lowercase SHA-256 digest")
        authorization_id = require_nonempty(authorization_id, "authorization_id", 512)
        actor_id = require_nonempty(actor_id, "actor_id", 512)
        key = self._key(logical_key)
        existing = self._head(key)
        if existing is not None:
            self._verify_head(
                existing,
                expected_digest=expected_digest,
                expected_size=size,
                expected_authorization_id=authorization_id,
                expected_actor_id=actor_id,
            )
            return self._receipt(
                key=key,
                expected_digest=expected_digest,
                head=existing,
                authorization_id=authorization_id,
                actor_id=actor_id,
                replayed=True,
                reconciled_after_unknown=False,
            )
        retain_until = datetime.now(timezone.utc) + timedelta(
            days=self.config.retention_days + 1
        )
        checksum = base64.b64encode(
            bytes.fromhex(expected_digest.removeprefix("sha256:"))
        ).decode("ascii")
        try:
            response = self.client.put_object(
                Bucket=self.config.bucket,
                Key=key,
                ExpectedBucketOwner=self.config.account_id,
                Body=body,
                ContentLength=size,
                ContentType="application/octet-stream",
                ChecksumAlgorithm="SHA256",
                ChecksumSHA256=checksum,
                ServerSideEncryption="aws:kms",
                SSEKMSKeyId=self.config.kms_key_arn,
                BucketKeyEnabled=True,
                ObjectLockMode=self.config.retention_mode,
                ObjectLockRetainUntilDate=retain_until,
                Metadata={
                    "sha256": expected_digest,
                    "authorization-id": authorization_id,
                    "actor-id": actor_id,
                },
                Tagging="managed-by=elmos-pi-harness&record-class=external-evidence",
                IfNoneMatch="*",
            )
            version_id = response.get("VersionId")
            reconciled_after_unknown = False
        except Exception as exc:
            if self._error_code(exc) in {"PreconditionFailed", "412"}:
                observed = self._head(key)
                if observed is None:
                    raise ProviderOutcomeUnknown(
                        "S3 precondition failed but no immutable object is observable"
                    ) from exc
                self._verify_head(
                    observed,
                    expected_digest=expected_digest,
                    expected_size=size,
                    expected_authorization_id=authorization_id,
                    expected_actor_id=actor_id,
                )
                return self._receipt(
                    key=key,
                    expected_digest=expected_digest,
                    head=observed,
                    authorization_id=authorization_id,
                    actor_id=actor_id,
                    replayed=True,
                    reconciled_after_unknown=True,
                )
            try:
                observed = self._head(key)
            except Exception as observation_error:
                raise ProviderOutcomeUnknown(
                    "S3 archive result and reconciliation are both unknown"
                ) from observation_error
            if observed is None:
                raise ProviderOutcomeUnknown(
                    "S3 archive result is unknown and no object is observable"
                ) from exc
            self._verify_head(
                observed,
                expected_digest=expected_digest,
                expected_size=size,
                expected_authorization_id=authorization_id,
                expected_actor_id=actor_id,
            )
            return self._receipt(
                key=key,
                expected_digest=expected_digest,
                head=observed,
                authorization_id=authorization_id,
                actor_id=actor_id,
                replayed=False,
                reconciled_after_unknown=True,
            )
        observed = self._head(key, version_id=version_id)
        if observed is None:
            raise ProviderOutcomeUnknown(
                "S3 accepted the archive write but its exact version is not observable"
            )
        self._verify_head(
            observed,
            expected_digest=expected_digest,
            expected_size=size,
            expected_authorization_id=authorization_id,
            expected_actor_id=actor_id,
        )
        return self._receipt(
            key=key,
            expected_digest=expected_digest,
            head=observed,
            authorization_id=authorization_id,
            actor_id=actor_id,
            replayed=False,
            reconciled_after_unknown=reconciled_after_unknown,
        )

    def put_bytes(
        self,
        logical_key: str,
        content: bytes,
        expected_digest: str,
        *,
        authorization_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        if digest_bytes(content) != expected_digest:
            raise ConflictError("immutable evidence byte digest mismatch")
        return self._put(
            logical_key=logical_key,
            body=content,
            expected_digest=expected_digest,
            size=len(content),
            authorization_id=authorization_id,
            actor_id=actor_id,
        )

    def put_file(
        self,
        logical_key: str,
        source: str | Path,
        expected_digest: str,
        *,
        authorization_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        path = Path(source)
        if not path.is_absolute() or path.is_symlink():
            raise PolicyDeniedError(
                "immutable evidence source must be an absolute non-symlink path"
            )
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise PolicyDeniedError(
                    "immutable evidence source is not a regular file"
                )
            hasher = hashlib.sha256()
            with os.fdopen(descriptor, "rb", closefd=False) as source_handle:
                while chunk := source_handle.read(1024 * 1024):
                    hasher.update(chunk)
                actual = "sha256:" + hasher.hexdigest()
                if actual != expected_digest:
                    raise ConflictError("immutable evidence file digest mismatch")
                source_handle.seek(0)
                return self._put(
                    logical_key=logical_key,
                    body=source_handle,
                    expected_digest=expected_digest,
                    size=metadata.st_size,
                    authorization_id=authorization_id,
                    actor_id=actor_id,
                )
        finally:
            os.close(descriptor)

    def verify_receipt(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        if set(receipt) != {
            "status",
            "certified",
            "archive",
            "archive_receipt_digest",
        }:
            raise ValueError("archive receipt fields mismatch")
        if receipt.get("status") != "ARCHIVED" or receipt.get("certified") is not False:
            raise PolicyDeniedError("archive receipt status is invalid")
        archive = receipt.get("archive")
        if not isinstance(archive, Mapping):
            raise ValueError("archive receipt is malformed")
        if set(archive) != {
            "target",
            "bucket",
            "key",
            "version_id",
            "content_digest",
            "content_length",
            "authorization_id",
            "actor_id",
            "retention_mode",
            "object_last_modified",
            "retain_until",
            "kms_key_arn",
            "native_checksum",
            "etag",
            "replayed",
            "reconciled_after_unknown",
            "observed_at",
        }:
            raise ValueError("archive receipt detail fields mismatch")
        if receipt.get("archive_receipt_digest") != digest(dict(archive)):
            raise PolicyDeniedError("archive receipt digest mismatch")
        if archive.get("target") != self.config.target.to_dict():
            raise PolicyDeniedError("archive receipt exact target mismatch")
        if archive.get("bucket") != self.config.bucket:
            raise PolicyDeniedError("archive receipt bucket mismatch")
        version_id = require_nonempty(archive.get("version_id"), "version_id", 1024)
        authorization_id = require_nonempty(
            archive.get("authorization_id"), "authorization_id", 512
        )
        actor_id = require_nonempty(archive.get("actor_id"), "actor_id", 512)
        expected_digest = str(archive.get("content_digest", ""))
        if not _DIGEST.fullmatch(expected_digest):
            raise ValueError("archive receipt content digest is invalid")
        expected_size = archive.get("content_length")
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 0
        ):
            raise ValueError("archive receipt content length is invalid")
        if archive.get("retention_mode") != self.config.retention_mode:
            raise PolicyDeniedError("archive receipt retention mode mismatch")
        if archive.get("kms_key_arn") != self.config.kms_key_arn:
            raise PolicyDeniedError("archive receipt KMS key mismatch")
        if not isinstance(archive.get("replayed"), bool) or not isinstance(
            archive.get("reconciled_after_unknown"), bool
        ):
            raise ValueError("archive receipt reconciliation flags are invalid")
        key = self._key(
            str(archive.get("key", "")).removeprefix(self.config.prefix + "/")
        )
        if key != archive.get("key"):
            raise PolicyDeniedError("archive receipt key mismatch")
        head = self._head(key, version_id=version_id)
        if head is None:
            raise PolicyDeniedError("archive receipt version is not observable")
        self._verify_head(
            head,
            expected_digest=expected_digest,
            expected_size=expected_size,
            expected_authorization_id=authorization_id,
            expected_actor_id=actor_id,
        )
        retain_until = head["ObjectLockRetainUntilDate"].astimezone(timezone.utc)
        normalized_retain_until = retain_until.isoformat().replace("+00:00", "Z")
        if archive.get("retain_until") != normalized_retain_until:
            raise PolicyDeniedError("archive receipt retention timestamp mismatch")
        last_modified = head["LastModified"].astimezone(timezone.utc)
        normalized_last_modified = last_modified.isoformat().replace("+00:00", "Z")
        if archive.get("object_last_modified") != normalized_last_modified:
            raise PolicyDeniedError("archive receipt creation timestamp mismatch")
        if archive.get("native_checksum") != head.get("ChecksumSHA256"):
            raise PolicyDeniedError("archive receipt native checksum mismatch")
        if archive.get("etag") != head.get("ETag"):
            raise PolicyDeniedError("archive receipt ETag mismatch")
        return {
            "status": "VERIFIED",
            "certified": False,
            "archive_receipt_digest": receipt["archive_receipt_digest"],
            "version_id": archive["version_id"],
        }


def s3_immutable_config_from_file(path: str | Path) -> S3ImmutableEvidenceConfig:
    source = Path(path)
    if not source.is_absolute() or source.is_symlink():
        raise PolicyDeniedError(
            "immutable evidence configuration must be an absolute non-symlink path"
        )
    descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1024 * 1024:
            raise PolicyDeniedError(
                "immutable evidence configuration must be a regular file below 1 MiB"
            )
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            raw = handle.read(1024 * 1024 + 1)
    finally:
        os.close(descriptor)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("immutable evidence configuration is not UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("immutable evidence configuration must be a JSON object")
    return S3ImmutableEvidenceConfig.from_dict(value)
