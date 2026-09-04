package io.elmos.security;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FileNonceStoreTest {
    private static final Instant NOW = Instant.parse("2026-09-05T00:00:00Z");
    private static final String NONCE = "12345678-1234-4234-8234-123456789abc";

    @TempDir
    Path temporary;

    @Test
    void persistsAtomicClaimsAcrossInstancesAndSeparatesRoleAndSigner() throws Exception {
        Path root = temporary.toRealPath().resolve("replay");
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        FileNonceStore first = new FileNonceStore(root, clock);
        FileNonceStore restarted = new FileNonceStore(root, clock);
        Instant expiry = NOW.plusSeconds(180);

        assertTrue(first.claim(
                SpringHmacProtocol.Role.VERIFIER, "JAVA_ENGINE_WORKER", NONCE, expiry));
        assertFalse(restarted.claim(
                SpringHmacProtocol.Role.VERIFIER, "JAVA_ENGINE_WORKER", NONCE, expiry));
        assertTrue(restarted.claim(
                SpringHmacProtocol.Role.TRANSFORMER, "JAVA_ENGINE_WORKER", NONCE, expiry));
        assertTrue(restarted.claim(
                SpringHmacProtocol.Role.VERIFIER, "OTHER_SIGNER", NONCE, expiry));

        assertEquals(Set.of(
                        PosixFilePermission.OWNER_READ,
                        PosixFilePermission.OWNER_WRITE,
                        PosixFilePermission.OWNER_EXECUTE),
                Files.getPosixFilePermissions(root));
        try (var records = Files.list(root)) {
            assertTrue(records.filter(path -> path.getFileName().toString().endsWith(".nonce"))
                    .allMatch(path -> {
                        try {
                            return Files.getPosixFilePermissions(path).equals(Set.of(
                                    PosixFilePermission.OWNER_READ,
                                    PosixFilePermission.OWNER_WRITE));
                        } catch (Exception error) {
                            return false;
                        }
                    }));
        }
    }

    @Test
    void expiryIsStrictAndCanBeReclaimedOnlyAfterTheSignedWindow() throws Exception {
        MutableClock clock = new MutableClock(NOW);
        FileNonceStore store = new FileNonceStore(
                temporary.toRealPath().resolve("expiry-replay"), clock);
        Instant expiry = NOW.plusSeconds(90);

        assertTrue(store.claim(
                SpringHmacProtocol.Role.RUNTIME, "JAVA_ENGINE_WORKER", NONCE, expiry));
        clock.set(expiry);
        assertFalse(store.claim(
                SpringHmacProtocol.Role.RUNTIME, "JAVA_ENGINE_WORKER", NONCE, expiry));
        clock.set(expiry.plusSeconds(1));
        assertTrue(store.claim(
                SpringHmacProtocol.Role.RUNTIME,
                "JAVA_ENGINE_WORKER",
                NONCE,
                expiry.plusSeconds(31)));
    }

    @Test
    void concurrentProcessesHaveOneSetNxWinner() throws Exception {
        Path root = temporary.toRealPath().resolve("concurrent-replay");
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        List<Callable<Boolean>> claims = new ArrayList<>();
        for (int index = 0; index < 16; index++) {
            claims.add(() -> new FileNonceStore(root, clock).claim(
                    SpringHmacProtocol.Role.TRANSFORMER,
                    "JAVA_ENGINE_WORKER",
                    NONCE,
                    NOW.plusSeconds(90)));
        }
        try (var pool = Executors.newFixedThreadPool(8)) {
            long accepted = pool.invokeAll(claims).stream().filter(future -> {
                try {
                    return future.get();
                } catch (Exception error) {
                    throw new IllegalStateException(error);
                }
            }).count();
            assertEquals(1, accepted);
        }
    }

    @Test
    void twoInstancesHaveOneWinnerWhenReplacingAnExpiredClaim() throws Exception {
        MutableClock clock = new MutableClock(NOW);
        Path root = temporary.toRealPath().resolve("expired-concurrent-replay");
        FileNonceStore first = new FileNonceStore(root, clock);
        FileNonceStore second = new FileNonceStore(root, clock);
        assertTrue(first.claim(
                SpringHmacProtocol.Role.VERIFIER,
                "JAVA_ENGINE_WORKER",
                NONCE,
                NOW.plusSeconds(30)));
        clock.set(NOW.plusSeconds(31));

        try (var pool = Executors.newFixedThreadPool(2)) {
            List<Callable<Boolean>> replacements = List.of(
                    () -> first.claim(
                            SpringHmacProtocol.Role.VERIFIER,
                            "JAVA_ENGINE_WORKER",
                            NONCE,
                            NOW.plusSeconds(120)),
                    () -> second.claim(
                            SpringHmacProtocol.Role.VERIFIER,
                            "JAVA_ENGINE_WORKER",
                            NONCE,
                            NOW.plusSeconds(120)));
            long accepted = pool.invokeAll(replacements).stream().filter(future -> {
                try {
                    return future.get();
                } catch (Exception error) {
                    throw new IllegalStateException(error);
                }
            }).count();
            assertEquals(1, accepted);
        }
    }

    @Test
    void rejectsRelativeSymlinkAndInsecureExistingRoots() throws Exception {
        assertThrows(IllegalArgumentException.class,
                () -> new FileNonceStore(Path.of("relative"), Clock.systemUTC()));

        Path insecure = temporary.toRealPath().resolve("insecure");
        Files.createDirectory(insecure);
        Files.setPosixFilePermissions(insecure, Set.of(
                PosixFilePermission.OWNER_READ,
                PosixFilePermission.OWNER_WRITE,
                PosixFilePermission.OWNER_EXECUTE,
                PosixFilePermission.GROUP_READ,
                PosixFilePermission.GROUP_EXECUTE));
        assertThrows(IllegalStateException.class,
                () -> new FileNonceStore(insecure, Clock.systemUTC()));

        Path actual = temporary.toRealPath().resolve("actual");
        Files.createDirectory(actual);
        Path linked = temporary.toRealPath().resolve("linked");
        Files.createSymbolicLink(linked, actual);
        assertThrows(IllegalStateException.class,
                () -> new FileNonceStore(linked.resolve("replay"), Clock.systemUTC()));
    }

    private static final class MutableClock extends Clock {
        private Instant instant;

        private MutableClock(Instant instant) {
            this.instant = instant;
        }

        void set(Instant value) {
            instant = value;
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            if (!ZoneOffset.UTC.equals(zone)) throw new IllegalArgumentException("UTC only");
            return this;
        }

        @Override
        public Instant instant() {
            return instant;
        }
    }
}
