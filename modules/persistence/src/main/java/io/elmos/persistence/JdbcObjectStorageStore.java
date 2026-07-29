package io.elmos.persistence;

import io.elmos.storage.S3ObjectStore;
import io.elmos.storage.SigV4Presigner;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.sql.ResultSet;
import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.function.Supplier;

/**
 * PostgreSQL adapter for the V54 artifact tables.
 *
 * <p>Follows the {@code JdbcSelfServiceBillingStore} shape: JdbcClient plus an
 * explicit TransactionTemplate, RLS bound inside the same transaction as the
 * work, and state transitions delegated to the migration-owned functions.</p>
 */
public final class JdbcObjectStorageStore implements S3ObjectStore.ObjectStorageMetadata {

    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;
    private final SecretResolver secrets;

    /** Resolves a {@code secret://} reference through the V9 secret lease authority. */
    public interface SecretResolver {
        SigV4Presigner.Credentials resolve(String reference);
    }

    public JdbcObjectStorageStore(JdbcClient jdbc, TransactionTemplate transactions, SecretResolver secrets) {
        this.jdbc = Objects.requireNonNull(jdbc);
        this.transactions = Objects.requireNonNull(transactions);
        this.secrets = Objects.requireNonNull(secrets);
    }

    // ---- backend resolution ------------------------------------------------

    /**
     * Loads the single ACTIVE (or READ_ONLY) backend. Returns a NOT_CONFIGURED
     * backend when none exists, so callers fail closed rather than falling back to
     * local disk.
     */
    public S3ObjectStore.Backend activeBackend() {
        Optional<S3ObjectStore.Backend> backend = jdbc.sql("""
                SELECT backend_id, backend_kind, endpoint, region, bucket, path_style,
                       server_side_encryption, cmk_reference, credential_reference,
                       backend_state, max_object_bytes
                  FROM object_storage_backends
                 WHERE backend_state IN ('ACTIVE', 'READ_ONLY')
                 ORDER BY CASE backend_state WHEN 'ACTIVE' THEN 0 ELSE 1 END
                 LIMIT 1
                """)
                .query((ResultSet rs, int row) -> new S3ObjectStore.Backend(
                        rs.getString("backend_id"),
                        rs.getString("backend_state"),
                        rs.getString("endpoint"),
                        rs.getString("bucket"),
                        rs.getString("region"),
                        rs.getBoolean("path_style"),
                        rs.getString("server_side_encryption"),
                        rs.getString("cmk_reference"),
                        rs.getLong("max_object_bytes"),
                        credentials(rs.getString("credential_reference"))))
                .optional();

        return backend.orElseGet(() -> new S3ObjectStore.Backend(
                "primary", "NOT_CONFIGURED", null, null, null, false,
                "NONE", null, 0, SigV4Presigner.Credentials.of("", "")));
    }

    private SigV4Presigner.Credentials credentials(String reference) {
        // The reference is resolved, never the value stored. A database dump alone
        // therefore does not yield object-store credentials.
        SigV4Presigner.Credentials credentials = secrets.resolve(reference);
        if (credentials == null
                || credentials.accessKeyId() == null
                || credentials.accessKeyId().isBlank()
                || credentials.secretAccessKey() == null
                || credentials.secretAccessKey().isBlank()) {
            throw new S3ObjectStore.ObjectStorageException("OBJECT_STORAGE_CREDENTIAL_MALFORMED");
        }
        return credentials;
    }

    // ---- ObjectStorageMetadata --------------------------------------------

    @Override
    public String registerPendingObject(String organizationId, String contentSha256, long byteSize,
                                        String mediaType, String backendId, String storageKey) {
        return inTenant(organizationId, () -> jdbc.sql("""
                INSERT INTO content_objects (
                    content_object_id, organization_id, content_sha256, byte_size,
                    media_type, backend_id, storage_key, object_state)
                VALUES (:id, :org, :sha, :size, :media, :backend, :key, 'PENDING_UPLOAD')
                ON CONFLICT (organization_id, content_sha256) DO UPDATE
                    SET media_type = EXCLUDED.media_type
                RETURNING content_object_id
                """)
                .param("id", "obj-" + UUID.randomUUID())
                .param("org", organizationId)
                .param("sha", contentSha256)
                .param("size", byteSize)
                .param("media", mediaType)
                .param("backend", backendId)
                .param("key", storageKey)
                .query(String.class).single());
    }

    @Override
    public void markAvailable(String organizationId, String contentObjectId) {
        inTenant(organizationId, () -> jdbc.sql("""
                UPDATE content_objects
                   SET object_state = 'AVAILABLE', uploaded_at = coalesce(uploaded_at, now()),
                       verified_at = now()
                 WHERE content_object_id = :id AND object_state = 'PENDING_UPLOAD'
                """)
                .param("id", contentObjectId)
                .update());
    }

    @Override
    public void markQuarantined(String organizationId, String contentObjectId, String reason) {
        inTenant(organizationId, () -> jdbc.sql("""
                UPDATE content_objects SET object_state = 'QUARANTINED'
                 WHERE content_object_id = :id AND object_state <> 'PURGED'
                """)
                .param("id", contentObjectId)
                .update());
    }

    // ---- artifact publication and download --------------------------------

    public String publishArtifact(String organizationId, String jobId, String role,
                                  String filename, String contentObjectId, String retentionClass) {
        return inTenant(organizationId, () -> jdbc.sql("""
                SELECT elmos_publish_job_artifact(
                    :artifactId, :org, :jobId, :role, :filename, :objectId, :retention)
                """)
                .param("artifactId", "art-" + UUID.randomUUID())
                .param("org", organizationId)
                .param("jobId", jobId)
                .param("role", role)
                .param("filename", filename)
                .param("objectId", contentObjectId)
                .param("retention", retentionClass == null ? "STANDARD" : retentionClass)
                .query(String.class).single());
    }

    /**
     * Newest live artifact for a job and role.
     *
     * <p>Scoped by organization even though RLS already applies: defence in depth
     * costs one predicate here and removes a whole class of mistake if a future
     * caller forgets to bind the tenant.</p>
     */
    public Optional<String> artifactIdFor(String organizationId, String jobId, String role) {
        return inTenant(organizationId, () -> jdbc.sql("""
                SELECT artifact_id FROM job_artifacts
                 WHERE organization_id = :org
                   AND job_id = :jobId
                   AND artifact_role = :role
                   AND deleted_at IS NULL
                 ORDER BY published_at DESC
                 LIMIT 1
                """)
                .param("org", organizationId)
                .param("jobId", jobId)
                .param("role", role)
                .query(String.class)
                .optional());
    }

    public record ArtifactSummary(
            String role,
            String filename,
            String contentSha256,
            long byteSize
    ) {
    }

    public List<ArtifactSummary> artifactsFor(String organizationId, String jobId) {
        return inTenant(organizationId, () -> jdbc.sql("""
                SELECT artifact.artifact_role,
                       artifact.filename,
                       content.content_sha256,
                       content.byte_size
                  FROM job_artifacts artifact
                  JOIN content_objects content
                    ON content.content_object_id = artifact.content_object_ref
                   AND content.organization_id = artifact.organization_id
                 WHERE artifact.organization_id = :org
                   AND artifact.job_id = :jobId
                   AND artifact.deleted_at IS NULL
                   AND content.object_state = 'AVAILABLE'
                 ORDER BY artifact.published_at, artifact.artifact_id
                """)
                .param("org", organizationId)
                .param("jobId", jobId)
                .query((ResultSet rs, int row) -> new ArtifactSummary(
                        rs.getString("artifact_role"),
                        rs.getString("filename"),
                        rs.getString("content_sha256"),
                        rs.getLong("byte_size")))
                .list());
    }

    public record GrantedDownload(String backendId, String storageKey, String contentSha256,
                                  long byteSize, String mediaType, String filename, Duration ttl) {
    }

    public record PendingPurge(
            String organizationId,
            String contentObjectId,
            String contentSha256
    ) {
    }

    public int expireArtifacts(String gcRunId, int batchLimit) {
        return jdbc.sql("SELECT elmos_expire_artifacts(:runId, :limit)")
                .param("runId", gcRunId)
                .param("limit", batchLimit)
                .query(Integer.class)
                .single();
    }

    public List<PendingPurge> pendingPurges(int batchLimit) {
        return jdbc.sql("SELECT * FROM elmos_pending_object_purges(:limit)")
                .param("limit", batchLimit)
                .query((ResultSet rs, int row) -> new PendingPurge(
                        rs.getString("organization_id"),
                        rs.getString("content_object_id"),
                        rs.getString("content_sha256")))
                .list();
    }

    public boolean confirmPurged(String organizationId, String contentObjectId) {
        Boolean confirmed = jdbc.sql("""
                SELECT elmos_confirm_object_purged(:organization, :object)
                """)
                .param("organization", organizationId)
                .param("object", contentObjectId)
                .query(Boolean.class)
                .single();
        return Boolean.TRUE.equals(confirmed);
    }

    public void finishGcRun(
            String gcRunId,
            int purgedCount,
            int purgeFailedCount
    ) {
        Boolean finished = jdbc.sql("""
                SELECT elmos_finish_object_gc(
                    :runId, :purged, :failed)
                """)
                .param("runId", gcRunId)
                .param("purged", purgedCount)
                .param("failed", purgeFailedCount)
                .query(Boolean.class)
                .single();
        if (!Boolean.TRUE.equals(finished)) {
            throw new IllegalStateException(
                    "OBJECT_GC_RUN_NOT_FINISHED");
        }
    }

    /**
     * Records the grant and returns what the caller needs to presign. The URL is
     * built outside the database and never stored - only who asked, for what, and
     * when it expires.
     */
    public GrantedDownload issueDownloadGrant(String organizationId, String artifactId,
                                              String actorId, int ttlSeconds) {
        return inTenant(organizationId, () -> jdbc.sql("""
                SELECT * FROM elmos_issue_download_grant(:grantId, :org, :artifactId, :actor, :ttl)
                """)
                .param("grantId", "grant-" + UUID.randomUUID())
                .param("org", organizationId)
                .param("artifactId", artifactId)
                .param("actor", actorId)
                .param("ttl", ttlSeconds)
                .query((ResultSet rs, int row) -> new GrantedDownload(
                        rs.getString("backend_id"),
                        rs.getString("storage_key"),
                        rs.getString("content_sha256"),
                        rs.getLong("byte_size"),
                        rs.getString("media_type"),
                        rs.getString("filename"),
                        Duration.ofSeconds(ttlSeconds)))
                .single());
    }

    /** Confirms the lease still owns the job before any artifact write is allowed. */
    public boolean leaseOwnsJob(String leaseId, String jobId, String tokenSha256) {
        Integer matches = jdbc.sql("""
                SELECT count(*) FROM runner_job_leases
                 WHERE runner_job_lease_id = :leaseId
                   AND job_ref = :jobId
                   AND token_sha256 = :tokenHash
                   AND lease_state IN ('ISSUED', 'ACTIVE')
                   AND expires_at > now()
                """)
                .param("leaseId", leaseId)
                .param("jobId", jobId)
                .param("tokenHash", tokenSha256)
                .query(Integer.class).single();
        return matches != null && matches > 0;
    }

    /** Resolves the organization for a lease without trusting anything the runner sent. */
    public Optional<String> organizationForLease(String leaseId) {
        return jdbc.sql("SELECT organization_id FROM runner_job_leases WHERE runner_job_lease_id = :leaseId")
                .param("leaseId", leaseId)
                .query(String.class).optional();
    }

    private <T> T inTenant(String organizationId, Supplier<T> work) {
        return transactions.execute(status -> {
            jdbc.sql("SELECT set_config('app.organization_id', :organization, true)")
                    .param("organization", organizationId).query(String.class).single();
            return work.get();
        });
    }

    private void inTenant(String organizationId, Runnable work) {
        inTenant(organizationId, () -> {
            work.run();
            return null;
        });
    }
}
