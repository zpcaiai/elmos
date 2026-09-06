package io.elmos.cas;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.io.ByteArrayInputStream;
import java.nio.file.Path;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

class CasStreamingConcurrencyTest {
    @TempDir Path root;

    @Test void streamingLocalRoundTripVerifiesBeforeExposureAndOwnsItsBytes() throws Exception {
        var store = new LocalDiskCasStore("disk", root);
        byte[] bytes = new byte[256 * 1024];
        new java.util.Random(42).nextBytes(bytes);
        var digest = CasDigest.of(bytes);
        store.putDurable(digest, new ByteArrayInputStream(bytes));
        try (var input = store.openVerified(digest)) {
            java.nio.file.Files.write(store.pathFor(digest), new byte[bytes.length]);
            assertArrayEquals(bytes, input.readAllBytes(), "a verified stream is independent of a later rewrite");
        }
        assertThrows(CasExceptions.CasCorruptionException.class, () -> store.openVerified(digest));
        assertFalse(store.contains(digest));
    }

    @Test void independentMissesProgressAndSameDigestFetchesCoalesce() throws Exception {
        var remote = new BlockingStore();
        var tier = new TieredCasStore(new InMemoryCasStore("local"), remote,
                TieredCasStore.TierPolicy.unbounded(), System::currentTimeMillis);
        try (var pool = Executors.newFixedThreadPool(8)) {
            var first = pool.submit(() -> tier.get(remote.slow));
            try {
                assertTrue(remote.entered.await(3, TimeUnit.SECONDS));
                var same = pool.submit(() -> tier.get(remote.slow));
                assertArrayEquals("fast".getBytes(), pool.submit(() -> tier.get(remote.fast))
                        .get(3, TimeUnit.SECONDS));
                remote.release.countDown();
                assertArrayEquals(first.get(3, TimeUnit.SECONDS), same.get(3, TimeUnit.SECONDS));
                assertEquals(1, remote.slowReads.get());
            } finally { remote.release.countDown(); }
        }
    }

    private static final class BlockingStore implements CasStore {
        final InMemoryCasStore delegate = new InMemoryCasStore("remote");
        final CasDigest slow = CasDigest.ofUtf8("slow");
        final CasDigest fast = CasDigest.ofUtf8("fast");
        final CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
        final AtomicInteger slowReads = new AtomicInteger();
        BlockingStore() { delegate.put(slow, "slow".getBytes()); delegate.put(fast, "fast".getBytes()); }
        public String name() { return "remote"; }
        public boolean contains(CasDigest digest) { return delegate.contains(digest); }
        public void put(CasDigest digest, byte[] content) { delegate.put(digest, content); }
        public byte[] get(CasDigest digest) {
            if (digest.equals(slow)) {
                slowReads.incrementAndGet(); entered.countDown();
                try { if (!release.await(10, TimeUnit.SECONDS)) throw new IllegalStateException("test deadline"); }
                catch (InterruptedException error) { Thread.currentThread().interrupt(); throw new IllegalStateException(error); }
            }
            return delegate.get(digest);
        }
        public byte[] readRange(CasDigest digest, long offset, int length) { return delegate.readRange(digest, offset, length); }
        public boolean delete(CasDigest digest) { return delegate.delete(digest); }
        public Set<CasDigest> inventory() { return delegate.inventory(); }
        public long totalBytes() { return delegate.totalBytes(); }
    }
}
