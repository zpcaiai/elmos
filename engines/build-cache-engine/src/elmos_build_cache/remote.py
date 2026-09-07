"""Remote shared cache.

Three properties drive the design:

* **A remote outage cannot corrupt local execution.** Every remote call is
  optional; failures degrade to local-only work and a bounded write-behind
  queue, never to a wedged run.
* **Identity is verified end to end.** The SHA-256 of the bytes we get back is
  recomputed locally. A transport checksum proves the pipe was clean, not that
  the object is the one we asked for.
* **An ActionResult becomes discoverable only after every blob it references is
  durable.** Metadata is published last, so a reader can never resolve an entry
  whose outputs are still uploading.

Trust namespaces are separate key spaces. A fork's result physically cannot
overwrite an official one.
"""

from __future__ import annotations

import os
import shutil
import threading
from collections import deque
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .canonical import canonical_json_bytes, digest_hex, digest_of, require_digest, sha256_bytes
from .cas import ContentAddressableStore
from .clock import SYSTEM_CLOCK, Clock
from .db import MetadataStore
from .enums import ArtifactStorageState, TrustNamespace
from .errors import ConflictError, DigestMismatch, NotFound, RemoteUnavailable

SCHEMA_VERSION = "1.0.0"
DEFAULT_MULTIPART_THRESHOLD = 64 * 1024 * 1024
DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024


class RemoteBackend(Protocol):
    """Minimal object-store surface. Implementations must be create-if-absent."""

    def exists(self, key: str) -> bool: ...

    def get(self, key: str) -> bytes: ...

    def put_if_absent(self, key: str, data: bytes) -> bool: ...

    def delete(self, key: str) -> bool: ...

    def list_prefix(self, prefix: str) -> Iterator[str]: ...


class FilesystemRemoteBackend:
    """A shared directory acting as the object store.

    Used for team NFS deployments and as the deterministic backend in tests.
    ``put_if_absent`` is implemented with ``os.link`` so two writers converge.
    """

    def __init__(self, root: Path, fail: bool = False) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        #: Test/chaos hook: when true every call raises RemoteUnavailable.
        self.fail = fail
        self.bytes_uploaded = 0
        self.bytes_downloaded = 0

    def _path(self, key: str) -> Path:
        safe = key.replace("..", "__")
        return self.root / safe

    def _check(self) -> None:
        if self.fail:
            raise RemoteUnavailable("remote backend is unavailable", backend="filesystem")

    def exists(self, key: str) -> bool:
        self._check()
        return self._path(key).exists()

    def get(self, key: str) -> bytes:
        self._check()
        path = self._path(key)
        if not path.exists():
            raise NotFound("remote object is missing", key=key)
        data = path.read_bytes()
        self.bytes_downloaded += len(data)
        return data

    def put_if_absent(self, key: str, data: bytes) -> bool:
        self._check()
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return False
        temporary = path.parent / f".{path.name}.incoming-{os.getpid()}-{os.urandom(4).hex()}"
        try:
            with temporary.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                return False
            except OSError:
                os.replace(temporary, path)
            self.bytes_uploaded += len(data)
            return True
        finally:
            temporary.unlink(missing_ok=True)

    def delete(self, key: str) -> bool:
        self._check()
        path = self._path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_prefix(self, prefix: str) -> Iterator[str]:
        self._check()
        base = self._path(prefix)
        root = base if base.is_dir() else base.parent
        if not root.exists():
            return
        for path in sorted(root.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                yield path.relative_to(self.root).as_posix()


class S3RemoteBackend:
    """S3/MinIO backend. Requires the ``s3`` extra (``boto3``)."""

    def __init__(self, bucket: str, prefix: str = "", client: Any | None = None) -> None:
        if client is None:  # pragma: no cover - requires credentials
            import boto3

            client = boto3.client("s3")
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.bytes_uploaded = 0
        self.bytes_downloaded = 0

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except Exception:  # noqa: BLE001 - any head failure means "treat as absent"
            return False

    def get(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
        except Exception as exc:  # noqa: BLE001
            raise NotFound("remote object is missing", key=key, error=str(exc)) from exc
        data: bytes = response["Body"].read()
        self.bytes_downloaded += len(data)
        return data

    def put_if_absent(self, key: str, data: bytes) -> bool:
        if self.exists(key):
            return False
        # ``IfNoneMatch`` gives conditional creation where the service supports
        # it; the pre-check above is the portable fallback.
        try:
            self.client.put_object(
                Bucket=self.bucket, Key=self._key(key), Body=data, IfNoneMatch="*"
            )
        except TypeError:  # pragma: no cover - older clients
            self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=data)
        except Exception as exc:  # noqa: BLE001
            if "PreconditionFailed" in str(exc) or "412" in str(exc):
                return False
            raise RemoteUnavailable("remote upload failed", key=key, error=str(exc)) from exc
        self.bytes_uploaded += len(data)
        return True

    def put_multipart(self, key: str, data: bytes, chunk_size: int) -> bool:
        """Native S3 multipart upload.

        The object becomes visible only when ``CompleteMultipartUpload``
        succeeds, so an interrupted transfer leaves nothing discoverable. On
        any failure the upload is aborted so the parts do not linger and accrue
        storage charges.
        """
        if self.exists(key):
            return False
        target = self._key(key)
        # S3 requires every part except the last to be at least 5 MiB.
        part_size = max(chunk_size, 5 * 1024 * 1024)
        created = self.client.create_multipart_upload(Bucket=self.bucket, Key=target)
        upload_id = created["UploadId"]
        try:
            parts = []
            for number, offset in enumerate(range(0, len(data), part_size), start=1):
                chunk = data[offset : offset + part_size]
                response = self.client.upload_part(
                    Bucket=self.bucket,
                    Key=target,
                    UploadId=upload_id,
                    PartNumber=number,
                    Body=chunk,
                )
                parts.append({"ETag": response["ETag"], "PartNumber": number})
            self.client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=target,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
        except Exception as exc:  # noqa: BLE001 - normalised, and always aborted
            self.abort_multipart(key, upload_id)
            raise RemoteUnavailable("multipart upload failed", key=key, error=str(exc)) from exc
        self.bytes_uploaded += len(data)
        return True

    def abort_multipart(self, key: str, upload_id: str) -> None:
        try:
            self.client.abort_multipart_upload(
                Bucket=self.bucket, Key=self._key(key), UploadId=upload_id
            )
        except Exception:  # noqa: BLE001, S110 - the caller is already failing;
            # an abort that cannot be delivered must not mask the original error.
            pass

    def list_multipart_uploads(self) -> list[dict[str, Any]]:
        """In-flight uploads. A healthy cache leaves none behind."""
        response = self.client.list_multipart_uploads(Bucket=self.bucket)
        uploads: list[dict[str, Any]] = response.get("Uploads", [])
        return uploads

    def delete(self, key: str) -> bool:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except Exception:  # noqa: BLE001
            return False

    def list_prefix(self, prefix: str) -> Iterator[str]:
        token: str | None = None
        while True:
            kwargs: dict[str, Any] = {"Bucket": self.bucket, "Prefix": self._key(prefix)}
            if token:
                kwargs["ContinuationToken"] = token
            response = self.client.list_objects_v2(**kwargs)
            for item in response.get("Contents", []):
                key = item["Key"]
                yield key[len(self.prefix) + 1 :] if self.prefix else key
            if not response.get("IsTruncated"):
                return
            token = response.get("NextContinuationToken")


@dataclass
class TransferBudget:
    """Bandwidth and egress guard rails."""

    max_upload_bytes: int | None = None
    max_download_bytes: int | None = None
    uploaded: int = 0
    downloaded: int = 0

    def allow_upload(self, size: int) -> bool:
        return self.max_upload_bytes is None or self.uploaded + size <= self.max_upload_bytes

    def allow_download(self, size: int) -> bool:
        return self.max_download_bytes is None or self.downloaded + size <= self.max_download_bytes


@dataclass
class PendingUpload:
    kind: str
    key: str
    payload: bytes
    attempts: int = 0


@dataclass
class RemoteStats:
    uploads: int = 0
    downloads: int = 0
    dedup_skips: int = 0
    failures: int = 0
    queued: int = 0
    dropped: int = 0
    repaired: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "uploads": self.uploads,
            "downloads": self.downloads,
            "dedup_skips": self.dedup_skips,
            "failures": self.failures,
            "queued": self.queued,
            "dropped": self.dropped,
            "repaired": self.repaired,
        }


class RemoteCache:
    """Read-through / write-through / write-behind over a :class:`RemoteBackend`."""

    def __init__(
        self,
        backend: RemoteBackend,
        cas: ContentAddressableStore,
        store: MetadataStore,
        tenant_id: str,
        trust_namespace: TrustNamespace = TrustNamespace.BRANCH,
        mode: str = "write-behind",
        clock: Clock = SYSTEM_CLOCK,
        retry_budget: int = 5,
        queue_limit: int = 1024,
        multipart_threshold: int = DEFAULT_MULTIPART_THRESHOLD,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        budget: TransferBudget | None = None,
        replicas: Sequence[RemoteBackend] = (),
    ) -> None:
        if mode not in ("read-through", "write-through", "write-behind"):
            raise ConflictError("unsupported remote mode", mode=mode)
        self.backend = backend
        self.cas = cas
        self.store = store
        self.tenant_id = tenant_id
        self.trust_namespace = trust_namespace
        self.mode = mode
        self.clock = clock
        self.retry_budget = retry_budget
        self.multipart_threshold = multipart_threshold
        self.chunk_size = chunk_size
        self.budget = budget or TransferBudget()
        self.replicas = list(replicas)
        self.stats = RemoteStats()
        self._queue: deque[PendingUpload] = deque()
        self._queue_limit = queue_limit
        self._leases: dict[str, float] = {}
        self._lock = threading.RLock()

    # -- key layout -------------------------------------------------------
    def blob_key(self, digest: str) -> str:
        value = digest_hex(digest)
        return f"blobs/sha256/{value[:2]}/{value[2:4]}/{value}"

    def action_key(self, action_key: str) -> str:
        return f"actions/{self.tenant_id}/{self.trust_namespace}/{digest_hex(action_key)}.json"

    # -- blobs ------------------------------------------------------------
    def upload_blob(self, digest: str, force: bool = False) -> bool:
        """Push a local object. Returns ``True`` when this call stored it."""
        require_digest(digest)
        key = self.blob_key(digest)
        try:
            if not force and self.backend.exists(key):
                self.stats.dedup_skips += 1
                self.store.set_artifact_state(self.tenant_id, digest, ArtifactStorageState.REMOTE)
                return False
            data = self.cas.get_bytes(digest, verify=True)
            if not self.budget.allow_upload(len(data)):
                raise RemoteUnavailable("upload budget exhausted", digest=digest)
            created = self._put_object(key, data)
            self.budget.uploaded += len(data)
            self.stats.uploads += 1
            self.store.set_artifact_state(self.tenant_id, digest, ArtifactStorageState.REMOTE)
            return created
        except RemoteUnavailable:
            self.stats.failures += 1
            raise

    def _put_object(self, key: str, data: bytes) -> bool:
        """Single-shot below the threshold; multipart above it.

        A backend with native multipart (S3) uses it, because the service only
        makes the object visible when the upload is *completed* -- an abandoned
        upload leaves no discoverable key at all. Backends without it get the
        emulation below, where parts land before the assembled object so a torn
        upload still cannot produce a readable-but-short object.
        """
        if len(data) <= self.multipart_threshold:
            return self.backend.put_if_absent(key, data)

        native = getattr(self.backend, "put_multipart", None)
        if callable(native):
            created: bool = native(key, data, self.chunk_size)
            return created

        parts = [data[offset : offset + self.chunk_size] for offset in range(0, len(data), self.chunk_size)]
        part_keys: list[str] = []
        for index, part in enumerate(parts):
            part_key = f"{key}.part{index:05d}"
            self.backend.put_if_absent(part_key, part)
            part_keys.append(part_key)
        manifest = canonical_json_bytes(
            {
                "kind": "elmos.multipart/v1",
                "parts": part_keys,
                "size": len(data),
                "digest": sha256_bytes(data),
            }
        )
        self.backend.put_if_absent(f"{key}.multipart.json", manifest)
        return self.backend.put_if_absent(key, data)

    def download_blob(self, digest: str) -> bool:
        """Read-through fetch with independent end-to-end digest verification."""
        require_digest(digest)
        if self.cas.contains(digest):
            return True
        key = self.blob_key(digest)
        for source in [self.backend, *self.replicas]:
            try:
                data = source.get(key)
            except (NotFound, RemoteUnavailable):
                continue
            actual = sha256_bytes(data)
            if actual != digest:
                # Never admit unverified bytes into the local CAS.
                self.stats.failures += 1
                raise DigestMismatch(
                    "remote object does not match its key", expected=digest, actual=actual
                )
            if not self.budget.allow_download(len(data)):
                raise RemoteUnavailable("download budget exhausted", digest=digest)
            self.cas.put_bytes(data, expected_digest=digest)
            self.budget.downloaded += len(data)
            self.stats.downloads += 1
            self.store.set_artifact_state(self.tenant_id, digest, ArtifactStorageState.LOCAL)
            return True
        return False

    def prefetch(self, digests: Iterable[str]) -> dict[str, bool]:
        return {digest: self.download_blob(digest) for digest in sorted(set(digests))}

    # -- action results ---------------------------------------------------
    def publish_action(
        self,
        action_key: str,
        result_manifest_digest: str,
        blob_digests: Sequence[str],
        validation_level: str,
        producer_identity: str,
        provenance_digest: str,
    ) -> bool:
        """Upload blobs first, then the manifest, then the discoverable entry."""
        require_digest(action_key)
        require_digest(result_manifest_digest)
        pending = [*sorted(set(blob_digests)), result_manifest_digest]
        for digest in pending:
            self.upload_blob(digest)
        for digest in pending:
            if not self.backend.exists(self.blob_key(digest)):
                raise RemoteUnavailable(
                    "refusing to publish: a referenced blob is not durable", digest=digest
                )
        entry = {
            "schema_version": SCHEMA_VERSION,
            "action_key": action_key,
            "result_manifest_digest": result_manifest_digest,
            "blobs": sorted(set(blob_digests)),
            "validation_level": validation_level,
            "producer_identity": producer_identity,
            "provenance_digest": provenance_digest,
            "trust_namespace": str(self.trust_namespace),
            "tenant_id": self.tenant_id,
        }
        payload = canonical_json_bytes(entry)
        created = self.backend.put_if_absent(self.action_key(action_key), payload)
        if not created:
            existing = self.backend.get(self.action_key(action_key))
            if existing != payload:
                # Canonical entries are never overwritten; divergence is a
                # nondeterminism signal for the local Action Cache to handle.
                raise ConflictError(
                    "remote entry already exists with different content",
                    action_key=action_key,
                    remote_digest=sha256_bytes(existing),
                    local_digest=sha256_bytes(payload),
                )
        return created

    def fetch_action(self, action_key: str) -> dict[str, Any] | None:
        try:
            payload = self.backend.get(self.action_key(action_key))
        except (NotFound, RemoteUnavailable):
            return None
        import json

        entry = json.loads(payload.decode("utf-8"))
        if not isinstance(entry, dict):
            return None
        if entry.get("tenant_id") != self.tenant_id:
            return None
        namespace = TrustNamespace(entry.get("trust_namespace", "experimental"))
        if not namespace.satisfies(self.trust_namespace):
            return None
        return entry

    def restore_action(self, action_key: str) -> dict[str, Any] | None:
        """Fetch an entry and materialise all its blobs, or fail cleanly."""
        entry = self.fetch_action(action_key)
        if entry is None:
            return None
        wanted = [*entry.get("blobs", []), entry["result_manifest_digest"]]
        for digest in wanted:
            if not self.download_blob(digest):
                return None
        return entry

    # -- write-behind -----------------------------------------------------
    def enqueue(self, kind: str, key: str, payload: bytes) -> bool:
        """Bounded queue: dropping the oldest beats unbounded memory growth."""
        with self._lock:
            if len(self._queue) >= self._queue_limit:
                self._queue.popleft()
                self.stats.dropped += 1
            self._queue.append(PendingUpload(kind, key, payload))
            self.stats.queued = len(self._queue)
            return True

    def enqueue_blob(self, digest: str) -> bool:
        return self.enqueue("blob", self.blob_key(digest), self.cas.get_bytes(digest))

    def drain(self, limit: int | None = None) -> dict[str, int]:
        """Flush the queue. Exhausted retries are dropped, never retried forever."""
        flushed = 0
        failed = 0
        dropped = 0
        with self._lock:
            budget = len(self._queue) if limit is None else min(limit, len(self._queue))
            for _ in range(budget):
                item = self._queue.popleft()
                try:
                    self.backend.put_if_absent(item.key, item.payload)
                    flushed += 1
                except RemoteUnavailable:
                    item.attempts += 1
                    failed += 1
                    if item.attempts >= self.retry_budget:
                        dropped += 1
                        self.stats.dropped += 1
                    else:
                        self._queue.append(item)
            self.stats.queued = len(self._queue)
        self.stats.uploads += flushed
        self.stats.failures += failed
        return {"flushed": flushed, "failed": failed, "dropped": dropped, "remaining": len(self._queue)}

    @property
    def pending(self) -> int:
        return len(self._queue)

    # -- miss deduplication ----------------------------------------------
    def acquire_miss_lease(self, action_key: str, seconds: float = 60.0) -> bool:
        """One executor per remote miss; others may still speculate locally."""
        now = self.clock.now()
        with self._lock:
            expiry = self._leases.get(action_key)
            if expiry is not None and expiry > now:
                return False
            self._leases[action_key] = now + seconds
            return True

    def release_miss_lease(self, action_key: str) -> None:
        with self._lock:
            self._leases.pop(action_key, None)

    # -- integrity --------------------------------------------------------
    def scrub(self, digests: Iterable[str]) -> dict[str, list[str]]:
        healthy: list[str] = []
        corrupt: list[str] = []
        missing: list[str] = []
        for digest in sorted(set(digests)):
            key = self.blob_key(digest)
            try:
                if not self.backend.exists(key):
                    missing.append(digest)
                    continue
                data = self.backend.get(key)
            except (NotFound, RemoteUnavailable):
                missing.append(digest)
                continue
            (healthy if sha256_bytes(data) == digest else corrupt).append(digest)
        return {"healthy": healthy, "corrupt": corrupt, "missing": missing}

    def repair(self, digest: str) -> bool:
        """Restore a bad remote object from a verified local or replica copy."""
        key = self.blob_key(digest)
        if self.cas.contains(digest) and self.cas.verify(digest):
            self.backend.delete(key)
            self.backend.put_if_absent(key, self.cas.get_bytes(digest))
            self.stats.repaired += 1
            return True
        for replica in self.replicas:
            try:
                data = replica.get(key)
            except (NotFound, RemoteUnavailable):
                continue
            if sha256_bytes(data) == digest:
                self.backend.delete(key)
                self.backend.put_if_absent(key, data)
                self.stats.repaired += 1
                return True
        return False

    # -- offline ----------------------------------------------------------
    def synchronize(self, digests: Iterable[str], action_entries: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
        """Push work produced while offline. Never overwrites a canonical entry."""
        uploaded: list[str] = []
        skipped: list[str] = []
        conflicts: list[str] = []
        for digest in sorted(set(digests)):
            try:
                if self.upload_blob(digest):
                    uploaded.append(digest)
                else:
                    skipped.append(digest)
            except RemoteUnavailable:
                return {
                    "uploaded": uploaded,
                    "skipped": skipped,
                    "conflicts": conflicts,
                    "status": "REMOTE_UNAVAILABLE",
                }
        for entry in action_entries:
            try:
                self.publish_action(
                    entry["action_key"],
                    entry["result_manifest_digest"],
                    entry.get("blobs", []),
                    entry.get("validation_level", "UNVERIFIED"),
                    entry.get("producer_identity", "offline"),
                    entry.get("provenance_digest", entry["result_manifest_digest"]),
                )
            except ConflictError:
                conflicts.append(entry["action_key"])
        return {
            "uploaded": uploaded,
            "skipped": skipped,
            "conflicts": conflicts,
            "status": "OK",
        }

    def health(self) -> dict[str, Any]:
        try:
            self.backend.exists("healthcheck")
            reachable = True
        except RemoteUnavailable:
            reachable = False
        return {
            "reachable": reachable,
            "mode": self.mode,
            "trust_namespace": str(self.trust_namespace),
            "pending_uploads": self.pending,
            "stats": self.stats.to_dict(),
            "budget": {
                "uploaded": self.budget.uploaded,
                "downloaded": self.budget.downloaded,
                "max_upload_bytes": self.budget.max_upload_bytes,
                "max_download_bytes": self.budget.max_download_bytes,
            },
        }


@dataclass
class ReplicaSet:
    """Regional replicas: read from the nearest, write to all."""

    primary: RemoteBackend
    regions: dict[str, RemoteBackend] = field(default_factory=dict)

    def read(self, key: str, preferred: str | None = None) -> bytes:
        order: list[RemoteBackend] = []
        if preferred and preferred in self.regions:
            order.append(self.regions[preferred])
        order.append(self.primary)
        order.extend(backend for name, backend in sorted(self.regions.items()) if name != preferred)
        errors: list[str] = []
        for backend in order:
            try:
                return backend.get(key)
            except (NotFound, RemoteUnavailable) as exc:
                errors.append(str(exc))
        raise NotFound("object is absent from every replica", key=key, errors=errors[:5])

    def write(self, key: str, data: bytes) -> dict[str, bool]:
        results = {"primary": self.primary.put_if_absent(key, data)}
        for name, backend in sorted(self.regions.items()):
            try:
                results[name] = backend.put_if_absent(key, data)
            except RemoteUnavailable:
                results[name] = False
        return results


def mirror_local_to_remote(
    remote: RemoteCache, digests: Iterable[str], write_behind: bool = True
) -> dict[str, Any]:
    """Best-effort push; a remote failure queues instead of failing the run."""
    pushed: list[str] = []
    queued: list[str] = []
    for digest in sorted(set(digests)):
        try:
            remote.upload_blob(digest)
            pushed.append(digest)
        except RemoteUnavailable:
            if not write_behind:
                raise
            remote.enqueue_blob(digest)
            queued.append(digest)
    return {"pushed": pushed, "queued": queued}


def local_backup(root: Path, cas: ContentAddressableStore, digests: Iterable[str]) -> int:
    """Copy objects to a second local root; used by the offline profile."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    copied = 0
    for digest in sorted(set(digests)):
        source = cas.path_for(digest)
        if not source.exists():
            continue
        target = root / f"{digest_hex(digest)}.blob"
        if target.exists():
            continue
        shutil.copyfile(source, target)
        copied += 1
    return copied


def entry_digest(entry: dict[str, Any]) -> str:
    return digest_of(entry)
