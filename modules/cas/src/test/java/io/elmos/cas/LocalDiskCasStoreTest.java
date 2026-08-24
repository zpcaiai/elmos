package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

class LocalDiskCasStoreTest {

    private static byte[] bytes(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    private LocalDiskCasStore store() throws IOException {
        return new LocalDiskCasStore("l1", Files.createTempDirectory("elmos-cas-"));
    }

    @Test void uploadAndDownloadRoundTrip() throws IOException {
        LocalDiskCasStore store = store();
        byte[] content = bytes("hello elmos");
        CasDigest digest = CasDigest.of(content);
        store.put(digest, content);
        assertTrue(store.contains(digest));
        assertArrayEquals(content, store.get(digest));
        assertEquals(content.length, store.totalBytes());
        assertEquals(List.of(digest), new ArrayList<>(store.inventory()));
    }

    @Test void storingContentUnderAForeignDigestIsRefused() throws IOException {
        LocalDiskCasStore store = store();
        CasDigest lie = CasDigest.of(bytes("expected"));
        var error = assertThrows(CasExceptions.CasCorruptionException.class,
                () -> store.put(lie, bytes("actual")));
        assertEquals(lie, error.expected());
        assertFalse(store.contains(lie));
    }

    @Test void poisonedObjectIsQuarantinedOnReadRatherThanServed() throws IOException {
        LocalDiskCasStore store = store();
        byte[] content = bytes("trusted artifact");
        CasDigest digest = CasDigest.of(content);
        store.put(digest, content);

        Files.write(store.pathFor(digest), bytes("poisoned artifact"));

        assertThrows(CasExceptions.CasCorruptionException.class, () -> store.get(digest));
        assertFalse(Files.exists(store.pathFor(digest)));
        assertEquals(1, store.quarantinedPaths().size());
    }

    @Test void truncatedObjectFailsExistenceCheckOnSize() throws IOException {
        LocalDiskCasStore store = store();
        byte[] content = bytes("0123456789");
        CasDigest digest = CasDigest.of(content);
        store.put(digest, content);
        Files.write(store.pathFor(digest), bytes("01234"));
        assertFalse(store.contains(digest));
    }

    @Test void rangeReadsServeSlicesWithoutMaterialisingTheWholeObject() throws IOException {
        LocalDiskCasStore store = store();
        byte[] content = bytes("abcdefghij");
        CasDigest digest = CasDigest.of(content);
        store.put(digest, content);
        assertArrayEquals(bytes("cde"), store.readRange(digest, 2, 3));
        assertArrayEquals(bytes("ij"), store.readRange(digest, 8, 100));
        assertThrows(IllegalArgumentException.class, () -> store.readRange(digest, 11, 1));
    }

    @Test void concurrentWritersOfIdenticalContentBothSucceed() throws Exception {
        LocalDiskCasStore store = store();
        byte[] content = bytes("shared output artifact");
        CasDigest digest = CasDigest.of(content);
        int writers = 8;
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(writers);
        AtomicInteger failures = new AtomicInteger();
        for (int index = 0; index < writers; index++) {
            new Thread(() -> {
                try {
                    start.await();
                    store.put(digest, content);
                } catch (Exception error) {
                    failures.incrementAndGet();
                } finally {
                    done.countDown();
                }
            }).start();
        }
        start.countDown();
        assertTrue(done.await(20, TimeUnit.SECONDS));
        assertEquals(0, failures.get());
        assertArrayEquals(content, store.get(digest));
        assertEquals(1, store.inventory().size());
    }

    @Test void duplicateStoresAreIdempotentAndDoNotRewriteTheObject() throws IOException {
        LocalDiskCasStore store = store();
        byte[] content = bytes("idempotent");
        CasDigest digest = CasDigest.of(content);
        store.put(digest, content);
        Path path = store.pathFor(digest);
        long firstModified = Files.getLastModifiedTime(path).toMillis();
        store.put(digest, content);
        assertEquals(firstModified, Files.getLastModifiedTime(path).toMillis());
    }

    @Test void missingObjectsAreReportedInCallerOrder() throws IOException {
        LocalDiskCasStore store = store();
        CasDigest present = CasDigest.of(bytes("present"));
        CasDigest absentOne = CasDigest.of(bytes("absent-1"));
        CasDigest absentTwo = CasDigest.of(bytes("absent-2"));
        store.put(present, bytes("present"));
        assertEquals(List.of(absentOne, absentTwo),
                new ArrayList<>(store.missing(List.of(absentOne, present, absentTwo))));
    }

    @Test void streamingDigestMatchesInMemoryDigest() throws IOException {
        LocalDiskCasStore store = store();
        Path file = Files.createTempFile("blob-", ".bin");
        byte[] content = new byte[300_000];
        for (int index = 0; index < content.length; index++) {
            content[index] = (byte) (index % 251);
        }
        Files.write(file, content);
        assertEquals(CasDigest.of(content), store.digestOf(file));
    }
}
