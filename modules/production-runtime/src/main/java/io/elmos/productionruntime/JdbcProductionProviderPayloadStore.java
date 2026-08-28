package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallRequest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Objects;

/** PostgreSQL-backed, byte-exact provider request materialization store. */
public final class JdbcProductionProviderPayloadStore implements ProductionProviderPayloadPort {
    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;

    public JdbcProductionProviderPayloadStore(JdbcClient jdbc, TransactionTemplate transactions) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.transactions = Objects.requireNonNull(transactions, "transactions");
    }

    /**
     * Persists the exact request bytes before any provider side effect.
     * Reusing a digest with different bytes is rejected even if a caller has a
     * database role capable of bypassing the primary-key constraint.
     */
    public void persist(ModelCallRequest request, byte[] bytes) {
        Objects.requireNonNull(request, "request");
        var payload = new MaterializedPayload(bytes, "application/json");
        String actual = sha256(payload.bytes());
        if (!actual.equalsIgnoreCase(request.requestHash())) {
            throw new ProductionRuntimeException(
                    "PROVIDER_REQUEST_DIGEST_MISMATCH",
                    "provider request bytes do not match requestHash");
        }
        inTenant(request, () -> {
            var existing = jdbc.sql("""
                    select request_bytes
                      from ai_usage.model_call_request_payloads
                     where tenant_id = :tenantId and request_hash = :requestHash
                     for update
                    """)
                    .param("tenantId", request.tenantId())
                    .param("requestHash", actual)
                    .query(byte[].class)
                    .optional();
            if (existing.isPresent()) {
                if (!MessageDigest.isEqual(existing.get(), payload.bytes())) {
                    throw new ProductionRuntimeException(
                            "PROVIDER_REQUEST_HASH_COLLISION",
                            "stored provider request bytes differ for the same digest");
                }
                return null;
            }
            jdbc.sql("""
                    insert into ai_usage.model_call_request_payloads
                      (tenant_id, request_hash, provider, model, request_bytes, media_type, size_bytes)
                    values
                      (:tenantId, :requestHash, :provider, :model, :requestBytes, 'application/json', :sizeBytes)
                    """)
                    .param("tenantId", request.tenantId())
                    .param("requestHash", actual)
                    .param("provider", request.provider())
                    .param("model", request.model())
                    .param("requestBytes", payload.bytes())
                    .param("sizeBytes", payload.bytes().length)
                    .update();
            return null;
        });
    }

    @Override
    public MaterializedPayload materialize(ModelCallRequest request) {
        Objects.requireNonNull(request, "request");
        return inTenant(request, () -> jdbc.sql("""
                        select request_bytes, media_type, provider, model
                          from ai_usage.model_call_request_payloads
                         where tenant_id = :tenantId and request_hash = :requestHash
                        """)
                .param("tenantId", request.tenantId())
                .param("requestHash", request.requestHash().toLowerCase(java.util.Locale.ROOT))
                .query((rs, row) -> {
                    if (!request.provider().equals(rs.getString("provider"))
                            || !request.model().equals(rs.getString("model"))) {
                        throw new ProductionRuntimeException(
                                "PROVIDER_REQUEST_BINDING_MISMATCH",
                                "durable provider payload is bound to a different provider or model");
                    }
                    byte[] stored = rs.getBytes("request_bytes");
                    if (!sha256(stored).equalsIgnoreCase(request.requestHash())) {
                        throw new ProductionRuntimeException(
                                "PROVIDER_REQUEST_STORAGE_CORRUPT",
                                "durable provider payload no longer matches its digest");
                    }
                    return new MaterializedPayload(stored, rs.getString("media_type"));
                })
                .optional()
                .orElseThrow(() -> new ProductionRuntimeException(
                        "PROVIDER_REQUEST_NOT_MATERIALIZED",
                        "provider request bytes must be durably persisted before execution")));
    }

    private <T> T inTenant(ModelCallRequest request, java.util.function.Supplier<T> body) {
        return transactions.execute(status -> {
            jdbc.sql("select set_config('app.tenant_id', :tenantId, true)")
                    .param("tenantId", request.tenantId().toString())
                    .query(String.class)
                    .single();
            return body.get();
        });
    }

    public static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (java.security.NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
