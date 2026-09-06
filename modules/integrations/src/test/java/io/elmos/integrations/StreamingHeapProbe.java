package io.elmos.integrations;

import io.elmos.cas.CasDigest;
import io.elmos.cas.LocalDiskCasStore;
import io.elmos.snapshot.DeterministicSnapshotArchiver;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Random;

/** Execute in a separate JVM with -Xmx64m; input is twice the entire heap. */
public final class StreamingHeapProbe {
    public static void main(String[] args) throws Exception {
        var root = Files.createTempDirectory("elmos-streaming-heap-");
        try {
            var source = Files.createDirectory(root.resolve("source"));
            byte[] buffer = new byte[65536];
            var random = new Random(417);
            try (var output = Files.newOutputStream(source.resolve("large.bin"))) {
                for (int i = 0; i < 2048; i++) {
                    random.nextBytes(buffer);
                    output.write(buffer);
                }
            }
            var limits = new DeterministicSnapshotArchiver.Limits(8, 8, 128L << 20, 128L << 20);
            var archiver = new DeterministicSnapshotArchiver(limits);
            var context = new DeterministicSnapshotArchiver.SnapshotContext("local", "probe", "probe", "head", "a".repeat(40), "b".repeat(40));
            long start = System.nanoTime();
            try (var spool = archiver.spool(source, context)) {
                var meta = spool.metadata();
                var digest = new CasDigest("sha256", meta.archiveSha256(), meta.archiveSize());
                var store = new LocalDiskCasStore("heap-probe", root.resolve("cas"));
                try (var input = spool.openStream()) { store.putDurable(digest, input); }
                var hash = MessageDigest.getInstance("SHA-256");
                try (var input = store.openVerified(digest)) {
                    int count;
                    while ((count = input.read(buffer)) != -1) hash.update(buffer, 0, count);
                }
                if (!HexFormat.of().formatHex(hash.digest()).equals(digest.hex())) throw new AssertionError("digest parity");
                System.out.printf("STREAMING_HEAP_PASS source_bytes=%d heap_max=%d archive_bytes=%d elapsed_ms=%d%n",
                        128L << 20, Runtime.getRuntime().maxMemory(), meta.archiveSize(), (System.nanoTime()-start)/1_000_000);
            }
        } finally {
            try (var paths = Files.walk(root)) {
                for (var path : paths.sorted(java.util.Comparator.reverseOrder()).toList()) Files.delete(path);
            }
        }
    }
}
