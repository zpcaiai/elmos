"""Checkpoint commit and resume.

A checkpoint is only allowed to reference *sealed*, digest-verified artifacts
and committed state. That single rule is what makes resume safe: there is no
way for a half-written file to be resumed as if it were complete.

Commit order is deliberate:

1. flush staged files (seal + promote) so every referenced artifact is durable;
2. record side-effect receipts so a retry cannot duplicate an external effect;
3. store the manifest in CAS (content-addressed, so re-commit is idempotent);
4. attach the manifest to the node atomically, under the current lease epoch.

If the process dies between 3 and 4 the manifest is an unreferenced CAS object,
which the GC will collect -- never a node pointing at nothing.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .cas import ContentAddressableStore
from .clock import SYSTEM_CLOCK, Clock
from .db import MetadataStore
from .db.records import CheckpointRecord, StagedFileRecord
from .db.store import new_id
from .enums import CheckpointStatus, StagedFileStatus
from .errors import ConflictError, ContractViolation, NotFound, StaleLease
from .journal import Lease, RunJournal
from .manifests import CheckpointManifest
from .staging import Workspace

SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class CompatibilityProfile:
    """Everything resume must re-prove before trusting a checkpoint."""

    stage_id: str
    stage_version: str
    stage_contract_digest: str
    rule_pack_digest: str | None = None
    toolchain_digest: str | None = None
    source_snapshot: str = ""
    action_key: str = ""
    pipeline_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "stage_version": self.stage_version,
            "stage_contract_digest": self.stage_contract_digest,
            "rule_pack_digest": self.rule_pack_digest,
            "toolchain_digest": self.toolchain_digest,
            "source_snapshot": self.source_snapshot,
            "action_key": self.action_key,
            "pipeline_version": self.pipeline_version,
        }

    def incompatibilities(self, other: CompatibilityProfile) -> list[str]:
        reasons: list[str] = []
        for name in (
            "stage_id",
            "stage_version",
            "stage_contract_digest",
            "rule_pack_digest",
            "toolchain_digest",
            "source_snapshot",
            "action_key",
            "pipeline_version",
        ):
            mine = getattr(self, name)
            theirs = getattr(other, name)
            if mine != theirs:
                reasons.append(f"{name} changed: {mine!r} -> {theirs!r}")
        return reasons


@dataclass(frozen=True)
class ResumeDecision:
    resumable: bool
    checkpoint: CheckpointRecord | None
    manifest: CheckpointManifest | None
    reasons: tuple[str, ...]
    completed_partitions: tuple[str, ...] = ()
    resume_cursor: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resumable": self.resumable,
            "checkpoint_id": self.checkpoint.checkpoint_id if self.checkpoint else None,
            "reasons": list(self.reasons),
            "completed_partitions": list(self.completed_partitions),
            "resume_cursor": self.resume_cursor,
        }


@dataclass
class CheckpointPolicy:
    """When to checkpoint. Cheap stages should not pay for durability."""

    stage_boundary: bool = True
    interval_seconds: float = 30.0
    max_chain_length: int = 100
    min_recompute_cost_ms: int = 5_000
    partitionable: bool = True
    verify_all_digests_on_resume: bool = True
    _last_checkpoint_at: float = field(default=0.0, repr=False)

    def should_checkpoint(
        self,
        now: float,
        at_stage_boundary: bool,
        estimated_recompute_ms: int,
        pending_artifact_bytes: int = 0,
    ) -> tuple[bool, str]:
        if at_stage_boundary and self.stage_boundary:
            return True, "stage boundary"
        if estimated_recompute_ms < self.min_recompute_cost_ms and pending_artifact_bytes < 1_000_000:
            return False, "recomputation is cheaper than checkpointing"
        if not self.partitionable:
            return False, "stage is not partitionable, so a mid-stage checkpoint cannot resume"
        if now - self._last_checkpoint_at >= self.interval_seconds:
            return True, f"interval of {self.interval_seconds}s elapsed"
        return False, "interval has not elapsed"

    def mark(self, now: float) -> None:
        self._last_checkpoint_at = now


class CheckpointService:
    def __init__(
        self,
        store: MetadataStore,
        cas: ContentAddressableStore,
        workspace: Workspace,
        journal: RunJournal,
        clock: Clock = SYSTEM_CLOCK,
        policy: CheckpointPolicy | None = None,
    ) -> None:
        self.store = store
        self.cas = cas
        self.workspace = workspace
        self.journal = journal
        self.clock = clock
        self.policy = policy or CheckpointPolicy()

    # -- commit -----------------------------------------------------------
    def commit(
        self,
        lease: Lease,
        profile: CompatibilityProfile,
        completed_partitions: Sequence[str] = (),
        resume_cursor: Any = None,
        dependency_checkpoints: Sequence[str] = (),
        extra_artifacts: Sequence[str] = (),
    ) -> tuple[CheckpointRecord, CheckpointManifest]:
        """Flush, then commit. Refuses if anything is still unsealed."""
        node = self.store.assert_lease(lease.run_id, lease.node_id, lease.attempt, lease.epoch)
        if node.lease_id != lease.lease_id:
            raise StaleLease("another worker owns this node", node_id=lease.node_id)

        staged = [
            record
            for record in self.store.list_staged_files(lease.run_id)
            if record.node_id == lease.node_id and record.attempt == lease.attempt
        ]
        unsealed = [
            record.logical_path
            for record in staged
            if record.status in (StagedFileStatus.RESERVED, StagedFileStatus.WRITING)
        ]
        if unsealed:
            raise ContractViolation(
                "unsealed staged files cannot enter a checkpoint", paths=sorted(unsealed)[:20]
            )

        promoted: list[StagedFileRecord] = []
        for record in staged:
            if record.status is StagedFileStatus.SEALED:
                record = self.workspace.promote(record)
            if record.status in (
                StagedFileStatus.CAS_PROMOTED,
                StagedFileStatus.TREE_INCLUDED,
                StagedFileStatus.PUBLISHED,
            ):
                promoted.append(record)

        artifacts = sorted(
            {record.artifact_digest for record in promoted if record.artifact_digest}
            | set(extra_artifacts)
        )
        missing = [digest for digest in artifacts if not self.cas.contains(digest)]
        if missing:
            raise ContractViolation("checkpoint references artifacts that are not durable", missing=missing)

        chain = [
            checkpoint
            for checkpoint in self.store.list_checkpoints(lease.run_id, lease.node_id)
            if checkpoint.attempt == lease.attempt
        ]
        if len(chain) >= self.policy.max_chain_length:
            raise ConflictError(
                "checkpoint chain is at its maximum length",
                node_id=lease.node_id,
                length=len(chain),
            )
        sequence = (max((checkpoint.sequence for checkpoint in chain), default=0)) + 1

        receipts = [
            receipt
            for receipt in self.store.list_side_effects(lease.run_id)
            if receipt["node_id"] == lease.node_id
        ]

        checkpoint_id = new_id("cp")
        manifest = CheckpointManifest(
            checkpoint_id=checkpoint_id,
            run_id=lease.run_id,
            node_id=lease.node_id,
            attempt=lease.attempt,
            sequence=sequence,
            lease_epoch=lease.epoch,
            source_snapshot=profile.source_snapshot,
            action_key=profile.action_key,
            artifacts=tuple(artifacts),
            journal_sequence=self.journal.sequence,
            staged_files=tuple(sorted(record.staged_file_id for record in promoted)),
            completed_partitions=tuple(sorted(completed_partitions)),
            side_effect_receipts=tuple(receipts),
            resume_cursor=resume_cursor,
            dependencies=tuple(sorted(dependency_checkpoints)),
            compatibility=profile.to_dict(),
        )
        manifest_digest = manifest.store(self.cas)

        # Re-check the epoch immediately before attaching: recovery may have
        # reassigned the node while the manifest was being written.
        self.store.assert_lease(lease.run_id, lease.node_id, lease.attempt, lease.epoch)

        checkpoint_record = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            tenant_id=self.workspace.tenant_id,
            project_id=self.workspace.project_id,
            run_id=lease.run_id,
            node_id=lease.node_id,
            attempt=lease.attempt,
            sequence=sequence,
            lease_epoch=lease.epoch,
            manifest_digest=manifest_digest,
            journal_sequence=manifest.journal_sequence,
            status=CheckpointStatus.ACTIVE,
        )
        self.store.insert_checkpoint(checkpoint_record)
        self.store.register_artifact(
            self.workspace.tenant_id,
            manifest_digest,
            size_bytes=self.cas.info(manifest_digest).size,
            media_type="application/json",
            artifact_kind="checkpoint-manifest",
        )
        self.store.add_artifact_ref(
            self.workspace.tenant_id, "checkpoint", checkpoint_id, manifest_digest, "manifest"
        )
        for digest in artifacts:
            self.store.add_artifact_ref(
                self.workspace.tenant_id, "checkpoint", checkpoint_id, digest, "artifact"
            )
        self.policy.mark(self.clock.now())
        self.journal.append(
            "CHECKPOINT_COMMITTED",
            "checkpoint-service",
            {"checkpoint_id": checkpoint_id, "manifest_digest": manifest_digest, "sequence": sequence},
            node_id=lease.node_id,
            attempt=lease.attempt,
            lease_epoch=lease.epoch,
        )
        return checkpoint_record, manifest

    # -- resume -----------------------------------------------------------
    def latest(self, run_id: str, node_id: str, attempt: int | None = None) -> CheckpointRecord | None:
        candidates = [
            checkpoint
            for checkpoint in self.store.list_checkpoints(run_id, node_id)
            if checkpoint.status is CheckpointStatus.ACTIVE
            and (attempt is None or checkpoint.attempt == attempt)
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda c: (c.attempt, c.sequence))[-1]

    def load(self, checkpoint: CheckpointRecord) -> CheckpointManifest:
        document = self.cas.get_document(checkpoint.manifest_digest)
        if not isinstance(document, dict):
            raise ConflictError("checkpoint manifest is malformed", checkpoint_id=checkpoint.checkpoint_id)
        return CheckpointManifest(
            checkpoint_id=document["checkpoint_id"],
            run_id=document["run_id"],
            node_id=document["node_id"],
            attempt=int(document["attempt"]),
            sequence=int(document["sequence"]),
            lease_epoch=int(document.get("lease_epoch", 0)),
            source_snapshot=document["source_snapshot"],
            action_key=document["action_key"],
            artifacts=tuple(document.get("artifacts", ())),
            journal_sequence=int(document["journal_sequence"]),
            staged_files=tuple(document.get("staged_files", ())),
            completed_partitions=tuple(document.get("completed_partitions", ())),
            side_effect_receipts=tuple(document.get("side_effect_receipts", ())),
            resume_cursor=document.get("resume_cursor"),
            dependencies=tuple(document.get("dependencies", ())),
            compatibility=document.get("compatibility", {}),
        )

    def evaluate(
        self,
        run_id: str,
        node_id: str,
        expected: CompatibilityProfile,
        attempt: int | None = None,
    ) -> ResumeDecision:
        """Pick the newest compatible checkpoint, or explain why none qualifies."""
        candidates = sorted(
            (
                checkpoint
                for checkpoint in self.store.list_checkpoints(run_id, node_id)
                if checkpoint.status is CheckpointStatus.ACTIVE
                and (attempt is None or checkpoint.attempt == attempt)
            ),
            key=lambda c: (c.attempt, c.sequence),
            reverse=True,
        )
        if not candidates:
            return ResumeDecision(False, None, None, ("no active checkpoint for this node",))

        collected: list[str] = []
        for checkpoint in candidates:
            try:
                manifest = self.load(checkpoint)
            except Exception as exc:  # noqa: BLE001 - normalised into a reason
                collected.append(f"{checkpoint.checkpoint_id}: manifest unreadable ({exc})")
                self.store.set_checkpoint_status(checkpoint.checkpoint_id, CheckpointStatus.INVALID)
                continue

            recorded = CompatibilityProfile(
                stage_id=manifest.compatibility.get("stage_id", ""),
                stage_version=manifest.compatibility.get("stage_version", ""),
                stage_contract_digest=manifest.compatibility.get("stage_contract_digest", ""),
                rule_pack_digest=manifest.compatibility.get("rule_pack_digest"),
                toolchain_digest=manifest.compatibility.get("toolchain_digest"),
                source_snapshot=manifest.compatibility.get("source_snapshot", ""),
                action_key=manifest.compatibility.get("action_key", ""),
                pipeline_version=manifest.compatibility.get("pipeline_version", ""),
            )
            reasons = recorded.incompatibilities(expected)
            if reasons:
                collected.extend(f"{checkpoint.checkpoint_id}: {reason}" for reason in reasons)
                continue

            missing = [digest for digest in manifest.artifacts if not self.cas.contains(digest)]
            if missing:
                collected.append(
                    f"{checkpoint.checkpoint_id}: {len(missing)} referenced artifacts are missing"
                )
                self.store.set_checkpoint_status(checkpoint.checkpoint_id, CheckpointStatus.INVALID)
                continue
            if self.policy.verify_all_digests_on_resume:
                corrupt = [digest for digest in manifest.artifacts if not self.cas.verify(digest)]
                if corrupt:
                    collected.append(f"{checkpoint.checkpoint_id}: {len(corrupt)} artifacts are corrupt")
                    self.store.set_checkpoint_status(checkpoint.checkpoint_id, CheckpointStatus.QUARANTINED)
                    continue

            broken = self._broken_dependencies(manifest)
            if broken:
                collected.append(f"{checkpoint.checkpoint_id}: dependency checkpoints invalid: {broken}")
                continue

            journal_end = self.journal.sequence
            if manifest.journal_sequence > journal_end:
                collected.append(
                    f"{checkpoint.checkpoint_id}: journal boundary {manifest.journal_sequence}"
                    f" is ahead of the journal ({journal_end})"
                )
                self.store.set_checkpoint_status(checkpoint.checkpoint_id, CheckpointStatus.INVALID)
                continue

            return ResumeDecision(
                True,
                checkpoint,
                manifest,
                ("newest compatible checkpoint",),
                completed_partitions=manifest.completed_partitions,
                resume_cursor=manifest.resume_cursor,
            )

        return ResumeDecision(False, None, None, tuple(collected))

    def _broken_dependencies(self, manifest: CheckpointManifest) -> list[str]:
        broken: list[str] = []
        for digest in manifest.dependencies:
            if not self.cas.contains(digest):
                broken.append(digest)
        return broken

    def invalidate(self, checkpoint_id: str, reason: str) -> None:
        self.store.set_checkpoint_status(checkpoint_id, CheckpointStatus.INVALID)
        self.journal.append(
            "CHECKPOINT_INVALIDATED",
            "checkpoint-service",
            {"checkpoint_id": checkpoint_id, "reason": reason},
        )

    # -- side effects -----------------------------------------------------
    def guard_side_effect(
        self,
        lease: Lease,
        idempotency_key: str,
        effect_type: str,
        payload_digest: str,
    ) -> tuple[bool, str | None]:
        """Claim an effect. ``True`` means it already ran; do not repeat it."""
        return self.store.claim_side_effect(
            self.workspace.tenant_id,
            lease.run_id,
            lease.node_id,
            idempotency_key,
            effect_type,
            payload_digest,
        )

    def complete_side_effect(
        self, idempotency_key: str, external_reference: str | None, status: str = "COMMITTED"
    ) -> None:
        self.store.complete_side_effect(
            self.workspace.tenant_id, idempotency_key, status, external_reference
        )


def remaining_partitions(
    all_partitions: Iterable[str], decision: ResumeDecision
) -> tuple[str, ...]:
    """Partitions still to do. Completed work is never regenerated."""
    done = set(decision.completed_partitions)
    return tuple(sorted(partition for partition in all_partitions if partition not in done))


def require_resume(decision: ResumeDecision) -> CheckpointManifest:
    if not decision.resumable or decision.manifest is None:
        raise NotFound("no compatible checkpoint", reasons=list(decision.reasons))
    return decision.manifest
