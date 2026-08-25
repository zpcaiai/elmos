package io.elmos.snapshot;

import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SnapshotArchiveServiceTest {
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-23T00:00:00Z"), ZoneOffset.UTC);

    @Test void archivesBeforeGenerationSafeRootRelease() {
        List<String> events = new ArrayList<>();
        RecordingArtifacts artifacts = new RecordingArtifacts(events);
        RecordingJournal journal = new RecordingJournal(events);
        SnapshotModel.RepositorySnapshot available = snapshot(SnapshotModel.Status.AVAILABLE);
        SnapshotLifecyclePorts.SnapshotArchiveCoordinator coordinator =
                new SnapshotLifecyclePorts.SnapshotArchiveCoordinator() {
                    @Override public SnapshotModel.RepositorySnapshot requireSnapshot(
                            String organizationId, String repositoryId, String snapshotId) {
                        return available;
                    }
                    @Override public SnapshotModel.RepositorySnapshot archive(
                            SnapshotRootReconciliation reconciliation) {
                        events.add("database-archive");
                        journal.markDatabaseCommitted(
                                "org", reconciliation.reconciliationId(),
                                available.snapshotId());
                        return snapshot(SnapshotModel.Status.ARCHIVED);
                    }
                };
        var service = new SnapshotArchiveService(
                artifacts, coordinator, journal, CLOCK);

        SnapshotArchiveService.ArchiveResult result = service.archive(
                new SnapshotArchiveService.ArchiveRequest(
                        "org", "repo", "snapshot-1", "archive-request-1"));

        assertEquals(SnapshotModel.Status.ARCHIVED, result.status());
        assertEquals(List.of("retain", "journal-pending", "database-archive",
                "journal-committed", "release-generation:7", "journal-resolved"), events);
    }

    @Test void databaseFailureKeepsTheDurableRootAndRecordsTheOutcome() {
        List<String> events = new ArrayList<>();
        RecordingArtifacts artifacts = new RecordingArtifacts(events);
        RecordingJournal journal = new RecordingJournal(events);
        SnapshotModel.RepositorySnapshot available = snapshot(SnapshotModel.Status.AVAILABLE);
        SnapshotLifecyclePorts.SnapshotArchiveCoordinator coordinator =
                new SnapshotLifecyclePorts.SnapshotArchiveCoordinator() {
                    @Override public SnapshotModel.RepositorySnapshot requireSnapshot(
                            String organizationId, String repositoryId, String snapshotId) {
                        return available;
                    }
                    @Override public SnapshotModel.RepositorySnapshot archive(
                            SnapshotRootReconciliation reconciliation) {
                        throw new IllegalStateException("database unavailable");
                    }
                };
        var service = new SnapshotArchiveService(
                artifacts, coordinator, journal, CLOCK);

        assertThrows(IllegalStateException.class, () -> service.archive(
                new SnapshotArchiveService.ArchiveRequest(
                        "org", "repo", "snapshot-1", "archive-request-2")));

        assertTrue(events.contains("journal-failed"));
        assertTrue(events.stream().noneMatch(value -> value.startsWith("release")),
                "an AVAILABLE snapshot must retain its durable root");
    }

    @Test void conflictingArchiveAcknowledgementNeverReleasesTheRoot() {
        List<String> events = new ArrayList<>();
        RecordingArtifacts artifacts = new RecordingArtifacts(events);
        RecordingJournal journal = new RecordingJournal(events);
        SnapshotModel.RepositorySnapshot available = snapshot(SnapshotModel.Status.AVAILABLE);
        SnapshotLifecyclePorts.SnapshotArchiveCoordinator coordinator =
                new SnapshotLifecyclePorts.SnapshotArchiveCoordinator() {
                    @Override public SnapshotModel.RepositorySnapshot requireSnapshot(
                            String organizationId, String repositoryId, String snapshotId) {
                        return available;
                    }
                    @Override public SnapshotModel.RepositorySnapshot archive(
                            SnapshotRootReconciliation reconciliation) {
                        journal.markDatabaseCommitted(
                                "org", reconciliation.reconciliationId(),
                                available.snapshotId());
                        return new SnapshotModel.RepositorySnapshot(
                                available.snapshotId(), available.organizationId(),
                                available.repositoryId(), available.requestedRef(),
                                available.resolvedCommitSha(), available.treeSha(),
                                "cas:sha256:" + "e".repeat(64), available.archiveSha256(),
                                available.archiveSize(), available.manifestArtifactRef(),
                                available.manifestSha256(), available.snapshotSchemaVersion(),
                                SnapshotModel.Status.ARCHIVED, available.capturedAt());
                    }
                };

        assertThrows(SecurityException.class, () -> new SnapshotArchiveService(
                artifacts, coordinator, journal, CLOCK).archive(
                new SnapshotArchiveService.ArchiveRequest(
                        "org", "repo", "snapshot-1", "archive-conflict")));

        assertTrue(events.stream().noneMatch(value -> value.startsWith("release")),
                "a conflicting durable acknowledgement must leave the root reachable");
    }

    @Test void archivedRetryDoesNotReactivateTheCollectorRoot() {
        List<String> events = new ArrayList<>();
        RecordingArtifacts artifacts = new RecordingArtifacts(events);
        RecordingJournal journal = new RecordingJournal(events);
        SnapshotLifecyclePorts.SnapshotArchiveCoordinator coordinator =
                new SnapshotLifecyclePorts.SnapshotArchiveCoordinator() {
                    @Override public SnapshotModel.RepositorySnapshot requireSnapshot(
                            String organizationId, String repositoryId, String snapshotId) {
                        return snapshot(SnapshotModel.Status.ARCHIVED);
                    }
                    @Override public SnapshotModel.RepositorySnapshot archive(
                            SnapshotRootReconciliation reconciliation) {
                        throw new AssertionError("archived retry must not write");
                    }
                };
        var service = new SnapshotArchiveService(
                artifacts, coordinator, journal, CLOCK);

        SnapshotArchiveService.ArchiveResult result = service.archive(
                new SnapshotArchiveService.ArchiveRequest(
                        "org", "repo", "snapshot-1", "archive-request-3"));

        assertEquals(SnapshotModel.Status.ARCHIVED, result.status());
        assertTrue(events.isEmpty());
    }

    @Test void failedAttemptCanRetryTheSameLogicalArchiveOperation() {
        List<String> events = new ArrayList<>();
        RecordingArtifacts artifacts = new RecordingArtifacts(events);
        RecordingJournal journal = new RecordingJournal(events);
        SnapshotModel.RepositorySnapshot available = snapshot(SnapshotModel.Status.AVAILABLE);
        java.util.concurrent.atomic.AtomicInteger attempts =
                new java.util.concurrent.atomic.AtomicInteger();
        SnapshotLifecyclePorts.SnapshotArchiveCoordinator coordinator =
                new SnapshotLifecyclePorts.SnapshotArchiveCoordinator() {
                    @Override public SnapshotModel.RepositorySnapshot requireSnapshot(
                            String organizationId, String repositoryId, String snapshotId) {
                        return available;
                    }
                    @Override public SnapshotModel.RepositorySnapshot archive(
                            SnapshotRootReconciliation reconciliation) {
                        if (attempts.getAndIncrement() == 0) {
                            throw new IllegalStateException("first transaction rolled back");
                        }
                        journal.markDatabaseCommitted(
                                "org", reconciliation.reconciliationId(),
                                available.snapshotId());
                        return snapshot(SnapshotModel.Status.ARCHIVED);
                    }
                };
        var service = new SnapshotArchiveService(
                artifacts, coordinator, journal, CLOCK);
        var request = new SnapshotArchiveService.ArchiveRequest(
                "org", "repo", "snapshot-1", "same-idempotency-key");

        assertThrows(IllegalStateException.class, () -> service.archive(request));
        service.archive(request);

        List<SnapshotRootReconciliation> records =
                new ArrayList<>(journal.records.values());
        assertEquals(2, records.size());
        assertEquals(records.get(0).logicalOperationId(),
                records.get(1).logicalOperationId());
        assertTrue(!records.get(0).reconciliationId().equals(
                records.get(1).reconciliationId()));
        assertEquals(SnapshotRootReconciliation.Phase.COMMIT_FAILED,
                records.get(0).phase());
        assertEquals(SnapshotRootReconciliation.Phase.RESOLVED,
                records.get(1).phase());
    }

    private static SnapshotModel.RepositorySnapshot snapshot(SnapshotModel.Status status) {
        return new SnapshotModel.RepositorySnapshot(
                "snapshot-1", "org", "repo", "main", "a".repeat(40),
                "b".repeat(40), "cas:sha256:" + "c".repeat(64), "c".repeat(64),
                10, "cas:sha256:" + "d".repeat(64), "d".repeat(64), 1, status,
                Instant.parse("2026-08-22T00:00:00Z"));
    }

    private static final class RecordingArtifacts implements SnapshotPorts.ArtifactStore {
        private final List<String> events;
        private RecordingArtifacts(List<String> events) { this.events = events; }
        @Override public String putIfAbsent(SnapshotPorts.ArtifactResourceContext resource,
                String sha256, long size, java.io.InputStream content, String mediaType) {
            throw new UnsupportedOperationException();
        }
        @Override public SnapshotPorts.ArtifactRetention retainSnapshotGeneration(
                SnapshotPorts.ArtifactResourceContext resource, String snapshotId,
                List<String> references) {
            events.add("retain");
            return new SnapshotPorts.ArtifactRetention(
                    snapshotId, Map.of("test.generation", 7L));
        }
        @Override public void releaseSnapshotGeneration(
                SnapshotPorts.ArtifactResourceContext resource,
                SnapshotPorts.ArtifactRetention retention) {
            events.add("release-generation:"
                    + retention.requireGeneration("test.generation"));
        }
    }

    private static final class RecordingJournal implements
            SnapshotLifecyclePorts.RootReconciliationJournal {
        private final List<String> events;
        private final Map<String, SnapshotRootReconciliation> records = new LinkedHashMap<>();
        private RecordingJournal(List<String> events) { this.events = events; }
        @Override public void recordPending(SnapshotRootReconciliation reconciliation) {
            events.add("journal-pending"); records.put(reconciliation.reconciliationId(), reconciliation);
        }
        @Override public void markDatabaseCommitted(
                String organizationId, String id, String durableId) {
            events.add("journal-committed"); records.computeIfPresent(id,
                    (key, value) -> value.committed(durableId));
        }
        @Override public void markCommitFailed(String organizationId, String id) {
            events.add("journal-failed"); records.computeIfPresent(id,
                    (key, value) -> value.failed());
        }
        @Override public void markResolved(String organizationId, String id) {
            events.add("journal-resolved"); records.computeIfPresent(id,
                    (key, value) -> value.resolved());
        }
        @Override public List<SnapshotRootReconciliation> pending(String organizationId, int limit) {
            return records.values().stream().limit(limit).toList();
        }
    }
}
