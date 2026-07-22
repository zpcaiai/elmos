package io.elmos.snapshot;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class DeterministicSnapshotArchiverTest {
    @TempDir Path temp;

    @Test void createsStableArchiveAndExcludesGitAndSecrets() throws Exception {
        Path source = Files.createDirectory(temp.resolve("source"));
        Files.writeString(source.resolve("pom.xml"), "<project/>");
        Files.createDirectories(source.resolve("src")); Files.writeString(source.resolve("src/App.java"), "class App {}");
        Files.createDirectories(source.resolve(".git")); Files.writeString(source.resolve(".git/config"), "token=secret");
        Files.writeString(source.resolve(".env"), "TOKEN=secret");
        DeterministicSnapshotArchiver archiver = new DeterministicSnapshotArchiver();
        var first = archiver.archive(source); Thread.sleep(5); var second = archiver.archive(source);
        assertEquals(first.archiveSha256(), second.archiveSha256());
        assertArrayEquals(first.archive(), second.archive());
        String manifest = new String(first.manifest());
        assertTrue(manifest.contains("pom.xml")); assertFalse(manifest.contains(".git")); assertFalse(manifest.contains(".env"));
        assertEquals(2, first.sourceFiles());
    }

    @Test void rejectsEscapingSymlink() throws Exception {
        Path source = Files.createDirectory(temp.resolve("source"));
        Files.writeString(temp.resolve("outside"), "private");
        try { Files.createSymbolicLink(source.resolve("escape"), Path.of("../outside")); }
        catch (UnsupportedOperationException exception) { return; }
        assertThrows(SecurityException.class, () -> new DeterministicSnapshotArchiver().archive(source));
    }

    @Test void rejectsSourceBeyondConfiguredLimits(@TempDir Path temp) throws Exception {
        Files.writeString(temp.resolve("large.txt"), "0123456789");
        var archiver = new DeterministicSnapshotArchiver(new DeterministicSnapshotArchiver.Limits(10, 5, 8, 16));
        assertThrows(SecurityException.class, () -> archiver.archive(temp));
    }
}
