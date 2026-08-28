"""Production persistence adapters for artifacts and committed event delivery.

The adapters in this module are deliberately client-injected.  Importing the
runtime never opens a network connection; a deployment must bind an
authenticated SDK client and explicitly call the operation.  This keeps the
archive supplied with the task as data rather than executable authority while
still providing complete, real adapter code for S3, Kafka and JetStream.
"""

from __future__ import annotations

import base64
import hashlib
import io
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol

from .errors import ContractViolation, CorruptState, NotConfigured, TenantIsolationError
from .models import ArtifactRef, canonical_json, utc_now, validate_id


class ObjectStoreClient(Protocol):
    def put_object(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def get_object(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def head_object(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def head_bucket(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def get_bucket_versioning(self, **kwargs: Any) -> Mapping[str, Any]: ...


class S3ContentAddressedStore:
    """Tenant-scoped S3/MinIO CAS with digest and encryption enforcement."""

    def __init__(
        self,
        bucket: str,
        *,
        client: ObjectStoreClient | None = None,
        prefix: str = "elmos/openhands",
        kms_key_id: str | None = None,
        require_versioning: bool = True,
    ) -> None:
        if not bucket or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,254}", bucket):
            raise ContractViolation("object-store bucket is invalid")
        if prefix.startswith("/") or ".." in prefix.split("/"):
            raise ContractViolation("object-store prefix is unsafe")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.kms_key_id = kms_key_id
        self.require_versioning = require_versioning
        self._client = client
        self._configuration_validated = False

    @property
    def client(self) -> ObjectStoreClient:
        if self._client is None:
            try:
                import boto3  # type: ignore[import-untyped]
            except ImportError as error:  # pragma: no cover - optional production dependency
                raise NotConfigured("boto3 is required for the S3 artifact adapter") from error
            self._client = boto3.client("s3")
        return self._client

    def validate_configuration(self) -> None:
        self.client.head_bucket(Bucket=self.bucket)
        versioning = self.client.get_bucket_versioning(Bucket=self.bucket)
        if self.require_versioning and versioning.get("Status") != "Enabled":
            raise NotConfigured("artifact bucket versioning must be enabled")
        self._configuration_validated = True

    def put(
        self,
        tenant_id: str,
        data: bytes,
        *,
        kind: str = "artifact",
        media_type: str = "application/octet-stream",
    ) -> ArtifactRef:
        self._validate_tenant(tenant_id)
        validate_id(kind, "artifact.kind")
        if not isinstance(data, bytes):
            raise ContractViolation("artifact payload must be bytes")
        if not self._configuration_validated:
            self.validate_configuration()
        digest_hex = hashlib.sha256(data).hexdigest()
        digest = "sha256:" + digest_hex
        key = self._key(tenant_id, digest)
        try:
            existing = self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as error:
            if not _is_not_found(error):
                raise
        else:
            metadata = {str(k).lower(): str(v) for k, v in dict(existing.get("Metadata", {})).items()}
            if metadata.get("sha256") != digest_hex or metadata.get("tenant-id") != tenant_id:
                raise CorruptState("existing S3 artifact metadata does not match its CAS key")
            return ArtifactRef(tenant_id, digest, len(data), media_type, kind)

        request: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": data,
            "ContentType": media_type,
            "ChecksumSHA256": base64.b64encode(hashlib.sha256(data).digest()).decode("ascii"),
            "Metadata": {
                "tenant-id": tenant_id,
                "sha256": digest_hex,
                "kind": kind,
                "created-at": utc_now(),
            },
        }
        if self.kms_key_id:
            request.update(ServerSideEncryption="aws:kms", SSEKMSKeyId=self.kms_key_id)
        else:
            request["ServerSideEncryption"] = "AES256"
        response = self.client.put_object(**request)
        if response.get("ChecksumSHA256") not in {None, request["ChecksumSHA256"]}:
            raise CorruptState("S3 acknowledged a different object checksum")
        return ArtifactRef(tenant_id, digest, len(data), media_type, kind)

    def get(self, tenant_id: str, ref: ArtifactRef | str) -> bytes:
        self._validate_tenant(tenant_id)
        digest = ref.digest if isinstance(ref, ArtifactRef) else ref
        if isinstance(ref, ArtifactRef) and ref.tenant_id != tenant_id:
            raise TenantIsolationError("artifact belongs to another tenant")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise CorruptState("invalid artifact digest")
        response = self.client.get_object(Bucket=self.bucket, Key=self._key(tenant_id, digest))
        body = response.get("Body")
        if isinstance(body, bytes):
            data = body
        elif callable(getattr(body, "read", None)):
            data = body.read()  # type: ignore[union-attr]
        else:
            raise CorruptState("object-store response has no readable body")
        if not isinstance(data, bytes) or "sha256:" + hashlib.sha256(data).hexdigest() != digest:
            raise CorruptState("S3 artifact failed content digest verification")
        metadata = {str(k).lower(): str(v) for k, v in dict(response.get("Metadata", {})).items()}
        if metadata.get("tenant-id") not in {None, tenant_id}:
            raise TenantIsolationError("object-store metadata belongs to another tenant")
        return data

    def exists(self, tenant_id: str, digest: str) -> bool:
        self._validate_tenant(tenant_id)
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            return False
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=self._key(tenant_id, digest))
        except Exception as error:
            if _is_not_found(error):
                return False
            raise
        metadata = {str(k).lower(): str(v) for k, v in dict(response.get("Metadata", {})).items()}
        return metadata.get("sha256") == digest.removeprefix("sha256:") and metadata.get("tenant-id") == tenant_id

    def _key(self, tenant_id: str, digest: str) -> str:
        return f"{self.prefix}/tenants/{tenant_id}/sha256/{digest.removeprefix('sha256:')}"

    @staticmethod
    def _validate_tenant(tenant_id: str) -> None:
        validate_id(tenant_id, "tenant_id")
        if "/" in tenant_id or "\\" in tenant_id or tenant_id in {".", ".."}:
            raise TenantIsolationError("unsafe tenant object-store scope")


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    outbox_id: int
    tenant_id: str
    run_id: str
    seq: int
    event: Mapping[str, Any]

    @property
    def message_key(self) -> str:
        event_id = str(self.event.get("event_id", ""))
        return event_id or f"{self.tenant_id}:{self.run_id}:{self.seq}"


class OutboxSource(Protocol):
    def pending_outbox(self, *, limit: int = 100) -> tuple[OutboxRecord, ...]: ...

    def mark_outbox_published(self, outbox_ids: Iterable[int]) -> None: ...


class EventPublisher(Protocol):
    def publish(self, subject: str, payload: bytes, *, message_key: str, headers: Mapping[str, str]) -> None: ...


class NatsJetStreamPublisher:
    """Synchronous wrapper around a configured JetStream client."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def publish(self, subject: str, payload: bytes, *, message_key: str, headers: Mapping[str, str]) -> None:
        result = self.client.publish(subject, payload, headers={**headers, "Nats-Msg-Id": message_key})
        if hasattr(result, "result"):
            result.result()
        elif hasattr(result, "__await__"):
            raise ContractViolation("async JetStream client requires an async deployment wrapper")


class KafkaEventPublisher:
    """Kafka publisher that waits for broker acknowledgement before outbox commit."""

    def __init__(self, producer: Any, *, acknowledgement_timeout: float = 30.0) -> None:
        if acknowledgement_timeout <= 0:
            raise ContractViolation("Kafka acknowledgement timeout must be positive")
        self.producer = producer
        self.acknowledgement_timeout = acknowledgement_timeout

    def publish(self, subject: str, payload: bytes, *, message_key: str, headers: Mapping[str, str]) -> None:
        errors: list[BaseException] = []

        def delivered(error: BaseException | None, _message: Any) -> None:
            if error is not None:
                errors.append(error)

        self.producer.produce(
            subject,
            key=message_key.encode("utf-8"),
            value=payload,
            headers=[(name, value.encode("utf-8")) for name, value in sorted(headers.items())],
            on_delivery=delivered,
        )
        remaining = self.producer.flush(self.acknowledgement_timeout)
        if remaining or errors:
            raise RuntimeError("Kafka did not acknowledge committed outbox event") from (errors[0] if errors else None)


class TransactionalOutboxDispatcher:
    """Publishes only committed events and marks rows after broker acknowledgement."""

    def __init__(self, source: OutboxSource, publisher: EventPublisher, *, subject_prefix: str = "elmos.execution") -> None:
        if not subject_prefix or not all(part for part in subject_prefix.split(".")):
            raise ContractViolation("event subject prefix is invalid")
        self.source = source
        self.publisher = publisher
        self.subject_prefix = subject_prefix

    def dispatch_once(self, *, limit: int = 100) -> int:
        if limit < 1 or limit > 10_000:
            raise ContractViolation("outbox dispatch limit is out of bounds")
        published: list[int] = []
        for record in self.source.pending_outbox(limit=limit):
            event_type = str(record.event.get("event_type", "unknown")).replace("/", ".")
            subject = f"{self.subject_prefix}.{event_type}"
            payload = canonical_json(dict(record.event)).encode("utf-8")
            self.publisher.publish(
                subject,
                payload,
                message_key=record.message_key,
                headers={
                    "content-type": "application/json",
                    "tenant-id": record.tenant_id,
                    "run-id": record.run_id,
                    "event-seq": str(record.seq),
                },
            )
            published.append(record.outbox_id)
        if published:
            self.source.mark_outbox_published(published)
        return len(published)


def _is_not_found(error: BaseException) -> bool:
    response = getattr(error, "response", None)
    if isinstance(response, Mapping):
        error_body = response.get("Error", {})
        if isinstance(error_body, Mapping) and str(error_body.get("Code")) in {"404", "NoSuchKey", "NotFound"}:
            return True
    return isinstance(error, (FileNotFoundError, KeyError))


def bytes_body(data: bytes) -> io.BytesIO:
    """Small helper used by conformance tests and SDK shims."""

    return io.BytesIO(data)
