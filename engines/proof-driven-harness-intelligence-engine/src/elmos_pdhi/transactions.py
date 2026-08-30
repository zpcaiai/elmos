"""Stale-safe, scope-fenced, content-addressed patch transactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
import threading
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .canonical import digest_bytes, digest_object, require_sha256_digest
from .semantic import OperationSpec


class TransactionStatus(str, Enum):
    PREPARED = "PREPARED"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    CONFLICTED = "CONFLICTED"
    APPLIED = "APPLIED"
    VERIFIED = "VERIFIED"
    COMMITTED = "COMMITTED"
    POSTCONDITION_FAILED = "POSTCONDITION_FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    APPLY_FAILED = "APPLY_FAILED"


@dataclass(frozen=True, slots=True)
class ScopeFence:
    root: str
    allowed_paths: tuple[str, ...]
    fence_token: str

    def __post_init__(self) -> None:
        root_path = Path(self.root).absolute()
        metadata = root_path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("scope root must be a real directory")
        if not self.allowed_paths:
            raise ValueError("scope fence requires at least one allowed path")
        normalized = tuple(_validate_relative_path(item) for item in self.allowed_paths)
        if len(set(normalized)) != len(normalized):
            raise ValueError("scope paths must be unique")
        if not self.fence_token.strip() or len(self.fence_token) > 256:
            raise ValueError("fence_token is required and bounded")
        object.__setattr__(self, "root", str(root_path))
        object.__setattr__(self, "allowed_paths", normalized)

    def authorize(self, path: str, fence_token: str) -> str:
        normalized = _validate_relative_path(path)
        if not secrets.compare_digest(self.fence_token, fence_token):
            raise PermissionError("stale or invalid workspace fence token")
        if not any(
            normalized == allowed or normalized.startswith(f"{allowed}/")
            for allowed in self.allowed_paths
        ):
            raise PermissionError(f"path is outside the write scope: {normalized}")
        return normalized


@dataclass(frozen=True, slots=True)
class ContentAnchor:
    path: str
    exists: bool
    digest: str | None
    size: int
    mode: int | None

    def __post_init__(self) -> None:
        _validate_relative_path(self.path)
        if self.exists:
            if self.digest is None or self.mode is None or self.size < 0:
                raise ValueError("existing content anchor is incomplete")
            require_sha256_digest(self.digest)
        elif self.digest is not None or self.mode is not None or self.size != 0:
            raise ValueError("absent content anchor cannot claim content metadata")


@dataclass(frozen=True, slots=True)
class SymbolAnchor:
    path: str
    symbol_identity: str
    content_digest: str
    span_start: int
    span_end: int
    symbol_digest: str

    def __post_init__(self) -> None:
        _validate_relative_path(self.path)
        if not self.symbol_identity.strip():
            raise ValueError("symbol_identity is required")
        if self.span_start < 0 or self.span_end < self.span_start:
            raise ValueError("symbol anchor span is invalid")
        require_sha256_digest(self.content_digest)
        require_sha256_digest(self.symbol_digest)


@dataclass(frozen=True, slots=True)
class WriteIntent:
    path: str
    expected: ContentAnchor
    content: bytes | None
    mode: int = 0o644
    symbol_anchor: SymbolAnchor | None = None

    def __post_init__(self) -> None:
        normalized = _validate_relative_path(self.path)
        if self.expected.path != normalized:
            raise ValueError("write intent and content anchor paths differ")
        if self.symbol_anchor is not None and self.symbol_anchor.path != normalized:
            raise ValueError("write intent and symbol anchor paths differ")
        if self.content is not None and not isinstance(self.content, bytes):
            raise TypeError("write content must be bytes or None")
        if not 0 <= self.mode <= 0o777:
            raise ValueError("write mode is invalid")


@dataclass(frozen=True, slots=True)
class Postcondition:
    kind: str
    path: str
    expected_digest: str | None = None
    expected_bytes: bytes | None = None

    def __post_init__(self) -> None:
        _validate_relative_path(self.path)
        if self.kind not in {"exists", "absent", "digest", "contains"}:
            raise ValueError("unsupported typed postcondition")
        if self.kind == "digest":
            if self.expected_digest is None:
                raise ValueError("digest postcondition requires expected_digest")
            require_sha256_digest(self.expected_digest)
        elif self.expected_digest is not None:
            raise ValueError("expected_digest is only valid for digest postconditions")
        if self.kind == "contains":
            if not self.expected_bytes:
                raise ValueError("contains postcondition requires non-empty bytes")
        elif self.expected_bytes is not None:
            raise ValueError("expected_bytes is only valid for contains postconditions")


@dataclass(frozen=True, slots=True)
class PatchPlan:
    transaction_id: str
    base_revision: str
    intent: str
    read_set: tuple[ContentAnchor, ...]
    write_set: tuple[WriteIntent, ...]
    postconditions: tuple[Postcondition, ...]
    dependencies: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.transaction_id.strip() or not self.intent.strip():
            raise ValueError("transaction identity and intent are required")
        require_sha256_digest(self.base_revision)
        read_paths = [item.path for item in self.read_set]
        write_paths = [item.path for item in self.write_set]
        if len(set(read_paths)) != len(read_paths):
            raise ValueError("read set contains duplicate paths")
        if not write_paths or len(set(write_paths)) != len(write_paths):
            raise ValueError("write set must be non-empty with unique paths")
        if not self.postconditions:
            raise ValueError("patch plan requires at least one typed postcondition")
        normalized_dependencies: dict[str, tuple[str, ...]] = {}
        for raw_path, raw_dependencies in self.dependencies.items():
            path = _validate_relative_path(raw_path)
            if path not in write_paths:
                raise ValueError("commit dependency owner is not in write_set")
            dependencies = tuple(_validate_relative_path(item) for item in raw_dependencies)
            if any(item not in write_paths for item in dependencies):
                raise ValueError("commit dependency target is not in write_set")
            normalized_dependencies[path] = dependencies
        object.__setattr__(self, "dependencies", MappingProxyType(normalized_dependencies))


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    stale_paths: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class SnapshotEntry:
    path: str
    existed: bool
    content_digest: str | None
    mode: int | None


@dataclass(frozen=True, slots=True)
class SnapshotReceipt:
    snapshot_id: str
    entries: tuple[SnapshotEntry, ...]
    evidence_digest: str

    def __post_init__(self) -> None:
        require_sha256_digest(self.snapshot_id)
        require_sha256_digest(self.evidence_digest)


@dataclass(frozen=True, slots=True)
class RollbackReceipt:
    snapshot_id: str
    restored_paths: tuple[str, ...]
    status: str
    evidence_digest: str
    reason: str | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.snapshot_id)
        require_sha256_digest(self.evidence_digest)
        if self.status not in {"RESTORED", "FAILED"}:
            raise ValueError("rollback status is invalid")


@dataclass(frozen=True, slots=True)
class TransactionReceipt:
    transaction_id: str
    status: TransactionStatus
    snapshot_id: str | None
    changed_paths: tuple[str, ...]
    stale_paths: tuple[str, ...]
    rollback: RollbackReceipt | None
    before_revision: str
    after_revision: str | None
    evidence_digest: str
    reason: str | None = None
    atomic_file_replacement: bool = True
    multi_file_atomicity: str = "COMPENSATED_NOT_GLOBALLY_ATOMIC"

    def __post_init__(self) -> None:
        require_sha256_digest(self.before_revision)
        require_sha256_digest(self.evidence_digest)
        if self.snapshot_id is not None:
            require_sha256_digest(self.snapshot_id)
        if self.after_revision is not None:
            require_sha256_digest(self.after_revision)


@dataclass(frozen=True, slots=True)
class RewriteIntent:
    content: bytes
    span_start: int
    span_end: int
    expected_fragment_digest: str
    replacement: bytes
    mapping_rule: str | None = None

    def __post_init__(self) -> None:
        if self.span_start < 0 or self.span_end < self.span_start:
            raise ValueError("rewrite span is invalid")
        if self.span_end > len(self.content):
            raise ValueError("rewrite span exceeds content")
        require_sha256_digest(self.expected_fragment_digest)


@dataclass(frozen=True, slots=True)
class RewriteResult:
    status: str
    content: bytes | None
    before_digest: str
    after_digest: str | None
    reason: str | None = None
    mapping_rule: str | None = None


@dataclass(frozen=True, slots=True)
class MergeValidation:
    valid: bool
    merged: bytes | None
    classification: str
    base_digest: str
    left_digest: str
    right_digest: str
    merged_digest: str | None


class ContentAddressedStore:
    """Bounded process-local CAS used only for deterministic transaction rollback."""

    def __init__(self, *, max_bytes: int = 128 * 1024 * 1024) -> None:
        if max_bytes <= 0:
            raise ValueError("CAS max_bytes must be positive")
        self._max_bytes = max_bytes
        self._size = 0
        self._objects: dict[str, bytes] = {}
        self._lock = threading.RLock()

    def put(self, content: bytes) -> str:
        digest = digest_bytes(content)
        with self._lock:
            if digest in self._objects:
                return digest
            if self._size + len(content) > self._max_bytes:
                raise ValueError("transaction CAS capacity exceeded")
            self._objects[digest] = bytes(content)
            self._size += len(content)
            return digest

    def get(self, digest: str) -> bytes:
        require_sha256_digest(digest)
        with self._lock:
            try:
                content = self._objects[digest]
            except KeyError as exc:
                raise KeyError("CAS object is unavailable") from exc
            if digest_bytes(content) != digest:
                raise RuntimeError("CAS integrity failure")
            return bytes(content)


class TransactionManager:
    """Apply bounded patches with stale checks and deterministic compensation."""

    def __init__(self, scope: ScopeFence, *, cas: ContentAddressedStore | None = None) -> None:
        self.scope = scope
        self.cas = cas or ContentAddressedStore()
        self._transaction_lock = threading.RLock()

    def execute(self, operation: str, **kwargs: Any) -> Any:
        spec = K2_OPERATION_SPECS.get(operation)
        if spec is None:
            raise KeyError(f"unknown K2 operation: {operation}")
        return getattr(self, spec.method)(**kwargs)

    def content_hash_anchor(self, path: str) -> ContentAnchor:
        normalized = _validate_relative_path(path)
        content, mode = _read_optional(self.scope.root, normalized)
        if content is None:
            return ContentAnchor(normalized, False, None, 0, None)
        return ContentAnchor(normalized, True, digest_bytes(content), len(content), mode)

    def symbol_identity_anchor(
        self,
        path: str,
        symbol_identity: str,
        span_start: int,
        span_end: int,
    ) -> SymbolAnchor:
        content, _ = _read_optional(self.scope.root, path)
        if content is None:
            raise FileNotFoundError(path)
        if span_start < 0 or span_end < span_start or span_end > len(content):
            raise ValueError("symbol span is outside the anchored content")
        return SymbolAnchor(
            path=_validate_relative_path(path),
            symbol_identity=symbol_identity,
            content_digest=digest_bytes(content),
            span_start=span_start,
            span_end=span_end,
            symbol_digest=digest_bytes(content[span_start:span_end]),
        )

    def semantic_anchor(self, **kwargs: Any) -> SymbolAnchor:
        return self.symbol_identity_anchor(**kwargs)

    def stale_state_detector(self, anchors: Sequence[ContentAnchor]) -> tuple[str, ...]:
        return tuple(
            sorted(
                anchor.path
                for anchor in anchors
                if self.content_hash_anchor(anchor.path) != anchor
            )
        )

    def read_set_tracker(self, paths: Sequence[str]) -> tuple[ContentAnchor, ...]:
        normalized = tuple(_validate_relative_path(path) for path in paths)
        if len(set(normalized)) != len(normalized):
            raise ValueError("read set paths must be unique")
        return tuple(self.content_hash_anchor(path) for path in normalized)

    @staticmethod
    def write_set_tracker(writes: Sequence[WriteIntent]) -> tuple[WriteIntent, ...]:
        result = tuple(writes)
        if not result or len({item.path for item in result}) != len(result):
            raise ValueError("write set must be non-empty with unique paths")
        return result

    @staticmethod
    def patch_intent_contract(
        *,
        transaction_id: str,
        base_revision: str,
        intent: str,
        read_set: Sequence[ContentAnchor],
        write_set: Sequence[WriteIntent],
        postconditions: Sequence[Postcondition],
        dependencies: Mapping[str, tuple[str, ...]] | None = None,
    ) -> PatchPlan:
        return PatchPlan(
            transaction_id=transaction_id,
            base_revision=base_revision,
            intent=intent,
            read_set=tuple(read_set),
            write_set=tuple(write_set),
            postconditions=tuple(postconditions),
            dependencies=dependencies or {},
        )

    def edit_precondition_validator(self, plan: PatchPlan) -> ValidationResult:
        anchors = tuple(plan.read_set) + tuple(item.expected for item in plan.write_set)
        stale = self.stale_state_detector(anchors)
        conflicts = self.semantic_conflict_detector(plan)
        return ValidationResult(
            valid=not stale and not conflicts,
            stale_paths=stale,
            conflicts=conflicts,
            reason=("stale anchors" if stale else "semantic conflicts" if conflicts else None),
        )

    def semantic_conflict_detector(self, plan: PatchPlan) -> tuple[str, ...]:
        conflicts: list[str] = []
        for write in plan.write_set:
            anchor = write.symbol_anchor
            if anchor is not None and anchor.content_digest != write.expected.digest:
                conflicts.append(f"{write.path}: symbol/content anchor mismatch")
            if anchor is not None:
                content, _ = _read_optional(self.scope.root, write.path)
                if (
                    content is None
                    or anchor.span_end > len(content)
                    or digest_bytes(content) != anchor.content_digest
                    or digest_bytes(content[anchor.span_start : anchor.span_end])
                    != anchor.symbol_digest
                ):
                    conflicts.append(f"{write.path}: symbol anchor is stale")
        try:
            _topological_order(tuple(item.path for item in plan.write_set), plan.dependencies)
        except ValueError as exc:
            conflicts.append(str(exc))
        return tuple(sorted(conflicts))

    @staticmethod
    def ast_structural_rewrite(intent: RewriteIntent) -> RewriteResult:
        return _rewrite(intent, require_mapping_rule=False)

    @staticmethod
    def semantic_ir_rewrite(intent: RewriteIntent) -> RewriteResult:
        return _rewrite(intent, require_mapping_rule=True)

    @staticmethod
    def framework_aware_rewrite(intent: RewriteIntent) -> RewriteResult:
        return _rewrite(intent, require_mapping_rule=True)

    def edit_postcondition_validator(
        self, postconditions: Sequence[Postcondition]
    ) -> ValidationResult:
        failures: list[str] = []
        for condition in postconditions:
            content, _ = _read_optional(self.scope.root, condition.path)
            if condition.kind == "exists" and content is None:
                failures.append(f"{condition.path}: expected to exist")
            elif condition.kind == "absent" and content is not None:
                failures.append(f"{condition.path}: expected to be absent")
            elif condition.kind == "digest" and (
                content is None or digest_bytes(content) != condition.expected_digest
            ):
                failures.append(f"{condition.path}: digest mismatch")
            elif condition.kind == "contains" and (
                content is None
                or condition.expected_bytes is None
                or condition.expected_bytes not in content
            ):
                failures.append(f"{condition.path}: required bytes are absent")
        return ValidationResult(not failures, conflicts=tuple(failures), reason=("postcondition failure" if failures else None))

    def snapshot_manager(self, paths: Sequence[str]) -> SnapshotReceipt:
        normalized = tuple(_validate_relative_path(path) for path in paths)
        if len(set(normalized)) != len(normalized):
            raise ValueError("snapshot paths must be unique")
        entries: list[SnapshotEntry] = []
        for path in sorted(normalized):
            content, mode = _read_optional(self.scope.root, path)
            entries.append(
                SnapshotEntry(
                    path=path,
                    existed=content is not None,
                    content_digest=self.cas.put(content) if content is not None else None,
                    mode=mode,
                )
            )
        evidence = digest_object(
            tuple((item.path, item.existed, item.content_digest, item.mode) for item in entries),
            domain="transaction-snapshot",
        )
        return SnapshotReceipt(evidence, tuple(entries), evidence)

    def rollback_manager(
        self, snapshot: SnapshotReceipt, *, fence_token: str
    ) -> RollbackReceipt:
        restored: list[str] = []
        try:
            for entry in snapshot.entries:
                self.scope.authorize(entry.path, fence_token)
                if entry.existed:
                    if entry.content_digest is None or entry.mode is None:
                        raise RuntimeError("snapshot entry is incomplete")
                    _atomic_replace(
                        self.scope.root,
                        entry.path,
                        self.cas.get(entry.content_digest),
                        entry.mode,
                    )
                else:
                    _unlink_if_exists(self.scope.root, entry.path)
                restored.append(entry.path)
            status = "RESTORED"
            reason = None
        except Exception as exc:
            status = "FAILED"
            reason = f"rollback failed: {type(exc).__name__}"
        evidence = digest_object(
            {
                "snapshot_id": snapshot.snapshot_id,
                "restored_paths": tuple(restored),
                "status": status,
                "reason": reason,
            },
            domain="transaction-rollback",
        )
        return RollbackReceipt(
            snapshot.snapshot_id, tuple(restored), status, evidence, reason
        )

    def transactional_patch(
        self, plan: PatchPlan, *, fence_token: str
    ) -> TransactionReceipt:
        with self._transaction_lock:
            return self._transactional_patch_locked(plan, fence_token=fence_token)

    def _transactional_patch_locked(
        self, plan: PatchPlan, *, fence_token: str
    ) -> TransactionReceipt:
        for item in plan.write_set:
            self.scope.authorize(item.path, fence_token)
        before_revision = _revision_digest(self, plan.read_set, plan.write_set)
        if before_revision != plan.base_revision:
            return _transaction_receipt(
                plan,
                TransactionStatus.PRECONDITION_FAILED,
                before_revision,
                stale_paths=tuple(sorted({item.path for item in plan.read_set} | {item.path for item in plan.write_set})),
                reason="base revision is stale",
            )
        validation = self.edit_precondition_validator(plan)
        if not validation.valid:
            status = TransactionStatus.PRECONDITION_FAILED if validation.stale_paths else TransactionStatus.CONFLICTED
            return _transaction_receipt(
                plan,
                status,
                before_revision,
                stale_paths=validation.stale_paths,
                reason=validation.reason,
            )
        try:
            snapshot = self.snapshot_manager(tuple(item.path for item in plan.write_set))
        except Exception as exc:
            return _transaction_receipt(
                plan,
                TransactionStatus.APPLY_FAILED,
                before_revision,
                reason=f"snapshot failed: {type(exc).__name__}",
            )
        order = self.atomic_commit_planner(plan)
        writes = {item.path: item for item in plan.write_set}
        changed: list[str] = []
        try:
            for path in order:
                write = writes[path]
                if write.content is None:
                    _unlink_if_exists(self.scope.root, path)
                else:
                    _atomic_replace(self.scope.root, path, write.content, write.mode)
                changed.append(path)
        except Exception as exc:
            rollback = self.rollback_manager(snapshot, fence_token=fence_token)
            return _transaction_receipt(
                plan,
                (
                    TransactionStatus.ROLLED_BACK
                    if rollback.status == "RESTORED"
                    else TransactionStatus.APPLY_FAILED
                ),
                before_revision,
                snapshot=snapshot,
                changed_paths=tuple(changed),
                rollback=rollback,
                reason=f"apply failed: {type(exc).__name__}",
            )
        postconditions = self.edit_postcondition_validator(plan.postconditions)
        if not postconditions.valid:
            rollback = self.rollback_manager(snapshot, fence_token=fence_token)
            return _transaction_receipt(
                plan,
                (
                    TransactionStatus.ROLLED_BACK
                    if rollback.status == "RESTORED"
                    else TransactionStatus.POSTCONDITION_FAILED
                ),
                before_revision,
                snapshot=snapshot,
                changed_paths=tuple(changed),
                rollback=rollback,
                reason="postcondition failed",
            )
        after_revision = _revision_digest(self, plan.read_set, plan.write_set)
        return _transaction_receipt(
            plan,
            TransactionStatus.COMMITTED,
            before_revision,
            snapshot=snapshot,
            changed_paths=tuple(changed),
            after_revision=after_revision,
        )

    def atomic_commit_planner(self, plan: PatchPlan) -> tuple[str, ...]:
        return self.dependency_aware_commit_ordering(
            tuple(item.path for item in plan.write_set), plan.dependencies
        )

    @staticmethod
    def dependency_aware_commit_ordering(
        paths: Sequence[str], dependencies: Mapping[str, tuple[str, ...]]
    ) -> tuple[str, ...]:
        return _topological_order(tuple(paths), dependencies)

    @staticmethod
    def semantic_merge_validator(base: bytes, left: bytes, right: bytes) -> MergeValidation:
        if left == right:
            merged, classification = left, "IDENTICAL_BRANCH_RESULTS"
        elif left == base:
            merged, classification = right, "RIGHT_ONLY_CHANGE"
        elif right == base:
            merged, classification = left, "LEFT_ONLY_CHANGE"
        else:
            merged, classification = None, "CONFLICTED"
        return MergeValidation(
            valid=merged is not None,
            merged=merged,
            classification=classification,
            base_digest=digest_bytes(base),
            left_digest=digest_bytes(left),
            right_digest=digest_bytes(right),
            merged_digest=digest_bytes(merged) if merged is not None else None,
        )

    @staticmethod
    def merge_proof_generator(validation: MergeValidation) -> Mapping[str, Any]:
        status = "LOCAL_INPUT_VALIDATED" if validation.valid else "CONFLICTED"
        payload = {
            "status": status,
            "classification": validation.classification,
            "base_digest": validation.base_digest,
            "left_digest": validation.left_digest,
            "right_digest": validation.right_digest,
            "merged_digest": validation.merged_digest,
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
        return MappingProxyType(
            {**payload, "proof_digest": digest_object(payload, domain="merge-proof")}
        )


def _rewrite(intent: RewriteIntent, *, require_mapping_rule: bool) -> RewriteResult:
    before = digest_bytes(intent.content)
    fragment = intent.content[intent.span_start : intent.span_end]
    if digest_bytes(fragment) != intent.expected_fragment_digest:
        return RewriteResult("STALE", None, before, None, "rewrite anchor is stale", intent.mapping_rule)
    if require_mapping_rule and not intent.mapping_rule:
        return RewriteResult(
            "INSUFFICIENT_EVIDENCE",
            None,
            before,
            None,
            "semantic/framework rewrite requires an exact mapping rule",
            None,
        )
    content = (
        intent.content[: intent.span_start]
        + intent.replacement
        + intent.content[intent.span_end :]
    )
    return RewriteResult("PLANNED", content, before, digest_bytes(content), mapping_rule=intent.mapping_rule)


def _revision_digest(
    manager: TransactionManager,
    read_set: Sequence[ContentAnchor],
    write_set: Sequence[WriteIntent],
) -> str:
    paths = sorted({item.path for item in read_set} | {item.path for item in write_set})
    anchors = tuple(manager.content_hash_anchor(path) for path in paths)
    return digest_object(
        tuple((item.path, item.exists, item.digest, item.size, item.mode) for item in anchors),
        domain="transaction-revision",
    )


def revision_digest(
    manager: TransactionManager,
    read_set: Sequence[ContentAnchor],
    write_set: Sequence[WriteIntent],
) -> str:
    """Public helper for binding a plan to the exact current read/write state."""

    return _revision_digest(manager, read_set, write_set)


def _transaction_receipt(
    plan: PatchPlan,
    status: TransactionStatus,
    before_revision: str,
    *,
    snapshot: SnapshotReceipt | None = None,
    changed_paths: tuple[str, ...] = (),
    stale_paths: tuple[str, ...] = (),
    rollback: RollbackReceipt | None = None,
    after_revision: str | None = None,
    reason: str | None = None,
) -> TransactionReceipt:
    payload = {
        "transaction_id": plan.transaction_id,
        "status": status.value,
        "snapshot_id": snapshot.snapshot_id if snapshot else None,
        "changed_paths": changed_paths,
        "stale_paths": stale_paths,
        "rollback_digest": rollback.evidence_digest if rollback else None,
        "before_revision": before_revision,
        "after_revision": after_revision,
        "reason": reason,
        "atomic_file_replacement": True,
        "multi_file_atomicity": "COMPENSATED_NOT_GLOBALLY_ATOMIC",
    }
    return TransactionReceipt(
        transaction_id=plan.transaction_id,
        status=status,
        snapshot_id=snapshot.snapshot_id if snapshot else None,
        changed_paths=changed_paths,
        stale_paths=stale_paths,
        rollback=rollback,
        before_revision=before_revision,
        after_revision=after_revision,
        evidence_digest=digest_object(payload, domain="transaction-receipt"),
        reason=reason,
    )


def _read_optional(root: str, path: str) -> tuple[bytes | None, int | None]:
    normalized = _validate_relative_path(path)
    parent_fd, leaf = _open_parent(root, normalized)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        try:
            file_fd = os.open(leaf, os.O_RDONLY | nofollow, dir_fd=parent_fd)
        except FileNotFoundError:
            return None, None
        try:
            metadata = os.fstat(file_fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("transaction target is not a regular file")
            if metadata.st_size > 64 * 1024 * 1024:
                raise ValueError("transaction target exceeds bounded read size")
            remaining = metadata.st_size
            chunks: list[bytes] = []
            while remaining:
                chunk = os.read(file_fd, min(remaining, 1024 * 1024))
                if not chunk:
                    raise OSError("transaction target changed while reading")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(file_fd, 1):
                raise OSError("transaction target grew while reading")
            return b"".join(chunks), stat.S_IMODE(metadata.st_mode)
        finally:
            os.close(file_fd)
    finally:
        os.close(parent_fd)


def _atomic_replace(root: str, path: str, content: bytes, mode: int) -> None:
    normalized = _validate_relative_path(path)
    parent_fd, leaf = _open_parent(root, normalized)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    temp_name = f".elmos-pdhi-{secrets.token_hex(16)}.tmp"
    temp_fd: int | None = None
    try:
        temp_fd = os.open(
            temp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
            mode,
            dir_fd=parent_fd,
        )
        offset = 0
        while offset < len(content):
            written = os.write(temp_fd, content[offset:])
            if written <= 0:
                raise OSError("atomic patch write made no progress")
            offset += written
        os.fchmod(temp_fd, mode)
        os.fsync(temp_fd)
        os.close(temp_fd)
        temp_fd = None
        os.rename(temp_name, leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        if temp_fd is not None:
            os.close(temp_fd)
        try:
            os.unlink(temp_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)


def _unlink_if_exists(root: str, path: str) -> None:
    normalized = _validate_relative_path(path)
    parent_fd, leaf = _open_parent(root, normalized)
    try:
        try:
            os.unlink(leaf, dir_fd=parent_fd)
        except FileNotFoundError:
            return
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _open_parent(root: str, path: str) -> tuple[int, str]:
    components = PurePosixPath(path).parts
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | nofollow)
    try:
        for component in components[:-1]:
            next_fd = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | nofollow,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        return directory_fd, components[-1]
    except Exception:
        os.close(directory_fd)
        raise


def _topological_order(
    paths: tuple[str, ...], dependencies: Mapping[str, tuple[str, ...]]
) -> tuple[str, ...]:
    normalized = tuple(_validate_relative_path(path) for path in paths)
    if len(set(normalized)) != len(normalized):
        raise ValueError("commit paths must be unique")
    nodes = set(normalized)
    incoming = {
        path: set(dependencies.get(path, ()))
        for path in normalized
    }
    if any(dependency not in nodes for values in incoming.values() for dependency in values):
        raise ValueError("commit dependency is outside the write set")
    ready = sorted(path for path, values in incoming.items() if not values)
    ordered: list[str] = []
    while ready:
        path = ready.pop(0)
        ordered.append(path)
        for candidate in sorted(nodes - set(ordered)):
            if path in incoming[candidate]:
                incoming[candidate].remove(path)
                if not incoming[candidate] and candidate not in ready:
                    ready.append(candidate)
                    ready.sort()
    if len(ordered) != len(nodes):
        raise ValueError("commit dependency graph contains a cycle")
    return tuple(ordered)


def _validate_relative_path(path: str) -> str:
    if not isinstance(path, str) or not path or "\x00" in path or "\\" in path:
        raise ValueError("transaction path must be a non-empty POSIX relative path")
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("transaction path traversal is forbidden")
    normalized = candidate.as_posix()
    if normalized != path:
        raise ValueError("transaction path must already be normalized")
    return normalized


K2_OPERATION_SPECS: Mapping[str, OperationSpec] = MappingProxyType(
    {
        "semantic-anchor": OperationSpec("semantic-anchor", "K2", "semantic_anchor", "SymbolAnchor"),
        "content-hash-anchor": OperationSpec("content-hash-anchor", "K2", "content_hash_anchor", "ContentAnchor"),
        "symbol-identity-anchor": OperationSpec("symbol-identity-anchor", "K2", "symbol_identity_anchor", "SymbolAnchor"),
        "stale-state-detector": OperationSpec("stale-state-detector", "K2", "stale_state_detector", "path[]"),
        "read-set-tracker": OperationSpec("read-set-tracker", "K2", "read_set_tracker", "ContentAnchor[]"),
        "write-set-tracker": OperationSpec("write-set-tracker", "K2", "write_set_tracker", "WriteIntent[]"),
        "patch-intent-contract": OperationSpec("patch-intent-contract", "K2", "patch_intent_contract", "PatchPlan"),
        "edit-precondition-validator": OperationSpec("edit-precondition-validator", "K2", "edit_precondition_validator", "ValidationResult"),
        "semantic-conflict-detector": OperationSpec("semantic-conflict-detector", "K2", "semantic_conflict_detector", "conflict[]"),
        "ast-structural-rewrite": OperationSpec("ast-structural-rewrite", "K2", "ast_structural_rewrite", "RewriteResult"),
        "semantic-ir-rewrite": OperationSpec("semantic-ir-rewrite", "K2", "semantic_ir_rewrite", "RewriteResult"),
        "framework-aware-rewrite": OperationSpec("framework-aware-rewrite", "K2", "framework_aware_rewrite", "RewriteResult"),
        "edit-postcondition-validator": OperationSpec("edit-postcondition-validator", "K2", "edit_postcondition_validator", "ValidationResult"),
        "transactional-patch": OperationSpec("transactional-patch", "K2", "transactional_patch", "TransactionReceipt"),
        "snapshot-manager": OperationSpec("snapshot-manager", "K2", "snapshot_manager", "SnapshotReceipt"),
        "rollback-manager": OperationSpec("rollback-manager", "K2", "rollback_manager", "RollbackReceipt"),
        "atomic-commit-planner": OperationSpec("atomic-commit-planner", "K2", "atomic_commit_planner", "path[]"),
        "dependency-aware-commit-ordering": OperationSpec("dependency-aware-commit-ordering", "K2", "dependency_aware_commit_ordering", "path[]"),
        "semantic-merge-validator": OperationSpec("semantic-merge-validator", "K2", "semantic_merge_validator", "MergeValidation"),
        "merge-proof-generator": OperationSpec("merge-proof-generator", "K2", "merge_proof_generator", "MergeProof"),
    }
)


if len(K2_OPERATION_SPECS) != 20:
    raise RuntimeError("K2 operation bindings drifted from the source catalog")


__all__ = [
    "ContentAddressedStore",
    "ContentAnchor",
    "K2_OPERATION_SPECS",
    "MergeValidation",
    "PatchPlan",
    "Postcondition",
    "RewriteIntent",
    "RewriteResult",
    "RollbackReceipt",
    "ScopeFence",
    "SnapshotEntry",
    "SnapshotReceipt",
    "SymbolAnchor",
    "TransactionManager",
    "TransactionReceipt",
    "TransactionStatus",
    "ValidationResult",
    "WriteIntent",
    "revision_digest",
]
