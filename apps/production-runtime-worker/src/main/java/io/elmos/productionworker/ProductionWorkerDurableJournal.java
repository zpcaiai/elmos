package io.elmos.productionworker;

import io.elmos.productionruntime.ProductionRuntimeException;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermission;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/**
 * File-per-attempt write-ahead journal on the StatefulSet PVC. Every accepted
 * envelope and transition is fsynced and atomically renamed before it can be
 * acknowledged or acted on.
 */
final class ProductionWorkerDurableJournal {
    private static final int MAX_RECORD_BYTES = 32 * 1024 * 1024;
    private final Path directory;

    ProductionWorkerDurableJournal(Path configuredDirectory) {
        if (configuredDirectory == null) {
            throw new IllegalArgumentException("worker state directory is required");
        }
        this.directory = configuredDirectory.toAbsolutePath().normalize();
        try {
            boolean existed = Files.exists(directory, LinkOption.NOFOLLOW_LINKS);
            if (Files.isSymbolicLink(directory)) {
                throw failure("worker state directory may not be a symlink", null);
            }
            Files.createDirectories(directory);
            if (!existed) {
                try {
                    Files.setPosixFilePermissions(directory, Set.of(
                            PosixFilePermission.OWNER_READ,
                            PosixFilePermission.OWNER_WRITE,
                            PosixFilePermission.OWNER_EXECUTE,
                            PosixFilePermission.GROUP_READ,
                            PosixFilePermission.GROUP_WRITE,
                            PosixFilePermission.GROUP_EXECUTE));
                } catch (UnsupportedOperationException ignored) {
                    // Equivalent ACL is an environment responsibility.
                }
            }
            if (!Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS)) {
                throw failure("worker state path is not a directory", null);
            }
            try {
                Set<PosixFilePermission> permissions = Files.getPosixFilePermissions(
                        directory, LinkOption.NOFOLLOW_LINKS);
                if (permissions.contains(PosixFilePermission.OTHERS_READ)
                        || permissions.contains(PosixFilePermission.OTHERS_WRITE)
                        || permissions.contains(PosixFilePermission.OTHERS_EXECUTE)) {
                    throw failure("worker state directory is accessible by other users", null);
                }
            } catch (UnsupportedOperationException ignored) {
                // Deployment policy supplies an equivalent ACL on non-POSIX stores.
            }
        } catch (IOException ex) {
            throw failure("worker state directory cannot be initialized", ex);
        }
    }

    Map<UUID, byte[]> load(int maximumRecords) {
        Map<UUID, byte[]> records = new LinkedHashMap<>();
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(directory, "*.json")) {
            for (Path path : stream) {
                if (records.size() >= maximumRecords) {
                    throw failure("worker journal exceeds the retained-attempt limit", null);
                }
                if (Files.isSymbolicLink(path) || !Files.isRegularFile(
                        path, LinkOption.NOFOLLOW_LINKS)) {
                    throw failure("worker journal contains a non-regular record", null);
                }
                String name = path.getFileName().toString();
                UUID attemptId;
                try {
                    attemptId = UUID.fromString(name.substring(0, name.length() - 5));
                } catch (IllegalArgumentException | IndexOutOfBoundsException ex) {
                    throw failure("worker journal record name is invalid", ex);
                }
                long size = Files.size(path);
                if (size < 2 || size > MAX_RECORD_BYTES) {
                    throw failure("worker journal record size is invalid", null);
                }
                records.put(attemptId, Files.readAllBytes(path));
            }
            return records;
        } catch (IOException ex) {
            throw failure("worker journal cannot be loaded", ex);
        }
    }

    void write(UUID attemptId, byte[] payload) {
        if (payload == null || payload.length < 2 || payload.length > MAX_RECORD_BYTES) {
            throw new IllegalArgumentException("worker journal payload size is invalid");
        }
        Path target = record(attemptId);
        Path temporary = directory.resolve("." + attemptId + "." + UUID.randomUUID() + ".tmp");
        try {
            if (Files.exists(temporary, LinkOption.NOFOLLOW_LINKS)) {
                throw failure("worker journal temporary path collision", null);
            }
            try (FileChannel channel = FileChannel.open(
                    temporary,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE,
                    LinkOption.NOFOLLOW_LINKS)) {
                ByteBuffer buffer = ByteBuffer.wrap(payload);
                while (buffer.hasRemaining()) channel.write(buffer);
                channel.force(true);
            }
            try {
                Files.setPosixFilePermissions(temporary, Set.of(
                        PosixFilePermission.OWNER_READ,
                        PosixFilePermission.OWNER_WRITE,
                        PosixFilePermission.GROUP_READ));
            } catch (UnsupportedOperationException ignored) {
                // Equivalent ACL is an environment responsibility.
            }
            try {
                Files.move(
                        temporary, target,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException ex) {
                throw failure("worker journal filesystem lacks atomic rename", ex);
            }
            fsyncDirectory();
        } catch (IOException ex) {
            throw failure("worker journal write failed", ex);
        } finally {
            try {
                Files.deleteIfExists(temporary);
            } catch (IOException ignored) {
                // A dot-prefixed incomplete record is never loaded.
            }
        }
    }

    void delete(UUID attemptId) {
        try {
            Files.deleteIfExists(record(attemptId));
            fsyncDirectory();
        } catch (IOException ex) {
            throw failure("worker journal eviction failed", ex);
        }
    }

    private Path record(UUID attemptId) {
        return directory.resolve(attemptId + ".json");
    }

    private void fsyncDirectory() throws IOException {
        try (FileChannel channel = FileChannel.open(directory, StandardOpenOption.READ)) {
            channel.force(true);
        }
    }

    private static ProductionRuntimeException failure(String message, Throwable cause) {
        return cause == null
                ? new ProductionRuntimeException("WORKER_DURABLE_JOURNAL_FAILURE", message)
                : new ProductionRuntimeException(
                        "WORKER_DURABLE_JOURNAL_FAILURE", message, cause);
    }
}
