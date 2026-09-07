package io.elmos.integrations;

import io.elmos.scm.EphemeralCredential;
import io.elmos.snapshot.SnapshotPorts;
import org.eclipse.jgit.api.Git;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class JGitSnapshotSourceAdapterTest {
    @TempDir Path temp;
    @Test void resolvesFetchesExactCommitAndDeletesStaging() throws Exception {
        Path repository = temp.resolve("repository"), staging = temp.resolve("staging"); Files.createDirectories(repository);
        String branch;
        try (Git git = Git.init().setDirectory(repository.toFile()).call()) {
            Files.writeString(repository.resolve("pom.xml"), "<project/>"); git.add().addFilepattern("pom.xml").call();
            git.commit().setMessage("initial").setAuthor("ELMOS", "elmos@example.invalid").call(); branch = git.getRepository().getFullBranch();
        }
        JGitSnapshotSourceAdapter adapter = new JGitSnapshotSourceAdapter(
                (organization, id) -> repository.toUri(), staging);
        var resource = new SnapshotPorts.ArtifactResourceContext("org", "repo");
        try (EphemeralCredential credential = new EphemeralCredential("unused".toCharArray())) {
            var resolved = adapter.resolve(resource, branch, credential);
            assertTrue(resolved.commitSha().matches("[0-9a-f]{40}"));
            Path materialized;
            try (var source = adapter.fetch(resource, resolved, credential)) {
                materialized = source.path(); assertEquals("<project/>", Files.readString(materialized.resolve("pom.xml")));
                assertTrue(source.treeSha().matches("[0-9a-f]{40}"));
            }
            assertFalse(Files.exists(materialized));
        }
    }
    @Test void rejectsRefInjection() {
        JGitSnapshotSourceAdapter adapter = new JGitSnapshotSourceAdapter(
                (organization, id) -> temp.toUri(), temp.resolve("staging"));
        var resource = new SnapshotPorts.ArtifactResourceContext("org", "repo");
        try (EphemeralCredential credential = new EphemeralCredential("unused".toCharArray())) {
            assertThrows(SecurityException.class,
                    () -> adapter.resolve(resource, "--upload-pack=evil", credential));
        }
    }
}
