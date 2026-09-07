package io.elmos.productionruntime;

import io.elmos.storage.S3ObjectStore;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.Objects;
import java.util.UUID;
import java.util.function.Supplier;

/**
 * Tenant-bound metadata authority for content-addressed provider responses.
 * Object bytes cannot be published as an Artifact until S3 read-back has moved
 * this row from PENDING_UPLOAD to AVAILABLE.
 */
public final class JdbcProductionObjectStorageMetadata
        implements S3ObjectStore.ObjectStorageMetadata {
    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;

    public JdbcProductionObjectStorageMetadata(
            JdbcClient jdbc,
            TransactionTemplate transactions
    ) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.transactions = Objects.requireNonNull(transactions, "transactions");
    }

    @Override
    public String registerPendingObject(
            String organizationId,
            String contentSha256,
            long byteSize,
            String mediaType,
            String backendId,
            String storageKey
    ) {
        UUID tenantId = tenant(organizationId);
        if (contentSha256 == null || !contentSha256.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("contentSha256 must be lowercase SHA-256");
        }
        if (byteSize < 1) throw new IllegalArgumentException("byteSize must be positive");
        ProductionRuntimeModels.requireText(mediaType, "mediaType", 200);
        ProductionRuntimeModels.requireText(backendId, "backendId", 160);
        ProductionRuntimeModels.requireText(storageKey, "storageKey", 2_000);
        return inTenant(tenantId, () -> {
            jdbc.sql("""
                    insert into artifact.content_objects (
                        tenant_id, content_sha256, byte_size, media_type,
                        backend_id, storage_key, object_state
                    ) values (
                        :tenantId, :sha256, :byteSize, :mediaType,
                        :backendId, :storageKey, 'PENDING_UPLOAD'
                    )
                    on conflict (tenant_id, content_sha256) do nothing
                    """)
                    .param("tenantId", tenantId)
                    .param("sha256", contentSha256)
                    .param("byteSize", byteSize)
                    .param("mediaType", mediaType)
                    .param("backendId", backendId)
                    .param("storageKey", storageKey)
                    .update();
            Stored stored = jdbc.sql("""
                    select id, byte_size, media_type, backend_id, storage_key, object_state
                      from artifact.content_objects
                     where tenant_id = :tenantId and content_sha256 = :sha256
                     for update
                    """)
                    .param("tenantId", tenantId)
                    .param("sha256", contentSha256)
                    .query((rs, row) -> new Stored(
                            rs.getObject("id", UUID.class),
                            rs.getLong("byte_size"),
                            rs.getString("media_type"),
                            rs.getString("backend_id"),
                            rs.getString("storage_key"),
                            rs.getString("object_state")))
                    .single();
            if (stored.byteSize != byteSize
                    || !stored.mediaType.equals(mediaType)
                    || !stored.backendId.equals(backendId)
                    || !stored.storageKey.equals(storageKey)) {
                throw new ProductionRuntimeException(
                        "CONTENT_OBJECT_IDEMPOTENCY_CONFLICT",
                        "content digest was replayed with different object metadata");
            }
            if ("QUARANTINED".equals(stored.state)) {
                throw new ProductionRuntimeException(
                        "CONTENT_OBJECT_QUARANTINED",
                        "quarantined content cannot be silently reused");
            }
            return stored.id.toString();
        });
    }

    @Override
    public void markAvailable(String organizationId, String contentObjectId) {
        UUID tenantId = tenant(organizationId);
        UUID objectId = UUID.fromString(contentObjectId);
        inTenant(tenantId, () -> {
            int changed = jdbc.sql("""
                    update artifact.content_objects
                       set object_state = 'AVAILABLE', updated_at = now()
                     where tenant_id = :tenantId and id = :id
                       and object_state = 'PENDING_UPLOAD'
                    """)
                    .param("tenantId", tenantId).param("id", objectId).update();
            if (changed == 0
                    && state(tenantId, objectId).filter(value -> "AVAILABLE".equals(value)).isEmpty()) {
                throw new ProductionRuntimeException(
                        "CONTENT_OBJECT_STATE_CONFLICT",
                        "content object cannot transition to AVAILABLE");
            }
            return null;
        });
    }

    @Override
    public void markQuarantined(
            String organizationId,
            String contentObjectId,
            String reason
    ) {
        UUID tenantId = tenant(organizationId);
        UUID objectId = UUID.fromString(contentObjectId);
        ProductionRuntimeModels.requireText(reason, "quarantineReason", 500);
        inTenant(tenantId, () -> {
            int changed = jdbc.sql("""
                    update artifact.content_objects
                       set object_state = 'QUARANTINED',
                           quarantine_reason = :reason,
                           updated_at = now()
                     where tenant_id = :tenantId and id = :id
                       and object_state = 'PENDING_UPLOAD'
                    """)
                    .param("tenantId", tenantId)
                    .param("id", objectId)
                    .param("reason", reason)
                    .update();
            if (changed == 0) {
                var stored = jdbc.sql("""
                        select object_state, quarantine_reason
                          from artifact.content_objects
                         where tenant_id = :tenantId and id = :id
                        """)
                        .param("tenantId", tenantId).param("id", objectId)
                        .query((rs, row) -> new String[] {
                                rs.getString("object_state"),
                                rs.getString("quarantine_reason")})
                        .optional();
                if (stored.isEmpty()
                        || !"QUARANTINED".equals(stored.get()[0])
                        || !reason.equals(stored.get()[1])) {
                    throw new ProductionRuntimeException(
                            "CONTENT_OBJECT_STATE_CONFLICT",
                            "content object cannot transition to QUARANTINED");
                }
            }
            return null;
        });
    }

    private java.util.Optional<String> state(UUID tenantId, UUID objectId) {
        return jdbc.sql("""
                select object_state from artifact.content_objects
                 where tenant_id = :tenantId and id = :id
                """)
                .param("tenantId", tenantId).param("id", objectId)
                .query(String.class).optional();
    }

    private static UUID tenant(String value) {
        try {
            return UUID.fromString(Objects.requireNonNull(value, "organizationId"));
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("organizationId must be a tenant UUID", ex);
        }
    }

    private <T> T inTenant(UUID tenantId, Supplier<T> work) {
        return transactions.execute(status -> {
            jdbc.sql("select set_config('app.tenant_id', :tenantId, true)")
                    .param("tenantId", tenantId.toString()).query(String.class).single();
            return work.get();
        });
    }

    private record Stored(
            UUID id,
            long byteSize,
            String mediaType,
            String backendId,
            String storageKey,
            String state
    ) {}
}
