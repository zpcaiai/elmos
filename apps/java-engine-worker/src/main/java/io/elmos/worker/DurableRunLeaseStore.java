package io.elmos.worker;

import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.HexFormat;
import java.util.Objects;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantLock;
import java.util.stream.Stream;

/**
 * Filesystem-backed, cross-process admission leases for one exact business line.
 *
 * <p>Run state remains the authoritative queue record. Lease files only grant
 * bounded execution authority and are safe to expire after missed heartbeats.</p>
 */
final class DurableRunLeaseStore {
    /*
     * In-process monitors, one per queue lock file.
     *
     * java.nio.channels.FileLock is held on behalf of the entire JVM rather
     * than the acquiring thread. A second overlapping request from the same
     * JVM therefore throws OverlappingFileLockException instead of blocking,
     * so the file lock alone does not serialise concurrent runs inside one
     * worker. Keyed by the normalised lock path so that two store instances
     * addressing the same queue in one JVM share a single monitor.
     */
    private static final ConcurrentHashMap<Path, ReentrantLock> PROCESS_LOCKS =
            new ConcurrentHashMap<>();

    enum Failure {
        QUEUE_ITEM_EXPIRED(false),
        QUEUE_GLOBAL_CAPACITY_REACHED(true),
        QUEUE_TENANT_CAPACITY_REACHED(true),
        QUEUE_JOB_ALREADY_LEASED(true),
        QUEUE_LEASE_LOST(false);

        private final boolean retryable;
        Failure(boolean retryable) { this.retryable = retryable; }
        boolean retryable() { return retryable; }
    }

    static final class LeaseException extends RuntimeException {
        private final Failure failure;
        LeaseException(Failure failure) {
            super(failure.name());
            this.failure = failure;
        }
        Failure failure() { return failure; }
    }

    final class Lease implements AutoCloseable {
        private final String tenantDigest;
        private final String runId;
        private final String inputDigest;
        private final String ownerId;
        private boolean released;

        private Lease(String tenantDigest, String runId, String inputDigest, String ownerId) {
            this.tenantDigest = tenantDigest;
            this.runId = runId;
            this.inputDigest = inputDigest;
            this.ownerId = ownerId;
        }

        Duration heartbeatInterval() { return leaseTtl.dividedBy(3); }

        void heartbeat() {
            withLock(() -> {
                Properties current = readOwnedLease();
                requireOwned(current, tenantDigest, runId, inputDigest, ownerId);
                Instant now = clock.instant();
                current.setProperty("heartbeatAt", now.toString());
                current.setProperty("expiresAt", now.plus(leaseTtl).toString());
                atomicStore(leasePath(tenantDigest, runId), current);
                return null;
            });
        }

        void release(String outcome) {
            if (released) return;
            withLock(() -> {
                Path lease = leasePath(tenantDigest, runId);
                Properties current = readOwnedLease();
                requireOwned(current, tenantDigest, runId, inputDigest, ownerId);
                current.setProperty("releasedAt", clock.instant().toString());
                current.setProperty("outcome", requireToken(outcome, "outcome"));
                Path receipt = confined(receiptsRoot, tenantDigest, runId + ".properties");
                atomicStore(receipt, current);
                Files.delete(lease);
                released = true;
                return null;
            });
        }

        private Properties readOwnedLease() {
            try {
                return readLease(leasePath(tenantDigest, runId));
            } catch (RuntimeException error) {
                throw new LeaseException(Failure.QUEUE_LEASE_LOST);
            }
        }

        @Override public void close() {
            if (!released) release("BLOCKED");
        }
    }

    private final Path root;
    private final Path leasesRoot;
    private final Path receiptsRoot;
    private final Path deadRoot;
    private final Path lockPath;
    private final String line;
    private final int globalCapacity;
    private final int tenantCapacity;
    private final Duration queueTtl;
    private final Duration leaseTtl;
    private final Clock clock;

    DurableRunLeaseStore(
            Path runnerRoot,
            String line,
            int globalCapacity,
            int tenantCapacity,
            Duration queueTtl,
            Duration leaseTtl,
            Clock clock
    ) {
        Path normalized = Objects.requireNonNull(runnerRoot).toAbsolutePath().normalize();
        if (normalized.getParent() == null
                || line == null || !line.matches("[a-z][a-z0-9-]{2,40}")
                || globalCapacity < 1 || globalCapacity > 1_000
                || tenantCapacity < 1 || tenantCapacity > globalCapacity
                || queueTtl == null || queueTtl.compareTo(Duration.ofMinutes(1)) < 0
                || queueTtl.compareTo(Duration.ofDays(30)) > 0
                || leaseTtl == null || leaseTtl.compareTo(Duration.ofSeconds(30)) < 0
                || leaseTtl.compareTo(Duration.ofHours(1)) > 0) {
            throw new IllegalArgumentException("durable queue configuration is invalid");
        }
        this.root = normalized.resolve(".durable-queue").normalize();
        this.line = line;
        this.globalCapacity = globalCapacity;
        this.tenantCapacity = tenantCapacity;
        this.queueTtl = queueTtl;
        this.leaseTtl = leaseTtl;
        this.clock = Objects.requireNonNull(clock);
        this.leasesRoot = confined(root, "leases", line);
        this.receiptsRoot = confined(root, "receipts", line);
        this.deadRoot = confined(root, "dead-letter", line);
        this.lockPath = confined(root, "control", line + ".lock");
        try {
            Files.createDirectories(leasesRoot);
            Files.createDirectories(receiptsRoot);
            Files.createDirectories(deadRoot);
            Files.createDirectories(lockPath.getParent());
        } catch (IOException error) {
            throw new IllegalStateException("durable queue root unavailable", error);
        }
    }

    Lease acquire(
            String tenantId,
            String runId,
            Instant createdAt,
            String inputDigest
    ) {
        requireToken(tenantId, "tenantId");
        if (runId == null || !runId.matches(
                "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")) {
            throw new IllegalArgumentException("runId is invalid");
        }
        if (inputDigest == null || !inputDigest.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("inputDigest is invalid");
        }
        if (createdAt == null || !createdAt.plus(queueTtl).isAfter(clock.instant())) {
            throw new LeaseException(Failure.QUEUE_ITEM_EXPIRED);
        }
        String tenantDigest = sha256Text(tenantId);
        String ownerId = ManagementFactory.getRuntimeMXBean().getName() + "-" + UUID.randomUUID();
        return withLock(() -> {
            List<Properties> active = activeLeases();
            if (active.stream().anyMatch(value -> runId.equals(value.getProperty("runId")))) {
                throw new LeaseException(Failure.QUEUE_JOB_ALREADY_LEASED);
            }
            if (active.size() >= globalCapacity) {
                throw new LeaseException(Failure.QUEUE_GLOBAL_CAPACITY_REACHED);
            }
            long tenantActive = active.stream()
                    .filter(value -> tenantDigest.equals(value.getProperty("tenantDigest")))
                    .count();
            if (tenantActive >= tenantCapacity) {
                throw new LeaseException(Failure.QUEUE_TENANT_CAPACITY_REACHED);
            }
            Instant now = clock.instant();
            Properties properties = new Properties();
            properties.setProperty("schemaVersion", "1.0");
            properties.setProperty("line", line);
            properties.setProperty("tenantDigest", tenantDigest);
            properties.setProperty("runId", runId);
            properties.setProperty("ownerId", ownerId);
            properties.setProperty("inputDigest", inputDigest);
            properties.setProperty("acquiredAt", now.toString());
            properties.setProperty("heartbeatAt", now.toString());
            properties.setProperty("expiresAt", now.plus(leaseTtl).toString());
            Path destination = leasePath(tenantDigest, runId);
            try {
                Files.createDirectories(destination.getParent());
                try (var output = Files.newOutputStream(
                        destination, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
                    properties.store(output, "ELMOS durable execution lease");
                }
            } catch (java.nio.file.FileAlreadyExistsException error) {
                throw new LeaseException(Failure.QUEUE_JOB_ALREADY_LEASED);
            }
            return new Lease(tenantDigest, runId, inputDigest, ownerId);
        });
    }

    private List<Properties> activeLeases() throws IOException {
        List<Properties> active = new ArrayList<>();
        if (!Files.exists(leasesRoot)) return active;
        try (Stream<Path> stream = Files.walk(leasesRoot, 2)) {
            for (Path path : stream.filter(Files::isRegularFile).sorted(Comparator.naturalOrder()).toList()) {
                if (!path.getFileName().toString().endsWith(".properties")) continue;
                Properties value;
                try {
                    value = readLease(path);
                } catch (RuntimeException error) {
                    Files.move(path, confined(deadRoot, "corrupt-" + UUID.randomUUID() + ".properties"));
                    continue;
                }
                if (!Instant.parse(value.getProperty("expiresAt")).isAfter(clock.instant())) {
                    Files.move(path, confined(deadRoot,
                            "expired-" + value.getProperty("tenantDigest") + "-"
                                    + value.getProperty("runId") + "-" + UUID.randomUUID()
                                    + ".properties"));
                    continue;
                }
                active.add(value);
            }
        }
        return active;
    }

    private Properties readLease(Path path) {
        if (Files.isSymbolicLink(path)
                || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
            throw new IllegalStateException("durable lease is not a regular file");
        }
        Properties properties = new Properties();
        try (var input = Files.newInputStream(path)) {
            properties.load(input);
        } catch (IOException error) {
            throw new IllegalStateException("durable lease unreadable", error);
        }
        if (!"1.0".equals(properties.getProperty("schemaVersion"))
                || !line.equals(properties.getProperty("line"))
                || !properties.getProperty("tenantDigest", "").matches("[0-9a-f]{64}")
                || !properties.getProperty("runId", "").matches(
                        "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
                || !properties.getProperty("inputDigest", "").matches("[0-9a-f]{64}")
                || properties.getProperty("ownerId", "").isBlank()) {
            throw new IllegalStateException("durable lease contract invalid");
        }
        Instant.parse(properties.getProperty("expiresAt"));
        return properties;
    }

    private void requireOwned(
            Properties properties,
            String tenantDigest,
            String runId,
            String inputDigest,
            String ownerId
    ) {
        if (!tenantDigest.equals(properties.getProperty("tenantDigest"))
                || !runId.equals(properties.getProperty("runId"))
                || !inputDigest.equals(properties.getProperty("inputDigest"))
                || !ownerId.equals(properties.getProperty("ownerId"))
                || !Instant.parse(properties.getProperty("expiresAt")).isAfter(clock.instant())) {
            throw new LeaseException(Failure.QUEUE_LEASE_LOST);
        }
    }

    private void atomicStore(Path destination, Properties value) throws IOException {
        Files.createDirectories(destination.getParent());
        Path temporary = destination.resolveSibling(
                destination.getFileName() + "." + UUID.randomUUID() + ".tmp");
        try (var output = Files.newOutputStream(
                temporary, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
            value.store(output, "ELMOS durable queue record");
        }
        Files.move(temporary, destination,
                StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
    }

    /**
     * Runs one queue mutation under both exclusion levels. Neither level alone
     * is sufficient: the in-process monitor serialises threads within this JVM,
     * which FileLock deliberately does not do, and the file lock serialises the
     * several worker JVMs that may share one queue root.
     *
     * <p>Before the in-process monitor existed, a heartbeat overlapping an
     * admission attempt raised OverlappingFileLockException. That exception is
     * unchecked and neither catch clause below matches it, so it surfaced to the
     * caller, which reads any heartbeat failure as a lost lease and destroys the
     * run's build process. A healthy run was cancelled because an unrelated run
     * happened to be admitted at the same moment.</p>
     */
    private <T> T withLock(IoSupplier<T> operation) {
        ReentrantLock processLock =
                PROCESS_LOCKS.computeIfAbsent(lockPath, key -> new ReentrantLock());
        processLock.lock();
        try (FileChannel channel = FileChannel.open(
                lockPath, StandardOpenOption.CREATE, StandardOpenOption.WRITE);
             FileLock ignored = channel.lock()) {
            return operation.get();
        } catch (LeaseException error) {
            throw error;
        } catch (IOException error) {
            throw new IllegalStateException("durable queue lock unavailable", error);
        } finally {
            processLock.unlock();
        }
    }

    private Path leasePath(String tenantDigest, String runId) {
        return confined(leasesRoot, tenantDigest, runId + ".properties");
    }

    private static Path confined(Path root, String... segments) {
        Path candidate = root.resolve(Path.of("", segments)).normalize();
        if (!candidate.startsWith(root)) throw new SecurityException("durable queue path escaped root");
        return candidate;
    }

    private static String requireToken(String value, String field) {
        if (value == null || value.isBlank() || value.length() > 160
                || value.indexOf('\0') >= 0 || value.indexOf('\n') >= 0) {
            throw new IllegalArgumentException(field + " is invalid");
        }
        return value;
    }

    private static String sha256Text(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    @FunctionalInterface
    private interface IoSupplier<T> {
        T get() throws IOException;
    }
}
