package io.elmos.storage;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;

/**
 * S3-protocol object store adapter, used for AWS S3, Alibaba Cloud OSS and MinIO.
 *
 * <p>Deliberately free of any database dependency: it signs URLs and verifies
 * bytes, nothing else. Metadata lives behind {@link ObjectStorageMetadata} so this
 * class can be unit-tested against a fake endpoint without a PostgreSQL instance,
 * and so a storage bug can never be a tenancy bug.</p>
 *
 * <p>Fail-closed rules enforced here:</p>
 * <ul>
 *   <li>An unconfigured or non-ACTIVE backend refuses every operation.</li>
 *   <li>A presigned upload is scoped to one tenant prefix and one content digest.</li>
 *   <li>An object becomes downloadable only after the server has re-read the stored
 *       bytes and recomputed SHA-256. A client-declared digest is never trusted.</li>
 * </ul>
 */
public final class S3ObjectStore {

    public static final class ObjectStorageException extends RuntimeException {
        private static final long serialVersionUID = 1L;
        private final String code;

        public ObjectStorageException(String code) {
            super(code);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    /**
     * Resolved backend configuration, mirroring one ACTIVE row of
     * {@code object_storage_backends}.
     */
    public record Backend(
            String backendId,
            String state,
            String endpoint,
            String bucket,
            String region,
            boolean pathStyle,
            String serverSideEncryption,
            String cmkReference,
            long maxObjectBytes,
            SigV4Presigner.Credentials credentials) {

        public boolean writable() {
            return "ACTIVE".equals(state);
        }

        public boolean readable() {
            return "ACTIVE".equals(state) || "READ_ONLY".equals(state);
        }
    }

    /** Metadata operations the store needs, implemented by the JDBC adapter. */
    public interface ObjectStorageMetadata {
        /** Creates or returns the PENDING_UPLOAD row for this tenant and digest. */
        String registerPendingObject(String organizationId, String contentSha256, long byteSize,
                                     String mediaType, String backendId, String storageKey);

        void markAvailable(String organizationId, String contentObjectId);

        void markQuarantined(String organizationId, String contentObjectId, String reason);
    }

    private final Backend backend;
    private final ObjectStorageMetadata metadata;
    private final HttpClient http;
    private final Clock clock;

    public S3ObjectStore(Backend backend, ObjectStorageMetadata metadata, Clock clock) {
        this.backend = backend;
        this.metadata = metadata;
        this.clock = clock;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    public record UploadTicket(URI uploadUrl, String storageKey, String contentObjectId, Map<String, String> requiredHeaders) {
    }

    public record DownloadTicket(URI downloadUrl, String storageKey, Duration expiresIn) {
    }

    /**
     * The object key. The tenant prefix is first so a bucket policy or RAM policy
     * can enforce tenant separation independently of this application - isolation
     * that does not depend on our own correctness.
     */
    public static String storageKey(String organizationId, String contentSha256) {
        if (!organizationId.matches("^[A-Za-z0-9][A-Za-z0-9._-]{1,95}$")) {
            throw new ObjectStorageException("ORGANIZATION_ID_UNSAFE_FOR_KEY");
        }
        if (!contentSha256.matches("^[0-9a-f]{64}$")) {
            throw new ObjectStorageException("CONTENT_DIGEST_INVALID");
        }
        return organizationId + "/obj/" + contentSha256;
    }

    public UploadTicket presignUpload(String organizationId, String contentSha256, long byteSize,
                                      String mediaType, Duration expiresIn) {
        requireWritable();
        if (byteSize <= 0 || byteSize > backend.maxObjectBytes()) {
            throw new ObjectStorageException("ARTIFACT_SIZE_OUT_OF_RANGE");
        }
        String key = storageKey(organizationId, contentSha256);
        String contentObjectId = metadata.registerPendingObject(
                organizationId, contentSha256, byteSize, mediaType, backend.backendId(), key);

        URI url = SigV4Presigner.presign("PUT", backend.endpoint(), backend.bucket(), key,
                backend.region(), backend.pathStyle(), backend.credentials(),
                clock.instant(), expiresIn, Map.of());

        // Server-side encryption is requested through headers the uploader must
        // send. They are returned with the ticket so the runner cannot silently
        // write an unencrypted object.
        Map<String, String> headers = switch (backend.serverSideEncryption()) {
            case "SSE_KMS" -> Map.of(
                    "x-amz-server-side-encryption", "aws:kms",
                    "x-amz-server-side-encryption-aws-kms-key-id", backend.cmkReference());
            case "SSE_S3" -> Map.of("x-amz-server-side-encryption", "AES256");
            default -> Map.of();
        };

        return new UploadTicket(url, key, contentObjectId, headers);
    }

    public DownloadTicket presignDownload(String organizationId, String contentSha256,
                                          String filename, Duration expiresIn) {
        requireReadable();
        if (expiresIn.toMinutes() > 15) {
            // Mirrors the artifact_grant_max_ttl CHECK. A presigned URL is a bearer
            // credential; fifteen minutes is the ceiling in both places.
            throw new ObjectStorageException("DOWNLOAD_GRANT_TTL_TOO_LONG");
        }
        String key = storageKey(organizationId, contentSha256);
        Map<String, String> extra = filename == null || filename.isBlank()
                ? Map.of()
                : Map.of("response-content-disposition",
                        "attachment; filename=\"" + sanitizeFilename(filename) + "\"");

        URI url = SigV4Presigner.presign("GET", backend.endpoint(), backend.bucket(), key,
                backend.region(), backend.pathStyle(), backend.credentials(),
                clock.instant(), expiresIn, extra);
        return new DownloadTicket(url, key, expiresIn);
    }

    /**
     * Physically deletes a retained object. DELETE and a provider 404 are both
     * success because the desired state is absence; an unknown provider result is
     * surfaced and metadata must remain PURGE_PENDING for retry.
     */
    public void deleteObject(String organizationId, String contentSha256) {
        requireWritable();
        String key = storageKey(organizationId, contentSha256);
        URI url = SigV4Presigner.presign(
                "DELETE", backend.endpoint(), backend.bucket(), key,
                backend.region(), backend.pathStyle(), backend.credentials(),
                clock.instant(), Duration.ofMinutes(5), Map.of());
        try {
            HttpResponse<Void> response = http.send(
                    HttpRequest.newBuilder(url)
                            .timeout(Duration.ofSeconds(30))
                            .DELETE()
                            .build(),
                    HttpResponse.BodyHandlers.discarding());
            if (response.statusCode() == 404 || response.statusCode() / 100 == 2) {
                return;
            }
            throw new ObjectStorageException(
                    "OBJECT_DELETE_FAILED_" + response.statusCode());
        } catch (IOException error) {
            throw new ObjectStorageException("OBJECT_DELETE_IO");
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new ObjectStorageException("OBJECT_DELETE_INTERRUPTED");
        }
    }

    /**
     * Re-reads the stored object and recomputes SHA-256 over the actual bytes.
     *
     * <p>This is the step that makes a truncated or substituted upload impossible
     * to publish. On mismatch the object is quarantined rather than deleted, so the
     * incident stays inspectable.</p>
     *
     * @return true when the stored bytes match, false when the object was quarantined
     */
    public boolean verifyUpload(String organizationId, String contentObjectId,
                                String expectedSha256, long expectedBytes) {
        requireReadable();
        String key = storageKey(organizationId, expectedSha256);
        URI url = SigV4Presigner.presign("GET", backend.endpoint(), backend.bucket(), key,
                backend.region(), backend.pathStyle(), backend.credentials(),
                clock.instant(), Duration.ofMinutes(10), Map.of());

        try {
            HttpResponse<InputStream> response = http.send(
                    HttpRequest.newBuilder(url).timeout(Duration.ofMinutes(15)).GET().build(),
                    HttpResponse.BodyHandlers.ofInputStream());

            if (response.statusCode() == 404) {
                metadata.markQuarantined(organizationId, contentObjectId, "OBJECT_ABSENT");
                return false;
            }
            if (response.statusCode() / 100 != 2) {
                throw new ObjectStorageException("OBJECT_READ_FAILED_" + response.statusCode());
            }

            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            long counted = 0;
            try (InputStream body = response.body();
                 DigestInputStream digesting = new DigestInputStream(body, digest)) {
                byte[] buffer = new byte[1 << 16];
                int read;
                while ((read = digesting.read(buffer)) != -1) {
                    counted += read;
                    if (counted > backend.maxObjectBytes()) {
                        metadata.markQuarantined(organizationId, contentObjectId, "OBJECT_TOO_LARGE");
                        return false;
                    }
                }
            }

            String actual = HexFormat.of().formatHex(digest.digest()).toLowerCase(Locale.ROOT);
            if (!actual.equals(expectedSha256)) {
                metadata.markQuarantined(organizationId, contentObjectId, "DIGEST_MISMATCH");
                return false;
            }
            if (counted != expectedBytes) {
                // Length and digest disagreeing at once would be extraordinary, but
                // both are declared by the client, so both are checked.
                metadata.markQuarantined(organizationId, contentObjectId, "LENGTH_MISMATCH");
                return false;
            }

            metadata.markAvailable(organizationId, contentObjectId);
            return true;

        } catch (IOException ex) {
            throw new ObjectStorageException("OBJECT_READ_IO");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new ObjectStorageException("OBJECT_READ_INTERRUPTED");
        } catch (java.security.NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    private void requireWritable() {
        if (!backend.writable()) {
            // No fallback to local disk. That fallback is exactly what makes a
            // multi-replica deployment serve 404s.
            throw new ObjectStorageException("OBJECT_STORAGE_NOT_CONFIGURED");
        }
    }

    private void requireReadable() {
        if (!backend.readable()) {
            throw new ObjectStorageException("OBJECT_STORAGE_NOT_CONFIGURED");
        }
    }

    /** Keeps a hostile filename out of the Content-Disposition header. */
    static String sanitizeFilename(String filename) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < filename.length() && out.length() < 120; i++) {
            char c = filename.charAt(i);
            if (c == '"' || c == '\\' || c == '\r' || c == '\n' || c < 0x20) {
                out.append('_');
            } else {
                out.append(c);
            }
        }
        return out.length() == 0 ? "artifact" : out.toString();
    }
}
