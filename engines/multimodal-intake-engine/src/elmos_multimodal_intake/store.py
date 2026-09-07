"""SQLite metadata store and tenant-namespaced local content-addressed storage."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import shutil
import sqlite3
import tempfile
import threading
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .canonical import (
    CANONICAL_JSON_SHA256_CONTRACT,
    MAX_SAFE_JSON_INTEGER,
    canonical_digest,
    canonical_json,
    new_id,
    normalize_sha256,
    require_actor_id,
    require_idempotency_key,
    require_resource_id,
    sha256_bytes,
    utc_now,
)
from .errors import AuthorizationError, ConflictError, IntegrityError, NotFoundError, ValidationError
from .content import content_contract_digest, content_contract_json
from .models import (
    AssetKind,
    AssetStatus,
    ContentBlock,
    ContentBlockKind,
    InputAsset,
    InputSession,
    JobStatus,
    ParseReport,
    ProcessingJob,
    ResultStatus,
    ReviewTargetKind,
    SecurityDecision,
    SessionStatus,
    SourceAnchor,
    TenantContext,
    UploadSession,
    UploadStatus,
    UNTRUSTED_CONTENT,
)
from ._migrations import migrate_connection, migration_sql


class _VersionedProcessingJob(ProcessingJob):
    """Backwards-compatible job value carrying its durable row version.

    ``ProcessingJob`` predates resumable progress delivery and is a frozen,
    slotted public value.  A private subclass lets existing callers keep the
    exact public type contract while progress readers bind cursors to the
    database-owned monotone version instead of a wall clock.
    """

    __slots__ = ("version",)


class LocalCasStore:
    """Immutable local CAS with physical tenant isolation and verify-on-read."""

    _MAX_GENERATION_INDEX_BYTES = 16 * 1024 * 1024
    _MAX_GENERATION_OBJECTS = 50_000
    _GENERATION_MANIFEST_FIELDS = frozenset(
        {
            "schema_version",
            "kind",
            "scope_digest",
            "manifest_digest",
            "publication_receipt_digest",
            "objects",
        }
    )

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    @staticmethod
    def _tenant_namespace(tenant_id: str) -> str:
        require_resource_id(tenant_id, "tenant_id")
        return hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()

    def path_for(self, tenant_id: str, digest: str) -> Path:
        normalized = normalize_sha256(digest)
        namespace = self._tenant_namespace(tenant_id)
        return self.root / "tenants" / namespace / "sha256" / normalized[:2] / normalized

    def generation_path_for(self, tenant_id: str, generation_digest: str) -> Path:
        """Resolve an atomically published, tenant-private object generation."""

        normalized = normalize_sha256(generation_digest)
        namespace = self._tenant_namespace(tenant_id)
        return (
            self.root
            / "tenants"
            / namespace
            / "generations"
            / "sha256"
            / normalized[:2]
            / normalized
        )

    def generation_object_path_for(
        self,
        tenant_id: str,
        generation_digest: str,
        object_digest: str,
    ) -> Path:
        normalized = normalize_sha256(object_digest)
        return self.generation_path_for(tenant_id, generation_digest) / "objects" / normalized[:2] / normalized

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _verify_generation(
        self,
        target: Path,
        generation_digest: str,
        descriptors: Sequence[Mapping[str, Any]],
    ) -> None:
        if target.is_symlink() or not target.is_dir():
            raise IntegrityError("CAS_GENERATION_PATH_INVALID")
        observed = self._load_generation_descriptors(target, generation_digest)
        if tuple(descriptors) != observed:
            raise IntegrityError("CAS_GENERATION_INDEX_MISMATCH")
        for descriptor in descriptors:
            digest = str(descriptor["digest"])
            size = int(descriptor["byte_count"])
            path = target / "objects" / digest[:2] / digest
            if path.is_symlink() or not path.is_file():
                raise IntegrityError("CAS_GENERATION_OBJECT_MISSING")
            self._verify(path, digest, size)

    def _validate_generation_manifest(
        self,
        target: Path,
        generation_digest: str,
        descriptors: Sequence[Mapping[str, Any]],
    ) -> None:
        """Bind the generation identity to one canonical, exact object set."""

        manifest_descriptor = next(
            (item for item in descriptors if item.get("digest") == generation_digest),
            None,
        )
        if manifest_descriptor is None:
            raise IntegrityError("CAS_GENERATION_MANIFEST_MISSING")
        manifest_path = target / "objects" / generation_digest[:2] / generation_digest
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise IntegrityError("CAS_GENERATION_MANIFEST_MISSING")
        manifest_size = manifest_descriptor.get("byte_count")
        if (
            isinstance(manifest_size, bool)
            or not isinstance(manifest_size, int)
            or manifest_size < 0
            or manifest_size > self._MAX_GENERATION_INDEX_BYTES
        ):
            raise IntegrityError("CAS_GENERATION_MANIFEST_INVALID")
        try:
            if manifest_path.stat().st_size != manifest_size:
                raise IntegrityError("CAS_GENERATION_MANIFEST_INVALID")
            manifest_bytes = manifest_path.read_bytes()
            if len(manifest_bytes) != manifest_size or sha256_bytes(manifest_bytes) != generation_digest:
                raise IntegrityError("CAS_GENERATION_MANIFEST_INVALID")
            manifest = json.loads(manifest_bytes)
            canonical_manifest_bytes = canonical_json(manifest).encode("utf-8")
        except IntegrityError:
            raise
        except (
            FileNotFoundError,
            OSError,
            UnicodeDecodeError,
            UnicodeEncodeError,
            json.JSONDecodeError,
            RecursionError,
            ValidationError,
        ) as exc:
            raise IntegrityError("CAS_GENERATION_MANIFEST_INVALID") from exc
        if (
            not isinstance(manifest, dict)
            or set(manifest) != self._GENERATION_MANIFEST_FIELDS
            or manifest.get("schema_version") != "1.0.0"
            or manifest.get("kind") != "ATOMIC_CAS_GENERATION_MANIFEST"
            or manifest_bytes != canonical_manifest_bytes
            or not isinstance(manifest.get("objects"), list)
        ):
            raise IntegrityError("CAS_GENERATION_MANIFEST_INVALID")
        raw_scope_digest = manifest.get("scope_digest")
        raw_manifest_digest = manifest.get("manifest_digest")
        raw_receipt_digest = manifest.get("publication_receipt_digest")
        if (
            not isinstance(raw_scope_digest, str)
            or not isinstance(raw_manifest_digest, str)
            or not isinstance(raw_receipt_digest, str)
        ):
            raise IntegrityError("CAS_GENERATION_MANIFEST_INVALID")
        try:
            scope_digest = normalize_sha256(raw_scope_digest)
            publication_manifest_digest = normalize_sha256(raw_manifest_digest)
            publication_receipt_digest = normalize_sha256(raw_receipt_digest)
        except ValidationError as exc:
            raise IntegrityError("CAS_GENERATION_MANIFEST_INVALID") from exc
        if (
            manifest.get("scope_digest") != f"sha256:{scope_digest}"
            or manifest.get("manifest_digest") != f"sha256:{publication_manifest_digest}"
            or manifest.get("publication_receipt_digest")
            != f"sha256:{publication_receipt_digest}"
        ):
            raise IntegrityError("CAS_GENERATION_MANIFEST_INVALID")

        bound_objects: list[dict[str, Any]] = []
        prior_digest = ""
        for raw in manifest["objects"]:
            if not isinstance(raw, dict) or set(raw) != {"digest", "byte_count"}:
                raise IntegrityError("CAS_GENERATION_MANIFEST_INVALID")
            raw_digest = raw.get("digest")
            if not isinstance(raw_digest, str):
                raise IntegrityError("CAS_GENERATION_MANIFEST_INVALID")
            try:
                digest = normalize_sha256(raw_digest)
            except ValidationError as exc:
                raise IntegrityError("CAS_GENERATION_MANIFEST_INVALID") from exc
            byte_count = raw.get("byte_count")
            if (
                raw.get("digest") != f"sha256:{digest}"
                or digest <= prior_digest
                or digest == generation_digest
                or isinstance(byte_count, bool)
                or not isinstance(byte_count, int)
                or byte_count < 0
            ):
                raise IntegrityError("CAS_GENERATION_MANIFEST_INVALID")
            prior_digest = digest
            bound_objects.append({"digest": f"sha256:{digest}", "byte_count": byte_count})

        expected_objects = [
            {"digest": f"sha256:{item['digest']}", "byte_count": item["byte_count"]}
            for item in descriptors
            if item["digest"] != generation_digest
        ]
        expected_objects.sort(key=lambda item: item["digest"])
        bound_digests = {normalize_sha256(item["digest"]) for item in bound_objects}
        if (
            bound_objects != expected_objects
            or publication_manifest_digest not in bound_digests
            or publication_receipt_digest not in bound_digests
        ):
            raise IntegrityError("CAS_GENERATION_MANIFEST_OBJECT_SET_MISMATCH")

    def _load_generation_descriptors(
        self,
        target: Path,
        generation_digest: str,
    ) -> tuple[Mapping[str, Any], ...]:
        index_path = target / ".generation.json"
        if index_path.is_symlink():
            raise IntegrityError("CAS_GENERATION_INDEX_INVALID")
        try:
            if index_path.stat().st_size > self._MAX_GENERATION_INDEX_BYTES:
                raise IntegrityError("CAS_GENERATION_INDEX_SIZE_LIMIT")
            index_bytes = index_path.read_bytes()
            index = json.loads(index_bytes)
        except IntegrityError:
            raise
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IntegrityError("CAS_GENERATION_INDEX_INVALID") from exc
        try:
            canonical_index_bytes = canonical_json(index).encode("utf-8")
        except (ValidationError, UnicodeEncodeError) as exc:
            raise IntegrityError("CAS_GENERATION_INDEX_MISMATCH") from exc
        if (
            not isinstance(index, dict)
            or set(index) != {"schema_version", "generation_digest", "objects"}
            or index.get("schema_version") != "1.0.0"
            or index.get("generation_digest") != generation_digest
            or not isinstance(index.get("objects"), list)
            or len(index["objects"]) > self._MAX_GENERATION_OBJECTS
            or index_bytes != canonical_index_bytes
        ):
            raise IntegrityError("CAS_GENERATION_INDEX_MISMATCH")
        descriptors: list[Mapping[str, Any]] = []
        prior_digest = ""
        for raw in index["objects"]:
            if not isinstance(raw, dict) or set(raw) != {"digest", "byte_count"}:
                raise IntegrityError("CAS_GENERATION_INDEX_MISMATCH")
            raw_digest = raw.get("digest")
            if not isinstance(raw_digest, str):
                raise IntegrityError("CAS_GENERATION_INDEX_MISMATCH")
            try:
                digest = normalize_sha256(raw_digest)
            except ValidationError as exc:
                raise IntegrityError("CAS_GENERATION_INDEX_MISMATCH") from exc
            byte_count = raw.get("byte_count")
            if (
                digest != raw.get("digest")
                or digest <= prior_digest
                or isinstance(byte_count, bool)
                or not isinstance(byte_count, int)
                or byte_count < 0
            ):
                raise IntegrityError("CAS_GENERATION_INDEX_MISMATCH")
            prior_digest = digest
            descriptors.append({"digest": digest, "byte_count": byte_count})
        if not descriptors:
            raise IntegrityError("CAS_GENERATION_INDEX_MISMATCH")
        result = tuple(descriptors)
        self._validate_generation_manifest(target, generation_digest, result)
        return result

    def publish_generation(
        self,
        tenant_id: str,
        generation_digest: str,
        objects: Sequence[tuple[str, int, Iterable[bytes]]],
    ) -> str:
        """Publish a complete object set with one atomic directory rename.

        Objects are written below an unreadable incoming namespace.  The public
        generation path appears only after every byte count and SHA-256 binding
        has been verified and fsynced.
        """

        normalized_generation = normalize_sha256(generation_digest)
        if not objects:
            raise ValidationError("CAS_GENERATION_EMPTY")
        if len(objects) > self._MAX_GENERATION_OBJECTS:
            raise ValidationError("CAS_GENERATION_OBJECT_LIMIT")
        target = self.generation_path_for(tenant_id, normalized_generation)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = Path(tempfile.mkdtemp(prefix=".incoming-generation-", dir=target.parent))
        descriptors: list[dict[str, Any]] = []
        seen: set[str] = set()
        published = False
        try:
            for raw_digest, expected_size, chunks in objects:
                digest = normalize_sha256(raw_digest)
                if digest in seen:
                    raise ValidationError("CAS_GENERATION_DUPLICATE_OBJECT")
                seen.add(digest)
                if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
                    raise ValidationError("CAS_SIZE_INVALID")
                object_path = temporary / "objects" / digest[:2] / digest
                object_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                measured = hashlib.sha256()
                total = 0
                descriptor = os.open(object_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                try:
                    with os.fdopen(descriptor, "wb") as output:
                        for chunk in chunks:
                            if not isinstance(chunk, bytes):
                                raise ValidationError("CAS_CHUNK_TYPE_INVALID")
                            if len(chunk) > expected_size - total:
                                raise IntegrityError("CAS_SIZE_MISMATCH")
                            output.write(chunk)
                            measured.update(chunk)
                            total += len(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                except Exception:
                    object_path.unlink(missing_ok=True)
                    raise
                if total != expected_size:
                    raise IntegrityError("CAS_SIZE_MISMATCH")
                if measured.hexdigest() != digest:
                    raise IntegrityError("CAS_DIGEST_MISMATCH")
                descriptors.append({"digest": digest, "byte_count": expected_size})
            descriptors.sort(key=lambda item: item["digest"])
            self._validate_generation_manifest(temporary, normalized_generation, descriptors)
            index = {
                "schema_version": "1.0.0",
                "generation_digest": normalized_generation,
                "objects": descriptors,
            }
            index_bytes = canonical_json(index).encode("utf-8")
            if len(index_bytes) > self._MAX_GENERATION_INDEX_BYTES:
                raise ValidationError("CAS_GENERATION_INDEX_SIZE_LIMIT")
            index_path = temporary / ".generation.json"
            with index_path.open("xb") as output:
                output.write(index_bytes)
                output.flush()
                os.fsync(output.fileno())
            for directory in sorted(
                (path for path in temporary.rglob("*") if path.is_dir()),
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                self._fsync_directory(directory)
            self._fsync_directory(temporary)
            try:
                os.rename(temporary, target)
                published = True
                self._fsync_directory(target.parent)
            except OSError:
                if target.is_symlink() or not target.is_dir():
                    raise
                self._verify_generation(target, normalized_generation, descriptors)
                try:
                    shutil.rmtree(temporary)
                except OSError as cleanup_exc:
                    raise IntegrityError(
                        "CAS_GENERATION_ROLLBACK_INCOMPLETE",
                        retryable=True,
                    ) from cleanup_exc
                published = True
            return normalized_generation
        except Exception as exc:
            if not published and temporary.exists():
                try:
                    shutil.rmtree(temporary)
                except OSError as cleanup_exc:
                    raise IntegrityError(
                        "CAS_GENERATION_ROLLBACK_INCOMPLETE",
                        retryable=True,
                    ) from cleanup_exc
            raise exc
        finally:
            if not published and temporary.exists():
                try:
                    shutil.rmtree(temporary)
                except OSError:
                    pass

    def read_generation_bytes(
        self,
        tenant_id: str,
        generation_digest: str,
        object_digest: str,
        *,
        maximum_bytes: int | None = None,
        expected_size: int | None = None,
    ) -> bytes:
        normalized_generation = normalize_sha256(generation_digest)
        normalized_object = normalize_sha256(object_digest)
        generation = self.generation_path_for(tenant_id, normalized_generation)
        if generation.is_symlink() or not generation.is_dir():
            raise NotFoundError("CAS_GENERATION_NOT_FOUND")
        descriptors = self._load_generation_descriptors(generation, normalized_generation)
        descriptor = next(
            (item for item in descriptors if item["digest"] == normalized_object),
            None,
        )
        if descriptor is None:
            raise NotFoundError("CAS_GENERATION_OBJECT_NOT_FOUND")
        path = self.generation_object_path_for(tenant_id, normalized_generation, normalized_object)
        if path.is_symlink():
            raise IntegrityError("CAS_GENERATION_OBJECT_INVALID")
        try:
            size = path.stat().st_size
        except FileNotFoundError as exc:
            raise NotFoundError("CAS_GENERATION_OBJECT_NOT_FOUND") from exc
        if maximum_bytes is not None and size > maximum_bytes:
            raise IntegrityError("CAS_GENERATION_OBJECT_SIZE_OUTSIDE_BOUND")
        bound_size = int(descriptor["byte_count"])
        if size != bound_size or expected_size is not None and size != expected_size:
            raise IntegrityError("CAS_GENERATION_OBJECT_SIZE_BINDING_MISMATCH")
        data = path.read_bytes()
        if len(data) != size or sha256_bytes(data) != normalized_object:
            raise IntegrityError("CAS_GENERATION_OBJECT_CORRUPT")
        return data

    def put_bytes(self, tenant_id: str, data: bytes, expected_sha256: str | None = None) -> str:
        actual = sha256_bytes(data)
        if expected_sha256 is not None and actual != normalize_sha256(expected_sha256):
            raise IntegrityError("CAS_DIGEST_MISMATCH", "Bytes do not match the declared digest")
        return self.put_stream(tenant_id, actual, len(data), (data,))

    def put_stream(
        self,
        tenant_id: str,
        expected_sha256: str,
        expected_size: int,
        chunks: Iterable[bytes],
    ) -> str:
        expected = normalize_sha256(expected_sha256)
        if expected_size < 0:
            raise ValidationError("CAS_SIZE_INVALID")
        target = self.path_for(tenant_id, expected)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        file_descriptor, temporary_name = tempfile.mkstemp(prefix=".incoming-", dir=target.parent)
        temporary = Path(temporary_name)
        digest = hashlib.sha256()
        total = 0
        try:
            with os.fdopen(file_descriptor, "wb") as output:
                for chunk in chunks:
                    if not isinstance(chunk, bytes):
                        raise ValidationError("CAS_CHUNK_TYPE_INVALID")
                    digest.update(chunk)
                    total += len(chunk)
                    if total > expected_size:
                        raise IntegrityError("CAS_SIZE_MISMATCH", "CAS stream exceeds its declared size")
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if total != expected_size:
                raise IntegrityError("CAS_SIZE_MISMATCH", "CAS stream is shorter than its declared size")
            if digest.hexdigest() != expected:
                raise IntegrityError("CAS_DIGEST_MISMATCH", "CAS stream does not match its declared digest")
            try:
                os.link(temporary, target)
            except FileExistsError:
                self._verify(target, expected, expected_size)
            finally:
                temporary.unlink(missing_ok=True)
            os.chmod(target, 0o600)
            return expected
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def read_bytes(
        self,
        tenant_id: str,
        digest: str,
        *,
        maximum_bytes: int | None = None,
        expected_size: int | None = None,
    ) -> bytes:
        normalized = normalize_sha256(digest)
        path = self.path_for(tenant_id, normalized)
        try:
            size = path.stat().st_size
        except FileNotFoundError as error:
            raise NotFoundError("CAS_OBJECT_NOT_FOUND") from error
        if maximum_bytes is not None and size > maximum_bytes:
            self._quarantine(path, normalized)
            raise IntegrityError("CAS_OBJECT_SIZE_OUTSIDE_BOUND")
        if expected_size is not None and size != expected_size:
            self._quarantine(path, normalized)
            raise IntegrityError("CAS_OBJECT_SIZE_BINDING_MISMATCH")
        data = path.read_bytes()
        if len(data) != size or sha256_bytes(data) != normalized:
            self._quarantine(path, normalized)
            raise IntegrityError("CAS_OBJECT_CORRUPT")
        return data

    def quarantine_object(self, tenant_id: str, digest: str, reason: str) -> bool:
        """Recoverably move a tenant object out of the readable CAS namespace."""
        normalized = normalize_sha256(digest)
        source = self.path_for(tenant_id, normalized)
        namespace = self._tenant_namespace(tenant_id)
        destination = (
            self.root
            / "quarantine"
            / "tenants"
            / namespace
            / "sha256"
            / normalized[:2]
            / f"{normalized}-{canonical_digest(reason)[:12]}"
        )
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.replace(source, destination)
        except FileNotFoundError:
            return destination.is_file()
        os.chmod(destination, 0o600)
        return True

    def iter_bytes(self, tenant_id: str, digest: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        normalized = normalize_sha256(digest)
        path = self.path_for(tenant_id, normalized)
        if not path.is_file():
            raise NotFoundError("CAS_OBJECT_NOT_FOUND")
        measured = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(chunk_size):
                measured.update(chunk)
                yield chunk
        if measured.hexdigest() != normalized:
            self._quarantine(path, normalized)
            raise IntegrityError("CAS_OBJECT_CORRUPT")

    def _verify(self, path: Path, digest: str, expected_size: int) -> None:
        if path.stat().st_size != expected_size:
            self._quarantine(path, digest)
            raise IntegrityError("CAS_EXISTING_SIZE_MISMATCH")
        measured = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                measured.update(chunk)
        if measured.hexdigest() != digest:
            self._quarantine(path, digest)
            raise IntegrityError("CAS_EXISTING_DIGEST_MISMATCH")

    def _quarantine(self, path: Path, digest: str) -> None:
        quarantine = self.root / "quarantine"
        quarantine.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = quarantine / f"{digest}-{new_id('corrupt')}"
        try:
            os.replace(path, destination)
        except FileNotFoundError:
            pass


class IntakeStore:
    """Single-node durable metadata store; every resource lookup is tenant/project scoped."""

    _CONTENT_TRUST_PAYLOAD_KEY = "_elmos_trust_label"
    WRITE = "intake:write"
    READ = "intake:read"
    REVIEW = "intake:review"
    ADMIN = "intake:admin"
    _ALL_PERMISSIONS = (WRITE, READ, REVIEW, ADMIN)
    _MAX_EXECUTION_RECEIPT_BYTES = 16 * 1024 * 1024
    _MAX_CORE_OUTBOX_PAYLOAD_BYTES = 4 * 1024 * 1024
    _MAX_CORE_OUTBOX_FUTURE_SKEW = timedelta(minutes=5)
    _DURABLE_TRANSITIONS: Mapping[str, frozenset[str]] = {
        "PENDING": frozenset({"RUNNING", "CANCELLED"}),
        "RUNNING": frozenset({"PAUSED", "SUCCEEDED", "FAILED_RETRYABLE", "FAILED_FINAL", "CANCELLED"}),
        "PAUSED": frozenset({"RUNNING", "CANCELLED"}),
        "FAILED_RETRYABLE": frozenset({"RUNNING", "FAILED_FINAL", "CANCELLED"}),
        "SUCCEEDED": frozenset(),
        "FAILED_FINAL": frozenset(),
        "CANCELLED": frozenset(),
    }
    _DURABLE_EVENT_FIELDS = frozenset(
        {
            "tenant_id",
            "project_id",
            "skill",
            "actor_id",
            "task_id",
            "sequence_number",
            "from_state",
            "target_state",
            "idempotency_key",
            "request_digest",
            "payload_digest",
            "checkpoint_digest",
            "effects_to_skip",
            "effects_to_reconcile",
            "recorded_at",
            "event_id",
        }
    )
    _TERMINAL_JOB_STATUSES = frozenset(
        {
            JobStatus.COMPLETED,
            JobStatus.PARTIAL,
            JobStatus.NEEDS_REVIEW,
            JobStatus.BLOCKED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    )
    _RETRY_SAFE_INTERNAL_RECEIPT_SKILLS = frozenset(
        {"core.elmos-multimodal-input-orchestrator.cancel_job"}
    )
    _TERMINAL_JOB_SESSION_STATUSES: Mapping[JobStatus, frozenset[SessionStatus]] = {
        JobStatus.COMPLETED: frozenset({SessionStatus.READY}),
        JobStatus.PARTIAL: frozenset({SessionStatus.PARTIAL_READY}),
        JobStatus.NEEDS_REVIEW: frozenset({SessionStatus.NEEDS_REVIEW}),
        JobStatus.BLOCKED: frozenset(
            {SessionStatus.NEEDS_REVIEW, SessionStatus.QUARANTINED}
        ),
        JobStatus.FAILED: frozenset({SessionStatus.FAILED}),
        JobStatus.CANCELLED: frozenset({SessionStatus.CANCELLED}),
    }
    _JOB_TRANSITIONS: Mapping[JobStatus, frozenset[JobStatus]] = {
        JobStatus.QUEUED: frozenset(
            {
                JobStatus.RUNNING,
                JobStatus.BLOCKED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            }
        ),
        JobStatus.RUNNING: frozenset(
            {
                JobStatus.RUNNING,
                JobStatus.COMPLETED,
                JobStatus.PARTIAL,
                JobStatus.NEEDS_REVIEW,
                JobStatus.BLOCKED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            }
        ),
        JobStatus.COMPLETED: frozenset(),
        JobStatus.PARTIAL: frozenset(),
        JobStatus.NEEDS_REVIEW: frozenset(),
        JobStatus.BLOCKED: frozenset(),
        JobStatus.FAILED: frozenset(),
        JobStatus.CANCELLED: frozenset(),
    }
    _JOB_RESULT_STATUS: Mapping[JobStatus, ResultStatus] = {
        JobStatus.QUEUED: ResultStatus.NOT_RUN,
        JobStatus.RUNNING: ResultStatus.NOT_RUN,
        JobStatus.COMPLETED: ResultStatus.PASSED,
        JobStatus.PARTIAL: ResultStatus.PARTIAL,
        JobStatus.NEEDS_REVIEW: ResultStatus.NEEDS_REVIEW,
        JobStatus.BLOCKED: ResultStatus.BLOCKED,
        JobStatus.FAILED: ResultStatus.FAILED,
        JobStatus.CANCELLED: ResultStatus.BLOCKED,
    }
    _HUMAN_REVIEW_ASSET_STATES = frozenset(
        {AssetStatus.READY.value, AssetStatus.NEEDS_REVIEW.value}
    )
    _HUMAN_REVIEW_REBUILD_TASKS = (
        "content-index",
        "requirements",
        "project-memory",
    )
    _HUMAN_REVIEW_PARSER_PRODUCER = "workload:multimodal-parser"
    _HUMAN_REVIEW_PARSER_SOURCE_KINDS = ("CONTENT_BLOCK", "SOURCE_ANCHOR")
    _HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER = (
        "workload:human-review-correction-store"
    )
    _HUMAN_REVIEW_CORRECTION_SOURCE_KIND = "TRUSTED_DERIVATION"
    _HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER_VERSION = (
        "elmos-human-review-correction-authoritative-source-v1"
    )
    _HUMAN_REVIEW_CORRECTION_SOURCE_CONFIDENCE = 1.0
    _MAX_HUMAN_REVIEW_SOURCE_JSON_BYTES = 2 * 1024 * 1024
    _MAX_HUMAN_REVIEW_SOURCE_TARGETS = 50_000
    _HUMAN_REVIEW_CORRECTION_FIELDS = frozenset(
        {
            "content_id",
            "version",
            "value",
            "tenant_id",
            "project_id",
            "supersedes_digest",
            "actor",
            "reason",
            "policy_version",
            "review_state_version",
            "idempotency_key",
            "idempotency_binding_digest",
            "digest",
        }
    )

    def __init__(
        self,
        database: str | Path,
        *,
        human_review_source_capability: object | None = None,
        deletion_worker_capability: object | None = None,
        deletion_verifier_capability: object | None = None,
        outbox_publisher_capability: object | None = None,
        outbox_response_verifier_capability: object | None = None,
    ) -> None:
        path = Path(database).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = path
        self._lock = threading.RLock()
        self._human_review_source_capability = human_review_source_capability
        if (
            deletion_worker_capability is not None
            and deletion_worker_capability is deletion_verifier_capability
        ):
            raise ValidationError("GOVERNANCE_DELETION_CAPABILITY_SEPARATION_REQUIRED")
        self._deletion_worker_capability = deletion_worker_capability
        self._deletion_verifier_capability = deletion_verifier_capability
        if (
            outbox_publisher_capability is not None
            and outbox_publisher_capability is outbox_response_verifier_capability
        ):
            raise ValidationError("OUTBOX_PUBLISHER_VERIFIER_SEPARATION_REQUIRED")
        self._outbox_publisher_capability = outbox_publisher_capability
        self._outbox_response_verifier_capability = outbox_response_verifier_capability
        self._deletion_worker_capability_id = new_id("delete-worker-cap")
        self._deletion_verifier_capability_id = new_id("delete-verifier-cap")
        self._outbox_publisher_capability_id = new_id("outbox-publisher-cap")
        self._outbox_response_verifier_capability_id = new_id("outbox-verifier-cap")
        self._connection = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        try:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA busy_timeout = 30000")
            installed_version = migrate_connection(self._connection, target_version=24)
            if installed_version != 24:
                raise IntegrityError("INTAKE_SCHEMA_VERSION_UNSUPPORTED")
            self._validate_processing_job_version_schema()
            self._validate_processing_job_cancellation_schema()
            self._validate_core_outbox_delivery_schema()
            self._validate_skill_execution_dispatch_schema()
            self._validate_skill_execution_response_digest_schema()
            self._validate_core_outbox_payload_schema()
            self._validate_human_review_correction_schema()
            self._validate_human_review_workflow_schema()
            self._validate_archive_expansion_schema()
            self._validate_governance_deletion_schema()
            self._validate_context_lifecycle_schema()
            self._validate_project_package_lifecycle_schema()
            self._validate_telemetry_cost_ledger_schema()
            self._validate_downstream_agent_schema()
        except BaseException:
            try:
                self._connection.close()
            except Exception:
                pass
            raise

    @staticmethod
    def _normalized_schema_sql(sql: Any) -> str:
        if not isinstance(sql, str) or not sql.strip():
            raise IntegrityError("INTAKE_SCHEMA_OBJECT_SQL_INVALID")
        return "".join(sql.lower().split()).removesuffix(";")

    def _validate_telemetry_cost_ledger_schema(self) -> None:
        expected = {
            "multimodal_telemetry_subjects": (
                "tenant_id", "project_id", "subject_kind", "subject_id", "version",
                "latest_estimate_sequence", "latest_trace_sequence", "actuals_state",
                "updated_at",
            ),
            "multimodal_cost_estimates": (
                "tenant_id", "project_id", "subject_kind", "subject_id",
                "estimate_sequence", "idempotency_key", "request_digest",
                "estimate_json", "estimate_digest", "result_state", "result_code",
                "calibration_version", "estimated_cost", "currency", "actuals_state",
                "provider_actuals_digest", "provider_actuals_byte_count", "trace_id",
                "actor_id", "created_at",
            ),
            "multimodal_cost_line_items": (
                "tenant_id", "project_id", "subject_kind", "subject_id",
                "estimate_sequence", "stage_id", "stage", "asset_id", "provider",
                "file_type", "quantity", "unit", "unit_price", "estimated_cost",
                "actual_quantity", "actual_cost", "currency", "actual_evidence_digest",
                "actual_evidence_byte_count", "created_at",
            ),
            "multimodal_telemetry_traces": (
                "tenant_id", "project_id", "subject_kind", "subject_id",
                "trace_sequence", "idempotency_key", "request_digest", "trace_id",
                "trace_json", "trace_digest", "result_state", "result_code",
                "policy_version", "missing_stage_count", "event_count", "actor_id",
                "created_at",
            ),
            "multimodal_telemetry_events": (
                "tenant_id", "project_id", "subject_kind", "subject_id",
                "trace_sequence", "event_id", "trace_id", "parent_event_id",
                "event_type", "stage", "provider", "file_type", "status",
                "error_code", "event_json", "event_digest", "created_at",
            ),
        }
        for table, columns in expected.items():
            observed = tuple(
                str(row["name"])
                for row in self._connection.execute(f"PRAGMA table_info({table})").fetchall()
            )
            if observed != columns:
                raise IntegrityError("TELEMETRY_LEDGER_SCHEMA_INVALID", details={"table": table})

    def _validate_downstream_agent_schema(self) -> None:
        expected = {
            "downstream_agent_contexts": (
                "tenant_id", "project_id", "context_id", "task_id", "subject_id",
                "package_version", "actor_id", "idempotency_key", "request_digest",
                "policy_version", "source_set_digest", "context_json", "context_digest",
                "state", "created_at", "revoked_at",
            ),
            "downstream_context_sources": (
                "tenant_id", "project_id", "context_id", "ordinal",
                "source_receipt_id", "source_kind", "source_id", "source_digest",
                "receipt_digest", "normalized_json", "normalized_digest",
                "raw_asset_included", "created_at",
            ),
            "downstream_tool_grants": (
                "tenant_id", "project_id", "context_id", "grant_id",
                "tool_receipt_id", "tool_id", "capability_version", "subject_id",
                "input_digest", "scope_digest", "receipt_digest", "policy_version",
                "state", "expires_at", "single_use", "claim_fence",
                "claim_token_digest", "claimed_by", "execution_receipt_id", "issued_at",
                "claimed_at", "terminal_at", "revocation_reason",
            ),
            "downstream_tool_executions": (
                "tenant_id", "project_id", "execution_id", "context_id", "grant_id",
                "idempotency_key", "request_digest", "executor_id", "claim_fence",
                "state", "result_receipt_id", "result_receipt_json",
                "result_receipt_digest", "response_json", "response_digest",
                "started_at", "completed_at",
            ),
            "downstream_agent_result_links": (
                "tenant_id", "project_id", "link_id", "context_id", "grant_id",
                "execution_id", "result_receipt_id", "result_digest",
                "result_byte_count", "result_locator", "executor_id", "verifier_id",
                "verification_method", "receipt_digest", "link_json", "link_digest",
                "created_by", "created_at",
            ),
            "downstream_agent_operation_receipts": (
                "tenant_id", "project_id", "actor_id", "operation", "idempotency_key",
                "request_digest", "response_json", "response_digest", "created_at",
            ),
            "downstream_agent_outbox": (
                "tenant_id", "project_id", "event_id", "aggregate_type",
                "aggregate_id", "event_type", "idempotency_key", "payload_json",
                "payload_digest", "delivery_state", "attempt_count", "claim_token_digest",
                "claim_expires_at", "created_at", "published_at",
            ),
        }
        for table, columns in expected.items():
            observed = tuple(
                str(row["name"])
                for row in self._connection.execute(f"PRAGMA table_info({table})").fetchall()
            )
            if observed != columns:
                raise IntegrityError("DOWNSTREAM_SCHEMA_INVALID", details={"table": table})

    def _validate_project_package_lifecycle_schema(self) -> None:
        expected = {
            "project_package_sessions": (
                "tenant_id", "project_id", "session_id", "state",
                "expected_entry_count", "accepted_entry_count", "next_chunk_index",
                "generation", "manifest_version", "manifest_digest", "merkle_root",
                "created_by", "created_at", "updated_at",
            ),
            "project_package_versions": (
                "tenant_id", "project_id", "package_version", "parent_version",
                "state", "entry_count", "manifest_digest", "merkle_root",
                "created_by", "created_at",
            ),
            "project_package_entries": (
                "tenant_id", "project_id", "package_version", "path", "entry_digest",
                "content_digest", "byte_count", "kind", "role",
                "model_read_allowed", "security_state", "metadata_json",
                "override_version",
            ),
            "project_package_artifacts": (
                "tenant_id", "project_id", "package_version", "artifact_kind",
                "artifact_version", "state", "result_state", "input_digest",
                "artifact_digest", "artifact_json", "created_by", "created_at",
            ),
        }
        for table, columns in expected.items():
            observed = tuple(
                str(row["name"])
                for row in self._connection.execute(f"PRAGMA table_info({table})").fetchall()
            )
            if observed != columns:
                raise IntegrityError("PROJECT_PACKAGE_SCHEMA_INVALID", details={"table": table})

    def _validate_context_lifecycle_schema(self) -> None:
        expected = {
            "context_capability_snapshots": (
                "tenant_id", "project_id", "snapshot_id", "provider", "model_id",
                "version", "snapshot_json", "snapshot_digest", "source", "trust",
                "observed_at", "expires_at", "previous_snapshot_id", "created_at",
            ),
            "context_capability_heads": (
                "tenant_id", "project_id", "provider", "model_id", "snapshot_id",
                "version", "updated_at",
            ),
            "context_usage_ledger": (
                "tenant_id", "project_id", "usage_id", "task_id", "request_id",
                "idempotency_key", "model_snapshot_id", "estimator_version",
                "accounting_digest", "current_window_input_tokens",
                "current_window_output_reserved_tokens", "cumulative_provider_input_tokens",
                "cumulative_provider_output_tokens", "cumulative_cost_minor_units",
                "currency", "estimate_kind", "record_json", "record_digest", "created_at",
            ),
            "context_lifecycle_records": (
                "tenant_id", "project_id", "record_id", "task_id", "kind",
                "request_id", "idempotency_key", "parent_record_id", "payload_json",
                "payload_digest", "created_at",
            ),
            "context_pressure_snapshots": (
                "tenant_id", "project_id", "pressure_id", "task_id", "request_id",
                "idempotency_key", "previous_pressure_id", "previous_state",
                "pressure_state", "used_tokens", "effective_input_budget",
                "forecast_tokens", "forecast_horizon", "action", "policy_version",
                "snapshot_json", "snapshot_digest", "created_at",
            ),
            "context_integrity_reports": (
                "tenant_id", "project_id", "report_id", "task_id", "request_id",
                "idempotency_key", "checkpoint_id", "passed",
                "side_effect_authorized", "report_json", "report_digest", "created_at",
            ),
            "context_checkpoints": (
                "tenant_id", "project_id", "checkpoint_id", "task_id", "request_id",
                "idempotency_key", "package_version", "model_snapshot_id",
                "raw_history_digest", "raw_history_bytes", "checkpoint_json",
                "checkpoint_digest", "integrity_report_id", "rollback_checkpoint_id",
                "side_effect_cursor_digest", "cost_cursor_digest", "created_at",
            ),
            "context_recovery_attempts": (
                "tenant_id", "project_id", "attempt_id", "checkpoint_id",
                "restore_request_id", "idempotency_key", "outcome",
                "side_effect_cursor_digest", "cost_cursor_digest", "result_json",
                "result_digest", "created_at",
            ),
        }
        with self._lock:
            for table, columns in expected.items():
                observed_columns = tuple(
                    str(row["name"])
                    for row in self._connection.execute(
                        f"PRAGMA table_info({table})"
                    ).fetchall()
                )
                if observed_columns != columns:
                    raise IntegrityError("CONTEXT_LIFECYCLE_SCHEMA_INVALID")
            immutable = {
                "context_capability_snapshots_no_update",
                "context_capability_snapshots_no_delete",
                "context_usage_ledger_no_update", "context_usage_ledger_no_delete",
                "context_lifecycle_records_no_update", "context_lifecycle_records_no_delete",
                "context_pressure_snapshots_no_update", "context_pressure_snapshots_no_delete",
                "context_checkpoints_no_update", "context_checkpoints_no_delete",
                "context_integrity_reports_no_update", "context_integrity_reports_no_delete",
                "context_recovery_attempts_no_update", "context_recovery_attempts_no_delete",
            }
            observed_triggers = {
                str(row["name"])
                for row in self._connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                ).fetchall()
            }
            if not immutable <= observed_triggers:
                raise IntegrityError("CONTEXT_LIFECYCLE_SCHEMA_INVALID")

    def _validate_governance_deletion_schema(self) -> None:
        expected = {
            "governance_deletion_jobs": (
                "tenant_id", "project_id", "job_id", "actor_id",
                "idempotency_key", "request_digest", "policy_version",
                "inventory_version", "inventory_digest", "state",
                "backup_delete_not_before", "legal_hold_count", "command_count",
                "proof_json", "proof_digest", "created_at", "updated_at",
                "completed_at",
            ),
            "governance_deletion_commands": (
                "tenant_id", "project_id", "command_id", "job_id", "store_kind",
                "object_id", "object_version", "object_digest", "byte_count",
                "command_digest", "state", "attempt", "claim_token_digest",
                "execution_receipt_digest", "verification_receipt_digest",
                "failure_code", "created_at", "updated_at",
            ),
            "governance_deletion_execution_receipts": (
                "tenant_id", "project_id", "command_id", "receipt_json",
                "receipt_digest", "executor_id", "recorded_at",
            ),
            "governance_deletion_verification_receipts": (
                "tenant_id", "project_id", "command_id", "receipt_json",
                "receipt_digest", "verifier_id", "recorded_at",
            ),
            "governance_deletion_audit": (
                "tenant_id", "project_id", "audit_id", "job_id", "command_id",
                "actor_id", "action", "event_digest", "occurred_at",
            ),
        }
        with self._lock:
            for table, columns in expected.items():
                observed = tuple(
                    str(row["name"])
                    for row in self._connection.execute(
                        f"PRAGMA table_info({table})"
                    ).fetchall()
                )
                if observed != columns:
                    raise IntegrityError("GOVERNANCE_DELETION_SCHEMA_INVALID")
            required_schema_objects = {
                "governance_deletion_command_queue",
                "governance_deletion_claim_identity",
                "governance_deletion_audit_job",
                "governance_deletion_jobs_scope_immutable",
                "governance_deletion_commands_binding_immutable",
                "governance_deletion_jobs_state_guard",
                "governance_deletion_commands_state_guard",
                "governance_deletion_jobs_no_delete",
                "governance_deletion_commands_no_delete",
                "governance_deletion_execution_receipts_no_update",
                "governance_deletion_execution_receipts_no_delete",
                "governance_deletion_verification_receipts_no_update",
                "governance_deletion_verification_receipts_no_delete",
                "governance_deletion_audit_no_update",
                "governance_deletion_audit_no_delete",
            }
            observed_schema_objects = {
                str(row["name"])
                for row in self._connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('index','trigger')"
                ).fetchall()
            }
            if not required_schema_objects <= observed_schema_objects:
                raise IntegrityError("GOVERNANCE_DELETION_SCHEMA_INVALID")

    def _validate_archive_expansion_schema(self) -> None:
        """Fail closed when the persistent cross-layer archive ledger drifts."""

        expected = {
            "archive_expansion_roots": (
                "tenant_id", "project_id", "root_archive_digest", "policy_digest",
                "max_total_uncompressed_bytes", "max_entries", "max_nested_depth",
                "consumed_uncompressed_bytes", "consumed_entries", "version",
                "created_at", "updated_at",
            ),
            "archive_expansion_nodes": (
                "tenant_id", "project_id", "node_digest", "root_archive_digest",
                "parent_node_digest", "parent_archive_digest", "parent_entry_digest",
                "parent_entry_receipt_digest", "parent_generation_digest",
                "archive_digest", "depth", "expanded_uncompressed_bytes",
                "expanded_entries", "request_digest", "state",
                "generation_digest", "result_digest", "created_at", "published_at",
            ),
            "archive_expansion_entries": (
                "tenant_id", "project_id", "node_digest", "entry_receipt_digest",
                "entry_digest", "path_digest", "byte_count", "nested_container",
                "generation_digest",
            ),
        }
        with self._lock:
            for table, columns in expected.items():
                observed = tuple(
                    str(row["name"])
                    for row in self._connection.execute(
                        f"PRAGMA table_info({table})"
                    ).fetchall()
                )
                if observed != columns:
                    raise IntegrityError("ARCHIVE_EXPANSION_SCHEMA_INVALID")
            invalid = self._connection.execute(
                """
                SELECT 1
                  FROM archive_expansion_roots AS root
                 WHERE typeof(root.tenant_id) <> 'text'
                    OR typeof(root.project_id) <> 'text'
                    OR length(root.root_archive_digest) <> 64
                    OR root.root_archive_digest GLOB '*[^0-9a-f]*'
                    OR length(root.policy_digest) <> 64
                    OR root.policy_digest GLOB '*[^0-9a-f]*'
                    OR root.consumed_uncompressed_bytes < 0
                    OR root.consumed_uncompressed_bytes > root.max_total_uncompressed_bytes
                    OR root.consumed_entries < 0
                    OR root.consumed_entries > root.max_entries
                    OR root.version < 1
                    OR root.consumed_uncompressed_bytes <> COALESCE((
                        SELECT SUM(node.expanded_uncompressed_bytes)
                          FROM archive_expansion_nodes AS node
                         WHERE node.tenant_id = root.tenant_id
                           AND node.project_id = root.project_id
                           AND node.root_archive_digest = root.root_archive_digest
                    ), 0)
                    OR root.consumed_entries <> COALESCE((
                        SELECT SUM(node.expanded_entries)
                          FROM archive_expansion_nodes AS node
                         WHERE node.tenant_id = root.tenant_id
                           AND node.project_id = root.project_id
                           AND node.root_archive_digest = root.root_archive_digest
                    ), 0)
                    OR EXISTS (
                        SELECT 1 FROM archive_expansion_nodes AS node
                         WHERE node.tenant_id = root.tenant_id
                           AND node.project_id = root.project_id
                           AND node.root_archive_digest = root.root_archive_digest
                           AND node.depth > root.max_nested_depth
                    )
                 LIMIT 1
                """
            ).fetchone()
            invalid_node = self._connection.execute(
                """
                SELECT 1
                  FROM archive_expansion_nodes AS node
                 WHERE length(node.node_digest) <> 64
                    OR node.node_digest GLOB '*[^0-9a-f]*'
                    OR length(node.archive_digest) <> 64
                    OR node.archive_digest GLOB '*[^0-9a-f]*'
                    OR length(node.request_digest) <> 64
                    OR node.request_digest GLOB '*[^0-9a-f]*'
                    OR (node.depth = 0 AND (
                        node.root_archive_digest <> node.archive_digest
                        OR node.parent_node_digest IS NOT NULL
                        OR node.parent_archive_digest IS NOT NULL
                        OR node.parent_entry_digest IS NOT NULL
                        OR node.parent_entry_receipt_digest IS NOT NULL
                        OR node.parent_generation_digest IS NOT NULL
                    ))
                    OR (node.depth > 0 AND (
                        node.parent_node_digest IS NULL
                        OR node.parent_archive_digest IS NULL
                        OR node.parent_entry_digest IS NULL
                        OR node.parent_entry_receipt_digest IS NULL
                        OR node.parent_generation_digest IS NULL
                    ))
                    OR (node.depth > 0 AND NOT EXISTS (
                        SELECT 1
                          FROM archive_expansion_nodes AS parent
                          JOIN archive_expansion_entries AS parent_entry
                            ON parent_entry.tenant_id = parent.tenant_id
                           AND parent_entry.project_id = parent.project_id
                           AND parent_entry.node_digest = parent.node_digest
                         WHERE parent.tenant_id = node.tenant_id
                           AND parent.project_id = node.project_id
                           AND parent.node_digest = node.parent_node_digest
                           AND parent.root_archive_digest = node.root_archive_digest
                           AND parent.depth + 1 = node.depth
                           AND parent.archive_digest = node.parent_archive_digest
                           AND parent.state = 'PUBLISHED'
                           AND parent.generation_digest = node.parent_generation_digest
                           AND parent_entry.entry_digest = node.parent_entry_digest
                           AND parent_entry.entry_receipt_digest = node.parent_entry_receipt_digest
                           AND parent_entry.nested_container IS NOT NULL
                    ))
                    OR (node.state = 'RESERVED' AND EXISTS (
                        SELECT 1 FROM archive_expansion_entries AS entry
                         WHERE entry.tenant_id = node.tenant_id
                           AND entry.project_id = node.project_id
                           AND entry.node_digest = node.node_digest
                    ))
                    OR (node.state = 'PUBLISHED' AND (
                        node.expanded_entries < (
                            SELECT COUNT(*) FROM archive_expansion_entries AS entry
                             WHERE entry.tenant_id = node.tenant_id
                               AND entry.project_id = node.project_id
                               AND entry.node_digest = node.node_digest
                        )
                        OR node.expanded_uncompressed_bytes <> COALESCE((
                            SELECT SUM(entry.byte_count)
                              FROM archive_expansion_entries AS entry
                             WHERE entry.tenant_id = node.tenant_id
                               AND entry.project_id = node.project_id
                               AND entry.node_digest = node.node_digest
                        ), 0)
                    ))
                    OR EXISTS (
                        SELECT 1 FROM archive_expansion_entries AS entry
                         WHERE entry.tenant_id = node.tenant_id
                           AND entry.project_id = node.project_id
                           AND entry.node_digest = node.node_digest
                           AND (
                               length(entry.entry_receipt_digest) <> 64
                               OR entry.entry_receipt_digest GLOB '*[^0-9a-f]*'
                               OR length(entry.entry_digest) <> 64
                               OR entry.entry_digest GLOB '*[^0-9a-f]*'
                               OR length(entry.path_digest) <> 64
                               OR entry.path_digest GLOB '*[^0-9a-f]*'
                               OR entry.generation_digest IS NOT node.generation_digest
                           )
                    )
                 LIMIT 1
                """
            ).fetchone()
        if invalid is not None or invalid_node is not None:
            raise IntegrityError("ARCHIVE_EXPANSION_STATE_INVALID")

    def _validate_processing_job_version_schema(self) -> None:
        """Verify the formal v7 migration installed the exact job version."""

        with self._lock:
            columns = {
                str(row["name"]): row
                for row in self._connection.execute(
                    "PRAGMA table_info(processing_jobs)"
                ).fetchall()
            }
            version = columns.get("version")
            if (
                version is None
                or str(version["type"]).upper() != "INTEGER"
                or int(version["notnull"]) != 1
                or str(version["dflt_value"]) not in {"1", "(1)"}
                or int(version["pk"]) != 0
            ):
                raise IntegrityError("PROCESSING_JOB_VERSION_SCHEMA_INVALID")
            invalid = self._connection.execute(
                """SELECT 1 FROM processing_jobs
                WHERE typeof(version) <> 'integer' OR version < 1
                   OR version > ? LIMIT 1""",
                (MAX_SAFE_JSON_INTEGER,),
            ).fetchone()
            if invalid is not None:
                raise IntegrityError("PROCESSING_JOB_VERSION_INVALID")

    def _validate_processing_job_cancellation_schema(self) -> None:
        """Verify the v23 durable cancellation request fence."""

        def normalized_sql(value: object) -> str:
            return " ".join(str(value or "").split()).lower()

        with self._lock:
            columns = {
                str(row["name"]): row
                for row in self._connection.execute(
                    "PRAGMA table_info(processing_jobs)"
                ).fetchall()
            }
            marker = columns.get("cancel_requested")
            if (
                marker is None
                or str(marker["type"]).upper() != "INTEGER"
                or int(marker["notnull"]) != 1
                or str(marker["dflt_value"]) not in {"0", "(0)"}
                or int(marker["pk"]) != 0
            ):
                raise IntegrityError("PROCESSING_JOB_CANCELLATION_SCHEMA_INVALID")
            for name in ("cancel_requested_by", "cancel_requested_at", "cancel_reason"):
                column = columns.get(name)
                if (
                    column is None
                    or str(column["type"]).upper() != "TEXT"
                    or int(column["notnull"]) != 0
                    or column["dflt_value"] is not None
                    or int(column["pk"]) != 0
                ):
                    raise IntegrityError("PROCESSING_JOB_CANCELLATION_SCHEMA_INVALID")
            invalid = self._connection.execute(
                """
                SELECT 1 FROM processing_jobs
                 WHERE typeof(cancel_requested) <> 'integer'
                    OR cancel_requested NOT IN (0, 1)
                    OR (cancel_requested = 0 AND (
                        cancel_requested_by IS NOT NULL
                        OR cancel_requested_at IS NOT NULL
                        OR cancel_reason IS NOT NULL
                    ))
                    OR (cancel_requested = 1 AND (
                        cancel_requested_by IS NULL
                        OR length(cancel_requested_by) = 0
                        OR length(cancel_requested_by) > 255
                        OR cancel_requested_at IS NULL
                        OR length(cancel_requested_at) = 0
                        OR cancel_reason IS NULL
                        OR length(cancel_reason) = 0
                        OR length(cancel_reason) > 128
                    ))
                 LIMIT 1
                """
            ).fetchone()
            table_row = self._connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='processing_jobs'"
            ).fetchone()
            table_sql = (
                self._normalized_schema_sql(table_row["sql"])
                if table_row is not None
                else ""
            )
            schema_rows = {
                (str(row["type"]), str(row["name"])): normalized_sql(row["sql"])
                for row in self._connection.execute(
                    """
                    SELECT type,name,sql FROM sqlite_master
                     WHERE (type='index' AND name='processing_jobs_cancellation_idx')
                        OR (type='trigger' AND name IN (
                            'processing_jobs_cancellation_insert_guard',
                            'processing_jobs_cancellation_metadata_guard'
                        ))
                    """
                ).fetchall()
            }
            expected_index = normalized_sql(
                """
                CREATE INDEX processing_jobs_cancellation_idx
                    ON processing_jobs (tenant_id, project_id, cancel_requested, cancel_requested_at)
                    WHERE cancel_requested = 1
                """
            )
            expected_insert_guard = normalized_sql(
                """
                CREATE TRIGGER processing_jobs_cancellation_insert_guard
                BEFORE INSERT ON processing_jobs
                FOR EACH ROW
                WHEN
                    (NEW.cancel_requested = 0 AND (
                        NEW.cancel_requested_by IS NOT NULL
                        OR NEW.cancel_requested_at IS NOT NULL
                        OR NEW.cancel_reason IS NOT NULL
                    ))
                    OR
                    (NEW.cancel_requested = 1 AND (
                        NEW.cancel_requested_by IS NULL
                        OR length(NEW.cancel_requested_by) = 0
                        OR length(NEW.cancel_requested_by) > 255
                        OR NEW.cancel_requested_at IS NULL
                        OR length(NEW.cancel_requested_at) = 0
                        OR NEW.cancel_reason IS NULL
                        OR length(NEW.cancel_reason) = 0
                        OR length(NEW.cancel_reason) > 128
                    ))
                BEGIN
                    SELECT RAISE(ABORT, 'processing_job_cancellation_metadata_invalid');
                END
                """
            )
            expected_metadata_guard = normalized_sql(
                """
                CREATE TRIGGER processing_jobs_cancellation_metadata_guard
                BEFORE UPDATE OF cancel_requested, cancel_requested_by, cancel_requested_at, cancel_reason
                ON processing_jobs
                FOR EACH ROW
                WHEN
                    (OLD.cancel_requested = 1 AND (
                        NEW.cancel_requested <> 1
                        OR NEW.cancel_requested_by IS NOT OLD.cancel_requested_by
                        OR NEW.cancel_requested_at IS NOT OLD.cancel_requested_at
                        OR NEW.cancel_reason IS NOT OLD.cancel_reason
                    ))
                    OR
                    (NEW.cancel_requested = 0 AND (
                        NEW.cancel_requested_by IS NOT NULL
                        OR NEW.cancel_requested_at IS NOT NULL
                        OR NEW.cancel_reason IS NOT NULL
                    ))
                    OR
                    (NEW.cancel_requested = 1 AND (
                        NEW.cancel_requested_by IS NULL
                        OR length(NEW.cancel_requested_by) = 0
                        OR length(NEW.cancel_requested_by) > 255
                        OR NEW.cancel_requested_at IS NULL
                        OR length(NEW.cancel_requested_at) = 0
                        OR NEW.cancel_reason IS NULL
                        OR length(NEW.cancel_reason) = 0
                        OR length(NEW.cancel_reason) > 128
                    ))
                BEGIN
                    SELECT RAISE(ABORT, 'processing_job_cancellation_metadata_immutable');
                END
                """
            )
            if (
                invalid is not None
                or "cancel_requestedintegernotnulldefault0check(cancel_requestedin(0,1))"
                not in table_sql
                or schema_rows.get(("index", "processing_jobs_cancellation_idx")) != expected_index
                or schema_rows.get(("trigger", "processing_jobs_cancellation_insert_guard"))
                != expected_insert_guard
                or schema_rows.get(("trigger", "processing_jobs_cancellation_metadata_guard"))
                != expected_metadata_guard
            ):
                raise IntegrityError("PROCESSING_JOB_CANCELLATION_SCHEMA_INVALID")

    def _validate_core_outbox_delivery_schema(self) -> None:
        """Verify immutable v24 transport receipts for core outbox publication."""

        expected_columns = (
            "event_id",
            "tenant_id",
            "project_id",
            "actor_id",
            "payload_digest",
            "transport",
            "delivery_id",
            "receipt_json",
            "receipt_digest",
            "verified_response_digest",
            "delivered_at",
            "publisher_capability_id",
            "response_verifier_capability_id",
            "recorded_at",
        )
        with self._lock:
            columns = tuple(
                str(row["name"])
                for row in self._connection.execute(
                    "PRAGMA table_info(core_outbox_delivery_receipts)"
                ).fetchall()
            )
            table_row = self._connection.execute(
                """SELECT sql FROM sqlite_master
                    WHERE type='table' AND name='core_outbox_delivery_receipts'"""
            ).fetchone()
            schema_rows = self._connection.execute(
                """SELECT type,name,sql FROM sqlite_master
                    WHERE tbl_name='core_outbox_delivery_receipts'
                      AND type IN ('index','trigger')"""
            ).fetchall()
            schema_sql = {
                (str(row["type"]), str(row["name"])): self._normalized_schema_sql(row["sql"])
                for row in schema_rows
                if row["sql"] is not None
            }
            index_rows = self._connection.execute(
                "PRAGMA index_list(core_outbox_delivery_receipts)"
            ).fetchall()
            scope_index = next(
                (row for row in index_rows if row["name"] == "core_outbox_delivery_scope_idx"),
                None,
            )
            scope_columns = tuple(
                str(row["name"])
                for row in self._connection.execute(
                    "PRAGMA index_info(core_outbox_delivery_scope_idx)"
                ).fetchall()
            )
            unique_delivery_indexes = [
                tuple(
                    str(column["name"])
                    for column in self._connection.execute(
                        "SELECT name FROM pragma_index_info(?)",
                        (str(row["name"]),),
                    ).fetchall()
                )
                for row in index_rows
                if int(row["unique"]) == 1
            ]
            foreign_keys = self._connection.execute(
                "PRAGMA foreign_key_list(core_outbox_delivery_receipts)"
            ).fetchall()
            table_sql = (
                self._normalized_schema_sql(table_row["sql"])
                if table_row is not None
                else ""
            )
            expected_scope_sql = self._normalized_schema_sql(
                """CREATE INDEX core_outbox_delivery_scope_idx
                    ON core_outbox_delivery_receipts
                    (tenant_id, project_id, delivered_at, event_id)"""
            )
            expected_update_trigger = self._normalized_schema_sql(
                """CREATE TRIGGER core_outbox_delivery_receipts_no_update
                    BEFORE UPDATE ON core_outbox_delivery_receipts
                    BEGIN
                        SELECT RAISE(ABORT, 'core outbox delivery receipt immutable');
                    END"""
            )
            expected_delete_trigger = self._normalized_schema_sql(
                """CREATE TRIGGER core_outbox_delivery_receipts_no_delete
                    BEFORE DELETE ON core_outbox_delivery_receipts
                    BEGIN
                        SELECT RAISE(ABORT, 'core outbox delivery receipt immutable');
                    END"""
            )
            fk_shape = tuple(
                (
                    int(row["seq"]),
                    str(row["table"]),
                    str(row["from"]),
                    str(row["to"]),
                    str(row["on_update"]),
                    str(row["on_delete"]),
                    str(row["match"]),
                )
                for row in sorted(foreign_keys, key=lambda item: int(item["seq"]))
            )
            invalid_scope = self._connection.execute(
                """
                SELECT 1
                  FROM core_outbox_delivery_receipts AS receipt
                  LEFT JOIN outbox_events AS event ON event.event_id = receipt.event_id
                 WHERE event.event_id IS NULL
                    OR event.tenant_id <> receipt.tenant_id
                    OR event.project_id <> receipt.project_id
                    OR event.payload_digest IS NULL
                    OR event.payload_digest <> receipt.payload_digest
                    OR event.published_at IS NULL
                    OR event.published_at <> receipt.delivered_at
                 LIMIT 1
                """
            ).fetchone()
            receipt_rows = self._connection.execute(
                "SELECT * FROM core_outbox_delivery_receipts"
            ).fetchall()

        required_table_fragments = {
            "check(typeof(actor_id)='text'andlength(actor_id)between1and200)",
            "check(length(payload_digest)=64andpayload_digestnotglob'*[^0-9a-f]*')",
            "check(length(receipt_digest)=64andreceipt_digestnotglob'*[^0-9a-f]*')",
            "check(length(verified_response_digest)=64andverified_response_digestnotglob'*[^0-9a-f]*')",
            "unique(tenant_id,project_id,transport,delivery_id)",
            "foreignkey(tenant_id,project_id,event_id)referencesoutbox_events(tenant_id,project_id,event_id)",
        }
        expected_fk_shape = (
            (0, "outbox_events", "tenant_id", "tenant_id", "NO ACTION", "NO ACTION", "NONE"),
            (1, "outbox_events", "project_id", "project_id", "NO ACTION", "NO ACTION", "NONE"),
            (2, "outbox_events", "event_id", "event_id", "NO ACTION", "NO ACTION", "NONE"),
        )
        if (
            columns != expected_columns
            or not all(fragment in table_sql for fragment in required_table_fragments)
            or scope_index is None
            or int(scope_index["unique"]) != 0
            or str(scope_index["origin"]) != "c"
            or int(scope_index["partial"]) != 0
            or scope_columns != ("tenant_id", "project_id", "delivered_at", "event_id")
            or schema_sql.get(("index", "core_outbox_delivery_scope_idx"))
            != expected_scope_sql
            or ("tenant_id", "project_id", "transport", "delivery_id")
            not in unique_delivery_indexes
            or fk_shape != expected_fk_shape
            or schema_sql.get(("trigger", "core_outbox_delivery_receipts_no_update"))
            != expected_update_trigger
            or schema_sql.get(("trigger", "core_outbox_delivery_receipts_no_delete"))
            != expected_delete_trigger
            or len([key for key in schema_sql if key[0] == "trigger"]) != 2
            or invalid_scope is not None
        ):
            raise IntegrityError("CORE_OUTBOX_DELIVERY_SCHEMA_INVALID")

        future_bound = datetime.now(UTC) + self._MAX_CORE_OUTBOX_FUTURE_SKEW
        for row in receipt_rows:
            try:
                actor_id = require_actor_id(row["actor_id"])
                publisher_capability_id = require_resource_id(
                    row["publisher_capability_id"], "publisher_capability_id"
                )
                verifier_capability_id = require_resource_id(
                    row["response_verifier_capability_id"],
                    "response_verifier_capability_id",
                )
                receipt_digest = normalize_sha256(row["receipt_digest"])
                verified_response_digest = normalize_sha256(
                    row["verified_response_digest"]
                )
                receipt = json.loads(row["receipt_json"])
                delivered_timestamp = self._core_outbox_timestamp(
                    row["delivered_at"], "delivered_at"
                )
                recorded_timestamp = self._core_outbox_timestamp(
                    row["recorded_at"], "recorded_at"
                )
            except Exception as error:
                raise IntegrityError("CORE_OUTBOX_DELIVERY_STATE_INVALID") from error
            if (
                row["actor_id"] != actor_id
                or row["publisher_capability_id"] != publisher_capability_id
                or row["response_verifier_capability_id"] != verifier_capability_id
                or not isinstance(receipt, dict)
                or canonical_json(receipt) != row["receipt_json"]
                or not hmac.compare_digest(
                    receipt_digest,
                    sha256_bytes(row["receipt_json"].encode("utf-8")),
                )
                or receipt.get("response_digest") != verified_response_digest
                or receipt.get("event_id") != row["event_id"]
                or receipt.get("payload_digest") != row["payload_digest"]
                or receipt.get("delivered_at") != row["delivered_at"]
                or delivered_timestamp > future_bound
                or recorded_timestamp > future_bound
            ):
                raise IntegrityError("CORE_OUTBOX_DELIVERY_STATE_INVALID")

    def _validate_skill_execution_dispatch_schema(self) -> None:
        """Verify the dispatch marker required by the v9 replay fence."""

        with self._lock:
            columns = {
                str(row["name"]): row
                for row in self._connection.execute(
                    "PRAGMA table_info(skill_execution_receipts)"
                ).fetchall()
            }
            marker = columns.get("dispatch_started_at")
            if (
                marker is None
                or str(marker["type"]).upper() != "TEXT"
                or int(marker["notnull"]) != 0
                or marker["dflt_value"] is not None
                or int(marker["pk"]) != 0
            ):
                raise IntegrityError("SKILL_EXECUTION_DISPATCH_SCHEMA_INVALID")
            invalid = self._connection.execute(
                """
                SELECT 1 FROM skill_execution_receipts
                 WHERE dispatch_started_at IS NOT NULL
                   AND (typeof(dispatch_started_at) <> 'text'
                        OR length(dispatch_started_at) < 20
                        OR length(dispatch_started_at) > 64)
                 LIMIT 1
                """
            ).fetchone()
            if invalid is not None:
                raise IntegrityError("SKILL_EXECUTION_DISPATCH_STATE_INVALID")

    def _validate_skill_execution_response_digest_schema(self) -> None:
        """Verify the formal v12 tamper-evident response binding."""

        with self._lock:
            columns = {
                str(row["name"]): row
                for row in self._connection.execute(
                    "PRAGMA table_info(skill_execution_receipts)"
                ).fetchall()
            }
            response_digest = columns.get("response_digest")
            if (
                response_digest is None
                or str(response_digest["type"]).upper() != "TEXT"
                or int(response_digest["notnull"]) != 0
                or response_digest["dflt_value"] is not None
                or int(response_digest["pk"]) != 0
            ):
                raise IntegrityError("SKILL_EXECUTION_RESPONSE_DIGEST_SCHEMA_INVALID")
            invalid = self._connection.execute(
                """
                SELECT 1 FROM skill_execution_receipts
                 WHERE response_digest IS NOT NULL
                   AND (typeof(response_digest) <> 'text'
                        OR length(response_digest) <> 64
                        OR response_digest GLOB '*[^0-9a-f]*'
                        OR status <> 'COMPLETED')
                 LIMIT 1
                """
            ).fetchone()
            if invalid is not None:
                raise IntegrityError("SKILL_EXECUTION_RESPONSE_DIGEST_STATE_INVALID")

    def _validate_core_outbox_payload_schema(self) -> None:
        """Verify the v13 nullable legacy marker and trusted digest shape."""

        with self._lock:
            columns = {
                str(row["name"]): row
                for row in self._connection.execute(
                    "PRAGMA table_info(outbox_events)"
                ).fetchall()
            }
            payload_digest = columns.get("payload_digest")
            if (
                payload_digest is None
                or str(payload_digest["type"]).upper() != "TEXT"
                or int(payload_digest["notnull"]) != 0
                or payload_digest["dflt_value"] is not None
                or int(payload_digest["pk"]) != 0
            ):
                raise IntegrityError("OUTBOX_EVENT_PAYLOAD_DIGEST_SCHEMA_INVALID")
            invalid = self._connection.execute(
                """
                SELECT 1 FROM outbox_events
                 WHERE payload_digest IS NOT NULL
                   AND (typeof(payload_digest) <> 'text'
                        OR length(payload_digest) <> 64
                        OR payload_digest GLOB '*[^0-9a-f]*')
                 LIMIT 1
                """
            ).fetchone()
            if invalid is not None:
                raise IntegrityError("OUTBOX_EVENT_PAYLOAD_DIGEST_STATE_INVALID")

    def _validate_human_review_correction_schema(self) -> None:
        """Verify the exact v10 immutable correction-ledger contract."""

        expected_columns = (
            ("correction_id", "TEXT", 0, None, 1),
            ("tenant_id", "TEXT", 1, None, 0),
            ("project_id", "TEXT", 1, None, 0),
            ("actor_id", "TEXT", 1, None, 0),
            ("asset_id", "TEXT", 1, None, 0),
            ("source_version", "INTEGER", 1, None, 0),
            ("version", "INTEGER", 1, None, 0),
            ("source_digest", "TEXT", 1, None, 0),
            ("source_json", "TEXT", 1, None, 0),
            ("correction_digest", "TEXT", 1, None, 0),
            ("correction_json", "TEXT", 1, None, 0),
            ("idempotency_key", "TEXT", 1, None, 0),
            ("request_digest", "TEXT", 1, None, 0),
            ("policy_version", "TEXT", 1, None, 0),
            ("review_state_version", "TEXT", 1, None, 0),
            ("approval_state", "TEXT", 1, None, 0),
            ("rebuild_state", "TEXT", 1, None, 0),
            ("result_json", "TEXT", 1, None, 0),
            ("result_digest", "TEXT", 1, None, 0),
            ("created_at", "TEXT", 1, None, 0),
        )
        expected_table_sql = """
            CREATE TABLE human_review_corrections (
                correction_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                source_version INTEGER NOT NULL CHECK (source_version >= 1),
                version INTEGER NOT NULL CHECK (version = source_version + 1),
                source_digest TEXT NOT NULL CHECK (length(source_digest) = 64),
                source_json TEXT NOT NULL,
                correction_digest TEXT NOT NULL CHECK (length(correction_digest) = 64),
                correction_json TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
                policy_version TEXT NOT NULL,
                review_state_version TEXT NOT NULL,
                approval_state TEXT NOT NULL CHECK (approval_state = 'NOT_RUN'),
                rebuild_state TEXT NOT NULL CHECK (rebuild_state = 'NOT_RUN'),
                result_json TEXT NOT NULL,
                result_digest TEXT NOT NULL CHECK (length(result_digest) = 64),
                created_at TEXT NOT NULL,
                UNIQUE (tenant_id, project_id, correction_id),
                UNIQUE (tenant_id, project_id, asset_id, version),
                UNIQUE (tenant_id, project_id, actor_id, idempotency_key),
                FOREIGN KEY (tenant_id, project_id, asset_id)
                    REFERENCES input_assets (tenant_id, project_id, asset_id)
            )
        """

        def normalize_sql(value: Any) -> str:
            if not isinstance(value, str):
                return ""
            return " ".join(value.strip().rstrip(";").split()).upper()

        with self._lock:
            columns = tuple(
                (
                    str(row["name"]),
                    str(row["type"]).upper(),
                    int(row["notnull"]),
                    row["dflt_value"],
                    int(row["pk"]),
                )
                for row in self._connection.execute(
                    "PRAGMA table_info(human_review_corrections)"
                ).fetchall()
            )
            table_row = self._connection.execute(
                """SELECT sql FROM sqlite_master
                    WHERE type='table' AND name='human_review_corrections'"""
            ).fetchone()
            if (
                columns != expected_columns
                or table_row is None
                or normalize_sql(table_row["sql"]) != normalize_sql(expected_table_sql)
            ):
                raise IntegrityError("HUMAN_REVIEW_CORRECTION_SCHEMA_INVALID")

            foreign_keys = self._connection.execute(
                "PRAGMA foreign_key_list(human_review_corrections)"
            ).fetchall()
            if (
                len(foreign_keys) != 3
                or len({int(row["id"]) for row in foreign_keys}) != 1
                or {
                    (str(row["from"]), str(row["to"])) for row in foreign_keys
                }
                != {
                    ("tenant_id", "tenant_id"),
                    ("project_id", "project_id"),
                    ("asset_id", "asset_id"),
                }
                or any(
                    str(row["table"]) != "input_assets"
                    or str(row["on_update"]).upper() != "NO ACTION"
                    or str(row["on_delete"]).upper() != "NO ACTION"
                    or str(row["match"]).upper() != "NONE"
                    for row in foreign_keys
                )
            ):
                raise IntegrityError("HUMAN_REVIEW_CORRECTION_SCHEMA_INVALID")

            indexes = self._connection.execute(
                "PRAGMA index_list(human_review_corrections)"
            ).fetchall()
            index_contracts: dict[str, tuple[tuple[str, int, str], ...]] = {}
            for index in indexes:
                index_name = str(index["name"])
                escaped_name = index_name.replace('"', '""')
                key_columns = tuple(
                    (
                        str(row["name"]),
                        int(row["desc"]),
                        str(row["coll"]).upper(),
                    )
                    for row in self._connection.execute(
                        f'PRAGMA index_xinfo("{escaped_name}")'
                    ).fetchall()
                    if int(row["key"]) == 1
                )
                index_contracts[index_name] = key_columns
            unique_contracts = {
                index_contracts[str(index["name"])]
                for index in indexes
                if int(index["unique"]) == 1
            }
            expected_unique_contracts = {
                (("correction_id", 0, "BINARY"),),
                (
                    ("tenant_id", 0, "BINARY"),
                    ("project_id", 0, "BINARY"),
                    ("correction_id", 0, "BINARY"),
                ),
                (
                    ("tenant_id", 0, "BINARY"),
                    ("project_id", 0, "BINARY"),
                    ("asset_id", 0, "BINARY"),
                    ("version", 0, "BINARY"),
                ),
                (
                    ("tenant_id", 0, "BINARY"),
                    ("project_id", 0, "BINARY"),
                    ("actor_id", 0, "BINARY"),
                    ("idempotency_key", 0, "BINARY"),
                ),
            }
            latest = next(
                (
                    index
                    for index in indexes
                    if str(index["name"]) == "human_review_corrections_latest_idx"
                ),
                None,
            )
            expected_latest = (
                ("tenant_id", 0, "BINARY"),
                ("project_id", 0, "BINARY"),
                ("asset_id", 0, "BINARY"),
                ("version", 1, "BINARY"),
                ("correction_id", 0, "BINARY"),
            )
            if (
                len(indexes) != 5
                or unique_contracts != expected_unique_contracts
                or latest is None
                or int(latest["unique"]) != 0
                or str(latest["origin"]) != "c"
                or int(latest["partial"]) != 0
                or index_contracts.get("human_review_corrections_latest_idx")
                != expected_latest
            ):
                raise IntegrityError("HUMAN_REVIEW_CORRECTION_SCHEMA_INVALID")

            expected_triggers = {
                "human_review_corrections_no_update": normalize_sql(
                    """CREATE TRIGGER human_review_corrections_no_update
                    BEFORE UPDATE ON human_review_corrections
                    BEGIN
                        SELECT RAISE(ABORT, 'HUMAN_REVIEW_CORRECTION_IMMUTABLE');
                    END"""
                ),
                "human_review_corrections_no_delete": normalize_sql(
                    """CREATE TRIGGER human_review_corrections_no_delete
                    BEFORE DELETE ON human_review_corrections
                    BEGIN
                        SELECT RAISE(ABORT, 'HUMAN_REVIEW_CORRECTION_IMMUTABLE');
                    END"""
                ),
            }
            triggers = {
                str(row["name"]): normalize_sql(row["sql"])
                for row in self._connection.execute(
                    """SELECT name,sql FROM sqlite_master
                        WHERE type='trigger' AND tbl_name='human_review_corrections'"""
                ).fetchall()
            }
            if triggers != expected_triggers:
                raise IntegrityError("HUMAN_REVIEW_CORRECTION_IMMUTABILITY_INVALID")

            invalid = self._connection.execute(
                """
                SELECT 1 FROM human_review_corrections
                 WHERE typeof(correction_id) <> 'text'
                    OR typeof(tenant_id) <> 'text'
                    OR typeof(project_id) <> 'text'
                    OR typeof(actor_id) <> 'text'
                    OR typeof(asset_id) <> 'text'
                    OR typeof(source_version) <> 'integer'
                    OR source_version < 1 OR source_version >= ?
                    OR typeof(version) <> 'integer'
                    OR version <> source_version + 1 OR version > ?
                    OR typeof(source_digest) <> 'text'
                    OR length(source_digest) <> 64
                    OR source_digest GLOB '*[^0-9a-f]*'
                    OR typeof(correction_digest) <> 'text'
                    OR length(correction_digest) <> 64
                    OR correction_digest GLOB '*[^0-9a-f]*'
                    OR typeof(request_digest) <> 'text'
                    OR length(request_digest) <> 64
                    OR request_digest GLOB '*[^0-9a-f]*'
                    OR typeof(result_digest) <> 'text'
                    OR length(result_digest) <> 64
                    OR result_digest GLOB '*[^0-9a-f]*'
                    OR typeof(source_json) <> 'text'
                    OR length(CAST(source_json AS BLOB)) > ?
                    OR typeof(correction_json) <> 'text'
                    OR length(CAST(correction_json AS BLOB)) > ?
                    OR typeof(result_json) <> 'text'
                    OR length(CAST(result_json AS BLOB)) > ?
                    OR typeof(idempotency_key) <> 'text'
                    OR length(CAST(idempotency_key AS BLOB)) NOT BETWEEN 1 AND 200
                    OR typeof(policy_version) <> 'text' OR policy_version = ''
                    OR typeof(review_state_version) <> 'text'
                    OR review_state_version = ''
                    OR approval_state <> 'NOT_RUN'
                    OR rebuild_state <> 'NOT_RUN'
                    OR typeof(created_at) <> 'text'
                    OR length(created_at) NOT BETWEEN 20 AND 64
                 LIMIT 1
                """,
                (
                    MAX_SAFE_JSON_INTEGER,
                    MAX_SAFE_JSON_INTEGER,
                    2 * 1024 * 1024,
                    2 * 1024 * 1024,
                    4 * 1024 * 1024,
                ),
            ).fetchone()
            if invalid is not None:
                raise IntegrityError("HUMAN_REVIEW_CORRECTION_STATE_INVALID")

    def _validate_human_review_workflow_schema(self) -> None:
        """Fail closed on v11 review workflow schema or persisted-row drift."""

        def migration_contract(resource: str, object_type: str) -> dict[str, str]:
            statements: list[str] = []
            pending = ""
            for line in migration_sql(resource).splitlines():
                pending += line + "\n"
                if sqlite3.complete_statement(pending):
                    statements.append(pending.strip())
                    pending = ""
            if pending.strip():
                raise IntegrityError("HUMAN_REVIEW_WORKFLOW_SCHEMA_INVALID")
            prefix = f"CREATE {object_type.upper()} "
            result: dict[str, str] = {}
            for statement in statements:
                statement = "\n".join(
                    line
                    for line in statement.splitlines()
                    if not line.lstrip().startswith("--")
                ).strip()
                normalized = " ".join(statement.rstrip(";").split()).upper()
                if not normalized.startswith(prefix):
                    continue
                tokens = statement.split()
                if len(tokens) < 3:
                    raise IntegrityError("HUMAN_REVIEW_WORKFLOW_SCHEMA_INVALID")
                result[tokens[2].strip('"`[]').lower()] = normalized
            return result

        expected_table_sql = {
            **migration_contract("010_human_review_corrections.sql", "TABLE"),
            **migration_contract("011_human_review_workflow.sql", "TABLE"),
            **migration_contract("014_human_review_authoritative_sources.sql", "TABLE"),
            **migration_contract("015_human_review_enqueue_recovery.sql", "TABLE"),
            **migration_contract("016_human_review_target_head_reservations.sql", "TABLE"),
        }
        expected_index_sql = {
            **migration_contract("010_human_review_corrections.sql", "INDEX"),
            **migration_contract("011_human_review_workflow.sql", "INDEX"),
            **migration_contract("014_human_review_authoritative_sources.sql", "INDEX"),
            **migration_contract("015_human_review_enqueue_recovery.sql", "INDEX"),
            **migration_contract("016_human_review_target_head_reservations.sql", "INDEX"),
        }
        expected_trigger_sql = {
            **migration_contract("010_human_review_corrections.sql", "TRIGGER"),
            **migration_contract("011_human_review_workflow.sql", "TRIGGER"),
            **migration_contract("014_human_review_authoritative_sources.sql", "TRIGGER"),
            **migration_contract("015_human_review_enqueue_recovery.sql", "TRIGGER"),
            **migration_contract("016_human_review_target_head_reservations.sql", "TRIGGER"),
        }

        expected_columns = {
            "human_review_tasks": (
                "task_id", "tenant_id", "project_id", "asset_id", "target_kind",
                "target_json", "target_digest", "original_value_json",
                "original_value_digest", "source_digest", "source_ref_json",
                "source_ref_digest", "confidence", "reason", "state",
                "current_correction_version", "current_correction_digest",
                "effective_version", "effective_digest", "claim_actor_id",
                "claim_token_digest", "claim_fence", "claim_expires_at", "version",
                "created_by", "created_at", "updated_at", "closed_at",
            ),
            "human_review_correction_versions": (
                "correction_id", "tenant_id", "project_id", "task_id",
                "correction_version", "parent_correction_version", "target_kind",
                "target_json", "original_value_json", "original_value_digest",
                "corrected_value_json", "corrected_value_digest", "source_digest",
                "correction_digest", "actor_id", "reason", "request_digest",
                "created_at",
            ),
            "human_review_decisions": (
                "decision_id", "tenant_id", "project_id", "task_id",
                "decision_version", "decision", "prior_state", "next_state",
                "correction_version", "correction_digest", "source_digest",
                "actor_id", "reason", "request_digest", "created_at",
            ),
            "human_review_audit_log": (
                "audit_id", "tenant_id", "project_id", "task_id", "event_type",
                "actor_id", "prior_state", "next_state", "task_version",
                "details_json", "details_digest", "occurred_at",
            ),
            "human_review_operation_receipts": (
                "tenant_id", "project_id", "actor_id", "operation",
                "idempotency_key", "request_digest", "response_json",
                "response_digest", "created_at",
            ),
            "human_review_worker_capabilities": (
                "capability_id", "tenant_id", "project_id", "worker_id",
                "token_digest", "actions_json", "actions_digest", "expires_at",
                "revoked_at", "version", "created_by", "created_at",
            ),
            "human_review_propagation_tasks": (
                "propagation_id", "tenant_id", "project_id", "task_id",
                "decision_id", "correction_version", "channel", "direction",
                "payload_json", "payload_digest", "state", "claim_capability_id",
                "claim_owner_digest", "claim_fence", "claim_expires_at",
                "dispatch_started_at", "result_json", "result_digest",
                "failure_code", "reconciliation_required", "version", "created_at",
                "updated_at", "completed_at", "reconciled_at",
            ),
            "human_review_effective_projections": (
                "tenant_id", "project_id", "task_id", "channel",
                "source_decision_id", "correction_version", "direction",
                "target_kind", "target_json", "effective_value_json",
                "effective_value_digest", "source_digest", "version", "updated_at",
            ),
            "human_review_source_producer_capabilities": (
                "capability_id", "tenant_id", "project_id", "producer_id",
                "token_digest", "source_kinds_json", "source_kinds_digest",
                "expires_at", "revoked_at", "version", "created_by", "created_at",
            ),
            "human_review_source_snapshots": (
                "snapshot_id", "tenant_id", "project_id", "asset_id",
                "asset_version", "target_kind", "target_json", "target_digest",
                "original_value_json", "original_value_digest", "confidence",
                "asset_sha256", "source_digest", "provenance_json",
                "provenance_digest", "producer_capability_id", "producer_actor_id",
                "idempotency_key", "request_digest", "snapshot_digest", "created_at",
            ),
            "human_review_source_collection_generations": (
                "tenant_id", "project_id", "asset_id", "asset_version", "generation",
            ),
            "human_review_enqueue_preparations": (
                "preparation_id", "tenant_id", "project_id", "actor_id",
                "recovery_handle_digest", "execute_idempotency_key_digest",
                "enqueue_input_json", "enqueue_input_digest", "prepare_request_digest",
                "state", "expires_at", "prepared_at", "executed_at", "task_id",
            ),
            "human_review_target_heads": (
                "tenant_id", "project_id", "asset_id", "asset_version",
                "target_kind", "target_json", "target_digest", "base_snapshot_id",
                "current_value_json", "current_value_digest", "source_digest",
                "provenance_digest", "source_decision_id", "correction_version",
                "direction", "version", "updated_at",
            ),
            "human_review_target_head_reservations": (
                "reservation_id", "tenant_id", "project_id", "asset_id",
                "asset_version", "asset_content_digest", "asset_sha256",
                "target_kind", "target_digest", "snapshot_id",
                "snapshot_digest", "reserved_head_version",
                "reserved_head_value_digest", "task_id", "decision_id",
                "decision_action", "correction_version", "correction_digest",
                "source_digest", "source_ref_digest", "parent_reservation_id",
                "reservation_fence", "binding_digest", "state", "state_version",
                "materialized_head_version", "failure_code", "created_at",
                "updated_at", "completed_at",
            ),
        }
        integer_columns = {
            "current_correction_version", "effective_version", "claim_fence", "version",
            "correction_version", "parent_correction_version", "decision_version",
            "task_version", "reconciliation_required", "asset_version",
            "generation",
            "reserved_head_version", "reservation_fence", "state_version",
            "materialized_head_version",
        }
        nullable_columns = {
            "human_review_tasks": {
                "current_correction_digest", "effective_digest", "claim_actor_id",
                "claim_token_digest", "claim_expires_at", "closed_at",
            },
            "human_review_decisions": {
                "correction_version", "correction_digest",
            },
            "human_review_audit_log": {"prior_state", "next_state"},
            "human_review_worker_capabilities": {"revoked_at"},
            "human_review_source_producer_capabilities": {"revoked_at"},
            "human_review_enqueue_preparations": {"executed_at", "task_id"},
            "human_review_propagation_tasks": {
                "claim_capability_id", "claim_owner_digest", "claim_expires_at",
                "dispatch_started_at", "result_json", "result_digest", "failure_code",
                "completed_at", "reconciled_at",
            },
            "human_review_target_heads": {"source_decision_id"},
            "human_review_target_head_reservations": {
                "parent_reservation_id", "materialized_head_version",
                "failure_code", "completed_at",
            },
        }
        single_primary_keys = {
            "human_review_tasks": "task_id",
            "human_review_correction_versions": "correction_id",
            "human_review_decisions": "decision_id",
            "human_review_audit_log": "audit_id",
            "human_review_worker_capabilities": "capability_id",
            "human_review_propagation_tasks": "propagation_id",
            "human_review_source_producer_capabilities": "capability_id",
            "human_review_source_snapshots": "snapshot_id",
            "human_review_enqueue_preparations": "preparation_id",
            "human_review_target_head_reservations": "reservation_id",
        }
        composite_primary_keys = {
            "human_review_operation_receipts": {
                "tenant_id": 1, "project_id": 2, "actor_id": 3,
                "operation": 4, "idempotency_key": 5,
            },
            "human_review_effective_projections": {
                "tenant_id": 1, "project_id": 2, "task_id": 3, "channel": 4,
            },
            "human_review_source_collection_generations": {
                "tenant_id": 1, "project_id": 2, "asset_id": 3,
                "asset_version": 4,
            },
            "human_review_target_heads": {
                "tenant_id": 1, "project_id": 2, "asset_id": 3,
                "asset_version": 4, "target_kind": 5, "target_digest": 6,
            },
        }

        def normalize_sql(value: Any) -> str:
            return " ".join(value.strip().rstrip(";").split()).upper() if isinstance(value, str) else ""

        with self._lock:
            actual_table_sql = {
                str(row["name"]): normalize_sql(row["sql"])
                for row in self._connection.execute(
                    """SELECT name,sql FROM sqlite_master
                        WHERE type='table' AND name LIKE 'human_review_%'"""
                ).fetchall()
            }
            if actual_table_sql != expected_table_sql:
                raise IntegrityError("HUMAN_REVIEW_WORKFLOW_SCHEMA_INVALID")
            actual_index_sql = {
                str(row["name"]): normalize_sql(row["sql"])
                for row in self._connection.execute(
                    """SELECT name,sql FROM sqlite_master
                        WHERE type='index' AND name LIKE '%human_review%'
                          AND sql IS NOT NULL"""
                ).fetchall()
            }
            if actual_index_sql != expected_index_sql:
                raise IntegrityError("HUMAN_REVIEW_WORKFLOW_SCHEMA_INVALID")
            actual_trigger_sql = {
                str(row["name"]): normalize_sql(row["sql"])
                for row in self._connection.execute(
                    """SELECT name,sql FROM sqlite_master
                        WHERE type='trigger' AND name LIKE '%human_review%'"""
                ).fetchall()
            }
            if actual_trigger_sql != expected_trigger_sql:
                raise IntegrityError("HUMAN_REVIEW_WORKFLOW_IMMUTABILITY_INVALID")

            for table, expected_names in expected_columns.items():
                columns = self._connection.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
                if tuple(str(row["name"]) for row in columns) != expected_names:
                    raise IntegrityError("HUMAN_REVIEW_WORKFLOW_SCHEMA_INVALID")
                single_pk = single_primary_keys.get(table)
                composite_pk = composite_primary_keys.get(table, {})
                for row in columns:
                    name = str(row["name"])
                    expected_type = (
                        "REAL" if name == "confidence"
                        else "INTEGER" if name in integer_columns
                        else "TEXT"
                    )
                    expected_pk = 1 if name == single_pk else int(composite_pk.get(name, 0))
                    expected_notnull = (
                        0
                        if name == single_pk or name in nullable_columns.get(table, set())
                        else 1
                    )
                    if (
                        str(row["type"]).upper() != expected_type
                        or int(row["pk"]) != expected_pk
                        or int(row["notnull"]) != expected_notnull
                    ):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_SCHEMA_INVALID")

            expected_unique_indexes = {
                "human_review_tasks": {
                    ("task_id",),
                    ("tenant_id", "project_id", "task_id"),
                },
                "human_review_correction_versions": {
                    ("correction_id",),
                    ("tenant_id", "project_id", "correction_id"),
                    ("tenant_id", "project_id", "task_id", "correction_version"),
                },
                "human_review_decisions": {
                    ("decision_id",),
                    ("tenant_id", "project_id", "decision_id"),
                    ("tenant_id", "project_id", "task_id", "decision_version"),
                },
                "human_review_audit_log": {
                    ("audit_id",),
                    ("tenant_id", "project_id", "audit_id"),
                },
                "human_review_operation_receipts": {
                    ("tenant_id", "project_id", "actor_id", "operation", "idempotency_key"),
                },
                "human_review_worker_capabilities": {
                    ("capability_id",),
                    ("tenant_id", "project_id", "capability_id"),
                    ("tenant_id", "project_id", "worker_id", "token_digest"),
                },
                "human_review_propagation_tasks": {
                    ("propagation_id",),
                    ("tenant_id", "project_id", "propagation_id"),
                    ("tenant_id", "project_id", "decision_id", "channel"),
                },
                "human_review_effective_projections": {
                    ("tenant_id", "project_id", "task_id", "channel"),
                },
                "human_review_source_producer_capabilities": {
                    ("capability_id",),
                    ("tenant_id", "project_id", "capability_id"),
                    ("tenant_id", "project_id", "producer_id", "token_digest"),
                },
                "human_review_source_snapshots": {
                    ("snapshot_id",),
                    ("tenant_id", "project_id", "snapshot_id"),
                    (
                        "tenant_id", "project_id", "asset_id", "asset_version",
                        "target_kind", "target_digest",
                    ),
                    (
                        "tenant_id", "project_id", "producer_actor_id",
                        "idempotency_key",
                    ),
                },
                "human_review_source_collection_generations": {
                    ("tenant_id", "project_id", "asset_id", "asset_version"),
                },
                "human_review_enqueue_preparations": {
                    ("preparation_id",),
                    ("tenant_id", "project_id", "actor_id", "preparation_id"),
                    ("tenant_id", "project_id", "actor_id", "recovery_handle_digest"),
                },
                "human_review_target_heads": {
                    (
                        "tenant_id", "project_id", "asset_id", "asset_version",
                        "target_kind", "target_digest",
                    ),
                },
                "human_review_target_head_reservations": {
                    ("reservation_id",),
                    ("tenant_id", "project_id", "reservation_id"),
                    (
                        "tenant_id", "project_id", "asset_id", "asset_version",
                        "target_kind", "target_digest", "reserved_head_version",
                    ),
                    ("tenant_id", "project_id", "decision_id"),
                    ("tenant_id", "project_id", "parent_reservation_id"),
                },
            }
            for table, expected_unique in expected_unique_indexes.items():
                indexes = self._connection.execute(f"PRAGMA index_list({table})").fetchall()
                observed_unique: set[tuple[str, ...]] = set()
                for index in indexes:
                    if int(index["unique"]) != 1:
                        continue
                    index_name = str(index["name"]).replace('"', '""')
                    observed_unique.add(
                        tuple(
                            str(row["name"])
                            for row in self._connection.execute(
                                f'PRAGMA index_xinfo("{index_name}")'
                            ).fetchall()
                            if int(row["key"]) == 1
                        )
                    )
                if observed_unique != expected_unique:
                    raise IntegrityError("HUMAN_REVIEW_WORKFLOW_SCHEMA_INVALID")

            expected_foreign_keys = {
                "human_review_tasks": {
                    ("input_assets", "tenant_id", "tenant_id"),
                    ("input_assets", "project_id", "project_id"),
                    ("input_assets", "asset_id", "asset_id"),
                },
                "human_review_correction_versions": {
                    ("human_review_tasks", "tenant_id", "tenant_id"),
                    ("human_review_tasks", "project_id", "project_id"),
                    ("human_review_tasks", "task_id", "task_id"),
                },
                "human_review_decisions": {
                    ("human_review_tasks", "tenant_id", "tenant_id"),
                    ("human_review_tasks", "project_id", "project_id"),
                    ("human_review_tasks", "task_id", "task_id"),
                },
                "human_review_audit_log": {
                    ("human_review_tasks", "tenant_id", "tenant_id"),
                    ("human_review_tasks", "project_id", "project_id"),
                    ("human_review_tasks", "task_id", "task_id"),
                },
                "human_review_propagation_tasks": {
                    ("human_review_tasks", "tenant_id", "tenant_id"),
                    ("human_review_tasks", "project_id", "project_id"),
                    ("human_review_tasks", "task_id", "task_id"),
                    ("human_review_decisions", "tenant_id", "tenant_id"),
                    ("human_review_decisions", "project_id", "project_id"),
                    ("human_review_decisions", "decision_id", "decision_id"),
                    ("human_review_worker_capabilities", "tenant_id", "tenant_id"),
                    ("human_review_worker_capabilities", "project_id", "project_id"),
                    ("human_review_worker_capabilities", "claim_capability_id", "capability_id"),
                },
                "human_review_effective_projections": {
                    ("human_review_tasks", "tenant_id", "tenant_id"),
                    ("human_review_tasks", "project_id", "project_id"),
                    ("human_review_tasks", "task_id", "task_id"),
                    ("human_review_decisions", "tenant_id", "tenant_id"),
                    ("human_review_decisions", "project_id", "project_id"),
                    ("human_review_decisions", "source_decision_id", "decision_id"),
                },
                "human_review_target_head_reservations": {
                    ("human_review_tasks", "tenant_id", "tenant_id"),
                    ("human_review_tasks", "project_id", "project_id"),
                    ("human_review_tasks", "task_id", "task_id"),
                    ("human_review_correction_versions", "tenant_id", "tenant_id"),
                    ("human_review_correction_versions", "project_id", "project_id"),
                    ("human_review_correction_versions", "task_id", "task_id"),
                    (
                        "human_review_correction_versions",
                        "correction_version",
                        "correction_version",
                    ),
                    ("human_review_decisions", "tenant_id", "tenant_id"),
                    ("human_review_decisions", "project_id", "project_id"),
                    ("human_review_decisions", "decision_id", "decision_id"),
                    ("human_review_source_snapshots", "tenant_id", "tenant_id"),
                    ("human_review_source_snapshots", "project_id", "project_id"),
                    ("human_review_source_snapshots", "snapshot_id", "snapshot_id"),
                    ("human_review_target_heads", "tenant_id", "tenant_id"),
                    ("human_review_target_heads", "project_id", "project_id"),
                    ("human_review_target_heads", "asset_id", "asset_id"),
                    ("human_review_target_heads", "asset_version", "asset_version"),
                    ("human_review_target_heads", "target_kind", "target_kind"),
                    ("human_review_target_heads", "target_digest", "target_digest"),
                    (
                        "human_review_target_head_reservations",
                        "tenant_id",
                        "tenant_id",
                    ),
                    (
                        "human_review_target_head_reservations",
                        "project_id",
                        "project_id",
                    ),
                    (
                        "human_review_target_head_reservations",
                        "parent_reservation_id",
                        "reservation_id",
                    ),
                },
                "human_review_source_snapshots": {
                    ("input_assets", "tenant_id", "tenant_id"),
                    ("input_assets", "project_id", "project_id"),
                    ("input_assets", "asset_id", "asset_id"),
                    (
                        "human_review_source_producer_capabilities",
                        "tenant_id",
                        "tenant_id",
                    ),
                    (
                        "human_review_source_producer_capabilities",
                        "project_id",
                        "project_id",
                    ),
                    (
                        "human_review_source_producer_capabilities",
                        "producer_capability_id",
                        "capability_id",
                    ),
                },
                "human_review_source_collection_generations": {
                    ("input_assets", "tenant_id", "tenant_id"),
                    ("input_assets", "project_id", "project_id"),
                    ("input_assets", "asset_id", "asset_id"),
                },
                "human_review_enqueue_preparations": {
                    ("human_review_tasks", "tenant_id", "tenant_id"),
                    ("human_review_tasks", "project_id", "project_id"),
                    ("human_review_tasks", "task_id", "task_id"),
                },
                "human_review_target_heads": {
                    ("input_assets", "tenant_id", "tenant_id"),
                    ("input_assets", "project_id", "project_id"),
                    ("input_assets", "asset_id", "asset_id"),
                    ("human_review_source_snapshots", "tenant_id", "tenant_id"),
                    ("human_review_source_snapshots", "project_id", "project_id"),
                    (
                        "human_review_source_snapshots",
                        "base_snapshot_id",
                        "snapshot_id",
                    ),
                    ("human_review_decisions", "tenant_id", "tenant_id"),
                    ("human_review_decisions", "project_id", "project_id"),
                    ("human_review_decisions", "source_decision_id", "decision_id"),
                },
            }
            for table, expected in expected_foreign_keys.items():
                rows = self._connection.execute(f"PRAGMA foreign_key_list({table})").fetchall()
                observed = {
                    (str(row["table"]), str(row["from"]), str(row["to"])) for row in rows
                }
                if observed != expected or any(
                    str(row["on_update"]).upper() != "NO ACTION"
                    or str(row["on_delete"]).upper() != "NO ACTION"
                    for row in rows
                ):
                    raise IntegrityError("HUMAN_REVIEW_WORKFLOW_SCHEMA_INVALID")

            expected_indexes = {
                "human_review_tasks_queue_idx": (
                    "human_review_tasks", 0,
                    (("tenant_id", 0), ("project_id", 0), ("state", 0),
                     ("confidence", 0), ("created_at", 0), ("task_id", 0)),
                ),
                "human_review_tasks_asset_idx": (
                    "human_review_tasks", 0,
                    (("tenant_id", 0), ("project_id", 0), ("asset_id", 0),
                     ("target_kind", 0), ("state", 0), ("created_at", 0)),
                ),
                "human_review_correction_versions_task_idx": (
                    "human_review_correction_versions", 0,
                    (("tenant_id", 0), ("project_id", 0), ("task_id", 0),
                     ("correction_version", 1)),
                ),
                "human_review_decisions_task_idx": (
                    "human_review_decisions", 0,
                    (("tenant_id", 0), ("project_id", 0), ("task_id", 0),
                     ("decision_version", 1)),
                ),
                "human_review_audit_task_idx": (
                    "human_review_audit_log", 0,
                    (("tenant_id", 0), ("project_id", 0), ("task_id", 0),
                     ("occurred_at", 0), ("audit_id", 0)),
                ),
                "human_review_worker_capability_lookup_idx": (
                    "human_review_worker_capabilities", 1,
                    (("tenant_id", 0), ("project_id", 0), ("worker_id", 0),
                     ("capability_id", 0), ("expires_at", 0)),
                ),
                "human_review_propagation_pending_idx": (
                    "human_review_propagation_tasks", 0,
                    (("tenant_id", 0), ("project_id", 0), ("state", 0),
                     ("created_at", 0), ("propagation_id", 0)),
                ),
                "human_review_propagation_task_idx": (
                    "human_review_propagation_tasks", 0,
                    (("tenant_id", 0), ("project_id", 0), ("task_id", 0),
                     ("decision_id", 0), ("channel", 0)),
                ),
                "human_review_source_producer_capability_lookup_idx": (
                    "human_review_source_producer_capabilities", 1,
                    (("tenant_id", 0), ("project_id", 0), ("producer_id", 0),
                     ("capability_id", 0), ("expires_at", 0)),
                ),
                "human_review_source_snapshots_lookup_idx": (
                    "human_review_source_snapshots", 0,
                    (("tenant_id", 0), ("project_id", 0), ("asset_id", 0),
                     ("asset_version", 0), ("target_kind", 0),
                     ("target_digest", 0), ("created_at", 0)),
                ),
                "idx_human_review_enqueue_preparations_expiry": (
                    "human_review_enqueue_preparations", 0,
                    (("tenant_id", 0), ("project_id", 0), ("actor_id", 0),
                     ("expires_at", 0)),
                ),
                "human_review_target_heads_decision_idx": (
                    "human_review_target_heads", 1,
                    (("tenant_id", 0), ("project_id", 0),
                     ("source_decision_id", 0), ("updated_at", 0)),
                ),
                "human_review_target_head_reservations_task_idx": (
                    "human_review_target_head_reservations", 0,
                    (("tenant_id", 0), ("project_id", 0), ("task_id", 0),
                     ("created_at", 0), ("reservation_id", 0)),
                ),
                "human_review_target_head_reservations_state_idx": (
                    "human_review_target_head_reservations", 1,
                    (("tenant_id", 0), ("project_id", 0), ("state", 0),
                     ("updated_at", 0), ("reservation_id", 0)),
                ),
            }
            for name, (table, partial, expected_key) in expected_indexes.items():
                rows = self._connection.execute(f"PRAGMA index_list({table})").fetchall()
                descriptor = next((row for row in rows if row["name"] == name), None)
                if (
                    descriptor is None
                    or int(descriptor["unique"]) != 0
                    or int(descriptor["partial"]) != partial
                    or str(descriptor["origin"]) != "c"
                ):
                    raise IntegrityError("HUMAN_REVIEW_WORKFLOW_SCHEMA_INVALID")
                key_rows = self._connection.execute(
                    f'PRAGMA index_xinfo("{name}")'
                ).fetchall()
                observed_key = tuple(
                    (str(row["name"]), int(row["desc"]))
                    for row in key_rows if int(row["key"]) == 1
                )
                if observed_key != expected_key:
                    raise IntegrityError("HUMAN_REVIEW_WORKFLOW_SCHEMA_INVALID")

            state_queries = (
                """SELECT 1 FROM human_review_tasks WHERE
                    target_kind NOT IN ('TEXT','SPEAKER','TIME_RANGE','BBOX','TABLE','REQUIREMENT','CONFLICT')
                    OR state NOT IN ('QUEUED','CLAIMED','EDITED','APPROVED','REJECTED','REOPENED','REVERTING','REVERTED')
                    OR typeof(confidence) NOT IN ('real','integer') OR confidence<0 OR confidence>1
                    OR typeof(version)<>'integer' OR version<1 OR version>9007199254740991
                    OR typeof(current_correction_version)<>'integer' OR current_correction_version<0
                    OR (current_correction_version=0)<>(current_correction_digest IS NULL)
                    OR typeof(effective_version)<>'integer' OR effective_version<0
                    OR (claim_actor_id IS NULL)<>(claim_token_digest IS NULL)
                    OR (claim_actor_id IS NULL)<>(claim_expires_at IS NULL)
                    OR (state IN ('CLAIMED','EDITED'))<>(claim_actor_id IS NOT NULL)
                    LIMIT 1""",
                """SELECT 1 FROM human_review_correction_versions WHERE
                    correction_version<>parent_correction_version+1
                    OR correction_version<1 OR correction_version>9007199254740991
                    OR target_kind NOT IN ('TEXT','SPEAKER','TIME_RANGE','BBOX','TABLE','REQUIREMENT','CONFLICT')
                    LIMIT 1""",
                """SELECT 1 FROM human_review_decisions WHERE
                    decision NOT IN ('APPROVE','REJECT','REOPEN','REVERT')
                    OR decision_version<2 OR decision_version>9007199254740991 LIMIT 1""",
                """SELECT 1 FROM human_review_propagation_tasks WHERE
                    channel NOT IN ('content-index','requirements','project-memory','downstream')
                    OR direction NOT IN ('APPLY','REVERT')
                    OR state NOT IN ('PENDING','CLAIMED','SUCCEEDED','FAILED','UNKNOWN')
                    OR (claim_capability_id IS NULL)<>(claim_owner_digest IS NULL)
                    OR (claim_capability_id IS NULL)<>(claim_expires_at IS NULL)
                    OR (state='CLAIMED')<>(claim_capability_id IS NOT NULL)
                    OR (state='UNKNOWN')<>(reconciliation_required=1)
                    OR (result_json IS NULL)<>(result_digest IS NULL)
                    OR version<1 OR version>9007199254740991 LIMIT 1""",
                """SELECT 1 FROM human_review_effective_projections WHERE
                    channel NOT IN ('content-index','requirements','project-memory','downstream')
                    OR direction NOT IN ('APPLY','REVERT') OR correction_version<1
                    OR version<1 OR version>9007199254740991 LIMIT 1""",
                """SELECT 1 FROM human_review_source_producer_capabilities WHERE
                    typeof(version)<>'integer' OR version<1
                    OR version>9007199254740991 LIMIT 1""",
                """SELECT 1 FROM human_review_source_snapshots WHERE
                    target_kind NOT IN ('TEXT','SPEAKER','TIME_RANGE','BBOX','TABLE','REQUIREMENT','CONFLICT')
                    OR typeof(asset_version)<>'integer' OR asset_version<1
                    OR typeof(confidence) NOT IN ('real','integer')
                    OR confidence<0 OR confidence>1 LIMIT 1""",
                """SELECT 1 FROM human_review_enqueue_preparations WHERE
                    state NOT IN ('PREPARED','EXECUTED')
                    OR (state='PREPARED')<>(executed_at IS NULL AND task_id IS NULL)
                    OR (state='EXECUTED')<>(executed_at IS NOT NULL AND task_id IS NOT NULL)
                    OR length(recovery_handle_digest)<>64
                    OR length(execute_idempotency_key_digest)<>64
                    OR length(enqueue_input_digest)<>64
                    OR length(prepare_request_digest)<>64 LIMIT 1""",
                """SELECT 1 FROM human_review_target_heads WHERE
                    target_kind NOT IN ('TEXT','SPEAKER','TIME_RANGE','BBOX','TABLE','REQUIREMENT','CONFLICT')
                    OR direction NOT IN ('SNAPSHOT','APPLY','REVERT')
                    OR typeof(asset_version)<>'integer' OR asset_version<1
                    OR typeof(correction_version)<>'integer' OR correction_version<0
                    OR typeof(version)<>'integer' OR version<1
                    OR (direction='SNAPSHOT' AND
                        (source_decision_id IS NOT NULL OR correction_version<>0))
                    OR (direction IN ('APPLY','REVERT') AND source_decision_id IS NULL)
                    OR (direction='APPLY' AND correction_version<1)
                    LIMIT 1""",
                """SELECT 1 FROM human_review_target_head_reservations WHERE
                    target_kind NOT IN ('TEXT','SPEAKER','TIME_RANGE','BBOX','TABLE','REQUIREMENT','CONFLICT')
                    OR decision_action NOT IN ('APPROVE','REVERT')
                    OR state NOT IN ('PROPAGATING','UNKNOWN','FAILED','APPLIED','REVERTED')
                    OR typeof(asset_version)<>'integer' OR asset_version<1
                    OR typeof(reserved_head_version)<>'integer' OR reserved_head_version<1
                    OR typeof(reservation_fence)<>'integer'
                    OR reservation_fence<>reserved_head_version
                    OR typeof(correction_version)<>'integer' OR correction_version<1
                    OR typeof(state_version)<>'integer' OR state_version<1
                    OR (decision_action='APPROVE')<>(parent_reservation_id IS NULL)
                    OR (state IN ('PROPAGATING','UNKNOWN') AND
                        (materialized_head_version IS NOT NULL OR failure_code IS NOT NULL
                         OR completed_at IS NOT NULL))
                    OR (state='FAILED' AND
                        (materialized_head_version IS NOT NULL OR failure_code IS NULL
                         OR completed_at IS NULL))
                    OR (state='APPLIED' AND
                        (decision_action<>'APPROVE'
                         OR materialized_head_version<>reserved_head_version+1
                         OR failure_code IS NOT NULL OR completed_at IS NULL))
                    OR (state='REVERTED' AND
                        (decision_action<>'REVERT'
                         OR materialized_head_version<>reserved_head_version+1
                         OR failure_code IS NOT NULL OR completed_at IS NULL))
                    LIMIT 1""",
            )
            if any(self._connection.execute(query).fetchone() is not None for query in state_queries):
                raise IntegrityError("HUMAN_REVIEW_WORKFLOW_STATE_INVALID")

            def validate_json_value(value: Any, depth: int, remaining: list[int]) -> None:
                remaining[0] -= 1
                if remaining[0] < 0 or depth > 32:
                    raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                if value is None or isinstance(value, (str, bool)):
                    return
                if isinstance(value, int):
                    if abs(value) > MAX_SAFE_JSON_INTEGER:
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                    return
                if isinstance(value, float):
                    if not (-float("inf") < value < float("inf")):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                    return
                if isinstance(value, list):
                    for item in value:
                        validate_json_value(item, depth + 1, remaining)
                    return
                if isinstance(value, dict):
                    for key, item in value.items():
                        if not isinstance(key, str) or not key or len(key.encode("utf-8")) > 256:
                            raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                        validate_json_value(item, depth + 1, remaining)
                    return
                raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")

            def validate_json_columns(
                table: str,
                digest_pairs: tuple[tuple[str, str], ...],
                raw_columns: tuple[str, ...] = (),
            ) -> None:
                selected = tuple(dict.fromkeys(
                    [column for pair in digest_pairs for column in pair] + list(raw_columns)
                ))
                rows = self._connection.execute(
                    f"SELECT {','.join(selected)} FROM {table}"
                ).fetchall()
                for row in rows:
                    for json_column, digest_column in digest_pairs:
                        raw = row[json_column]
                        digest = row[digest_column]
                        if raw is None and digest is None:
                            continue
                        try:
                            if (
                                not isinstance(raw, str)
                                or not raw
                                or len(raw.encode("utf-8")) > 2 * 1024 * 1024
                                or not isinstance(digest, str)
                                or digest != normalize_sha256(digest)
                            ):
                                raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                            value = json.loads(raw)
                            validate_json_value(value, 0, [250_000])
                            rendered = content_contract_json(value)
                            observed = normalize_sha256(content_contract_digest(value))
                            expected = digest
                        except IntegrityError:
                            raise
                        except (TypeError, ValueError, UnicodeError, RecursionError, ValidationError) as error:
                            raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID") from error
                        if rendered != raw or not hmac.compare_digest(observed, expected):
                            raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                    for json_column in raw_columns:
                        raw = row[json_column]
                        try:
                            if (
                                not isinstance(raw, str)
                                or not raw
                                or len(raw.encode("utf-8")) > 2 * 1024 * 1024
                            ):
                                raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                            value = json.loads(raw)
                            validate_json_value(value, 0, [250_000])
                            if content_contract_json(value) != raw:
                                raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                        except IntegrityError:
                            raise
                        except (TypeError, ValueError, UnicodeError, RecursionError) as error:
                            raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID") from error

            def validate_digest_columns(table: str, columns: tuple[str, ...]) -> None:
                rows = self._connection.execute(
                    f"SELECT {','.join(columns)} FROM {table}"
                ).fetchall()
                for row in rows:
                    for column in columns:
                        digest = row[column]
                        if digest is None:
                            continue
                        try:
                            if (
                                not isinstance(digest, str)
                                or digest != normalize_sha256(digest)
                            ):
                                raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                        except ValidationError as error:
                            raise IntegrityError(
                                "HUMAN_REVIEW_WORKFLOW_ROW_INVALID"
                            ) from error

            def validate_target_rows(table: str) -> None:
                rows = self._connection.execute(
                    f"SELECT target_kind,target_json FROM {table}"
                ).fetchall()
                for row in rows:
                    try:
                        kind = str(row["target_kind"])
                        target = json.loads(row["target_json"])
                        fields = set(target) if isinstance(target, dict) else set()
                        if kind == "TEXT":
                            valid = (
                                fields == {"path"}
                                and isinstance(target.get("path"), str)
                                and bool(target["path"].strip())
                                and target["path"] == target["path"].strip()
                                and len(target["path"].encode("utf-8")) <= 1_024
                            )
                        elif kind == "SPEAKER":
                            valid = fields == {"segment_id"}
                            if valid:
                                require_resource_id(target["segment_id"], "segment_id")
                        elif kind == "TIME_RANGE":
                            valid = fields == {"start_ms", "end_ms"}
                            if valid:
                                start, end = target["start_ms"], target["end_ms"]
                                valid = (
                                    isinstance(start, int)
                                    and not isinstance(start, bool)
                                    and isinstance(end, int)
                                    and not isinstance(end, bool)
                                    and 0 <= start <= end <= MAX_SAFE_JSON_INTEGER - 1
                                )
                        elif kind == "BBOX":
                            valid = fields == {"page", "x", "y", "width", "height"}
                            if valid:
                                page = target["page"]
                                valid = (
                                    isinstance(page, int)
                                    and not isinstance(page, bool)
                                    and 1 <= page <= MAX_SAFE_JSON_INTEGER - 1
                                    and all(
                                        isinstance(target[field], (int, float))
                                        and not isinstance(target[field], bool)
                                        and -float("inf") < float(target[field]) < float("inf")
                                        and target[field] >= 0
                                        and (field not in {"width", "height"} or target[field] > 0)
                                        for field in ("x", "y", "width", "height")
                                    )
                                )
                        elif kind == "TABLE":
                            valid = fields == {"table_id", "row", "column"}
                            if valid:
                                require_resource_id(target["table_id"], "table_id")
                                valid = all(
                                    isinstance(target[field], int)
                                    and not isinstance(target[field], bool)
                                    and 0 <= target[field] <= MAX_SAFE_JSON_INTEGER - 1
                                    for field in ("row", "column")
                                )
                        elif kind == "REQUIREMENT":
                            valid = fields == {"requirement_id"}
                            if valid:
                                require_resource_id(target["requirement_id"], "requirement_id")
                        elif kind == "CONFLICT":
                            valid = fields == {"conflict_id"}
                            if valid:
                                require_resource_id(target["conflict_id"], "conflict_id")
                        else:
                            valid = False
                    except (TypeError, ValueError, UnicodeError, ValidationError):
                        valid = False
                    if not valid:
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")

            validate_json_columns(
                "human_review_tasks",
                (("target_json", "target_digest"),
                 ("original_value_json", "original_value_digest"),
                 ("source_ref_json", "source_ref_digest")),
            )
            validate_json_columns(
                "human_review_correction_versions",
                (("original_value_json", "original_value_digest"),
                 ("corrected_value_json", "corrected_value_digest")),
                ("target_json",),
            )
            validate_json_columns(
                "human_review_audit_log", (("details_json", "details_digest"),)
            )
            validate_json_columns(
                "human_review_operation_receipts",
                (("response_json", "response_digest"),),
            )
            validate_json_columns(
                "human_review_worker_capabilities", (("actions_json", "actions_digest"),)
            )
            validate_json_columns(
                "human_review_propagation_tasks",
                (("payload_json", "payload_digest"), ("result_json", "result_digest")),
            )
            validate_json_columns(
                "human_review_effective_projections",
                (("effective_value_json", "effective_value_digest"),),
                ("target_json",),
            )
            validate_json_columns(
                "human_review_source_producer_capabilities",
                (("source_kinds_json", "source_kinds_digest"),),
            )
            validate_json_columns(
                "human_review_source_snapshots",
                (("target_json", "target_digest"),
                 ("original_value_json", "original_value_digest"),
                 ("provenance_json", "provenance_digest")),
            )
            validate_json_columns(
                "human_review_target_heads",
                (("target_json", "target_digest"),
                 ("current_value_json", "current_value_digest")),
            )
            validate_digest_columns(
                "human_review_tasks",
                (
                    "target_digest", "original_value_digest", "source_digest",
                    "source_ref_digest", "current_correction_digest", "effective_digest",
                    "claim_token_digest",
                ),
            )
            validate_digest_columns(
                "human_review_correction_versions",
                (
                    "original_value_digest", "corrected_value_digest", "source_digest",
                    "correction_digest", "request_digest",
                ),
            )
            validate_digest_columns(
                "human_review_decisions",
                ("correction_digest", "source_digest", "request_digest"),
            )
            validate_digest_columns(
                "human_review_audit_log", ("details_digest",)
            )
            validate_digest_columns(
                "human_review_operation_receipts",
                ("request_digest", "response_digest"),
            )
            validate_digest_columns(
                "human_review_worker_capabilities",
                ("token_digest", "actions_digest"),
            )
            validate_digest_columns(
                "human_review_propagation_tasks",
                ("payload_digest", "claim_owner_digest", "result_digest"),
            )
            validate_digest_columns(
                "human_review_effective_projections",
                ("effective_value_digest", "source_digest"),
            )
            validate_digest_columns(
                "human_review_source_producer_capabilities",
                ("token_digest", "source_kinds_digest"),
            )
            validate_digest_columns(
                "human_review_source_snapshots",
                (
                    "target_digest", "original_value_digest", "asset_sha256",
                    "source_digest", "provenance_digest", "request_digest",
                    "snapshot_digest",
                ),
            )
            validate_digest_columns(
                "human_review_target_heads",
                (
                    "target_digest", "current_value_digest", "source_digest",
                    "provenance_digest",
                ),
            )
            validate_digest_columns(
                "human_review_target_head_reservations",
                (
                    "asset_content_digest", "asset_sha256", "target_digest",
                    "snapshot_digest", "reserved_head_value_digest",
                    "correction_digest", "source_digest", "source_ref_digest",
                    "binding_digest",
                ),
            )
            for target_table in (
                "human_review_tasks",
                "human_review_correction_versions",
                "human_review_effective_projections",
                "human_review_source_snapshots",
                "human_review_target_heads",
            ):
                validate_target_rows(target_table)

            reservation_rows = self._connection.execute(
                "SELECT * FROM human_review_target_head_reservations"
            ).fetchall()
            for reservation in reservation_rows:
                try:
                    reservation_id = require_resource_id(
                        reservation["reservation_id"], "reservation_id"
                    )
                    parent_id = (
                        require_resource_id(
                            reservation["parent_reservation_id"], "reservation_id"
                        )
                        if reservation["parent_reservation_id"] is not None
                        else None
                    )
                    binding = {
                        "schema_version": "human-review-target-head-reservation-binding-v1",
                        "tenant_id": require_resource_id(
                            reservation["tenant_id"], "tenant_id"
                        ),
                        "project_id": require_resource_id(
                            reservation["project_id"], "project_id"
                        ),
                        "asset_id": require_resource_id(
                            reservation["asset_id"], "asset_id"
                        ),
                        "asset_version": int(reservation["asset_version"]),
                        "asset_content_digest": (
                            f"sha256:{normalize_sha256(reservation['asset_content_digest'])}"
                        ),
                        "asset_sha256": (
                            f"sha256:{normalize_sha256(reservation['asset_sha256'])}"
                        ),
                        "target_kind": ReviewTargetKind(
                            reservation["target_kind"]
                        ).value,
                        "target_digest": (
                            f"sha256:{normalize_sha256(reservation['target_digest'])}"
                        ),
                        "snapshot_id": require_resource_id(
                            reservation["snapshot_id"], "snapshot_id"
                        ),
                        "snapshot_digest": (
                            f"sha256:{normalize_sha256(reservation['snapshot_digest'])}"
                        ),
                        "reserved_head_version": int(
                            reservation["reserved_head_version"]
                        ),
                        "reserved_head_value_digest": (
                            "sha256:"
                            + normalize_sha256(
                                reservation["reserved_head_value_digest"]
                            )
                        ),
                        "task_id": require_resource_id(
                            reservation["task_id"], "task_id"
                        ),
                        "decision_id": require_resource_id(
                            reservation["decision_id"], "decision_id"
                        ),
                        "decision_action": str(reservation["decision_action"]),
                        "correction_version": int(
                            reservation["correction_version"]
                        ),
                        "correction_digest": (
                            f"sha256:{normalize_sha256(reservation['correction_digest'])}"
                        ),
                        "source_digest": (
                            f"sha256:{normalize_sha256(reservation['source_digest'])}"
                        ),
                        "source_ref_digest": (
                            f"sha256:{normalize_sha256(reservation['source_ref_digest'])}"
                        ),
                        "parent_reservation_id": parent_id,
                        "reservation_fence": int(reservation["reservation_fence"]),
                    }
                    expected_binding = normalize_sha256(canonical_digest(binding))
                    if (
                        not hmac.compare_digest(
                            expected_binding,
                            normalize_sha256(reservation["binding_digest"]),
                        )
                        or reservation_id
                        != "review-reservation-" + expected_binding[:32]
                    ):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                except IntegrityError:
                    raise
                except (TypeError, ValueError, ValidationError) as error:
                    raise IntegrityError(
                        "HUMAN_REVIEW_WORKFLOW_ROW_INVALID"
                    ) from error

            source_kinds = {
                "CONTENT_BLOCK", "SOURCE_ANCHOR", "REQUIREMENT", "CONFLICT",
                "TRUSTED_DERIVATION", "WHOLE_ASSET",
            }
            provenance_fields = {
                "schema_version", "source_kind", "source_id", "source_digest",
                "producer_version",
            }
            source_ref_v2_fields = {
                "schema_version", "content_id", "content_version",
                "content_digest", "asset_sha256", "target_kind",
                "target_digest", "snapshot_id", "snapshot_digest",
                "head_version", "head_value_digest", "source_digest",
                "provenance_digest", "original_value_client_digest",
                "original_value_digest_contract",
            }
            producer_rows = self._connection.execute(
                "SELECT * FROM human_review_source_producer_capabilities"
            ).fetchall()
            for producer in producer_rows:
                try:
                    require_resource_id(producer["capability_id"], "capability_id")
                    require_actor_id(producer["producer_id"])
                    require_actor_id(producer["created_by"])
                    allowed_kinds = json.loads(producer["source_kinds_json"])
                    expires_at = datetime.fromisoformat(producer["expires_at"])
                    created_at = datetime.fromisoformat(producer["created_at"])
                    revoked_at = (
                        datetime.fromisoformat(producer["revoked_at"])
                        if producer["revoked_at"] is not None
                        else None
                    )
                    canonical_expiry = expires_at.astimezone(UTC).replace(
                        microsecond=0
                    ).isoformat()
                    canonical_created = created_at.astimezone(UTC).replace(
                        microsecond=0
                    ).isoformat()
                    canonical_revoked = (
                        revoked_at.astimezone(UTC).replace(microsecond=0).isoformat()
                        if revoked_at is not None
                        else None
                    )
                    if (
                        not isinstance(allowed_kinds, list)
                        or not allowed_kinds
                        or allowed_kinds != sorted(set(allowed_kinds))
                        or not set(allowed_kinds) <= source_kinds
                        or expires_at.tzinfo is None
                        or expires_at.utcoffset() is None
                        or created_at.tzinfo is None
                        or created_at.utcoffset() is None
                        or canonical_expiry != producer["expires_at"]
                        or canonical_created != producer["created_at"]
                        or expires_at <= created_at
                        or (
                            revoked_at is None and int(producer["version"]) != 1
                        )
                        or (
                            revoked_at is not None
                            and (
                                revoked_at.tzinfo is None
                                or revoked_at.utcoffset() is None
                                or canonical_revoked != producer["revoked_at"]
                                or revoked_at < created_at
                                or int(producer["version"]) != 2
                            )
                        )
                    ):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                except IntegrityError:
                    raise
                except (TypeError, ValueError, UnicodeError, ValidationError) as error:
                    raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID") from error
            snapshot_rows = self._connection.execute(
                "SELECT * FROM human_review_source_snapshots"
            ).fetchall()
            snapshots: dict[str, sqlite3.Row] = {}
            for row in snapshot_rows:
                try:
                    snapshot_id = require_resource_id(row["snapshot_id"], "snapshot_id")
                    require_actor_id(row["producer_actor_id"])
                    require_idempotency_key(row["idempotency_key"])
                    target = json.loads(row["target_json"])
                    original_value = json.loads(row["original_value_json"])
                    provenance = json.loads(row["provenance_json"])
                    if (
                        not isinstance(provenance, dict)
                        or set(provenance) != provenance_fields
                        or provenance.get("schema_version")
                        != "human-review-source-provenance-v1"
                        or provenance.get("source_kind") not in source_kinds
                        or not isinstance(provenance.get("producer_version"), str)
                        or not provenance["producer_version"].strip()
                        or len(provenance["producer_version"].encode("utf-8")) > 256
                    ):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                    provenance_source_id = provenance.get("source_id")
                    provenance_digest_value = provenance.get("source_digest")
                    if (
                        not isinstance(provenance_source_id, str)
                        or not isinstance(provenance_digest_value, str)
                    ):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                    require_resource_id(provenance_source_id, "source_id")
                    provenance_source_digest = normalize_sha256(provenance_digest_value)
                    if not hmac.compare_digest(
                        provenance_source_digest, normalize_sha256(row["source_digest"])
                    ):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                    asset = self._connection.execute(
                        """SELECT sha256,version FROM input_assets
                            WHERE tenant_id=? AND project_id=? AND asset_id=?""",
                        (row["tenant_id"], row["project_id"], row["asset_id"]),
                    ).fetchone()
                    producer = self._connection.execute(
                        """SELECT producer_id,source_kinds_json,created_by,
                                  created_at,expires_at,revoked_at
                            FROM human_review_source_producer_capabilities
                            WHERE tenant_id=? AND project_id=? AND capability_id=?""",
                        (
                            row["tenant_id"], row["project_id"],
                            row["producer_capability_id"],
                        ),
                    ).fetchone()
                    snapshot_created_at = datetime.fromisoformat(row["created_at"])
                    producer_created_at = (
                        datetime.fromisoformat(producer["created_at"])
                        if producer is not None
                        else None
                    )
                    producer_expires_at = (
                        datetime.fromisoformat(producer["expires_at"])
                        if producer is not None
                        else None
                    )
                    producer_revoked_at = (
                        datetime.fromisoformat(producer["revoked_at"])
                        if producer is not None and producer["revoked_at"] is not None
                        else None
                    )
                    if (
                        asset is None
                        or producer is None
                        or producer_created_at is None
                        or producer_expires_at is None
                        or snapshot_created_at.tzinfo is None
                        or snapshot_created_at.utcoffset() is None
                        or snapshot_created_at.isoformat() != row["created_at"]
                        or producer_created_at.tzinfo is None
                        or producer_created_at.utcoffset() is None
                        or producer_created_at.isoformat() != producer["created_at"]
                        or producer_expires_at.tzinfo is None
                        or producer_expires_at.utcoffset() is None
                        or producer_expires_at.isoformat() != producer["expires_at"]
                        or snapshot_created_at < producer_created_at
                        or snapshot_created_at >= producer_expires_at
                        or (
                            producer_revoked_at is not None
                            and (
                                producer_revoked_at.tzinfo is None
                                or producer_revoked_at.utcoffset() is None
                                or producer_revoked_at.isoformat()
                                != producer["revoked_at"]
                                or snapshot_created_at > producer_revoked_at
                            )
                        )
                        or producer["producer_id"] != row["producer_actor_id"]
                        or provenance["source_kind"]
                        not in json.loads(producer["source_kinds_json"])
                        or int(asset["version"]) < int(row["asset_version"])
                        or not hmac.compare_digest(
                            normalize_sha256(asset["sha256"]),
                            normalize_sha256(row["asset_sha256"]),
                        )
                    ):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                    snapshot_body = {
                        "schema_version": "human-review-source-snapshot-v1",
                        "snapshot_id": snapshot_id,
                        "tenant_id": row["tenant_id"],
                        "project_id": row["project_id"],
                        "asset_id": row["asset_id"],
                        "asset_version": int(row["asset_version"]),
                        "target_kind": row["target_kind"],
                        "target": target,
                        "original_value": original_value,
                        "confidence": float(row["confidence"]),
                        "asset_sha256": (
                            f"sha256:{normalize_sha256(row['asset_sha256'])}"
                        ),
                        "source_digest": (
                            f"sha256:{normalize_sha256(row['source_digest'])}"
                        ),
                        "provenance": provenance,
                        "producer_capability_id": row["producer_capability_id"],
                        "producer_actor_id": row["producer_actor_id"],
                        "idempotency_key": row["idempotency_key"],
                        "request_digest": (
                            f"sha256:{normalize_sha256(row['request_digest'])}"
                        ),
                        "created_at": row["created_at"],
                    }
                    if not hmac.compare_digest(
                        normalize_sha256(content_contract_digest(snapshot_body)),
                        normalize_sha256(row["snapshot_digest"]),
                    ):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                    if (
                        row["producer_actor_id"]
                        == self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER
                    ):
                        correction_row = self._connection.execute(
                            """SELECT * FROM human_review_corrections
                                WHERE tenant_id=? AND project_id=?
                                  AND correction_id=?""",
                            (
                                row["tenant_id"],
                                row["project_id"],
                                provenance["source_id"],
                            ),
                        ).fetchone()
                        if correction_row is None:
                            raise IntegrityError(
                                "HUMAN_REVIEW_WORKFLOW_ROW_INVALID"
                            )
                        try:
                            correction_document = self._human_review_correction(
                                correction_row
                            )
                            source_fact = self._human_review_correction_source_fact(
                                correction_id=correction_row["correction_id"],
                                correction_document=correction_document,
                                correction_digest=correction_row["correction_digest"],
                                source_version=int(correction_row["source_version"]),
                                asset_version=int(correction_row["version"]),
                            )
                            expected_target_json = content_contract_json(
                                source_fact["target"]
                            )
                            expected_original_json = content_contract_json(
                                source_fact["original_value"]
                            )
                            expected_source_digest = canonical_digest(source_fact)
                        except (
                            IntegrityError,
                            TypeError,
                            ValueError,
                            UnicodeError,
                            RecursionError,
                            ValidationError,
                        ) as error:
                            raise IntegrityError(
                                "HUMAN_REVIEW_WORKFLOW_ROW_INVALID"
                            ) from error
                        if (
                            producer["created_by"]
                            != self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER
                            or provenance["source_kind"]
                            != self._HUMAN_REVIEW_CORRECTION_SOURCE_KIND
                            or provenance["producer_version"]
                            != self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER_VERSION
                            or row["asset_id"] != correction_row["asset_id"]
                            or int(row["asset_version"])
                            != int(correction_row["version"])
                            or row["target_kind"] != ReviewTargetKind.TEXT.value
                            or row["target_json"] != expected_target_json
                            or row["original_value_json"] != expected_original_json
                            or float(row["confidence"])
                            != self._HUMAN_REVIEW_CORRECTION_SOURCE_CONFIDENCE
                            or row["created_at"] != correction_row["created_at"]
                            or not hmac.compare_digest(
                                normalize_sha256(row["source_digest"]),
                                expected_source_digest,
                            )
                        ):
                            raise IntegrityError(
                                "HUMAN_REVIEW_WORKFLOW_ROW_INVALID"
                            )
                except IntegrityError:
                    raise
                except (TypeError, ValueError, UnicodeError, ValidationError) as error:
                    raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID") from error
                snapshots[snapshot_id] = row

            head_rows = self._connection.execute(
                "SELECT * FROM human_review_target_heads"
            ).fetchall()
            generation_rows = self._connection.execute(
                "SELECT * FROM human_review_source_collection_generations"
            ).fetchall()
            generation_keys = {
                (
                    row["tenant_id"], row["project_id"], row["asset_id"],
                    int(row["asset_version"]),
                )
                for row in generation_rows
                if int(row["generation"]) >= 1
            }
            head_generation_keys = {
                (
                    row["tenant_id"], row["project_id"], row["asset_id"],
                    int(row["asset_version"]),
                )
                for row in head_rows
            }
            if (
                len(generation_keys) != len(generation_rows)
                or generation_keys != head_generation_keys
            ):
                raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
            heads = {
                (
                    row["tenant_id"], row["project_id"], row["asset_id"],
                    int(row["asset_version"]), row["target_kind"],
                    normalize_sha256(row["target_digest"]),
                ): row
                for row in head_rows
            }
            task_rows = self._connection.execute(
                "SELECT * FROM human_review_tasks"
            ).fetchall()
            for task in task_rows:
                try:
                    source_ref = json.loads(task["source_ref_json"])
                    original_value = json.loads(task["original_value_json"])
                    if (
                        not isinstance(source_ref, dict)
                        or set(source_ref) != source_ref_v2_fields
                        or source_ref.get("schema_version")
                        != "human-review-source-ref-v2"
                        or source_ref.get("content_id") != task["asset_id"]
                        or source_ref.get("target_kind") != task["target_kind"]
                        or source_ref.get("original_value_digest_contract")
                        != CANONICAL_JSON_SHA256_CONTRACT
                    ):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                    content_version = source_ref.get("content_version")
                    head_version = source_ref.get("head_version")
                    if (
                        isinstance(content_version, bool)
                        or not isinstance(content_version, int)
                        or content_version < 1
                        or isinstance(head_version, bool)
                        or not isinstance(head_version, int)
                        or head_version < 1
                    ):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                    target_digest = normalize_sha256(task["target_digest"])
                    snapshot_digest = normalize_sha256(source_ref["snapshot_digest"])
                    head_value_digest = normalize_sha256(
                        source_ref["head_value_digest"]
                    )
                    client_value_digest = normalize_sha256(
                        source_ref["original_value_client_digest"]
                    )
                    snapshot = snapshots.get(
                        require_resource_id(source_ref["snapshot_id"], "snapshot_id")
                    )
                    head = heads.get(
                        (
                            task["tenant_id"], task["project_id"], task["asset_id"],
                            content_version, task["target_kind"], target_digest,
                        )
                    )
                    if (
                        snapshot is None
                        or head is None
                        or snapshot["tenant_id"] != task["tenant_id"]
                        or snapshot["project_id"] != task["project_id"]
                        or snapshot["asset_id"] != task["asset_id"]
                        or int(snapshot["asset_version"]) != content_version
                        or snapshot["target_kind"] != task["target_kind"]
                        or snapshot["target_json"] != task["target_json"]
                        or source_ref["snapshot_id"] != head["base_snapshot_id"]
                        or source_ref["asset_sha256"]
                        != f"sha256:{normalize_sha256(snapshot['asset_sha256'])}"
                        or normalize_sha256(source_ref["target_digest"])
                        != target_digest
                        or not hmac.compare_digest(
                            snapshot_digest,
                            normalize_sha256(snapshot["snapshot_digest"]),
                        )
                        or not hmac.compare_digest(
                            head_value_digest,
                            normalize_sha256(task["original_value_digest"]),
                        )
                        or not hmac.compare_digest(
                            client_value_digest, canonical_digest(original_value)
                        )
                        or normalize_sha256(source_ref["source_digest"])
                        != normalize_sha256(snapshot["source_digest"])
                        or normalize_sha256(source_ref["provenance_digest"])
                        != normalize_sha256(snapshot["provenance_digest"])
                        or int(head["version"]) < head_version
                        or (
                            int(head["version"]) == head_version
                            and normalize_sha256(head["current_value_digest"])
                            != head_value_digest
                        )
                    ):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                    normalize_sha256(source_ref["content_digest"])
                except IntegrityError:
                    raise
                except (
                    KeyError, TypeError, ValueError, UnicodeError,
                    RecursionError, ValidationError,
                ) as error:
                    raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID") from error
            for head in head_rows:
                try:
                    snapshot = snapshots.get(str(head["base_snapshot_id"]))
                    if snapshot is None:
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                    if (
                        snapshot["tenant_id"] != head["tenant_id"]
                        or snapshot["project_id"] != head["project_id"]
                        or snapshot["asset_id"] != head["asset_id"]
                        or int(snapshot["asset_version"]) != int(head["asset_version"])
                        or snapshot["target_kind"] != head["target_kind"]
                        or snapshot["target_json"] != head["target_json"]
                        or not hmac.compare_digest(
                            normalize_sha256(snapshot["target_digest"]),
                            normalize_sha256(head["target_digest"]),
                        )
                        or not hmac.compare_digest(
                            normalize_sha256(snapshot["source_digest"]),
                            normalize_sha256(head["source_digest"]),
                        )
                        or not hmac.compare_digest(
                            normalize_sha256(snapshot["provenance_digest"]),
                            normalize_sha256(head["provenance_digest"]),
                        )
                    ):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                    if head["direction"] == "SNAPSHOT":
                        if (
                            head["source_decision_id"] is not None
                            or int(head["correction_version"]) != 0
                            or head["current_value_json"]
                            != snapshot["original_value_json"]
                            or not hmac.compare_digest(
                                normalize_sha256(head["current_value_digest"]),
                                normalize_sha256(snapshot["original_value_digest"]),
                            )
                        ):
                            raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                        continue
                    decision = self._connection.execute(
                        """SELECT * FROM human_review_decisions
                            WHERE tenant_id=? AND project_id=? AND decision_id=?""",
                        (
                            head["tenant_id"], head["project_id"],
                            head["source_decision_id"],
                        ),
                    ).fetchone()
                    task = (
                        self._connection.execute(
                            """SELECT * FROM human_review_tasks
                                WHERE tenant_id=? AND project_id=? AND task_id=?""",
                            (
                                head["tenant_id"], head["project_id"],
                                decision["task_id"],
                            ),
                        ).fetchone()
                        if decision is not None
                        else None
                    )
                    expected_decision = (
                        "APPROVE" if head["direction"] == "APPLY" else "REVERT"
                    )
                    if (
                        decision is None
                        or task is None
                        or decision["decision"] != expected_decision
                        or task["asset_id"] != head["asset_id"]
                        or task["target_kind"] != head["target_kind"]
                        or task["target_json"] != head["target_json"]
                        or not hmac.compare_digest(
                            normalize_sha256(task["target_digest"]),
                            normalize_sha256(head["target_digest"]),
                        )
                    ):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                    source_ref = json.loads(task["source_ref_json"])
                    if (
                        not isinstance(source_ref, dict)
                        or source_ref.get("schema_version")
                        != "human-review-source-ref-v2"
                        or source_ref.get("snapshot_id") != head["base_snapshot_id"]
                        or int(source_ref.get("content_version", -1))
                        != int(head["asset_version"])
                    ):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                    projections = self._connection.execute(
                        """SELECT channel,effective_value_json,effective_value_digest,
                                  correction_version,direction
                            FROM human_review_effective_projections
                            WHERE tenant_id=? AND project_id=? AND task_id=?
                              AND source_decision_id=?""",
                        (
                            head["tenant_id"], head["project_id"], task["task_id"],
                            head["source_decision_id"],
                        ),
                    ).fetchall()
                    if (
                        len(projections) != 4
                        or {row["channel"] for row in projections}
                        != {"content-index", "requirements", "project-memory", "downstream"}
                        or any(
                            row["effective_value_json"] != head["current_value_json"]
                            or not hmac.compare_digest(
                                normalize_sha256(row["effective_value_digest"]),
                                normalize_sha256(head["current_value_digest"]),
                            )
                            or int(row["correction_version"])
                            != int(decision["correction_version"])
                            or row["direction"] != head["direction"]
                            for row in projections
                        )
                    ):
                        raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID")
                except IntegrityError:
                    raise
                except (TypeError, ValueError, UnicodeError, ValidationError) as error:
                    raise IntegrityError("HUMAN_REVIEW_WORKFLOW_ROW_INVALID") from error

    def get_archive_expansion_context(
        self,
        *,
        tenant_id: str,
        project_id: str,
        parent_archive_digest: str,
        parent_entry_digest: str,
        parent_entry_receipt_digest: str,
        parent_generation_digest: str,
    ) -> dict[str, Any]:
        """Resolve a nested archive only through a published, scope-bound parent entry."""

        safe_tenant = require_resource_id(tenant_id, "tenant_id")
        safe_project = require_resource_id(project_id, "project_id")
        parent_archive = normalize_sha256(parent_archive_digest)
        parent_entry = normalize_sha256(parent_entry_digest)
        parent_receipt = normalize_sha256(parent_entry_receipt_digest)
        parent_generation = normalize_sha256(parent_generation_digest)
        with self._lock:
            row = self._connection.execute(
                """
                SELECT node.node_digest, node.root_archive_digest, node.depth,
                       root.policy_digest, root.max_total_uncompressed_bytes,
                       root.max_entries, root.max_nested_depth,
                       root.consumed_uncompressed_bytes, root.consumed_entries,
                       root.version,
                       child.node_digest AS existing_child_node_digest
                  FROM archive_expansion_entries AS entry
                  JOIN archive_expansion_nodes AS node
                    ON node.tenant_id = entry.tenant_id
                   AND node.project_id = entry.project_id
                   AND node.node_digest = entry.node_digest
                  JOIN archive_expansion_roots AS root
                    ON root.tenant_id = node.tenant_id
                   AND root.project_id = node.project_id
                   AND root.root_archive_digest = node.root_archive_digest
                  LEFT JOIN archive_expansion_nodes AS child
                    ON child.tenant_id = entry.tenant_id
                   AND child.project_id = entry.project_id
                   AND child.parent_node_digest = node.node_digest
                   AND child.parent_entry_receipt_digest = entry.entry_receipt_digest
                 WHERE entry.tenant_id = ? AND entry.project_id = ?
                   AND node.archive_digest = ?
                   AND entry.entry_digest = ?
                   AND entry.entry_receipt_digest = ?
                   AND entry.generation_digest = ?
                   AND entry.nested_container IS NOT NULL
                   AND node.state = 'PUBLISHED'
                """,
                (
                    safe_tenant,
                    safe_project,
                    parent_archive,
                    parent_entry,
                    parent_receipt,
                    parent_generation,
                ),
            ).fetchone()
        if row is None:
            raise IntegrityError("ARCHIVE_PARENT_LINEAGE_INVALID")
        return {
            "parent_node_digest": str(row["node_digest"]),
            "root_archive_digest": str(row["root_archive_digest"]),
            "depth": int(row["depth"]) + 1,
            "policy_digest": str(row["policy_digest"]),
            "max_total_uncompressed_bytes": int(row["max_total_uncompressed_bytes"]),
            "max_entries": int(row["max_entries"]),
            "max_nested_depth": int(row["max_nested_depth"]),
            "consumed_uncompressed_bytes": int(row["consumed_uncompressed_bytes"]),
            "consumed_entries": int(row["consumed_entries"]),
            "budget_version": int(row["version"]),
            "existing_child_node_digest": row["existing_child_node_digest"],
        }

    def reserve_archive_expansion(
        self,
        *,
        tenant_id: str,
        project_id: str,
        archive_digest: str,
        policy_digest: str,
        max_total_uncompressed_bytes: int,
        max_entries: int,
        max_nested_depth: int,
        expanded_uncompressed_bytes: int,
        expanded_entries: int,
        request_digest: str,
        parent: Mapping[str, str] | None,
    ) -> dict[str, Any]:
        """Atomically charge one expansion against its persistent global root budget."""

        safe_tenant = require_resource_id(tenant_id, "tenant_id")
        safe_project = require_resource_id(project_id, "project_id")
        archive = normalize_sha256(archive_digest)
        policy = normalize_sha256(policy_digest)
        request = normalize_sha256(request_digest)
        if (
            isinstance(expanded_uncompressed_bytes, bool)
            or not isinstance(expanded_uncompressed_bytes, int)
            or expanded_uncompressed_bytes < 0
            or isinstance(expanded_entries, bool)
            or not isinstance(expanded_entries, int)
            or expanded_entries < 1
        ):
            raise ValidationError("ARCHIVE_EXPANSION_USAGE_INVALID")
        raw_limits = (
            max_total_uncompressed_bytes,
            max_entries,
            max_nested_depth,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in raw_limits):
            raise ValidationError("ARCHIVE_EXPANSION_LIMIT_INVALID")
        limits = raw_limits
        if limits[0] < 1 or limits[1] < 1 or limits[2] < 0:
            raise ValidationError("ARCHIVE_EXPANSION_LIMIT_INVALID")
        now = utc_now()
        parent_archive: str | None = None
        with self.transaction() as connection:
            if parent is None:
                root_digest = archive
                depth = 0
                parent_node = parent_entry = parent_receipt = parent_generation = None
                root = connection.execute(
                    """SELECT * FROM archive_expansion_roots
                         WHERE tenant_id = ? AND project_id = ? AND root_archive_digest = ?""",
                    (safe_tenant, safe_project, root_digest),
                ).fetchone()
                if root is None:
                    if expanded_uncompressed_bytes > limits[0] or expanded_entries > limits[1]:
                        raise ConflictError("ARCHIVE_GLOBAL_BUDGET_EXCEEDED")
                    connection.execute(
                        """
                        INSERT INTO archive_expansion_roots (
                            tenant_id, project_id, root_archive_digest, policy_digest,
                            max_total_uncompressed_bytes, max_entries, max_nested_depth,
                            consumed_uncompressed_bytes, consumed_entries, version,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                        """,
                        (
                            safe_tenant, safe_project, root_digest, policy,
                            limits[0], limits[1], limits[2],
                            expanded_uncompressed_bytes, expanded_entries, now, now,
                        ),
                    )
                    consumed_bytes = expanded_uncompressed_bytes
                    consumed_entries = expanded_entries
                    budget_version = 1
                    budget_already_charged = True
                    root_preexisting = False
                else:
                    if (
                        str(root["policy_digest"]) != policy
                        or int(root["max_total_uncompressed_bytes"]) != limits[0]
                        or int(root["max_entries"]) != limits[1]
                        or int(root["max_nested_depth"]) != limits[2]
                    ):
                        raise IntegrityError("ARCHIVE_ROOT_POLICY_MISMATCH")
                    consumed_bytes = int(root["consumed_uncompressed_bytes"])
                    consumed_entries = int(root["consumed_entries"])
                    budget_version = int(root["version"])
                    budget_already_charged = False
                    root_preexisting = True
            else:
                required = {
                    "parent_node_digest", "parent_archive_digest", "parent_entry_digest",
                    "parent_entry_receipt_digest", "parent_generation_digest",
                }
                if set(parent) != required:
                    raise ValidationError("ARCHIVE_PARENT_LINEAGE_INVALID")
                parent_node = normalize_sha256(parent["parent_node_digest"])
                parent_archive = normalize_sha256(parent["parent_archive_digest"])
                parent_entry = normalize_sha256(parent["parent_entry_digest"])
                parent_receipt = normalize_sha256(parent["parent_entry_receipt_digest"])
                parent_generation = normalize_sha256(parent["parent_generation_digest"])
                row = connection.execute(
                    """
                    SELECT node.root_archive_digest, node.depth,
                           root.policy_digest, root.max_total_uncompressed_bytes,
                           root.max_entries, root.max_nested_depth,
                           root.consumed_uncompressed_bytes, root.consumed_entries,
                           root.version
                      FROM archive_expansion_entries AS entry
                      JOIN archive_expansion_nodes AS node
                        ON node.tenant_id = entry.tenant_id
                       AND node.project_id = entry.project_id
                       AND node.node_digest = entry.node_digest
                      JOIN archive_expansion_roots AS root
                        ON root.tenant_id = node.tenant_id
                       AND root.project_id = node.project_id
                       AND root.root_archive_digest = node.root_archive_digest
                     WHERE entry.tenant_id = ? AND entry.project_id = ?
                       AND node.node_digest = ? AND node.archive_digest = ?
                       AND entry.entry_digest = ? AND entry.entry_receipt_digest = ?
                       AND entry.generation_digest = ?
                       AND entry.nested_container IS NOT NULL
                       AND node.state = 'PUBLISHED'
                    """,
                    (
                        safe_tenant, safe_project, parent_node, parent_archive,
                        parent_entry, parent_receipt, parent_generation,
                    ),
                ).fetchone()
                if row is None or archive != parent_entry:
                    raise IntegrityError("ARCHIVE_PARENT_LINEAGE_INVALID")
                root_digest = str(row["root_archive_digest"])
                depth = int(row["depth"]) + 1
                if (
                    str(row["policy_digest"]) != policy
                    or int(row["max_total_uncompressed_bytes"]) != limits[0]
                    or int(row["max_entries"]) != limits[1]
                    or int(row["max_nested_depth"]) != limits[2]
                ):
                    raise IntegrityError("ARCHIVE_ROOT_POLICY_MISMATCH")
                if depth > int(row["max_nested_depth"]):
                    raise ConflictError("ARCHIVE_NESTED_DEPTH_LIMIT")
                consumed_bytes = int(row["consumed_uncompressed_bytes"])
                consumed_entries = int(row["consumed_entries"])
                budget_version = int(row["version"])
                budget_already_charged = False
                root_preexisting = True

            node_digest = canonical_digest(
                {
                    "schema_version": "archive-expansion-node-v1",
                    "tenant_id": safe_tenant,
                    "project_id": safe_project,
                    "root_archive_digest": f"sha256:{root_digest}",
                    "parent_node_digest": None if parent_node is None else f"sha256:{parent_node}",
                    "parent_entry_receipt_digest": (
                        None if parent_receipt is None else f"sha256:{parent_receipt}"
                    ),
                    "archive_digest": f"sha256:{archive}",
                    "depth": depth,
                }
            )
            existing = connection.execute(
                """SELECT * FROM archive_expansion_nodes
                     WHERE tenant_id = ? AND project_id = ? AND node_digest = ?""",
                (safe_tenant, safe_project, node_digest),
            ).fetchone()
            if depth == 0 and root_preexisting and existing is None:
                raise IntegrityError("ARCHIVE_ROOT_LINEAGE_INVALID")
            if existing is not None:
                if (
                    str(existing["request_digest"]) != request
                    or int(existing["expanded_uncompressed_bytes"]) != expanded_uncompressed_bytes
                    or int(existing["expanded_entries"]) != expanded_entries
                    or str(existing["archive_digest"]) != archive
                ):
                    raise ConflictError("ARCHIVE_EXPANSION_REPLAY_MISMATCH")
                return {
                    "node_digest": node_digest,
                    "root_archive_digest": root_digest,
                    "depth": depth,
                    "state": str(existing["state"]),
                    "generation_digest": existing["generation_digest"],
                    "result_digest": existing["result_digest"],
                    "consumed_uncompressed_bytes": consumed_bytes,
                    "consumed_entries": consumed_entries,
                    "budget_version": budget_version,
                    "replay": True,
                }

            if not budget_already_charged and (
                consumed_bytes + expanded_uncompressed_bytes > limits[0]
                or consumed_entries + expanded_entries > limits[1]
            ):
                raise ConflictError("ARCHIVE_GLOBAL_BUDGET_EXCEEDED")
            if not budget_already_charged:
                budget_version += 1
                consumed_bytes += expanded_uncompressed_bytes
                consumed_entries += expanded_entries
                connection.execute(
                    """
                    UPDATE archive_expansion_roots
                       SET consumed_uncompressed_bytes = ?, consumed_entries = ?,
                           version = ?, updated_at = ?
                     WHERE tenant_id = ? AND project_id = ? AND root_archive_digest = ?
                    """,
                    (
                        consumed_bytes, consumed_entries, budget_version, now,
                        safe_tenant, safe_project, root_digest,
                    ),
                )
            connection.execute(
                """
                INSERT INTO archive_expansion_nodes (
                    tenant_id, project_id, node_digest, root_archive_digest,
                    parent_node_digest, parent_archive_digest, parent_entry_digest,
                    parent_entry_receipt_digest, parent_generation_digest,
                    archive_digest, depth, expanded_uncompressed_bytes,
                    expanded_entries, request_digest, state, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RESERVED', ?)
                """,
                (
                    safe_tenant, safe_project, node_digest, root_digest,
                    parent_node, parent_archive,
                    parent_entry, parent_receipt, parent_generation,
                    archive, depth, expanded_uncompressed_bytes, expanded_entries,
                    request, now,
                ),
            )
            return {
                "node_digest": node_digest,
                "root_archive_digest": root_digest,
                "depth": depth,
                "state": "RESERVED",
                "generation_digest": None,
                "result_digest": None,
                "consumed_uncompressed_bytes": consumed_bytes,
                "consumed_entries": consumed_entries,
                "budget_version": budget_version,
                "replay": False,
            }

    def complete_archive_expansion(
        self,
        *,
        tenant_id: str,
        project_id: str,
        node_digest: str,
        generation_digest: str,
        result_digest: str,
        entries: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Publish immutable child bindings and advance a reservation exactly once."""

        safe_tenant = require_resource_id(tenant_id, "tenant_id")
        safe_project = require_resource_id(project_id, "project_id")
        node = normalize_sha256(node_digest)
        generation = normalize_sha256(generation_digest)
        result = normalize_sha256(result_digest)
        now = utc_now()
        normalized_entries: list[tuple[str, str, str, int, str | None]] = []
        for raw in entries:
            if set(raw) != {
                "entry_receipt_digest", "entry_digest", "path_digest",
                "byte_count", "nested_container",
            }:
                raise ValidationError("ARCHIVE_EXPANSION_ENTRY_INVALID")
            receipt = normalize_sha256(raw["entry_receipt_digest"])
            digest = normalize_sha256(raw["entry_digest"])
            path_digest = normalize_sha256(raw["path_digest"])
            byte_count = raw["byte_count"]
            nested = raw["nested_container"]
            if (
                isinstance(byte_count, bool)
                or not isinstance(byte_count, int)
                or byte_count < 0
                or nested not in {None, "zip", "tar", "gzip"}
            ):
                raise ValidationError("ARCHIVE_EXPANSION_ENTRY_INVALID")
            normalized_entries.append((receipt, digest, path_digest, byte_count, nested))
        if len({item[0] for item in normalized_entries}) != len(normalized_entries):
            raise ValidationError("ARCHIVE_EXPANSION_ENTRY_INVALID")
        with self.transaction() as connection:
            row = connection.execute(
                """SELECT node.*, root.consumed_uncompressed_bytes,
                              root.consumed_entries, root.version
                       FROM archive_expansion_nodes AS node
                       JOIN archive_expansion_roots AS root
                         ON root.tenant_id = node.tenant_id
                        AND root.project_id = node.project_id
                        AND root.root_archive_digest = node.root_archive_digest
                      WHERE node.tenant_id = ? AND node.project_id = ?
                        AND node.node_digest = ?""",
                (safe_tenant, safe_project, node),
            ).fetchone()
            if row is None:
                raise IntegrityError("ARCHIVE_EXPANSION_RESERVATION_MISSING")
            if (
                len(normalized_entries) > int(row["expanded_entries"])
                or sum(item[3] for item in normalized_entries)
                != int(row["expanded_uncompressed_bytes"])
            ):
                raise IntegrityError("ARCHIVE_EXPANSION_USAGE_MISMATCH")
            if str(row["state"]) == "PUBLISHED":
                if (
                    str(row["generation_digest"]) != generation
                    or str(row["result_digest"]) != result
                ):
                    raise ConflictError("ARCHIVE_EXPANSION_REPLAY_MISMATCH")
            else:
                connection.executemany(
                    """
                    INSERT INTO archive_expansion_entries (
                        tenant_id, project_id, node_digest, entry_receipt_digest,
                        entry_digest, path_digest, byte_count, nested_container,
                        generation_digest
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            safe_tenant, safe_project, node, receipt, digest,
                            path_digest, byte_count, nested, generation,
                        )
                        for receipt, digest, path_digest, byte_count, nested in normalized_entries
                    ],
                )
                updated = connection.execute(
                    """
                    UPDATE archive_expansion_nodes
                       SET state = 'PUBLISHED', generation_digest = ?,
                           result_digest = ?, published_at = ?
                     WHERE tenant_id = ? AND project_id = ? AND node_digest = ?
                       AND state = 'RESERVED'
                    """,
                    (generation, result, now, safe_tenant, safe_project, node),
                ).rowcount
                if updated != 1:
                    raise ConflictError("ARCHIVE_EXPANSION_STATE_CONFLICT")
            return {
                "root_archive_digest": str(row["root_archive_digest"]),
                "node_digest": node,
                "depth": int(row["depth"]),
                "consumed_uncompressed_bytes": int(row["consumed_uncompressed_bytes"]),
                "consumed_entries": int(row["consumed_entries"]),
                "budget_version": int(row["version"]),
            }

    @staticmethod
    def _governance_deadline(value: Any, field: str) -> str:
        if not isinstance(value, str):
            raise ValidationError("GOVERNANCE_DELETION_DEADLINE_INVALID", details={"field": field})
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValidationError(
                "GOVERNANCE_DELETION_DEADLINE_INVALID", details={"field": field}
            ) from error
        if parsed.tzinfo is None:
            raise ValidationError("GOVERNANCE_DELETION_DEADLINE_INVALID", details={"field": field})
        return parsed.astimezone(UTC).replace(microsecond=0).isoformat()

    @staticmethod
    def _governance_audit(
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        job_id: str,
        command_id: str | None,
        action: str,
        event: Mapping[str, Any],
        occurred_at: str,
    ) -> None:
        event_digest = canonical_digest(dict(event))
        audit_id = "deletion-audit-" + canonical_digest(
            [context.tenant_id, context.project_id, job_id, command_id, action, event_digest]
        )[:40]
        connection.execute(
            """INSERT OR IGNORE INTO governance_deletion_audit
               (tenant_id,project_id,audit_id,job_id,command_id,actor_id,
                action,event_digest,occurred_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                context.tenant_id, context.project_id, audit_id, job_id,
                command_id, context.actor_id, action, event_digest, occurred_at,
            ),
        )

    @classmethod
    def _materialize_governance_deletion(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        job_id: str,
    ) -> dict[str, Any]:
        job = connection.execute(
            """SELECT * FROM governance_deletion_jobs
                WHERE tenant_id=? AND project_id=? AND job_id=?""",
            (context.tenant_id, context.project_id, require_resource_id(job_id, "job_id")),
        ).fetchone()
        if job is None:
            raise NotFoundError("GOVERNANCE_DELETION_JOB_NOT_FOUND")
        rows = connection.execute(
            """SELECT * FROM governance_deletion_commands
                WHERE tenant_id=? AND project_id=? AND job_id=?
                ORDER BY store_kind,object_id,object_version""",
            (context.tenant_id, context.project_id, job_id),
        ).fetchall()
        if len(rows) != int(job["command_count"]):
            raise IntegrityError("GOVERNANCE_DELETION_COMMAND_SET_CORRUPT")
        commands: list[dict[str, Any]] = []
        for row in rows:
            command = {
                "schema_version": "elmos-governance-deletion-command-v1",
                "tenant_id": row["tenant_id"],
                "project_id": row["project_id"],
                "job_id": row["job_id"],
                "command_id": row["command_id"],
                "store_kind": row["store_kind"],
                "object_id": row["object_id"],
                "object_version": row["object_version"],
                "object_digest": "sha256:" + row["object_digest"],
                "byte_count": int(row["byte_count"]),
            }
            if not hmac.compare_digest(canonical_digest(command), row["command_digest"]):
                raise IntegrityError("GOVERNANCE_DELETION_COMMAND_CORRUPT")
            execution_row = connection.execute(
                """SELECT * FROM governance_deletion_execution_receipts
                    WHERE tenant_id=? AND project_id=? AND command_id=?""",
                (context.tenant_id, context.project_id, row["command_id"]),
            ).fetchone()
            verification_row = connection.execute(
                """SELECT * FROM governance_deletion_verification_receipts
                    WHERE tenant_id=? AND project_id=? AND command_id=?""",
                (context.tenant_id, context.project_id, row["command_id"]),
            ).fetchone()
            execution: dict[str, Any] | None = None
            if execution_row is not None:
                try:
                    decoded = json.loads(execution_row["receipt_json"])
                except (TypeError, json.JSONDecodeError) as error:
                    raise IntegrityError("GOVERNANCE_DELETION_EXECUTION_RECEIPT_CORRUPT") from error
                if (
                    not isinstance(decoded, dict)
                    or set(decoded) != {
                        "schema_version", "tenant_id", "project_id", "job_id",
                        "command_id", "command_digest", "store_kind", "object_id",
                        "object_version", "object_digest", "expected_byte_count",
                        "disposition", "deleted_byte_count", "provider_evidence_digest",
                        "provider_evidence_byte_count", "executor_id",
                        "worker_capability_id", "recorded_at",
                    }
                    or canonical_json(decoded) != execution_row["receipt_json"]
                    or not hmac.compare_digest(
                        canonical_digest(decoded), execution_row["receipt_digest"]
                    )
                    or decoded["tenant_id"] != context.tenant_id
                    or decoded["project_id"] != context.project_id
                    or decoded["job_id"] != row["job_id"]
                    or decoded["command_id"] != row["command_id"]
                    or decoded["command_digest"] != "sha256:" + row["command_digest"]
                    or decoded["object_digest"] != "sha256:" + row["object_digest"]
                    or decoded["expected_byte_count"] != int(row["byte_count"])
                    or decoded["executor_id"] != execution_row["executor_id"]
                ):
                    raise IntegrityError("GOVERNANCE_DELETION_EXECUTION_RECEIPT_CORRUPT")
                execution = decoded
            verification: dict[str, Any] | None = None
            if verification_row is not None:
                try:
                    decoded = json.loads(verification_row["receipt_json"])
                except (TypeError, json.JSONDecodeError) as error:
                    raise IntegrityError("GOVERNANCE_DELETION_VERIFICATION_RECEIPT_CORRUPT") from error
                if (
                    not isinstance(decoded, dict)
                    or set(decoded) != {
                        "schema_version", "tenant_id", "project_id", "job_id",
                        "command_id", "command_digest", "execution_receipt_digest",
                        "observed_absent", "verification_evidence_digest",
                        "verification_evidence_byte_count", "verifier_id",
                        "verifier_capability_id", "recorded_at",
                    }
                    or canonical_json(decoded) != verification_row["receipt_json"]
                    or not hmac.compare_digest(
                        canonical_digest(decoded), verification_row["receipt_digest"]
                    )
                    or decoded["tenant_id"] != context.tenant_id
                    or decoded["project_id"] != context.project_id
                    or decoded["job_id"] != row["job_id"]
                    or decoded["command_id"] != row["command_id"]
                    or decoded["command_digest"] != "sha256:" + row["command_digest"]
                    or execution_row is None
                    or decoded["execution_receipt_digest"]
                    != "sha256:" + execution_row["receipt_digest"]
                    or not isinstance(decoded["observed_absent"], bool)
                    or decoded["verifier_id"] != verification_row["verifier_id"]
                    or decoded["verifier_id"] == execution_row["executor_id"]
                ):
                    raise IntegrityError("GOVERNANCE_DELETION_VERIFICATION_RECEIPT_CORRUPT")
                verification = decoded
            if (
                (execution is None) != (row["execution_receipt_digest"] is None)
                or execution is not None
                and not hmac.compare_digest(
                    execution_row["receipt_digest"], row["execution_receipt_digest"]
                )
                or (verification is None) != (row["verification_receipt_digest"] is None)
                or verification is not None
                and not hmac.compare_digest(
                    verification_row["receipt_digest"], row["verification_receipt_digest"]
                )
                or row["state"] == "UNKNOWN" and execution is None
                or row["state"] == "VERIFIED"
                and (execution is None or verification is None or verification["observed_absent"] is not True)
                or row["state"] == "BLOCKED"
                and verification is not None
                and verification["observed_absent"] is not False
                or row["state"] in {"PENDING", "CLAIMED"}
                and (execution is not None or verification is not None)
            ):
                raise IntegrityError("GOVERNANCE_DELETION_RECEIPT_STATE_CORRUPT")
            commands.append(
                {
                    **command,
                    "command_digest": "sha256:" + row["command_digest"],
                    "state": row["state"],
                    "attempt": int(row["attempt"]),
                    "execution_receipt_digest": (
                        "sha256:" + row["execution_receipt_digest"]
                        if row["execution_receipt_digest"] else None
                    ),
                    "verification_receipt_digest": (
                        "sha256:" + row["verification_receipt_digest"]
                        if row["verification_receipt_digest"] else None
                    ),
                    "failure_code": row["failure_code"],
                }
            )
        result: dict[str, Any] = {
            "schema_version": "elmos-governance-deletion-job-v1",
            "tenant_id": job["tenant_id"],
            "project_id": job["project_id"],
            "job_id": job["job_id"],
            "actor_id": job["actor_id"],
            "request_digest": "sha256:" + job["request_digest"],
            "policy_version": job["policy_version"],
            "inventory_version": job["inventory_version"],
            "inventory_digest": "sha256:" + job["inventory_digest"],
            "state": job["state"],
            "backup_delete_not_before": job["backup_delete_not_before"],
            "legal_hold_count": int(job["legal_hold_count"]),
            "command_count": int(job["command_count"]),
            "commands": commands,
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "completed_at": job["completed_at"],
            "proof": None,
            "proof_digest": "sha256:" + job["proof_digest"] if job["proof_digest"] else None,
        }
        if job["proof_json"] is not None:
            try:
                proof = json.loads(job["proof_json"])
            except (TypeError, json.JSONDecodeError) as error:
                raise IntegrityError("GOVERNANCE_DELETION_PROOF_CORRUPT") from error
            if (
                not isinstance(proof, dict)
                or canonical_json(proof) != job["proof_json"]
                or not hmac.compare_digest(canonical_digest(proof), job["proof_digest"])
            ):
                raise IntegrityError("GOVERNANCE_DELETION_PROOF_CORRUPT")
            result["proof"] = proof
        return result

    def prepare_governance_deletion(
        self,
        context: TenantContext,
        *,
        objects: Sequence[Mapping[str, Any]],
        policy_version: str,
        inventory_version: str,
        inventory_digest: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Persist an exact per-store deletion plan; inventory flags never prove deletion."""

        self.require(context, self.ADMIN)
        safe_key = require_idempotency_key(idempotency_key)
        safe_policy = require_resource_id(policy_version, "policy_version")
        safe_inventory = require_resource_id(inventory_version, "inventory_version")
        safe_inventory_digest = normalize_sha256(inventory_digest)
        if not isinstance(objects, Sequence) or isinstance(objects, (str, bytes)) or not 1 <= len(objects) <= 50_000:
            raise ValidationError("GOVERNANCE_DELETION_OBJECTS_INVALID")
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for index, raw in enumerate(objects):
            if not isinstance(raw, Mapping) or set(raw) != {
                "tenant_id", "project_id", "object_id", "store", "object_version",
                "object_digest", "byte_count", "retention_hold", "backup_delete_not_before",
            }:
                raise ValidationError(
                    "GOVERNANCE_DELETION_OBJECT_FIELDS_INVALID", details={"index": index}
                )
            if raw["tenant_id"] != context.tenant_id or raw["project_id"] != context.project_id:
                raise AuthorizationError("GOVERNANCE_DELETION_SCOPE_MISMATCH")
            store_kind = require_resource_id(raw["store"], "store")
            object_id = require_resource_id(raw["object_id"], "object_id")
            object_version = require_resource_id(raw["object_version"], "object_version")
            key = (store_kind, object_id, object_version)
            if key in seen:
                raise ValidationError("GOVERNANCE_DELETION_OBJECT_DUPLICATE")
            seen.add(key)
            byte_count = raw["byte_count"]
            if isinstance(byte_count, bool) or not isinstance(byte_count, int) or not 0 <= byte_count <= MAX_SAFE_JSON_INTEGER:
                raise ValidationError("GOVERNANCE_DELETION_BYTE_COUNT_INVALID")
            if not isinstance(raw["retention_hold"], bool):
                raise ValidationError("GOVERNANCE_DELETION_HOLD_INVALID")
            normalized.append(
                {
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "store_kind": store_kind,
                    "object_id": object_id,
                    "object_version": object_version,
                    "object_digest": "sha256:" + normalize_sha256(raw["object_digest"]),
                    "byte_count": byte_count,
                    "retention_hold": raw["retention_hold"],
                    "backup_delete_not_before": self._governance_deadline(
                        raw["backup_delete_not_before"], "backup_delete_not_before"
                    ),
                }
            )
        normalized.sort(key=lambda item: (item["store_kind"], item["object_id"], item["object_version"]))
        request_body = {
            "schema_version": "elmos-governance-deletion-request-v1",
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "actor_id": context.actor_id,
            "policy_version": safe_policy,
            "inventory_version": safe_inventory,
            "inventory_digest": "sha256:" + safe_inventory_digest,
            "objects": normalized,
        }
        request_digest = canonical_digest(request_body)
        job_id = "deletion-job-" + canonical_digest(
            [context.tenant_id, context.project_id, context.actor_id, safe_key]
        )[:40]
        held = sum(1 for item in normalized if item["retention_hold"])
        backup_deadline = max(item["backup_delete_not_before"] for item in normalized)
        now = utc_now()
        with self.transaction() as connection:
            self._require(connection, context, self.ADMIN)
            prior = connection.execute(
                """SELECT request_digest,job_id FROM governance_deletion_jobs
                    WHERE tenant_id=? AND project_id=? AND actor_id=? AND idempotency_key=?""",
                (context.tenant_id, context.project_id, context.actor_id, safe_key),
            ).fetchone()
            if prior is not None:
                if not hmac.compare_digest(prior["request_digest"], request_digest):
                    raise ConflictError("GOVERNANCE_DELETION_IDEMPOTENCY_CONFLICT")
                return self._materialize_governance_deletion(connection, context, prior["job_id"])
            state = "BLOCKED" if held else "PENDING"
            connection.execute(
                """INSERT INTO governance_deletion_jobs
                   (tenant_id,project_id,job_id,actor_id,idempotency_key,request_digest,
                    policy_version,inventory_version,inventory_digest,state,
                    backup_delete_not_before,legal_hold_count,command_count,
                    proof_json,proof_digest,created_at,updated_at,completed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,?,?,NULL)""",
                (
                    context.tenant_id, context.project_id, job_id, context.actor_id,
                    safe_key, request_digest, safe_policy, safe_inventory,
                    safe_inventory_digest, state, backup_deadline, held, len(normalized),
                    now, now,
                ),
            )
            for item in normalized:
                command = {
                    "schema_version": "elmos-governance-deletion-command-v1",
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "job_id": job_id,
                    "command_id": "deletion-command-" + canonical_digest(
                        [job_id, item["store_kind"], item["object_id"], item["object_version"]]
                    )[:40],
                    "store_kind": item["store_kind"],
                    "object_id": item["object_id"],
                    "object_version": item["object_version"],
                    "object_digest": item["object_digest"],
                    "byte_count": item["byte_count"],
                }
                connection.execute(
                    """INSERT INTO governance_deletion_commands
                       (tenant_id,project_id,command_id,job_id,store_kind,object_id,
                        object_version,object_digest,byte_count,command_digest,state,
                        attempt,claim_token_digest,execution_receipt_digest,
                        verification_receipt_digest,failure_code,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,0,NULL,NULL,NULL,?,?,?)""",
                    (
                        context.tenant_id, context.project_id, command["command_id"], job_id,
                        command["store_kind"], command["object_id"], command["object_version"],
                        normalize_sha256(command["object_digest"]), command["byte_count"],
                        canonical_digest(command), "BLOCKED" if item["retention_hold"] else "PENDING",
                        "LEGAL_HOLD" if item["retention_hold"] else None, now, now,
                    ),
                )
            event = {
                "schema_version": "elmos-governance-deletion-event-v1",
                "job_id": job_id,
                "state": state,
                "request_digest": "sha256:" + request_digest,
                "command_count": len(normalized),
                "legal_hold_count": held,
            }
            self._governance_audit(
                connection, context, job_id=job_id, command_id=None,
                action="DELETE_REQUESTED", event=event, occurred_at=now,
            )
            self._event(
                connection, context, "governance_deletion", job_id,
                "governance.deletion.requested", f"governance-delete-request:{job_id}", event,
            )
            return self._materialize_governance_deletion(connection, context, job_id)

    def governance_deletion_status(
        self, context: TenantContext, *, job_id: str
    ) -> dict[str, Any]:
        self.require(context, self.READ)
        with self.transaction() as connection:
            self._require(connection, context, self.READ)
            self._finalize_governance_deletion(connection, context, job_id)
            return self._materialize_governance_deletion(connection, context, job_id)

    def claim_governance_deletion_command(
        self,
        context: TenantContext,
        *,
        job_id: str,
        claim_token: str,
        capability: object,
    ) -> dict[str, Any]:
        if capability is None or capability is not self._deletion_worker_capability:
            raise AuthorizationError("GOVERNANCE_DELETION_WORKER_UNAUTHORIZED")
        safe_claim = require_idempotency_key(claim_token)
        claim_digest = canonical_digest(safe_claim)
        now = utc_now()
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            job = connection.execute(
                """SELECT * FROM governance_deletion_jobs
                    WHERE tenant_id=? AND project_id=? AND job_id=?""",
                (context.tenant_id, context.project_id, require_resource_id(job_id, "job_id")),
            ).fetchone()
            if job is None:
                raise NotFoundError("GOVERNANCE_DELETION_JOB_NOT_FOUND")
            if int(job["legal_hold_count"]):
                raise ConflictError("GOVERNANCE_DELETION_LEGAL_HOLD_ACTIVE")
            if job["backup_delete_not_before"] > now:
                raise ConflictError(
                    "GOVERNANCE_DELETION_BACKUP_LAG_ACTIVE",
                    retryable=True,
                    details={"not_before": job["backup_delete_not_before"]},
                )
            claimed = connection.execute(
                """SELECT * FROM governance_deletion_commands
                    WHERE tenant_id=? AND project_id=? AND job_id=?
                      AND claim_token_digest=?""",
                (context.tenant_id, context.project_id, job_id, claim_digest),
            ).fetchone()
            if claimed is not None and claimed["state"] != "CLAIMED":
                raise ConflictError(
                    "GOVERNANCE_DELETION_CLAIM_ALREADY_DISPATCHED", retryable=False
                )
            row = claimed or connection.execute(
                """SELECT * FROM governance_deletion_commands
                    WHERE tenant_id=? AND project_id=? AND job_id=? AND state='PENDING'
                    ORDER BY created_at,command_id LIMIT 1""",
                (context.tenant_id, context.project_id, job_id),
            ).fetchone()
            if row is None:
                raise ConflictError("GOVERNANCE_DELETION_COMMAND_UNAVAILABLE", retryable=False)
            if claimed is None:
                updated = connection.execute(
                    """UPDATE governance_deletion_commands
                          SET state='CLAIMED',attempt=attempt+1,claim_token_digest=?,updated_at=?
                        WHERE tenant_id=? AND project_id=? AND command_id=? AND state='PENDING'""",
                    (
                        claim_digest, now, context.tenant_id,
                        context.project_id, row["command_id"],
                    ),
                ).rowcount
                if updated != 1:
                    raise ConflictError("GOVERNANCE_DELETION_COMMAND_CLAIM_CONFLICT")
                connection.execute(
                    """UPDATE governance_deletion_jobs SET state='RUNNING',updated_at=?
                        WHERE tenant_id=? AND project_id=? AND job_id=? AND state='PENDING'""",
                    (now, context.tenant_id, context.project_id, job_id),
                )
            event = {
                "schema_version": "elmos-governance-deletion-event-v1",
                "job_id": job_id,
                "command_id": row["command_id"],
                "command_digest": "sha256:" + row["command_digest"],
                "worker_capability_id": self._deletion_worker_capability_id,
                "attempt": int(row["attempt"]) + (1 if claimed is None else 0),
            }
            self._governance_audit(
                connection, context, job_id=job_id, command_id=row["command_id"],
                action="COMMAND_CLAIMED", event=event, occurred_at=now,
            )
            return {
                "claim_token": safe_claim,
                "command": {
                    "schema_version": "elmos-governance-deletion-command-v1",
                    "tenant_id": row["tenant_id"], "project_id": row["project_id"],
                    "job_id": row["job_id"], "command_id": row["command_id"],
                    "store_kind": row["store_kind"], "object_id": row["object_id"],
                    "object_version": row["object_version"],
                    "object_digest": "sha256:" + row["object_digest"],
                    "byte_count": int(row["byte_count"]),
                    "command_digest": "sha256:" + row["command_digest"],
                },
            }

    def record_governance_deletion_execution(
        self,
        context: TenantContext,
        *,
        command_id: str,
        claim_token: str,
        executor_id: str,
        disposition: str,
        observed_object_digest: str,
        deleted_byte_count: int,
        provider_evidence_digest: str,
        provider_evidence_byte_count: int,
        capability: object,
    ) -> dict[str, Any]:
        if capability is None or capability is not self._deletion_worker_capability:
            raise AuthorizationError("GOVERNANCE_DELETION_WORKER_UNAUTHORIZED")
        safe_executor = require_actor_id(executor_id)
        safe_disposition = str(disposition).upper()
        if safe_disposition not in {"DELETED", "ALREADY_ABSENT", "OUTCOME_UNKNOWN"}:
            raise ValidationError("GOVERNANCE_DELETION_DISPOSITION_INVALID")
        safe_observed = normalize_sha256(observed_object_digest)
        safe_evidence = normalize_sha256(provider_evidence_digest)
        if isinstance(deleted_byte_count, bool) or not isinstance(deleted_byte_count, int) or deleted_byte_count < 0:
            raise ValidationError("GOVERNANCE_DELETION_BYTE_COUNT_INVALID")
        if (
            isinstance(provider_evidence_byte_count, bool)
            or not isinstance(provider_evidence_byte_count, int)
            or not 1 <= provider_evidence_byte_count <= MAX_SAFE_JSON_INTEGER
        ):
            raise ValidationError("GOVERNANCE_DELETION_EVIDENCE_BYTE_COUNT_INVALID")
        now = utc_now()
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            row = connection.execute(
                """SELECT * FROM governance_deletion_commands
                    WHERE tenant_id=? AND project_id=? AND command_id=?""",
                (context.tenant_id, context.project_id, require_resource_id(command_id, "command_id")),
            ).fetchone()
            if row is None:
                raise NotFoundError("GOVERNANCE_DELETION_COMMAND_NOT_FOUND")
            if row["state"] == "UNKNOWN" and row["execution_receipt_digest"]:
                prior_row = connection.execute(
                    """SELECT receipt_json FROM governance_deletion_execution_receipts
                        WHERE tenant_id=? AND project_id=? AND command_id=?""",
                    (context.tenant_id, context.project_id, row["command_id"]),
                ).fetchone()
                try:
                    prior = json.loads(prior_row["receipt_json"]) if prior_row else None
                except (TypeError, json.JSONDecodeError) as error:
                    raise IntegrityError("GOVERNANCE_DELETION_EXECUTION_RECEIPT_CORRUPT") from error
                if (
                    not isinstance(prior, dict)
                    or prior.get("executor_id") != safe_executor
                    or prior.get("disposition") != safe_disposition
                    or prior.get("object_digest") != "sha256:" + safe_observed
                    or prior.get("deleted_byte_count") != deleted_byte_count
                    or prior.get("provider_evidence_digest") != "sha256:" + safe_evidence
                    or prior.get("provider_evidence_byte_count") != provider_evidence_byte_count
                ):
                    raise ConflictError("GOVERNANCE_DELETION_EXECUTION_REPLAY_CONFLICT")
                return self._materialize_governance_deletion(connection, context, row["job_id"])
            if row["state"] != "CLAIMED" or not hmac.compare_digest(
                str(row["claim_token_digest"] or ""), canonical_digest(require_idempotency_key(claim_token))
            ):
                raise ConflictError("GOVERNANCE_DELETION_COMMAND_CLAIM_NOT_OWNED")
            if not hmac.compare_digest(safe_observed, row["object_digest"]):
                raise ConflictError("GOVERNANCE_DELETION_OBJECT_DIGEST_MISMATCH")
            if safe_disposition == "DELETED" and deleted_byte_count != int(row["byte_count"]):
                raise ConflictError("GOVERNANCE_DELETION_BYTE_COUNT_MISMATCH")
            if safe_disposition in {"ALREADY_ABSENT", "OUTCOME_UNKNOWN"} and deleted_byte_count != 0:
                raise ValidationError("GOVERNANCE_DELETION_ABSENT_BYTE_COUNT_INVALID")
            receipt = {
                "schema_version": "elmos-governance-deletion-execution-receipt-v1",
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "job_id": row["job_id"],
                "command_id": row["command_id"],
                "command_digest": "sha256:" + row["command_digest"],
                "store_kind": row["store_kind"],
                "object_id": row["object_id"],
                "object_version": row["object_version"],
                "object_digest": "sha256:" + row["object_digest"],
                "expected_byte_count": int(row["byte_count"]),
                "disposition": safe_disposition,
                "deleted_byte_count": deleted_byte_count,
                "provider_evidence_digest": "sha256:" + safe_evidence,
                "provider_evidence_byte_count": provider_evidence_byte_count,
                "executor_id": safe_executor,
                "worker_capability_id": self._deletion_worker_capability_id,
                "recorded_at": now,
            }
            receipt_json = canonical_json(receipt)
            receipt_digest = canonical_digest(receipt)
            connection.execute(
                """INSERT INTO governance_deletion_execution_receipts
                   (tenant_id,project_id,command_id,receipt_json,receipt_digest,executor_id,recorded_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    context.tenant_id, context.project_id, row["command_id"],
                    receipt_json, receipt_digest, safe_executor, now,
                ),
            )
            connection.execute(
                """UPDATE governance_deletion_commands
                      SET state='UNKNOWN',
                          execution_receipt_digest=?,failure_code='INDEPENDENT_VERIFICATION_REQUIRED',updated_at=?
                    WHERE tenant_id=? AND project_id=? AND command_id=? AND state='CLAIMED'""",
                (receipt_digest, now, context.tenant_id, context.project_id, row["command_id"]),
            )
            connection.execute(
                """UPDATE governance_deletion_jobs SET state='UNKNOWN',updated_at=?
                    WHERE tenant_id=? AND project_id=? AND job_id=? AND state<>'COMPLETED'""",
                (now, context.tenant_id, context.project_id, row["job_id"]),
            )
            event = {
                "schema_version": "elmos-governance-deletion-event-v1",
                "job_id": row["job_id"], "command_id": row["command_id"],
                "execution_receipt_digest": "sha256:" + receipt_digest,
                "state": "UNKNOWN",
            }
            self._governance_audit(
                connection, context, job_id=row["job_id"], command_id=row["command_id"],
                action="EXECUTION_RECORDED_UNKNOWN", event=event, occurred_at=now,
            )
            self._event(
                connection, context, "governance_deletion", row["job_id"],
                "governance.deletion.execution-recorded",
                f"governance-delete-execution:{row['command_id']}", event,
            )
            return self._materialize_governance_deletion(connection, context, row["job_id"])

    def verify_governance_deletion_command(
        self,
        context: TenantContext,
        *,
        command_id: str,
        verifier_id: str,
        observed_absent: bool,
        verification_evidence_digest: str,
        verification_evidence_byte_count: int,
        capability: object,
    ) -> dict[str, Any]:
        if capability is None or capability is not self._deletion_verifier_capability:
            raise AuthorizationError("GOVERNANCE_DELETION_VERIFIER_UNAUTHORIZED")
        safe_verifier = require_actor_id(verifier_id)
        safe_evidence = normalize_sha256(verification_evidence_digest)
        if (
            isinstance(verification_evidence_byte_count, bool)
            or not isinstance(verification_evidence_byte_count, int)
            or not 1 <= verification_evidence_byte_count <= MAX_SAFE_JSON_INTEGER
        ):
            raise ValidationError("GOVERNANCE_DELETION_EVIDENCE_BYTE_COUNT_INVALID")
        if not isinstance(observed_absent, bool):
            raise ValidationError("GOVERNANCE_DELETION_OBSERVED_ABSENCE_INVALID")
        now = utc_now()
        with self.transaction() as connection:
            self._require(connection, context, self.ADMIN)
            row = connection.execute(
                """SELECT command.*,receipt.receipt_json,receipt.executor_id
                      FROM governance_deletion_commands AS command
                      JOIN governance_deletion_execution_receipts AS receipt
                        ON receipt.tenant_id=command.tenant_id
                       AND receipt.project_id=command.project_id
                       AND receipt.command_id=command.command_id
                     WHERE command.tenant_id=? AND command.project_id=? AND command.command_id=?""",
                (context.tenant_id, context.project_id, require_resource_id(command_id, "command_id")),
            ).fetchone()
            if row is None:
                raise NotFoundError("GOVERNANCE_DELETION_EXECUTION_RECEIPT_NOT_FOUND")
            if row["state"] == "VERIFIED" and row["verification_receipt_digest"]:
                prior_row = connection.execute(
                    """SELECT receipt_json FROM governance_deletion_verification_receipts
                        WHERE tenant_id=? AND project_id=? AND command_id=?""",
                    (context.tenant_id, context.project_id, row["command_id"]),
                ).fetchone()
                try:
                    prior = json.loads(prior_row["receipt_json"]) if prior_row else None
                except (TypeError, json.JSONDecodeError) as error:
                    raise IntegrityError("GOVERNANCE_DELETION_VERIFICATION_RECEIPT_CORRUPT") from error
                if (
                    not isinstance(prior, dict)
                    or prior.get("verifier_id") != safe_verifier
                    or prior.get("observed_absent") is not observed_absent
                    or prior.get("verification_evidence_digest") != "sha256:" + safe_evidence
                    or prior.get("verification_evidence_byte_count")
                    != verification_evidence_byte_count
                ):
                    raise ConflictError("GOVERNANCE_DELETION_VERIFICATION_REPLAY_CONFLICT")
                return self._materialize_governance_deletion(connection, context, row["job_id"])
            if row["state"] != "UNKNOWN":
                raise ConflictError("GOVERNANCE_DELETION_RECONCILIATION_NOT_REQUIRED")
            if hmac.compare_digest(safe_verifier, row["executor_id"]):
                raise AuthorizationError("GOVERNANCE_DELETION_INDEPENDENT_VERIFIER_REQUIRED")
            execution_receipt_digest = canonical_digest(json.loads(row["receipt_json"]))
            if not hmac.compare_digest(execution_receipt_digest, row["execution_receipt_digest"]):
                raise IntegrityError("GOVERNANCE_DELETION_EXECUTION_RECEIPT_CORRUPT")
            receipt = {
                "schema_version": "elmos-governance-deletion-verification-receipt-v1",
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "job_id": row["job_id"],
                "command_id": row["command_id"],
                "command_digest": "sha256:" + row["command_digest"],
                "execution_receipt_digest": "sha256:" + execution_receipt_digest,
                "observed_absent": observed_absent,
                "verification_evidence_digest": "sha256:" + safe_evidence,
                "verification_evidence_byte_count": verification_evidence_byte_count,
                "verifier_id": safe_verifier,
                "verifier_capability_id": self._deletion_verifier_capability_id,
                "recorded_at": now,
            }
            receipt_json = canonical_json(receipt)
            receipt_digest = canonical_digest(receipt)
            connection.execute(
                """INSERT INTO governance_deletion_verification_receipts
                   (tenant_id,project_id,command_id,receipt_json,receipt_digest,verifier_id,recorded_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    context.tenant_id, context.project_id, row["command_id"],
                    receipt_json, receipt_digest, safe_verifier, now,
                ),
            )
            target_state = "VERIFIED" if observed_absent else "BLOCKED"
            failure_code = None if observed_absent else "OBJECT_STILL_PRESENT"
            connection.execute(
                """UPDATE governance_deletion_commands
                      SET state=?,verification_receipt_digest=?,failure_code=?,updated_at=?
                    WHERE tenant_id=? AND project_id=? AND command_id=? AND state='UNKNOWN'""",
                (
                    target_state, receipt_digest, failure_code, now,
                    context.tenant_id, context.project_id, row["command_id"],
                ),
            )
            if not observed_absent:
                connection.execute(
                    """UPDATE governance_deletion_jobs
                          SET state='BLOCKED',updated_at=?
                        WHERE tenant_id=? AND project_id=? AND job_id=?
                          AND state IN ('RUNNING','UNKNOWN')""",
                    (now, context.tenant_id, context.project_id, row["job_id"]),
                )
            event = {
                "schema_version": "elmos-governance-deletion-event-v1",
                "job_id": row["job_id"], "command_id": row["command_id"],
                "verification_receipt_digest": "sha256:" + receipt_digest,
                "state": target_state,
            }
            self._governance_audit(
                connection, context, job_id=row["job_id"], command_id=row["command_id"],
                action="COMMAND_VERIFIED" if observed_absent else "COMMAND_BLOCKED_PRESENT",
                event=event, occurred_at=now,
            )
            self._event(
                connection, context, "governance_deletion", row["job_id"],
                (
                    "governance.deletion.command-verified"
                    if observed_absent else "governance.deletion.command-blocked"
                ),
                f"governance-delete-verified:{row['command_id']}", event,
            )
            if observed_absent:
                self._finalize_governance_deletion(connection, context, row["job_id"])
            return self._materialize_governance_deletion(connection, context, row["job_id"])

    @classmethod
    def _finalize_governance_deletion(
        cls, connection: sqlite3.Connection, context: TenantContext, job_id: str
    ) -> None:
        job = connection.execute(
            """SELECT * FROM governance_deletion_jobs
                WHERE tenant_id=? AND project_id=? AND job_id=?""",
            (context.tenant_id, context.project_id, require_resource_id(job_id, "job_id")),
        ).fetchone()
        if job is None:
            raise NotFoundError("GOVERNANCE_DELETION_JOB_NOT_FOUND")
        if job["state"] == "COMPLETED" or int(job["legal_hold_count"]):
            return
        now = utc_now()
        if job["backup_delete_not_before"] > now:
            return
        rows = connection.execute(
            """SELECT command_id,command_digest,execution_receipt_digest,
                       verification_receipt_digest,state
                  FROM governance_deletion_commands
                 WHERE tenant_id=? AND project_id=? AND job_id=?
                 ORDER BY command_id""",
            (context.tenant_id, context.project_id, job_id),
        ).fetchall()
        if not rows or any(row["state"] != "VERIFIED" for row in rows):
            return
        proof = {
            "schema_version": "elmos-governance-deletion-proof-v1",
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "job_id": job_id,
            "policy_version": job["policy_version"],
            "inventory_version": job["inventory_version"],
            "inventory_digest": "sha256:" + job["inventory_digest"],
            "backup_delete_not_before": job["backup_delete_not_before"],
            "verified_commands": [
                {
                    "command_id": row["command_id"],
                    "command_digest": "sha256:" + row["command_digest"],
                    "execution_receipt_digest": "sha256:" + row["execution_receipt_digest"],
                    "verification_receipt_digest": "sha256:" + row["verification_receipt_digest"],
                }
                for row in rows
            ],
            "completed_at": now,
            "content_in_audit_log": False,
        }
        proof_json = canonical_json(proof)
        proof_digest = canonical_digest(proof)
        updated = connection.execute(
            """UPDATE governance_deletion_jobs
                  SET state='COMPLETED',proof_json=?,proof_digest=?,updated_at=?,completed_at=?
                WHERE tenant_id=? AND project_id=? AND job_id=? AND state<>'COMPLETED'""",
            (
                proof_json, proof_digest, now, now,
                context.tenant_id, context.project_id, job_id,
            ),
        ).rowcount
        if updated != 1:
            raise ConflictError("GOVERNANCE_DELETION_FINALIZATION_CONFLICT")
        event = {
            "schema_version": "elmos-governance-deletion-event-v1",
            "job_id": job_id,
            "proof_digest": "sha256:" + proof_digest,
            "verified_command_count": len(rows),
        }
        cls._governance_audit(
            connection, context, job_id=job_id, command_id=None,
            action="DELETION_COMPLETED", event=event, occurred_at=now,
        )
        cls._event(
            connection, context, "governance_deletion", job_id,
            "deletion.completed", f"governance-delete-completed:{job_id}", event,
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    @contextmanager
    def read_transaction(self) -> Iterator[sqlite3.Connection]:
        """Hold one deferred SQLite read snapshot without reserving the writer."""

        with self._lock:
            if self._connection.in_transaction:
                raise IntegrityError("INTAKE_READ_TRANSACTION_NESTED")
            self._connection.execute("BEGIN")
            try:
                yield self._connection
                self._connection.execute("COMMIT")
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def bootstrap_project(self, context: TenantContext) -> None:
        """Create the initial owner only when the project has no ACL rows."""
        with self.transaction() as connection:
            count = connection.execute(
                "SELECT count(*) FROM project_acl WHERE tenant_id=? AND project_id=?",
                (context.tenant_id, context.project_id),
            ).fetchone()[0]
            if count:
                self._require(connection, context, self.ADMIN)
                return
            now = utc_now()
            connection.executemany(
                "INSERT INTO project_acl VALUES (?,?,?,?,?,?)",
                [
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        permission,
                        context.actor_id,
                        now,
                    )
                    for permission in self._ALL_PERMISSIONS
                ],
            )

    def grant_permissions(
        self,
        context: TenantContext,
        principal_id: str,
        permissions: Sequence[str],
    ) -> None:
        invalid = set(permissions) - set(self._ALL_PERMISSIONS)
        if not permissions or invalid:
            raise ValidationError("ACL_PERMISSION_INVALID")
        principal_id = require_actor_id(principal_id)
        with self.transaction() as connection:
            self._require(connection, context, self.ADMIN)
            now = utc_now()
            connection.executemany(
                "INSERT OR IGNORE INTO project_acl VALUES (?,?,?,?,?,?)",
                [
                    (
                        context.tenant_id,
                        context.project_id,
                        principal_id,
                        permission,
                        context.actor_id,
                        now,
                    )
                    for permission in permissions
                ],
            )

    def require(self, context: TenantContext, permission: str) -> None:
        with self._lock:
            self._require(self._connection, context, permission)

    @classmethod
    def _receipt_permission(cls, permission: str) -> str:
        # Receipt persistence is infrastructure, not business authorization.
        # The public execution fence must use the exact operation permission;
        # otherwise a READ-only principal can create a receipt before a WRITE,
        # REVIEW, or ADMIN denial.  Owning methods still re-check authority in
        # the same transaction as their business mutation.
        if permission not in set(cls._ALL_PERMISSIONS):
            raise ValidationError("SKILL_EXECUTION_RECEIPT_PERMISSION_INVALID")
        return permission

    def skill_execution_receipt(
        self,
        context: TenantContext,
        *,
        skill: str,
        idempotency_key: str,
        request_digest: str,
    ) -> tuple[int, dict[str, Any]] | None:
        """Replay an actor-scoped exact request or reject key reuse with drift."""

        safe_skill = require_resource_id(skill, "skill")
        safe_key = require_idempotency_key(idempotency_key)
        safe_digest = normalize_sha256(request_digest)
        with self._lock:
            self._require(self._connection, context, self.READ)
            row = self._connection.execute(
                """
                SELECT request_digest,status,response_json,response_digest,http_status,
                       lease_expires_at,dispatch_started_at
                  FROM skill_execution_receipts
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND skill=? AND idempotency_key=?
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_skill,
                    safe_key,
                ),
            ).fetchone()
        if row is None:
            return None
        if not hmac.compare_digest(row["request_digest"], safe_digest):
            raise ConflictError("SKILL_EXECUTION_IDEMPOTENCY_CONFLICT")
        if row["status"] == "IN_PROGRESS":
            if row["dispatch_started_at"] is not None:
                raise ConflictError(
                    "SKILL_EXECUTION_OUTCOME_RECONCILIATION_REQUIRED",
                    retryable=False,
                    details={"automatic_retry_allowed": False},
                )
            raise ConflictError(
                "SKILL_EXECUTION_IN_PROGRESS",
                retryable=True,
                details={"lease_expires_at": row["lease_expires_at"]},
            )
        return self._execution_receipt_body(row)

    def claim_skill_execution(
        self,
        context: TenantContext,
        *,
        skill: str,
        idempotency_key: str,
        request_digest: str,
        owner_token: str,
        lease_seconds: int = 300,
        required_permission: str = WRITE,
        retry_safe_internal: bool = False,
    ) -> tuple[str, tuple[int, dict[str, Any]] | None]:
        """Atomically claim an exact execution, replay it, or report a live lease.

        ``retry_safe_internal`` is deliberately restricted to the explicit
        store-owned allowlist.  Such mutations are monotone, actor-bound and
        transactionally idempotent, so a crash may reclaim even an older
        generic dispatch marker.  Provider and other external effects retain
        the normal reconciliation-only fence.
        """

        safe_skill = require_resource_id(skill, "skill")
        safe_key = require_idempotency_key(idempotency_key)
        safe_digest = normalize_sha256(request_digest)
        safe_owner = require_idempotency_key(owner_token)
        receipt_permission = self._receipt_permission(required_permission)
        if not isinstance(retry_safe_internal, bool):
            raise ValidationError("SKILL_EXECUTION_RETRY_MODE_INVALID")
        if retry_safe_internal and safe_skill not in self._RETRY_SAFE_INTERNAL_RECEIPT_SKILLS:
            raise ValidationError("SKILL_EXECUTION_RETRY_MODE_FORBIDDEN")
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 86_400:
            raise ValidationError("SKILL_EXECUTION_LEASE_INVALID")
        now_dt = datetime.now(UTC).replace(microsecond=0)
        now = now_dt.isoformat()
        lease_expires_at = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        with self.transaction() as connection:
            self._require(connection, context, receipt_permission)
            row = connection.execute(
                """
                SELECT * FROM skill_execution_receipts
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND skill=? AND idempotency_key=?
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_skill,
                    safe_key,
                ),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO skill_execution_receipts (
                        tenant_id,project_id,actor_id,skill,idempotency_key,request_digest,
                        status,owner_token,lease_expires_at,response_json,http_status,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?, 'IN_PROGRESS',?,?,NULL,NULL,?,?)
                    """,
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        safe_skill,
                        safe_key,
                        safe_digest,
                        safe_owner,
                        lease_expires_at,
                        now,
                        now,
                    ),
                )
                return "CLAIMED", None
            if not hmac.compare_digest(row["request_digest"], safe_digest):
                raise ConflictError("SKILL_EXECUTION_IDEMPOTENCY_CONFLICT")
            if row["status"] == "COMPLETED":
                try:
                    return "REPLAY", self._execution_receipt_body(row)
                except ConflictError as error:
                    if error.code != "SKILL_EXECUTION_OUTCOME_RECONCILIATION_REQUIRED":
                        raise
                    return "RECONCILIATION_REQUIRED", None
            if retry_safe_internal:
                changed = connection.execute(
                    """
                    UPDATE skill_execution_receipts
                       SET owner_token=?,lease_expires_at=?,dispatch_started_at=NULL,updated_at=?
                     WHERE tenant_id=? AND project_id=? AND actor_id=?
                       AND skill=? AND idempotency_key=? AND status='IN_PROGRESS'
                    """,
                    (
                        safe_owner,
                        lease_expires_at,
                        now,
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        safe_skill,
                        safe_key,
                    ),
                ).rowcount
                if changed != 1:
                    raise ConflictError("SKILL_EXECUTION_LEASE_NOT_OWNED")
                return "CLAIMED", None
            # Once dispatch has durably started, expiry is not authority to
            # invoke the handler again.  The original owner may still publish
            # its exact result, but every new claimant must reconcile.
            if row["dispatch_started_at"] is not None:
                return "RECONCILIATION_REQUIRED", None
            if row["owner_token"] == safe_owner or str(row["lease_expires_at"]) <= now:
                connection.execute(
                    """
                    UPDATE skill_execution_receipts
                       SET owner_token=?,lease_expires_at=?,updated_at=?
                     WHERE tenant_id=? AND project_id=? AND actor_id=?
                       AND skill=? AND idempotency_key=? AND status='IN_PROGRESS'
                    """,
                    (
                        safe_owner,
                        lease_expires_at,
                        now,
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        safe_skill,
                        safe_key,
                    ),
                )
                return "CLAIMED", None
            return "IN_PROGRESS", None

    def mark_skill_execution_dispatched(
        self,
        context: TenantContext,
        *,
        skill: str,
        idempotency_key: str,
        request_digest: str,
        owner_token: str,
        required_permission: str = WRITE,
        job_id: str | None = None,
    ) -> str:
        """Durably fence an execution immediately before handler dispatch.

        A marked receipt is never eligible for lease-expiry takeover.  This
        deliberately prefers an explicit reconciliation state over repeating
        an external effect after a process or response-loss crash.
        """

        safe_skill = require_resource_id(skill, "skill")
        safe_key = require_idempotency_key(idempotency_key)
        safe_digest = normalize_sha256(request_digest)
        safe_owner = require_idempotency_key(owner_token)
        receipt_permission = self._receipt_permission(required_permission)
        now = utc_now()
        with self.transaction() as connection:
            self._require(connection, context, receipt_permission)
            if job_id is not None:
                safe_job_id = require_resource_id(job_id, "job_id")
                job = self._scoped_job(connection, context, safe_job_id)
                if (
                    job["status"] != JobStatus.RUNNING.value
                    or job["lease_owner"] != safe_owner
                ):
                    raise ConflictError("PROCESSING_JOB_LEASE_NOT_OWNED")
                if job["cancel_requested"]:
                    raise ConflictError("PROCESSING_JOB_CANCELLATION_REQUESTED")
            row = connection.execute(
                """
                SELECT request_digest,status,owner_token,lease_expires_at,
                       dispatch_started_at
                  FROM skill_execution_receipts
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND skill=? AND idempotency_key=?
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_skill,
                    safe_key,
                ),
            ).fetchone()
            if row is None:
                raise ConflictError("SKILL_EXECUTION_CLAIM_REQUIRED")
            if not hmac.compare_digest(row["request_digest"], safe_digest):
                raise ConflictError("SKILL_EXECUTION_IDEMPOTENCY_CONFLICT")
            if row["status"] != "IN_PROGRESS" or row["owner_token"] != safe_owner:
                raise ConflictError("SKILL_EXECUTION_LEASE_NOT_OWNED")
            if row["dispatch_started_at"] is not None:
                return str(row["dispatch_started_at"])
            if str(row["lease_expires_at"] or "") <= now:
                raise ConflictError("SKILL_EXECUTION_LEASE_NOT_OWNED")
            changed = connection.execute(
                """
                UPDATE skill_execution_receipts
                   SET dispatch_started_at=?,updated_at=?
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND skill=? AND idempotency_key=? AND status='IN_PROGRESS'
                   AND owner_token=? AND lease_expires_at>?
                   AND dispatch_started_at IS NULL
                """,
                (
                    now,
                    now,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_skill,
                    safe_key,
                    safe_owner,
                    now,
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("SKILL_EXECUTION_LEASE_NOT_OWNED")
        return now

    def complete_skill_execution(
        self,
        context: TenantContext,
        *,
        skill: str,
        idempotency_key: str,
        request_digest: str,
        owner_token: str,
        http_status: int,
        response: Mapping[str, Any],
        required_permission: str = WRITE,
    ) -> tuple[int, dict[str, Any]]:
        """Complete a claimed execution; only its current lease owner may publish."""

        safe_skill = require_resource_id(skill, "skill")
        safe_key = require_idempotency_key(idempotency_key)
        safe_digest = normalize_sha256(request_digest)
        safe_owner = require_idempotency_key(owner_token)
        receipt_permission = self._receipt_permission(required_permission)
        if not isinstance(http_status, int) or isinstance(http_status, bool) or not 200 <= http_status <= 599:
            raise ValidationError("SKILL_EXECUTION_HTTP_STATUS_INVALID")
        serialized = canonical_json(response)
        serialized_bytes = serialized.encode("utf-8")
        if len(serialized_bytes) > self._MAX_EXECUTION_RECEIPT_BYTES:
            raise ValidationError("SKILL_EXECUTION_RECEIPT_TOO_LARGE")
        response_digest = sha256_bytes(serialized_bytes)
        now = utc_now()
        with self.transaction() as connection:
            self._require(connection, context, receipt_permission)
            row = connection.execute(
                """
                SELECT * FROM skill_execution_receipts
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND skill=? AND idempotency_key=?
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_skill,
                    safe_key,
                ),
            ).fetchone()
            if row is None:
                raise ConflictError("SKILL_EXECUTION_CLAIM_REQUIRED")
            if not hmac.compare_digest(row["request_digest"], safe_digest):
                raise ConflictError("SKILL_EXECUTION_IDEMPOTENCY_CONFLICT")
            if row["status"] == "COMPLETED":
                return self._execution_receipt_body(row)
            dispatched = row["dispatch_started_at"] is not None
            if row["owner_token"] != safe_owner or (
                not dispatched and str(row["lease_expires_at"] or "") <= now
            ):
                raise ConflictError("SKILL_EXECUTION_LEASE_NOT_OWNED")
            changed = connection.execute(
                """
                UPDATE skill_execution_receipts
                   SET status='COMPLETED',owner_token=NULL,lease_expires_at=NULL,
                       response_json=?,response_digest=?,http_status=?,updated_at=?
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND skill=? AND idempotency_key=? AND status='IN_PROGRESS'
                   AND owner_token=?
                   AND (dispatch_started_at IS NOT NULL OR lease_expires_at>?)
                """,
                (
                    serialized,
                    response_digest,
                    http_status,
                    now,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_skill,
                    safe_key,
                    safe_owner,
                    now,
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("SKILL_EXECUTION_LEASE_NOT_OWNED")
        return http_status, dict(response)

    def renew_skill_execution(
        self,
        context: TenantContext,
        *,
        skill: str,
        idempotency_key: str,
        request_digest: str,
        owner_token: str,
        lease_seconds: int = 300,
        required_permission: str = WRITE,
    ) -> str:
        """Extend a live execution lease without permitting stale-owner resurrection."""

        safe_skill = require_resource_id(skill, "skill")
        safe_key = require_idempotency_key(idempotency_key)
        safe_digest = normalize_sha256(request_digest)
        safe_owner = require_idempotency_key(owner_token)
        receipt_permission = self._receipt_permission(required_permission)
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 86_400:
            raise ValidationError("SKILL_EXECUTION_LEASE_INVALID")
        now_dt = datetime.now(UTC).replace(microsecond=0)
        now = now_dt.isoformat()
        lease_expires_at = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        with self.transaction() as connection:
            self._require(connection, context, receipt_permission)
            row = connection.execute(
                """
                SELECT * FROM skill_execution_receipts
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND skill=? AND idempotency_key=?
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_skill,
                    safe_key,
                ),
            ).fetchone()
            if row is None:
                raise ConflictError("SKILL_EXECUTION_CLAIM_REQUIRED")
            if not hmac.compare_digest(row["request_digest"], safe_digest):
                raise ConflictError("SKILL_EXECUTION_IDEMPOTENCY_CONFLICT")
            dispatched = row["dispatch_started_at"] is not None
            if (
                row["status"] != "IN_PROGRESS"
                or row["owner_token"] != safe_owner
                or (not dispatched and str(row["lease_expires_at"] or "") <= now)
            ):
                raise ConflictError("SKILL_EXECUTION_LEASE_NOT_OWNED")
            changed = connection.execute(
                """
                UPDATE skill_execution_receipts
                   SET lease_expires_at=?,updated_at=?
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND skill=? AND idempotency_key=? AND status='IN_PROGRESS'
                   AND owner_token=?
                   AND (dispatch_started_at IS NOT NULL OR lease_expires_at>?)
                """,
                (
                    lease_expires_at,
                    now,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_skill,
                    safe_key,
                    safe_owner,
                    now,
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("SKILL_EXECUTION_LEASE_NOT_OWNED")
        return lease_expires_at

    def release_skill_execution(
        self,
        context: TenantContext,
        *,
        skill: str,
        idempotency_key: str,
        request_digest: str,
        owner_token: str,
        required_permission: str = WRITE,
    ) -> bool:
        """Release an unfinished claim after a side-effect-free failure."""

        safe_skill = require_resource_id(skill, "skill")
        safe_key = require_idempotency_key(idempotency_key)
        safe_digest = normalize_sha256(request_digest)
        safe_owner = require_idempotency_key(owner_token)
        receipt_permission = self._receipt_permission(required_permission)
        with self.transaction() as connection:
            self._require(connection, context, receipt_permission)
            row = connection.execute(
                """
                SELECT request_digest,status,owner_token,dispatch_started_at
                  FROM skill_execution_receipts
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND skill=? AND idempotency_key=?
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_skill,
                    safe_key,
                ),
            ).fetchone()
            if row is None:
                return False
            if not hmac.compare_digest(row["request_digest"], safe_digest):
                raise ConflictError("SKILL_EXECUTION_IDEMPOTENCY_CONFLICT")
            if row["status"] == "COMPLETED":
                return False
            if row["owner_token"] != safe_owner:
                raise ConflictError("SKILL_EXECUTION_LEASE_NOT_OWNED")
            if row["dispatch_started_at"] is not None:
                raise ConflictError(
                    "SKILL_EXECUTION_ALREADY_DISPATCHED",
                    retryable=False,
                )
            connection.execute(
                """
                DELETE FROM skill_execution_receipts
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND skill=? AND idempotency_key=? AND status='IN_PROGRESS'
                   AND owner_token=? AND dispatch_started_at IS NULL
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_skill,
                    safe_key,
                    safe_owner,
                ),
            )
            return True

    def save_skill_execution_receipt(
        self,
        context: TenantContext,
        *,
        skill: str,
        idempotency_key: str,
        request_digest: str,
        http_status: int,
        response: Mapping[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        """Persist the first exact result; concurrent identical calls replay it."""

        safe_skill = require_resource_id(skill, "skill")
        safe_key = require_idempotency_key(idempotency_key)
        safe_digest = normalize_sha256(request_digest)
        if not isinstance(http_status, int) or isinstance(http_status, bool) or not 200 <= http_status <= 599:
            raise ValidationError("SKILL_EXECUTION_HTTP_STATUS_INVALID")
        serialized = canonical_json(response)
        serialized_bytes = serialized.encode("utf-8")
        if len(serialized_bytes) > self._MAX_EXECUTION_RECEIPT_BYTES:
            raise ValidationError("SKILL_EXECUTION_RECEIPT_TOO_LARGE")
        response_digest = sha256_bytes(serialized_bytes)
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            existing = connection.execute(
                """
                SELECT request_digest,status,response_json,response_digest,http_status
                  FROM skill_execution_receipts
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND skill=? AND idempotency_key=?
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_skill,
                    safe_key,
                ),
            ).fetchone()
            if existing is not None:
                if not hmac.compare_digest(existing["request_digest"], safe_digest):
                    raise ConflictError("SKILL_EXECUTION_IDEMPOTENCY_CONFLICT")
                if existing["status"] == "IN_PROGRESS":
                    raise ConflictError("SKILL_EXECUTION_IN_PROGRESS", retryable=True)
                return self._execution_receipt_body(existing)
            connection.execute(
                """
                INSERT INTO skill_execution_receipts (
                    tenant_id,project_id,actor_id,skill,idempotency_key,
                    request_digest,status,owner_token,lease_expires_at,
                    response_json,response_digest,http_status,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,'COMPLETED',NULL,NULL,?,?,?,?,?)
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_skill,
                    safe_key,
                    safe_digest,
                    serialized,
                    response_digest,
                    http_status,
                    utc_now(),
                    utc_now(),
                ),
            )
        return http_status, dict(response)

    @classmethod
    def _execution_receipt_body(cls, row: sqlite3.Row) -> tuple[int, dict[str, Any]]:
        if row["status"] != "COMPLETED":
            raise IntegrityError("SKILL_EXECUTION_RECEIPT_INCOMPLETE")
        if "response_digest" not in row.keys() or row["response_digest"] is None:
            raise ConflictError(
                "SKILL_EXECUTION_OUTCOME_RECONCILIATION_REQUIRED",
                retryable=False,
                details={
                    "automatic_retry_allowed": False,
                    "reason": "LEGACY_RESPONSE_DIGEST_MISSING",
                },
            )
        encoded = row["response_json"]
        if not isinstance(encoded, str) or not encoded:
            raise IntegrityError("SKILL_EXECUTION_RECEIPT_CORRUPT")
        try:
            encoded_bytes = encoded.encode("utf-8", errors="strict")
            if len(encoded_bytes) > cls._MAX_EXECUTION_RECEIPT_BYTES:
                raise ValueError("receipt exceeds the bounded replay size")
            stored_digest = normalize_sha256(row["response_digest"])
            body = json.loads(encoded)
            canonical = canonical_json(body)
        except Exception as error:
            raise IntegrityError("SKILL_EXECUTION_RECEIPT_CORRUPT") from error
        http_status = row["http_status"]
        if (
            not isinstance(body, dict)
            or canonical != encoded
            or row["response_digest"] != stored_digest
            or not hmac.compare_digest(stored_digest, sha256_bytes(encoded_bytes))
            or isinstance(http_status, bool)
            or not isinstance(http_status, int)
            or not 200 <= http_status <= 599
        ):
            raise IntegrityError("SKILL_EXECUTION_RECEIPT_CORRUPT")
        return http_status, body

    @staticmethod
    def _require(connection: sqlite3.Connection, context: TenantContext, permission: str) -> None:
        allowed = connection.execute(
            """
            SELECT 1 FROM project_acl
             WHERE tenant_id=? AND project_id=? AND principal_id=?
               AND permission IN (?, 'intake:admin') LIMIT 1
            """,
            (context.tenant_id, context.project_id, context.actor_id, permission),
        ).fetchone()
        if not allowed:
            raise AuthorizationError("INTAKE_PROJECT_ACCESS_DENIED")

    def create_session(
        self,
        context: TenantContext,
        *,
        idempotency_key: str,
        requested_role: str = "PRIMARY",
        trace_id: str | None = None,
    ) -> InputSession:
        idempotency_key = require_idempotency_key(idempotency_key)
        request = {"requested_role": requested_role}
        request_digest = canonical_digest(request)
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            existing = connection.execute(
                "SELECT * FROM input_sessions WHERE tenant_id=? AND project_id=? AND idempotency_key=?",
                (context.tenant_id, context.project_id, idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_digest"] != request_digest:
                    raise ConflictError("INPUT_SESSION_IDEMPOTENCY_CONFLICT")
                return self._session(existing)
            now = utc_now()
            session_id = new_id("ins")
            connection.execute(
                """
                INSERT INTO input_sessions (
                    session_id,tenant_id,project_id,created_by,requested_role,status,
                    idempotency_key,request_digest,trace_id,version,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    session_id,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    requested_role,
                    SessionStatus.DRAFT.value,
                    idempotency_key,
                    request_digest,
                    trace_id or new_id("trace"),
                    1,
                    now,
                    now,
                ),
            )
            self._event(
                connection,
                context,
                "input_session",
                session_id,
                "input.session.created",
                f"session-created:{session_id}",
                {"status": SessionStatus.DRAFT.value},
            )
            return self._session(
                connection.execute("SELECT * FROM input_sessions WHERE session_id=?", (session_id,)).fetchone()
            )

    def get_session(self, context: TenantContext, session_id: str, *, write: bool = False) -> InputSession:
        self.require(context, self.WRITE if write else self.READ)
        row = self._connection.execute(
            "SELECT * FROM input_sessions WHERE session_id=? AND tenant_id=? AND project_id=?",
            (session_id, context.tenant_id, context.project_id),
        ).fetchone()
        if not row:
            raise NotFoundError("INPUT_SESSION_NOT_FOUND")
        return self._session(row)

    def update_session_status(
        self,
        context: TenantContext,
        session_id: str,
        status: SessionStatus,
    ) -> InputSession:
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            row = self._scoped_session(connection, context, session_id)
            if row["status"] == SessionStatus.CANCELLED.value and status != SessionStatus.CANCELLED:
                raise ConflictError("INPUT_SESSION_CANCELLED")
            now = utc_now()
            connection.execute(
                "UPDATE input_sessions SET status=?,version=version+1,updated_at=? WHERE session_id=?",
                (status.value, now, session_id),
            )
            self._event(
                connection,
                context,
                "input_session",
                session_id,
                "input.session.status_changed",
                f"session-status:{session_id}:{status.value}:{row['version'] + 1}",
                {"from": row["status"], "to": status.value},
            )
            return self._session(connection.execute("SELECT * FROM input_sessions WHERE session_id=?", (session_id,)).fetchone())

    def create_upload(
        self,
        context: TenantContext,
        *,
        session_id: str,
        display_name: str,
        declared_media_type: str,
        expected_size: int,
        expected_sha256: str,
        part_size: int,
        idempotency_key: str,
        request_digest: str,
        expires_at: str,
    ) -> tuple[InputAsset, UploadSession]:
        idempotency_key = require_idempotency_key(idempotency_key)
        expected_sha256 = normalize_sha256(expected_sha256)
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            session = self._scoped_session(connection, context, session_id)
            existing = connection.execute(
                "SELECT * FROM upload_sessions WHERE tenant_id=? AND project_id=? AND idempotency_key=?",
                (context.tenant_id, context.project_id, idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_digest"] != request_digest:
                    raise ConflictError("UPLOAD_START_IDEMPOTENCY_CONFLICT")
                asset = connection.execute("SELECT * FROM input_assets WHERE asset_id=?", (existing["asset_id"],)).fetchone()
                return self._asset(asset), self._upload(existing)
            if session["status"] not in {SessionStatus.DRAFT.value, SessionStatus.UPLOADING.value}:
                raise ConflictError("INPUT_SESSION_UPLOADS_CLOSED")
            now = utc_now()
            asset_id = new_id("asset")
            upload_id = new_id("upload")
            connection.execute(
                """
                INSERT INTO input_assets (
                    asset_id,session_id,tenant_id,project_id,display_name,declared_media_type,
                    detected_media_type,kind,byte_size,sha256,cas_digest,status,security_decision,
                    failure_code,version,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    asset_id,
                    session_id,
                    context.tenant_id,
                    context.project_id,
                    display_name,
                    declared_media_type,
                    None,
                    AssetKind.UNKNOWN.value,
                    expected_size,
                    None,
                    None,
                    AssetStatus.UPLOADING.value,
                    None,
                    None,
                    1,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO upload_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    upload_id,
                    asset_id,
                    context.tenant_id,
                    context.project_id,
                    idempotency_key,
                    request_digest,
                    expected_size,
                    expected_sha256,
                    part_size,
                    UploadStatus.OPEN.value,
                    0,
                    None,
                    expires_at,
                    now,
                    now,
                ),
            )
            connection.execute(
                "UPDATE input_sessions SET status=?,version=version+1,updated_at=? WHERE session_id=?",
                (SessionStatus.UPLOADING.value, now, session_id),
            )
            self._event(
                connection,
                context,
                "upload",
                upload_id,
                "asset.upload.initialized",
                f"upload-start:{upload_id}",
                {"asset_id": asset_id, "expected_size": expected_size},
            )
            return (
                self._asset(connection.execute("SELECT * FROM input_assets WHERE asset_id=?", (asset_id,)).fetchone()),
                self._upload(connection.execute("SELECT * FROM upload_sessions WHERE upload_id=?", (upload_id,)).fetchone()),
            )

    def get_upload(self, context: TenantContext, upload_id: str, *, write: bool = False) -> UploadSession:
        self.require(context, self.WRITE if write else self.READ)
        row = self._connection.execute(
            "SELECT * FROM upload_sessions WHERE upload_id=? AND tenant_id=? AND project_id=?",
            (upload_id, context.tenant_id, context.project_id),
        ).fetchone()
        if not row:
            raise NotFoundError("UPLOAD_SESSION_NOT_FOUND")
        return self._upload(row)

    def record_part(
        self,
        context: TenantContext,
        upload_id: str,
        *,
        part_number: int,
        idempotency_key: str,
        byte_offset: int,
        byte_size: int,
        sha256: str,
        cas_digest: str,
    ) -> tuple[bool, int, int]:
        idempotency_key = require_idempotency_key(idempotency_key)
        sha256 = normalize_sha256(sha256)
        cas_digest = normalize_sha256(cas_digest)
        if part_number < 0 or byte_offset < 0 or byte_size <= 0 or sha256 != cas_digest:
            raise ValidationError("UPLOAD_PART_METADATA_INVALID")
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            upload = self._scoped_upload(connection, context, upload_id)
            expected_offset = part_number * upload["part_size"]
            expected_size = min(upload["part_size"], upload["expected_size"] - expected_offset)
            if byte_offset != expected_offset or byte_size != expected_size or expected_size <= 0:
                raise ValidationError("UPLOAD_PART_LAYOUT_INVALID")
            existing_key = connection.execute(
                """
                SELECT * FROM upload_parts
                 WHERE tenant_id=? AND project_id=? AND upload_id=? AND idempotency_key=?
                """,
                (context.tenant_id, context.project_id, upload_id, idempotency_key),
            ).fetchone()
            existing_part = connection.execute(
                """
                SELECT * FROM upload_parts
                 WHERE tenant_id=? AND project_id=? AND upload_id=? AND part_number=?
                """,
                (context.tenant_id, context.project_id, upload_id, part_number),
            ).fetchone()
            existing = existing_key or existing_part
            if existing:
                identical = (
                    existing["part_number"] == part_number
                    and existing["idempotency_key"] == idempotency_key
                    and existing["byte_offset"] == byte_offset
                    and existing["byte_size"] == byte_size
                    and existing["sha256"] == sha256
                    and existing["cas_digest"] == cas_digest
                )
                if not identical:
                    raise ConflictError("UPLOAD_PART_IDEMPOTENCY_CONFLICT")
                return True, upload["received_bytes"], self._next_offset(connection, upload)
            if upload["status"] != UploadStatus.OPEN.value:
                raise ConflictError("UPLOAD_SESSION_NOT_OPEN")
            connection.execute(
                "INSERT INTO upload_parts VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    upload_id,
                    context.tenant_id,
                    context.project_id,
                    part_number,
                    idempotency_key,
                    byte_offset,
                    byte_size,
                    sha256,
                    cas_digest,
                    utc_now(),
                ),
            )
            received = connection.execute(
                """
                SELECT coalesce(sum(byte_size),0) FROM upload_parts
                 WHERE tenant_id=? AND project_id=? AND upload_id=?
                """,
                (context.tenant_id, context.project_id, upload_id),
            ).fetchone()[0]
            now = utc_now()
            connection.execute(
                "UPDATE upload_sessions SET received_bytes=?,updated_at=? WHERE upload_id=?",
                (received, now, upload_id),
            )
            self._event(
                connection,
                context,
                "upload",
                upload_id,
                "asset.part.received",
                f"upload-part:{upload_id}:{part_number}:{sha256}",
                {"part_number": part_number, "byte_size": byte_size},
            )
            refreshed = connection.execute("SELECT * FROM upload_sessions WHERE upload_id=?", (upload_id,)).fetchone()
            return False, received, self._next_offset(connection, refreshed)

    def upload_parts(self, context: TenantContext, upload_id: str) -> list[sqlite3.Row]:
        self.get_upload(context, upload_id)
        return list(
            self._connection.execute(
                """
                SELECT * FROM upload_parts
                 WHERE tenant_id=? AND project_id=? AND upload_id=? ORDER BY part_number
                """,
                (context.tenant_id, context.project_id, upload_id),
            ).fetchall()
        )

    def complete_upload(
        self,
        context: TenantContext,
        upload_id: str,
        *,
        commit_idempotency_key: str,
        digest: str,
        byte_size: int,
    ) -> InputAsset:
        commit_idempotency_key = require_idempotency_key(commit_idempotency_key)
        digest = normalize_sha256(digest)
        if byte_size < 0:
            raise ValidationError("UPLOAD_COMMIT_SIZE_INVALID")
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            upload = self._scoped_upload(connection, context, upload_id)
            if digest != upload["expected_sha256"] or byte_size != upload["expected_size"]:
                raise IntegrityError("UPLOAD_COMMIT_DECLARATION_MISMATCH")
            if upload["status"] == UploadStatus.COMPLETED.value:
                if upload["commit_idempotency_key"] != commit_idempotency_key:
                    raise ConflictError("UPLOAD_COMMIT_IDEMPOTENCY_CONFLICT")
                return self._asset(connection.execute("SELECT * FROM input_assets WHERE asset_id=?", (upload["asset_id"],)).fetchone())
            if upload["status"] != UploadStatus.OPEN.value:
                raise ConflictError("UPLOAD_SESSION_NOT_OPEN")
            if digest != upload["expected_sha256"] or byte_size != upload["expected_size"]:
                raise IntegrityError("UPLOAD_COMMIT_DECLARATION_MISMATCH")
            now = utc_now()
            connection.execute(
                """
                UPDATE upload_sessions SET status=?,commit_idempotency_key=?,received_bytes=?,updated_at=?
                 WHERE upload_id=?
                """,
                (UploadStatus.COMPLETED.value, commit_idempotency_key, byte_size, now, upload_id),
            )
            connection.execute(
                """
                UPDATE input_assets SET sha256=?,cas_digest=?,byte_size=?,status=?,version=version+1,updated_at=?
                 WHERE asset_id=?
                """,
                (digest, digest, byte_size, AssetStatus.UPLOADED.value, now, upload["asset_id"]),
            )
            self._event(
                connection,
                context,
                "upload",
                upload_id,
                "asset.upload.completed",
                f"upload-commit:{upload_id}:{commit_idempotency_key}",
                {"asset_id": upload["asset_id"], "sha256": digest, "byte_size": byte_size},
            )
            return self._asset(connection.execute("SELECT * FROM input_assets WHERE asset_id=?", (upload["asset_id"],)).fetchone())

    def quarantine_upload(self, context: TenantContext, upload_id: str, code: str) -> None:
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            upload = self._scoped_upload(connection, context, upload_id)
            now = utc_now()
            connection.execute(
                "UPDATE upload_sessions SET status=?,updated_at=? WHERE upload_id=?",
                (UploadStatus.QUARANTINED.value, now, upload_id),
            )
            connection.execute(
                """
                UPDATE input_assets SET status=?,security_decision=?,failure_code=?,version=version+1,updated_at=?
                 WHERE asset_id=?
                """,
                (AssetStatus.QUARANTINED.value, SecurityDecision.QUARANTINE.value, code, now, upload["asset_id"]),
            )
            self._security_finding(connection, context, upload["asset_id"], SecurityDecision.QUARANTINE, code, {})

    def abort_upload(self, context: TenantContext, upload_id: str) -> UploadSession:
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            upload = self._scoped_upload(connection, context, upload_id)
            if upload["status"] == UploadStatus.COMPLETED.value:
                raise ConflictError("COMPLETED_UPLOAD_CANNOT_ABORT")
            if upload["status"] == UploadStatus.ABORTED.value:
                return self._upload(upload)
            if upload["status"] != UploadStatus.OPEN.value:
                raise ConflictError("UPLOAD_SESSION_NOT_OPEN")
            connection.execute(
                "UPDATE upload_sessions SET status=?,updated_at=? WHERE upload_id=?",
                (UploadStatus.ABORTED.value, utc_now(), upload_id),
            )
            connection.execute(
                "UPDATE input_assets SET status=?,failure_code=?,version=version+1,updated_at=? WHERE asset_id=?",
                (AssetStatus.FAILED.value, "UPLOAD_ABORTED", utc_now(), upload["asset_id"]),
            )
            return self._upload(connection.execute("SELECT * FROM upload_sessions WHERE upload_id=?", (upload_id,)).fetchone())

    def expire_upload(self, context: TenantContext, upload_id: str) -> UploadSession:
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            upload = self._scoped_upload(connection, context, upload_id)
            if upload["status"] == UploadStatus.COMPLETED.value:
                raise ConflictError("COMPLETED_UPLOAD_CANNOT_EXPIRE")
            connection.execute(
                "UPDATE upload_sessions SET status=?,updated_at=? WHERE upload_id=?",
                (UploadStatus.EXPIRED.value, utc_now(), upload_id),
            )
            connection.execute(
                "UPDATE input_assets SET status=?,failure_code=?,version=version+1,updated_at=? WHERE asset_id=?",
                (AssetStatus.FAILED.value, "UPLOAD_EXPIRED", utc_now(), upload["asset_id"]),
            )
            return self._upload(
                connection.execute("SELECT * FROM upload_sessions WHERE upload_id=?", (upload_id,)).fetchone()
            )

    def list_assets(self, context: TenantContext, session_id: str) -> list[InputAsset]:
        self.get_session(context, session_id)
        return [
            self._asset(row)
            for row in self._connection.execute(
                """
                SELECT * FROM input_assets
                 WHERE tenant_id=? AND project_id=? AND session_id=? ORDER BY created_at,asset_id
                """,
                (context.tenant_id, context.project_id, session_id),
            ).fetchall()
        ]

    def get_asset(self, context: TenantContext, asset_id: str, *, write: bool = False) -> InputAsset:
        self.require(context, self.WRITE if write else self.READ)
        row = self._connection.execute(
            "SELECT * FROM input_assets WHERE asset_id=? AND tenant_id=? AND project_id=?",
            (asset_id, context.tenant_id, context.project_id),
        ).fetchone()
        if not row:
            raise NotFoundError("INPUT_ASSET_NOT_FOUND")
        return self._asset(row)

    def prepare_human_review_correction(
        self,
        context: TenantContext,
        *,
        asset_id: str,
        idempotency_key: str,
        request_digest: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
        """Load a store-owned current snapshot or replay one exact correction.

        The caller never supplies the current value, scope, digest, or review
        state.  Those values are derived under the review ACL from the exact
        tenant/project asset and its latest immutable correction row.
        """

        safe_asset_id = require_resource_id(asset_id, "asset_id")
        safe_key = require_idempotency_key(idempotency_key)
        safe_request_digest = normalize_sha256(request_digest)
        with self._lock:
            self._require(self._connection, context, self.REVIEW)
            existing = self._connection.execute(
                """
                SELECT * FROM human_review_corrections
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND idempotency_key=?
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_key,
                ),
            ).fetchone()
            if existing is not None:
                if not hmac.compare_digest(existing["request_digest"], safe_request_digest):
                    raise ConflictError("HUMAN_REVIEW_IDEMPOTENCY_CONFLICT")
                if existing["asset_id"] != safe_asset_id:
                    raise IntegrityError("HUMAN_REVIEW_CORRECTION_SCOPE_INVALID")
                return None, None, self._human_review_result(existing)
            asset = self._scoped_asset(self._connection, context, safe_asset_id)
            self._require_human_review_asset_state(asset)
            current = self._human_review_current(self._connection, context, asset)
            return current, self._human_review_state(context, asset, current), None

    def commit_human_review_correction(
        self,
        context: TenantContext,
        *,
        asset_id: str,
        expected_version: int,
        expected_current_digest: str,
        idempotency_key: str,
        request_digest: str,
        domain_result: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Append one correction and advance the asset with an optimistic CAS."""

        safe_asset_id = require_resource_id(asset_id, "asset_id")
        safe_key = require_idempotency_key(idempotency_key)
        safe_request_digest = normalize_sha256(request_digest)
        safe_current_digest = normalize_sha256(expected_current_digest)
        if (
            not isinstance(expected_version, int)
            or isinstance(expected_version, bool)
            or not 1 <= expected_version <= MAX_SAFE_JSON_INTEGER - 1
        ):
            raise ValidationError("HUMAN_REVIEW_EXPECTED_VERSION_INVALID")
        with self.transaction() as connection:
            self._require(connection, context, self.REVIEW)
            existing = connection.execute(
                """
                SELECT * FROM human_review_corrections
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND idempotency_key=?
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_key,
                ),
            ).fetchone()
            if existing is not None:
                if not hmac.compare_digest(existing["request_digest"], safe_request_digest):
                    raise ConflictError("HUMAN_REVIEW_IDEMPOTENCY_CONFLICT")
                if existing["asset_id"] != safe_asset_id:
                    raise IntegrityError("HUMAN_REVIEW_CORRECTION_SCOPE_INVALID")
                return self._human_review_result(existing)

            asset = self._scoped_asset(connection, context, safe_asset_id)
            self._require_human_review_asset_state(asset)
            current = self._human_review_current(connection, context, asset)
            current_digest_value = current.get("digest")
            if not isinstance(current_digest_value, str):
                raise IntegrityError("HUMAN_REVIEW_CURRENT_STATE_INVALID")
            current_digest = normalize_sha256(current_digest_value)
            if asset["version"] != expected_version:
                raise ConflictError(
                    "OPTIMISTIC_LOCK_CONFLICT",
                    details={
                        "expected_version": expected_version,
                        "actual_version": int(asset["version"]),
                    },
                )
            if not hmac.compare_digest(current_digest, safe_current_digest):
                raise ConflictError("HUMAN_REVIEW_CURRENT_DRIFT")

            if (
                not isinstance(domain_result, Mapping)
                or set(domain_result) != {"state", "code", "outputs"}
                or domain_result.get("state") != "SUCCEEDED"
                or domain_result.get("code") != "CORRECTION_VERSION_CREATED"
            ):
                raise IntegrityError("HUMAN_REVIEW_DOMAIN_RESULT_INVALID")
            outputs = domain_result.get("outputs")
            if not isinstance(outputs, Mapping) or set(outputs) != {
                "correction",
                "approval_state",
                "rebuild_tasks",
                "rollback_to_digest",
            }:
                raise IntegrityError("HUMAN_REVIEW_DOMAIN_RESULT_INVALID")
            correction = outputs.get("correction")
            if not isinstance(correction, Mapping):
                raise IntegrityError("HUMAN_REVIEW_CORRECTION_INVALID")
            correction_document = dict(correction)
            correction_digest_value = correction_document.get("digest")
            if not isinstance(correction_digest_value, str):
                raise IntegrityError("HUMAN_REVIEW_CORRECTION_INVALID")
            correction_digest = normalize_sha256(correction_digest_value)
            correction_body = dict(correction_document)
            correction_body.pop("digest", None)
            new_version = expected_version + 1
            expected_rebuild_tasks = [
                {"task": task, "state": "NOT_RUN"}
                for task in self._HUMAN_REVIEW_REBUILD_TASKS
            ]
            if (
                set(correction_document) != self._HUMAN_REVIEW_CORRECTION_FIELDS
                or correction_document.get("digest") != f"sha256:{correction_digest}"
                or self._human_review_content_digest(
                    correction_body,
                    "HUMAN_REVIEW_CORRECTION_INVALID",
                )
                != f"sha256:{correction_digest}"
                or correction_document.get("content_id") != safe_asset_id
                or correction_document.get("tenant_id") != context.tenant_id
                or correction_document.get("project_id") != context.project_id
                or correction_document.get("actor") != context.actor_id
                or correction_document.get("version") != new_version
                or correction_document.get("idempotency_key") != safe_key
                or correction_document.get("supersedes_digest")
                != f"sha256:{safe_current_digest}"
                or not str(correction_document.get("policy_version", "")).strip()
                or not str(correction_document.get("review_state_version", "")).strip()
                or outputs.get("approval_state") != "NOT_RUN"
                or outputs.get("rebuild_tasks") != expected_rebuild_tasks
                or outputs.get("rollback_to_digest") != f"sha256:{safe_current_digest}"
            ):
                raise IntegrityError("HUMAN_REVIEW_CORRECTION_INVALID")

            now = utc_now()
            correction_id = (
                "correction-"
                + canonical_digest(
                    {
                        "tenant_id": context.tenant_id,
                        "project_id": context.project_id,
                        "asset_id": safe_asset_id,
                        "version": new_version,
                        "digest": f"sha256:{correction_digest}",
                    }
                )[:32]
            )
            persisted_outputs = dict(outputs)
            persisted_outputs.update(
                {
                    "asset_status": AssetStatus.NEEDS_REVIEW.value,
                    "asset_version": new_version,
                    "correction_persisted": True,
                    "original_version_preserved": True,
                    "rebuild_state": "NOT_RUN",
                }
            )
            persisted_result = {
                "state": "SUCCEEDED",
                "code": "CORRECTION_VERSION_CREATED",
                "outputs": persisted_outputs,
                "metrics": {},
                "retryable": False,
            }
            correction_json = self._human_review_content_json(
                correction_document,
                "HUMAN_REVIEW_CORRECTION_INVALID",
            )
            source_json = self._human_review_content_json(
                current,
                "HUMAN_REVIEW_ASSET_INTEGRITY_INVALID",
            )
            result_json = self._human_review_content_json(
                persisted_result,
                "HUMAN_REVIEW_RESULT_INVALID",
            )
            if (
                len(source_json.encode("utf-8")) > 2 * 1024 * 1024
                or len(correction_json.encode("utf-8")) > 2 * 1024 * 1024
            ):
                raise ValidationError("HUMAN_REVIEW_CORRECTION_TOO_LARGE")
            if len(result_json.encode("utf-8")) > 4 * 1024 * 1024:
                raise ValidationError("HUMAN_REVIEW_RESULT_TOO_LARGE")
            result_digest = normalize_sha256(
                self._human_review_content_digest(
                    persisted_result,
                    "HUMAN_REVIEW_RESULT_INVALID",
                )
            )
            connection.execute(
                """
                INSERT INTO human_review_corrections (
                    correction_id,tenant_id,project_id,actor_id,asset_id,
                    source_version,version,source_digest,source_json,correction_digest,
                    correction_json,idempotency_key,request_digest,policy_version,
                    review_state_version,approval_state,rebuild_state,result_json,
                    result_digest,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    correction_id,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_asset_id,
                    expected_version,
                    new_version,
                    safe_current_digest,
                    source_json,
                    correction_digest,
                    correction_json,
                    safe_key,
                    safe_request_digest,
                    str(correction_document["policy_version"]),
                    str(correction_document["review_state_version"]),
                    "NOT_RUN",
                    "NOT_RUN",
                    result_json,
                    result_digest,
                    now,
                ),
            )
            changed = connection.execute(
                """
                UPDATE input_assets
                   SET status=?,failure_code=NULL,version=?,updated_at=?
                 WHERE asset_id=? AND tenant_id=? AND project_id=? AND version=?
                """,
                (
                    AssetStatus.NEEDS_REVIEW.value,
                    new_version,
                    now,
                    safe_asset_id,
                    context.tenant_id,
                    context.project_id,
                    expected_version,
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("OPTIMISTIC_LOCK_CONFLICT")
            authoritative_source = self._publish_human_review_correction_source(
                connection,
                context,
                asset=asset,
                source_version=expected_version,
                asset_version=new_version,
                correction_id=correction_id,
                correction_document=correction_document,
                correction_digest=correction_digest,
                created_at=now,
            )
            self._event(
                connection,
                context,
                "input_asset",
                safe_asset_id,
                "human_review.correction.created",
                f"human-review-correction:{context.actor_id}:{safe_key}",
                {
                    "correction_id": correction_id,
                    "source_version": expected_version,
                    "version": new_version,
                    "source_digest": f"sha256:{safe_current_digest}",
                    "correction_digest": f"sha256:{correction_digest}",
                    "request_digest": f"sha256:{safe_request_digest}",
                    "approval_state": "NOT_RUN",
                    "rebuild_state": "NOT_RUN",
                    "authoritative_source": authoritative_source,
                },
            )
            return persisted_result

    @staticmethod
    def _human_review_content_json(value: Any, error_code: str) -> str:
        try:
            rendered = content_contract_json(value)
            rendered.encode("utf-8", errors="strict")
            return rendered
        except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as error:
            raise IntegrityError(error_code) from error

    @staticmethod
    def _human_review_content_digest(value: Any, error_code: str) -> str:
        try:
            return content_contract_digest(value)
        except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as error:
            raise IntegrityError(error_code) from error

    @classmethod
    def _require_human_review_asset_state(cls, asset: sqlite3.Row) -> None:
        if (
            asset["status"] not in cls._HUMAN_REVIEW_ASSET_STATES
            or asset["security_decision"] == SecurityDecision.QUARANTINE.value
        ):
            raise ConflictError(
                "HUMAN_REVIEW_ASSET_STATE_CONFLICT",
                details={"asset_status": str(asset["status"])},
            )
        try:
            source_digest = normalize_sha256(asset["sha256"])
            cas_digest = normalize_sha256(asset["cas_digest"])
        except ValidationError as error:
            raise IntegrityError("HUMAN_REVIEW_ASSET_INTEGRITY_INVALID") from error
        if not hmac.compare_digest(source_digest, cas_digest):
            raise IntegrityError("HUMAN_REVIEW_ASSET_INTEGRITY_INVALID")

    @classmethod
    def _human_review_current(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        asset: sqlite3.Row,
    ) -> dict[str, Any]:
        latest = connection.execute(
            """
            SELECT * FROM human_review_corrections
             WHERE tenant_id=? AND project_id=? AND asset_id=?
             ORDER BY version DESC,correction_id DESC LIMIT 1
            """,
            (context.tenant_id, context.project_id, asset["asset_id"]),
        ).fetchone()
        if latest is not None:
            current = cls._human_review_correction(latest)
            if current.get("version") != asset["version"]:
                raise ConflictError("HUMAN_REVIEW_CURRENT_VERSION_DRIFT")
            return current
        value = {
            "source": "input_asset",
            "asset_id": asset["asset_id"],
            "session_id": asset["session_id"],
            "display_name": asset["display_name"],
            "declared_media_type": asset["declared_media_type"],
            "detected_media_type": asset["detected_media_type"],
            "kind": asset["kind"],
            "byte_size": asset["byte_size"],
            "content_digest": (
                f"sha256:{asset['sha256']}" if asset["sha256"] is not None else None
            ),
            "cas_digest": (
                f"sha256:{asset['cas_digest']}" if asset["cas_digest"] is not None else None
            ),
            "status": asset["status"],
            "security_decision": asset["security_decision"],
            "failure_code": asset["failure_code"],
            "created_at": asset["created_at"],
            "updated_at": asset["updated_at"],
        }
        body = {
            "content_id": asset["asset_id"],
            "version": asset["version"],
            "value": value,
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
        }
        return {
            **body,
            "digest": cls._human_review_content_digest(
                body,
                "HUMAN_REVIEW_ASSET_INTEGRITY_INVALID",
            ),
        }

    @staticmethod
    def _human_review_state(
        context: TenantContext,
        asset: sqlite3.Row,
        current: Mapping[str, Any],
    ) -> dict[str, Any]:
        digest_value = current.get("digest")
        if not isinstance(digest_value, str):
            raise IntegrityError("HUMAN_REVIEW_CURRENT_STATE_INVALID")
        digest = normalize_sha256(digest_value)
        state = {
            "version": "store-human-review-state-v1",
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "content_id": asset["asset_id"],
            "current_version": asset["version"],
            "current_digest": f"sha256:{digest}",
            "asset_status": asset["status"],
        }
        state["state_digest"] = f"sha256:{canonical_digest(state)}"
        return state

    @classmethod
    def _human_review_correction(cls, row: sqlite3.Row) -> dict[str, Any]:
        try:
            source = json.loads(row["source_json"])
            correction = json.loads(row["correction_json"])
        except (TypeError, UnicodeError, json.JSONDecodeError, RecursionError) as error:
            raise IntegrityError("HUMAN_REVIEW_CORRECTION_CORRUPT") from error
        if not isinstance(source, dict) or not isinstance(correction, dict):
            raise IntegrityError("HUMAN_REVIEW_CORRECTION_CORRUPT")
        source_body = dict(source)
        source_digest = source_body.pop("digest", None)
        body = dict(correction)
        digest = body.pop("digest", None)
        idempotency_binding_digest = cls._human_review_content_digest(
            {
                "tenant_id": row["tenant_id"],
                "project_id": row["project_id"],
                "skill": "elmos-human-review-and-correction",
                "idempotency_key": row["idempotency_key"],
                "current_digest": f"sha256:{row['source_digest']}",
                "correction": {
                    "expected_version": row["source_version"],
                    "value": correction.get("value"),
                    "reason": correction.get("reason"),
                },
            },
            "HUMAN_REVIEW_CORRECTION_CORRUPT",
        )
        if (
            set(correction) != cls._HUMAN_REVIEW_CORRECTION_FIELDS
            or cls._human_review_content_json(
                source,
                "HUMAN_REVIEW_CORRECTION_CORRUPT",
            )
            != row["source_json"]
            or source_digest != f"sha256:{row['source_digest']}"
            or cls._human_review_content_digest(
                source_body,
                "HUMAN_REVIEW_CORRECTION_CORRUPT",
            )
            != f"sha256:{row['source_digest']}"
            or source.get("content_id") != row["asset_id"]
            or source.get("tenant_id") != row["tenant_id"]
            or source.get("project_id") != row["project_id"]
            or source.get("version") != row["source_version"]
            or cls._human_review_content_json(
                correction,
                "HUMAN_REVIEW_CORRECTION_CORRUPT",
            )
            != row["correction_json"]
            or digest != f"sha256:{row['correction_digest']}"
            or cls._human_review_content_digest(
                body,
                "HUMAN_REVIEW_CORRECTION_CORRUPT",
            )
            != f"sha256:{row['correction_digest']}"
            or correction.get("content_id") != row["asset_id"]
            or correction.get("tenant_id") != row["tenant_id"]
            or correction.get("project_id") != row["project_id"]
            or correction.get("actor") != row["actor_id"]
            or correction.get("version") != row["version"]
            or correction.get("idempotency_key") != row["idempotency_key"]
            or correction.get("idempotency_binding_digest")
            != idempotency_binding_digest
            or correction.get("supersedes_digest")
            != f"sha256:{row['source_digest']}"
            or correction.get("policy_version") != row["policy_version"]
            or correction.get("review_state_version") != row["review_state_version"]
            or row["approval_state"] != "NOT_RUN"
            or row["rebuild_state"] != "NOT_RUN"
            or row["version"] != row["source_version"] + 1
        ):
            raise IntegrityError("HUMAN_REVIEW_CORRECTION_CORRUPT")
        return correction

    @classmethod
    def _human_review_result(cls, row: sqlite3.Row) -> dict[str, Any]:
        correction = cls._human_review_correction(row)
        try:
            result = json.loads(row["result_json"])
        except (TypeError, UnicodeError, json.JSONDecodeError, RecursionError) as error:
            raise IntegrityError("HUMAN_REVIEW_RESULT_CORRUPT") from error
        if (
            not isinstance(result, dict)
            or set(result) != {"state", "code", "outputs", "metrics", "retryable"}
            or result.get("state") != "SUCCEEDED"
            or result.get("code") != "CORRECTION_VERSION_CREATED"
            or result.get("retryable") is not False
            or result.get("metrics") != {}
            or cls._human_review_content_json(
                result,
                "HUMAN_REVIEW_RESULT_CORRUPT",
            )
            != row["result_json"]
            or cls._human_review_content_digest(
                result,
                "HUMAN_REVIEW_RESULT_CORRUPT",
            )
            != f"sha256:{row['result_digest']}"
        ):
            raise IntegrityError("HUMAN_REVIEW_RESULT_CORRUPT")
        outputs = result.get("outputs")
        if (
            not isinstance(outputs, dict)
            or outputs.get("correction") != correction
            or outputs.get("approval_state") != row["approval_state"]
            or outputs.get("rebuild_state") != row["rebuild_state"]
            or outputs.get("asset_version") != row["version"]
            or outputs.get("asset_status") != AssetStatus.NEEDS_REVIEW.value
            or outputs.get("correction_persisted") is not True
            or outputs.get("original_version_preserved") is not True
        ):
            raise IntegrityError("HUMAN_REVIEW_RESULT_CORRUPT")
        return result

    def set_asset_result(
        self,
        context: TenantContext,
        asset_id: str,
        *,
        status: AssetStatus,
        kind: AssetKind | None = None,
        detected_media_type: str | None = None,
        security_decision: SecurityDecision | None = None,
        failure_code: str | None = None,
        expected_version: int | None = None,
        job_id: str | None = None,
        lease_owner: str | None = None,
    ) -> InputAsset:
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            row = self._scoped_asset(connection, context, asset_id)
            if expected_version is not None and row["version"] != expected_version:
                raise ConflictError("INPUT_ASSET_VERSION_CONFLICT")
            if job_id is not None:
                if lease_owner is None:
                    raise ConflictError("PROCESSING_JOB_LEASE_REQUIRED")
                self._require_job_lease(connection, context, job_id, lease_owner)
            changed = connection.execute(
                """
                UPDATE input_assets
                   SET status=?,kind=?,detected_media_type=?,security_decision=?,failure_code=?,
                       version=version+1,updated_at=?
                 WHERE asset_id=? AND tenant_id=? AND project_id=? AND version=?
                """,
                (
                    status.value,
                    (kind or AssetKind(row["kind"])).value,
                    detected_media_type if detected_media_type is not None else row["detected_media_type"],
                    security_decision.value if security_decision is not None else row["security_decision"],
                    failure_code,
                    utc_now(),
                    asset_id,
                    context.tenant_id,
                    context.project_id,
                    row["version"],
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("INPUT_ASSET_VERSION_CONFLICT")
            return self._asset(connection.execute("SELECT * FROM input_assets WHERE asset_id=?", (asset_id,)).fetchone())

    def add_security_findings(
        self,
        context: TenantContext,
        asset_id: str,
        decision: SecurityDecision,
        codes: Sequence[str],
    ) -> None:
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            self._scoped_asset(connection, context, asset_id)
            for code in sorted(set(codes)):
                self._security_finding(connection, context, asset_id, decision, code, {})

    @classmethod
    def _validate_job_transition(
        cls,
        current: sqlite3.Row,
        target_status: JobStatus,
        target_result: ResultStatus,
    ) -> JobStatus:
        try:
            current_status = JobStatus(current["status"])
            current_result = ResultStatus(current["result_status"])
        except (TypeError, ValueError) as error:
            raise IntegrityError("PROCESSING_JOB_STATE_CORRUPT") from error
        if current_result is not cls._JOB_RESULT_STATUS[current_status]:
            raise IntegrityError("PROCESSING_JOB_STATE_CORRUPT")
        if not isinstance(target_status, JobStatus) or not isinstance(target_result, ResultStatus):
            raise ValidationError("PROCESSING_JOB_STATE_INVALID")
        if target_result is not cls._JOB_RESULT_STATUS[target_status]:
            raise ConflictError(
                "PROCESSING_JOB_RESULT_STATUS_MISMATCH",
                details={
                    "status": target_status.value,
                    "required_result_status": cls._JOB_RESULT_STATUS[target_status].value,
                },
            )
        if target_status not in cls._JOB_TRANSITIONS[current_status]:
            code = (
                "PROCESSING_JOB_TERMINAL"
                if current_status in cls._TERMINAL_JOB_STATUSES
                else "PROCESSING_JOB_STATE_TRANSITION_INVALID"
            )
            raise ConflictError(
                code,
                details={
                    "current_status": current_status.value,
                    "target_status": target_status.value,
                },
            )
        return current_status

    @staticmethod
    def _next_job_version(current: sqlite3.Row) -> int:
        version = current["version"]
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or not 1 <= version < MAX_SAFE_JSON_INTEGER
        ):
            raise IntegrityError("PROCESSING_JOB_VERSION_INVALID")
        return int(version) + 1

    @classmethod
    def _validate_terminal_job_session_pair(
        cls,
        job_status: JobStatus,
        session_status: SessionStatus,
    ) -> None:
        allowed = cls._TERMINAL_JOB_SESSION_STATUSES.get(job_status)
        if allowed is None or session_status not in allowed:
            raise IntegrityError(
                "PROCESSING_JOB_SESSION_TERMINAL_STATE_MISMATCH",
                details={
                    "job_status": getattr(job_status, "value", str(job_status)),
                    "session_status": getattr(session_status, "value", str(session_status)),
                },
            )

    def create_job(
        self,
        context: TenantContext,
        session_id: str,
        *,
        idempotency_key: str,
        request_digest: str,
        max_attempts: int = 3,
    ) -> ProcessingJob:
        idempotency_key = require_idempotency_key(idempotency_key)
        request_digest = normalize_sha256(request_digest)
        if not 1 <= max_attempts <= 20:
            raise ValidationError("PROCESSING_JOB_MAX_ATTEMPTS_INVALID")
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            self._scoped_session(connection, context, session_id)
            existing = connection.execute(
                "SELECT * FROM processing_jobs WHERE tenant_id=? AND project_id=? AND idempotency_key=?",
                (context.tenant_id, context.project_id, idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_digest"] != request_digest or existing["session_id"] != session_id:
                    raise ConflictError("PROCESSING_JOB_IDEMPOTENCY_CONFLICT")
                return self._job(existing)
            now = utc_now()
            job_id = new_id("job")
            connection.execute(
                """
                INSERT INTO processing_jobs (
                    job_id,tenant_id,project_id,session_id,idempotency_key,request_digest,
                    status,stage,attempt,max_attempts,result_status,failure_code,
                    lease_owner,lease_expires_at,created_at,updated_at,version
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,?,?,1)
                """,
                (
                    job_id,
                    context.tenant_id,
                    context.project_id,
                    session_id,
                    idempotency_key,
                    request_digest,
                    JobStatus.QUEUED.value,
                    "queued",
                    0,
                    max_attempts,
                    ResultStatus.NOT_RUN.value,
                    None,
                    now,
                    now,
                ),
            )
            return self._job(connection.execute("SELECT * FROM processing_jobs WHERE job_id=?", (job_id,)).fetchone())

    def get_job(self, context: TenantContext, job_id: str, *, write: bool = False) -> ProcessingJob:
        with self._lock:
            self._require(self._connection, context, self.WRITE if write else self.READ)
            row = self._connection.execute(
                "SELECT * FROM processing_jobs WHERE job_id=? AND tenant_id=? AND project_id=?",
                (job_id, context.tenant_id, context.project_id),
            ).fetchone()
        if not row:
            raise NotFoundError("PROCESSING_JOB_NOT_FOUND")
        return self._job(row)

    def update_job(
        self,
        context: TenantContext,
        job_id: str,
        *,
        status: JobStatus,
        stage: str,
        result_status: ResultStatus,
        failure_code: str | None = None,
        increment_attempt: bool = False,
        lease_owner: str | None = None,
    ) -> ProcessingJob:
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            current = self._scoped_job(connection, context, job_id)
            try:
                current_status = JobStatus(current["status"])
                current_result = ResultStatus(current["result_status"])
            except (TypeError, ValueError) as error:
                raise IntegrityError("PROCESSING_JOB_STATE_CORRUPT") from error
            if current_result is not self._JOB_RESULT_STATUS[current_status]:
                raise IntegrityError("PROCESSING_JOB_STATE_CORRUPT")
            if not isinstance(status, JobStatus) or not isinstance(result_status, ResultStatus):
                raise ValidationError("PROCESSING_JOB_STATE_INVALID")
            if (
                current["cancel_requested"]
                and current_status not in self._TERMINAL_JOB_STATUSES
            ):
                raise ConflictError("PROCESSING_JOB_CANCELLATION_REQUESTED")
            if current_status in self._TERMINAL_JOB_STATUSES:
                if (
                    status is current_status
                    and stage == current["stage"]
                    and result_status is current_result
                    and failure_code == current["failure_code"]
                    and not increment_attempt
                    and lease_owner is None
                ):
                    return self._job(current)
                self._validate_job_transition(current, status, result_status)
            self._validate_job_transition(current, status, result_status)
            if current["status"] == JobStatus.RUNNING.value and status is not JobStatus.CANCELLED:
                if lease_owner is None or current["lease_owner"] != require_idempotency_key(lease_owner):
                    raise ConflictError("PROCESSING_JOB_LEASE_NOT_OWNED")
            attempt = current["attempt"] + (1 if increment_attempt else 0)
            if attempt > current["max_attempts"]:
                raise ConflictError("PROCESSING_JOB_ATTEMPT_LIMIT")
            if status is JobStatus.RUNNING:
                if lease_owner is None:
                    raise ConflictError("PROCESSING_JOB_CLAIM_REQUIRED")
                stored_owner = require_idempotency_key(lease_owner)
                lease_expires_at = current["lease_expires_at"]
                if not lease_expires_at:
                    raise ConflictError("PROCESSING_JOB_CLAIM_REQUIRED")
            else:
                stored_owner = None
                lease_expires_at = None
            next_version = self._next_job_version(current)
            changed = connection.execute(
                """
                UPDATE processing_jobs
                   SET status=?,stage=?,result_status=?,failure_code=?,attempt=?,
                       lease_owner=?,lease_expires_at=?,updated_at=?,version=?
                 WHERE job_id=? AND tenant_id=? AND project_id=? AND version=?
                """,
                (
                    status.value,
                    stage,
                    result_status.value,
                    failure_code,
                    attempt,
                    stored_owner,
                    lease_expires_at,
                    utc_now(),
                    next_version,
                    job_id,
                    context.tenant_id,
                    context.project_id,
                    current["version"],
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("PROCESSING_JOB_VERSION_CONFLICT")
            return self._job(connection.execute("SELECT * FROM processing_jobs WHERE job_id=?", (job_id,)).fetchone())

    def finalize_job_and_session(
        self,
        context: TenantContext,
        job_id: str,
        *,
        session_status: SessionStatus,
        status: JobStatus,
        stage: str,
        result_status: ResultStatus,
        failure_code: str | None = None,
        lease_owner: str | None = None,
    ) -> tuple[ProcessingJob, InputSession]:
        """Atomically choose and persist one consistent job/session terminal pair.

        The cancellation marker and terminal transition share the same SQLite
        writer fence.  If cancellation wins, this method canonicalizes both
        records to CANCELLED.  If terminalization wins, a later cancellation
        request observes and returns the already committed pair without
        changing the session.
        """

        if not isinstance(session_status, SessionStatus):
            raise ValidationError("INPUT_SESSION_STATUS_INVALID")
        if status not in self._TERMINAL_JOB_STATUSES:
            raise ValidationError("PROCESSING_JOB_TERMINAL_STATUS_REQUIRED")
        if not isinstance(result_status, ResultStatus):
            raise ValidationError("PROCESSING_JOB_STATE_INVALID")
        self._validate_terminal_job_session_pair(status, session_status)
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            current = self._scoped_job(connection, context, job_id)
            session = self._scoped_session(connection, context, current["session_id"])
            try:
                current_status = JobStatus(current["status"])
                current_result = ResultStatus(current["result_status"])
            except (TypeError, ValueError) as error:
                raise IntegrityError("PROCESSING_JOB_STATE_CORRUPT") from error
            if current_result is not self._JOB_RESULT_STATUS[current_status]:
                raise IntegrityError("PROCESSING_JOB_STATE_CORRUPT")
            if current_status in self._TERMINAL_JOB_STATUSES:
                try:
                    current_session_status = SessionStatus(session["status"])
                except (TypeError, ValueError) as error:
                    raise IntegrityError("INPUT_SESSION_STATE_CORRUPT") from error
                self._validate_terminal_job_session_pair(
                    current_status,
                    current_session_status,
                )
                return self._job(current), self._session(session)

            cancellation_won = bool(current["cancel_requested"])
            effective_job_status = JobStatus.CANCELLED if cancellation_won else status
            effective_result_status = (
                ResultStatus.BLOCKED if cancellation_won else result_status
            )
            effective_session_status = (
                SessionStatus.CANCELLED if cancellation_won else session_status
            )
            effective_stage = "cancelled" if cancellation_won else stage
            effective_failure = (
                str(current["cancel_reason"] or "CANCELLED_BY_CALLER")
                if cancellation_won
                else failure_code
            )
            self._validate_terminal_job_session_pair(
                effective_job_status,
                effective_session_status,
            )
            self._validate_job_transition(
                current,
                effective_job_status,
                effective_result_status,
            )
            if current_status is JobStatus.RUNNING:
                if lease_owner is None:
                    raise ConflictError("PROCESSING_JOB_LEASE_NOT_OWNED")
                safe_owner = require_idempotency_key(lease_owner)
                if current["lease_owner"] != safe_owner:
                    raise ConflictError("PROCESSING_JOB_LEASE_NOT_OWNED")

            if (
                session["status"] == SessionStatus.CANCELLED.value
                and effective_session_status is not SessionStatus.CANCELLED
            ):
                raise ConflictError("INPUT_SESSION_CANCELLED")
            now = utc_now()
            next_version = self._next_job_version(current)
            changed = connection.execute(
                """
                UPDATE processing_jobs
                   SET status=?,stage=?,result_status=?,failure_code=?,
                       lease_owner=NULL,lease_expires_at=NULL,updated_at=?,version=?
                 WHERE job_id=? AND tenant_id=? AND project_id=? AND version=?
                """,
                (
                    effective_job_status.value,
                    effective_stage,
                    effective_result_status.value,
                    effective_failure,
                    now,
                    next_version,
                    job_id,
                    context.tenant_id,
                    context.project_id,
                    current["version"],
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("PROCESSING_JOB_VERSION_CONFLICT")
            if session["status"] != effective_session_status.value:
                connection.execute(
                    """
                    UPDATE input_sessions SET status=?,version=version+1,updated_at=?
                     WHERE session_id=? AND tenant_id=? AND project_id=?
                    """,
                    (
                        effective_session_status.value,
                        now,
                        current["session_id"],
                        context.tenant_id,
                        context.project_id,
                    ),
                )
                self._event(
                    connection,
                    context,
                    "input_session",
                    current["session_id"],
                    "input.session.status_changed",
                    f"session-status:{current['session_id']}:{effective_session_status.value}:{session['version'] + 1}",
                    {"from": session["status"], "to": effective_session_status.value},
                )
            self._event(
                connection,
                context,
                "processing_job",
                job_id,
                "processing.job.terminalized",
                f"processing-job-terminal:{job_id}:{next_version}",
                {
                    "status": effective_job_status.value,
                    "session_status": effective_session_status.value,
                    "result_status": effective_result_status.value,
                    "stage": effective_stage,
                    "failure_code": effective_failure,
                    "cancel_requested": cancellation_won,
                    "cancel_requested_by": current["cancel_requested_by"],
                    "cancel_requested_at": current["cancel_requested_at"],
                    "cancel_reason": current["cancel_reason"],
                    "version": next_version,
                },
            )
            return (
                self._job(
                    connection.execute(
                        "SELECT * FROM processing_jobs WHERE job_id=?", (job_id,)
                    ).fetchone()
                ),
                self._session(
                    connection.execute(
                        "SELECT * FROM input_sessions WHERE session_id=?",
                        (current["session_id"],),
                    ).fetchone()
                ),
            )

    def request_job_cancellation(
        self,
        context: TenantContext,
        job_id: str,
        *,
        reason: str = "CANCELLED_BY_CALLER",
    ) -> tuple[ProcessingJob, InputSession]:
        """Durably request actor-bound cancellation under the terminal writer fence."""

        safe_reason = require_resource_id(reason, "cancel_reason")
        if len(safe_reason) > 128:
            raise ValidationError("PROCESSING_JOB_CANCELLATION_REASON_INVALID")
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            current = self._scoped_job(connection, context, job_id)
            session = self._scoped_session(connection, context, current["session_id"])
            try:
                status = JobStatus(current["status"])
            except (TypeError, ValueError) as error:
                raise IntegrityError("PROCESSING_JOB_STATE_CORRUPT") from error
            if status in self._TERMINAL_JOB_STATUSES:
                try:
                    current_session_status = SessionStatus(session["status"])
                except (TypeError, ValueError) as error:
                    raise IntegrityError("INPUT_SESSION_STATE_CORRUPT") from error
                self._validate_terminal_job_session_pair(
                    status,
                    current_session_status,
                )
                return self._job(current), self._session(session)
            if current["cancel_requested"]:
                if not all(
                    isinstance(current[name], str) and bool(current[name])
                    for name in (
                        "cancel_requested_by",
                        "cancel_requested_at",
                        "cancel_reason",
                    )
                ):
                    raise IntegrityError("PROCESSING_JOB_CANCELLATION_STATE_CORRUPT")
                if session["status"] == SessionStatus.CANCELLED.value:
                    raise IntegrityError(
                        "PROCESSING_JOB_SESSION_TERMINAL_STATE_MISMATCH"
                    )
                return self._job(current), self._session(session)
            requested_at = utc_now()
            next_version = self._next_job_version(current)
            terminalize_now = status is JobStatus.QUEUED
            changed = connection.execute(
                """
                UPDATE processing_jobs
                   SET cancel_requested=1,cancel_requested_by=?,cancel_requested_at=?,
                       cancel_reason=?,status=?,stage=?,result_status=?,failure_code=?,
                       lease_owner=?,lease_expires_at=?,updated_at=?,version=?
                 WHERE job_id=? AND tenant_id=? AND project_id=? AND version=?
                """,
                (
                    context.actor_id,
                    requested_at,
                    safe_reason,
                    JobStatus.CANCELLED.value if terminalize_now else current["status"],
                    "cancelled" if terminalize_now else current["stage"],
                    ResultStatus.BLOCKED.value if terminalize_now else current["result_status"],
                    safe_reason if terminalize_now else current["failure_code"],
                    None if terminalize_now else current["lease_owner"],
                    None if terminalize_now else current["lease_expires_at"],
                    requested_at,
                    next_version,
                    job_id,
                    context.tenant_id,
                    context.project_id,
                    current["version"],
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("PROCESSING_JOB_VERSION_CONFLICT")
            self._event(
                connection,
                context,
                "processing_job",
                job_id,
                "processing.job.cancellation_requested",
                f"processing-job-cancellation:{job_id}",
                {
                    "actor_id": context.actor_id,
                    "requested_at": requested_at,
                    "reason": safe_reason,
                    "job_status_at_request": status.value,
                    "terminalized_immediately": terminalize_now,
                },
            )
            if terminalize_now and session["status"] != SessionStatus.CANCELLED.value:
                connection.execute(
                    """
                    UPDATE input_sessions SET status=?,version=version+1,updated_at=?
                     WHERE session_id=? AND tenant_id=? AND project_id=?
                    """,
                    (
                        SessionStatus.CANCELLED.value,
                        requested_at,
                        current["session_id"],
                        context.tenant_id,
                        context.project_id,
                    ),
                )
                self._event(
                    connection,
                    context,
                    "input_session",
                    current["session_id"],
                    "input.session.status_changed",
                    f"session-status:{current['session_id']}:{SessionStatus.CANCELLED.value}:{session['version'] + 1}",
                    {"from": session["status"], "to": SessionStatus.CANCELLED.value},
                )
            return (
                self._job(
                    connection.execute(
                        "SELECT * FROM processing_jobs WHERE job_id=?", (job_id,)
                    ).fetchone()
                ),
                self._session(
                    connection.execute(
                        "SELECT * FROM input_sessions WHERE session_id=?",
                        (current["session_id"],),
                    ).fetchone()
                ),
            )

    def job_cancellation_requested(
        self,
        context: TenantContext,
        job_id: str,
    ) -> bool:
        with self._lock:
            self._require(self._connection, context, self.WRITE)
            current = self._scoped_job(self._connection, context, job_id)
            value = current["cancel_requested"]
        if value not in {0, 1}:
            raise IntegrityError("PROCESSING_JOB_CANCELLATION_STATE_CORRUPT")
        if value == 1 and not all(
            isinstance(current[name], str) and bool(current[name])
            for name in ("cancel_requested_by", "cancel_requested_at", "cancel_reason")
        ):
            raise IntegrityError("PROCESSING_JOB_CANCELLATION_STATE_CORRUPT")
        return bool(value)

    def claim_job(
        self,
        context: TenantContext,
        job_id: str,
        *,
        owner_token: str,
        stage: str = "asset-processing",
        lease_seconds: int = 300,
    ) -> ProcessingJob:
        """Atomically acquire or take over an expired processing lease."""

        safe_owner = require_idempotency_key(owner_token)
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 3600:
            raise ValidationError("PROCESSING_JOB_LEASE_INVALID")
        now_dt = datetime.now(UTC).replace(microsecond=0)
        now = now_dt.isoformat()
        expires_at = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            current = self._scoped_job(connection, context, job_id)
            try:
                status = JobStatus(current["status"])
            except (TypeError, ValueError) as error:
                raise IntegrityError("PROCESSING_JOB_STATE_CORRUPT") from error
            if status in self._TERMINAL_JOB_STATUSES:
                return self._job(current)
            if current["cancel_requested"]:
                raise ConflictError("PROCESSING_JOB_CANCELLATION_REQUESTED")
            if (
                status is JobStatus.RUNNING
                and current["lease_owner"] != safe_owner
                and str(current["lease_expires_at"] or "") > now
            ):
                raise ConflictError(
                    "PROCESSING_JOB_ALREADY_CLAIMED",
                    retryable=True,
                    details={"lease_expires_at": current["lease_expires_at"]},
                )
            if (
                status is JobStatus.RUNNING
                and str(current["lease_expires_at"] or "") <= now
                and str(current["stage"] or "").startswith("external-effect:")
            ):
                effect_key = self.job_effect_stage_key(job_id, str(current["stage"]))
                completed_effect = connection.execute(
                    """
                    SELECT payload_json,payload_sha256 FROM processing_checkpoints
                     WHERE tenant_id=? AND project_id=? AND job_id=? AND stage_key=?
                    """,
                    (
                        context.tenant_id,
                        context.project_id,
                        job_id,
                        effect_key,
                    ),
                ).fetchone()
                if completed_effect is None:
                    self._validate_job_transition(
                        current,
                        JobStatus.BLOCKED,
                        ResultStatus.BLOCKED,
                    )
                    next_version = self._next_job_version(current)
                    changed = connection.execute(
                        """
                        UPDATE processing_jobs
                           SET status=?,stage=?,result_status=?,failure_code=?,
                               lease_owner=NULL,lease_expires_at=NULL,updated_at=?,version=?
                         WHERE job_id=? AND tenant_id=? AND project_id=? AND version=?
                        """,
                        (
                            JobStatus.BLOCKED.value,
                            "external-effect-reconciliation-required",
                            ResultStatus.BLOCKED.value,
                            "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED",
                            now,
                            next_version,
                            job_id,
                            context.tenant_id,
                            context.project_id,
                            current["version"],
                        ),
                    ).rowcount
                    if changed != 1:
                        raise ConflictError("PROCESSING_JOB_VERSION_CONFLICT")
                    connection.execute(
                        """
                        UPDATE input_sessions SET status=?,version=version+1,updated_at=?
                         WHERE session_id=? AND tenant_id=? AND project_id=? AND status<>?
                        """,
                        (
                            SessionStatus.NEEDS_REVIEW.value,
                            now,
                            current["session_id"],
                            context.tenant_id,
                            context.project_id,
                            SessionStatus.CANCELLED.value,
                        ),
                    )
                    return self._job(
                        connection.execute("SELECT * FROM processing_jobs WHERE job_id=?", (job_id,)).fetchone()
                    )
                # A valid exact-stage effect receipt makes takeover safe.  Its
                # payload is still revalidated by the workflow before use.
                self._decode_job_effect_receipt(completed_effect)
            same_owner = status is JobStatus.RUNNING and current["lease_owner"] == safe_owner
            attempt = current["attempt"] if same_owner else current["attempt"] + 1
            if attempt > current["max_attempts"]:
                raise ConflictError("PROCESSING_JOB_ATTEMPT_LIMIT")
            self._validate_job_transition(
                current,
                JobStatus.RUNNING,
                ResultStatus.NOT_RUN,
            )
            next_version = self._next_job_version(current)
            changed = connection.execute(
                """
                UPDATE processing_jobs
                   SET status=?,stage=?,result_status=?,failure_code=NULL,attempt=?,
                       lease_owner=?,lease_expires_at=?,updated_at=?,version=?
                 WHERE job_id=? AND tenant_id=? AND project_id=? AND version=?
                """,
                (
                    JobStatus.RUNNING.value,
                    stage,
                    ResultStatus.NOT_RUN.value,
                    attempt,
                    safe_owner,
                    expires_at,
                    now,
                    next_version,
                    job_id,
                    context.tenant_id,
                    context.project_id,
                    current["version"],
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("PROCESSING_JOB_VERSION_CONFLICT")
            return self._job(connection.execute("SELECT * FROM processing_jobs WHERE job_id=?", (job_id,)).fetchone())

    def renew_job_lease(
        self,
        context: TenantContext,
        job_id: str,
        *,
        owner_token: str,
        lease_seconds: int = 300,
    ) -> ProcessingJob:
        safe_owner = require_idempotency_key(owner_token)
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 3600:
            raise ValidationError("PROCESSING_JOB_LEASE_INVALID")
        now_dt = datetime.now(UTC).replace(microsecond=0)
        expires_at = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            current = self._scoped_job(connection, context, job_id)
            if current["cancel_requested"]:
                raise ConflictError("PROCESSING_JOB_CANCELLATION_REQUESTED")
            if current["status"] != JobStatus.RUNNING.value or current["lease_owner"] != safe_owner:
                raise ConflictError("PROCESSING_JOB_LEASE_NOT_OWNED")
            self._validate_job_transition(
                current,
                JobStatus.RUNNING,
                ResultStatus.NOT_RUN,
            )
            next_version = self._next_job_version(current)
            changed = connection.execute(
                """
                UPDATE processing_jobs SET lease_expires_at=?,updated_at=?,version=?
                 WHERE job_id=? AND tenant_id=? AND project_id=?
                   AND status=? AND lease_owner=? AND version=?
                """,
                (
                    expires_at,
                    utc_now(),
                    next_version,
                    job_id,
                    context.tenant_id,
                    context.project_id,
                    JobStatus.RUNNING.value,
                    safe_owner,
                    current["version"],
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("PROCESSING_JOB_VERSION_CONFLICT")
            return self._job(connection.execute("SELECT * FROM processing_jobs WHERE job_id=?", (job_id,)).fetchone())

    def checkpoint_exists(self, context: TenantContext, job_id: str, stage_key: str) -> bool:
        self.get_job(context, job_id)
        return self._connection.execute(
            """
            SELECT 1 FROM processing_checkpoints
             WHERE tenant_id=? AND project_id=? AND job_id=? AND stage_key=?
            """,
            (context.tenant_id, context.project_id, job_id, stage_key),
        ).fetchone() is not None

    def save_checkpoint(
        self,
        context: TenantContext,
        job_id: str,
        stage_key: str,
        payload: dict[str, Any],
    ) -> None:
        safe_stage = require_resource_id(stage_key, "checkpoint_stage_key")
        if safe_stage.startswith("effect:"):
            raise ValidationError("CHECKPOINT_EFFECT_NAMESPACE_RESERVED")
        encoded = canonical_json(payload)
        digest = sha256_bytes(encoded.encode("utf-8"))
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            self._scoped_job(connection, context, job_id)
            existing = connection.execute(
                """
                SELECT payload_sha256 FROM processing_checkpoints
                 WHERE tenant_id=? AND project_id=? AND job_id=? AND stage_key=?
                """,
                (context.tenant_id, context.project_id, job_id, safe_stage),
            ).fetchone()
            if existing:
                if existing["payload_sha256"] != digest:
                    raise ConflictError("CHECKPOINT_IMMUTABILITY_CONFLICT")
                return
            connection.execute(
                "INSERT INTO processing_checkpoints VALUES (?,?,?,?,?,?,?)",
                (
                    job_id,
                    context.tenant_id,
                    context.project_id,
                    safe_stage,
                    encoded,
                    digest,
                    utc_now(),
                ),
            )

    def load_job_effect_receipt(
        self,
        context: TenantContext,
        job_id: str,
        stage_key: str,
        *,
        lease_owner: str,
    ) -> dict[str, Any] | None:
        """Load a tenant/project job effect only for its current lease owner."""

        safe_stage = require_resource_id(stage_key, "effect_stage_key")
        if not safe_stage.startswith("effect:"):
            raise ValidationError("JOB_EFFECT_STAGE_KEY_INVALID")
        safe_owner = require_idempotency_key(lease_owner)
        now = utc_now()
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            current = self._scoped_job(connection, context, job_id)
            self._require_external_effect_lease(current, safe_owner, now)
            row = connection.execute(
                """
                SELECT payload_json,payload_sha256 FROM processing_checkpoints
                 WHERE tenant_id=? AND project_id=? AND job_id=? AND stage_key=?
                """,
                (context.tenant_id, context.project_id, job_id, safe_stage),
            ).fetchone()
            if row is None:
                return None
            return self._decode_job_effect_receipt(row)

    @staticmethod
    def job_effect_stage_key(job_id: str, external_effect_stage: str) -> str:
        """Derive the exact checkpoint key shared by claim and execution."""

        safe_job = require_resource_id(job_id, "job_id")
        safe_stage = require_resource_id(
            external_effect_stage,
            "external_effect_stage",
        )
        if not safe_stage.startswith("external-effect:"):
            raise ValidationError("JOB_EFFECT_STAGE_INVALID")
        return "effect:" + canonical_digest(
            {
                "schema_version": "elmos-job-effect-stage-v1",
                "job_id": safe_job,
                "external_effect_stage": safe_stage,
            }
        )

    def save_job_effect_receipt(
        self,
        context: TenantContext,
        job_id: str,
        stage_key: str,
        payload: Mapping[str, Any],
        *,
        lease_owner: str,
    ) -> str:
        """Immutably persist a fenced, cross-actor job effect outcome."""

        safe_stage = require_resource_id(stage_key, "effect_stage_key")
        if not safe_stage.startswith("effect:"):
            raise ValidationError("JOB_EFFECT_STAGE_KEY_INVALID")
        safe_owner = require_idempotency_key(lease_owner)
        encoded = canonical_json(payload)
        encoded_bytes = encoded.encode("utf-8")
        if len(encoded_bytes) > 16 * 1024 * 1024:
            raise ValidationError("JOB_EFFECT_RECEIPT_TOO_LARGE")
        digest = sha256_bytes(encoded_bytes)
        now = utc_now()
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            current = self._scoped_job(connection, context, job_id)
            self._require_external_effect_lease(current, safe_owner, now)
            existing = connection.execute(
                """
                SELECT payload_json,payload_sha256 FROM processing_checkpoints
                 WHERE tenant_id=? AND project_id=? AND job_id=? AND stage_key=?
                """,
                (context.tenant_id, context.project_id, job_id, safe_stage),
            ).fetchone()
            if existing is not None:
                self._decode_job_effect_receipt(existing)
                if not hmac.compare_digest(existing["payload_sha256"], digest):
                    raise ConflictError("JOB_EFFECT_RECEIPT_IMMUTABILITY_CONFLICT")
                return digest
            connection.execute(
                "INSERT INTO processing_checkpoints VALUES (?,?,?,?,?,?,?)",
                (
                    job_id,
                    context.tenant_id,
                    context.project_id,
                    safe_stage,
                    encoded,
                    digest,
                    now,
                ),
            )
        return digest

    @staticmethod
    def _require_external_effect_lease(
        current: sqlite3.Row,
        lease_owner: str,
        now: str,
    ) -> None:
        if (
            current["status"] != JobStatus.RUNNING.value
            or current["lease_owner"] != lease_owner
            or str(current["lease_expires_at"] or "") <= now
            or not str(current["stage"] or "").startswith("external-effect:")
        ):
            raise ConflictError("PROCESSING_JOB_EXTERNAL_EFFECT_LEASE_NOT_OWNED")

    @staticmethod
    def _decode_job_effect_receipt(row: sqlite3.Row) -> dict[str, Any]:
        encoded = row["payload_json"]
        if not isinstance(encoded, str) or len(encoded.encode("utf-8")) > 16 * 1024 * 1024:
            raise IntegrityError("JOB_EFFECT_RECEIPT_CORRUPT")
        try:
            stored_digest = normalize_sha256(row["payload_sha256"])
            payload = json.loads(encoded)
            canonical = canonical_json(payload)
        except Exception as error:
            raise IntegrityError("JOB_EFFECT_RECEIPT_CORRUPT") from error
        if (
            not isinstance(payload, dict)
            or canonical != encoded
            or not hmac.compare_digest(
                stored_digest,
                sha256_bytes(encoded.encode("utf-8")),
            )
        ):
            raise IntegrityError("JOB_EFFECT_RECEIPT_CORRUPT")
        return payload

    def replace_content_blocks(
        self,
        context: TenantContext,
        asset: InputAsset,
        blocks: Sequence[ContentBlock],
        *,
        asset_version: int | None = None,
    ) -> None:
        ordered = sorted(blocks, key=lambda item: item.ordinal)
        if any(block.ordinal != expected for expected, block in enumerate(ordered)):
            raise ValidationError("CONTENT_BLOCK_ORDINALS_NOT_CONTIGUOUS")
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            current = self._scoped_asset(connection, context, asset.asset_id)
            if current["version"] != asset.version:
                raise ConflictError("INPUT_ASSET_VERSION_CONFLICT")
            selected_version = current["version"] if asset_version is None else asset_version
            if not isinstance(selected_version, int) or selected_version < current["version"]:
                raise ValidationError("CONTENT_BLOCK_ASSET_VERSION_INVALID")
            self._write_content_blocks(connection, context, asset, ordered, selected_version)

    def finalize_asset_processing(
        self,
        context: TenantContext,
        *,
        human_review_source_capability: object,
        job_id: str,
        lease_owner: str,
        asset: InputAsset,
        report: ParseReport,
        status: AssetStatus,
        kind: AssetKind,
        detected_media_type: str,
        security_decision: SecurityDecision,
        failure_code: str | None,
        finding_codes: Sequence[str] = (),
    ) -> tuple[InputAsset, str]:
        """Atomically publish blocks, final asset version, findings, and a digested report."""

        if (
            self._human_review_source_capability is None
            or human_review_source_capability is not self._human_review_source_capability
        ):
            raise AuthorizationError("HUMAN_REVIEW_PARSER_SOURCE_CAPABILITY_DENIED")
        ordered = sorted(report.blocks, key=lambda item: item.ordinal)
        if any(block.ordinal != expected for expected, block in enumerate(ordered)):
            raise ValidationError("CONTENT_BLOCK_ORDINALS_NOT_CONTIGUOUS")
        if len(ordered) > 10_000:
            raise ValidationError("CONTENT_BLOCK_LIMIT_EXCEEDED")
        total_text_bytes = sum(len((block.text or "").encode("utf-8")) for block in ordered)
        if total_text_bytes > 16 * 1024 * 1024:
            raise ValidationError("CONTENT_TEXT_LIMIT_EXCEEDED")
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            self._require_job_lease(connection, context, job_id, lease_owner)
            current = self._scoped_asset(connection, context, asset.asset_id)
            if current["version"] != asset.version:
                raise ConflictError("INPUT_ASSET_VERSION_CONFLICT")
            if not asset.sha256 or current["sha256"] != asset.sha256:
                raise IntegrityError("ASSET_REPORT_SOURCE_DIGEST_MISMATCH")
            final_version = current["version"] + 1
            self._write_content_blocks(connection, context, asset, ordered, final_version)
            now = utc_now()
            changed = connection.execute(
                """
                UPDATE input_assets
                   SET status=?,kind=?,detected_media_type=?,security_decision=?,failure_code=?,
                       version=?,updated_at=?
                 WHERE asset_id=? AND tenant_id=? AND project_id=? AND version=?
                """,
                (
                    status.value,
                    kind.value,
                    detected_media_type,
                    security_decision.value,
                    failure_code,
                    final_version,
                    now,
                    asset.asset_id,
                    context.tenant_id,
                    context.project_id,
                    current["version"],
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("INPUT_ASSET_VERSION_CONFLICT")
            for code in sorted(set(finding_codes)):
                self._security_finding(connection, context, asset.asset_id, security_decision, code, {})
            report_payload = self._report_payload(report, final_version)
            encoded = canonical_json(report_payload)
            if len(encoded.encode("utf-8")) > 8 * 1024 * 1024:
                raise ValidationError("ASSET_PARSE_REPORT_TOO_LARGE")
            report_digest = sha256_bytes(encoded.encode("utf-8"))
            report_id = f"report-{canonical_digest([job_id, asset.asset_id, asset.sha256])[:32]}"
            existing = connection.execute(
                """
                SELECT report_sha256 FROM asset_parse_reports
                 WHERE tenant_id=? AND project_id=? AND job_id=? AND asset_id=? AND source_sha256=?
                """,
                (context.tenant_id, context.project_id, job_id, asset.asset_id, asset.sha256),
            ).fetchone()
            if existing is not None:
                if not hmac.compare_digest(existing["report_sha256"], report_digest):
                    raise ConflictError("ASSET_PARSE_REPORT_IMMUTABILITY_CONFLICT")
            else:
                connection.execute(
                    """
                    INSERT INTO asset_parse_reports (
                        report_id,tenant_id,project_id,job_id,asset_id,source_sha256,
                        asset_version,report_json,report_sha256,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        report_id,
                        context.tenant_id,
                        context.project_id,
                        job_id,
                        asset.asset_id,
                        asset.sha256,
                        final_version,
                        encoded,
                        report_digest,
                        now,
                    ),
                )
            if (
                status.value in self._HUMAN_REVIEW_ASSET_STATES
                and security_decision is not SecurityDecision.QUARANTINE
                and ordered
            ):
                self._publish_human_review_parser_sources(
                    connection,
                    context,
                    asset=asset,
                    asset_version=final_version,
                    report=report,
                    report_digest=report_digest,
                    job_id=job_id,
                    created_at=now,
                )
            refreshed = connection.execute(
                """
                SELECT * FROM input_assets
                 WHERE asset_id=? AND tenant_id=? AND project_id=?
                """,
                (asset.asset_id, context.tenant_id, context.project_id),
            ).fetchone()
            return self._asset(refreshed), report_digest

    def load_asset_report(self, context: TenantContext, asset: InputAsset) -> ParseReport | None:
        self.require(context, self.READ)
        if not asset.sha256:
            return None
        row = self._connection.execute(
            """
            SELECT * FROM asset_parse_reports
             WHERE tenant_id=? AND project_id=? AND asset_id=? AND source_sha256=?
             ORDER BY created_at DESC,report_id DESC LIMIT 1
            """,
            (context.tenant_id, context.project_id, asset.asset_id, asset.sha256),
        ).fetchone()
        if row is None:
            return None
        encoded = row["report_json"]
        if (
            not isinstance(encoded, str)
            or not hmac.compare_digest(sha256_bytes(encoded.encode("utf-8")), row["report_sha256"])
            or row["asset_version"] != asset.version
        ):
            raise IntegrityError("ASSET_PARSE_REPORT_CORRUPT")
        try:
            payload = json.loads(encoded)
        except (TypeError, json.JSONDecodeError) as error:
            raise IntegrityError("ASSET_PARSE_REPORT_CORRUPT") from error
        if not isinstance(payload, dict) or payload.get("schema_version") != "1.0.0":
            raise IntegrityError("ASSET_PARSE_REPORT_CORRUPT")
        blocks = tuple(self.content_blocks(context, asset.asset_id))
        try:
            blocks_digest = self._blocks_digest(blocks)
        except (TypeError, ValueError, ValidationError) as error:
            raise IntegrityError("ASSET_PARSE_REPORT_BLOCK_BINDING_MISMATCH") from error
        if (
            payload.get("block_ids") != [block.block_id for block in blocks]
            or not isinstance(payload.get("blocks_sha256"), str)
            or not hmac.compare_digest(payload["blocks_sha256"], blocks_digest)
        ):
            raise IntegrityError("ASSET_PARSE_REPORT_BLOCK_BINDING_MISMATCH")
        warnings = payload.get("warnings")
        receipt = payload.get("provider_receipt")
        metadata = payload.get("metadata")
        if (
            not isinstance(payload.get("parser"), str)
            or not isinstance(warnings, list)
            or any(not isinstance(item, str) for item in warnings)
            or not isinstance(receipt, dict)
            or not isinstance(metadata, dict)
        ):
            raise IntegrityError("ASSET_PARSE_REPORT_CORRUPT")
        try:
            status = ResultStatus(payload["status"])
        except (KeyError, ValueError) as error:
            raise IntegrityError("ASSET_PARSE_REPORT_CORRUPT") from error
        error_code = payload.get("error_code")
        if error_code is not None and not isinstance(error_code, str):
            raise IntegrityError("ASSET_PARSE_REPORT_CORRUPT")
        return ParseReport(
            parser=payload["parser"],
            status=status,
            blocks=blocks,
            warnings=tuple(warnings),
            error_code=error_code,
            provider_receipt=receipt,
            metadata=metadata,
        )

    def content_blocks(self, context: TenantContext, asset_id: str) -> list[ContentBlock]:
        asset = self.get_asset(context, asset_id)
        blocks: list[ContentBlock] = []
        for row in self._connection.execute(
            """
            SELECT * FROM content_blocks
             WHERE tenant_id=? AND project_id=? AND asset_id=? AND asset_version=?
             ORDER BY ordinal
            """,
            (context.tenant_id, context.project_id, asset_id, asset.version),
        ).fetchall():
            try:
                anchors = tuple(
                    self._anchor(anchor)
                    for anchor in self._connection.execute(
                        """
                        SELECT * FROM source_anchors
                         WHERE tenant_id=? AND project_id=? AND block_id=? AND asset_id=?
                         ORDER BY anchor_id
                        """,
                        (context.tenant_id, context.project_id, row["block_id"], asset_id),
                    ).fetchall()
                )
                payload = json.loads(row["payload_json"])
                if not isinstance(payload, dict):
                    raise ValueError("content block payload is not an object")
                trust_label = payload.pop(self._CONTENT_TRUST_PAYLOAD_KEY, None)
                if trust_label != UNTRUSTED_CONTENT:
                    raise ValueError("content block trust label is missing or invalid")
                blocks.append(
                    ContentBlock(
                        block_id=row["block_id"],
                        asset_id=row["asset_id"],
                        kind=ContentBlockKind(row["kind"]),
                        ordinal=row["ordinal"],
                        text=row["text_content"],
                        payload=payload,
                        anchors=anchors,
                        confidence=row["confidence"],
                        schema_version=row["schema_version"],
                        trust_label=trust_label,
                    )
                )
            except (TypeError, ValueError, json.JSONDecodeError, ValidationError) as error:
                raise IntegrityError("CONTENT_BLOCK_RECORD_CORRUPT") from error
        return blocks

    @staticmethod
    def _report_payload(report: ParseReport, asset_version: int) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "asset_version": asset_version,
            "parser": report.parser,
            "status": report.status.value,
            "warnings": list(report.warnings),
            "error_code": report.error_code,
            "provider_receipt": dict(report.provider_receipt),
            "metadata": dict(report.metadata),
            "block_ids": [block.block_id for block in report.blocks],
            "blocks_sha256": IntakeStore._blocks_digest(report.blocks),
        }

    @staticmethod
    def _content_block_source_document(block: ContentBlock) -> dict[str, Any]:
        return {
            "block_id": block.block_id,
            "asset_id": block.asset_id,
            "kind": block.kind.value,
            "ordinal": block.ordinal,
            "text": block.text,
            "payload": dict(block.payload),
            "confidence": block.confidence,
            "schema_version": block.schema_version,
            "trust_label": block.trust_label,
            "anchors": [
                {
                    "anchor_id": anchor.anchor_id,
                    "asset_id": anchor.asset_id,
                    "source_sha256": anchor.source_sha256,
                    "locator_type": anchor.locator_type,
                    "page_number": anchor.page_number,
                    "paragraph_index": anchor.paragraph_index,
                    "line_start": anchor.line_start,
                    "line_end": anchor.line_end,
                    "time_start_ms": anchor.time_start_ms,
                    "time_end_ms": anchor.time_end_ms,
                    "bbox": anchor.bbox,
                    "symbol": anchor.symbol,
                    "excerpt_sha256": anchor.excerpt_sha256,
                }
                for anchor in sorted(block.anchors, key=lambda item: item.anchor_id)
            ],
        }

    @classmethod
    def _blocks_digest(cls, blocks: Sequence[ContentBlock]) -> str:
        return canonical_digest(
            [
                cls._content_block_source_document(block)
                for block in sorted(blocks, key=lambda item: (item.ordinal, item.block_id))
            ]
        )

    @classmethod
    def _human_review_source_content(
        cls,
        value: Any,
        *,
        code: str,
    ) -> tuple[str, str]:
        try:
            rendered = content_contract_json(value)
            encoded = rendered.encode("utf-8", errors="strict")
            digest = normalize_sha256(content_contract_digest(value))
        except (TypeError, ValueError, UnicodeError, RecursionError, ValidationError) as error:
            raise ValidationError(code) from error
        if len(encoded) > cls._MAX_HUMAN_REVIEW_SOURCE_JSON_BYTES:
            raise ValidationError("HUMAN_REVIEW_SOURCE_VALUE_LIMIT_EXCEEDED")
        return rendered, digest

    @classmethod
    def _human_review_parser_source_candidates(
        cls,
        report: ParseReport,
        *,
        asset_id: str,
        asset_version: int,
        report_digest: str,
    ) -> tuple[dict[str, Any], ...]:
        """Compile real parser blocks/anchors into the seven typed review locator space."""

        candidates: dict[tuple[str, str], dict[str, Any]] = {}
        safe_report_digest = normalize_sha256(report_digest)
        producer_version = "elmos-multimodal-parser-authoritative-source-v1"

        def add(
            *,
            block: ContentBlock,
            anchor: SourceAnchor | None,
            target_kind: ReviewTargetKind,
            target: dict[str, Any],
            original_value: Any,
            source_kind: str,
        ) -> None:
            _target_json, target_digest = cls._human_review_source_content(
                target,
                code="HUMAN_REVIEW_SOURCE_TARGET_INVALID",
            )
            cls._human_review_source_content(
                original_value,
                code="HUMAN_REVIEW_SOURCE_VALUE_INVALID",
            )
            source_id = (
                anchor.anchor_id
                if source_kind == "SOURCE_ANCHOR" and anchor is not None
                else block.block_id
            )
            source_fact = {
                "schema_version": "human-review-parser-source-v1",
                "asset_id": asset_id,
                "asset_version": asset_version,
                "parser": report.parser,
                "report_digest": f"sha256:{safe_report_digest}",
                "block": cls._content_block_source_document(block),
                "anchor_id": anchor.anchor_id if anchor is not None else None,
                "target_kind": target_kind.value,
                "target": target,
                "original_value": original_value,
            }
            source_digest = canonical_digest(source_fact)
            candidate = {
                "target_kind": target_kind.value,
                "target": target,
                "original_value": original_value,
                "confidence": float(block.confidence if block.confidence is not None else 1.0),
                "source_digest": source_digest,
                "provenance": {
                    "schema_version": "human-review-source-provenance-v1",
                    "source_kind": source_kind,
                    "source_id": source_id,
                    "source_digest": f"sha256:{source_digest}",
                    "producer_version": producer_version,
                },
            }
            key = (target_kind.value, target_digest)
            prior = candidates.get(key)
            if prior is not None:
                if content_contract_json(prior) != content_contract_json(candidate):
                    raise IntegrityError("HUMAN_REVIEW_SOURCE_TARGET_COLLISION")
                return
            if len(candidates) >= cls._MAX_HUMAN_REVIEW_SOURCE_TARGETS:
                raise ValidationError("HUMAN_REVIEW_SOURCE_TARGET_LIMIT_EXCEEDED")
            candidates[key] = candidate

        for block in sorted(report.blocks, key=lambda item: (item.ordinal, item.block_id)):
            if block.asset_id != asset_id:
                raise ValidationError("CONTENT_BLOCK_ASSET_MISMATCH")
            anchors = tuple(sorted(block.anchors, key=lambda item: item.anchor_id))
            primary_anchor = anchors[0] if anchors else None
            if block.text is not None:
                add(
                    block=block,
                    anchor=primary_anchor,
                    target_kind=ReviewTargetKind.TEXT,
                    target={"path": f"content_blocks/{block.block_id}/text"},
                    original_value=block.text,
                    source_kind="SOURCE_ANCHOR" if primary_anchor is not None else "CONTENT_BLOCK",
                )
            for anchor in anchors:
                if block.text is not None and anchor.bbox is not None:
                    x, y, width, height = anchor.bbox
                    if width <= 0 or height <= 0:
                        raise ValidationError("HUMAN_REVIEW_SOURCE_TARGET_INVALID")
                    page = anchor.page_number
                    if page is None:
                        raw_page = block.payload.get("page_number")
                        page = (
                            raw_page
                            if (
                                isinstance(raw_page, int)
                                and not isinstance(raw_page, bool)
                                and 1 <= raw_page <= MAX_SAFE_JSON_INTEGER - 1
                            )
                            else 1
                        )
                    add(
                        block=block,
                        anchor=anchor,
                        target_kind=ReviewTargetKind.BBOX,
                        target={
                            "page": page,
                            "x": x,
                            "y": y,
                            "width": width,
                            "height": height,
                        },
                        original_value=block.text,
                        source_kind="SOURCE_ANCHOR",
                    )
                if (
                    block.text is not None
                    and anchor.time_start_ms is not None
                    and anchor.time_end_ms is not None
                ):
                    if anchor.time_end_ms > MAX_SAFE_JSON_INTEGER - 1:
                        raise ValidationError("HUMAN_REVIEW_SOURCE_TARGET_INVALID")
                    add(
                        block=block,
                        anchor=anchor,
                        target_kind=ReviewTargetKind.TIME_RANGE,
                        target={
                            "start_ms": anchor.time_start_ms,
                            "end_ms": anchor.time_end_ms,
                        },
                        original_value=block.text,
                        source_kind="SOURCE_ANCHOR",
                    )
            speaker = block.payload.get("speaker")
            if (
                block.kind is ContentBlockKind.AUDIO_SEGMENT
                and isinstance(speaker, str)
                and speaker
            ):
                add(
                    block=block,
                    anchor=primary_anchor,
                    target_kind=ReviewTargetKind.SPEAKER,
                    target={"segment_id": block.block_id},
                    original_value=speaker,
                    source_kind="SOURCE_ANCHOR" if primary_anchor is not None else "CONTENT_BLOCK",
                )
            rows = block.payload.get("rows")
            if block.kind is ContentBlockKind.TABLE and isinstance(rows, list):
                for row_index, row in enumerate(rows):
                    if not isinstance(row, list):
                        raise ValidationError("HUMAN_REVIEW_SOURCE_VALUE_INVALID")
                    for column_index, cell in enumerate(row):
                        if not isinstance(cell, str):
                            raise ValidationError("HUMAN_REVIEW_SOURCE_VALUE_INVALID")
                        add(
                            block=block,
                            anchor=primary_anchor,
                            target_kind=ReviewTargetKind.TABLE,
                            target={
                                "table_id": block.block_id,
                                "row": row_index,
                                "column": column_index,
                            },
                            original_value=cell,
                            source_kind="CONTENT_BLOCK",
                        )
        return tuple(candidates[key] for key in sorted(candidates))

    @classmethod
    def _human_review_correction_source_target(
        cls,
        correction_id: str,
    ) -> dict[str, str]:
        safe_correction_id = require_resource_id(correction_id, "correction_id")
        return {
            "path": f"human_review_corrections/{safe_correction_id}/value",
        }

    @classmethod
    def _human_review_correction_source_fact(
        cls,
        *,
        correction_id: str,
        correction_document: Mapping[str, Any],
        correction_digest: str,
        source_version: int,
        asset_version: int,
    ) -> dict[str, Any]:
        """Bind an internal source fact to one immutable legacy correction.

        This fact is reconstructed from the store-owned correction row.  It is
        deliberately distinct from parser provenance and from the untrusted
        original-value echo accepted by ``enqueue`` only for drift detection.
        """

        safe_correction_id = require_resource_id(correction_id, "correction_id")
        safe_digest = normalize_sha256(correction_digest)
        if (
            isinstance(source_version, bool)
            or not isinstance(source_version, int)
            or source_version < 1
            or isinstance(asset_version, bool)
            or not isinstance(asset_version, int)
            or asset_version != source_version + 1
        ):
            raise IntegrityError("HUMAN_REVIEW_CORRECTION_SOURCE_INVALID")
        if not isinstance(correction_document, Mapping):
            raise IntegrityError("HUMAN_REVIEW_CORRECTION_SOURCE_INVALID")
        if (
            correction_document.get("digest") != f"sha256:{safe_digest}"
            or correction_document.get("version") != asset_version
        ):
            raise IntegrityError("HUMAN_REVIEW_CORRECTION_SOURCE_INVALID")
        target = cls._human_review_correction_source_target(safe_correction_id)
        fact = {
            "schema_version": "human-review-correction-authoritative-source-v1",
            "correction_id": safe_correction_id,
            "tenant_id": correction_document.get("tenant_id"),
            "project_id": correction_document.get("project_id"),
            "asset_id": correction_document.get("content_id"),
            "source_version": source_version,
            "asset_version": asset_version,
            "correction_digest": f"sha256:{safe_digest}",
            "supersedes_digest": correction_document.get("supersedes_digest"),
            "target_kind": ReviewTargetKind.TEXT.value,
            "target": target,
            "original_value": correction_document.get("value"),
            "actor_id": correction_document.get("actor"),
            "reason": correction_document.get("reason"),
            "policy_version": correction_document.get("policy_version"),
            "review_state_version": correction_document.get("review_state_version"),
            "approval_state": "NOT_RUN",
            "rebuild_state": "NOT_RUN",
            "confidence": cls._HUMAN_REVIEW_CORRECTION_SOURCE_CONFIDENCE,
            "confidence_basis": "EXPLICIT_HUMAN_CORRECTION_SOURCE",
        }
        try:
            content_contract_json(fact)
        except (TypeError, ValueError, UnicodeError, RecursionError) as error:
            raise IntegrityError("HUMAN_REVIEW_CORRECTION_SOURCE_INVALID") from error
        return fact

    def _human_review_correction_source_capability(
        self,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        created_at: str,
    ) -> str:
        try:
            now_dt = datetime.fromisoformat(created_at)
        except (TypeError, ValueError) as error:
            raise IntegrityError("HUMAN_REVIEW_CORRECTION_SOURCE_INVALID") from error
        if (
            now_dt.tzinfo is None
            or now_dt.utcoffset() is None
            or now_dt.isoformat() != created_at
        ):
            raise IntegrityError("HUMAN_REVIEW_CORRECTION_SOURCE_INVALID")
        now = created_at
        source_kinds = [self._HUMAN_REVIEW_CORRECTION_SOURCE_KIND]
        source_kinds_json, source_kinds_digest = self._human_review_source_content(
            source_kinds,
            code="HUMAN_REVIEW_SOURCE_KINDS_INVALID",
        )
        existing = connection.execute(
            """SELECT * FROM human_review_source_producer_capabilities
                WHERE tenant_id=? AND project_id=? AND producer_id=?
                  AND revoked_at IS NULL AND created_at<=? AND expires_at>?
                ORDER BY expires_at DESC,capability_id LIMIT 1""",
            (
                context.tenant_id,
                context.project_id,
                self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER,
                now,
                now,
            ),
        ).fetchone()
        if existing is not None:
            if (
                existing["source_kinds_json"] != source_kinds_json
                or existing["created_by"]
                != self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER
                or not hmac.compare_digest(
                    existing["source_kinds_digest"], source_kinds_digest
                )
            ):
                raise IntegrityError(
                    "HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_CORRUPT"
                )
            return str(existing["capability_id"])
        capability_id = new_id("review-source-cap")
        token_digest = hashlib.sha256(secrets.token_bytes(48)).hexdigest()
        expires_at = (now_dt + timedelta(days=30)).isoformat()
        connection.execute(
            """INSERT INTO human_review_source_producer_capabilities (
                capability_id,tenant_id,project_id,producer_id,token_digest,
                source_kinds_json,source_kinds_digest,expires_at,revoked_at,
                version,created_by,created_at
            ) VALUES (?,?,?,?,?,?,?,?,NULL,1,?,?)""",
            (
                capability_id,
                context.tenant_id,
                context.project_id,
                self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER,
                token_digest,
                source_kinds_json,
                source_kinds_digest,
                expires_at,
                self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER,
                now,
            ),
        )
        producer_context = TenantContext(
            context.tenant_id,
            context.project_id,
            self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER,
        )
        self._event(
            connection,
            producer_context,
            "human_review_source_producer_capability",
            capability_id,
            "human_review.source_producer.registered",
            f"human-review-correction-capability:{capability_id}",
            {
                "capability_id": capability_id,
                "producer_id": self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER,
                "source_kinds": source_kinds,
                "expires_at": expires_at,
                "created_at": now,
            },
        )
        return capability_id

    def _publish_human_review_correction_source(
        self,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        asset: sqlite3.Row,
        source_version: int,
        asset_version: int,
        correction_id: str,
        correction_document: Mapping[str, Any],
        correction_digest: str,
        created_at: str,
    ) -> dict[str, Any]:
        """Atomically publish the correction value as the new source head."""

        persisted = connection.execute(
            """SELECT * FROM human_review_corrections
                WHERE tenant_id=? AND project_id=? AND correction_id=?""",
            (context.tenant_id, context.project_id, correction_id),
        ).fetchone()
        if persisted is None or self._human_review_correction(persisted) != dict(
            correction_document
        ):
            raise IntegrityError("HUMAN_REVIEW_CORRECTION_SOURCE_INVALID")
        if (
            asset["asset_id"] != correction_document.get("content_id")
            or asset["tenant_id"] != context.tenant_id
            or asset["project_id"] != context.project_id
            or int(asset["version"]) != source_version
            or asset["sha256"] is None
        ):
            raise IntegrityError("HUMAN_REVIEW_CORRECTION_SOURCE_INVALID")

        source_fact = self._human_review_correction_source_fact(
            correction_id=correction_id,
            correction_document=correction_document,
            correction_digest=correction_digest,
            source_version=source_version,
            asset_version=asset_version,
        )
        source_digest = canonical_digest(source_fact)
        target = source_fact["target"]
        original_value = source_fact["original_value"]
        target_json, target_digest = self._human_review_source_content(
            target,
            code="HUMAN_REVIEW_SOURCE_TARGET_INVALID",
        )
        original_json, original_digest = self._human_review_source_content(
            original_value,
            code="HUMAN_REVIEW_SOURCE_VALUE_INVALID",
        )
        provenance = {
            "schema_version": "human-review-source-provenance-v1",
            "source_kind": self._HUMAN_REVIEW_CORRECTION_SOURCE_KIND,
            "source_id": correction_id,
            "source_digest": f"sha256:{source_digest}",
            "producer_version": (
                self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER_VERSION
            ),
        }
        provenance_json, provenance_digest = self._human_review_source_content(
            provenance,
            code="HUMAN_REVIEW_SOURCE_PROVENANCE_INVALID",
        )
        capability_id = self._human_review_correction_source_capability(
            connection,
            context,
            created_at=created_at,
        )
        safe_correction_digest = normalize_sha256(correction_digest)
        request_digest = canonical_digest(
            {
                "schema_version": "human-review-correction-source-register-v1",
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "producer_id": self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER,
                "correction_id": correction_id,
                "correction_digest": f"sha256:{safe_correction_digest}",
                "asset_id": asset["asset_id"],
                "source_version": source_version,
                "asset_version": asset_version,
                "target_kind": ReviewTargetKind.TEXT.value,
                "target_digest": f"sha256:{target_digest}",
                "source_digest": f"sha256:{source_digest}",
            }
        )
        idempotency_key = f"correction-source-{request_digest}"
        snapshot_id = "review-source-" + canonical_digest(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "asset_id": asset["asset_id"],
                "asset_version": asset_version,
                "correction_id": correction_id,
                "correction_digest": f"sha256:{safe_correction_digest}",
                "target_kind": ReviewTargetKind.TEXT.value,
                "target_digest": f"sha256:{target_digest}",
                "source_digest": f"sha256:{source_digest}",
                "request_digest": f"sha256:{request_digest}",
            }
        )[:32]
        asset_sha256 = normalize_sha256(asset["sha256"])
        snapshot_body = {
            "schema_version": "human-review-source-snapshot-v1",
            "snapshot_id": snapshot_id,
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "asset_id": asset["asset_id"],
            "asset_version": asset_version,
            "target_kind": ReviewTargetKind.TEXT.value,
            "target": target,
            "original_value": original_value,
            "confidence": self._HUMAN_REVIEW_CORRECTION_SOURCE_CONFIDENCE,
            "asset_sha256": f"sha256:{asset_sha256}",
            "source_digest": f"sha256:{source_digest}",
            "provenance": provenance,
            "producer_capability_id": capability_id,
            "producer_actor_id": self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER,
            "idempotency_key": idempotency_key,
            "request_digest": f"sha256:{request_digest}",
            "created_at": created_at,
        }
        snapshot_digest = normalize_sha256(content_contract_digest(snapshot_body))
        connection.execute(
            """INSERT INTO human_review_source_snapshots (
                snapshot_id,tenant_id,project_id,asset_id,asset_version,target_kind,
                target_json,target_digest,original_value_json,original_value_digest,
                confidence,asset_sha256,source_digest,provenance_json,provenance_digest,
                producer_capability_id,producer_actor_id,idempotency_key,request_digest,
                snapshot_digest,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                snapshot_id,
                context.tenant_id,
                context.project_id,
                asset["asset_id"],
                asset_version,
                ReviewTargetKind.TEXT.value,
                target_json,
                target_digest,
                original_json,
                original_digest,
                self._HUMAN_REVIEW_CORRECTION_SOURCE_CONFIDENCE,
                asset_sha256,
                source_digest,
                provenance_json,
                provenance_digest,
                capability_id,
                self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER,
                idempotency_key,
                request_digest,
                snapshot_digest,
                created_at,
            ),
        )
        connection.execute(
            """INSERT INTO human_review_target_heads (
                tenant_id,project_id,asset_id,asset_version,target_kind,target_json,
                target_digest,base_snapshot_id,current_value_json,current_value_digest,
                source_digest,provenance_digest,source_decision_id,correction_version,
                direction,version,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,0,'SNAPSHOT',1,?)""",
            (
                context.tenant_id,
                context.project_id,
                asset["asset_id"],
                asset_version,
                ReviewTargetKind.TEXT.value,
                target_json,
                target_digest,
                snapshot_id,
                original_json,
                original_digest,
                source_digest,
                provenance_digest,
                created_at,
            ),
        )
        producer_context = TenantContext(
            context.tenant_id,
            context.project_id,
            self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER,
        )
        response = {
            "snapshot_id": snapshot_id,
            "snapshot_digest": f"sha256:{snapshot_digest}",
            "asset_id": asset["asset_id"],
            "asset_version": asset_version,
            "target_kind": ReviewTargetKind.TEXT.value,
            "target_digest": f"sha256:{target_digest}",
            "head_version": 1,
            "head_value_digest": f"sha256:{original_digest}",
            "source_digest": f"sha256:{source_digest}",
            "provenance_digest": f"sha256:{provenance_digest}",
        }
        self._event(
            connection,
            producer_context,
            "human_review_source_snapshot",
            snapshot_id,
            "human_review.source.registered",
            (
                "human-review-source:"
                f"{self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER}:"
                f"{idempotency_key}"
            ),
            {
                **response,
                "correction_id": correction_id,
                "correction_digest": f"sha256:{safe_correction_digest}",
                "original_value_digest": f"sha256:{original_digest}",
                "producer_capability_id": capability_id,
                "producer_actor_id": (
                    self._HUMAN_REVIEW_CORRECTION_SOURCE_PRODUCER
                ),
                "request_digest": f"sha256:{request_digest}",
            },
        )
        return response

    def _human_review_parser_producer_capability(
        self,
        connection: sqlite3.Connection,
        context: TenantContext,
    ) -> str:
        now_dt = datetime.now(UTC).replace(microsecond=0)
        now = now_dt.isoformat()
        source_kinds = list(self._HUMAN_REVIEW_PARSER_SOURCE_KINDS)
        source_kinds_json, source_kinds_digest = self._human_review_source_content(
            source_kinds,
            code="HUMAN_REVIEW_SOURCE_KINDS_INVALID",
        )
        existing = connection.execute(
            """SELECT * FROM human_review_source_producer_capabilities
                WHERE tenant_id=? AND project_id=? AND producer_id=?
                  AND revoked_at IS NULL AND expires_at>?
                ORDER BY expires_at DESC,capability_id LIMIT 1""",
            (
                context.tenant_id,
                context.project_id,
                self._HUMAN_REVIEW_PARSER_PRODUCER,
                now,
            ),
        ).fetchone()
        if existing is not None:
            if (
                existing["source_kinds_json"] != source_kinds_json
                or not hmac.compare_digest(existing["source_kinds_digest"], source_kinds_digest)
            ):
                raise IntegrityError("HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_CORRUPT")
            return str(existing["capability_id"])
        capability_id = new_id("review-source-cap")
        token_digest = hashlib.sha256(secrets.token_bytes(48)).hexdigest()
        expires_at = (now_dt + timedelta(days=30)).isoformat()
        connection.execute(
            """INSERT INTO human_review_source_producer_capabilities (
                capability_id,tenant_id,project_id,producer_id,token_digest,
                source_kinds_json,source_kinds_digest,expires_at,revoked_at,
                version,created_by,created_at
            ) VALUES (?,?,?,?,?,?,?,?,NULL,1,?,?)""",
            (
                capability_id,
                context.tenant_id,
                context.project_id,
                self._HUMAN_REVIEW_PARSER_PRODUCER,
                token_digest,
                source_kinds_json,
                source_kinds_digest,
                expires_at,
                self._HUMAN_REVIEW_PARSER_PRODUCER,
                now,
            ),
        )
        producer_context = TenantContext(
            context.tenant_id,
            context.project_id,
            self._HUMAN_REVIEW_PARSER_PRODUCER,
        )
        self._event(
            connection,
            producer_context,
            "human_review_source_producer_capability",
            capability_id,
            "human_review.source_producer.registered",
            f"human-review-parser-capability:{capability_id}",
            {
                "capability_id": capability_id,
                "producer_id": self._HUMAN_REVIEW_PARSER_PRODUCER,
                "source_kinds": source_kinds,
                "expires_at": expires_at,
                "created_at": now,
            },
        )
        return capability_id

    def _publish_human_review_parser_sources(
        self,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        asset: InputAsset,
        asset_version: int,
        report: ParseReport,
        report_digest: str,
        job_id: str,
        created_at: str,
    ) -> None:
        if asset.sha256 is None:
            raise IntegrityError("ASSET_REPORT_SOURCE_DIGEST_MISMATCH")
        candidates = self._human_review_parser_source_candidates(
            report,
            asset_id=asset.asset_id,
            asset_version=asset_version,
            report_digest=report_digest,
        )
        if not candidates:
            return
        capability_id = self._human_review_parser_producer_capability(connection, context)
        producer_context = TenantContext(
            context.tenant_id,
            context.project_id,
            self._HUMAN_REVIEW_PARSER_PRODUCER,
        )
        asset_sha256 = normalize_sha256(asset.sha256)
        for candidate in candidates:
            target_json, target_digest = self._human_review_source_content(
                candidate["target"], code="HUMAN_REVIEW_SOURCE_TARGET_INVALID"
            )
            original_json, original_digest = self._human_review_source_content(
                candidate["original_value"], code="HUMAN_REVIEW_SOURCE_VALUE_INVALID"
            )
            provenance_json, provenance_digest = self._human_review_source_content(
                candidate["provenance"], code="HUMAN_REVIEW_SOURCE_PROVENANCE_INVALID"
            )
            source_digest = normalize_sha256(candidate["source_digest"])
            request_digest = canonical_digest(
                {
                    "schema_version": "human-review-parser-source-register-v1",
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "producer_id": self._HUMAN_REVIEW_PARSER_PRODUCER,
                    "job_id": job_id,
                    "asset_id": asset.asset_id,
                    "asset_version": asset_version,
                    "report_digest": f"sha256:{normalize_sha256(report_digest)}",
                    "target_kind": candidate["target_kind"],
                    "target_digest": f"sha256:{target_digest}",
                    "source_digest": f"sha256:{source_digest}",
                }
            )
            idempotency_key = f"parser-source-{request_digest}"
            snapshot_id = "review-source-" + canonical_digest(
                {
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "asset_id": asset.asset_id,
                    "asset_version": asset_version,
                    "job_id": job_id,
                    "report_digest": f"sha256:{normalize_sha256(report_digest)}",
                    "target_kind": candidate["target_kind"],
                    "target_digest": f"sha256:{target_digest}",
                    "source_digest": f"sha256:{source_digest}",
                    "request_digest": f"sha256:{request_digest}",
                }
            )[:32]
            snapshot_body = {
                "schema_version": "human-review-source-snapshot-v1",
                "snapshot_id": snapshot_id,
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "asset_id": asset.asset_id,
                "asset_version": asset_version,
                "target_kind": candidate["target_kind"],
                "target": candidate["target"],
                "original_value": candidate["original_value"],
                "confidence": candidate["confidence"],
                "asset_sha256": f"sha256:{asset_sha256}",
                "source_digest": f"sha256:{source_digest}",
                "provenance": candidate["provenance"],
                "producer_capability_id": capability_id,
                "producer_actor_id": self._HUMAN_REVIEW_PARSER_PRODUCER,
                "idempotency_key": idempotency_key,
                "request_digest": f"sha256:{request_digest}",
                "created_at": created_at,
            }
            snapshot_digest = normalize_sha256(content_contract_digest(snapshot_body))
            connection.execute(
                """INSERT INTO human_review_source_snapshots (
                    snapshot_id,tenant_id,project_id,asset_id,asset_version,target_kind,
                    target_json,target_digest,original_value_json,original_value_digest,
                    confidence,asset_sha256,source_digest,provenance_json,provenance_digest,
                    producer_capability_id,producer_actor_id,idempotency_key,request_digest,
                    snapshot_digest,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id,
                    context.tenant_id,
                    context.project_id,
                    asset.asset_id,
                    asset_version,
                    candidate["target_kind"],
                    target_json,
                    target_digest,
                    original_json,
                    original_digest,
                    candidate["confidence"],
                    asset_sha256,
                    source_digest,
                    provenance_json,
                    provenance_digest,
                    capability_id,
                    self._HUMAN_REVIEW_PARSER_PRODUCER,
                    idempotency_key,
                    request_digest,
                    snapshot_digest,
                    created_at,
                ),
            )
            connection.execute(
                """INSERT INTO human_review_target_heads (
                    tenant_id,project_id,asset_id,asset_version,target_kind,target_json,
                    target_digest,base_snapshot_id,current_value_json,current_value_digest,
                    source_digest,provenance_digest,source_decision_id,correction_version,
                    direction,version,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,0,'SNAPSHOT',1,?)""",
                (
                    context.tenant_id,
                    context.project_id,
                    asset.asset_id,
                    asset_version,
                    candidate["target_kind"],
                    target_json,
                    target_digest,
                    snapshot_id,
                    original_json,
                    original_digest,
                    source_digest,
                    provenance_digest,
                    created_at,
                ),
            )
            self._event(
                connection,
                producer_context,
                "human_review_source_snapshot",
                snapshot_id,
                "human_review.source.registered",
                f"human-review-source:{self._HUMAN_REVIEW_PARSER_PRODUCER}:{idempotency_key}",
                {
                    "snapshot_id": snapshot_id,
                    "asset_id": asset.asset_id,
                    "asset_version": asset_version,
                    "job_id": job_id,
                    "report_digest": f"sha256:{normalize_sha256(report_digest)}",
                    "target_kind": candidate["target_kind"],
                    "target_digest": f"sha256:{target_digest}",
                    "original_value_digest": f"sha256:{original_digest}",
                    "source_digest": f"sha256:{source_digest}",
                    "provenance_digest": f"sha256:{provenance_digest}",
                    "snapshot_digest": f"sha256:{snapshot_digest}",
                    "producer_capability_id": capability_id,
                    "producer_actor_id": self._HUMAN_REVIEW_PARSER_PRODUCER,
                    "request_digest": f"sha256:{request_digest}",
                },
            )

    @staticmethod
    def _write_content_blocks(
        connection: sqlite3.Connection,
        context: TenantContext,
        asset: InputAsset,
        ordered: Sequence[ContentBlock],
        asset_version: int,
    ) -> None:
        connection.execute(
            "DELETE FROM content_blocks WHERE tenant_id=? AND project_id=? AND asset_id=?",
            (context.tenant_id, context.project_id, asset.asset_id),
        )
        now = utc_now()
        for block in ordered:
            if block.asset_id != asset.asset_id:
                raise ValidationError("CONTENT_BLOCK_ASSET_MISMATCH")
            persisted_payload = dict(block.payload)
            if IntakeStore._CONTENT_TRUST_PAYLOAD_KEY in persisted_payload:
                raise ValidationError("CONTENT_BLOCK_TRUST_LABEL_RESERVED")
            if block.trust_label != UNTRUSTED_CONTENT:
                raise ValidationError("CONTENT_BLOCK_TRUST_LABEL_INVALID")
            persisted_payload[IntakeStore._CONTENT_TRUST_PAYLOAD_KEY] = block.trust_label
            connection.execute(
                "INSERT INTO content_blocks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    block.block_id,
                    context.tenant_id,
                    context.project_id,
                    asset.asset_id,
                    asset_version,
                    block.schema_version,
                    block.ordinal,
                    block.kind.value,
                    block.text,
                    canonical_json(persisted_payload),
                    block.confidence,
                    now,
                ),
            )
            for anchor in block.anchors:
                if anchor.asset_id != asset.asset_id:
                    raise ValidationError("SOURCE_ANCHOR_ASSET_MISMATCH")
                if asset.sha256 is None or anchor.source_sha256 != asset.sha256:
                    raise IntegrityError("SOURCE_ANCHOR_DIGEST_MISMATCH")
                connection.execute(
                    "INSERT INTO source_anchors VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        anchor.anchor_id,
                        context.tenant_id,
                        context.project_id,
                        block.block_id,
                        asset.asset_id,
                        anchor.source_sha256,
                        anchor.locator_type,
                        anchor.page_number,
                        anchor.paragraph_index,
                        anchor.line_start,
                        anchor.line_end,
                        anchor.time_start_ms,
                        anchor.time_end_ms,
                        canonical_json(anchor.bbox) if anchor.bbox is not None else None,
                        anchor.symbol,
                        anchor.excerpt_sha256,
                        now,
                    ),
                )

    def apply_durable_transition(
        self,
        context: TenantContext,
        *,
        task_id: str,
        idempotency_key: str,
        target_state: str,
        payload: Mapping[str, Any],
        current_state: str | None = None,
        checkpoint_digest: str | None = None,
        attempted_effect_receipts: Sequence[str] = (),
        recorded_effect_receipts: Sequence[str] = (),
    ) -> tuple[dict[str, Any], bool]:
        """Atomically append one task transition and its tenant-scoped outbox event."""

        safe_task = require_resource_id(task_id, "task_id")
        safe_key = require_idempotency_key(idempotency_key)
        target = str(target_state or "").strip().upper()
        if target not in self._DURABLE_TRANSITIONS:
            raise ValidationError("DURABLE_TARGET_STATE_INVALID")
        requested_current = str(current_state).strip().upper() if current_state is not None else None
        if requested_current is not None and requested_current not in self._DURABLE_TRANSITIONS:
            raise ValidationError("DURABLE_CURRENT_STATE_INVALID")
        if not isinstance(payload, Mapping):
            raise ValidationError("DURABLE_PAYLOAD_INVALID")
        checkpoint = normalize_sha256(checkpoint_digest) if checkpoint_digest is not None else None
        attempted = self._effect_receipts(attempted_effect_receipts)
        recorded = self._effect_receipts(recorded_effect_receipts)
        request = {
            "task_id": safe_task,
            "target_state": target,
            "current_state": requested_current,
            "payload": dict(payload),
            "checkpoint_digest": checkpoint,
            "attempted_effect_receipts": attempted,
            "recorded_effect_receipts": recorded,
        }
        request_digest = canonical_digest(request)
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            existing = connection.execute(
                """
                SELECT * FROM durable_transitions
                 WHERE tenant_id=? AND project_id=? AND task_id=? AND idempotency_key=?
                """,
                (context.tenant_id, context.project_id, safe_task, safe_key),
            ).fetchone()
            if existing is not None:
                if not hmac.compare_digest(existing["request_digest"], request_digest):
                    raise ConflictError("DURABLE_TRANSITION_IDEMPOTENCY_CONFLICT")
                return self._durable_event(existing), True
            latest = connection.execute(
                """
                SELECT sequence_number,target_state FROM durable_transitions
                 WHERE tenant_id=? AND project_id=? AND task_id=?
                 ORDER BY sequence_number DESC LIMIT 1
                """,
                (context.tenant_id, context.project_id, safe_task),
            ).fetchone()
            authoritative = latest["target_state"] if latest is not None else "PENDING"
            if requested_current is not None and requested_current != authoritative:
                raise ConflictError(
                    "DURABLE_STATE_MISMATCH",
                    details={"authoritative_state": authoritative},
                )
            if target not in self._DURABLE_TRANSITIONS[authoritative]:
                raise ConflictError(
                    "INVALID_DURABLE_STATE_TRANSITION",
                    details={"current_state": authoritative, "target_state": target},
                )
            sequence_number = 1 if latest is None else int(latest["sequence_number"]) + 1
            payload_digest = canonical_digest(dict(payload))
            event: dict[str, Any] = {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "skill": "elmos-durable-processing-and-recovery",
                "actor_id": context.actor_id,
                "task_id": safe_task,
                "sequence_number": sequence_number,
                "from_state": authoritative,
                "target_state": target,
                "idempotency_key": safe_key,
                "request_digest": request_digest,
                "payload_digest": payload_digest,
                "checkpoint_digest": checkpoint,
                "effects_to_skip": sorted(set(attempted) & set(recorded)),
                "effects_to_reconcile": sorted(set(attempted) - set(recorded)),
                "recorded_at": utc_now(),
            }
            event["event_id"] = f"transition-{canonical_digest(event)[:32]}"
            outbox_event_id = self._event(
                connection,
                context,
                "durable_task",
                safe_task,
                "durable.task.transitioned",
                f"durable-transition:{safe_task}:{safe_key}",
                event,
            )
            encoded = canonical_json(event)
            event_digest = sha256_bytes(encoded.encode("utf-8"))
            connection.execute(
                """
                INSERT INTO durable_transitions (
                    transition_id,tenant_id,project_id,actor_id,task_id,sequence_number,
                    idempotency_key,request_digest,from_state,target_state,event_json,
                    event_sha256,outbox_event_id,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    event["event_id"],
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    safe_task,
                    sequence_number,
                    safe_key,
                    request_digest,
                    authoritative,
                    target,
                    encoded,
                    event_digest,
                    outbox_event_id,
                    event["recorded_at"],
                ),
            )
            return event, False

    def durable_task_state(self, context: TenantContext, task_id: str) -> dict[str, Any]:
        snapshot = self.durable_task_progress_page(
            context,
            task_id,
            after_sequence=0,
            limit=1,
        )
        return {
            "task_id": snapshot["task_id"],
            "state": snapshot["latest_state"],
            "sequence_number": snapshot["latest_sequence"],
            "last_event": snapshot["latest_event"],
        }

    def durable_task_progress_page(
        self,
        context: TenantContext,
        task_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Read ACL, cursor, page, and latest state in one SQLite snapshot.

        Every transition in the task is verified before any page is returned.
        This intentionally trades a bounded one-shot response for complete
        local corruption and state-chain detection.  Only the requested page
        is retained in memory.  A concurrent writer may commit in WAL mode,
        but its new transition cannot be mixed into this reader's snapshot.
        """

        safe_task = require_resource_id(task_id, "task_id")
        if (
            not isinstance(after_sequence, int)
            or isinstance(after_sequence, bool)
            or not 0 <= after_sequence <= MAX_SAFE_JSON_INTEGER
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 1000
        ):
            raise ValidationError("DURABLE_TASK_EVENT_PAGE_INVALID")
        with self._lock:
            if self._connection.in_transaction:
                raise IntegrityError("DURABLE_TASK_PROGRESS_ACTIVE_TRANSACTION")
            self._connection.execute("BEGIN")
            try:
                self._require(self._connection, context, self.READ)
                rows = self._connection.execute(
                    """
                    SELECT d.*,
                           o.event_id AS progress_outbox_event_id,
                           o.tenant_id AS progress_outbox_tenant_id,
                           o.project_id AS progress_outbox_project_id,
                           o.aggregate_type AS progress_outbox_aggregate_type,
                           o.aggregate_id AS progress_outbox_aggregate_id,
                           o.event_type AS progress_outbox_event_type,
                           o.idempotency_key AS progress_outbox_idempotency_key,
                           o.payload_json AS progress_outbox_payload_json,
                           o.payload_digest AS progress_outbox_payload_digest,
                           o.occurred_at AS progress_outbox_occurred_at,
                           o.published_at AS progress_outbox_published_at
                      FROM durable_transitions AS d
                      LEFT JOIN outbox_events AS o
                        ON o.tenant_id=d.tenant_id
                       AND o.project_id=d.project_id
                       AND o.event_id=d.outbox_event_id
                     WHERE d.tenant_id=? AND d.project_id=? AND d.task_id=?
                     ORDER BY d.sequence_number
                    """,
                    (context.tenant_id, context.project_id, safe_task),
                )
                expected_sequence = 1
                prior_state = "PENDING"
                cursor_event: dict[str, Any] | None = None
                latest_event: dict[str, Any] | None = None
                page: list[dict[str, Any]] = []
                for row in rows:
                    event = self._durable_progress_event(row)
                    sequence = event["sequence_number"]
                    if (
                        sequence != expected_sequence
                        or event["from_state"] != prior_state
                        or event["target_state"] not in self._DURABLE_TRANSITIONS[prior_state]
                    ):
                        raise IntegrityError("DURABLE_TRANSITION_CHAIN_CORRUPT")
                    expected_sequence += 1
                    prior_state = event["target_state"]
                    latest_event = event
                    if sequence == after_sequence:
                        cursor_event = event
                    elif sequence > after_sequence and len(page) < limit:
                        page.append(event)
                latest_sequence = expected_sequence - 1
                if after_sequence > 0 and after_sequence <= latest_sequence and cursor_event is None:
                    raise IntegrityError("DURABLE_TRANSITION_CHAIN_CORRUPT")
                self._connection.execute("COMMIT")
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
        return {
            "task_id": safe_task,
            "latest_state": prior_state,
            "latest_sequence": latest_sequence,
            "latest_event": latest_event,
            "cursor_event": cursor_event,
            "events": page,
        }

    def durable_task_events(
        self,
        context: TenantContext,
        task_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return an exact bounded transition page for resumable read surfaces."""

        snapshot = self.durable_task_progress_page(
            context,
            task_id,
            after_sequence=after_sequence,
            limit=limit,
        )
        return list(snapshot["events"])

    @staticmethod
    def _core_outbox_event_id(
        *,
        tenant_id: str,
        project_id: str,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        idempotency_key: str,
        payload_digest: str,
        occurred_at: str,
    ) -> str:
        identity = {
            "schema_version": "core-outbox-event-identity-v1",
            "tenant_id": tenant_id,
            "project_id": project_id,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "event_type": event_type,
            "idempotency_key": idempotency_key,
            "payload_digest": payload_digest,
            "occurred_at": occurred_at,
        }
        return f"evt-{canonical_digest(identity)[:32]}"

    @classmethod
    def _encode_core_outbox_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> tuple[str, bytes, str]:
        if not isinstance(payload, Mapping):
            raise ValidationError("OUTBOX_EVENT_PAYLOAD_INVALID")
        encoded = canonical_json(dict(payload))
        try:
            encoded_bytes = encoded.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise ValidationError("OUTBOX_EVENT_PAYLOAD_INVALID") from error
        if not encoded_bytes or len(encoded_bytes) > cls._MAX_CORE_OUTBOX_PAYLOAD_BYTES:
            raise ValidationError("OUTBOX_EVENT_PAYLOAD_TOO_LARGE")
        return encoded, encoded_bytes, sha256_bytes(encoded_bytes)

    @staticmethod
    def _core_outbox_timestamp(value: Any, field: str) -> datetime:
        if not isinstance(value, str) or not 20 <= len(value) <= 64:
            raise IntegrityError("OUTBOX_EVENT_TIMESTAMP_INVALID", field)
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise IntegrityError("OUTBOX_EVENT_TIMESTAMP_INVALID", field) from error
        if (
            parsed.tzinfo is None
            or parsed.utcoffset() != timedelta(0)
            or parsed.microsecond != 0
            or parsed.isoformat() != value
        ):
            raise IntegrityError("OUTBOX_EVENT_TIMESTAMP_INVALID", field)
        return parsed.astimezone(UTC)

    @classmethod
    def _materialize_core_outbox_row(
        cls,
        row: Mapping[str, Any] | sqlite3.Row,
        *,
        expected_tenant_id: str | None = None,
        expected_project_id: str | None = None,
    ) -> dict[str, Any]:
        required = {
            "event_id",
            "tenant_id",
            "project_id",
            "aggregate_type",
            "aggregate_id",
            "event_type",
            "idempotency_key",
            "payload_json",
            "payload_digest",
            "occurred_at",
            "published_at",
        }
        if not required.issubset(set(row.keys())):
            raise IntegrityError("OUTBOX_EVENT_CORRUPT")
        if row["payload_digest"] is None:
            raise ConflictError(
                "OUTBOX_EVENT_RECONCILIATION_REQUIRED",
                retryable=False,
                details={
                    "automatic_retry_allowed": False,
                    "reason": "LEGACY_PAYLOAD_DIGEST_MISSING",
                },
            )
        try:
            resource_fields = {
                field: require_resource_id(row[field], field)
                for field in (
                    "event_id",
                    "tenant_id",
                    "project_id",
                    "aggregate_type",
                    "aggregate_id",
                    "event_type",
                )
            }
            idempotency_key = require_idempotency_key(row["idempotency_key"])
            stored_digest = normalize_sha256(row["payload_digest"])
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or not encoded:
                raise ValueError("outbox payload is not text")
            encoded_bytes = encoded.encode("utf-8", errors="strict")
            if len(encoded_bytes) > cls._MAX_CORE_OUTBOX_PAYLOAD_BYTES:
                raise ValueError("outbox payload exceeds the replay bound")
            payload = json.loads(encoded)
            canonical = canonical_json(payload)
        except Exception as error:
            raise IntegrityError("OUTBOX_EVENT_CORRUPT") from error
        if (
            any(row[field] != value for field, value in resource_fields.items())
            or row["idempotency_key"] != idempotency_key
            or row["payload_digest"] != stored_digest
            or not isinstance(payload, dict)
            or canonical != encoded
            or not hmac.compare_digest(stored_digest, sha256_bytes(encoded_bytes))
        ):
            raise IntegrityError("OUTBOX_EVENT_CORRUPT")
        occurred_at = cls._core_outbox_timestamp(row["occurred_at"], "occurred_at")
        published_at = None
        if row["published_at"] is not None:
            published_at = cls._core_outbox_timestamp(row["published_at"], "published_at")
            if published_at < occurred_at:
                raise IntegrityError("OUTBOX_EVENT_PUBLICATION_STATE_INVALID")
        expected_event_id = cls._core_outbox_event_id(
            tenant_id=resource_fields["tenant_id"],
            project_id=resource_fields["project_id"],
            aggregate_type=resource_fields["aggregate_type"],
            aggregate_id=resource_fields["aggregate_id"],
            event_type=resource_fields["event_type"],
            idempotency_key=idempotency_key,
            payload_digest=stored_digest,
            occurred_at=row["occurred_at"],
        )
        if (
            not hmac.compare_digest(resource_fields["event_id"], expected_event_id)
            or (
                expected_tenant_id is not None
                and resource_fields["tenant_id"] != expected_tenant_id
            )
            or (
                expected_project_id is not None
                and resource_fields["project_id"] != expected_project_id
            )
        ):
            raise IntegrityError("OUTBOX_EVENT_BINDING_MISMATCH")
        return {
            **resource_fields,
            "idempotency_key": idempotency_key,
            "payload": payload,
            "payload_json": encoded,
            "payload_digest": stored_digest,
            "occurred_at": row["occurred_at"],
            "published_at": row["published_at"],
        }

    def outbox_events(
        self,
        context: TenantContext,
        *,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        published: bool | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.require(context, self.READ)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
            raise ValidationError("OUTBOX_LIMIT_INVALID")
        clauses = ["tenant_id=?", "project_id=?"]
        parameters: list[Any] = [context.tenant_id, context.project_id]
        if aggregate_type is not None:
            clauses.append("aggregate_type=?")
            parameters.append(require_resource_id(aggregate_type, "aggregate_type"))
        if aggregate_id is not None:
            clauses.append("aggregate_id=?")
            parameters.append(require_resource_id(aggregate_id, "aggregate_id"))
        if published is not None:
            clauses.append("published_at IS NOT NULL" if published else "published_at IS NULL")
        parameters.append(limit)
        rows = self._connection.execute(
            f"""
            SELECT * FROM outbox_events
             WHERE {' AND '.join(clauses)}
             ORDER BY occurred_at,event_id LIMIT ?
            """,
            tuple(parameters),
        ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            event = self._materialize_core_outbox_row(
                row,
                expected_tenant_id=context.tenant_id,
                expected_project_id=context.project_id,
            )
            events.append(
                {
                    key: event[key]
                    for key in (
                        "event_id",
                        "aggregate_type",
                        "aggregate_id",
                        "event_type",
                        "idempotency_key",
                        "payload",
                        "payload_digest",
                        "occurred_at",
                        "published_at",
                    )
                }
            )
        return events

    def mark_outbox_published(
        self,
        context: TenantContext,
        event_id: str,
        *,
        publisher_capability: object,
        response_verifier_capability: object | None = None,
        transport_receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        if (
            self._outbox_publisher_capability is None
            or publisher_capability is not self._outbox_publisher_capability
        ):
            raise AuthorizationError("OUTBOX_PUBLISHER_AUTHORITY_REQUIRED")
        if (
            self._outbox_response_verifier_capability is None
            or response_verifier_capability
            is not self._outbox_response_verifier_capability
        ):
            raise AuthorizationError("OUTBOX_RESPONSE_VERIFIER_AUTHORITY_REQUIRED")
        safe_event = require_resource_id(event_id, "event_id")
        if not isinstance(transport_receipt, Mapping) or set(transport_receipt) != {
            "schema_version",
            "event_id",
            "payload_digest",
            "transport",
            "delivery_id",
            "status",
            "delivered_at",
            "response_digest",
        }:
            raise ValidationError("OUTBOX_TRANSPORT_RECEIPT_INVALID")
        receipt = dict(transport_receipt)
        if receipt.get("schema_version") != "core-outbox-transport-receipt-v1":
            raise ValidationError("OUTBOX_TRANSPORT_RECEIPT_INVALID")
        if receipt.get("status") != "DELIVERED":
            raise ConflictError("OUTBOX_TRANSPORT_DELIVERY_NOT_CONFIRMED")
        if receipt.get("event_id") != safe_event:
            raise ConflictError("OUTBOX_TRANSPORT_RECEIPT_BINDING_MISMATCH")
        raw_transport = receipt.get("transport")
        raw_delivery_id = receipt.get("delivery_id")
        raw_payload_digest = receipt.get("payload_digest")
        raw_response_digest = receipt.get("response_digest")
        if (
            not isinstance(raw_transport, str)
            or not isinstance(raw_delivery_id, str)
            or not isinstance(raw_payload_digest, str)
            or not isinstance(raw_response_digest, str)
        ):
            raise ValidationError("OUTBOX_TRANSPORT_RECEIPT_INVALID")
        transport = require_resource_id(raw_transport, "transport")
        delivery_id = require_resource_id(raw_delivery_id, "delivery_id")
        payload_digest = normalize_sha256(raw_payload_digest)
        response_digest = normalize_sha256(raw_response_digest)
        delivered_at = receipt.get("delivered_at")
        if not isinstance(delivered_at, str):
            raise ValidationError("OUTBOX_TRANSPORT_RECEIPT_INVALID")
        delivered_timestamp = self._core_outbox_timestamp(delivered_at, "delivered_at")
        if delivered_timestamp > datetime.now(UTC) + self._MAX_CORE_OUTBOX_FUTURE_SKEW:
            raise ValidationError("OUTBOX_TRANSPORT_RECEIPT_INVALID")
        receipt = {
            **receipt,
            "transport": transport,
            "delivery_id": delivery_id,
            "payload_digest": payload_digest,
            "response_digest": response_digest,
            "delivered_at": delivered_at,
        }
        receipt_json = canonical_json(receipt)
        receipt_digest = sha256_bytes(receipt_json.encode("utf-8"))
        with self.transaction() as connection:
            self._require(connection, context, self.WRITE)
            row = connection.execute(
                """
                SELECT * FROM outbox_events
                 WHERE event_id=? AND tenant_id=? AND project_id=?
                """,
                (safe_event, context.tenant_id, context.project_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("OUTBOX_EVENT_NOT_FOUND")
            event = self._materialize_core_outbox_row(
                row,
                expected_tenant_id=context.tenant_id,
                expected_project_id=context.project_id,
            )
            if event["event_id"] != safe_event:
                raise IntegrityError("OUTBOX_EVENT_BINDING_MISMATCH")
            if not hmac.compare_digest(event["payload_digest"], payload_digest):
                raise ConflictError("OUTBOX_TRANSPORT_RECEIPT_BINDING_MISMATCH")
            if delivered_timestamp < self._core_outbox_timestamp(
                event["occurred_at"], "occurred_at"
            ):
                raise ValidationError("OUTBOX_TRANSPORT_RECEIPT_INVALID")
            existing = connection.execute(
                """
                SELECT actor_id,receipt_json,receipt_digest,
                       verified_response_digest,delivered_at
                  FROM core_outbox_delivery_receipts
                 WHERE event_id=? AND tenant_id=? AND project_id=?
                """,
                (safe_event, context.tenant_id, context.project_id),
            ).fetchone()
            if existing is not None:
                if (
                    not hmac.compare_digest(existing["receipt_digest"], receipt_digest)
                    or existing["actor_id"] != context.actor_id
                    or existing["receipt_json"] != receipt_json
                    or not hmac.compare_digest(
                        existing["verified_response_digest"], response_digest
                    )
                    or existing["delivered_at"] != delivered_at
                    or event["published_at"] != delivered_at
                ):
                    raise ConflictError("OUTBOX_TRANSPORT_RECEIPT_CONFLICT")
                return {
                    "event_id": safe_event,
                    "published_at": delivered_at,
                    "transport_receipt_digest": receipt_digest,
                    "verified_response_digest": response_digest,
                }
            if event["published_at"] is not None:
                raise ConflictError(
                    "OUTBOX_EVENT_RECONCILIATION_REQUIRED",
                    retryable=False,
                )
            connection.execute(
                """
                INSERT INTO core_outbox_delivery_receipts (
                    event_id,tenant_id,project_id,actor_id,payload_digest,
                    transport,delivery_id,receipt_json,receipt_digest,
                    verified_response_digest,delivered_at,
                    publisher_capability_id,response_verifier_capability_id,
                    recorded_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    safe_event,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    payload_digest,
                    transport,
                    delivery_id,
                    receipt_json,
                    receipt_digest,
                    response_digest,
                    delivered_at,
                    self._outbox_publisher_capability_id,
                    self._outbox_response_verifier_capability_id,
                    utc_now(),
                ),
            )
            connection.execute(
                """
                UPDATE outbox_events SET published_at=?
                 WHERE event_id=? AND tenant_id=? AND project_id=?
                """,
                (delivered_at, safe_event, context.tenant_id, context.project_id),
            )
            return {
                "event_id": safe_event,
                "published_at": delivered_at,
                "transport_receipt_digest": receipt_digest,
                "verified_response_digest": response_digest,
            }

    @staticmethod
    def _effect_receipts(values: Sequence[str]) -> list[str]:
        if isinstance(values, (str, bytes)) or len(values) > 1000:
            raise ValidationError("DURABLE_EFFECT_RECEIPTS_INVALID")
        result: set[str] = set()
        for value in values:
            result.add(require_resource_id(value, "effect_receipt_id"))
        return sorted(result)

    @classmethod
    def _durable_event(cls, row: sqlite3.Row) -> dict[str, Any]:
        encoded = row["event_json"]
        event_sha256 = row["event_sha256"]
        if not isinstance(encoded, str) or not isinstance(event_sha256, str):
            raise IntegrityError("DURABLE_TRANSITION_EVENT_CORRUPT")
        try:
            encoded_bytes = encoded.encode("utf-8", errors="strict")
            normalized_event_sha = normalize_sha256(event_sha256)
            event = json.loads(encoded)
        except (
            TypeError,
            UnicodeEncodeError,
            json.JSONDecodeError,
            RecursionError,
            ValidationError,
        ) as error:
            raise IntegrityError("DURABLE_TRANSITION_EVENT_CORRUPT") from error
        if (
            event_sha256 != normalized_event_sha
            or not hmac.compare_digest(sha256_bytes(encoded_bytes), normalized_event_sha)
            or not isinstance(event, dict)
            or set(event) != cls._DURABLE_EVENT_FIELDS
        ):
            raise IntegrityError("DURABLE_TRANSITION_EVENT_CORRUPT")
        try:
            if canonical_json(event) != encoded:
                raise IntegrityError("DURABLE_TRANSITION_EVENT_CORRUPT")
            tenant_id = require_resource_id(event["tenant_id"], "tenant_id")
            project_id = require_resource_id(event["project_id"], "project_id")
            actor_id = require_actor_id(event["actor_id"])
            task_id = require_resource_id(event["task_id"], "task_id")
            idempotency_key = require_idempotency_key(event["idempotency_key"])
            request_digest = normalize_sha256(event["request_digest"])
            payload_digest = normalize_sha256(event["payload_digest"])
            checkpoint_value = event["checkpoint_digest"]
            checkpoint_digest = (
                normalize_sha256(checkpoint_value) if checkpoint_value is not None else None
            )
            sequence = event["sequence_number"]
            from_state = event["from_state"]
            target_state = event["target_state"]
            recorded_at = event["recorded_at"]
            recorded = datetime.fromisoformat(recorded_at)
            if (
                tenant_id != event["tenant_id"]
                or project_id != event["project_id"]
                or actor_id != event["actor_id"]
                or task_id != event["task_id"]
                or idempotency_key != event["idempotency_key"]
                or request_digest != event["request_digest"]
                or payload_digest != event["payload_digest"]
                or checkpoint_digest != checkpoint_value
                or event["skill"] != "elmos-durable-processing-and-recovery"
                or isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or not 1 <= sequence <= MAX_SAFE_JSON_INTEGER
                or from_state not in cls._DURABLE_TRANSITIONS
                or target_state not in cls._DURABLE_TRANSITIONS[from_state]
                or recorded.tzinfo is None
                or recorded.utcoffset() is None
            ):
                raise IntegrityError("DURABLE_TRANSITION_EVENT_CORRUPT")
            for field in ("effects_to_skip", "effects_to_reconcile"):
                effects = event[field]
                if not isinstance(effects, list) or len(effects) > 1000:
                    raise IntegrityError("DURABLE_TRANSITION_EVENT_CORRUPT")
                normalized_effects = [
                    require_resource_id(value, "effect_receipt_id") for value in effects
                ]
                if effects != sorted(set(normalized_effects)):
                    raise IntegrityError("DURABLE_TRANSITION_EVENT_CORRUPT")
            expected_event_id = (
                "transition-"
                + canonical_digest(
                    {key: value for key, value in event.items() if key != "event_id"}
                )[:32]
            )
        except IntegrityError:
            raise
        except (KeyError, TypeError, ValueError, RecursionError, ValidationError) as error:
            raise IntegrityError("DURABLE_TRANSITION_EVENT_CORRUPT") from error
        if (
            not isinstance(event["event_id"], str)
            or not hmac.compare_digest(event["event_id"], expected_event_id)
            or event["event_id"] != row["transition_id"]
            or tenant_id != row["tenant_id"]
            or project_id != row["project_id"]
            or actor_id != row["actor_id"]
            or task_id != row["task_id"]
            or sequence != row["sequence_number"]
            or idempotency_key != row["idempotency_key"]
            or request_digest != row["request_digest"]
            or from_state != row["from_state"]
            or target_state != row["target_state"]
            or recorded_at != row["created_at"]
        ):
            raise IntegrityError("DURABLE_TRANSITION_ROW_EVENT_MISMATCH")
        return event

    @classmethod
    def _durable_progress_event(cls, row: sqlite3.Row) -> dict[str, Any]:
        event = cls._durable_event(row)
        required_aliases = {
            "progress_outbox_event_id",
            "progress_outbox_tenant_id",
            "progress_outbox_project_id",
            "progress_outbox_aggregate_type",
            "progress_outbox_aggregate_id",
            "progress_outbox_event_type",
            "progress_outbox_idempotency_key",
            "progress_outbox_payload_json",
            "progress_outbox_payload_digest",
            "progress_outbox_occurred_at",
            "progress_outbox_published_at",
        }
        if not required_aliases.issubset(set(row.keys())):
            raise IntegrityError("DURABLE_TRANSITION_OUTBOX_MISMATCH")
        outbox = cls._materialize_core_outbox_row(
            {
                "event_id": row["progress_outbox_event_id"],
                "tenant_id": row["progress_outbox_tenant_id"],
                "project_id": row["progress_outbox_project_id"],
                "aggregate_type": row["progress_outbox_aggregate_type"],
                "aggregate_id": row["progress_outbox_aggregate_id"],
                "event_type": row["progress_outbox_event_type"],
                "idempotency_key": row["progress_outbox_idempotency_key"],
                "payload_json": row["progress_outbox_payload_json"],
                "payload_digest": row["progress_outbox_payload_digest"],
                "occurred_at": row["progress_outbox_occurred_at"],
                "published_at": row["progress_outbox_published_at"],
            },
            expected_tenant_id=event["tenant_id"],
            expected_project_id=event["project_id"],
        )
        expected_idempotency_key = (
            f"durable-transition:{event['task_id']}:{event['idempotency_key']}"
        )
        if (
            outbox["event_id"] != row["outbox_event_id"]
            or outbox["aggregate_type"] != "durable_task"
            or outbox["aggregate_id"] != event["task_id"]
            or outbox["event_type"] != "durable.task.transitioned"
            or outbox["idempotency_key"] != expected_idempotency_key
            or outbox["payload_json"] != row["event_json"]
            or outbox["payload"] != event
        ):
            raise IntegrityError("DURABLE_TRANSITION_OUTBOX_MISMATCH")
        return event

    @staticmethod
    def _next_offset(connection: sqlite3.Connection, upload: sqlite3.Row) -> int:
        expected = 0
        for part in connection.execute(
            """
            SELECT * FROM upload_parts
             WHERE tenant_id=? AND project_id=? AND upload_id=? ORDER BY part_number
            """,
            (upload["tenant_id"], upload["project_id"], upload["upload_id"]),
        ).fetchall():
            if part["byte_offset"] != expected:
                break
            expected += part["byte_size"]
        return expected

    @staticmethod
    def _session(row: sqlite3.Row) -> InputSession:
        return InputSession(
            session_id=row["session_id"],
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            created_by=row["created_by"],
            requested_role=row["requested_role"],
            status=SessionStatus(row["status"]),
            idempotency_key=row["idempotency_key"],
            trace_id=row["trace_id"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _asset(row: sqlite3.Row) -> InputAsset:
        return InputAsset(
            asset_id=row["asset_id"],
            session_id=row["session_id"],
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            display_name=row["display_name"],
            declared_media_type=row["declared_media_type"],
            detected_media_type=row["detected_media_type"],
            kind=AssetKind(row["kind"]),
            byte_size=row["byte_size"],
            sha256=row["sha256"],
            cas_digest=row["cas_digest"],
            status=AssetStatus(row["status"]),
            security_decision=SecurityDecision(row["security_decision"]) if row["security_decision"] else None,
            failure_code=row["failure_code"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _upload(row: sqlite3.Row) -> UploadSession:
        return UploadSession(
            upload_id=row["upload_id"],
            asset_id=row["asset_id"],
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            idempotency_key=row["idempotency_key"],
            request_digest=row["request_digest"],
            expected_size=row["expected_size"],
            expected_sha256=row["expected_sha256"],
            part_size=row["part_size"],
            status=UploadStatus(row["status"]),
            received_bytes=row["received_bytes"],
            commit_idempotency_key=row["commit_idempotency_key"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _job(row: sqlite3.Row) -> ProcessingJob:
        version = row["version"]
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or not 1 <= version <= MAX_SAFE_JSON_INTEGER
        ):
            raise IntegrityError("PROCESSING_JOB_VERSION_INVALID")
        cancel_requested = row["cancel_requested"]
        cancel_requested_by = row["cancel_requested_by"]
        cancel_requested_at = row["cancel_requested_at"]
        cancel_reason = row["cancel_reason"]
        if cancel_requested not in {0, 1}:
            raise IntegrityError("PROCESSING_JOB_CANCELLATION_STATE_CORRUPT")
        if cancel_requested == 0:
            if any(
                value is not None
                for value in (cancel_requested_by, cancel_requested_at, cancel_reason)
            ):
                raise IntegrityError("PROCESSING_JOB_CANCELLATION_STATE_CORRUPT")
        else:
            try:
                require_actor_id(cancel_requested_by)
                safe_reason = require_resource_id(cancel_reason, "cancel_reason")
                requested_at = datetime.fromisoformat(cancel_requested_at)
            except (TypeError, ValueError, ValidationError) as error:
                raise IntegrityError("PROCESSING_JOB_CANCELLATION_STATE_CORRUPT") from error
            if (
                len(safe_reason) > 128
                or requested_at.tzinfo is None
                or requested_at.utcoffset() is None
                or requested_at.isoformat() != cancel_requested_at
            ):
                raise IntegrityError("PROCESSING_JOB_CANCELLATION_STATE_CORRUPT")
        try:
            job = _VersionedProcessingJob(
                job_id=row["job_id"],
                tenant_id=row["tenant_id"],
                project_id=row["project_id"],
                session_id=row["session_id"],
                idempotency_key=row["idempotency_key"],
                request_digest=row["request_digest"],
                status=JobStatus(row["status"]),
                stage=row["stage"],
                attempt=row["attempt"],
                max_attempts=row["max_attempts"],
                result_status=ResultStatus(row["result_status"]),
                failure_code=row["failure_code"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                cancel_requested=bool(cancel_requested),
                cancel_requested_by=cancel_requested_by,
                cancel_requested_at=cancel_requested_at,
                cancel_reason=cancel_reason,
            )
        except (TypeError, ValueError) as error:
            raise IntegrityError("PROCESSING_JOB_STATE_CORRUPT") from error
        object.__setattr__(job, "version", version)
        return job

    @staticmethod
    def _anchor(row: sqlite3.Row) -> SourceAnchor:
        bbox_value = json.loads(row["bbox_json"]) if row["bbox_json"] else None
        if bbox_value is not None and (
            not isinstance(bbox_value, list)
            or len(bbox_value) != 4
            or any(
                not isinstance(value, (int, float)) or isinstance(value, bool)
                for value in bbox_value
            )
        ):
            raise ValueError("source anchor bbox is invalid")
        bbox = (
            (float(bbox_value[0]), float(bbox_value[1]), float(bbox_value[2]), float(bbox_value[3]))
            if isinstance(bbox_value, list)
            else None
        )
        return SourceAnchor(
            anchor_id=row["anchor_id"],
            asset_id=row["asset_id"],
            source_sha256=row["source_sha256"],
            locator_type=row["locator_type"],
            page_number=row["page_number"],
            paragraph_index=row["paragraph_index"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            time_start_ms=row["time_start_ms"],
            time_end_ms=row["time_end_ms"],
            bbox=bbox,
            symbol=row["symbol"],
            excerpt_sha256=row["excerpt_sha256"],
        )

    @staticmethod
    def _scoped_session(connection: sqlite3.Connection, context: TenantContext, session_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM input_sessions WHERE session_id=? AND tenant_id=? AND project_id=?",
            (session_id, context.tenant_id, context.project_id),
        ).fetchone()
        if not isinstance(row, sqlite3.Row):
            raise NotFoundError("INPUT_SESSION_NOT_FOUND")
        return row

    @staticmethod
    def _scoped_upload(connection: sqlite3.Connection, context: TenantContext, upload_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM upload_sessions WHERE upload_id=? AND tenant_id=? AND project_id=?",
            (upload_id, context.tenant_id, context.project_id),
        ).fetchone()
        if not isinstance(row, sqlite3.Row):
            raise NotFoundError("UPLOAD_SESSION_NOT_FOUND")
        return row

    @staticmethod
    def _scoped_asset(connection: sqlite3.Connection, context: TenantContext, asset_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM input_assets WHERE asset_id=? AND tenant_id=? AND project_id=?",
            (asset_id, context.tenant_id, context.project_id),
        ).fetchone()
        if not isinstance(row, sqlite3.Row):
            raise NotFoundError("INPUT_ASSET_NOT_FOUND")
        return row

    @staticmethod
    def _scoped_job(connection: sqlite3.Connection, context: TenantContext, job_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM processing_jobs WHERE job_id=? AND tenant_id=? AND project_id=?",
            (job_id, context.tenant_id, context.project_id),
        ).fetchone()
        if not isinstance(row, sqlite3.Row):
            raise NotFoundError("PROCESSING_JOB_NOT_FOUND")
        return row

    @classmethod
    def _require_job_lease(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        job_id: str,
        owner_token: str,
    ) -> sqlite3.Row:
        owner = require_idempotency_key(owner_token)
        row = cls._scoped_job(connection, context, job_id)
        if (
            row["status"] != JobStatus.RUNNING.value
            or row["lease_owner"] != owner
            or str(row["lease_expires_at"] or "") <= utc_now()
        ):
            raise ConflictError("PROCESSING_JOB_LEASE_NOT_OWNED")
        return row

    @classmethod
    def _event(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> str:
        safe_tenant = require_resource_id(context.tenant_id, "tenant_id")
        safe_project = require_resource_id(context.project_id, "project_id")
        safe_aggregate_type = require_resource_id(aggregate_type, "aggregate_type")
        safe_aggregate_id = require_resource_id(aggregate_id, "aggregate_id")
        safe_event_type = require_resource_id(event_type, "event_type")
        safe_key = require_idempotency_key(idempotency_key)
        encoded, _encoded_bytes, payload_digest = cls._encode_core_outbox_payload(payload)
        existing = connection.execute(
            """
            SELECT * FROM outbox_events
             WHERE tenant_id=? AND project_id=? AND idempotency_key=?
            """,
            (safe_tenant, safe_project, safe_key),
        ).fetchone()
        if existing is not None:
            event = cls._materialize_core_outbox_row(
                existing,
                expected_tenant_id=safe_tenant,
                expected_project_id=safe_project,
            )
            if (
                event["aggregate_type"] != safe_aggregate_type
                or event["aggregate_id"] != safe_aggregate_id
                or event["event_type"] != safe_event_type
                or event["idempotency_key"] != safe_key
                or event["payload_json"] != encoded
                or not hmac.compare_digest(event["payload_digest"], payload_digest)
            ):
                raise ConflictError("OUTBOX_EVENT_IDEMPOTENCY_CONFLICT")
            existing_event_id = event["event_id"]
            if not isinstance(existing_event_id, str):
                raise IntegrityError("OUTBOX_EVENT_CORRUPT")
            return existing_event_id
        occurred_at = utc_now()
        event_id = cls._core_outbox_event_id(
            tenant_id=safe_tenant,
            project_id=safe_project,
            aggregate_type=safe_aggregate_type,
            aggregate_id=safe_aggregate_id,
            event_type=safe_event_type,
            idempotency_key=safe_key,
            payload_digest=payload_digest,
            occurred_at=occurred_at,
        )
        connection.execute(
            """
            INSERT INTO outbox_events (
                event_id,tenant_id,project_id,aggregate_type,aggregate_id,event_type,
                idempotency_key,payload_json,occurred_at,published_at,payload_digest
            ) VALUES (?,?,?,?,?,?,?,?,?,NULL,?)
            """,
            (
                event_id,
                safe_tenant,
                safe_project,
                safe_aggregate_type,
                safe_aggregate_id,
                safe_event_type,
                safe_key,
                encoded,
                occurred_at,
                payload_digest,
            ),
        )
        return event_id

    @staticmethod
    def _security_finding(
        connection: sqlite3.Connection,
        context: TenantContext,
        asset_id: str,
        decision: SecurityDecision,
        code: str,
        details: dict[str, Any],
    ) -> None:
        finding_id = f"finding-{canonical_digest([asset_id, decision.value, code])[:32]}"
        connection.execute(
            "INSERT OR IGNORE INTO security_findings VALUES (?,?,?,?,?,?,?,?)",
            (
                finding_id,
                context.tenant_id,
                context.project_id,
                asset_id,
                decision.value,
                code,
                canonical_json(details),
                utc_now(),
            ),
        )
