package io.elmos.snapshot;

import io.elmos.scm.EphemeralCredential;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.*;

class SnapshotCaptureServiceTest {
    @TempDir Path temp;
    @Test void capturesImmutableCommitAndAlwaysClosesCredentialAndStaging() throws Exception {
        Files.writeString(temp.resolve("pom.xml"), "<project/>"); AtomicBoolean stagingClosed = new AtomicBoolean();
        EphemeralCredential credential = new EphemeralCredential("token".toCharArray()); List<String> stored = new ArrayList<>();
        List<SnapshotPorts.ArtifactResourceContext> resources = new ArrayList<>();
        List<SnapshotModel.RepositorySnapshot> saved = new ArrayList<>();
        var service = new SnapshotCaptureService((organization, repository, external, installation) -> credential,
                (repository, ref, secret) -> new SnapshotPorts.ResolvedRef("a".repeat(40), "b".repeat(40)),
                (repository, ref, secret) -> new SnapshotPorts.FetchedSource(temp, () -> stagingClosed.set(true)),
                new DeterministicSnapshotArchiver(), (resource, digest, size, content, media) -> {
                    resources.add(resource); stored.add(digest); return "cas:sha256:" + digest;
                },
                new SnapshotPorts.SnapshotStore() {
                    public SnapshotModel.RepositorySnapshot findReusable(String repository, String sha, int version) { return null; }
                    public SnapshotModel.RepositorySnapshot saveAvailable(SnapshotModel.RepositorySnapshot snapshot) { saved.add(snapshot); return snapshot; }
                }, Clock.fixed(Instant.parse("2026-07-20T00:00:00Z"), ZoneOffset.UTC));
        var result = service.capture(new SnapshotCaptureService.CaptureRequest("org", "repo", 1, 2, "example/repo", "refs/heads/main", "corr", "key"));
        assertEquals(SnapshotModel.Status.AVAILABLE, result.status()); assertEquals(2, stored.size()); assertEquals(1, saved.size()); assertTrue(stagingClosed.get());
        assertEquals(List.of(
                new SnapshotPorts.ArtifactResourceContext("org", "repo"),
                new SnapshotPorts.ArtifactResourceContext("org", "repo")), resources);
        assertThrows(IllegalStateException.class, () -> credential.use(String::new));
    }

    @Test void retainsArchiveAndManifestBeforePublishingTheSnapshot() throws Exception {
        Files.writeString(temp.resolve("pom.xml"), "<project/>");
        RecordingArtifacts artifacts = new RecordingArtifacts();
        AtomicBoolean saveObservedRoot = new AtomicBoolean();
        var service = service(artifacts, new SnapshotPorts.SnapshotStore() {
            public SnapshotModel.RepositorySnapshot findReusable(
                    String repository, String sha, int version) {
                return null;
            }

            public SnapshotModel.RepositorySnapshot saveAvailable(
                    SnapshotModel.RepositorySnapshot snapshot) {
                saveObservedRoot.set(artifacts.retentions.stream()
                        .anyMatch(retention -> retention.snapshotId().equals(snapshot.snapshotId())
                                && retention.references().equals(List.of(
                                        snapshot.archiveArtifactRef(),
                                        snapshot.manifestArtifactRef()))));
                return snapshot;
            }
        });

        SnapshotModel.RepositorySnapshot result = service.capture(request());

        assertTrue(saveObservedRoot.get(), "GC roots must exist before the DB snapshot is visible");
        assertEquals(1, artifacts.retentions.size());
        assertEquals(result.snapshotId(), artifacts.retentions.get(0).snapshotId());
        assertEquals(2, artifacts.retentions.get(0).references().size());
        assertTrue(artifacts.releases.isEmpty());
    }

    @Test void keepsTheProvisionalRootWhenSnapshotCommitOutcomeIsUnknown() throws Exception {
        Files.writeString(temp.resolve("pom.xml"), "<project/>");
        RecordingArtifacts artifacts = new RecordingArtifacts();
        var service = service(artifacts, new SnapshotPorts.SnapshotStore() {
            public SnapshotModel.RepositorySnapshot findReusable(
                    String repository, String sha, int version) {
                return null;
            }

            public SnapshotModel.RepositorySnapshot saveAvailable(
                    SnapshotModel.RepositorySnapshot snapshot) {
                throw new IllegalStateException("database rejected snapshot");
            }
        });

        assertThrows(IllegalStateException.class, () -> service.capture(request()));

        assertEquals(1, artifacts.retentions.size());
        assertTrue(artifacts.releases.isEmpty(),
                "an unknown commit outcome must keep bytes reachable for reconciliation");
        assertEquals(List.of("retain:" + artifacts.retentions.get(0).snapshotId()),
                artifacts.events);
    }

    @Test void reusableSnapshotRepairsItsDurableRootBeforeItIsReturned() {
        RecordingArtifacts artifacts = new RecordingArtifacts();
        SnapshotModel.RepositorySnapshot reusable = new SnapshotModel.RepositorySnapshot(
                "snapshot-existing", "org", "repo", "refs/heads/main",
                "a".repeat(40), "b".repeat(40), "cas:sha256:" + "1".repeat(64),
                "1".repeat(64), 123, "cas:sha256:" + "2".repeat(64),
                "2".repeat(64), 1, SnapshotModel.Status.AVAILABLE,
                Instant.parse("2026-07-19T00:00:00Z"));
        var service = service(artifacts, new SnapshotPorts.SnapshotStore() {
            public SnapshotModel.RepositorySnapshot findReusable(
                    String repository, String sha, int version) {
                return reusable;
            }

            public SnapshotModel.RepositorySnapshot saveAvailable(
                    SnapshotModel.RepositorySnapshot snapshot) {
                throw new AssertionError("reusable snapshot must not be saved again");
            }
        });

        assertSame(reusable, service.capture(request()));
        assertEquals(0, artifacts.putCount);
        assertEquals(List.of(new Retention("snapshot-existing", List.of(
                reusable.archiveArtifactRef(), reusable.manifestArtifactRef()))),
                artifacts.retentions);
    }

    @Test void concurrentWinnerIsRetainedBeforeTheProvisionalRootIsReleased() throws Exception {
        Files.writeString(temp.resolve("pom.xml"), "<project/>");
        RecordingArtifacts artifacts = new RecordingArtifacts();
        var service = service(artifacts, new SnapshotPorts.SnapshotStore() {
            public SnapshotModel.RepositorySnapshot findReusable(
                    String repository, String sha, int version) {
                return null;
            }

            public SnapshotModel.RepositorySnapshot saveAvailable(
                    SnapshotModel.RepositorySnapshot snapshot) {
                return new SnapshotModel.RepositorySnapshot(
                        "snapshot-winner", snapshot.organizationId(), snapshot.repositoryId(),
                        snapshot.requestedRef(), snapshot.resolvedCommitSha(), snapshot.treeSha(),
                        snapshot.archiveArtifactRef(), snapshot.archiveSha256(), snapshot.archiveSize(),
                        snapshot.manifestArtifactRef(), snapshot.manifestSha256(),
                        snapshot.snapshotSchemaVersion(), snapshot.status(), snapshot.capturedAt());
            }
        });

        SnapshotModel.RepositorySnapshot result = service.capture(request());

        assertEquals("snapshot-winner", result.snapshotId());
        assertEquals(2, artifacts.retentions.size());
        String provisional = artifacts.retentions.get(0).snapshotId();
        assertNotEquals("snapshot-winner", provisional);
        assertEquals("snapshot-winner", artifacts.retentions.get(1).snapshotId());
        assertEquals(List.of(provisional), artifacts.releases);
        assertEquals(List.of(
                "retain:" + provisional,
                "retain:snapshot-winner",
                "release:" + provisional), artifacts.events);
    }

    @Test void conflictingWinnerReferenceNeverCausesProvisionalRootRelease() throws Exception {
        Files.writeString(temp.resolve("pom.xml"), "<project/>");
        RecordingArtifacts artifacts = new RecordingArtifacts();
        var service = service(artifacts, new SnapshotPorts.SnapshotStore() {
            public SnapshotModel.RepositorySnapshot findReusable(
                    String repository, String sha, int version) {
                return null;
            }

            public SnapshotModel.RepositorySnapshot saveAvailable(
                    SnapshotModel.RepositorySnapshot snapshot) {
                return new SnapshotModel.RepositorySnapshot(
                        "snapshot-conflict", snapshot.organizationId(), snapshot.repositoryId(),
                        snapshot.requestedRef(), snapshot.resolvedCommitSha(), snapshot.treeSha(),
                        "cas:sha256:" + "f".repeat(64), snapshot.archiveSha256(),
                        snapshot.archiveSize(), snapshot.manifestArtifactRef(),
                        snapshot.manifestSha256(), snapshot.snapshotSchemaVersion(),
                        snapshot.status(), snapshot.capturedAt());
            }
        });

        assertThrows(SecurityException.class, () -> service.capture(request()));

        assertEquals(1, artifacts.retentions.size());
        assertTrue(artifacts.releases.isEmpty(),
                "a conflicting durable winner must leave provisional bytes reachable");
    }

    private SnapshotCaptureService service(
            SnapshotPorts.ArtifactStore artifacts,
            SnapshotPorts.SnapshotStore snapshots
    ) {
        return new SnapshotCaptureService(
                (organization, repository, external, installation) ->
                        new EphemeralCredential("token".toCharArray()),
                (repository, ref, secret) ->
                        new SnapshotPorts.ResolvedRef("a".repeat(40), "b".repeat(40)),
                (repository, ref, secret) ->
                        new SnapshotPorts.FetchedSource(temp, () -> { }),
                new DeterministicSnapshotArchiver(), artifacts, snapshots,
                Clock.fixed(Instant.parse("2026-07-20T00:00:00Z"), ZoneOffset.UTC));
    }

    private static SnapshotCaptureService.CaptureRequest request() {
        return new SnapshotCaptureService.CaptureRequest(
                "org", "repo", 1, 2, "example/repo", "refs/heads/main", "corr", "key");
    }

    private record Retention(String snapshotId, List<String> references) {
        private Retention {
            references = List.copyOf(references);
        }
    }

    private static final class RecordingArtifacts implements SnapshotPorts.ArtifactStore {
        private final List<Retention> retentions = new ArrayList<>();
        private final List<String> releases = new ArrayList<>();
        private final List<String> events = new ArrayList<>();
        private int putCount;

        @Override
        public String putIfAbsent(SnapshotPorts.ArtifactResourceContext resource,
                                  String sha256,
                                  long size,
                                  java.io.InputStream content,
                                  String mediaType) {
            putCount++;
            return "cas:sha256:" + sha256;
        }

        @Override
        public void retainSnapshot(SnapshotPorts.ArtifactResourceContext resource,
                                   String snapshotId,
                                   List<String> references) {
            retentions.add(new Retention(snapshotId, references));
            events.add("retain:" + snapshotId);
        }

        @Override
        public void releaseSnapshot(SnapshotPorts.ArtifactResourceContext resource,
                                    String snapshotId) {
            releases.add(snapshotId);
            events.add("release:" + snapshotId);
        }
    }
}
