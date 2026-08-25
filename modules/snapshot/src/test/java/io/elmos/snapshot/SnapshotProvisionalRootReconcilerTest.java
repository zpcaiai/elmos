package io.elmos.snapshot;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.time.Clock;
import java.time.Duration;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SnapshotProvisionalRootReconcilerTest {
    @Test void stalePendingIsFailedAtomicallyBeforeItsGenerationIsReleased() {
        SnapshotModel.RepositorySnapshot snapshot = snapshot("snapshot-stale", "org");
        RecordingJournal journal = new RecordingJournal(List.of(reconciliation(
                "reconcile-stale", snapshot,
                SnapshotRootReconciliation.Phase.PENDING, null))) {
            @Override public int failStalePending(
                    String organizationId, Instant staleBefore, int limit) {
                assertEquals(Instant.parse("2026-08-24T00:05:00Z"), staleBefore);
                records.computeIfPresent("reconcile-stale",
                        (key, value) -> value.failed());
                return 1;
            }
        };
        RecordingArtifacts artifacts = new RecordingArtifacts();
        var reconciler = new SnapshotProvisionalRootReconciler(
                artifacts, emptySnapshots(), journal,
                Clock.fixed(Instant.parse("2026-08-24T00:10:00Z"), ZoneOffset.UTC),
                Duration.ofMinutes(5));

        SnapshotProvisionalRootReconciler.ReconciliationReport report =
                reconciler.reconcile("org", 10);

        assertEquals(1, report.resolved());
        assertEquals(List.of("release:snapshot-stale"), artifacts.events);
    }

    @Test void ambiguousFirstRecordDoesNotStarveAResolvedLaterRecord() {
        SnapshotModel.RepositorySnapshot first = snapshot("snapshot-1", "org");
        SnapshotModel.RepositorySnapshot second = snapshot("snapshot-2", "org");
        RecordingJournal journal = new RecordingJournal(List.of(
                reconciliation("reconcile-1", first,
                        SnapshotRootReconciliation.Phase.PENDING, null),
                reconciliation("reconcile-2", second,
                        SnapshotRootReconciliation.Phase.COMMIT_FAILED, null)));
        RecordingArtifacts artifacts = new RecordingArtifacts();
        var reconciler = new SnapshotProvisionalRootReconciler(
                artifacts, emptySnapshots(), journal);

        SnapshotProvisionalRootReconciler.ReconciliationReport report =
                reconciler.reconcile("org", 10);

        assertEquals(2, report.examined());
        assertEquals(1, report.resolved());
        assertEquals(1, report.retained());
        assertEquals(0, report.failed());
        assertEquals(List.of("release:snapshot-2"), artifacts.events);
        assertEquals(List.of("reconcile-2"), journal.resolved);
    }

    @Test void committedConcurrentWinnerIsRetainedBeforeProvisionalRelease() {
        SnapshotModel.RepositorySnapshot candidate = snapshot("snapshot-provisional", "org");
        SnapshotModel.RepositorySnapshot winner = snapshot("snapshot-winner", "org");
        SnapshotRootReconciliation reconciliation = reconciliation(
                "reconcile-winner", candidate,
                SnapshotRootReconciliation.Phase.DATABASE_COMMITTED,
                winner.snapshotId());
        RecordingJournal journal = new RecordingJournal(List.of(reconciliation));
        RecordingArtifacts artifacts = new RecordingArtifacts();
        SnapshotPorts.SnapshotStore snapshots = new SnapshotPorts.SnapshotStore() {
            @Override public SnapshotModel.RepositorySnapshot findReusable(
                    String organizationId, String repositoryId, String commitSha,
                    int schemaVersion) {
                return winner;
            }
            @Override public SnapshotModel.RepositorySnapshot saveAvailable(
                    SnapshotModel.RepositorySnapshot snapshot) {
                throw new UnsupportedOperationException();
            }
        };

        var report = new SnapshotProvisionalRootReconciler(
                artifacts, snapshots, journal).reconcile("org", 10);

        assertEquals(1, report.resolved());
        assertEquals(List.of("retain:snapshot-winner", "release:snapshot-provisional"),
                artifacts.events);
    }

    @Test void committedArchiveIsVerifiedDurableBeforeItsRootIsReleased() {
        SnapshotModel.RepositorySnapshot candidate = snapshot("snapshot-archive", "org");
        SnapshotModel.RepositorySnapshot archived = snapshot(
                "snapshot-archive", "org", SnapshotModel.Status.ARCHIVED);
        SnapshotRootReconciliation reconciliation = reconciliation(
                "reconcile-archive", SnapshotRootReconciliation.Kind.ARCHIVE_RELEASE,
                candidate, SnapshotRootReconciliation.Phase.DATABASE_COMMITTED,
                candidate.snapshotId());
        RecordingJournal journal = new RecordingJournal(List.of(reconciliation));
        RecordingArtifacts artifacts = new RecordingArtifacts();

        SnapshotProvisionalRootReconciler.ReconciliationReport report =
                new SnapshotProvisionalRootReconciler(
                        artifacts, snapshotsReturning(archived), journal)
                        .reconcile("org", 10);

        assertEquals(1, report.resolved());
        assertEquals(List.of("release:snapshot-archive"), artifacts.events);
        assertEquals(List.of("reconcile-archive"), journal.resolved);
    }

    @Test void committedArchiveWithAvailableDatabaseRowFailsClosed() {
        SnapshotModel.RepositorySnapshot available = snapshot("snapshot-archive", "org");
        SnapshotRootReconciliation reconciliation = reconciliation(
                "reconcile-archive-conflict",
                SnapshotRootReconciliation.Kind.ARCHIVE_RELEASE,
                available, SnapshotRootReconciliation.Phase.DATABASE_COMMITTED,
                available.snapshotId());
        RecordingJournal journal = new RecordingJournal(List.of(reconciliation));
        RecordingArtifacts artifacts = new RecordingArtifacts();

        assertThrows(SecurityException.class, () ->
                new SnapshotProvisionalRootReconciler(
                        artifacts, snapshotsReturning(available), journal)
                        .reconcile("org", 10));

        assertEquals(List.of(), artifacts.events);
        assertEquals(List.of(), journal.resolved);
    }

    @Test void failedArchiveSupersededBySuccessfulRetryReleasesAndResolves() {
        SnapshotModel.RepositorySnapshot candidate = snapshot("snapshot-retried", "org");
        SnapshotModel.RepositorySnapshot archived = snapshot(
                "snapshot-retried", "org", SnapshotModel.Status.ARCHIVED);
        SnapshotRootReconciliation failedAttempt = reconciliation(
                "reconcile-failed-archive",
                SnapshotRootReconciliation.Kind.ARCHIVE_RELEASE,
                candidate, SnapshotRootReconciliation.Phase.COMMIT_FAILED, null);
        RecordingJournal journal = new RecordingJournal(List.of(failedAttempt));
        RecordingArtifacts artifacts = new RecordingArtifacts();

        SnapshotProvisionalRootReconciler.ReconciliationReport report =
                new SnapshotProvisionalRootReconciler(
                        artifacts, snapshotsReturning(archived), journal)
                        .reconcile("org", 10);

        assertEquals(1, report.resolved());
        assertEquals(0, report.failed());
        assertEquals(List.of("release:snapshot-retried"), artifacts.events);
        assertEquals(List.of("reconcile-failed-archive"), journal.resolved);
    }

    @Test void captureHandoffDoesNotReactivateAnAlreadyArchivedWinner() {
        SnapshotModel.RepositorySnapshot candidate = snapshot("snapshot-provisional", "org");
        SnapshotModel.RepositorySnapshot archivedWinner = snapshot(
                "snapshot-winner", "org", SnapshotModel.Status.ARCHIVED);
        SnapshotRootReconciliation reconciliation = reconciliation(
                "reconcile-archived-winner", candidate,
                SnapshotRootReconciliation.Phase.DATABASE_COMMITTED,
                archivedWinner.snapshotId());
        RecordingJournal journal = new RecordingJournal(List.of(reconciliation));
        RecordingArtifacts artifacts = new RecordingArtifacts();

        SnapshotProvisionalRootReconciler.ReconciliationReport report =
                new SnapshotProvisionalRootReconciler(
                        artifacts, snapshotsReturning(archivedWinner), journal)
                        .reconcile("org", 10);

        assertEquals(1, report.resolved());
        assertEquals(List.of("release:snapshot-provisional"), artifacts.events);
    }

    @Test void tenantConflictIsBatchFatalAndNeverReleases() {
        SnapshotModel.RepositorySnapshot foreign = snapshot("snapshot-foreign", "org-b");
        RecordingJournal journal = new RecordingJournal(List.of(reconciliation(
                "reconcile-foreign", foreign,
                SnapshotRootReconciliation.Phase.COMMIT_FAILED, null)));
        RecordingArtifacts artifacts = new RecordingArtifacts();

        assertThrows(SecurityException.class, () -> new SnapshotProvisionalRootReconciler(
                artifacts, emptySnapshots(), journal).reconcile("org-a", 10));
        assertEquals(List.of(), artifacts.events);
    }

    @Test void oneOperationalFailureIsReportedWithoutStarvingLaterWork() {
        SnapshotModel.RepositorySnapshot first = snapshot("snapshot-fails", "org");
        SnapshotModel.RepositorySnapshot second = snapshot("snapshot-succeeds", "org");
        RecordingJournal journal = new RecordingJournal(List.of(
                reconciliation("reconcile-fails", first,
                        SnapshotRootReconciliation.Phase.COMMIT_FAILED, null),
                reconciliation("reconcile-succeeds", second,
                        SnapshotRootReconciliation.Phase.COMMIT_FAILED, null)));
        List<String> released = new ArrayList<>();
        SnapshotPorts.ArtifactStore artifacts = new SnapshotPorts.ArtifactStore() {
            @Override public String putIfAbsent(SnapshotPorts.ArtifactResourceContext resource,
                    String sha256, long size, java.io.InputStream content, String mediaType) {
                throw new UnsupportedOperationException();
            }
            @Override public void releaseSnapshotGeneration(
                    SnapshotPorts.ArtifactResourceContext resource,
                    SnapshotPorts.ArtifactRetention retention) {
                if (retention.snapshotId().equals("snapshot-fails")) {
                    throw new IllegalStateException("catalog temporarily unavailable");
                }
                released.add(retention.snapshotId());
            }
        };

        SnapshotProvisionalRootReconciler.ReconciliationReport report =
                new SnapshotProvisionalRootReconciler(
                        artifacts, emptySnapshots(), journal).reconcile("org", 10);

        assertEquals(1, report.resolved());
        assertEquals(0, report.retained());
        assertEquals(1, report.failed());
        assertEquals("reconcile-fails", report.failures().get(0).reconciliationId());
        assertEquals(List.of("snapshot-succeeds"), released);
    }

    private static SnapshotRootReconciliation reconciliation(
            String id,
            SnapshotModel.RepositorySnapshot snapshot,
            SnapshotRootReconciliation.Phase phase,
            String durableSnapshotId
    ) {
        return reconciliation(id, SnapshotRootReconciliation.Kind.CAPTURE_COMMIT,
                snapshot, phase, durableSnapshotId);
    }

    private static SnapshotRootReconciliation reconciliation(
            String id,
            SnapshotRootReconciliation.Kind kind,
            SnapshotModel.RepositorySnapshot snapshot,
            SnapshotRootReconciliation.Phase phase,
            String durableSnapshotId
    ) {
        return new SnapshotRootReconciliation(
                id, "logical-" + id, kind,
                phase, snapshot,
                new SnapshotPorts.ArtifactRetention(
                        snapshot.snapshotId(), Map.of("test.generation", 9L)),
                durableSnapshotId, Instant.parse("2026-08-23T00:00:00Z"));
    }

    private static SnapshotModel.RepositorySnapshot snapshot(String id, String organization) {
        return snapshot(id, organization, SnapshotModel.Status.AVAILABLE);
    }

    private static SnapshotModel.RepositorySnapshot snapshot(
            String id,
            String organization,
            SnapshotModel.Status status
    ) {
        return new SnapshotModel.RepositorySnapshot(
                id, organization, "repo", "main", "a".repeat(40), "b".repeat(40),
                "cas:sha256:" + "c".repeat(64), "c".repeat(64), 10,
                "cas:sha256:" + "d".repeat(64), "d".repeat(64), 1,
                status,
                Instant.parse("2026-08-22T00:00:00Z"));
    }

    private static SnapshotPorts.SnapshotStore snapshotsReturning(
            SnapshotModel.RepositorySnapshot stored
    ) {
        return new SnapshotPorts.SnapshotStore() {
            @Override public SnapshotModel.RepositorySnapshot findReusable(
                    String organizationId, String repositoryId, String commitSha,
                    int schemaVersion) {
                return stored;
            }
            @Override public SnapshotModel.RepositorySnapshot saveAvailable(
                    SnapshotModel.RepositorySnapshot snapshot) {
                throw new UnsupportedOperationException();
            }
        };
    }

    private static SnapshotPorts.SnapshotStore emptySnapshots() {
        return new SnapshotPorts.SnapshotStore() {
            @Override public SnapshotModel.RepositorySnapshot findReusable(
                    String organizationId, String repositoryId, String commitSha,
                    int schemaVersion) { return null; }
            @Override public SnapshotModel.RepositorySnapshot saveAvailable(
                    SnapshotModel.RepositorySnapshot snapshot) {
                throw new UnsupportedOperationException();
            }
        };
    }

    private static final class RecordingArtifacts implements SnapshotPorts.ArtifactStore {
        private final List<String> events = new ArrayList<>();
        @Override public String putIfAbsent(SnapshotPorts.ArtifactResourceContext resource,
                String sha256, long size, java.io.InputStream content, String mediaType) {
            throw new UnsupportedOperationException();
        }
        @Override public SnapshotPorts.ArtifactRetention retainSnapshotGeneration(
                SnapshotPorts.ArtifactResourceContext resource, String snapshotId,
                List<String> references) {
            events.add("retain:" + snapshotId);
            return new SnapshotPorts.ArtifactRetention(
                    snapshotId, Map.of("test.generation", 10L));
        }
        @Override public void releaseSnapshotGeneration(
                SnapshotPorts.ArtifactResourceContext resource,
                SnapshotPorts.ArtifactRetention retention) {
            events.add("release:" + retention.snapshotId());
        }
    }

    private static class RecordingJournal implements
            SnapshotLifecyclePorts.RootReconciliationJournal {
        protected final Map<String, SnapshotRootReconciliation> records = new LinkedHashMap<>();
        private final List<String> resolved = new ArrayList<>();
        private RecordingJournal(List<SnapshotRootReconciliation> values) {
            values.forEach(value -> records.put(value.reconciliationId(), value));
        }
        @Override public void recordPending(SnapshotRootReconciliation reconciliation) {
            records.put(reconciliation.reconciliationId(), reconciliation);
        }
        @Override public void markDatabaseCommitted(
                String organizationId, String id, String durableId) {
            records.computeIfPresent(id, (key, value) -> value.committed(durableId));
        }
        @Override public void markCommitFailed(String organizationId, String id) {
            records.computeIfPresent(id, (key, value) -> value.failed());
        }
        @Override public void markResolved(String organizationId, String id) {
            resolved.add(id); records.computeIfPresent(id, (key, value) -> value.resolved());
        }
        @Override public List<SnapshotRootReconciliation> pending(String organizationId, int limit) {
            // Deliberately return the supplied order; tenant validation belongs to the reconciler.
            return records.values().stream()
                    .filter(value -> value.phase() != SnapshotRootReconciliation.Phase.RESOLVED)
                    .limit(limit).toList();
        }
    }
}
