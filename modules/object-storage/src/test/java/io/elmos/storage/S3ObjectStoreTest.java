package io.elmos.storage;

import com.sun.net.httpserver.HttpServer;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Exercises the store against a real HTTP endpoint that behaves like S3.
 *
 * <p>The fake accepts presigned PUTs and serves them back, so the upload, the
 * server-side digest recomputation and the quarantine path all run for real.</p>
 */
public final class S3ObjectStoreTest {

    private static final List<String> FAILURES = new ArrayList<>();
    private static int checks;

    private static final Map<String, byte[]> OBJECTS = new ConcurrentHashMap<>();

    public static void main(String[] args) throws Exception {
        HttpServer fakeS3 = startFakeS3();
        try {
            String endpoint = "http://127.0.0.1:" + fakeS3.getAddress().getPort();
            uploadVerifyRoundTrip(endpoint);
            truncatedUploadIsQuarantined(endpoint);
            substitutedBytesAreQuarantined(endpoint);
            absentObjectIsQuarantined(endpoint);
            unconfiguredBackendRefusesEverything(endpoint);
            encryptionHeadersAreReturned(endpoint);
            downloadTtlIsCapped(endpoint);
            physicalDeleteIsIdempotent(endpoint);
            keysAreTenantPrefixed();
            filenameIsSanitised();
        } finally {
            fakeS3.stop(0);
        }

        System.out.println();
        if (FAILURES.isEmpty()) {
            System.out.println("S3 OBJECT STORE TEST PASSED (" + checks + " checks)");
            return;
        }
        System.out.println("S3 OBJECT STORE TEST FAILED (" + FAILURES.size() + "/" + checks + ")");
        FAILURES.forEach(f -> System.out.println("  - " + f));
        throw new AssertionError("S3 OBJECT STORE TEST FAILED");
    }

    // ---- scenarios ---------------------------------------------------------

    static void uploadVerifyRoundTrip(String endpoint) throws Exception {
        byte[] payload = "generated-project-bytes".getBytes(StandardCharsets.UTF_8);
        String digest = sha256(payload);
        RecordingMetadata metadata = new RecordingMetadata();
        S3ObjectStore store = store(endpoint, "ACTIVE", metadata);

        S3ObjectStore.UploadTicket ticket = store.presignUpload(
                "org-a", digest, payload.length, "application/zip", Duration.ofMinutes(10));

        check("upload key is tenant prefixed", ticket.storageKey().equals("org-a/obj/" + digest));
        check("pending object was registered", metadata.registered == 1);

        put(ticket.uploadUrl(), payload);

        boolean verified = store.verifyUpload("org-a", ticket.contentObjectId(), digest, payload.length);
        check("matching upload verifies", verified);
        check("object was marked AVAILABLE", metadata.available == 1);
        check("object was not quarantined", metadata.quarantined.isEmpty());
    }

    static void truncatedUploadIsQuarantined(String endpoint) throws Exception {
        byte[] declared = "the-whole-archive-contents".getBytes(StandardCharsets.UTF_8);
        byte[] actual = "the-whole".getBytes(StandardCharsets.UTF_8);
        String digest = sha256(declared);
        RecordingMetadata metadata = new RecordingMetadata();
        S3ObjectStore store = store(endpoint, "ACTIVE", metadata);

        S3ObjectStore.UploadTicket ticket = store.presignUpload(
                "org-a", digest, declared.length, "application/zip", Duration.ofMinutes(10));
        put(ticket.uploadUrl(), actual);   // the classic truncated upload

        boolean verified = store.verifyUpload("org-a", ticket.contentObjectId(), digest, declared.length);
        check("truncated upload fails verification", !verified);
        check("truncated upload is quarantined as a digest mismatch",
                metadata.quarantined.contains("DIGEST_MISMATCH"));
        check("truncated upload never becomes AVAILABLE", metadata.available == 0);
    }

    static void substitutedBytesAreQuarantined(String endpoint) throws Exception {
        byte[] good = "trusted-bytes".getBytes(StandardCharsets.UTF_8);
        byte[] evil = "swapped-bytes".getBytes(StandardCharsets.UTF_8);
        String digest = sha256(good);
        RecordingMetadata metadata = new RecordingMetadata();
        S3ObjectStore store = store(endpoint, "ACTIVE", metadata);

        S3ObjectStore.UploadTicket ticket = store.presignUpload(
                "org-a", digest, good.length, "application/zip", Duration.ofMinutes(10));
        put(ticket.uploadUrl(), evil);

        check("substituted bytes fail verification",
                !store.verifyUpload("org-a", ticket.contentObjectId(), digest, good.length));
        check("substituted bytes are quarantined",
                metadata.quarantined.contains("DIGEST_MISMATCH"));
    }

    static void absentObjectIsQuarantined(String endpoint) {
        String digest = sha256("never-uploaded".getBytes(StandardCharsets.UTF_8));
        RecordingMetadata metadata = new RecordingMetadata();
        S3ObjectStore store = store(endpoint, "ACTIVE", metadata);
        store.presignUpload("org-b", digest, 14, "application/zip", Duration.ofMinutes(10));

        check("absent object fails verification",
                !store.verifyUpload("org-b", "obj-missing", digest, 14));
        check("absent object is quarantined", metadata.quarantined.contains("OBJECT_ABSENT"));
    }

    static void unconfiguredBackendRefusesEverything(String endpoint) {
        S3ObjectStore store = store(endpoint, "NOT_CONFIGURED", new RecordingMetadata());
        String digest = sha256("x".getBytes(StandardCharsets.UTF_8));

        check("unconfigured backend refuses upload", throwsStorage(() ->
                store.presignUpload("org-a", digest, 1, "application/zip", Duration.ofMinutes(10))));
        check("unconfigured backend refuses download", throwsStorage(() ->
                store.presignDownload("org-a", digest, "a.zip", Duration.ofMinutes(10))));

        S3ObjectStore readOnly = store(endpoint, "READ_ONLY", new RecordingMetadata());
        check("read-only backend refuses upload", throwsStorage(() ->
                readOnly.presignUpload("org-a", digest, 1, "application/zip", Duration.ofMinutes(10))));
        check("read-only backend still allows download", !throwsStorage(() ->
                readOnly.presignDownload("org-a", digest, "a.zip", Duration.ofMinutes(10))));
    }

    static void encryptionHeadersAreReturned(String endpoint) {
        String digest = sha256("y".getBytes(StandardCharsets.UTF_8));
        S3ObjectStore.UploadTicket ticket = store(endpoint, "ACTIVE", new RecordingMetadata())
                .presignUpload("org-a", digest, 1, "application/zip", Duration.ofMinutes(10));
        check("SSE-KMS headers accompany the ticket",
                "aws:kms".equals(ticket.requiredHeaders().get("x-amz-server-side-encryption")));
        check("CMK reference is carried",
                "kms://cn-north/elmos".equals(
                        ticket.requiredHeaders().get("x-amz-server-side-encryption-aws-kms-key-id")));
    }

    static void downloadTtlIsCapped(String endpoint) {
        String digest = sha256("z".getBytes(StandardCharsets.UTF_8));
        S3ObjectStore store = store(endpoint, "ACTIVE", new RecordingMetadata());
        check("a two-hour download grant is refused", throwsStorage(() ->
                store.presignDownload("org-a", digest, "a.zip", Duration.ofHours(2))));
        check("a five-minute download grant is allowed", !throwsStorage(() ->
                store.presignDownload("org-a", digest, "a.zip", Duration.ofMinutes(5))));
    }

    static void physicalDeleteIsIdempotent(String endpoint) throws Exception {
        byte[] payload = "retained-object".getBytes(StandardCharsets.UTF_8);
        String digest = sha256(payload);
        S3ObjectStore store = store(endpoint, "ACTIVE", new RecordingMetadata());
        S3ObjectStore.UploadTicket ticket = store.presignUpload(
                "org-gc", digest, payload.length, "application/octet-stream",
                Duration.ofMinutes(5));
        put(ticket.uploadUrl(), payload);
        store.deleteObject("org-gc", digest);
        check("retention physically deletes the provider object",
                !OBJECTS.containsKey(ticket.storageKey()));
        check("deleting an already absent object is idempotent",
                !throwsStorage(() -> store.deleteObject("org-gc", digest)));
    }

    static void keysAreTenantPrefixed() {
        String digest = "a".repeat(64);
        check("key starts with the organization",
                S3ObjectStore.storageKey("org-a", digest).equals("org-a/obj/" + digest));
        check("a traversal organization id is rejected", throwsStorage(() ->
                S3ObjectStore.storageKey("../org-b", digest)));
        check("a non-hex digest is rejected", throwsStorage(() ->
                S3ObjectStore.storageKey("org-a", "not-a-digest")));
    }

    static void filenameIsSanitised() {
        check("quotes and newlines are stripped from the filename",
                S3ObjectStore.sanitizeFilename("a\"b\r\nc").equals("a_b__c"));
        check("an empty filename falls back",
                S3ObjectStore.sanitizeFilename("").equals("artifact"));
    }

    // ---- fake S3 -----------------------------------------------------------

    private static HttpServer startFakeS3() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            // Path style: /<bucket>/<key...>
            String path = exchange.getRequestURI().getPath();
            String key = path.substring(path.indexOf('/', 1) + 1);
            switch (exchange.getRequestMethod()) {
                case "PUT" -> {
                    OBJECTS.put(key, exchange.getRequestBody().readAllBytes());
                    exchange.sendResponseHeaders(200, -1);
                }
                case "GET" -> {
                    byte[] body = OBJECTS.get(key);
                    if (body == null) {
                        exchange.sendResponseHeaders(404, -1);
                    } else {
                        exchange.sendResponseHeaders(200, body.length);
                        try (OutputStream out = exchange.getResponseBody()) {
                            out.write(body);
                        }
                    }
                }
                case "DELETE" -> {
                    byte[] removed = OBJECTS.remove(key);
                    exchange.sendResponseHeaders(removed == null ? 404 : 204, -1);
                }
                default -> exchange.sendResponseHeaders(405, -1);
            }
            exchange.close();
        });
        server.setExecutor(null);
        server.start();
        return server;
    }

    private static void put(URI url, byte[] payload) throws Exception {
        HttpResponse<Void> response = HttpClient.newHttpClient().send(
                HttpRequest.newBuilder(url).PUT(HttpRequest.BodyPublishers.ofByteArray(payload)).build(),
                HttpResponse.BodyHandlers.discarding());
        if (response.statusCode() / 100 != 2) {
            throw new IllegalStateException("fake S3 rejected the upload: " + response.statusCode());
        }
    }

    // ---- helpers -----------------------------------------------------------

    private static final class RecordingMetadata implements S3ObjectStore.ObjectStorageMetadata {
        int registered;
        int available;
        final List<String> quarantined = new ArrayList<>();

        @Override
        public String registerPendingObject(String organizationId, String contentSha256, long byteSize,
                                            String mediaType, String backendId, String storageKey) {
            registered++;
            return "obj-" + contentSha256.substring(0, 12);
        }

        @Override
        public void markAvailable(String organizationId, String contentObjectId) {
            available++;
        }

        @Override
        public void markQuarantined(String organizationId, String contentObjectId, String reason) {
            quarantined.add(reason);
        }
    }

    private static S3ObjectStore store(String endpoint, String state,
                                       S3ObjectStore.ObjectStorageMetadata metadata) {
        S3ObjectStore.Backend backend = new S3ObjectStore.Backend(
                "primary", state, endpoint, "elmos-artifacts", "cn-north-1", true,
                "SSE_KMS", "kms://cn-north/elmos", 5L * 1024 * 1024 * 1024,
                SigV4Presigner.Credentials.of("AK", "SK"));
        return new S3ObjectStore(backend, metadata,
                Clock.fixed(Instant.parse("2026-07-28T12:00:00Z"), ZoneOffset.UTC));
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes))
                    .toLowerCase(Locale.ROOT);
        } catch (Exception ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static boolean throwsStorage(Runnable action) {
        try {
            action.run();
            return false;
        } catch (S3ObjectStore.ObjectStorageException ex) {
            return true;
        }
    }

    private static void check(String description, boolean condition) {
        checks++;
        System.out.println((condition ? "  ok   " : "  FAIL ") + description);
        if (!condition) {
            FAILURES.add(description);
        }
    }
}
