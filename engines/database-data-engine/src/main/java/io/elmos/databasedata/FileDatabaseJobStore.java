package io.elmos.databasedata;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.engine.api.EngineApi.JobResponse;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Optional;

final class FileDatabaseJobStore implements DatabaseJobStore {
    private record StoredIdempotency(String scopedKey, String fingerprint, JobResponse response) {}

    private final Path root;
    private final ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();

    FileDatabaseJobStore(Path root) {
        this.root = root.toAbsolutePath().normalize();
        try {
            Files.createDirectories(this.root);
            if (Files.isSymbolicLink(this.root) || !Files.isDirectory(this.root, LinkOption.NOFOLLOW_LINKS)) {
                throw new IllegalArgumentException("database job state root must be a real directory");
            }
            setOwnerOnly(this.root, true);
        } catch (IOException error) {
            throw new IllegalStateException("database job state root is unavailable", error);
        }
    }

    @Override
    public synchronized Optional<JobResponse> job(String organizationId, String jobId) {
        return read(path("job", organizationId + "\n" + jobId), JobResponse.class);
    }

    @Override
    public synchronized Optional<IdempotentResult> idempotent(String scopedKey) {
        Optional<StoredIdempotency> stored = read(path("idempotency", scopedKey), StoredIdempotency.class);
        if (stored.isEmpty()) return Optional.empty();
        if (!stored.get().scopedKey().equals(scopedKey)) {
            throw new IllegalStateException("database job idempotency digest collision");
        }
        return Optional.of(new IdempotentResult(stored.get().fingerprint(), stored.get().response()));
    }

    @Override
    public synchronized void save(
            String organizationId,
            String jobId,
            String scopedKey,
            IdempotentResult result
    ) {
        write(path("job", organizationId + "\n" + jobId), result.response());
        write(
                path("idempotency", scopedKey),
                new StoredIdempotency(scopedKey, result.fingerprint(), result.response()));
    }

    @Override
    public synchronized void replaceJob(String organizationId, String jobId, JobResponse response) {
        write(path("job", organizationId + "\n" + jobId), response);
    }

    @Override
    public boolean durable() {
        return true;
    }

    private Path path(String kind, String identity) {
        Path directory = root.resolve(kind);
        try {
            Files.createDirectories(directory);
            if (Files.isSymbolicLink(directory)) {
                throw new IllegalStateException("database job state directory must not be a symbolic link");
            }
            setOwnerOnly(directory, true);
        } catch (IOException error) {
            throw new IllegalStateException("database job state directory is unavailable", error);
        }
        return directory.resolve(digest(identity) + ".json");
    }

    private <T> Optional<T> read(Path path, Class<T> type) {
        if (!Files.exists(path, LinkOption.NOFOLLOW_LINKS)) return Optional.empty();
        if (Files.isSymbolicLink(path) || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
            throw new IllegalStateException("database job state entry is not a regular file");
        }
        try {
            return Optional.of(mapper.readValue(path.toFile(), type));
        } catch (IOException error) {
            throw new IllegalStateException("database job state entry is corrupt", error);
        }
    }

    private void write(Path destination, Object value) {
        try {
            byte[] bytes = mapper.writeValueAsBytes(value);
            Path temporary = Files.createTempFile(root, ".database-job-", ".tmp");
            setOwnerOnly(temporary, false);
            Files.write(temporary, bytes);
            try {
                Files.move(
                        temporary,
                        destination,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException ignored) {
                Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING);
            }
            setOwnerOnly(destination, false);
        } catch (IOException error) {
            throw new IllegalStateException("database job state could not be persisted", error);
        }
    }

    private static void setOwnerOnly(Path path, boolean directory) {
        try {
            Files.setPosixFilePermissions(
                    path,
                    PosixFilePermissions.fromString(directory ? "rwx------" : "rw-------"));
        } catch (UnsupportedOperationException ignored) {
            // Non-POSIX filesystems retain the platform's default ACL. The
            // production image and supported macOS runner are POSIX.
        } catch (IOException error) {
            throw new IllegalStateException("database job state permissions could not be restricted", error);
        }
    }

    private static String digest(String value) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }
}
