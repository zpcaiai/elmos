package io.elmos.snapshot;

import java.time.Clock;
import java.time.Duration;
import java.util.List;
import java.util.Objects;

/** Reconciles commit-unknown capture roots and committed archive releases. */
public final class SnapshotProvisionalRootReconciler {
    public record ReconciliationFailure(String reconciliationId, String code) { }
    public record ReconciliationReport(
            int examined,
            int resolved,
            int retained,
            List<ReconciliationFailure> failures
    ) {
        public ReconciliationReport {
            failures = List.copyOf(failures);
        }

        public int failed() {
            return failures.size();
        }
    }

    private enum Outcome {
        RESOLVED,
        RETAINED
    }

    private final SnapshotPorts.ArtifactStore artifacts;
    private final SnapshotPorts.SnapshotStore snapshots;
    private final SnapshotLifecyclePorts.RootReconciliationJournal reconciliations;
    private final Clock clock;
    private final Duration pendingGrace;

    public SnapshotProvisionalRootReconciler(
            SnapshotPorts.ArtifactStore artifacts,
            SnapshotPorts.SnapshotStore snapshots,
            SnapshotLifecyclePorts.RootReconciliationJournal reconciliations
    ) {
        this(artifacts, snapshots, reconciliations,
                Clock.systemUTC(), Duration.ofMinutes(5));
    }

    public SnapshotProvisionalRootReconciler(
            SnapshotPorts.ArtifactStore artifacts,
            SnapshotPorts.SnapshotStore snapshots,
            SnapshotLifecyclePorts.RootReconciliationJournal reconciliations,
            Clock clock,
            Duration pendingGrace
    ) {
        this.artifacts = Objects.requireNonNull(artifacts, "artifacts");
        this.snapshots = Objects.requireNonNull(snapshots, "snapshots");
        this.reconciliations = Objects.requireNonNull(reconciliations, "reconciliations");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.pendingGrace = Objects.requireNonNull(pendingGrace, "pendingGrace");
        if (pendingGrace.isNegative() || pendingGrace.isZero()
                || pendingGrace.compareTo(Duration.ofHours(1)) > 0) {
            throw new IllegalArgumentException(
                    "pending reconciliation grace must be between zero and one hour");
        }
    }

    public ReconciliationReport reconcile(String organizationId, int limit) {
        if (organizationId == null || organizationId.isBlank()) {
            throw new IllegalArgumentException("organizationId is required");
        }
        if (limit < 1 || limit > 1_000) {
            throw new IllegalArgumentException("reconciliation limit must be between 1 and 1000");
        }
        reconciliations.failStalePending(
                organizationId, clock.instant().minus(pendingGrace), limit);
        List<SnapshotRootReconciliation> pending =
                reconciliations.pending(organizationId, limit);
        int resolved = 0;
        int retained = 0;
        java.util.ArrayList<ReconciliationFailure> failures = new java.util.ArrayList<>();
        for (SnapshotRootReconciliation reconciliation : pending) {
            try {
                Outcome outcome = reconcileOne(organizationId, reconciliation);
                if (outcome == Outcome.RESOLVED) resolved++;
                else retained++;
            } catch (SecurityException violation) {
                // Tenant or immutable-identity conflicts are batch-fatal: continuing could turn a
                // hostile journal row into an existence oracle or release the wrong resource.
                throw violation;
            } catch (RuntimeException failure) {
                // The root remains active because resolution is marked only after release/handoff.
                // Keep processing independent records, but surface every failed identity.
                failures.add(new ReconciliationFailure(
                        reconciliation.reconciliationId(),
                        failure.getClass().getSimpleName()));
            }
        }
        return new ReconciliationReport(
                pending.size(), resolved, retained, failures);
    }

    private Outcome reconcileOne(
            String organizationId,
            SnapshotRootReconciliation reconciliation
    ) {
        SnapshotModel.RepositorySnapshot candidate = reconciliation.snapshot();
        if (!organizationId.equals(candidate.organizationId())) {
            throw new SecurityException("reconciliation belongs to another organization");
        }
        var resource = new SnapshotPorts.ArtifactResourceContext(
                candidate.organizationId(), candidate.repositoryId());
        SnapshotCaptureService.requireArtifactReferences(candidate);

        if (reconciliation.phase() == SnapshotRootReconciliation.Phase.PENDING) {
            return Outcome.RETAINED;
        }
        if (reconciliation.phase() == SnapshotRootReconciliation.Phase.RESOLVED) {
            throw new IllegalStateException("resolved reconciliation was returned as pending");
        }

        if (reconciliation.phase() == SnapshotRootReconciliation.Phase.COMMIT_FAILED) {
            if (reconciliation.kind() == SnapshotRootReconciliation.Kind.CAPTURE_COMMIT) {
                artifacts.releaseSnapshotGeneration(resource, reconciliation.retention());
            } else {
                SnapshotModel.RepositorySnapshot stored = requireDurableSnapshot(candidate);
                if (stored.status() == SnapshotModel.Status.ARCHIVED) {
                    // A later idempotent retry can legitimately win after this attempt's
                    // transaction failed. The archived row makes release safe; repeating the
                    // generation-bound release also closes a retry that committed but crashed
                    // before its own collector acknowledgement.
                    SnapshotArchiveService.requireEquivalent(
                            candidate, stored, SnapshotModel.Status.ARCHIVED);
                    artifacts.releaseSnapshotGeneration(
                            resource, reconciliation.retention());
                } else {
                    SnapshotArchiveService.requireEquivalent(
                            candidate, stored, SnapshotModel.Status.AVAILABLE);
                }
            }
            // A failed archive transaction leaves the snapshot AVAILABLE; preserving its root is
            // the correct resolution. Verify that state before resolving so a corrupt journal
            // cannot permanently leak an already-archived root.
            reconciliations.markResolved(
                    organizationId, reconciliation.reconciliationId());
            return Outcome.RESOLVED;
        }

        if (reconciliation.kind() == SnapshotRootReconciliation.Kind.ARCHIVE_RELEASE) {
            if (!candidate.snapshotId().equals(reconciliation.durableSnapshotId())) {
                throw new SecurityException("archive reconciliation changed snapshot identity");
            }
            SnapshotModel.RepositorySnapshot stored = requireDurableSnapshot(candidate);
            SnapshotArchiveService.requireEquivalent(
                    candidate, stored, SnapshotModel.Status.ARCHIVED);
            artifacts.releaseSnapshotGeneration(resource, reconciliation.retention());
            reconciliations.markResolved(
                    organizationId, reconciliation.reconciliationId());
            return Outcome.RESOLVED;
        }

        SnapshotModel.RepositorySnapshot stored = requireDurableSnapshot(candidate);
        SnapshotCaptureService.requirePersistedContentEquivalent(candidate, stored);
        if (!stored.snapshotId().equals(reconciliation.durableSnapshotId())) {
            throw new SecurityException("committed snapshot identity conflicts with journal");
        }
        if (stored.status() == SnapshotModel.Status.ARCHIVED) {
            // Archival can win after the database commit but before this handoff. Never
            // reactivate an archived winner merely to retire the provisional owner.
            artifacts.releaseSnapshotGeneration(resource, reconciliation.retention());
        } else if (!stored.snapshotId().equals(candidate.snapshotId())) {
            artifacts.retainSnapshotGeneration(
                    resource, stored.snapshotId(), SnapshotCaptureService.references(stored));
            artifacts.releaseSnapshotGeneration(resource, reconciliation.retention());
        }
        reconciliations.markResolved(
                organizationId, reconciliation.reconciliationId());
        return Outcome.RESOLVED;
    }

    private SnapshotModel.RepositorySnapshot requireDurableSnapshot(
            SnapshotModel.RepositorySnapshot candidate
    ) {
        SnapshotModel.RepositorySnapshot stored = snapshots.findReusable(
                candidate.organizationId(), candidate.repositoryId(),
                candidate.resolvedCommitSha(),
                candidate.snapshotSchemaVersion());
        if (stored == null) {
            throw new IllegalStateException(
                    "snapshot reconciliation has no durable database row; root retained");
        }
        return stored;
    }
}
