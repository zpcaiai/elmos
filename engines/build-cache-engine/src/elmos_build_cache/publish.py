"""Complete-tree assembly and atomic publication.

ELMOS never drips generated files into a live output folder. It materialises a
whole versioned tree under ``publish/<run_id>/<tree-digest>/``, verifies every
digest, checks the evidence bundle is bound to *that exact* tree digest, and
only then flips a pointer. A reader therefore observes either the previous
complete tree or the new complete tree -- never a mixture.

The previous tree is retained so rollback is a pointer flip, not a rebuild.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic import atomic_write_bytes
from .canonical import canonical_json_bytes, detect_path_collisions, fsync_directory, resolve_within
from .cas import ContentAddressableStore
from .clock import SYSTEM_CLOCK, Clock
from .db import MetadataStore
from .db.records import StagedFileRecord
from .enums import Ownership, StagedFileStatus, ValidationLevel
from .errors import ConflictError, ContractViolation, NotFound, SecretDetected, ValidationTooLow
from .manifests import EvidenceBundle, FileTreeManifest, TreeEntry, build_file_tree

POINTER_NAME = "current"
MANIFEST_NAME = ".elmos-tree-manifest.json"


@dataclass(frozen=True)
class PublishCandidate:
    tree: FileTreeManifest
    manifest_digest: str
    directory: Path


@dataclass(frozen=True)
class PublishResult:
    tree_digest: str
    directory: Path
    pointer: Path
    previous_tree_digest: str | None
    retained: tuple[str, ...]


class TreePublisher:
    def __init__(
        self,
        publish_root: Path,
        cas: ContentAddressableStore,
        store: MetadataStore,
        tenant_id: str,
        run_id: str,
        keep_previous: int = 2,
        clock: Clock = SYSTEM_CLOCK,
        secret_scanner: Any | None = None,
    ) -> None:
        self.publish_root = Path(publish_root) / run_id
        self.cas = cas
        self.store = store
        self.tenant_id = tenant_id
        self.run_id = run_id
        self.keep_previous = max(1, keep_previous)
        self.clock = clock
        self.secret_scanner = secret_scanner
        self.publish_root.mkdir(parents=True, exist_ok=True)

    # -- assembly ---------------------------------------------------------
    def build_tree_manifest(
        self,
        records: Sequence[StagedFileRecord],
        stage_id: str = "target-tree-assembly",
        validation_level: ValidationLevel = ValidationLevel.UNVERIFIED,
        evidence_bundle_ref: str | None = None,
        previous_tree_ref: str | None = None,
        extra_entries: Sequence[TreeEntry] = (),
    ) -> FileTreeManifest:
        """Turn sealed staged files into a candidate tree, refusing bad shapes."""
        entries: list[TreeEntry] = []
        for record in records:
            if record.status not in (StagedFileStatus.CAS_PROMOTED, StagedFileStatus.TREE_INCLUDED):
                raise ContractViolation(
                    "only CAS-promoted files may enter a tree manifest",
                    logical_path=record.logical_path,
                    status=str(record.status),
                )
            if record.artifact_digest is None:
                raise ContractViolation(
                    "staged file has no CAS artifact", logical_path=record.logical_path
                )
            entries.append(
                TreeEntry(
                    logical_path=record.logical_path,
                    artifact_digest=record.artifact_digest,
                    mode=record.mode,
                    ownership=record.ownership,
                    size=record.actual_size or 0,
                    source_map_ref=record.source_map_digest,
                )
            )
        entries.extend(extra_entries)
        return build_file_tree(
            entries,
            producer={"run_id": self.run_id, "stage_id": stage_id, "tenant_id": self.tenant_id},
            validation_level=validation_level,
            evidence_bundle_ref=evidence_bundle_ref,
            previous_tree_ref=previous_tree_ref,
        )

    def verify_tree(self, tree: FileTreeManifest) -> None:
        """Every referenced artifact must be present, uncorrupted and safe."""
        collisions = detect_path_collisions(tree.paths())
        if collisions:
            raise ConflictError("tree manifest has conflicting paths", collisions=[list(c) for c in collisions])
        missing: list[str] = []
        corrupt: list[str] = []
        for entry in tree.entries:
            if self.cas.is_quarantined(entry.artifact_digest):
                corrupt.append(entry.logical_path)
            elif not self.cas.contains(entry.artifact_digest):
                missing.append(entry.logical_path)
        if missing:
            raise NotFound("tree references artifacts that are not present", paths=missing[:20])
        if corrupt:
            raise ConflictError("tree references quarantined artifacts", paths=corrupt[:20])

    def check_evidence(self, tree: FileTreeManifest, evidence: EvidenceBundle | None) -> None:
        """Evidence must bind to *this* tree digest and be independently produced."""
        if tree.validation_level is ValidationLevel.UNVERIFIED:
            return
        if evidence is None:
            raise ValidationTooLow(
                "publication above UNVERIFIED requires an evidence bundle",
                validation_level=str(tree.validation_level),
            )
        if evidence.tree_digest != tree.root_digest:
            raise ConflictError(
                "evidence bundle is bound to a different tree digest",
                evidence_tree=evidence.tree_digest,
                candidate_tree=tree.root_digest,
            )
        if not evidence.validation_level.satisfies(tree.validation_level):
            raise ValidationTooLow(
                "evidence validation level is below the declared tree level",
                evidence=str(evidence.validation_level),
                tree=str(tree.validation_level),
            )
        if tree.validation_level.rank >= ValidationLevel.TEST_VERIFIED.rank and not evidence.verifier_identities:
            raise ValidationTooLow(
                "TEST_VERIFIED and above require at least one independent verifier identity"
            )

    # -- materialisation --------------------------------------------------
    def materialize(self, tree: FileTreeManifest) -> PublishCandidate:
        """Build the complete directory out of band, then rename it into place."""
        self.verify_tree(tree)
        short = tree.root_digest.split(":", 1)[1]
        final = self.publish_root / short
        manifest_digest = tree.store(self.cas)
        if final.exists():
            return PublishCandidate(tree, manifest_digest, final)

        staging = self.publish_root / f".{short}.elmos-tree-{os.getpid()}-{os.urandom(4).hex()}"
        if staging.exists():  # pragma: no cover - nonce collision
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        try:
            for entry in tree.entries:
                destination = resolve_within(staging, entry.logical_path)
                self.cas.materialize(entry.artifact_digest, destination, mode=entry.mode, verify=True)
            atomic_write_bytes(staging / MANIFEST_NAME, canonical_json_bytes(tree.to_dict()) + b"\n")
            if self.secret_scanner is not None:
                findings = self.secret_scanner.scan_tree(staging)
                if findings:
                    raise SecretDetected(
                        "secret material detected in the publish candidate",
                        paths=sorted({finding.path for finding in findings})[:20],
                    )
            fsync_directory(staging)
            os.replace(staging, final)
            fsync_directory(self.publish_root)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

        self.store.record_tree(
            self.tenant_id,
            tree.root_digest,
            self.run_id,
            manifest_digest,
            entry_count=len(tree.entries),
            total_bytes=tree.total_bytes,
            validation_level=tree.validation_level,
            evidence_digest=tree.evidence_bundle_ref,
            previous_tree=tree.previous_tree_ref,
        )
        self._register(manifest_digest, "application/json", "file-tree-manifest", tree.validation_level)
        self.store.add_artifact_ref(
            self.tenant_id, "file_tree", tree.root_digest, manifest_digest, "manifest"
        )
        for entry in tree.entries:
            self.store.add_artifact_ref(
                self.tenant_id, "file_tree", tree.root_digest, entry.artifact_digest, "entry"
            )
        return PublishCandidate(tree, manifest_digest, final)

    def _register(
        self, digest: str, media_type: str, artifact_kind: str, validation_level: ValidationLevel
    ) -> None:
        if self.store.get_artifact(self.tenant_id, digest) is not None:
            return
        self.store.register_artifact(
            self.tenant_id,
            digest,
            size_bytes=self.cas.info(digest).size,
            media_type=media_type,
            artifact_kind=artifact_kind,
            validation_level=validation_level,
        )

    # -- pointer ----------------------------------------------------------
    def current_tree_digest(self) -> str | None:
        pointer = self.publish_root / POINTER_NAME
        if not pointer.exists():
            return None
        if pointer.is_symlink():
            return "sha256:" + os.readlink(pointer).strip("/")
        return "sha256:" + pointer.read_text(encoding="utf-8").strip()

    def publish(self, candidate: PublishCandidate, evidence: EvidenceBundle | None = None) -> PublishResult:
        """Flip the pointer atomically. This is the only visibility change."""
        self.check_evidence(candidate.tree, evidence)
        if not candidate.directory.exists():
            raise NotFound("publish candidate directory is missing", directory=str(candidate.directory))

        previous = self.current_tree_digest()
        short = candidate.tree.root_digest.split(":", 1)[1]
        pointer = self.publish_root / POINTER_NAME
        temporary = self.publish_root / f".{POINTER_NAME}-{os.getpid()}-{os.urandom(4).hex()}"
        temporary.unlink(missing_ok=True)
        try:
            temporary.symlink_to(short, target_is_directory=True)
            os.replace(temporary, pointer)
        except (OSError, NotImplementedError):
            # Portable fallback: an atomically replaced pointer file.
            atomic_write_bytes(temporary, (short + "\n").encode("utf-8"))
            os.replace(temporary, pointer)
        finally:
            temporary.unlink(missing_ok=True)
        fsync_directory(self.publish_root)

        self.store.mark_tree_published(self.tenant_id, candidate.tree.root_digest)
        self.store.set_run_published_tree(
            self.run_id, candidate.tree.root_digest, evidence.digest() if evidence else None
        )
        for record in self.store.list_staged_files(self.run_id, [StagedFileStatus.CAS_PROMOTED]):
            if record.logical_path in candidate.tree.paths():
                included = self.store.update_staged_file(
                    record, StagedFileStatus.TREE_INCLUDED, record.version
                )
                self.store.update_staged_file(included, StagedFileStatus.PUBLISHED, included.version)

        retained = self._retain()
        return PublishResult(
            tree_digest=candidate.tree.root_digest,
            directory=candidate.directory,
            pointer=pointer,
            previous_tree_digest=previous,
            retained=retained,
        )

    def rollback(self, tree_digest: str) -> PublishResult:
        """Return to a retained complete tree. Same pointer flip, opposite direction."""
        short = tree_digest.split(":", 1)[1]
        directory = self.publish_root / short
        if not directory.is_dir():
            raise NotFound("cannot roll back to a tree that is no longer retained", tree_digest=tree_digest)
        manifest_path = directory / MANIFEST_NAME
        if not manifest_path.is_file():
            raise ConflictError("retained tree has no manifest", tree_digest=tree_digest)
        candidate = PublishCandidate(
            tree=_load_manifest(manifest_path), manifest_digest="", directory=directory
        )
        previous = self.current_tree_digest()
        # A retained tree was already validated when it was first published;
        # rollback re-points at it rather than re-proving it.
        result = self._flip(candidate)
        return PublishResult(
            tree_digest=tree_digest,
            directory=directory,
            pointer=result.pointer,
            previous_tree_digest=previous,
            retained=result.retained,
        )

    def _flip(self, candidate: PublishCandidate) -> PublishResult:
        short = candidate.tree.root_digest.split(":", 1)[1]
        pointer = self.publish_root / POINTER_NAME
        temporary = self.publish_root / f".{POINTER_NAME}-{os.getpid()}-{os.urandom(4).hex()}"
        previous = self.current_tree_digest()
        temporary.unlink(missing_ok=True)
        try:
            temporary.symlink_to(short, target_is_directory=True)
            os.replace(temporary, pointer)
        except (OSError, NotImplementedError):
            atomic_write_bytes(temporary, (short + "\n").encode("utf-8"))
            os.replace(temporary, pointer)
        finally:
            temporary.unlink(missing_ok=True)
        fsync_directory(self.publish_root)
        self.store.mark_tree_published(self.tenant_id, candidate.tree.root_digest)
        return PublishResult(
            tree_digest=candidate.tree.root_digest,
            directory=candidate.directory,
            pointer=pointer,
            previous_tree_digest=previous,
            retained=self._retain(),
        )

    def _tree_directories(self) -> list[Path]:
        """Real tree directories only -- never the ``current`` pointer itself."""
        return [
            path
            for path in self.publish_root.iterdir()
            if path.is_dir()
            and not path.is_symlink()
            and path.name != POINTER_NAME
            and not path.name.startswith(".")
        ]

    def _retain(self) -> tuple[str, ...]:
        """Keep the active tree plus ``keep_previous`` older complete trees."""
        active = self.current_tree_digest()
        ordered = sorted(self._tree_directories(), key=lambda path: path.stat().st_mtime, reverse=True)
        keep: list[str] = []
        others = 0
        for path in ordered:
            digest = "sha256:" + path.name
            if digest == active:
                keep.append(digest)
            elif others < self.keep_previous:
                others += 1
                keep.append(digest)
        for path in ordered:
            if "sha256:" + path.name not in keep:
                shutil.rmtree(path, ignore_errors=True)
        return tuple(keep)

    def list_trees(self) -> tuple[str, ...]:
        return tuple(sorted("sha256:" + path.name for path in self._tree_directories()))

    def read_published(self, logical_path: str) -> bytes:
        """Read through the pointer, the way a consumer would."""
        digest = self.current_tree_digest()
        if digest is None:
            raise NotFound("nothing is published yet", run_id=self.run_id)
        directory = self.publish_root / digest.split(":", 1)[1]
        return resolve_within(directory, logical_path).read_bytes()


def _load_manifest(path: Path) -> FileTreeManifest:
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    entries = tuple(
        TreeEntry(
            logical_path=item["logical_path"],
            artifact_digest=item["artifact_digest"],
            mode=int(item.get("mode", 0o644)),
            ownership=Ownership(item.get("ownership", "GENERATED")),
            size=int(item.get("size", 0)),
            source_map_ref=item.get("source_map_ref"),
        )
        for item in data["entries"]
    )
    return FileTreeManifest(
        tree_id=data["tree_id"],
        root_digest=data["root_digest"],
        entries=entries,
        producer=data.get("producer", {}),
        validation_level=ValidationLevel(data.get("validation_level", "UNVERIFIED")),
        evidence_bundle_ref=data.get("evidence_bundle_ref"),
        previous_tree_ref=data.get("previous_tree_ref"),
    )
