package io.elmos.controlplane;

import io.elmos.persistence.JdbcObjectStorageStore;
import io.elmos.storage.S3ObjectStore;
import io.elmos.workflow.ExecutionJobPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

/**
 * Closes the seam between the Runner Agent and object storage.
 *
 * <p>NOTE: depends on Spring Web; not compiled in the authoring sandbox. The SQL
 * it drives and the storage adapter it calls were both executed and verified
 * there.</p>
 *
 * <p>Three endpoints, two audiences:</p>
 * <ul>
 *   <li>Runner-facing upload-ticket and publish, authorised by the lease token.</li>
 *   <li>Tenant-facing download-ticket, authorised by the user session.</li>
 * </ul>
 *
 * <p>The runner endpoints deliberately do <b>not</b> trust the organization the
 * runner claims. The tenant is resolved from the lease record; a runner that
 * guessed another lease id would still fail the token check, and one that forged
 * an organization would be ignored.</p>
 */
@RestController
public class ArtifactController {

    private static final int UPLOAD_TICKET_TTL_SECONDS = 900;
    private static final int DOWNLOAD_TICKET_TTL_SECONDS = 300;

    private final JdbcObjectStorageStore storage;
    private final ObjectStoreFactory stores;
    private final ExecutionJobPort jobs;
    private final TenantContext tenants;

    public ArtifactController(JdbcObjectStorageStore storage, ObjectStoreFactory stores,
                              ExecutionJobPort jobs, TenantContext tenants) {
        this.storage = storage;
        this.stores = stores;
        this.jobs = jobs;
        this.tenants = tenants;
    }

    /** Builds an {@link S3ObjectStore} from the currently ACTIVE backend row. */
    public interface ObjectStoreFactory {
        S3ObjectStore current();
    }

    /** Server-derived tenant and actor for the authenticated session. */
    public interface TenantContext {
        String organizationId();

        String actorId();
    }

    // ---- runner facing -----------------------------------------------------

    public record UploadTicketRequest(String runnerNodeId, String jobId, String contentSha256,
                                      long byteSize, String mediaType) {
    }

    @PostMapping("/runner/v1/leases/{leaseId}/artifacts/upload-ticket")
    public ResponseEntity<?> uploadTicket(@PathVariable String leaseId,
                                          @RequestBody UploadTicketRequest request,
                                          @RequestHeader("X-Elmos-Lease-Token") String leaseToken) {
        String organizationId = authorizeLease(leaseId, request.jobId(), leaseToken);

        S3ObjectStore store = stores.current();
        S3ObjectStore.UploadTicket ticket = store.presignUpload(
                organizationId, normalizeDigest(request.contentSha256()), request.byteSize(),
                request.mediaType(), Duration.ofSeconds(UPLOAD_TICKET_TTL_SECONDS));

        return ResponseEntity.ok(Map.of(
                "uploadUrl", ticket.uploadUrl().toString(),
                "storageKey", ticket.storageKey(),
                "contentObjectId", ticket.contentObjectId(),
                // The runner must echo these back on the PUT, so it cannot
                // accidentally write an unencrypted object.
                "requiredHeaders", ticket.requiredHeaders(),
                "expiresInSeconds", UPLOAD_TICKET_TTL_SECONDS));
    }

    public record PublishRequest(String runnerNodeId, String jobId, String contentObjectId,
                                 String contentSha256, long byteSize,
                                 String artifactRole, String filename, String retentionClass) {
    }

    /**
     * Verifies the stored bytes, then publishes.
     *
     * <p>The verification is not optional and not cached: the control plane reads
     * the object back and recomputes SHA-256 before the artifact becomes
     * downloadable. A digest declared by the runner is a claim, not a fact.</p>
     */
    @PostMapping("/runner/v1/leases/{leaseId}/artifacts/publish")
    public ResponseEntity<?> publish(@PathVariable String leaseId,
                                     @RequestBody PublishRequest request,
                                     @RequestHeader("X-Elmos-Lease-Token") String leaseToken) {
        String organizationId = authorizeLease(leaseId, request.jobId(), leaseToken);

        S3ObjectStore store = stores.current();
        boolean verified = store.verifyUpload(organizationId, request.contentObjectId(),
                normalizeDigest(request.contentSha256()), request.byteSize());
        if (!verified) {
            return ResponseEntity.status(HttpStatus.UNPROCESSABLE_ENTITY)
                    .body(Map.of("status", "ERROR", "code", "ELMOS_ARTIFACT_VERIFICATION_FAILED"));
        }

        String artifactId = storage.publishArtifact(organizationId, request.jobId(),
                request.artifactRole(), request.filename(), request.contentObjectId(),
                request.retentionClass());

        return ResponseEntity.ok(Map.of("status", "PUBLISHED", "artifactId", artifactId));
    }

    // ---- tenant facing -----------------------------------------------------

    /**
     * Issues a short-lived presigned GET.
     *
     * <p>The browser still recomputes SHA-256 over the downloaded bytes before
     * accepting the file, which is what makes handing out a bearer URL safe. The
     * digest is therefore returned alongside the URL.</p>
     */
    @PostMapping("/api/v1/execution/jobs/{jobId}/artifacts/{role}/download-ticket")
    public ResponseEntity<?> downloadTicket(@PathVariable String jobId, @PathVariable String role) {
        String organizationId = tenants.organizationId();

        Optional<ExecutionJobPort.JobView> job = jobs.find(organizationId, jobId);
        if (job.isEmpty()) {
            // 404 rather than 403: a tenant must not be able to probe for the
            // existence of another tenant's job.
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(Map.of("status", "ERROR", "code", "ELMOS_EXECUTION_JOB_UNKNOWN"));
        }

        String artifactId = storage.artifactIdFor(organizationId, jobId, role)
                .orElse(null);
        if (artifactId == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(Map.of("status", "ERROR", "code", "ELMOS_ARTIFACT_UNKNOWN"));
        }

        JdbcObjectStorageStore.GrantedDownload granted = storage.issueDownloadGrant(
                organizationId, artifactId, tenants.actorId(), DOWNLOAD_TICKET_TTL_SECONDS);

        S3ObjectStore store = stores.current();
        S3ObjectStore.DownloadTicket ticket = store.presignDownload(
                organizationId, granted.contentSha256(), granted.filename(),
                Duration.ofSeconds(DOWNLOAD_TICKET_TTL_SECONDS));

        return ResponseEntity.ok(Map.of(
                "downloadUrl", ticket.downloadUrl().toString(),
                "filename", granted.filename(),
                "contentSha256", granted.contentSha256(),
                "byteSize", granted.byteSize(),
                "expiresInSeconds", DOWNLOAD_TICKET_TTL_SECONDS));
    }

    // ---- authorisation -----------------------------------------------------

    /**
     * The runner proves it holds a live lease for this exact job. The tenant is
     * then read from the lease record, never from the request body.
     */
    private String authorizeLease(String leaseId, String jobId, String leaseToken) {
        String tokenHash = sha256Hex(leaseToken);
        if (!storage.leaseOwnsJob(leaseId, jobId, tokenHash)) {
            throw new LeaseRejected("ELMOS_LEASE_CREDENTIAL_MISMATCH");
        }
        return storage.organizationForLease(leaseId)
                .orElseThrow(() -> new LeaseRejected("ELMOS_LEASE_UNKNOWN"));
    }

    static final class LeaseRejected extends RuntimeException {
        private static final long serialVersionUID = 1L;
        private final String code;

        LeaseRejected(String code) {
            super(code);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    private static String normalizeDigest(String value) {
        String digest = value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
        if (!digest.matches("^[0-9a-f]{64}$")) {
            throw new S3ObjectStore.ObjectStorageException("CONTENT_DIGEST_INVALID");
        }
        return digest;
    }

    private static String sha256Hex(String value) {
        try {
            return HexFormat.of()
                    .formatHex(MessageDigest.getInstance("SHA-256")
                            .digest(value.getBytes(StandardCharsets.UTF_8)))
                    .toLowerCase(Locale.ROOT);
        } catch (Exception ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    // ---- error mapping -----------------------------------------------------

    @ExceptionHandler(LeaseRejected.class)
    public ResponseEntity<?> onLeaseRejected(LeaseRejected ex) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(Map.of("status", "ERROR", "code", ex.code()));
    }

    @ExceptionHandler(S3ObjectStore.ObjectStorageException.class)
    public ResponseEntity<?> onStorage(S3ObjectStore.ObjectStorageException ex) {
        HttpStatus status = switch (ex.code()) {
            case "OBJECT_STORAGE_NOT_CONFIGURED" -> HttpStatus.SERVICE_UNAVAILABLE;
            case "ARTIFACT_SIZE_OUT_OF_RANGE", "CONTENT_DIGEST_INVALID" -> HttpStatus.BAD_REQUEST;
            case "DOWNLOAD_GRANT_TTL_TOO_LONG" -> HttpStatus.UNPROCESSABLE_ENTITY;
            default -> HttpStatus.BAD_GATEWAY;
        };
        // Stable code only; endpoint, bucket and key never reach the wire.
        return ResponseEntity.status(status).body(Map.of("status", "ERROR", "code", ex.code()));
    }
}
