"""Content-addressed artifact backends for local and managed object storage."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .canonical import digest_bytes, require_nonempty, require_uuid
from .models import ConflictError, PolicyDeniedError


class ArtifactBackend(Protocol):
    def put(
        self, tenant_id: str, sha256: str, content: bytes, metadata: Mapping[str, Any]
    ) -> str: ...
    def get(self, tenant_id: str, sha256: str) -> bytes: ...


@dataclass(frozen=True)
class S3ArtifactConfig:
    bucket: str
    region: str
    account_id: str
    kms_key_arn: str
    prefix: str = "pi-harness/artifacts"

    def __post_init__(self) -> None:
        for name in ("bucket", "region", "account_id", "kms_key_arn", "prefix"):
            require_nonempty(getattr(self, name), name, 512)
        if not self.kms_key_arn.startswith(
            f"arn:aws:kms:{self.region}:{self.account_id}:key/"
        ):
            raise ValueError("KMS key ARN must bind the exact region and account")
        if self.prefix.startswith("/") or ".." in self.prefix.split("/"):
            raise ValueError("artifact prefix is unsafe")


class S3ArtifactBackend:
    """S3 backend requiring account binding, KMS encryption, and public blocking."""

    def __init__(
        self,
        config: S3ArtifactConfig,
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
                "S3 credentials do not match the configured account"
            )
        location = (
            s3_client.get_bucket_location(Bucket=config.bucket).get(
                "LocationConstraint"
            )
            or "us-east-1"
        )
        if location != config.region:
            raise PolicyDeniedError("S3 bucket region does not match the exact target")
        public = s3_client.get_public_access_block(Bucket=config.bucket)[
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
            raise PolicyDeniedError("S3 public access block is incomplete")
        encryption = s3_client.get_bucket_encryption(Bucket=config.bucket)[
            "ServerSideEncryptionConfiguration"
        ]["Rules"]
        if not any(
            rule.get("ApplyServerSideEncryptionByDefault", {}).get("KMSMasterKeyID")
            == config.kms_key_arn
            for rule in encryption
        ):
            raise PolicyDeniedError(
                "S3 default KMS key does not match the configured key"
            )
        self.client = s3_client

    def put(
        self, tenant_id: str, sha256: str, content: bytes, metadata: Mapping[str, Any]
    ) -> str:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        if digest_bytes(content) != sha256:
            raise ConflictError("artifact content digest mismatch")
        key = self._key(tenant_id, sha256)
        native_metadata = {"sha256": sha256, "tenant-id": tenant_id}
        try:
            existing = self.client.head_object(Bucket=self.config.bucket, Key=key)
        except Exception as exc:
            error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if error_code not in {"404", "NoSuchKey", "NotFound"}:
                raise
        else:
            if (
                int(existing.get("ContentLength", -1)) != len(content)
                or existing.get("Metadata", {}).get("sha256") != sha256
            ):
                raise ConflictError(
                    "existing content-addressed artifact does not match"
                )
            return f"s3://{self.config.bucket}/{key}"
        self.client.put_object(
            Bucket=self.config.bucket,
            Key=key,
            Body=content,
            ContentLength=len(content),
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=self.config.kms_key_arn,
            BucketKeyEnabled=True,
            Metadata=native_metadata,
            Tagging="managed-by=elmos-pi-harness",
        )
        observed = self.client.head_object(Bucket=self.config.bucket, Key=key)
        if (
            int(observed.get("ContentLength", -1)) != len(content)
            or observed.get("Metadata", {}).get("sha256") != sha256
        ):
            raise ConflictError("S3 artifact post-write verification failed")
        return f"s3://{self.config.bucket}/{key}"

    def get(self, tenant_id: str, sha256: str) -> bytes:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        response = self.client.get_object(
            Bucket=self.config.bucket, Key=self._key(tenant_id, sha256)
        )
        content = response["Body"].read()
        if digest_bytes(content) != sha256:
            raise ConflictError("S3 artifact failed digest verification")
        return content

    def _key(self, tenant_id: str, sha256: str) -> str:
        if not sha256.startswith("sha256:") or len(sha256) != 71:
            raise ValueError("artifact digest must be canonical sha256")
        hexdigest = sha256[7:]
        return f"{self.config.prefix}/{tenant_id}/{hexdigest[:2]}/{hexdigest}"
