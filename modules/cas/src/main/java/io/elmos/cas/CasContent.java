package io.elmos.cas;

import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/** Private, verified, replayable stream staging. No bytes are published before verification. */
public final class CasContent implements AutoCloseable {
    private final Path path;
    private boolean closed;

    private CasContent(Path path) { this.path = path; }

    public static CasContent capture(CasDigest expected, InputStream source) {
        Path temporary = null;
        try {
            temporary = Files.createTempFile("elmos-cas-content-", ".part");
            MessageDigest hash = MessageDigest.getInstance("SHA-256");
            long size = 0;
            byte[] buffer = new byte[64 * 1024];
            try (var output = Files.newOutputStream(temporary)) {
                while (true) {
                    int count = source.read(buffer, 0, size == expected.sizeBytes() ? 1
                            : (int) Math.min(buffer.length, expected.sizeBytes() - size));
                    if (count < 0) break;
                    if (count == 0) continue;
                    size += count;
                    if (size > expected.sizeBytes()) {
                        throw new IllegalArgumentException("artifact stream is longer than its declared size");
                    }
                    hash.update(buffer, 0, count);
                    output.write(buffer, 0, count);
                }
            }
            if (size != expected.sizeBytes()) {
                throw new IllegalArgumentException("artifact stream ended after " + size
                        + " bytes but declared " + expected.sizeBytes());
            }
            CasDigest actual = new CasDigest(CasDigest.ALGORITHM, HexFormat.of().formatHex(hash.digest()), size);
            if (!expected.equals(actual)) throw new CasExceptions.CasCorruptionException("stream", expected, actual);
            return new CasContent(temporary);
        } catch (IOException | NoSuchAlgorithmException | RuntimeException failure) {
            if (temporary != null) {
                try { Files.deleteIfExists(temporary); }
                catch (IOException cleanup) { failure.addSuppressed(cleanup); }
            }
            if (failure instanceof RuntimeException runtime) throw runtime;
            throw new IllegalStateException("CAS stream staging failed", failure);
        }
    }

    public InputStream openStream() {
        if (closed) throw new IllegalStateException("CAS content is closed");
        try { return Files.newInputStream(path); }
        catch (IOException error) { throw new UncheckedIOException(error); }
    }

    /** Transfers spool ownership to the returned stream, which deletes it on close. */
    public InputStream ownedStream() {
        return new FilterInputStream(openStream()) {
            @Override public void close() throws IOException {
                try { super.close(); } finally { CasContent.this.close(); }
            }
        };
    }

    @Override public void close() {
        try { Files.deleteIfExists(path); closed = true; }
        catch (IOException error) { throw new UncheckedIOException(error); }
    }
}
