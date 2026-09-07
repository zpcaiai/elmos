package io.elmos.cas;

import java.util.Arrays;
import java.util.Locale;
import java.util.Set;
import java.util.zip.DataFormatException;
import java.util.zip.Deflater;
import java.util.zip.Inflater;

/**
 * ELMOS-CAS-008 and ELMOS-CAS-012. Transfer-shaping decisions that are policy, not mechanism.
 */
public final class TransferPolicy {

    private TransferPolicy() {
    }

    public enum ChunkEncoding {
        NONE,
        DEFLATE
    }

    /**
     * ELMOS-CAS-012. Deflating a jar, a zst archive or a png costs CPU on both ends and reliably
     * makes the payload slightly larger. The decision is made from the declared media type and
     * the name, never by trying and measuring, because a trial compression of a 4 GB artifact is
     * itself the cost being avoided.
     */
    public static final class CompressionPolicy {

        private static final Set<String> COMPRESSED_MEDIA_TYPES = Set.of(
                "application/zip", "application/gzip", "application/zstd", "application/x-xz",
                "application/x-bzip2", "application/java-archive", "application/vnd.android.package-archive",
                "image/png", "image/jpeg", "image/webp", "image/avif",
                "video/mp4", "video/webm", "audio/mpeg", "audio/ogg");

        private static final Set<String> COMPRESSED_SUFFIXES = Set.of(
                ".zip", ".gz", ".tgz", ".zst", ".xz", ".bz2", ".7z", ".jar", ".war", ".ear", ".aar",
                ".apk", ".png", ".jpg", ".jpeg", ".webp", ".avif", ".mp4", ".webm", ".mp3", ".ogg",
                ".woff", ".woff2", ".whl", ".nupkg", ".crate");

        private final int minimumBytes;

        public CompressionPolicy(int minimumBytes) {
            this.minimumBytes = minimumBytes;
        }

        public static CompressionPolicy standard() {
            return new CompressionPolicy(4096);
        }

        public ChunkEncoding encodingFor(String mediaType, String fileName, int sizeBytes) {
            if (sizeBytes < minimumBytes) {
                return ChunkEncoding.NONE;
            }
            if (mediaType != null && COMPRESSED_MEDIA_TYPES.contains(mediaType.toLowerCase(Locale.ROOT))) {
                return ChunkEncoding.NONE;
            }
            if (fileName != null) {
                String lower = fileName.toLowerCase(Locale.ROOT);
                for (String suffix : COMPRESSED_SUFFIXES) {
                    if (lower.endsWith(suffix)) {
                        return ChunkEncoding.NONE;
                    }
                }
            }
            return ChunkEncoding.DEFLATE;
        }
    }

    /** Wire codec for a single chunk. Round-trip is verified against the chunk digest. */
    public static final class ChunkCodec {

        public byte[] encode(ChunkEncoding encoding, byte[] plain) {
            if (encoding == ChunkEncoding.NONE) {
                return plain.clone();
            }
            Deflater deflater = new Deflater(Deflater.BEST_SPEED);
            try {
                deflater.setInput(plain);
                deflater.finish();
                byte[] buffer = new byte[Math.max(64, plain.length + 64)];
                int written = deflater.deflate(buffer);
                if (!deflater.finished()) {
                    // Incompressible payload grew past the buffer. Ship it uncompressed instead of
                    // paying for a second pass on data that will not shrink.
                    return plain.clone();
                }
                return Arrays.copyOf(buffer, written);
            } finally {
                deflater.end();
            }
        }

        public byte[] decode(ChunkEncoding encoding, byte[] wire, int plainLength) {
            if (encoding == ChunkEncoding.NONE) {
                return wire.clone();
            }
            Inflater inflater = new Inflater();
            try {
                inflater.setInput(wire);
                byte[] buffer = new byte[plainLength];
                int written = inflater.inflate(buffer);
                if (written != plainLength) {
                    throw new IllegalStateException("chunk inflated to " + written + " bytes, expected " + plainLength);
                }
                return buffer;
            } catch (DataFormatException error) {
                throw new IllegalStateException("chunk is not a valid deflate stream", error);
            } finally {
                inflater.end();
            }
        }
    }

    /**
     * ELMOS-CAS-008 bandwidth limiting as a token bucket that <em>reports</em> the delay it wants
     * instead of sleeping. Sleeping inside the transfer path makes the limiter impossible to test
     * and impossible to reason about under cancellation; the caller schedules the wait.
     */
    public static final class BandwidthLimiter {

        private final long bytesPerSecond;
        private final long burstBytes;
        private double tokens;
        private long lastRefillMillis;

        public BandwidthLimiter(long bytesPerSecond, long burstBytes, long startMillis) {
            CasText.requirePositive(bytesPerSecond, "bytesPerSecond");
            CasText.requirePositive(burstBytes, "burstBytes");
            this.bytesPerSecond = bytesPerSecond;
            this.burstBytes = burstBytes;
            this.tokens = burstBytes;
            this.lastRefillMillis = startMillis;
        }

        /** @return milliseconds the caller must wait before sending {@code bytes} */
        public long reserve(int bytes, long nowMillis) {
            refill(nowMillis);
            tokens -= bytes;
            if (tokens >= 0) {
                return 0;
            }
            double deficit = -tokens;
            return (long) Math.ceil(deficit * 1000d / bytesPerSecond);
        }

        private void refill(long nowMillis) {
            long elapsed = Math.max(0, nowMillis - lastRefillMillis);
            lastRefillMillis = nowMillis;
            tokens = Math.min(burstBytes, tokens + elapsed * bytesPerSecond / 1000d);
        }

        public double availableTokens() {
            return tokens;
        }
    }
}
