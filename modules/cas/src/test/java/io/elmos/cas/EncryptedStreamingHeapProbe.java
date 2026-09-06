package io.elmos.cas;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

/** Run separately with -Xmx64m; verifies a 128 MiB encrypted object using the actual stream API. */
public final class EncryptedStreamingHeapProbe {
    public static void main(String[] args) throws Exception {
        long size = 128L * 1024 * 1024;
        Path root = Files.createTempDirectory("elmos-encrypted-heap-");
        try {
            var encryption = new TenantEncryption.AesGcm().registerKey("probe", new byte[32]);
            var store = new TenantEncryptedLocalCasStore("heap-probe", root, encryption).forTenant("probe");
            CasHasher hash = new CasHasher();
            byte[] buffer = new byte[65536];
            try (InputStream input = source(size)) {
                int count;
                while ((count = input.read(buffer)) != -1) hash.update(buffer, 0, count);
            }
            CasDigest expected = hash.finish();
            long start = System.nanoTime();
            try (InputStream input = source(size)) { store.putDurable(expected, input); }
            CasHasher observed = new CasHasher();
            try (InputStream input = store.openVerified(expected)) {
                int count;
                while ((count = input.read(buffer)) != -1) observed.update(buffer, 0, count);
            }
            if (!expected.equals(observed.finish())) throw new AssertionError("encrypted streaming digest differs");
            System.out.println("ENCRYPTED_STREAM_HEAP_PASS size=" + size + " elapsed_ms="
                    + (System.nanoTime() - start) / 1_000_000 + " max_heap=" + Runtime.getRuntime().maxMemory());
        } finally {
            try (var paths = Files.walk(root)) {
                for (Path path : paths.sorted(java.util.Comparator.reverseOrder()).toList()) Files.delete(path);
            }
        }
    }

    private static InputStream source(long size) {
        return new InputStream() {
            final java.util.Random random = new java.util.Random(91357);
            long remaining = size;
            @Override public int read() {
                if (remaining == 0) return -1;
                remaining--;
                return random.nextInt(256);
            }
            @Override public int read(byte[] bytes, int offset, int length) {
                if (remaining == 0) return -1;
                int count = (int) Math.min(remaining, length);
                for (int index = 0; index < count; index++) bytes[offset + index] = (byte) random.nextInt(256);
                remaining -= count;
                return count;
            }
        };
    }
}
