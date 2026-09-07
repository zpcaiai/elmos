package io.elmos.snapshot;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SnapshotMaterializationServiceTest {
    @TempDir Path temporary;

    @Test void materializesDigestBoundReadOnlySnapshotIdempotently() throws Exception {
        Path source = Files.createDirectories(temporary.resolve("source"));
        Files.writeString(source.resolve("pom.xml"), "<project/>");
        Files.createDirectories(source.resolve("src/main/java"));
        Files.writeString(source.resolve("src/main/java/App.java"), "class App {}");

        var context = new DeterministicSnapshotArchiver.SnapshotContext(
                "GITHUB", "repo-1", "example/repo", "refs/heads/main",
                "a".repeat(40), "b".repeat(40));
        var archive = new DeterministicSnapshotArchiver().archive(source, context);
        Map<String, byte[]> content = new HashMap<>();
        content.put("archive", archive.archive());
        content.put("manifest", archive.manifest());
        SnapshotPorts.ArtifactReader reader = (resource, reference) ->
                new ByteArrayInputStream(content.get(reference));
        var snapshot = snapshot(archive);
        var service = new SnapshotMaterializationService(
                temporary.resolve("materialized"), reader, new ObjectMapper());

        var first = service.materialize("org-a", snapshot);
        var second = service.materialize("org-a", snapshot);

        assertEquals(first, second);
        Path output = temporary.resolve("materialized").resolve(first.relativePath());
        assertEquals("<project/>", Files.readString(output.resolve("pom.xml")));
        assertTrue(Files.isRegularFile(output.resolve(".elmos/materialization.json")));
        assertThrows(SecurityException.class, () -> service.materialize("org-b", snapshot));
    }

    @Test void rejectsTamperedArchiveAndUnauthorizedSpecialContent() throws Exception {
        Path source = Files.createDirectories(temporary.resolve("tampered-source"));
        Files.writeString(source.resolve("pom.xml"), "<project/>");
        var context = new DeterministicSnapshotArchiver.SnapshotContext(
                "GITHUB", "repo-1", "example/repo", "refs/heads/main",
                "a".repeat(40), "b".repeat(40));
        var archive = new DeterministicSnapshotArchiver().archive(source, context);
        byte[] tampered = archive.archive();
        tampered[tampered.length - 1] ^= 1;
        SnapshotPorts.ArtifactReader tamperedReader = (resource, reference) ->
                new ByteArrayInputStream("archive".equals(reference)
                        ? tampered : archive.manifest());
        var service = new SnapshotMaterializationService(
                temporary.resolve("tampered-materialized"),
                tamperedReader,
                new ObjectMapper());
        assertThrows(RuntimeException.class, () -> service.materialize(
                "org-a", snapshot(archive)));

        Path submoduleSource = Files.createDirectories(
                temporary.resolve("submodule-source"));
        Files.writeString(submoduleSource.resolve("pom.xml"), "<project/>");
        Files.writeString(submoduleSource.resolve(".gitmodules"),
                "[submodule \"private\"]\npath=private\nurl=https://github.com/example/private");
        var submoduleArchive = new DeterministicSnapshotArchiver()
                .archive(submoduleSource, context);
        Map<String, byte[]> submoduleContent = Map.of(
                "archive", submoduleArchive.archive(),
                "manifest", submoduleArchive.manifest());
        var submoduleService = new SnapshotMaterializationService(
                temporary.resolve("submodule-materialized"),
                (resource, reference) -> new ByteArrayInputStream(submoduleContent.get(reference)),
                new ObjectMapper());
        SecurityException rejection = assertThrows(SecurityException.class,
                () -> submoduleService.materialize(
                        "org-a", snapshot(submoduleArchive)));
        assertTrue(rejection.getMessage().contains("submodules"));
    }

    private static SnapshotModel.RepositorySnapshot snapshot(
            DeterministicSnapshotArchiver.SnapshotArchive archive
    ) {
        return new SnapshotModel.RepositorySnapshot(
                "snapshot-1",
                "org-a",
                "repo-1",
                "refs/heads/main",
                "a".repeat(40),
                "b".repeat(40),
                "archive",
                archive.archiveSha256(),
                archive.archive().length,
                "manifest",
                archive.manifestSha256(),
                1,
                SnapshotModel.Status.AVAILABLE,
                Instant.parse("2026-07-26T00:00:00Z")
        );
    }
}
