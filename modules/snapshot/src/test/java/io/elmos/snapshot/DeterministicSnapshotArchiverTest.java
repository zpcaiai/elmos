package io.elmos.snapshot;

import com.github.luben.zstd.ZstdInputStream;
import org.apache.commons.compress.archivers.tar.TarArchiveEntry;
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayInputStream;
import java.io.UncheckedIOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.FileTime;
import java.nio.file.attribute.PosixFilePermission;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeFalse;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

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

    @Test void rejectsLiteralBackslashInArchivePath() throws Exception {
        assumeFalse("\\".equals(FileSystems.getDefault().getSeparator()),
                "backslash is the platform path separator rather than a literal filename character");
        Path source = Files.createDirectory(temp.resolve("backslash-path-source"));
        Files.writeString(source.resolve("literal\\name.txt"), "payload");

        assertThrows(SecurityException.class,
                () -> new DeterministicSnapshotArchiver().archive(source));
    }

    @Test void rejectsLiteralBackslashInSymlinkTarget() throws Exception {
        assumeFalse("\\".equals(FileSystems.getDefault().getSeparator()),
                "backslash is the platform path separator rather than a literal filename character");
        Path source = Files.createDirectory(temp.resolve("backslash-symlink-source"));
        try { Files.createSymbolicLink(source.resolve("link"), Path.of("literal\\target")); }
        catch (UnsupportedOperationException exception) { return; }

        assertThrows(SecurityException.class,
                () -> new DeterministicSnapshotArchiver().archive(source));
    }

    @Test void rejectsSourceBeyondConfiguredLimits(@TempDir Path temp) throws Exception {
        Files.writeString(temp.resolve("large.txt"), "0123456789");
        var archiver = new DeterministicSnapshotArchiver(new DeterministicSnapshotArchiver.Limits(10, 5, 8, 16));
        assertThrows(SecurityException.class, () -> archiver.archive(temp));
    }

    @Test void skipsExcludedDirectorySubtreesBeforeTheirChildrenConsumeTheVisitBudget() throws Exception {
        Path source = Files.createDirectory(temp.resolve("excluded-subtree-source"));
        Path git = Files.createDirectory(source.resolve(".git"));
        for (int index = 0; index < 20; index++) {
            Files.writeString(git.resolve("untrusted-" + index), "ignored");
        }
        Files.writeString(source.resolve("included.txt"), "included");

        var archiver = new DeterministicSnapshotArchiver(
                new DeterministicSnapshotArchiver.Limits(2, 1, 64, 64));
        var snapshot = archiver.archive(source);

        assertEquals(1, snapshot.sourceFiles());
        String manifest = new String(snapshot.manifest());
        assertTrue(manifest.contains("included.txt"));
        assertFalse(manifest.contains("untrusted-"));
    }

    @Test void countsEveryVisitedNodeIncludingExcludedFiles() throws Exception {
        Path source = Files.createDirectory(temp.resolve("visited-node-source"));
        Files.writeString(source.resolve("included.txt"), "included");
        Files.writeString(source.resolve("elmos-secret-one"), "ignored");
        Files.writeString(source.resolve("elmos-secret-two"), "ignored");
        var archiver = new DeterministicSnapshotArchiver(
                new DeterministicSnapshotArchiver.Limits(2, 1, 64, 64));

        assertThrows(SecurityException.class, () -> archiver.archive(source));
    }

    @Test void rejectsFileChangedAfterItsStableChannelRead() throws Exception {
        Path source = Files.createDirectory(temp.resolve("toctou-source"));
        Path payload = source.resolve("payload.txt");
        Files.writeString(payload, "original");
        var archiver = new DeterministicSnapshotArchiver(
                new DeterministicSnapshotArchiver.Limits(10, 5, 64, 64),
                path -> {
                    try {
                        Files.writeString(path, "changed-after-read");
                    } catch (java.io.IOException exception) {
                        throw new UncheckedIOException(exception);
                    }
                });

        assertThrows(SecurityException.class, () -> archiver.archive(source));
    }

    @Test void rejectsNestedDirectoryChangedAfterDiscovery() throws Exception {
        Path source = Files.createDirectory(temp.resolve("directory-toctou-source"));
        Path nested = Files.createDirectory(source.resolve("nested"));
        Files.writeString(nested.resolve("payload.txt"), "original");
        var archiver = new DeterministicSnapshotArchiver(
                new DeterministicSnapshotArchiver.Limits(10, 5, 64, 64),
                path -> {
                    try {
                        Files.writeString(path.getParent().resolve("late-file.txt"), "late");
                    } catch (java.io.IOException exception) {
                        throw new UncheckedIOException(exception);
                    }
                });

        assertThrows(SecurityException.class, () -> archiver.archive(source));
    }

    @Test void recordsGitLfsPointerFromTheVerifiedFileContent() throws Exception {
        Path source = Files.createDirectory(temp.resolve("lfs-source"));
        Files.writeString(source.resolve("artifact.bin"), """
                version https://git-lfs.github.com/spec/v1
                oid sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
                size 123
                """);

        var snapshot = new DeterministicSnapshotArchiver().archive(source);

        assertTrue(new String(snapshot.manifest())
                .contains("\"gitLfsPointers\":[\"artifact.bin\"]"));
    }

    @Test void pathnameSwapAndRestoreCannotSubstituteBytesForTheAnchoredInode() throws Exception {
        Path source = Files.createDirectory(temp.resolve("swap-restore-source"));
        Path payload = source.resolve("payload.txt");
        Path displaced = temp.resolve("displaced-payload.txt");
        Path hostile = temp.resolve("hostile-payload.txt");
        Files.writeString(payload, "trusted");
        Files.writeString(hostile, "hostile");
        FileTime sourceMtime = Files.getLastModifiedTime(
                source, LinkOption.NOFOLLOW_LINKS);
        var probe = new DeterministicSnapshotArchiver.FileReadProbe() {
            @Override public void beforeAnchoredRead(Path path) {
                if (!path.equals(payload)) return;
                try {
                    Files.move(path, displaced, StandardCopyOption.ATOMIC_MOVE);
                    Files.move(hostile, path, StandardCopyOption.ATOMIC_MOVE);
                } catch (java.io.IOException exception) {
                    throw new UncheckedIOException(exception);
                }
            }

            @Override public void afterRead(Path path) {
                if (!path.equals(payload)) return;
                try {
                    Files.move(path, hostile, StandardCopyOption.ATOMIC_MOVE);
                    Files.move(displaced, path, StandardCopyOption.ATOMIC_MOVE);
                    Files.setLastModifiedTime(source, sourceMtime);
                } catch (java.io.IOException exception) {
                    throw new UncheckedIOException(exception);
                }
            }
        };
        var archiver = new DeterministicSnapshotArchiver(
                new DeterministicSnapshotArchiver.Limits(10, 5, 64, 64), probe);

        var snapshot = archiver.archive(source);

        String manifest = new String(snapshot.manifest(), StandardCharsets.UTF_8);
        assertTrue(manifest.contains(sha256("trusted")));
        assertFalse(manifest.contains(sha256("hostile")));
        assertEquals("trusted", Files.readString(payload));
        assertEquals(DeterministicSnapshotArchiver.SourceAssurance.LOCAL_SELF_ATTESTED,
                snapshot.sourceAssurance());
    }

    @Test void symlinkSwapAndRestoreCannotSubstituteTheAnchoredLinkTarget() throws Exception {
        Path source = Files.createDirectory(temp.resolve("symlink-swap-source"));
        Path link = source.resolve("link");
        Path displaced = temp.resolve("displaced-link");
        Path hostile = temp.resolve("hostile-link");
        try {
            Files.createSymbolicLink(link, Path.of("target-a"));
            Files.createSymbolicLink(hostile, Path.of("target-b"));
        } catch (UnsupportedOperationException exception) {
            return;
        }
        assumeTrue(supportsSymlinkHardLink(temp, link),
                "filesystem cannot create a stable hard-link anchor for a symlink inode");
        FileTime sourceMtime = Files.getLastModifiedTime(
                source, LinkOption.NOFOLLOW_LINKS);
        var probe = new DeterministicSnapshotArchiver.FileReadProbe() {
            @Override public void beforeAnchoredRead(Path path) {
                if (!path.equals(link)) return;
                try {
                    Files.move(path, displaced, StandardCopyOption.ATOMIC_MOVE);
                    Files.move(hostile, path, StandardCopyOption.ATOMIC_MOVE);
                } catch (java.io.IOException exception) {
                    throw new UncheckedIOException(exception);
                }
            }

            @Override public void afterRead(Path path) {
                if (!path.equals(link)) return;
                try {
                    Files.move(path, hostile, StandardCopyOption.ATOMIC_MOVE);
                    Files.move(displaced, path, StandardCopyOption.ATOMIC_MOVE);
                    Files.setLastModifiedTime(source, sourceMtime);
                } catch (java.io.IOException exception) {
                    throw new UncheckedIOException(exception);
                }
            }
        };
        var archiver = new DeterministicSnapshotArchiver(
                new DeterministicSnapshotArchiver.Limits(10, 5, 64, 64), probe);

        var snapshot = archiver.archive(source);

        String manifest = new String(snapshot.manifest(), StandardCharsets.UTF_8);
        assertTrue(manifest.contains("\"linkTarget\":\"target-a\""));
        assertFalse(manifest.contains("\"linkTarget\":\"target-b\""));
        assertEquals(Path.of("target-a"), Files.readSymbolicLink(link));
    }

    @Test void filesystemWithoutStableDirectoryFileKeysFailsClosed() throws Exception {
        Path zip = temp.resolve("no-file-key.zip");
        URI uri = URI.create("jar:" + zip.toUri());
        try (FileSystem fileSystem = FileSystems.newFileSystem(
                uri, Map.of("create", "true"))) {
            Path source = Files.createDirectory(fileSystem.getPath("/source"));
            Files.writeString(source.resolve("payload.txt"), "payload");
            assumeTrue(Files.readAttributes(source,
                            java.nio.file.attribute.BasicFileAttributes.class,
                            LinkOption.NOFOLLOW_LINKS).fileKey() == null,
                    "provider unexpectedly supplies stable directory file keys");

            assertThrows(SecurityException.class,
                    () -> new DeterministicSnapshotArchiver().archive(source));
        }
    }

    @Test void productionEntryPointRequiresAndRevalidatesAuthoritativeLease() throws Exception {
        Path source = Files.createDirectory(temp.resolve("leased-source"));
        Files.writeString(source.resolve("payload.txt"), "payload");
        var context = new DeterministicSnapshotArchiver.SnapshotContext(
                "GITHUB", "repository-a", "org/repository-a", "main",
                "1".repeat(40), "tree-a");
        AtomicInteger validations = new AtomicInteger();
        DeterministicSnapshotArchiver.SourceLease lease = root -> {
            validations.incrementAndGet();
            return new DeterministicSnapshotArchiver.SourceLeaseReceipt(
                    root, "checkout-lease-a", 42,
                    DeterministicSnapshotArchiver.SourceAssurance.AUTHORITATIVE_LEASE);
        };

        var snapshot = new DeterministicSnapshotArchiver().archive(
                source, context, lease);

        assertEquals(2, validations.get());
        assertEquals(DeterministicSnapshotArchiver.SourceAssurance.AUTHORITATIVE_LEASE,
                snapshot.sourceAssurance());

        DeterministicSnapshotArchiver.SourceLease localClaim = root ->
                new DeterministicSnapshotArchiver.SourceLeaseReceipt(
                        root, "not-authoritative", 0,
                        DeterministicSnapshotArchiver.SourceAssurance.LOCAL_SELF_ATTESTED);
        assertThrows(SecurityException.class,
                () -> new DeterministicSnapshotArchiver().archive(
                        source, context, localClaim));
    }

    @Test void changedSourceLeaseFenceFailsAfterReading() throws Exception {
        Path source = Files.createDirectory(temp.resolve("changing-lease-source"));
        Files.writeString(source.resolve("payload.txt"), "payload");
        var context = new DeterministicSnapshotArchiver.SnapshotContext(
                "GITHUB", "repository-a", "org/repository-a", "main",
                "1".repeat(40), "tree-a");
        AtomicInteger fence = new AtomicInteger(7);
        DeterministicSnapshotArchiver.SourceLease changing = root ->
                new DeterministicSnapshotArchiver.SourceLeaseReceipt(
                        root, "checkout-lease-a", fence.getAndIncrement(),
                        DeterministicSnapshotArchiver.SourceAssurance.AUTHORITATIVE_LEASE);

        assertThrows(SecurityException.class,
                () -> new DeterministicSnapshotArchiver().archive(
                        source, context, changing));
    }

    @Test void producerLimitsCloseMaterializerPathEntryAndMetadataBoundaries() {
        assertThrows(IllegalArgumentException.class,
                () -> new DeterministicSnapshotArchiver.Limits(
                        100_001, 1, 1, 1));
        assertThrows(IllegalArgumentException.class,
                () -> new DeterministicSnapshotArchiver.Limits(
                        1, 1, 1, 256L * 1024 * 1024 + 1));
        Path overlongUtf8 = Path.of(String.join("/",
                java.util.Collections.nCopies(180, "界".repeat(10))));
        assertThrows(SecurityException.class,
                () -> DeterministicSnapshotArchiver.portable(overlongUtf8));

        var budget = new DeterministicSnapshotArchiver.ArchiveMetadataBudget(1536);
        budget.reserve("short", null);
        assertEquals(1536, budget.used());
        assertThrows(SecurityException.class,
                () -> budget.reserve("another", null));
    }

    @Test void emittedTarHeadersMatchTheExactCanonicalProfile() throws Exception {
        Path source = Files.createDirectory(temp.resolve("canonical-tar-source"));
        Path bin = Files.createDirectory(source.resolve("bin"));
        Path executable = bin.resolve("run.sh");
        Files.writeString(executable, "#!/bin/sh\nexit 0\n");
        try {
            Files.setPosixFilePermissions(executable, Set.of(
                    PosixFilePermission.OWNER_READ,
                    PosixFilePermission.OWNER_WRITE,
                    PosixFilePermission.OWNER_EXECUTE));
        } catch (UnsupportedOperationException exception) {
            return;
        }
        assumeTrue(Files.isExecutable(executable));

        var snapshot = new DeterministicSnapshotArchiver().archive(source);
        List<TarHeader> headers = readHeaders(snapshot.archive());

        assertEquals(List.of("bin/", "bin/run.sh"),
                headers.stream().map(TarHeader::name).toList());
        assertEquals(new TarHeader("bin/", "directory", 0755, 0,
                        10001, 10001, "elmos", "elmos", 0),
                headers.get(0));
        assertEquals(new TarHeader("bin/run.sh", "file", 0755,
                        Files.size(executable), 10001, 10001,
                        "elmos", "elmos", 0),
                headers.get(1));
    }

    @Test void emittedSymlinkHeaderMatchesTheExactCanonicalProfile() throws Exception {
        Path source = Files.createDirectory(temp.resolve("canonical-symlink-source"));
        Path target = source.resolve("target.txt");
        Path link = source.resolve("link");
        Files.writeString(target, "payload");
        try {
            Files.createSymbolicLink(link, Path.of("target.txt"));
        } catch (UnsupportedOperationException exception) {
            return;
        }
        assumeTrue(supportsSymlinkHardLink(temp, link),
                "filesystem cannot create a stable hard-link anchor for a symlink inode");

        var snapshot = new DeterministicSnapshotArchiver().archive(source);
        List<TarHeader> headers = readHeaders(snapshot.archive());

        assertEquals(List.of("link", "target.txt"),
                headers.stream().map(TarHeader::name).toList());
        assertEquals(new TarHeader("link", "symlink", 0777, 0,
                        10001, 10001, "elmos", "elmos", 0),
                headers.get(0));
    }

    private static boolean supportsSymlinkHardLink(Path temporary, Path link) throws Exception {
        Path probe = temporary.resolve("symlink-hardlink-probe");
        try {
            Files.createLink(probe, link);
            return Files.isSymbolicLink(probe);
        } catch (UnsupportedOperationException | java.io.IOException unsupported) {
            return false;
        } finally {
            Files.deleteIfExists(probe);
        }
    }

    private static String sha256(String value) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8)));
    }

    private static List<TarHeader> readHeaders(byte[] archive) throws Exception {
        List<TarHeader> headers = new ArrayList<>();
        try (ZstdInputStream zstd = new ZstdInputStream(new ByteArrayInputStream(archive));
             TarArchiveInputStream tar = new TarArchiveInputStream(
                     zstd, StandardCharsets.UTF_8.name())) {
            TarArchiveEntry entry;
            while ((entry = tar.getNextEntry()) != null) {
                String type = entry.isDirectory() ? "directory"
                        : entry.isSymbolicLink() ? "symlink"
                        : entry.isFile() ? "file" : "unsupported";
                headers.add(new TarHeader(entry.getName(), type, entry.getMode(),
                        entry.getSize(), entry.getLongUserId(), entry.getLongGroupId(),
                        entry.getUserName(), entry.getGroupName(),
                        entry.getModTime().getTime()));
            }
        }
        return List.copyOf(headers);
    }

    private record TarHeader(
            String name,
            String type,
            int mode,
            long size,
            long uid,
            long gid,
            String user,
            String group,
            long mtime
    ) {
    }
}
