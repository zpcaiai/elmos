"""Content-addressed manifests: artifacts, file trees, action results, evidence.

Manifest identity is the digest of its canonical serialisation, so a manifest
cannot be edited in place -- an "update" is a new manifest with a new digest and
new reference edges. Every manifest is schema-validated *before* it is stored,
because a manifest that fails validation after storage is already reachable.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from . import schemas
from .canonical import (
    canonical_json_bytes,
    cas_uri,
    detect_path_collisions,
    digest_of,
    normalize_logical_path,
    require_digest,
    sha256_bytes,
)
from .cas import ContentAddressableStore
from .enums import Ownership, ValidationLevel
from .errors import ConflictError, ContractViolation

SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class Producer:
    stage_id: str
    stage_version: str
    action_key: str
    run_id: str | None = None
    node_id: str | None = None
    attempt: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {k: v for k, v in asdict(self).items() if v is not None}
        require_digest(self.action_key)
        return data


@dataclass(frozen=True)
class ArtifactManifest:
    """Describes one immutable byte sequence and where it came from."""

    artifact_id: str
    digest: str
    size: int
    media_type: str
    artifact_kind: str
    producer: Producer
    dependencies: tuple[str, ...] = ()
    logical_path: str | None = None
    schema_ref: str | None = None
    source_map_ref: str | None = None
    validation_level: ValidationLevel = ValidationLevel.UNVERIFIED
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": self.artifact_id,
            "digest": require_digest(self.digest),
            "size": self.size,
            "media_type": self.media_type,
            "artifact_kind": self.artifact_kind,
            "logical_path": self.logical_path,
            "schema_ref": self.schema_ref,
            "producer": self.producer.to_dict(),
            "dependencies": sorted(self.dependencies),
            "source_map_ref": self.source_map_ref,
            "validation_level": str(self.validation_level),
            "provenance": self.provenance,
        }

    def validate(self) -> None:
        schemas.validate("artifact-manifest", self.to_dict())

    def store(self, cas: ContentAddressableStore) -> str:
        self.validate()
        return cas.put_document(self.to_dict(), artifact_kind="artifact-manifest")


@dataclass(frozen=True)
class TreeEntry:
    logical_path: str
    artifact_digest: str
    mode: int = 0o644
    ownership: Ownership = Ownership.GENERATED
    size: int = 0
    source_map_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "logical_path": self.logical_path,
            "artifact_digest": require_digest(self.artifact_digest),
            "mode": self.mode,
            "ownership": str(self.ownership),
            "size": self.size,
            "source_map_ref": self.source_map_ref,
        }


@dataclass(frozen=True)
class FileTreeManifest:
    """The complete generated project. Publication operates on this, never files."""

    tree_id: str
    root_digest: str
    entries: tuple[TreeEntry, ...]
    producer: dict[str, Any]
    validation_level: ValidationLevel = ValidationLevel.UNVERIFIED
    evidence_bundle_ref: str | None = None
    previous_tree_ref: str | None = None

    @property
    def total_bytes(self) -> int:
        return sum(entry.size for entry in self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "tree_id": self.tree_id,
            "root_digest": self.root_digest,
            "entries": [entry.to_dict() for entry in self.entries],
            "producer": self.producer,
            "validation_level": str(self.validation_level),
            "evidence_bundle_ref": self.evidence_bundle_ref,
            "previous_tree_ref": self.previous_tree_ref,
        }

    def validate(self) -> None:
        schemas.validate("file-tree-manifest", self.to_dict())

    def store(self, cas: ContentAddressableStore) -> str:
        self.validate()
        return cas.put_document(self.to_dict(), artifact_kind="file-tree-manifest")

    def paths(self) -> tuple[str, ...]:
        return tuple(entry.logical_path for entry in self.entries)


def compute_tree_digest(entries: Sequence[TreeEntry]) -> str:
    """Digest of the sorted (path, digest, mode, ownership) tuples.

    Deliberately excludes sizes and source maps so an identical byte tree with
    a regenerated source map keeps its identity.
    """
    payload = [
        {
            "logical_path": entry.logical_path,
            "artifact_digest": entry.artifact_digest,
            "mode": entry.mode,
            "ownership": str(entry.ownership),
        }
        for entry in sorted(entries, key=lambda item: item.logical_path)
    ]
    return sha256_bytes(canonical_json_bytes({"kind": "file-tree", "entries": payload}))


def build_file_tree(
    entries: Iterable[TreeEntry],
    producer: dict[str, Any],
    validation_level: ValidationLevel = ValidationLevel.UNVERIFIED,
    evidence_bundle_ref: str | None = None,
    previous_tree_ref: str | None = None,
) -> FileTreeManifest:
    """Normalise, reject unsafe/conflicting paths, then seal the tree identity."""
    normalized: list[TreeEntry] = []
    for entry in entries:
        path = normalize_logical_path(entry.logical_path)
        require_digest(entry.artifact_digest)
        normalized.append(
            TreeEntry(
                logical_path=path,
                artifact_digest=entry.artifact_digest,
                mode=entry.mode,
                ownership=entry.ownership,
                size=entry.size,
                source_map_ref=entry.source_map_ref,
            )
        )
    collisions = detect_path_collisions(entry.logical_path for entry in normalized)
    if collisions:
        raise ConflictError(
            "file tree contains conflicting logical paths",
            collisions=[list(item) for item in collisions],
        )
    normalized.sort(key=lambda item: item.logical_path)
    root_digest = compute_tree_digest(normalized)
    return FileTreeManifest(
        tree_id=f"tree_{root_digest.split(':', 1)[1][:24]}",
        root_digest=root_digest,
        entries=tuple(normalized),
        producer=producer,
        validation_level=validation_level,
        evidence_bundle_ref=evidence_bundle_ref,
        previous_tree_ref=previous_tree_ref,
    )


@dataclass(frozen=True)
class ExecutionMetrics:
    """What a cache hit actually saved. Drives hit-rate and savings reporting."""

    wall_ms: int = 0
    cpu_ms: int = 0
    peak_memory_bytes: int = 0
    network_bytes: int = 0
    compiler_ms: int = 0
    model_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionResultManifest:
    """Immutable description of one stage execution's outputs."""

    action_key: str
    stage_id: str
    stage_version: str
    output_artifacts: tuple[str, ...]
    #: Where each output belongs in the generated tree. Without this a cache
    #: hit could restore the right bytes to nowhere in particular.
    outputs: tuple[dict[str, Any], ...] = ()
    required_outputs: tuple[str, ...] = ()
    optional_outputs: tuple[str, ...] = ()
    tree_ref: str | None = None
    exit_status: str = "SUCCESS"
    failure_code: str | None = None
    metrics: ExecutionMetrics = field(default_factory=ExecutionMetrics)
    evidence_refs: tuple[str, ...] = ()
    fingerprint_document_ref: str | None = None
    determinism: str = "DETERMINISTIC"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "elmos.action-result/v1",
            "action_key": require_digest(self.action_key),
            "stage_id": self.stage_id,
            "stage_version": self.stage_version,
            "output_artifacts": sorted(self.output_artifacts),
            "outputs": sorted(self.outputs, key=lambda item: str(item.get("logical_path", ""))),
            "required_outputs": sorted(self.required_outputs),
            "optional_outputs": sorted(self.optional_outputs),
            "tree_ref": self.tree_ref,
            "exit_status": self.exit_status,
            "failure_code": self.failure_code,
            "metrics": self.metrics.to_dict(),
            "evidence_refs": sorted(self.evidence_refs),
            "fingerprint_document_ref": self.fingerprint_document_ref,
            "determinism": self.determinism,
        }

    def digest(self) -> str:
        return digest_of(self.to_dict())

    def store(self, cas: ContentAddressableStore) -> str:
        missing = sorted(set(self.required_outputs) - set(self.output_artifacts))
        if missing:
            raise ContractViolation("action result omits declared required outputs", missing=missing)
        return cas.put_document(self.to_dict(), artifact_kind="action-result")


@dataclass(frozen=True)
class CheckpointManifest:
    checkpoint_id: str
    run_id: str
    node_id: str
    attempt: int
    sequence: int
    lease_epoch: int
    source_snapshot: str
    action_key: str
    artifacts: tuple[str, ...]
    journal_sequence: int
    staged_files: tuple[str, ...] = ()
    completed_partitions: tuple[str, ...] = ()
    side_effect_receipts: tuple[dict[str, Any], ...] = ()
    resume_cursor: Any = None
    dependencies: tuple[str, ...] = ()
    compatibility: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "checkpoint_id": self.checkpoint_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "attempt": self.attempt,
            "sequence": self.sequence,
            "lease_epoch": self.lease_epoch,
            "source_snapshot": self.source_snapshot,
            "action_key": require_digest(self.action_key),
            "artifacts": sorted(self.artifacts),
            "staged_files": sorted(self.staged_files),
            "completed_partitions": sorted(self.completed_partitions),
            "side_effect_receipts": list(self.side_effect_receipts),
            "journal_sequence": self.journal_sequence,
            "resume_cursor": self.resume_cursor,
            "dependencies": sorted(self.dependencies),
            "compatibility": self.compatibility,
        }

    def validate(self) -> None:
        schemas.validate("checkpoint-manifest", self.to_dict())

    def store(self, cas: ContentAddressableStore) -> str:
        self.validate()
        return cas.put_document(self.to_dict(), artifact_kind="checkpoint-manifest")


@dataclass(frozen=True)
class EvidenceBundle:
    """Compile/test/behaviour/security evidence bound to one exact tree digest."""

    tree_digest: str
    validation_level: ValidationLevel
    records: tuple[dict[str, Any], ...]
    produced_by: str
    verifier_identities: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "elmos.evidence-bundle/v1",
            "tree_digest": self.tree_digest,
            "validation_level": str(self.validation_level),
            "records": list(self.records),
            "produced_by": self.produced_by,
            "verifier_identities": sorted(self.verifier_identities),
        }

    def digest(self) -> str:
        return digest_of(self.to_dict())

    def store(self, cas: ContentAddressableStore) -> str:
        return cas.put_document(self.to_dict(), artifact_kind="evidence-bundle")


@dataclass(frozen=True)
class SourceMap:
    """Generated path/symbol back to the originating source AST or IR node."""

    generated_path: str
    entries: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "elmos.source-map/v1",
            "generated_path": self.generated_path,
            "entries": list(self.entries),
        }

    def store(self, cas: ContentAddressableStore) -> str:
        return cas.put_document(self.to_dict(), artifact_kind="source-map")


def artifact_reference(digest: str) -> str:
    return cas_uri(digest)
