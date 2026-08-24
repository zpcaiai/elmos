package io.elmos.cas;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Arrays;

/**
 * A deliberately small, dependency-free process boundary probe for the shared S3 tier.
 *
 * <p>This is a {@code main}, rather than a JUnit test, because the acceptance property is that a
 * writer JVM can exit and an unrelated reader JVM can recover the same bytes from the external
 * object store. {@code scripts/cas/run-two-process-shared-tier-probe.sh} owns the two process
 * launches and independently compares their receipts. Credentials are read only from the
 * environment and are never written to the receipt.
 */
public final class S3CasStoreProcessProbe {

    private static final String ENDPOINT = "ELMOS_CAS_PROBE_ENDPOINT";
    private static final String BUCKET = "ELMOS_CAS_PROBE_BUCKET";
    private static final String ACCESS_KEY = "ELMOS_CAS_PROBE_ACCESS_KEY";
    private static final String SECRET_KEY = "ELMOS_CAS_PROBE_SECRET_KEY";

    private S3CasStoreProcessProbe() {
    }

    public static void main(String[] arguments) throws Exception {
        if (arguments.length != 3) {
            throw new IllegalArgumentException(
                    "usage: S3CasStoreProcessProbe <write|read> <content-file> <receipt-file>");
        }
        String operation = arguments[0];
        if (!operation.equals("write") && !operation.equals("read")) {
            throw new IllegalArgumentException("operation must be write or read: " + operation);
        }

        URI endpoint = URI.create(requiredEnvironment(ENDPOINT));
        String bucket = requiredEnvironment(BUCKET);
        String accessKey = requiredEnvironment(ACCESS_KEY);
        String secretKey = requiredEnvironment(SECRET_KEY);
        Path contentPath = Path.of(arguments[1]).toAbsolutePath().normalize();
        Path receiptPath = Path.of(arguments[2]).toAbsolutePath().normalize();
        byte[] expectedContent = Files.readAllBytes(contentPath);
        CasDigest digest = CasDigest.of(expectedContent);
        S3CasStore store = S3CasStore.create(
                "external-minio-shared-tier",
                S3CasStore.Config.minio(endpoint, bucket, accessKey, secretKey));

        if (operation.equals("write")) {
            store.put(digest, expectedContent);
            if (!store.contains(digest)) {
                throw new IllegalStateException("writer could not observe the uploaded digest");
            }
        } else {
            byte[] recovered = store.get(digest);
            if (!Arrays.equals(expectedContent, recovered)) {
                throw new IllegalStateException("reader recovered bytes that differ from the source payload");
            }
        }

        long processId = ProcessHandle.current().pid();
        String receipt = "{\n"
                + "  \"schema_version\": 1,\n"
                + "  \"operation\": " + jsonString(operation) + ",\n"
                + "  \"process_id\": " + processId + ",\n"
                + "  \"observed_at\": " + jsonString(Instant.now().toString()) + ",\n"
                + "  \"endpoint\": " + jsonString(endpoint.toString()) + ",\n"
                + "  \"bucket\": " + jsonString(bucket) + ",\n"
                + "  \"digest\": " + jsonString(digest.compact()) + ",\n"
                + "  \"size_bytes\": " + expectedContent.length + ",\n"
                + "  \"verified\": true\n"
                + "}\n";
        Path parent = receiptPath.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }
        Files.writeString(receiptPath, receipt, StandardCharsets.UTF_8);
        System.out.printf("%s pid=%d digest=%s bytes=%d%n",
                operation, processId, digest.compact(), expectedContent.length);
    }

    private static String requiredEnvironment(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("missing required environment variable: " + name);
        }
        return value;
    }

    private static String jsonString(String value) {
        StringBuilder escaped = new StringBuilder(value.length() + 2).append('"');
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            switch (character) {
                case '"' -> escaped.append("\\\"");
                case '\\' -> escaped.append("\\\\");
                case '\n' -> escaped.append("\\n");
                case '\r' -> escaped.append("\\r");
                case '\t' -> escaped.append("\\t");
                default -> {
                    if (character < 0x20) {
                        escaped.append(String.format("\\u%04x", (int) character));
                    } else {
                        escaped.append(character);
                    }
                }
            }
        }
        return escaped.append('"').toString();
    }
}
