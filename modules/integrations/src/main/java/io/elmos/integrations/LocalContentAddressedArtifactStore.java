package io.elmos.integrations;

import io.elmos.snapshot.SnapshotPorts;

import java.io.*;
import java.nio.file.*;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;

public final class LocalContentAddressedArtifactStore
        implements SnapshotPorts.ArtifactStore, SnapshotPorts.ArtifactReader {
    private final Path root; private final long maxArtifactBytes;
    public LocalContentAddressedArtifactStore(Path root, long maxArtifactBytes) {
        this.root = Objects.requireNonNull(root).toAbsolutePath().normalize(); this.maxArtifactBytes = maxArtifactBytes;
        if (maxArtifactBytes < 1 || maxArtifactBytes > 100_000_000_000L) throw new IllegalArgumentException("artifact limit is outside policy");
        try { Files.createDirectories(this.root); } catch (IOException error) { throw new IllegalArgumentException("artifact root is unavailable", error); }
    }
    @Override public String putIfAbsent(SnapshotPorts.ArtifactResourceContext resource,
                                        String sha256, long size, InputStream content, String mediaType) {
        Objects.requireNonNull(resource);
        if (sha256 == null || !sha256.matches("[0-9a-f]{64}") || size < 0 || size > maxArtifactBytes) throw new IllegalArgumentException("artifact identity is invalid");
        Objects.requireNonNull(content); Path target = path(sha256);
        try {
            Files.createDirectories(target.getParent());
            if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) { verifyExisting(target, sha256, size); return reference(sha256); }
            Path temporary = Files.createTempFile(target.getParent(), ".upload-", ".tmp");
            try {
                MessageDigest digest = MessageDigest.getInstance("SHA-256"); long written = 0;
                try (InputStream input = new DigestInputStream(content, digest); OutputStream output = Files.newOutputStream(temporary, StandardOpenOption.TRUNCATE_EXISTING)) {
                    byte[] buffer = new byte[64 * 1024]; int read;
                    while ((read = input.read(buffer)) >= 0) { written += read; if (written > maxArtifactBytes || written > size) throw new SecurityException("artifact exceeds declared size"); output.write(buffer, 0, read); }
                }
                String actual = HexFormat.of().formatHex(digest.digest());
                if (written != size || !actual.equals(sha256)) throw new SecurityException("artifact digest or size mismatch");
                try { Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE); }
                catch (FileAlreadyExistsException ignored) { verifyExisting(target, sha256, size); }
                catch (AtomicMoveNotSupportedException error) { throw new IllegalStateException("artifact store requires atomic moves", error); }
            } finally { Files.deleteIfExists(temporary); }
            return reference(sha256);
        } catch (RuntimeException error) { throw error; }
        catch (Exception error) { throw new IllegalStateException("ARTIFACT_STORE_FAILED", error); }
    }
    @Override public InputStream open(SnapshotPorts.ArtifactResourceContext resource, String reference) {
        Objects.requireNonNull(resource);
        String sha = parse(reference); Path target = path(sha);
        try {
            long size = Files.size(target);
            if (size > maxArtifactBytes) throw new SecurityException("artifact exceeds store policy");
            // A legacy reference carries a digest but no size. Verify the bytes before returning
            // the stream; callers must never lose integrity checking merely because writer mode
            // was rolled back from CAS to the legacy directory.
            verifyExisting(target, sha, size);
            return Files.newInputStream(target, StandardOpenOption.READ);
        }
        catch (RuntimeException error) { throw error; }
        catch (Exception error) { throw new IllegalArgumentException("artifact is unavailable", error); }
    }
    @Override public void retainSnapshot(SnapshotPorts.ArtifactResourceContext resource,
                                         String snapshotId, List<String> references) {
        Objects.requireNonNull(resource);
        if (snapshotId == null
                || !snapshotId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
            throw new IllegalArgumentException("snapshotId must be a safe identifier");
        }
        if (references == null || references.isEmpty()) {
            throw new IllegalArgumentException("snapshot references must not be empty");
        }
        // The legacy store has no collector roots, but a reuse/rollback retention attempt still
        // validates the complete set before the snapshot is returned as durable and reusable.
        for (String reference : List.copyOf(references)) {
            try (InputStream ignored = open(resource, reference)) {
                // open() performs the full digest verification before it returns.
            } catch (IOException error) {
                throw new IllegalStateException("cannot close verified legacy artifact", error);
            }
        }
    }
    public Path pathFor(String reference) { return path(parse(reference)); }
    private void verifyExisting(Path target, String expected, long size) throws Exception {
        if (Files.isSymbolicLink(target) || Files.size(target) != size) throw new SecurityException("immutable artifact identity collision");
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = new DigestInputStream(Files.newInputStream(target), digest)) { input.transferTo(OutputStream.nullOutputStream()); }
        String actual = HexFormat.of().formatHex(digest.digest());
        if (!actual.equals(expected)) throw new SecurityException("immutable artifact digest mismatch");
    }
    private Path path(String sha) { Path path = root.resolve(sha.substring(0,2)).resolve(sha.substring(2,4)).resolve(sha).normalize(); if (!path.startsWith(root)) throw new SecurityException("artifact path escape"); return path; }
    private static String reference(String sha) { return "cas:sha256:" + sha; }
    private static String parse(String reference) { if (reference == null || !reference.matches("cas:sha256:[0-9a-f]{64}")) throw new IllegalArgumentException("invalid artifact reference"); return reference.substring("cas:sha256:".length()); }
}
