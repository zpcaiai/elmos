package io.elmos.security;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.DirectoryStream;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.time.Clock;
import java.time.Instant;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.locks.ReentrantLock;
import java.util.regex.Pattern;

/**
 * Host-persistent, cross-process nonce SETNX store.
 *
 * <p>Each claim is an owner-only file created with {@code O_EXCL}. The content is its expiry;
 * expired records are retired with an atomic rename before a replacement is attempted. The key
 * binds protocol, role, signer and nonce, so independent authentication domains cannot collide.
 * Production mounts an explicitly pre-created owner-only host directory so the records survive
 * process and container restarts without relying on root-owned empty-volume defaults.</p>
 */
public final class FileNonceStore {
    private static final String RECORD_VERSION = "ELMOS-SPRING-NONCE-V1";
    private static final Pattern TOKEN = Pattern.compile("[A-Z][A-Z0-9._-]{2,95}");
    private static final Pattern UUID_PATTERN = Pattern.compile(
            "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                    + "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");
    private static final Pattern RECORD_NAME = Pattern.compile("[0-9a-f]{64}\\.nonce");
    private static final Set<PosixFilePermission> DIRECTORY_PERMISSIONS = Set.of(
            PosixFilePermission.OWNER_READ,
            PosixFilePermission.OWNER_WRITE,
            PosixFilePermission.OWNER_EXECUTE);
    private static final Set<PosixFilePermission> FILE_PERMISSIONS = Set.of(
            PosixFilePermission.OWNER_READ,
            PosixFilePermission.OWNER_WRITE);
    private static final long MAX_TTL_SECONDS = 600;
    private static final int MAX_PRUNE_PER_CLAIM = 32;
    private static final String LOCK_FILE_NAME = ".nonce-store.lock";
    private static final ConcurrentMap<Path, ReentrantLock> JVM_LOCKS = new ConcurrentHashMap<>();

    private final Path root;
    private final Clock clock;
    private final Object rootFileKey;
    private final long processUid;
    private final Path lockFile;
    private final Object lockFileKey;
    private final ReentrantLock jvmLock;

    public FileNonceStore(Path root, Clock clock) {
        this.root = requireRoot(root);
        this.clock = Objects.requireNonNull(clock, "clock");
        this.processUid = currentUid();
        initializeRoot();
        this.rootFileKey = validateRoot().fileKey();
        if (rootFileKey == null) {
            throw new IllegalStateException("nonce store root has no stable filesystem identity");
        }
        this.lockFile = root.resolve(LOCK_FILE_NAME);
        this.lockFileKey = initializeLockFile();
        this.jvmLock = JVM_LOCKS.computeIfAbsent(realRoot(), ignored -> new ReentrantLock());
    }

    public boolean claim(
            SpringHmacProtocol.Role role,
            String signer,
            String nonce,
            Instant expiresAt
    ) {
        Objects.requireNonNull(role, "role");
        return claim(
                SpringHmacProtocol.VERSION, role.wireName(), signer, nonce, expiresAt);
    }

    public boolean claim(
            String protocol,
            String role,
            String signer,
            String nonce,
            Instant expiresAt
    ) {
        requireToken(protocol, "protocol");
        requireToken(role, "role");
        requireToken(signer, "signer");
        if (nonce == null || !UUID_PATTERN.matcher(nonce).matches()) {
            throw new IllegalArgumentException("nonce is invalid");
        }
        Objects.requireNonNull(expiresAt, "expiresAt");
        long now = clock.instant().getEpochSecond();
        long expiry = expiresAt.getEpochSecond();
        if (expiry < now || expiry > Math.addExact(now, MAX_TTL_SECONDS)) {
            throw new IllegalArgumentException("nonce expiry is outside the bounded window");
        }
        String digest = SpringHmacProtocol.sha256(String.join("\u0000",
                protocol, role, signer, nonce).getBytes(StandardCharsets.UTF_8));
        Path record = root.resolve(digest + ".nonce");
        jvmLock.lock();
        try (FileChannel channel = FileChannel.open(
                lockFile,
                Set.of(StandardOpenOption.READ, StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS));
             FileLock ignored = channel.lock()) {
            validateRootIdentity();
            validateRecordFile(lockFile, lockFileKey, true);
            pruneExpired(now);
            for (int attempt = 0; attempt < 4; attempt++) {
                if (createRecord(record, expiry)) return true;
                Long existingExpiry = readExpiry(record);
                if (existingExpiry == null || existingExpiry >= now) return false;
                retire(record);
            }
            throw new IllegalStateException("nonce store could not atomically settle a claim");
        } catch (IOException error) {
            throw new IllegalStateException("nonce store lock could not be acquired", error);
        } finally {
            jvmLock.unlock();
        }
    }

    private boolean createRecord(Path record, long expiry) {
        Object createdFileKey = null;
        try (FileChannel channel = FileChannel.open(
                record,
                Set.of(StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE),
                PosixFilePermissions.asFileAttribute(FILE_PERMISSIONS))) {
            BasicFileAttributes created = Files.readAttributes(
                    record, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            createdFileKey = created.fileKey();
            byte[] encoded = (RECORD_VERSION + "\n" + expiry + "\n")
                    .getBytes(StandardCharsets.US_ASCII);
            ByteBuffer buffer = ByteBuffer.wrap(encoded);
            int zeroWrites = 0;
            while (buffer.hasRemaining()) {
                int count = channel.write(buffer);
                if (count == 0 && ++zeroWrites > 8) {
                    throw new IOException("nonce record write made no progress");
                }
                if (count > 0) zeroWrites = 0;
            }
            channel.force(true);
            validateRecord(record, createdFileKey);
            forceDirectory();
            return true;
        } catch (FileAlreadyExistsException error) {
            return false;
        } catch (IOException | RuntimeException error) {
            cleanupCreatedRecord(record, createdFileKey);
            throw new IllegalStateException("nonce claim could not be persisted", error);
        }
    }

    private Long readExpiry(Path record) {
        try {
            BasicFileAttributes attributes = validateRecord(record, null);
            if (attributes.size() < 25) {
                // CREATE_NEW exposes the inode before its first fsync. Treat an in-progress or
                // crash-truncated record as an active claim; never reopen a replay window.
                return Long.MAX_VALUE;
            }
            if (attributes.size() > 64) {
                throw new IllegalStateException("nonce record size is invalid");
            }
            byte[] bytes = Files.readAllBytes(record);
            BasicFileAttributes after = validateRecord(record, attributes.fileKey());
            if (attributes.size() != after.size()
                    || !attributes.lastModifiedTime().equals(after.lastModifiedTime())) {
                return Long.MAX_VALUE;
            }
            String[] lines = new String(bytes, StandardCharsets.US_ASCII).split("\\n", -1);
            if (lines.length != 3
                    || !RECORD_VERSION.equals(lines[0])
                    || !lines[1].matches("[0-9]{1,20}")
                    || !lines[2].isEmpty()) {
                return Long.MAX_VALUE;
            }
            return Long.parseLong(lines[1]);
        } catch (NoSuchFileException error) {
            return null;
        } catch (IOException | NumberFormatException error) {
            throw new IllegalStateException("nonce record could not be read", error);
        }
    }

    private BasicFileAttributes validateRecord(Path record, Object expectedFileKey)
            throws IOException {
        return validateRecordFile(record, expectedFileKey, false);
    }

    private BasicFileAttributes validateRecordFile(
            Path record,
            Object expectedFileKey,
            boolean persistentLock
    ) throws IOException {
        BasicFileAttributes attributes = Files.readAttributes(
                record, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (!attributes.isRegularFile()
                || attributes.isSymbolicLink()
                || attributes.fileKey() == null
                || (expectedFileKey != null && !expectedFileKey.equals(attributes.fileKey()))) {
            throw new IllegalStateException((persistentLock ? "nonce lock" : "nonce record")
                    + " filesystem identity is invalid");
        }
        if (!Files.getPosixFilePermissions(record, LinkOption.NOFOLLOW_LINKS)
                .equals(FILE_PERMISSIONS)) {
            throw new IllegalStateException(
                    (persistentLock ? "nonce lock" : "nonce record") + " mode must be 0600");
        }
        Map<String, Object> unix = Files.readAttributes(
                record, "unix:uid,nlink", LinkOption.NOFOLLOW_LINKS);
        if (!(unix.get("uid") instanceof Number uid)
                || uid.longValue() != processUid
                || !(unix.get("nlink") instanceof Number links)
                || links.longValue() != 1) {
            throw new IllegalStateException((persistentLock ? "nonce lock" : "nonce record")
                    + " ownership or link count is invalid");
        }
        return attributes;
    }

    private void retire(Path record) {
        Path tombstone = root.resolve("." + record.getFileName() + "."
                + UUID.randomUUID() + ".expired");
        try {
            Files.move(record, tombstone, StandardCopyOption.ATOMIC_MOVE);
            forceDirectory();
            Files.delete(tombstone);
            forceDirectory();
        } catch (NoSuchFileException ignored) {
            // A competing process already retired the expired record; retry CREATE_NEW.
        } catch (AtomicMoveNotSupportedException error) {
            throw new IllegalStateException(
                    "nonce store filesystem does not support atomic expiry", error);
        } catch (IOException error) {
            throw new IllegalStateException("expired nonce record could not be retired", error);
        }
    }

    private void pruneExpired(long now) {
        int inspected = 0;
        try (DirectoryStream<Path> entries = Files.newDirectoryStream(root, "*.nonce")) {
            for (Path entry : entries) {
                if (++inspected > MAX_PRUNE_PER_CLAIM) break;
                if (!RECORD_NAME.matcher(entry.getFileName().toString()).matches()) continue;
                Long expiry = readExpiry(entry);
                if (expiry != null && expiry < now) retire(entry);
            }
        } catch (IOException error) {
            throw new IllegalStateException("nonce store could not prune expired records", error);
        }
    }

    private void initializeRoot() {
        ensureNoSymlinkParents(root);
        try {
            if (!Files.exists(root, LinkOption.NOFOLLOW_LINKS)) {
                Files.createDirectories(
                        root, PosixFilePermissions.asFileAttribute(DIRECTORY_PERMISSIONS));
                Files.setPosixFilePermissions(root, DIRECTORY_PERMISSIONS);
                forceDirectory();
            }
        } catch (IOException error) {
            throw new IllegalStateException("nonce store root could not be initialized", error);
        }
    }

    private Object initializeLockFile() {
        try {
            try (FileChannel channel = FileChannel.open(
                    lockFile,
                    Set.of(StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE),
                    PosixFilePermissions.asFileAttribute(FILE_PERMISSIONS))) {
                channel.force(true);
            } catch (FileAlreadyExistsException ignored) {
                // Another instance initialized the permanent lock; validate it below.
            }
            BasicFileAttributes attributes = validateRecordFile(lockFile, null, true);
            forceDirectory();
            return attributes.fileKey();
        } catch (IOException error) {
            throw new IllegalStateException("nonce store lock could not be initialized", error);
        }
    }

    private BasicFileAttributes validateRoot() {
        try {
            BasicFileAttributes attributes = Files.readAttributes(
                    root, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            if (!attributes.isDirectory()
                    || attributes.isSymbolicLink()
                    || !Files.getPosixFilePermissions(root, LinkOption.NOFOLLOW_LINKS)
                    .equals(DIRECTORY_PERMISSIONS)) {
                throw new IllegalStateException(
                        "nonce store root must be an owner-only 0700 directory");
            }
            Object uid = Files.getAttribute(root, "unix:uid", LinkOption.NOFOLLOW_LINKS);
            if (!(uid instanceof Number owner) || owner.longValue() != processUid) {
                throw new IllegalStateException(
                        "nonce store root must be owned by the current process user");
            }
            return attributes;
        } catch (IOException | UnsupportedOperationException error) {
            throw new IllegalStateException(
                    "nonce store requires POSIX ownership and filesystem metadata", error);
        }
    }

    private void validateRootIdentity() {
        BasicFileAttributes current = validateRoot();
        if (!rootFileKey.equals(current.fileKey())) {
            throw new IllegalStateException("nonce store root filesystem identity changed");
        }
    }

    private Path realRoot() {
        try {
            Path real = root.toRealPath(LinkOption.NOFOLLOW_LINKS);
            if (!real.equals(root)) {
                throw new IllegalStateException(
                        "nonce store root must not be reachable through a path alias");
            }
            return real;
        } catch (IOException error) {
            throw new IllegalStateException("nonce store root identity is unavailable", error);
        }
    }

    private void forceDirectory() throws IOException {
        try (FileChannel directory = FileChannel.open(root, StandardOpenOption.READ)) {
            directory.force(true);
        }
    }

    private void cleanupCreatedRecord(Path record, Object createdFileKey) {
        if (createdFileKey == null) return;
        try {
            BasicFileAttributes current = Files.readAttributes(
                    record, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            if (createdFileKey.equals(current.fileKey())) {
                Files.delete(record);
                forceDirectory();
            }
        } catch (IOException ignored) {
            // Fail closed: never unlink a path whose identity cannot be proven to be ours.
        }
    }

    private static void ensureNoSymlinkParents(Path path) {
        Path current = path.getRoot();
        try {
            for (Path component : path) {
                current = current.resolve(component);
                if (!Files.exists(current, LinkOption.NOFOLLOW_LINKS)) break;
                BasicFileAttributes attributes = Files.readAttributes(
                        current, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
                if (attributes.isSymbolicLink()) {
                    throw new IllegalStateException(
                            "nonce store path must not contain symbolic links");
                }
            }
        } catch (IOException error) {
            throw new IllegalStateException("nonce store path could not be inspected", error);
        }
    }

    private static Path requireRoot(Path value) {
        Objects.requireNonNull(value, "root");
        if (!value.isAbsolute() || !value.equals(value.normalize())) {
            throw new IllegalArgumentException(
                    "nonce store root must be an absolute normalized path");
        }
        return value;
    }

    private static void requireToken(String value, String label) {
        if (value == null || !TOKEN.matcher(value).matches()) {
            throw new IllegalArgumentException("nonce " + label + " is invalid");
        }
    }

    private static long currentUid() {
        try {
            if (System.getProperty("os.name", "").equalsIgnoreCase("Linux")) {
                return SpringHmacProtocol.parseEffectiveUid(Files.readString(
                        Path.of("/proc/self/status"), StandardCharsets.US_ASCII));
            }
            Object uid = Files.getAttribute(
                    Path.of(System.getProperty("user.home", ""))
                            .toAbsolutePath().normalize(),
                    "unix:uid");
            if (uid instanceof Number number) return number.longValue();
        } catch (IOException | RuntimeException error) {
            throw new IllegalStateException("current process UID is unavailable", error);
        }
        throw new IllegalStateException("current process UID is unavailable");
    }
}
