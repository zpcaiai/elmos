package io.elmos.cas;

import java.io.IOException;
import java.io.RandomAccessFile;
import java.io.UncheckedIOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.stream.Stream;

/**
 * ELMOS-CAS-013. The runner-local L1 tier, on real files.
 *
 * <p>Three properties are load bearing and easy to lose:
 *
 * <ol>
 *   <li><b>Writes are atomic.</b> Content goes to a temp file and is then moved into place. A
 *       reader must never observe a half-written object, because a half-written object still has
 *       a perfectly valid-looking path and would be trusted forever.</li>
 *   <li><b>Reads verify.</b> A local disk is the single most likely place for a silent
 *       bit-flip or a truncation after a full disk, and the read path is the only place that
 *       can catch it before the bytes reach a compiler.</li>
 *   <li><b>Poisoned objects are moved, not deleted.</b> An object that failed verification is
 *       evidence; it goes to {@code quarantine/} so the incident can be reconstructed.</li>
 * </ol>
 */
public final class LocalDiskCasStore implements CasStore {

    private static final int VERIFY_BUFFER = 64 * 1024;

    private final String name;
    private final Path root;
    private final Path blobs;
    private final Path staging;
    private final Path quarantine;

    public LocalDiskCasStore(String name, Path root) {
        this.name = CasText.required(name, "name");
        this.root = root;
        this.blobs = root.resolve("blobs");
        this.staging = root.resolve("staging");
        this.quarantine = root.resolve("quarantine");
        try {
            Files.createDirectories(blobs);
            Files.createDirectories(staging);
            Files.createDirectories(quarantine);
        } catch (IOException error) {
            throw new UncheckedIOException("cannot initialise CAS root " + root, error);
        }
    }

    @Override
    public String name() {
        return name;
    }

    public Path root() {
        return root;
    }

    public Path pathFor(CasDigest digest) {
        return blobs.resolve(digest.shardPath());
    }

    @Override
    public boolean contains(CasDigest digest) {
        Path path = pathFor(digest);
        try {
            return Files.exists(path) && Files.size(path) == digest.sizeBytes();
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    @Override
    public void put(CasDigest expected, byte[] content) {
        CasDigest actual = CasDigest.of(content);
        if (!actual.equals(expected)) {
            throw new CasExceptions.CasCorruptionException(name, expected, actual);
        }
        Path target = pathFor(expected);
        if (contains(expected)) {
            return;
        }
        try {
            Files.createDirectories(target.getParent());
            Path temporary = Files.createTempFile(staging, "put-", ".part");
            Files.write(temporary, content);
            moveIntoPlace(temporary, target);
        } catch (IOException error) {
            throw new UncheckedIOException("cannot store " + expected.compact(), error);
        }
    }

    /**
     * Promotes an already-materialised file into the store without a second copy through the
     * heap. Used by the chunked upload path, which has already assembled the object on disk.
     */
    public void promote(CasDigest expected, Path assembled) {
        CasDigest actual = digestOf(assembled);
        if (!actual.equals(expected)) {
            throw new CasExceptions.CasCorruptionException(name, expected, actual);
        }
        Path target = pathFor(expected);
        try {
            if (contains(expected)) {
                Files.deleteIfExists(assembled);
                return;
            }
            Files.createDirectories(target.getParent());
            moveIntoPlace(assembled, target);
        } catch (IOException error) {
            throw new UncheckedIOException("cannot promote " + expected.compact(), error);
        }
    }

    @Override
    public byte[] get(CasDigest digest) {
        Path path = pathFor(digest);
        if (!Files.exists(path)) {
            throw new CasExceptions.CasNotFoundException(digest);
        }
        byte[] content;
        try {
            content = Files.readAllBytes(path);
        } catch (IOException error) {
            throw new UncheckedIOException("cannot read " + digest.compact(), error);
        }
        CasDigest actual = CasDigest.of(content);
        if (!actual.equals(digest)) {
            quarantine(digest, path, actual);
            throw new CasExceptions.CasCorruptionException(name, digest, actual);
        }
        return content;
    }

    @Override
    public byte[] readRange(CasDigest digest, long offset, int length) {
        Path path = pathFor(digest);
        if (!Files.exists(path)) {
            throw new CasExceptions.CasNotFoundException(digest);
        }
        if (offset < 0) {
            throw new IllegalArgumentException("range offset must not be negative: " + offset);
        }
        try (RandomAccessFile file = new RandomAccessFile(path.toFile(), "r")) {
            if (offset > file.length()) {
                throw new IllegalArgumentException("range offset outside object: " + offset);
            }
            file.seek(offset);
            byte[] buffer = new byte[(int) Math.min(length, file.length() - offset)];
            file.readFully(buffer);
            return buffer;
        } catch (IOException error) {
            throw new UncheckedIOException("cannot range-read " + digest.compact(), error);
        }
    }

    @Override
    public boolean delete(CasDigest digest) {
        try {
            return Files.deleteIfExists(pathFor(digest));
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    @Override
    public Set<CasDigest> inventory() {
        Set<CasDigest> digests = new LinkedHashSet<>();
        if (!Files.exists(blobs)) {
            return digests;
        }
        try (Stream<Path> walk = Files.walk(blobs)) {
            walk.filter(Files::isRegularFile)
                    .sorted(Comparator.comparing(Path::toString))
                    .forEach(path -> {
                        try {
                            digests.add(new CasDigest(CasDigest.ALGORITHM, path.getFileName().toString(),
                                    Files.size(path)));
                        } catch (IOException error) {
                            throw new UncheckedIOException(error);
                        } catch (IllegalArgumentException ignored) {
                            // A file whose name is not a digest is not an object; the reconciler
                            // reports it as a stray rather than crashing the inventory walk.
                        }
                    });
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
        return digests;
    }

    @Override
    public long totalBytes() {
        return inventory().stream().mapToLong(CasDigest::sizeBytes).sum();
    }

    public long lastAccessEpochMillis(CasDigest digest) {
        try {
            return Files.getLastModifiedTime(pathFor(digest)).toMillis();
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    public Set<Path> quarantinedPaths() {
        try (Stream<Path> walk = Files.walk(quarantine)) {
            return walk.filter(Files::isRegularFile).collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new));
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    /** Streams the file so a multi-gigabyte object is verified without being held in memory. */
    public CasDigest digestOf(Path path) {
        CasHasher hasher = new CasHasher();
        byte[] buffer = new byte[VERIFY_BUFFER];
        try (var input = Files.newInputStream(path)) {
            int read;
            while ((read = input.read(buffer)) > 0) {
                hasher.update(buffer, 0, read);
            }
        } catch (IOException error) {
            throw new UncheckedIOException("cannot digest " + path, error);
        }
        return hasher.finish();
    }

    private void quarantine(CasDigest expected, Path path, CasDigest actual) {
        try {
            Path destination = quarantine.resolve(expected.hex() + "." + actual.hex() + ".poisoned");
            Files.move(path, destination, StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException error) {
            throw new UncheckedIOException("cannot quarantine " + expected.compact(), error);
        }
    }

    private void moveIntoPlace(Path temporary, Path target) throws IOException {
        try {
            Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException | java.nio.file.FileAlreadyExistsException fallback) {
            // Losing the race is the normal outcome under content addressing: the other writer
            // stored identical bytes. Drop our copy rather than overwrite a verified object.
            if (Files.exists(target)) {
                Files.deleteIfExists(temporary);
                return;
            }
            Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    public byte[] readRawForDiagnostics(CasDigest digest) {
        try {
            return Files.readAllBytes(pathFor(digest));
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    static byte[] copy(byte[] value) {
        return Arrays.copyOf(value, value.length);
    }
}
