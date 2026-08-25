package io.elmos.workspaceservice;

import io.elmos.workspace.WorkspaceInfrastructurePorts;
import io.elmos.workspace.WorkspaceModels;
import com.github.dockerjava.api.command.CreateContainerCmd;
import com.github.luben.zstd.ZstdInputStream;
import com.github.luben.zstd.ZstdOutputStream;
import org.apache.commons.compress.archivers.tar.TarArchiveEntry;
import org.apache.commons.compress.archivers.tar.TarArchiveOutputStream;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Answers.RETURNS_SELF;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class DockerSnapshotVolumeMaterializerTest {

    private static final byte[] CONTENT =
            "compressed snapshot archive".getBytes(StandardCharsets.UTF_8);
    private static final String SHA256 = sha256(CONTENT);

    @Test
    void resolvedArtifactMustMatchAuthenticatedWorkspaceBinding() {
        WorkspaceInfrastructurePorts.SnapshotArtifact artifact = artifact(
                "tenant-a", "run-a", "snapshot-a");
        assertEquals(artifact,
                DockerSnapshotVolumeMaterializer.requireBoundArtifact(request(), artifact));

        assertThrows(SecurityException.class,
                () -> DockerSnapshotVolumeMaterializer.requireBoundArtifact(
                        request(), artifact("tenant-b", "run-a", "snapshot-a")));
        assertThrows(SecurityException.class,
                () -> DockerSnapshotVolumeMaterializer.requireBoundArtifact(
                        request(), artifact("tenant-a", "run-b", "snapshot-a")));
        assertThrows(SecurityException.class,
                () -> DockerSnapshotVolumeMaterializer.requireBoundArtifact(
                        request(), artifact("tenant-a", "run-a", "snapshot-b")));
    }

    @Test
    void archiveStreamRequiresExactDigestAndSize() throws Exception {
        var verified = new DockerSnapshotVolumeMaterializer.VerifyingArchiveInputStream(
                new ByteArrayInputStream(CONTENT), SHA256, CONTENT.length);
        verified.readAllBytes();
        verified.requireComplete();

        var wrongDigest = new DockerSnapshotVolumeMaterializer.VerifyingArchiveInputStream(
                new ByteArrayInputStream(CONTENT), "f".repeat(64), CONTENT.length);
        wrongDigest.readAllBytes();
        assertThrows(SecurityException.class, wrongDigest::requireComplete);

        var shortStream = new DockerSnapshotVolumeMaterializer.VerifyingArchiveInputStream(
                new ByteArrayInputStream(CONTENT), SHA256, CONTENT.length + 1L);
        shortStream.readAllBytes();
        assertThrows(SecurityException.class, shortStream::requireComplete);
    }

    @Test
    void archiveStreamRejectsBytesBeyondDeclaredSizeDuringRead() {
        var oversized = new DockerSnapshotVolumeMaterializer.VerifyingArchiveInputStream(
                new ByteArrayInputStream(CONTENT), SHA256, CONTENT.length - 1L);
        assertThrows(SecurityException.class, oversized::readAllBytes);
    }

    @Test
    void helperLifetimeDoesNotExpireAtTheOldSixtySecondBoundaryAndIsCleanupBound() {
        WorkspaceModels.WorkspaceRequest request = request();
        WorkspaceInfrastructurePorts.SnapshotArtifact artifact = artifact(
                "tenant-a", "run-a", "snapshot-a");

        assertNotEquals("60", DockerSnapshotVolumeMaterializer.MATERIALIZER_IDLE_SECONDS);
        assertEquals("workspace-a",
                DockerSnapshotVolumeMaterializer.helperLabels(request, artifact)
                        .get("elmos.workspace_id"));
        assertEquals("snapshot-materializer",
                DockerSnapshotVolumeMaterializer.helperLabels(request, artifact)
                        .get("elmos.resource_role"));
    }

    @Test
    void helperAlwaysOverridesImageEntrypointAndCommand() {
        CreateContainerCmd command = mock(CreateContainerCmd.class, RETURNS_SELF);

        assertSame(command,
                DockerSnapshotVolumeMaterializer.configureHelperProcess(command));

        verify(command).withEntrypoint(
                DockerSnapshotVolumeMaterializer.MATERIALIZER_ENTRYPOINT);
        verify(command).withCmd(
                DockerSnapshotVolumeMaterializer.MATERIALIZER_IDLE_SECONDS);
    }

    @Test
    void archivePreflightBoundsExpansionAndRejectsTraversal() throws Exception {
        byte[] safe = archive("source/Main.java", "class Main {}".getBytes(StandardCharsets.UTF_8));
        var inventory = DockerSnapshotVolumeMaterializer.inspectArchive(
                new ByteArrayInputStream(safe), sha256(safe), safe.length, 1024);
        assertEquals(1, inventory.entryCount());
        assertEquals(13, inventory.expandedBytes());

        byte[] traversal = archive("../escape", new byte[]{1});
        assertThrows(SecurityException.class,
                () -> DockerSnapshotVolumeMaterializer.inspectArchive(
                        new ByteArrayInputStream(traversal), sha256(traversal),
                        traversal.length, 1024));

        byte[] expanded = archive("large.bin", new byte[2048]);
        assertThrows(SecurityException.class,
                () -> DockerSnapshotVolumeMaterializer.inspectArchive(
                        new ByteArrayInputStream(expanded), sha256(expanded),
                        expanded.length, 1024));
    }

    @Test
    void archivePreflightAcceptsOnlyRootContainedProducerSymlinks() throws Exception {
        byte[] contained = symlinkArchive("source/current", "Main.java", false);
        var inventory = DockerSnapshotVolumeMaterializer.inspectArchive(
                new ByteArrayInputStream(contained), sha256(contained), contained.length, 1024);
        assertEquals(1, inventory.entryCount());
        assertEquals(0, inventory.expandedBytes());

        byte[] escaping = symlinkArchive("source/current", "../../outside", false);
        assertThrows(SecurityException.class,
                () -> DockerSnapshotVolumeMaterializer.inspectArchive(
                        new ByteArrayInputStream(escaping), sha256(escaping),
                        escaping.length, 1024));

        byte[] hardLink = symlinkArchive("source/current", "source/Main.java", true);
        assertThrows(SecurityException.class,
                () -> DockerSnapshotVolumeMaterializer.inspectArchive(
                        new ByteArrayInputStream(hardLink), sha256(hardLink),
                        hardLink.length, 1024));
    }

    @Test
    void mutableLegacyReaderIsOpenedOnceAndEveryUseReadsTheVerifiedSpool() throws Exception {
        byte[] verifiedArchive = archive(
                "source/Main.java", "class Main {}".getBytes(StandardCharsets.UTF_8));
        byte[] replacementArchive = archive("../replacement", new byte[]{1});
        WorkspaceInfrastructurePorts.SnapshotArtifact fixedArtifact =
                artifactFor(verifiedArchive);
        AtomicInteger opens = new AtomicInteger();
        WorkspaceInfrastructurePorts.SnapshotArtifactReader mutableReader = ignored ->
                new ByteArrayInputStream(opens.getAndIncrement() == 0
                        ? verifiedArchive : replacementArchive);

        try (DockerSnapshotVolumeMaterializer.SnapshotSpool spool =
                     DockerSnapshotVolumeMaterializer.spoolArchive(
                             mutableReader, fixedArtifact, verifiedArchive.length)) {
            try (var preflight = spool.open()) {
                var inventory = DockerSnapshotVolumeMaterializer.inspectArchive(
                        preflight, fixedArtifact.sha256(), fixedArtifact.sizeBytes(), 1024);
                assertEquals(1, inventory.entryCount());
            }
            try (var snapshotCopy = spool.open(); var workspaceCopy = spool.open()) {
                assertArrayEquals(verifiedArchive, snapshotCopy.readAllBytes());
                assertArrayEquals(verifiedArchive, workspaceCopy.readAllBytes());
            }
        }

        assertEquals(1, opens.get(),
                "preflight and both copies must not reopen a mutable artifact source");
    }

    @Test
    void spoolReadersStayBoundToTheCreatedInodeAcrossAPathSwap() throws Exception {
        byte[] verifiedArchive = archive(
                "source/Main.java", "class Main {}".getBytes(StandardCharsets.UTF_8));
        byte[] replacementArchive = archive("replacement.txt", new byte[]{9, 8, 7});
        WorkspaceInfrastructurePorts.SnapshotArtifact fixedArtifact =
                artifactFor(verifiedArchive);

        try (DockerSnapshotVolumeMaterializer.SnapshotSpool spool =
                     DockerSnapshotVolumeMaterializer.spoolArchive(
                             ignored -> new ByteArrayInputStream(verifiedArchive),
                             fixedArtifact,
                             verifiedArchive.length)) {
            Path spoolPath = spoolPath(spool);
            Path originalInode = spoolPath.resolveSibling("captured-original.tar.zst");
            Files.move(spoolPath, originalInode);
            Files.write(spoolPath, replacementArchive);
            try {
                try (DockerSnapshotVolumeMaterializer.VerifyingArchiveInputStream input =
                             spool.openVerified()) {
                    assertArrayEquals(verifiedArchive, input.readAllBytes());
                    input.requireComplete();
                }
            } finally {
                Files.deleteIfExists(spoolPath);
                Files.move(originalInode, spoolPath);
            }
        }
    }

    @Test
    void everyVerifiedSpoolReadRejectsInPlaceMutationOfTheRetainedInode() throws Exception {
        byte[] verifiedArchive = archive(
                "source/Main.java", "class Main {}".getBytes(StandardCharsets.UTF_8));
        WorkspaceInfrastructurePorts.SnapshotArtifact fixedArtifact =
                artifactFor(verifiedArchive);

        try (DockerSnapshotVolumeMaterializer.SnapshotSpool spool =
                     DockerSnapshotVolumeMaterializer.spoolArchive(
                             ignored -> new ByteArrayInputStream(verifiedArchive),
                             fixedArtifact,
                             verifiedArchive.length)) {
            Path spoolPath = spoolPath(spool);
            Files.setPosixFilePermissions(spoolPath, Set.of(
                    PosixFilePermission.OWNER_READ,
                    PosixFilePermission.OWNER_WRITE));
            byte[] tampered = verifiedArchive.clone();
            tampered[tampered.length / 2] ^= 1;
            Files.write(spoolPath, tampered);

            try (DockerSnapshotVolumeMaterializer.VerifyingArchiveInputStream input =
                         spool.openVerified()) {
                input.readAllBytes();
                assertThrows(SecurityException.class, input::requireComplete);
            }
        }
    }

    @Test
    void symlinkTopologyIsRejectedInEitherArchiveOrder() throws Exception {
        byte[] symlinkFirst = symlinkAndDescendantArchive(true);
        byte[] descendantFirst = symlinkAndDescendantArchive(false);

        assertThrows(SecurityException.class,
                () -> DockerSnapshotVolumeMaterializer.inspectArchive(
                        new ByteArrayInputStream(symlinkFirst), sha256(symlinkFirst),
                        symlinkFirst.length, 1024));
        assertThrows(SecurityException.class,
                () -> DockerSnapshotVolumeMaterializer.inspectArchive(
                        new ByteArrayInputStream(descendantFirst), sha256(descendantFirst),
                        descendantFirst.length, 1024));
    }

    @Test
    void onlyCanonicalProducerHeadersAndPosixPathPaxAreAccepted() throws Exception {
        byte[] canonicalPax = longPathArchive(120);
        var accepted = DockerSnapshotVolumeMaterializer.inspectArchive(
                new ByteArrayInputStream(canonicalPax), sha256(canonicalPax),
                canonicalPax.length, 1024);
        assertEquals(1, accepted.entryCount());
        byte[] canonicalShortUnicodePax = unicodePathArchive();
        var unicodeAccepted = DockerSnapshotVolumeMaterializer.inspectArchive(
                new ByteArrayInputStream(canonicalShortUnicodePax),
                sha256(canonicalShortUnicodePax),
                canonicalShortUnicodePax.length, 1024);
        assertEquals(1, unicodeAccepted.entryCount(),
                "the consumer must accept the producer's canonical short non-ASCII PAX path");

        byte[] nonCanonicalMode = archiveWithMetadata(
                "source/Main.java", 0666, 0, Map.of());
        byte[] nonCanonicalTime = archiveWithMetadata(
                "source/Main.java", 0644, 1_000, Map.of());
        byte[] consumedPaxMetadata = archiveWithMetadata(
                "source/Main.java", 0644, 0,
                Map.of("SCHILY.xattr.user.untrusted", "present"));
        byte[] gnuLongName = longPathArchive(
                120, TarArchiveOutputStream.LONGFILE_GNU);

        assertRejectedArchive(nonCanonicalMode, "non-canonical mode");
        assertRejectedArchive(nonCanonicalTime, "non-canonical timestamp");
        assertRejectedArchive(consumedPaxMetadata, "non-path PAX metadata");
        assertRejectedArchive(gnuLongName, "GNU long-name extension");
    }

    private static void assertRejectedArchive(byte[] archive, String description) {
        assertThrows(SecurityException.class,
                () -> DockerSnapshotVolumeMaterializer.inspectArchive(
                        new ByteArrayInputStream(archive), sha256(archive),
                        archive.length, 1024), description);
    }

    @Test
    void zstdExpansionIsBoundedBeforeTheTarParser() throws Exception {
        byte[] compressed = zstd(new byte[2048]);
        try (ZstdInputStream zstd = new ZstdInputStream(
                new ByteArrayInputStream(compressed));
             DockerSnapshotVolumeMaterializer.BoundedExpandedInputStream bounded =
                     new DockerSnapshotVolumeMaterializer.BoundedExpandedInputStream(zstd, 1024)) {
            assertThrows(SecurityException.class, bounded::readAllBytes);
        }
    }

    @Test
    void oversizedPerEntryMetadataIsRejectedBeforeEntryExtraction() throws Exception {
        byte[] bomb = longPathArchive(
                Math.toIntExact(
                        DockerSnapshotVolumeMaterializer.MAX_TAR_ENTRY_HEADER_BYTES + 4096));

        SecurityException rejected = assertThrows(SecurityException.class,
                () -> DockerSnapshotVolumeMaterializer.inspectArchive(
                        new ByteArrayInputStream(bomb), sha256(bomb), bomb.length, 1024));

        assertEquals("snapshot archive per-entry metadata limit exceeded",
                rejected.getMessage());
    }

    private static WorkspaceInfrastructurePorts.SnapshotArtifact artifact(
            String organizationId,
            String migrationRunId,
            String snapshotId
    ) {
        return new WorkspaceInfrastructurePorts.SnapshotArtifact(
                organizationId, "repo-a", migrationRunId, snapshotId,
                "cas://sha256/" + SHA256 + "/" + CONTENT.length,
                SHA256, CONTENT.length);
    }

    private static WorkspaceInfrastructurePorts.SnapshotArtifact artifactFor(byte[] bytes) {
        String digest = sha256(bytes);
        return new WorkspaceInfrastructurePorts.SnapshotArtifact(
                "tenant-a", "repo-a", "run-a", "snapshot-a",
                "cas://sha256/" + digest + "/" + bytes.length,
                digest, bytes.length);
    }

    private static WorkspaceModels.WorkspaceRequest request() {
        return new WorkspaceModels.WorkspaceRequest(
                "workspace-a", "tenant-a", "run-a", "snapshot-a", "java-21",
                "sha256:" + "b".repeat(64),
                new WorkspaceModels.ResourceLimits(
                        1, 1024, 64, 2048, Duration.ofMinutes(30)),
                "network-a", "correlation-a");
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (Exception unavailable) {
            throw new IllegalStateException(unavailable);
        }
    }

    private static byte[] archive(String path, byte[] content) throws Exception {
        ByteArrayOutputStream encoded = new ByteArrayOutputStream();
        try (ZstdOutputStream zstd = new ZstdOutputStream(encoded);
             TarArchiveOutputStream tar = new TarArchiveOutputStream(zstd)) {
            TarArchiveEntry entry = new TarArchiveEntry(path);
            entry.setSize(content.length);
            entry.setMode(0644);
            canonicalOwnership(entry);
            tar.putArchiveEntry(entry);
            tar.write(content);
            tar.closeArchiveEntry();
            tar.finish();
        }
        return encoded.toByteArray();
    }

    private static byte[] symlinkArchive(
            String path, String target, boolean hardLink
    ) throws Exception {
        ByteArrayOutputStream encoded = new ByteArrayOutputStream();
        try (ZstdOutputStream zstd = new ZstdOutputStream(encoded);
             TarArchiveOutputStream tar = new TarArchiveOutputStream(zstd)) {
            TarArchiveEntry entry = new TarArchiveEntry(
                    path, hardLink ? TarArchiveEntry.LF_LINK : TarArchiveEntry.LF_SYMLINK);
            entry.setLinkName(target);
            entry.setMode(0777);
            canonicalOwnership(entry);
            tar.putArchiveEntry(entry);
            tar.closeArchiveEntry();
            tar.finish();
        }
        return encoded.toByteArray();
    }

    private static byte[] symlinkAndDescendantArchive(boolean symlinkFirst) throws Exception {
        ByteArrayOutputStream encoded = new ByteArrayOutputStream();
        try (ZstdOutputStream zstd = new ZstdOutputStream(encoded);
             TarArchiveOutputStream tar = new TarArchiveOutputStream(zstd)) {
            if (symlinkFirst) {
                addCanonicalSymlink(tar, "source", "target");
                addCanonicalFile(tar, "source/Main.java", new byte[]{1});
            } else {
                addCanonicalFile(tar, "source/Main.java", new byte[]{1});
                addCanonicalSymlink(tar, "source", "target");
            }
            tar.finish();
        }
        return encoded.toByteArray();
    }

    private static void addCanonicalSymlink(
            TarArchiveOutputStream tar, String path, String target
    ) throws Exception {
        TarArchiveEntry entry = new TarArchiveEntry(path, TarArchiveEntry.LF_SYMLINK);
        entry.setLinkName(target);
        entry.setMode(0777);
        canonicalOwnership(entry);
        tar.putArchiveEntry(entry);
        tar.closeArchiveEntry();
    }

    private static void addCanonicalFile(
            TarArchiveOutputStream tar, String path, byte[] content
    ) throws Exception {
        TarArchiveEntry entry = new TarArchiveEntry(path);
        entry.setSize(content.length);
        entry.setMode(0644);
        canonicalOwnership(entry);
        tar.putArchiveEntry(entry);
        tar.write(content);
        tar.closeArchiveEntry();
    }

    private static byte[] archiveWithMetadata(
            String path, int mode, long modifiedMillis, Map<String, String> pax
    ) throws Exception {
        ByteArrayOutputStream encoded = new ByteArrayOutputStream();
        try (ZstdOutputStream zstd = new ZstdOutputStream(encoded);
             TarArchiveOutputStream tar = new TarArchiveOutputStream(zstd)) {
            TarArchiveEntry entry = new TarArchiveEntry(path);
            entry.setSize(0);
            entry.setMode(mode);
            entry.setUserId(10001);
            entry.setGroupId(10001);
            entry.setUserName("elmos");
            entry.setGroupName("elmos");
            entry.setModTime(modifiedMillis);
            pax.forEach(entry::addPaxHeader);
            tar.putArchiveEntry(entry);
            tar.closeArchiveEntry();
            tar.finish();
        }
        return encoded.toByteArray();
    }

    private static byte[] longPathArchive(int pathBytes) throws Exception {
        return longPathArchive(pathBytes, TarArchiveOutputStream.LONGFILE_POSIX);
    }

    private static byte[] longPathArchive(int pathBytes, int longFileMode) throws Exception {
        ByteArrayOutputStream encoded = new ByteArrayOutputStream();
        try (ZstdOutputStream zstd = new ZstdOutputStream(encoded);
             TarArchiveOutputStream tar = new TarArchiveOutputStream(zstd)) {
            tar.setLongFileMode(longFileMode);
            TarArchiveEntry entry = new TarArchiveEntry(
                    "source/" + "a".repeat(pathBytes));
            entry.setSize(0);
            entry.setMode(0644);
            canonicalOwnership(entry);
            tar.putArchiveEntry(entry);
            tar.closeArchiveEntry();
            tar.finish();
        }
        return encoded.toByteArray();
    }

    private static byte[] unicodePathArchive() throws Exception {
        ByteArrayOutputStream encoded = new ByteArrayOutputStream();
        try (ZstdOutputStream zstd = new ZstdOutputStream(encoded);
             TarArchiveOutputStream tar = new TarArchiveOutputStream(
                     zstd, StandardCharsets.UTF_8.name())) {
            tar.setLongFileMode(TarArchiveOutputStream.LONGFILE_POSIX);
            tar.setAddPaxHeadersForNonAsciiNames(true);
            addCanonicalFile(tar, "source/\u77ed\u8def\u5f84.txt", new byte[]{1});
            tar.finish();
        }
        return encoded.toByteArray();
    }

    private static Path spoolPath(
            DockerSnapshotVolumeMaterializer.SnapshotSpool spool
    ) throws Exception {
        var field = DockerSnapshotVolumeMaterializer.SnapshotSpool.class
                .getDeclaredField("spool");
        field.setAccessible(true);
        return (Path) field.get(spool);
    }

    private static byte[] zstd(byte[] bytes) throws Exception {
        ByteArrayOutputStream encoded = new ByteArrayOutputStream();
        try (ZstdOutputStream zstd = new ZstdOutputStream(encoded)) {
            zstd.write(bytes);
        }
        return encoded.toByteArray();
    }

    private static void canonicalOwnership(TarArchiveEntry entry) {
        entry.setUserId(10001);
        entry.setGroupId(10001);
        entry.setUserName("elmos");
        entry.setGroupName("elmos");
        entry.setModTime(0);
    }
}
