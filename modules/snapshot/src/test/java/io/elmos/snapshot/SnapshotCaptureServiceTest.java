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
        EphemeralCredential credential = new EphemeralCredential("token".toCharArray()); List<String> stored = new ArrayList<>(); List<SnapshotModel.RepositorySnapshot> saved = new ArrayList<>();
        var service = new SnapshotCaptureService((repository, external, installation) -> credential,
                (repository, ref, secret) -> new SnapshotPorts.ResolvedRef("a".repeat(40), "b".repeat(40)),
                (repository, ref, secret) -> new SnapshotPorts.FetchedSource(temp, () -> stagingClosed.set(true)),
                new DeterministicSnapshotArchiver(), (digest, size, content, media) -> { stored.add(digest); return "artifact:" + digest; },
                new SnapshotPorts.SnapshotStore() {
                    public SnapshotModel.RepositorySnapshot findReusable(String repository, String sha, int version) { return null; }
                    public SnapshotModel.RepositorySnapshot saveAvailable(SnapshotModel.RepositorySnapshot snapshot) { saved.add(snapshot); return snapshot; }
                }, Clock.fixed(Instant.parse("2026-07-20T00:00:00Z"), ZoneOffset.UTC));
        var result = service.capture(new SnapshotCaptureService.CaptureRequest("org", "repo", 1, 2, "example/repo", "refs/heads/main", "corr", "key"));
        assertEquals(SnapshotModel.Status.AVAILABLE, result.status()); assertEquals(2, stored.size()); assertEquals(1, saved.size()); assertTrue(stagingClosed.get());
        assertThrows(IllegalStateException.class, () -> credential.use(String::new));
    }
}
