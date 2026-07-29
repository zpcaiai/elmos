package io.elmos.workflow;

import java.net.URI;
import java.time.Duration;
import java.time.Instant;

/**
 * Artifact object storage boundary.
 *
 * <p>The existing content-addressing contract is preserved end to end: the server
 * recomputes SHA-256 over the stored bytes before an object becomes AVAILABLE, and
 * the browser recomputes it again before accepting a download. What changes is
 * only where the bytes live.</p>
 *
 * <p>Implementations must fail closed. When {@code object_storage_backends} has no
 * ACTIVE row, {@link #status()} returns NOT_CONFIGURED and every publish and
 * download call raises rather than silently falling back to local disk - the
 * fallback is exactly what makes a multi-replica deployment serve 404s.</p>
 */
public interface ObjectStoragePort {

    enum BackendStatus { NOT_CONFIGURED, ACTIVE, READ_ONLY, DISABLED }

    final class ObjectStorageException extends RuntimeException {
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
     * @param uploadUrl  presigned PUT, valid for {@code expiresIn}
     * @param storageKey the key the runner must report back on completion
     */
    record UploadTicket(URI uploadUrl, String storageKey, String backendId, Instant expiresAt) {}

    record DownloadTicket(
            URI downloadUrl,
            String filename,
            String contentSha256,
            long byteSize,
            String mediaType,
            Instant expiresAt) {}

    BackendStatus status();

    /**
     * Issues a presigned PUT scoped to one tenant prefix and one content digest.
     * The runner never receives long-lived storage credentials.
     */
    UploadTicket presignUpload(String organizationId, String jobId, String contentSha256,
                               long byteSize, String mediaType, Duration expiresIn);

    /**
     * Verifies that the uploaded bytes hash to the declared digest and flips the
     * object to AVAILABLE. A mismatch quarantines the object; it is never published.
     */
    void verifyUpload(String organizationId, String contentObjectId);

    /**
     * Issues a presigned GET and records an {@code artifact_download_grants} row.
     * Capped at 15 minutes by the database, not only here.
     */
    DownloadTicket presignDownload(String organizationId, String artifactId, String actorId, Duration expiresIn);
}
