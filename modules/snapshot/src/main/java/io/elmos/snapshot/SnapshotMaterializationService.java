package io.elmos.snapshot;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.luben.zstd.ZstdInputStream;
import org.apache.commons.compress.archivers.tar.TarArchiveEntry;
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream;

import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * Materializes an immutable content-addressed Snapshot without trusting archive
 * paths, modes or declared digests. The resulting directory is read-only and
 * can be mounted into a Transformer as its source filesystem.
 */
public final class SnapshotMaterializationService {
    public record Materialization(
            String snapshotId,
            String organizationId,
            String relativePath,
            String archiveSha256,
            String manifestSha256
    ) {}

    private static final int MAX_MANIFEST_BYTES = 32 * 1024 * 1024;
    private static final int MAX_ENTRIES = 100_000;
    private static final long MAX_SOURCE_BYTES = 256L * 1024 * 1024;
    private static final String MARKER = ".elmos/materialization.json";

    private final Path root;
    private final SnapshotPorts.ArtifactReader artifacts;
    private final ObjectMapper json;

    public SnapshotMaterializationService(
            Path root,
            SnapshotPorts.ArtifactReader artifacts,
            ObjectMapper json
    ) {
        this.root = Objects.requireNonNull(root).toAbsolutePath().normalize();
        this.artifacts = Objects.requireNonNull(artifacts);
        this.json = Objects.requireNonNull(json);
        try {
            Files.createDirectories(this.root);
            if (Files.isSymbolicLink(this.root)
                    || !Files.isDirectory(this.root, LinkOption.NOFOLLOW_LINKS)) {
                throw new SecurityException("materialization root is invalid");
            }
        } catch (IOException error) {
            throw new IllegalArgumentException("materialization root is unavailable", error);
        }
    }

    public Materialization materialize(
            String trustedOrganizationId,
            SnapshotModel.RepositorySnapshot snapshot
    ) {
        requireIdentifier(trustedOrganizationId, "organization");
        Objects.requireNonNull(snapshot);
        if (!trustedOrganizationId.equals(snapshot.organizationId())) {
            throw new SecurityException("snapshot belongs to another organization");
        }
        if (snapshot.status() != SnapshotModel.Status.AVAILABLE) {
            throw new SecurityException("only an available immutable snapshot may be materialized");
        }
        requireIdentifier(snapshot.snapshotId(), "snapshot");
        requireIdentifier(snapshot.repositoryId(), "repository");
        var resource = new SnapshotPorts.ArtifactResourceContext(
                trustedOrganizationId, snapshot.repositoryId());

        Path organizationRoot = confined(root.resolve(trustedOrganizationId));
        Path target = confined(organizationRoot.resolve(snapshot.snapshotId()));
        try {
            Files.createDirectories(organizationRoot);
            if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) {
                verifyExisting(target, snapshot);
                return result(snapshot, target);
            }

            byte[] manifestBytes;
            try (InputStream input = artifacts.open(resource, snapshot.manifestArtifactRef())) {
                manifestBytes = readBounded(input, MAX_MANIFEST_BYTES);
            }
            requireDigest(manifestBytes, snapshot.manifestSha256(), "snapshot manifest");
            DeterministicSnapshotArchiver.SnapshotManifest manifest =
                    json.readValue(manifestBytes, DeterministicSnapshotArchiver.SnapshotManifest.class);
            validateManifest(snapshot, manifest);

            Path temporary = Files.createTempDirectory(organizationRoot, ".materialize-");
            try {
                extract(resource, snapshot, manifest, temporary);
                writeMarker(temporary, snapshot);
                makeReadOnly(temporary);
                try {
                    Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE);
                } catch (FileAlreadyExistsException race) {
                    deleteTree(temporary);
                } catch (AtomicMoveNotSupportedException unsupported) {
                    throw new IllegalStateException(
                            "materialization filesystem must support atomic publish", unsupported);
                }
                verifyExisting(target, snapshot);
                return result(snapshot, target);
            } finally {
                if (Files.exists(temporary, LinkOption.NOFOLLOW_LINKS)) {
                    makeWritableForCleanup(temporary);
                    deleteTree(temporary);
                }
            }
        } catch (RuntimeException error) {
            throw error;
        } catch (Exception error) {
            throw new IllegalStateException("snapshot materialization failed", error);
        }
    }

    private void extract(
            SnapshotPorts.ArtifactResourceContext resource,
            SnapshotModel.RepositorySnapshot snapshot,
            DeterministicSnapshotArchiver.SnapshotManifest manifest,
            Path temporary
    ) throws Exception {
        Map<String, DeterministicSnapshotArchiver.ManifestEntry> expected = new HashMap<>();
        long declaredSourceBytes = 0;
        for (var entry : manifest.files()) {
            String path = validateEntryPath(entry.path());
            if (expected.put(path, entry) != null) {
                throw new SecurityException("snapshot manifest contains duplicate paths");
            }
            declaredSourceBytes = Math.addExact(declaredSourceBytes, entry.size());
            if (declaredSourceBytes > MAX_SOURCE_BYTES) {
                throw new SecurityException("snapshot source bytes exceed materialization policy");
            }
        }
        if (expected.size() > MAX_ENTRIES) {
            throw new SecurityException("snapshot entry count exceeds materialization policy");
        }

        Set<String> observed = new HashSet<>();
        try (InputStream raw = artifacts.open(resource, snapshot.archiveArtifactRef());
             VerifiedInputStream verified = new VerifiedInputStream(
                     raw, snapshot.archiveSize(), snapshot.archiveSha256());
             ZstdInputStream zstd = new ZstdInputStream(verified);
             TarArchiveInputStream tar =
                     new TarArchiveInputStream(zstd, StandardCharsets.UTF_8.name())) {
            TarArchiveEntry archiveEntry;
            while ((archiveEntry = tar.getNextTarEntry()) != null) {
                String archivePath = normalizeArchiveName(archiveEntry.getName());
                validateEntryPath(archivePath);
                var manifestEntry = expected.get(archivePath);
                if (manifestEntry == null || !observed.add(archivePath)) {
                    throw new SecurityException("archive paths differ from the signed manifest");
                }
                Path output = confined(temporary.resolve(archivePath));
                if (!output.startsWith(temporary)) {
                    throw new SecurityException("archive path escapes materialization root");
                }
                requireEntryContract(archiveEntry, manifestEntry);
                if (archiveEntry.isDirectory()) {
                    Files.createDirectories(output);
                } else if (archiveEntry.isFile()) {
                    Files.createDirectories(output.getParent());
                    writeVerifiedFile(tar, output, manifestEntry);
                } else if (archiveEntry.isSymbolicLink()) {
                    Files.createDirectories(output.getParent());
                    createVerifiedSymlink(output, temporary, manifestEntry);
                } else {
                    throw new SecurityException("archive contains an unsupported special entry");
                }
            }
            verified.requireComplete();
        }
        if (!observed.equals(expected.keySet())) {
            throw new SecurityException("archive is incomplete for the signed manifest");
        }
    }

    private static void requireEntryContract(
            TarArchiveEntry archive,
            DeterministicSnapshotArchiver.ManifestEntry manifest
    ) {
        String actualType = archive.isDirectory() ? "directory"
                : archive.isFile() ? "file"
                : archive.isSymbolicLink() ? "symlink"
                : "unsupported";
        if (!actualType.equals(manifest.type())
                || archive.isLink()
                || archive.isCharacterDevice()
                || archive.isBlockDevice()
                || archive.isFIFO()) {
            throw new SecurityException("archive entry type differs from the signed manifest");
        }
        if (archive.isFile() && archive.getSize() != manifest.size()) {
            throw new SecurityException("archive entry size differs from the signed manifest");
        }
        if ((archive.getMode() & 0777) != (manifest.mode() & 0777)) {
            throw new SecurityException("archive entry mode differs from the signed manifest");
        }
        if (archive.isSymbolicLink()
                && !Objects.equals(archive.getLinkName(), manifest.linkTarget())) {
            throw new SecurityException("archive symlink differs from the signed manifest");
        }
    }

    private static void writeVerifiedFile(
            TarArchiveInputStream tar,
            Path output,
            DeterministicSnapshotArchiver.ManifestEntry manifest
    ) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        long written = 0;
        try (var stream = Files.newOutputStream(output)) {
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = tar.read(buffer)) >= 0) {
                written = Math.addExact(written, read);
                if (written > manifest.size()) {
                    throw new SecurityException("archive entry exceeds its signed size");
                }
                digest.update(buffer, 0, read);
                stream.write(buffer, 0, read);
            }
        }
        String actual = HexFormat.of().formatHex(digest.digest());
        if (written != manifest.size() || !actual.equals(manifest.sha256())) {
            throw new SecurityException("materialized file differs from its signed digest");
        }
        setMode(output, manifest.mode(), false);
    }

    private static void createVerifiedSymlink(
            Path output,
            Path temporary,
            DeterministicSnapshotArchiver.ManifestEntry manifest
    ) throws Exception {
        String targetValue = manifest.linkTarget();
        if (targetValue == null || targetValue.isBlank() || targetValue.indexOf('\0') >= 0) {
            throw new SecurityException("snapshot symlink target is invalid");
        }
        Path linkTarget = Path.of(targetValue);
        if (linkTarget.isAbsolute()
                || !output.getParent().resolve(linkTarget).normalize().startsWith(temporary)) {
            throw new SecurityException("snapshot symlink escapes materialization root");
        }
        String actualDigest = digest(targetValue.getBytes(StandardCharsets.UTF_8));
        if (!actualDigest.equals(manifest.sha256())) {
            throw new SecurityException("snapshot symlink target digest mismatch");
        }
        Files.createSymbolicLink(output, linkTarget);
    }

    private void verifyExisting(Path target, SnapshotModel.RepositorySnapshot snapshot) {
        try {
            if (Files.isSymbolicLink(target)
                    || !Files.isDirectory(target, LinkOption.NOFOLLOW_LINKS)) {
                throw new SecurityException("materialization target is invalid");
            }
            Path marker = target.resolve(MARKER);
            if (Files.isSymbolicLink(marker)
                    || !Files.isRegularFile(marker, LinkOption.NOFOLLOW_LINKS)) {
                throw new SecurityException("materialization marker is missing");
            }
            @SuppressWarnings("unchecked")
            Map<String, String> value = json.readValue(marker.toFile(), Map.class);
            if (!snapshot.snapshotId().equals(value.get("snapshot_id"))
                    || !snapshot.organizationId().equals(value.get("organization_id"))
                    || !snapshot.archiveSha256().equals(value.get("archive_sha256"))
                    || !snapshot.manifestSha256().equals(value.get("manifest_sha256"))) {
                throw new SecurityException("materialization marker does not match Snapshot identity");
            }
            var rearchived = new DeterministicSnapshotArchiver().archive(target);
            if (!snapshot.archiveSha256().equals(rearchived.archiveSha256())) {
                throw new SecurityException("materialized files no longer match Snapshot digest");
            }
        } catch (RuntimeException error) {
            throw error;
        } catch (Exception error) {
            throw new IllegalStateException("unable to verify materialized Snapshot", error);
        }
    }

    private void writeMarker(Path temporary, SnapshotModel.RepositorySnapshot snapshot)
            throws IOException {
        Path marker = temporary.resolve(MARKER);
        Files.createDirectories(marker.getParent());
        json.writeValue(marker.toFile(), Map.of(
                "schema_version", "1.0",
                "snapshot_id", snapshot.snapshotId(),
                "organization_id", snapshot.organizationId(),
                "archive_sha256", snapshot.archiveSha256(),
                "manifest_sha256", snapshot.manifestSha256()
        ));
    }

    private static void validateManifest(
            SnapshotModel.RepositorySnapshot snapshot,
            DeterministicSnapshotArchiver.SnapshotManifest manifest
    ) {
        if (manifest == null
                || !"1.0".equals(manifest.schemaVersion())
                || manifest.repository() == null
                || manifest.source() == null
                || manifest.archive() == null
                || manifest.files() == null
                || manifest.specialContent() == null
                || !snapshot.repositoryId().equals(manifest.repository().repositoryId())
                || !snapshot.requestedRef().equals(manifest.source().requestedRef())
                || !snapshot.resolvedCommitSha().equals(manifest.source().commitSha())
                || !snapshot.treeSha().equals(manifest.source().treeSha())
                || !"SHA-256".equals(manifest.archive().algorithm())
                || !"tar.zst".equals(manifest.archive().format())
                || !snapshot.archiveSha256().equals(manifest.archive().digest())) {
            throw new SecurityException("snapshot manifest identity is invalid");
        }
        if (!manifest.specialContent().submodules().isEmpty()) {
            throw new SecurityException(
                    "submodules require separate repository authorization and hydration");
        }
        if (!manifest.specialContent().gitLfsPointers().isEmpty()) {
            throw new SecurityException("Git LFS objects must be hydrated and verified");
        }
        if (!manifest.specialContent().symlinks().isEmpty()) {
            throw new SecurityException(
                    "symlink-bearing snapshots require an explicitly approved materialization profile");
        }
    }

    private Materialization result(
            SnapshotModel.RepositorySnapshot snapshot,
            Path target
    ) {
        String relative = root.relativize(target).toString()
                .replace(target.getFileSystem().getSeparator(), "/");
        return new Materialization(
                snapshot.snapshotId(),
                snapshot.organizationId(),
                relative,
                snapshot.archiveSha256(),
                snapshot.manifestSha256()
        );
    }

    private Path confined(Path raw) {
        Path normalized = raw.toAbsolutePath().normalize();
        if (!normalized.startsWith(root)) {
            throw new SecurityException("materialization path escapes configured root");
        }
        return normalized;
    }

    private static String validateEntryPath(String value) {
        if (value == null
                || value.isBlank()
                || value.length() > 4096
                || value.startsWith("/")
                || value.contains("\\")
                || value.indexOf('\0') >= 0) {
            throw new SecurityException("snapshot entry path is invalid");
        }
        Path path = Path.of(value);
        if (path.isAbsolute()) {
            throw new SecurityException("snapshot entry path is absolute");
        }
        for (Path segment : path) {
            if (".".equals(segment.toString()) || "..".equals(segment.toString())) {
                throw new SecurityException("snapshot entry path traverses directories");
            }
        }
        return value;
    }

    private static String normalizeArchiveName(String value) {
        if (value != null && value.endsWith("/")) {
            return value.substring(0, value.length() - 1);
        }
        return value;
    }

    private static void requireIdentifier(String value, String label) {
        if (value == null || !value.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
            throw new SecurityException(label + " identifier is invalid");
        }
    }

    private static byte[] readBounded(InputStream input, int limit) throws IOException {
        byte[] bytes = input.readNBytes(limit + 1);
        if (bytes.length > limit || input.read() >= 0) {
            throw new SecurityException("snapshot manifest exceeds policy");
        }
        return bytes;
    }

    private static void requireDigest(byte[] bytes, String expected, String label) {
        if (!digest(bytes).equals(expected)) {
            throw new SecurityException(label + " digest mismatch");
        }
    }

    private static String digest(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    private static void makeReadOnly(Path root) throws IOException {
        List<Path> paths;
        try (var stream = Files.walk(root)) {
            paths = stream.sorted(Comparator.reverseOrder()).toList();
        }
        for (Path path : paths) {
            if (Files.isSymbolicLink(path)) continue;
            if (Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) {
                setMode(path, 0555, true);
            } else {
                boolean executable = Files.isExecutable(path);
                setMode(path, executable ? 0555 : 0444, false);
            }
        }
    }

    private static void setMode(Path path, int mode, boolean directory)
            throws IOException {
        Set<PosixFilePermission> permissions = new HashSet<>();
        if ((mode & 0400) != 0) permissions.add(PosixFilePermission.OWNER_READ);
        if ((mode & 0200) != 0) permissions.add(PosixFilePermission.OWNER_WRITE);
        if ((mode & 0100) != 0) permissions.add(PosixFilePermission.OWNER_EXECUTE);
        if ((mode & 0040) != 0) permissions.add(PosixFilePermission.GROUP_READ);
        if ((mode & 0020) != 0) permissions.add(PosixFilePermission.GROUP_WRITE);
        if ((mode & 0010) != 0) permissions.add(PosixFilePermission.GROUP_EXECUTE);
        if ((mode & 0004) != 0) permissions.add(PosixFilePermission.OTHERS_READ);
        if ((mode & 0002) != 0) permissions.add(PosixFilePermission.OTHERS_WRITE);
        if ((mode & 0001) != 0) permissions.add(PosixFilePermission.OTHERS_EXECUTE);
        try {
            Files.setPosixFilePermissions(path, permissions);
        } catch (UnsupportedOperationException unsupported) {
            if (!path.toFile().setReadable(true, false)
                    || !path.toFile().setWritable(false, false)
                    || (directory && !path.toFile().setExecutable(true, false))) {
                throw new SecurityException("filesystem cannot enforce read-only materialization");
            }
        }
    }

    private static void makeWritableForCleanup(Path root) {
        try (var stream = Files.walk(root)) {
            stream.filter(path -> !Files.isSymbolicLink(path)).forEach(path -> {
                path.toFile().setWritable(true, true);
                if (Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) {
                    path.toFile().setExecutable(true, true);
                }
            });
        } catch (IOException ignored) {
            // deleteTree below remains the authoritative fail-closed cleanup.
        }
    }

    private void deleteTree(Path rawTarget) {
        Path target = confined(rawTarget);
        if (target.equals(root)) {
            throw new SecurityException("refusing unsafe materialization cleanup");
        }
        try {
            Files.walkFileTree(target, new SimpleFileVisitor<>() {
                @Override public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attributes
                ) throws IOException {
                    Files.deleteIfExists(file);
                    return FileVisitResult.CONTINUE;
                }

                @Override public FileVisitResult postVisitDirectory(
                        Path directory, IOException failure
                ) throws IOException {
                    if (failure != null) throw failure;
                    Files.deleteIfExists(directory);
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException error) {
            throw new IllegalStateException("materialization cleanup failed", error);
        }
    }

    private static final class VerifiedInputStream extends FilterInputStream {
        private final long expectedSize;
        private final String expectedDigest;
        private final MessageDigest digest;
        private long count;
        private boolean completed;

        VerifiedInputStream(InputStream input, long expectedSize, String expectedDigest)
                throws Exception {
            super(Objects.requireNonNull(input));
            if (expectedSize < 1 || expectedDigest == null
                    || !expectedDigest.matches("[0-9a-f]{64}")) {
                throw new SecurityException("snapshot archive identity is invalid");
            }
            this.expectedSize = expectedSize;
            this.expectedDigest = expectedDigest;
            this.digest = MessageDigest.getInstance("SHA-256");
        }

        @Override public int read() throws IOException {
            int value = super.read();
            if (value >= 0) update(new byte[]{(byte) value}, 0, 1);
            else completed = true;
            return value;
        }

        @Override public int read(byte[] bytes, int offset, int length)
                throws IOException {
            int value = super.read(bytes, offset, length);
            if (value > 0) update(bytes, offset, value);
            else if (value < 0) completed = true;
            return value;
        }

        private void update(byte[] bytes, int offset, int length) {
            count = Math.addExact(count, length);
            if (count > expectedSize) {
                throw new SecurityException("snapshot archive exceeds declared size");
            }
            digest.update(bytes, offset, length);
        }

        void requireComplete() throws IOException {
            byte[] buffer = new byte[8192];
            while (read(buffer) >= 0) {
                // Drain compressed input so size and digest cover every byte.
            }
            String actual = HexFormat.of().formatHex(digest.digest());
            if (!completed || count != expectedSize || !actual.equals(expectedDigest)) {
                throw new SecurityException("snapshot archive digest or size mismatch");
            }
        }
    }
}
