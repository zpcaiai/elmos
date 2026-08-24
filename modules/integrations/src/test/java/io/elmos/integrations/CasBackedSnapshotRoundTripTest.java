package io.elmos.integrations;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.cas.CasAccessPolicy;
import io.elmos.cas.CasCatalog;
import io.elmos.cas.InMemoryCasCatalog;
import io.elmos.cas.InMemoryCasStore;
import io.elmos.scm.EphemeralCredential;
import io.elmos.snapshot.DeterministicSnapshotArchiver;
import io.elmos.snapshot.SnapshotCaptureService;
import io.elmos.snapshot.SnapshotMaterializationService;
import io.elmos.snapshot.SnapshotModel;
import io.elmos.snapshot.SnapshotPorts;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CasBackedSnapshotRoundTripTest {

    @TempDir
    Path temporary;

    @Test
    void trustedCaptureContextSurvivesCasStorageAndMaterialization() throws Exception {
        Path source = Files.createDirectories(temporary.resolve("source"));
        Files.writeString(source.resolve("pom.xml"), "<project/>");
        Files.createDirectories(source.resolve("src/main/java"));
        Files.writeString(source.resolve("src/main/java/App.java"), "class App {}");

        var store = new InMemoryCasStore("snapshot-l2");
        var catalog = new InMemoryCasCatalog();
        var artifacts = new CasBackedArtifactStore(
                store, catalog, "cn-east",
                CasAccessPolicy.SecurityTier.CONFIDENTIAL,
                64L * 1024 * 1024, () -> 1_800_000_000_000L);
        var saved = new AtomicReference<SnapshotModel.RepositorySnapshot>();
        SnapshotPorts.SnapshotStore snapshots = new SnapshotPorts.SnapshotStore() {
            @Override
            public SnapshotModel.RepositorySnapshot findReusable(
                    String repositoryId, String commitSha, int schemaVersion
            ) {
                return null;
            }

            @Override
            public SnapshotModel.RepositorySnapshot saveAvailable(
                    SnapshotModel.RepositorySnapshot snapshot
            ) {
                saved.set(snapshot);
                return snapshot;
            }
        };
        var capture = new SnapshotCaptureService(
                (organization, repository, external, installation) ->
                        new EphemeralCredential("short-lived-token".toCharArray()),
                (repository, requestedRef, credential) ->
                        new SnapshotPorts.ResolvedRef("a".repeat(40), "b".repeat(40)),
                (repository, resolvedRef, credential) ->
                        new SnapshotPorts.FetchedSource(source, () -> { }),
                new DeterministicSnapshotArchiver(), artifacts, snapshots,
                Clock.fixed(Instant.parse("2026-08-20T00:00:00Z"), ZoneOffset.UTC));

        SnapshotModel.RepositorySnapshot snapshot = capture.capture(
                new SnapshotCaptureService.CaptureRequest(
                        "org-a", "repo-a", 11, 22, "example/repo",
                        "refs/heads/main", "correlation-1", "idempotency-1"));
        var materializer = new SnapshotMaterializationService(
                temporary.resolve("materialized"), artifacts, new ObjectMapper());
        SnapshotMaterializationService.Materialization materialization =
                materializer.materialize("org-a", snapshot);

        assertEquals(snapshot, saved.get());
        assertEquals("<project/>", Files.readString(temporary.resolve("materialized")
                .resolve(materialization.relativePath()).resolve("pom.xml")));
        var archiveEntry = catalog.find("org-a",
                CasBackedArtifactStore.parse(snapshot.archiveArtifactRef())).orElseThrow();
        var manifestEntry = catalog.find("org-a",
                CasBackedArtifactStore.parse(snapshot.manifestArtifactRef())).orElseThrow();
        assertEquals(2, catalog.activeResourceBindings(
                "org-a", CasCatalog.ResourceKind.REPOSITORY, "repo-a").size());
        assertEquals(2, catalog.activeReferenceRoots("org-a").size());
        assertTrue(catalog.activeReferenceRoots("org-a").stream()
                .allMatch(root -> root.rootId().equals(
                        CasBackedArtifactStore.snapshotRootOwner(
                                new SnapshotPorts.ArtifactResourceContext(
                                        snapshot.organizationId(), snapshot.repositoryId()),
                                snapshot.snapshotId()))));
        assertTrue(store.contains(archiveEntry.digest()));
        assertTrue(store.contains(manifestEntry.digest()));
    }
}
