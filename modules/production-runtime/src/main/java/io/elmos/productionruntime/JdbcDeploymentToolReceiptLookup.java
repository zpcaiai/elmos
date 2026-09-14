package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallStatus;
import java.util.Objects;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

/** Read-only lookup over the canonical tool ledger, using its existing tenant RLS context. */
public final class JdbcDeploymentToolReceiptLookup implements DeploymentToolExecutor.ReceiptLookup {
    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;

    public JdbcDeploymentToolReceiptLookup(JdbcClient jdbc, TransactionTemplate transactions) {
        this.jdbc = Objects.requireNonNull(jdbc);
        this.transactions = Objects.requireNonNull(transactions);
    }

    @Override public ToolCallReceipt find(ToolCallRequest request) {
        return transactions.execute(status -> {
            jdbc.sql("select set_config('app.tenant_id', :tenantId, true)")
                    .param("tenantId", request.tenantId().toString()).query(String.class).single();
            return jdbc.sql("""
                    select tc.*, r.request_hash, r.response_artifact_id, r.receipt_state,
                           r.provider_request_id as receipt_provider_id
                      from ai_usage.tool_calls tc
                      join ai_usage.tool_call_receipts r on r.tenant_id=tc.tenant_id and r.tool_call_id=tc.id
                     where tc.tenant_id=:tenantId and tc.idempotency_key=:key
                    """)
                    .param("tenantId", request.tenantId()).param("key", request.idempotencyKey())
                    .query((rs, row) -> {
                        boolean bound = request.accountId().equals(rs.getObject("account_id", UUID.class))
                                && request.projectId().equals(rs.getObject("project_id", UUID.class))
                                && request.jobId().equals(rs.getObject("job_id", UUID.class))
                                && request.stageId().equals(rs.getObject("stage_id", UUID.class))
                                && request.workItemId().equals(rs.getObject("work_item_id", UUID.class))
                                && request.attemptId().equals(rs.getObject("attempt_id", UUID.class))
                                && request.tool().equals(rs.getString("tool"))
                                && request.requestHash().equals(rs.getString("request_hash"));
                        if (!bound || !rs.getString("status").equals(rs.getString("receipt_state"))
                                || !Objects.equals(rs.getString("provider_request_id"),rs.getString("receipt_provider_id"))) {
                            throw new ProductionRuntimeException("DEPLOYMENT_TOOL_RECEIPT_CONFLICT",
                                    "canonical tool receipt does not match exact deployment context");
                        }
                        return new ToolCallReceipt(rs.getObject("id",UUID.class),
                                ToolCallStatus.valueOf(rs.getString("status")), rs.getString("provider_request_id"),
                                rs.getObject("response_artifact_id",UUID.class));
                    }).optional().orElse(null);
        });
    }
}
