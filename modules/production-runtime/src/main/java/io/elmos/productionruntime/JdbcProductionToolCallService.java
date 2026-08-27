package io.elmos.productionruntime;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/** PostgreSQL-owned tool-call receipt service with explicit uncertain-outcome handling. */
public final class JdbcProductionToolCallService implements ProductionToolCallPort {
    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;
    private final ObjectMapper json;

    public JdbcProductionToolCallService(JdbcClient jdbc, TransactionTemplate transactions, ObjectMapper json) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.transactions = Objects.requireNonNull(transactions, "transactions");
        this.json = Objects.requireNonNull(json, "json");
    }

    @Override
    public ToolCallReceipt begin(ToolCallRequest request) {
        return inTenant(request.tenantId(), () -> {
            var existing = jdbc.sql("select id, status, provider_request_id from ai_usage.tool_calls where tenant_id = :tenantId and idempotency_key = :key for update")
                    .param("tenantId", request.tenantId()).param("key", request.idempotencyKey())
                    .query((rs, row) -> new Existing(rs.getObject("id", UUID.class), ToolCallStatus.valueOf(rs.getString("status")), rs.getString("provider_request_id"))).optional();
            if (existing.isPresent()) {
                var call = existing.get();
                var receipt = jdbc.sql("select request_hash, response_artifact_id from ai_usage.tool_call_receipts where tool_call_id = :id for update")
                        .param("id", call.id()).query((rs, row) -> new ExistingReceipt(rs.getString("request_hash"), rs.getObject("response_artifact_id", UUID.class))).optional()
                        .orElseThrow(() -> new ProductionRuntimeException("TOOL_CALL_RECEIPT_MISSING", "tool call has no durable receipt"));
                if (!receipt.requestHash().equals(request.requestHash())) throw new ProductionRuntimeException("TOOL_CALL_IDEMPOTENCY_CONFLICT", "tool call key has a different request hash");
                if (call.status() == ToolCallStatus.UNKNOWN || call.status() == ToolCallStatus.PROVIDER_ACCEPTED) throw new ProductionRuntimeException("TOOL_CALL_RECONCILIATION_REQUIRED", "tool outcome must be reconciled before retry");
                return new ToolCallReceipt(call.id(), call.status(), call.providerRequestId(), receipt.responseArtifactId());
            }
            UUID id = UUID.randomUUID();
            jdbc.sql("insert into ai_usage.tool_calls (id, tenant_id, account_id, project_id, job_id, stage_id, work_item_id, attempt_id, tool, idempotency_key) values (:id, :tenantId, :accountId, :projectId, :jobId, :stageId, :workItemId, :attemptId, :tool, :key)")
                    .param("id", id).param("tenantId", request.tenantId()).param("accountId", request.accountId()).param("projectId", request.projectId()).param("jobId", request.jobId()).param("stageId", request.stageId()).param("workItemId", request.workItemId()).param("attemptId", request.attemptId()).param("tool", request.tool()).param("key", request.idempotencyKey()).update();
            jdbc.sql("insert into ai_usage.tool_call_receipts (tool_call_id, tenant_id, request_hash, receipt_state) values (:id, :tenantId, :hash, 'CREATED')")
                    .param("id", id).param("tenantId", request.tenantId()).param("hash", request.requestHash()).update();
            return new ToolCallReceipt(id, ToolCallStatus.CREATED, null, null);
        });
    }

    @Override
    public void markProviderAccepted(UUID tenantId, UUID toolCallId, String providerRequestId) {
        inTenant(tenantId, () -> {
            requireProviderRequestId(providerRequestId);
            int count = jdbc.sql("update ai_usage.tool_calls set status = 'PROVIDER_ACCEPTED', provider_request_id = :providerId where tenant_id = :tenantId and id = :id and status = 'CREATED'")
                    .param("providerId", providerRequestId).param("tenantId", tenantId).param("id", toolCallId).update();
            if (count != 1) throw new ProductionRuntimeException("TOOL_CALL_STATE_CONFLICT", "tool call is not accepting a provider acknowledgement");
            jdbc.sql("update ai_usage.tool_call_receipts set receipt_state = 'PROVIDER_ACCEPTED', provider_request_id = :providerId, updated_at = now() where tenant_id = :tenantId and tool_call_id = :id")
                    .param("providerId", providerRequestId).param("tenantId", tenantId).param("id", toolCallId).update();
            return null;
        });
    }

    @Override
    public void markProviderUnknown(UUID tenantId, UUID toolCallId, String providerStatus) {
        inTenant(tenantId, () -> {
            jdbc.sql("update ai_usage.tool_calls set status = 'UNKNOWN' where tenant_id = :tenantId and id = :id and status in ('CREATED','PROVIDER_ACCEPTED')")
                    .param("tenantId", tenantId).param("id", toolCallId).update();
            jdbc.sql("update ai_usage.tool_call_receipts set receipt_state = 'UNKNOWN', last_provider_status = :status, updated_at = now() where tenant_id = :tenantId and tool_call_id = :id")
                    .param("tenantId", tenantId).param("id", toolCallId).param("status", bounded(providerStatus)).update();
            return null;
        });
    }

    @Override
    public void complete(UUID tenantId, UUID toolCallId, UUID responseArtifactId) {
        inTenant(tenantId, () -> {
            int count = jdbc.sql("update ai_usage.tool_calls set status = 'COMPLETE', completed_at = now() where tenant_id = :tenantId and id = :id and status = 'PROVIDER_ACCEPTED'")
                    .param("tenantId", tenantId).param("id", toolCallId).update();
            if (count != 1) throw new ProductionRuntimeException("TOOL_CALL_STATE_CONFLICT", "tool call is not ready for completion");
            jdbc.sql("update ai_usage.tool_call_receipts set receipt_state = 'COMPLETE', response_artifact_id = :artifactId, updated_at = now() where tenant_id = :tenantId and tool_call_id = :id")
                    .param("tenantId", tenantId).param("id", toolCallId).param("artifactId", responseArtifactId).update();
            outbox(tenantId, toolCallId, responseArtifactId);
            return null;
        });
    }

    private void outbox(UUID tenantId, UUID toolCallId, UUID artifactId) {
        try {
            jdbc.sql("insert into observability.outbox_events (tenant_id, aggregate_type, aggregate_id, event_type, payload) values (:tenantId, 'TOOL_CALL', :id, 'TOOL_CALL_COMPLETED', cast(:payload as jsonb))")
                    .param("tenantId", tenantId).param("id", toolCallId).param("payload", json.writeValueAsString(Map.of("responseArtifactId", artifactId))).update();
        } catch (Exception ex) { throw new ProductionRuntimeException("OUTBOX_SERIALIZATION_FAILED", "could not serialize tool call event", ex); }
    }

    private <T> T inTenant(UUID tenantId, java.util.function.Supplier<T> body) {
        return transactions.execute(status -> {
            jdbc.sql("select set_config('app.tenant_id', :tenantId, true)").param("tenantId", tenantId.toString()).query(String.class).single();
            return body.get();
        });
    }

    private static void requireProviderRequestId(String value) { if (value == null || value.isBlank() || value.length() > 500) throw new IllegalArgumentException("providerRequestId is required"); }
    private static String bounded(String value) { return value == null || value.isBlank() ? "UNSPECIFIED" : value.substring(0, Math.min(value.length(), 500)); }
    private record Existing(UUID id, ToolCallStatus status, String providerRequestId) {}
    private record ExistingReceipt(String requestHash, UUID responseArtifactId) {}
}
